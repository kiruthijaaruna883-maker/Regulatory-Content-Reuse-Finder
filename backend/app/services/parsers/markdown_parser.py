"""Markdown regulatory document parser.

Parses Markdown formatted regulatory dossiers, extracting headings (# through ######),
hierarchical subsections, markdown tables, bullet lists, and paragraphs.
"""

import re
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4

from app.models.document import (
    CanonicalSectionConcept,
    RegulatoryDocument,
    RegulatoryProvenance,
    RegulatorySection,
)
from app.services.chunking.outline_engine import HeadingInfo, RegulatoryOutlineEngine
from app.services.parsers.base_parser import BaseDocumentParser


class MarkdownDocumentParser(BaseDocumentParser):
    """Deterministic parser for Markdown (.md) regulatory documents."""

    def __init__(self):
        self.outline_engine = RegulatoryOutlineEngine()

    def can_parse(
        self,
        content: Union[str, bytes],
        filename: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> bool:
        """Evaluate if content or filename indicates Markdown format."""
        if filename and filename.lower().endswith((".md", ".markdown")):
            return True
        if mime_type and mime_type.lower() in ("text/markdown", "text/x-markdown"):
            return True

        text = self.decode_content(content).strip()
        # Heuristic: starts with or contains Markdown headers
        if re.search(r'(?m)^#{1,6}\s+', text):
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
        """Parse Markdown content into a hierarchical RegulatoryDocument."""
        raw_text = self.decode_content(content)
        clean_text = raw_text.strip()

        meta = metadata or {}
        doc_id = document_id or meta.get("document_id") or f"doc_{uuid4().hex[:10]}"
        doc_title = document_name or meta.get("document_name") or meta.get("title") or "Markdown Document"
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

        # Segment by Markdown headers (# through ######) and outline numbers
        lines = clean_text.splitlines()
        raw_sections_data: List[Dict[str, Any]] = []

        current_heading: Optional[HeadingInfo] = None
        current_body_lines: List[str] = []
        order_idx = 0

        for line in lines:
            line_str = line.strip()
            heading_info = None
            if line_str.startswith("#"):
                match = re.match(r'^(#{1,6})\s+(.*)$', line_str)
                if match:
                    hashes, title_text = match.groups()
                    level = len(hashes)
                    parsed_info = self.outline_engine.parse_heading(title_text, order_index=order_idx)
                    sec_num = parsed_info.section_number if parsed_info else None
                    norm = (
                        parsed_info.heading_normalized
                        if parsed_info
                        else self.outline_engine.normalize_concept(title_text)
                    )
                    heading_info = HeadingInfo(
                        section_number=sec_num,
                        heading_raw=line_str,
                        heading_normalized=norm,
                        level=level,
                        order_index=order_idx,
                    )

            if heading_info:
                # Flush previous section
                if current_heading or current_body_lines:
                    body = "\n".join(current_body_lines).strip()
                    title = current_heading.heading_raw if current_heading else "General Content"
                    sec_num = current_heading.section_number if current_heading else None
                    norm = current_heading.heading_normalized if current_heading else None
                    level = current_heading.level if current_heading else 1

                    raw_sections_data.append({
                        "heading_raw": title,
                        "section_number": sec_num,
                        "heading_normalized": norm,
                        "level": level,
                        "raw_text": body,
                        "order_index": order_idx,
                    })
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
            level = current_heading.level if current_heading else 1

            raw_sections_data.append({
                "heading_raw": title,
                "section_number": sec_num,
                "heading_normalized": norm,
                "level": level,
                "raw_text": body,
                "order_index": order_idx,
            })

        # Build hierarchical sections tree based on heading levels
        root_sections = self._build_hierarchical_sections(raw_sections_data, doc_id)

        # If title wasn't explicitly provided and first section is level 1 header, infer title
        if doc_title == "Markdown Document" and raw_sections_data and raw_sections_data[0]["level"] == 1:
            inferred_title = raw_sections_data[0]["heading_raw"].lstrip("#").strip()
            if inferred_title:
                doc_title = inferred_title

        return RegulatoryDocument(
            document_id=doc_id,
            title=doc_title,
            document_type=doc_type,
            jurisdiction=jurisdiction,
            product_name=product,
            active_ingredient=drug,
            version=version,
            provenance=prov,
            sections=root_sections,
            raw_content=raw_text,
        )

    def _build_hierarchical_sections(
        self,
        raw_sections_data: List[Dict[str, Any]],
        doc_id: str,
    ) -> List[RegulatorySection]:
        """Convert flat list of raw section dictionaries into nested RegulatorySection hierarchy."""
        if not raw_sections_data:
            return []

        root_sections: List[RegulatorySection] = []
        # Stack tracks (level, RegulatorySection)
        stack: List[Tuple[int, RegulatorySection]] = []

        for data in raw_sections_data:
            level = data["level"]
            sec_num = data["section_number"]
            title = data["heading_raw"]
            sec_slug = (sec_num or title).lower().replace(" ", "_")[:20]
            sec_id = f"sec_{doc_id}_{data['order_index']}_{sec_slug}"

            section = RegulatorySection(
                section_id=sec_id,
                section_number=sec_num,
                heading_raw=title,
                heading_normalized=data["heading_normalized"],
                order_index=data["order_index"],
                raw_text=data["raw_text"],
                subsections=[],
            )

            # Pop elements from stack that are deeper or at same level
            while stack and stack[-1][0] >= level:
                stack.pop()

            if stack:
                parent_sec = stack[-1][1]
                section.parent_section_id = parent_sec.section_id
                parent_sec.subsections.append(section)
            else:
                root_sections.append(section)

            stack.append((level, section))

        return root_sections
