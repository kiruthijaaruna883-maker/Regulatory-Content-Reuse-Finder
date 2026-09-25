"""JSON regulatory document parser.

Parses arbitrary valid JSON regulatory payloads without assuming a single fixed schema.
Preserves nested object/array structures, key/value relationships, and JSON path locations.
"""

import json
import re
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from app.models.document import (
    CanonicalSectionConcept,
    RegulatoryDocument,
    RegulatoryProvenance,
    RegulatorySection,
)
from app.services.chunking.outline_engine import RegulatoryOutlineEngine
from app.services.parsers.base_parser import BaseDocumentParser


class JsonDocumentParser(BaseDocumentParser):
    """Deterministic parser for structured JSON regulatory documents."""

    def __init__(self):
        self.outline_engine = RegulatoryOutlineEngine()

    def can_parse(
        self,
        content: Union[str, bytes],
        filename: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> bool:
        """Evaluate if content or filename indicates JSON format."""
        if filename and filename.lower().endswith(".json"):
            return True
        if mime_type and mime_type.lower() in ("application/json", "text/json"):
            return True

        text = self.decode_content(content).strip()
        if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
            try:
                json.loads(text)
                return True
            except Exception:
                return False
        return False

    def parse(
        self,
        content: Union[str, bytes],
        document_id: Optional[str] = None,
        document_name: Optional[str] = None,
        provenance: Optional[RegulatoryProvenance] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RegulatoryDocument:
        """Parse JSON content into a structured RegulatoryDocument container."""
        raw_text = self.decode_content(content)
        clean_text = raw_text.strip()

        if not clean_text:
            prov = provenance or self.default_provenance(identifier=document_id)
            return RegulatoryDocument(
                document_id=document_id or f"doc_{uuid4().hex[:10]}",
                title=document_name or "Empty JSON Document",
                provenance=prov,
                sections=[],
                raw_content="",
            )

        try:
            payload = json.loads(clean_text)
        except Exception as exc:
            raise ValueError(f"Invalid JSON content: {exc}") from exc

        meta = metadata or {}
        doc_id = document_id or meta.get("document_id")
        doc_title = document_name or meta.get("document_name") or meta.get("title")
        doc_type = meta.get("document_type", "REGULATORY_LABEL")
        jurisdiction = meta.get("jurisdiction", "US_FDA")
        product = meta.get("product_name") or meta.get("product")
        drug = meta.get("active_ingredient") or meta.get("drug")
        version = meta.get("version", "1.0")

        # 1. Extract metadata from openFDA format if detected: {"results": [{...}]}
        if isinstance(payload, dict) and "results" in payload and isinstance(payload["results"], list) and payload["results"]:
            target_obj = payload["results"][0]
            openfda = target_obj.get("openfda", {})
            doc_id = doc_id or target_obj.get("id") or target_obj.get("set_id")
            brand_names = openfda.get("brand_name", [])
            generic_names = openfda.get("generic_name", [])
            product = product or (brand_names[0] if brand_names else None)
            drug = drug or (generic_names[0] if generic_names else None)
            doc_title = doc_title or f"{product or drug or 'FDA'} Drug Label"
            payload = target_obj

        # 2. Extract standard administrative metadata if present in root object
        if isinstance(payload, dict):
            doc_id = doc_id or payload.get("document_id") or payload.get("id") or f"doc_{uuid4().hex[:10]}"
            doc_title = doc_title or payload.get("title") or payload.get("document_name") or "JSON Regulatory Document"
            doc_type = payload.get("document_type") or doc_type
            jurisdiction = payload.get("jurisdiction") or jurisdiction
            product = product or payload.get("product_name") or payload.get("product")
            drug = drug or payload.get("active_ingredient") or payload.get("drug")
            version = payload.get("version") or version
        else:
            doc_id = doc_id or f"doc_{uuid4().hex[:10]}"
            doc_title = doc_title or "JSON Regulatory Document"

        prov = provenance or self.default_provenance(
            source_repo=meta.get("source", "InternalDraft"),
            identifier=meta.get("source_identifier", doc_id),
            url=meta.get("source_url"),
        )

        # 3. Transform payload into sections preserving JSON path and key relationships
        sections: List[RegulatorySection] = []

        if isinstance(payload, list):
            # Array of items: e.g. [{"section": "...", "content": "..."}, ...]
            for idx, item in enumerate(payload):
                sec = self._parse_json_list_item(item, idx, doc_id)
                sections.append(sec)
        elif isinstance(payload, dict):
            # Object mapping: e.g. {"indications": "...", "dosage": "..."} or {"sections": [...]}
            if "sections" in payload and isinstance(payload["sections"], list):
                for idx, item in enumerate(payload["sections"]):
                    sec = self._parse_json_list_item(item, idx, doc_id)
                    sections.append(sec)
            else:
                # Key-value mapping
                order_idx = 0
                for key, val in payload.items():
                    # Skip administrative keys already parsed
                    if key.lower() in ("document_id", "id", "title", "document_name", "product_name", "product", "active_ingredient", "drug", "jurisdiction", "document_type", "version", "provenance", "openfda"):
                        continue

                    sec = self._parse_json_key_value(key, val, f"$.{key}", order_idx, doc_id)
                    if sec:
                        sections.append(sec)
                        order_idx += 1

        if not sections:
            # Fallback for empty or flat dictionary
            formatted_json = json.dumps(payload, indent=2)
            sections.append(
                RegulatorySection(
                    section_id=f"sec_{doc_id}_0_general",
                    heading_raw="General Content",
                    order_index=0,
                    raw_text=formatted_json,
                )
            )

        return RegulatoryDocument(
            document_id=doc_id,
            title=doc_title,
            document_type=doc_type,
            jurisdiction=jurisdiction,
            product_name=product,
            active_ingredient=drug,
            version=str(version),
            provenance=prov,
            sections=sections,
            raw_content=clean_text,
        )

    def _parse_json_list_item(self, item: Any, idx: int, doc_id: str) -> RegulatorySection:
        """Parse an individual item from a JSON array into a RegulatorySection."""
        sec_id = f"sec_{doc_id}_{idx}_item_{idx + 1}"
        if isinstance(item, dict):
            title = (
                item.get("section")
                or item.get("heading")
                or item.get("title")
                or item.get("name")
                or f"Section {idx + 1}"
            )
            sec_num = item.get("section_number") or item.get("number")
            raw_body = item.get("content") or item.get("text") or item.get("raw_text")

            if raw_body is None:
                # Format other keys as key-value lines
                lines = []
                for k, v in item.items():
                    if k not in ("section", "heading", "title", "name", "section_number", "number"):
                        lines.append(f"{k}: {v}")
                raw_body = "\n".join(lines)
            elif not isinstance(raw_body, str):
                raw_body = json.dumps(raw_body, indent=2)

            norm_concept = self.outline_engine.normalize_concept(title)
            return RegulatorySection(
                section_id=sec_id,
                section_number=str(sec_num) if sec_num else None,
                heading_raw=title,
                heading_normalized=norm_concept,
                order_index=idx,
                raw_text=raw_body,
            )
        else:
            return RegulatorySection(
                section_id=sec_id,
                heading_raw=f"Item {idx + 1}",
                order_index=idx,
                raw_text=str(item),
            )

    def _parse_json_key_value(
        self,
        key: str,
        val: Any,
        json_path: str,
        order_idx: int,
        doc_id: str,
    ) -> Optional[RegulatorySection]:
        """Convert a JSON key-value pair into a RegulatorySection."""
        # Convert snake_case or camelCase key to human-readable heading
        title = re.sub(r'[_]+', ' ', key).title()
        norm_concept = self.outline_engine.normalize_concept(title)
        sec_slug = re.sub(r'[^a-zA-Z0-9]', '_', key)[:20]
        sec_id = f"sec_{doc_id}_{order_idx}_{sec_slug}"

        if isinstance(val, str):
            raw_text = val.strip()
        elif isinstance(val, list):
            # If list of strings, join with newlines
            if all(isinstance(x, str) for x in val):
                raw_text = "\n".join(val)
            else:
                raw_text = json.dumps(val, indent=2)
        elif isinstance(val, dict):
            # Nested dictionary: format keys as structured lines preserving nested json path
            lines = [f"[JSON Path: {json_path}]"]
            for sub_k, sub_v in val.items():
                if isinstance(sub_v, (str, int, float, bool)):
                    lines.append(f"{sub_k}: {sub_v}")
                else:
                    lines.append(f"{sub_k}:\n{json.dumps(sub_v, indent=2)}")
            raw_text = "\n".join(lines)
        else:
            raw_text = f"{key}: {val}"

        if not raw_text:
            return None

        return RegulatorySection(
            section_id=sec_id,
            heading_raw=title,
            heading_normalized=norm_concept,
            order_index=order_idx,
            raw_text=raw_text,
        )
