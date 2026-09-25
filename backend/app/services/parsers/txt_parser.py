"""Plain text regulatory document parser.

Parses plain text regulatory documents, detecting section outlines and headings
using RegulatoryOutlineEngine while preserving exact source content, ordering,
and document-level metadata.
"""

from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from app.models.document import (
    CanonicalSectionConcept,
    RegulatoryDocument,
    RegulatoryProvenance,
    RegulatorySection,
)
from app.services.chunking.outline_engine import HeadingInfo, RegulatoryOutlineEngine
from app.services.parsers.base_parser import BaseDocumentParser


class TextDocumentParser(BaseDocumentParser):
    """Deterministic parser for plain text (.txt) regulatory documents."""

    def __init__(self):
        self.outline_engine = RegulatoryOutlineEngine()

    def can_parse(
        self,
        content: Union[str, bytes],
        filename: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> bool:
        """Check if content or file extension corresponds to plain text."""
        if filename and filename.lower().endswith(".txt"):
            return True
        if mime_type and mime_type.lower() in ("text/plain", "application/txt"):
            return True

        text = self.decode_content(content).strip()
        # If it doesn't look like JSON, XML, or HTML, treat as plain text
        if (
            not (text.startswith("{") and text.endswith("}"))
            and not (text.startswith("[") and text.endswith("]"))
            and not (text.startswith("<") and ">" in text)
            and not text.startswith("# ")
        ):
            return True
        return False

    def parse(
        self,
        content: Union[str, bytes],
        document_id: Optional[str] = None,
        document_name: Optional[str] = None,
        provenance: Optional[RegulatoryProvenance] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RegulatoryDocument:
        """Parse plain text content into a structured RegulatoryDocument."""
        raw_text = self.decode_content(content)
        clean_text = raw_text.strip()

        meta = metadata or {}
        doc_id = document_id or meta.get("document_id") or f"doc_{uuid4().hex[:10]}"
        doc_title = document_name or meta.get("document_name") or meta.get("title") or "Plain Text Document"
        doc_type = meta.get("document_type", "REGULATORY_LABEL")
        jurisdiction = meta.get("jurisdiction", "US_FDA")
        product = meta.get("product_name") or meta.get("product")
        drug = meta.get("active_ingredient") or meta.get("drug")
        version = meta.get("version", "1.0")

        prov = provenance or self.default_provenance(
            source_repo=meta.get("source", "InternalDraft"),
            identifier=meta.get("source_identifier", doc_id),
            url=meta.get("source_url"),
        )

        if not clean_text:
            return RegulatoryDocument(
                document_id=doc_id,
                title=doc_title,
                document_type=doc_type,
                jurisdiction=jurisdiction,
                product_name=product,
                active_ingredient=drug,
                version=version,
                provenance=prov,
                sections=[],
                raw_content="",
            )

        # Segment into sections using RegulatoryOutlineEngine
        lines = clean_text.splitlines()
        sections: List[RegulatorySection] = []
        current_heading: Optional[HeadingInfo] = None
        current_body_lines: List[str] = []
        order_idx = 0

        for line in lines:
            line_str = line.strip()
            heading_info = self.outline_engine.parse_heading(line_str, order_index=order_idx)

            if heading_info:
                # Flush previous section
                if current_heading or current_body_lines:
                    body = "\n".join(current_body_lines).strip()
                    title = current_heading.heading_raw if current_heading else "General Content"
                    sec_num = current_heading.section_number if current_heading else None
                    norm = current_heading.heading_normalized if current_heading else None

                    sec_slug = (sec_num or title).lower().replace(" ", "_")[:24]
                    sec = RegulatorySection(
                        section_id=f"sec_{doc_id}_{order_idx}_{sec_slug}",
                        section_number=sec_num,
                        heading_raw=title,
                        heading_normalized=norm,
                        order_index=order_idx,
                        raw_text=body,
                    )
                    sections.append(sec)
                    order_idx += 1
                    current_body_lines = []

                current_heading = heading_info
            else:
                current_body_lines.append(line)

        # Flush final section
        if current_heading or current_body_lines:
            body = "\n".join(current_body_lines).strip()
            title = current_heading.heading_raw if current_heading else "General Content"
            sec_num = current_heading.section_number if current_heading else None
            norm = current_heading.heading_normalized if current_heading else None

            sec_slug = (sec_num or title).lower().replace(" ", "_")[:24]
            sec = RegulatorySection(
                section_id=f"sec_{doc_id}_{order_idx}_{sec_slug}",
                section_number=sec_num,
                heading_raw=title,
                heading_normalized=norm,
                order_index=order_idx,
                raw_text=body,
            )
            sections.append(sec)

        return RegulatoryDocument(
            document_id=doc_id,
            title=doc_title,
            document_type=doc_type,
            jurisdiction=jurisdiction,
            product_name=product,
            active_ingredient=drug,
            version=version,
            provenance=prov,
            sections=sections,
            raw_content=raw_text,
        )
