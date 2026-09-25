"""PDF regulatory document parser.

Extracts text from PDF regulatory dossiers, preserving page boundaries, page-level
traceability, reading order, outline headings, paragraphs, and list structures.
Detects image-only / scanned PDFs gracefully without crashing.
"""

import io
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4

import pypdf

from app.models.document import (
    CanonicalSectionConcept,
    RegulatoryDocument,
    RegulatoryProvenance,
    RegulatorySection,
)
from app.services.chunking.outline_engine import HeadingInfo, RegulatoryOutlineEngine
from app.services.parsers.base_parser import BaseDocumentParser


class PdfDocumentParser(BaseDocumentParser):
    """Deterministic parser for PDF (.pdf) regulatory documents."""

    def __init__(self):
        self.outline_engine = RegulatoryOutlineEngine()

    def can_parse(
        self,
        content: Union[str, bytes],
        filename: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> bool:
        """Evaluate if content or filename indicates PDF format."""
        if filename and filename.lower().endswith(".pdf"):
            return True
        if mime_type and mime_type.lower() in ("application/pdf", "application/x-pdf"):
            return True

        if isinstance(content, (bytes, bytearray)):
            return content.startswith(b"%PDF-")
        elif isinstance(content, str):
            return content.strip().startswith("%PDF-")
        return False

    def parse(
        self,
        content: Union[str, bytes],
        document_id: Optional[str] = None,
        document_name: Optional[str] = None,
        provenance: Optional[RegulatoryProvenance] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RegulatoryDocument:
        """Parse PDF content into a structured RegulatoryDocument container."""
        pdf_bytes = self._to_bytes(content)

        meta = metadata or {}
        doc_id = document_id or meta.get("document_id") or f"doc_{uuid4().hex[:10]}"
        doc_title = document_name or meta.get("document_name") or meta.get("title")
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

        if not pdf_bytes or len(pdf_bytes.strip()) == 0:
            prov.exact_location = "Pages: 0"
            return RegulatoryDocument(
                document_id=doc_id,
                title=doc_title or "Empty PDF Document",
                document_type=doc_type,
                jurisdiction=jurisdiction,
                product_name=product,
                active_ingredient=drug,
                version=version,
                provenance=prov,
                sections=[],
                raw_content="",
            )

        try:
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        except Exception as exc:
            raise ValueError(f"Invalid PDF content: {exc}") from exc

        # Handle encrypted PDFs
        if reader.is_encrypted:
            try:
                decrypt_res = reader.decrypt("")
                if decrypt_res == pypdf.constants.PasswordResult.NOT_DECRYPTED:
                    raise ValueError("Encrypted PDF document requires a password")
            except Exception as exc:
                raise ValueError(f"Encrypted PDF document cannot be decrypted: {exc}") from exc

        num_pages = len(reader.pages)
        if num_pages == 0:
            prov.exact_location = "Pages: 0"
            return RegulatoryDocument(
                document_id=doc_id,
                title=doc_title or "Empty PDF Document",
                document_type=doc_type,
                jurisdiction=jurisdiction,
                product_name=product,
                active_ingredient=drug,
                version=version,
                provenance=prov,
                sections=[],
                raw_content="",
            )

        # Extract PDF metadata if available
        pdf_info = {}
        if reader.metadata:
            for k, v in reader.metadata.items():
                clean_k = str(k).lstrip("/").lower()
                if v:
                    pdf_info[clean_k] = str(v)
            if not doc_title and pdf_info.get("title"):
                doc_title = pdf_info["title"]

        if not doc_title:
            doc_title = "PDF Regulatory Document"

        # Check for scanned / image-only PDF where no digital text is extracted
        page_texts: List[Tuple[int, str]] = []
        total_extracted_chars = 0

        for idx, page in enumerate(reader.pages):
            page_num = idx + 1
            try:
                txt = page.extract_text() or ""
            except Exception:
                txt = ""
            clean_page_txt = txt.strip()
            total_extracted_chars += len(clean_page_txt)
            page_texts.append((page_num, clean_page_txt))

        # Scanned PDF handling: preserve page metadata without fabricating text
        if total_extracted_chars == 0 and num_pages > 0:
            scanned_sections: List[RegulatorySection] = []
            for page_num, _ in page_texts:
                sec_id = f"sec_{doc_id}_p{page_num}_scanned"
                scanned_sections.append(
                    RegulatorySection(
                        section_id=sec_id,
                        heading_raw=f"Page {page_num} (Scanned)",
                        order_index=page_num - 1,
                        raw_text=f"[Scanned PDF Page {page_num}: No digital text layer detected. Image-only PDF.]",
                    )
                )

            prov.exact_location = f"Pages: {num_pages} (Scanned)"
            return RegulatoryDocument(
                document_id=doc_id,
                title=doc_title,
                document_type=doc_type,
                jurisdiction=jurisdiction,
                product_name=product,
                active_ingredient=drug,
                version=version,
                provenance=prov,
                sections=scanned_sections,
                raw_content="[Scanned image-only PDF: digital text extraction unavailable]",
            )

        # Standard digital text extraction: detect headings and preserve page numbers
        sections: List[RegulatorySection] = []
        raw_content_blocks: List[str] = []

        current_heading: Optional[HeadingInfo] = None
        current_body_lines: List[str] = []
        current_start_page: int = 1
        order_idx = 0

        for page_num, text in page_texts:
            if not text:
                continue

            raw_content_blocks.append(f"--- [Page {page_num}] ---\n{text}")
            lines = text.splitlines()

            for line in lines:
                line_str = line.strip()
                if not line_str:
                    continue

                heading_info = self.outline_engine.parse_heading(line_str, order_index=order_idx)

                if heading_info:
                    # Flush previous section
                    if current_heading or current_body_lines:
                        sec = self._create_section(
                            doc_id=doc_id,
                            heading=current_heading,
                            body_lines=current_body_lines,
                            order_index=order_idx,
                            page_num=current_start_page,
                        )
                        sections.append(sec)
                        order_idx += 1
                        current_body_lines = []

                    current_heading = heading_info
                    current_start_page = page_num
                else:
                    # Tag page boundary if transitioning to a new page within a section
                    if not current_body_lines and current_heading is None:
                        current_start_page = page_num
                    current_body_lines.append(line)

        # Flush final section
        if current_heading or current_body_lines:
            sec = self._create_section(
                doc_id=doc_id,
                heading=current_heading,
                body_lines=current_body_lines,
                order_index=order_idx,
                page_num=current_start_page,
            )
            sections.append(sec)

        # If no headings were identified, group by page
        if not sections and page_texts:
            for page_num, text in page_texts:
                if text:
                    sec_id = f"sec_{doc_id}_p{page_num}"
                    sections.append(
                        RegulatorySection(
                            section_id=sec_id,
                            heading_raw=f"Page {page_num}",
                            order_index=page_num - 1,
                            raw_text=f"[Page {page_num}]\n{text}",
                        )
                    )

        combined_raw = "\n\n".join(raw_content_blocks)
        prov.exact_location = f"Pages: {num_pages}"

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
            raw_content=combined_raw,
        )

    def _create_section(
        self,
        doc_id: str,
        heading: Optional[HeadingInfo],
        body_lines: List[str],
        order_index: int,
        page_num: int,
    ) -> RegulatorySection:
        """Create a RegulatorySection preserving page traceability."""
        title = heading.heading_raw if heading else f"General Content (Page {page_num})"
        sec_num = heading.section_number if heading else None
        norm = heading.heading_normalized if heading else None

        sec_slug = re.sub(r'[^a-zA-Z0-9]', '_', (sec_num or title).lower())[:20]
        sec_id = f"sec_{doc_id}_{order_index}_p{page_num}_{sec_slug}"

        body_text = "\n".join(body_lines).strip()
        # Add page breadcrumb if not already marked
        if not body_text.startswith(f"[Page {page_num}]"):
            body_text = f"[Page {page_num}]\n{body_text}"

        return RegulatorySection(
            section_id=sec_id,
            section_number=sec_num,
            heading_raw=title,
            heading_normalized=norm,
            order_index=order_index,
            raw_text=body_text,
        )

    @staticmethod
    def _to_bytes(content: Union[str, bytes]) -> bytes:
        """Safely convert string or bytes input to raw bytes."""
        if isinstance(content, (bytes, bytearray)):
            return bytes(content)
        if isinstance(content, str):
            try:
                return content.encode("latin-1")
            except Exception:
                return content.encode("utf-8", errors="replace")
        return bytes(content)
