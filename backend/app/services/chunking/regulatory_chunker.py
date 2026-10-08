"""Regulatory Content Chunker module.

Provides structure-aware, deterministic chunking for regulatory documents.
Converts parsed regulatory content into atomic, traceable RegulatoryChunk objects
ready for vector retrieval, comparison, and audit tracking.

Key Design Principles:
1. Structure-aware chunking, not arbitrary fixed-size text splitting.
2. Content integrity: `content` remains verbatim source text.
3. Context enrichment: `normalized_content` contains document/section breadcrumbs for search.
4. Granular typing: paragraph, bullet, numbered_item, table_row, structured_field, heading.
5. Sentence-boundary preservation: long paragraphs (>1,500 chars) split at sentence boundaries.
6. Deterministic, stable chunk identity based on document, section, order, and content hash.
7. Full traceability: document identity, section numbers, outline breadcrumbs, and provenance.
"""

import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from app.models.content import KeyInformation
from app.models.document import (
    CanonicalSectionConcept,
    RegulatoryChunk,
    RegulatoryChunkType,
    RegulatoryDocument,
    RegulatoryProvenance,
    RegulatorySection,
    RegulatoryTable,
    RegulatoryTableRow,
)
from app.services.chunking.outline_engine import HeadingInfo, RegulatoryOutlineEngine
from app.services.chunking.sentence_tokenizer import RegulatorySentenceTokenizer
from app.services.chunking.table_extractor import RegulatoryBulletExtractor, RegulatoryTableExtractor
from app.services.key_information_extractor import KeyInformationExtractor


class RegulatoryChunker:
    """Structure-aware regulatory content chunker preserving context and traceability."""

    # Default character threshold for paragraph splitting at sentence boundaries
    DEFAULT_MAX_CHUNK_CHARS = 1500
    # Minimum characters for a standalone paragraph chunk to avoid noisy fragments
    DEFAULT_MIN_CHUNK_CHARS = 25

    def __init__(
        self,
        max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
        sentence_overlap: int = 1,
        min_chunk_chars: int = DEFAULT_MIN_CHUNK_CHARS,
        extract_key_info: bool = True,
    ):
        self.max_chunk_chars = max_chunk_chars
        self.sentence_overlap = sentence_overlap
        self.min_chunk_chars = min_chunk_chars
        self.extract_key_info = extract_key_info

        self.tokenizer = RegulatorySentenceTokenizer()
        self.outline_engine = RegulatoryOutlineEngine()
        self.table_extractor = RegulatoryTableExtractor()
        self.bullet_extractor = RegulatoryBulletExtractor()
        self.info_extractor = KeyInformationExtractor() if extract_key_info else None

    @staticmethod
    def generate_chunk_id(
        document_id: str,
        section_id: str,
        chunk_type: str,
        order_index: int,
        content: str,
    ) -> str:
        """Generate a deterministic, stable chunk identifier.

        Guarantees that re-chunking the same document and section yields
        identical chunk IDs for auditability and idempotence.
        """
        seed = f"{document_id}:{section_id}:{chunk_type}:{order_index}:{content[:64]}"
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
        return f"chk_{digest}"

    def chunk_document(self, document: RegulatoryDocument) -> List[RegulatoryChunk]:
        """Chunk a complete RegulatoryDocument across all hierarchical sections.

        Populates `section.chunks` on each section and returns a flat list of
        all retrievable chunks.
        """
        all_chunks: List[RegulatoryChunk] = []

        doc_context = {
            "document_id": document.document_id,
            "document_fingerprint": document.document_fingerprint,
            "document_name": document.title,
            "document_type": document.document_type,
            "jurisdiction": document.jurisdiction,
            "product": document.product_name,
            "active_ingredient": document.active_ingredient,
            "source": document.provenance.source_repository,
            "source_identifier": document.provenance.source_identifier,
            "source_url": document.provenance.source_url,
            "version": document.version,
            "publication_date": document.effective_date or document.provenance.publication_date,
        }

        def process_section_tree(section: RegulatorySection, parent_path: str):
            current_path = f"{parent_path} > {section.section_number or ''} {section.heading_raw}".strip()
            # Chunk current section
            sec_chunks = self.chunk_section(section, doc_context, structure_prefix=parent_path)
            section.chunks = sec_chunks
            all_chunks.extend(sec_chunks)

            # Process subsections recursively
            for sub in section.subsections:
                process_section_tree(sub, current_path)

        for sec in document.sections:
            root_path = document.title or "Document"
            process_section_tree(sec, root_path)

        return all_chunks

    def chunk_section(
        self,
        section: RegulatorySection,
        doc_context: Optional[Dict[str, Any]] = None,
        structure_prefix: Optional[str] = None,
    ) -> List[RegulatoryChunk]:
        """Chunk a RegulatorySection into atomic RegulatoryChunk units.

        Extracts tables, bullet lists, structured fields, and sentence-bounded paragraphs.
        """
        raw_text = section.raw_text or ""
        if not raw_text.strip():
            return []

        doc_ctx = doc_context or {}
        document_id = doc_ctx.get("document_id", "doc_default")
        document_name = doc_ctx.get("document_name", "Document")
        section_id = section.section_id

        sec_title = section.heading_raw
        sec_num = section.section_number
        norm_sec = section.heading_normalized

        prefix = structure_prefix or document_name
        base_structure_path = f"{prefix} > {sec_num + ' ' if sec_num else ''}{sec_title}".strip()

        chunks: List[RegulatoryChunk] = []
        order_index = 0

        # 1. Extract Tables (Markdown and HTML)
        md_tables = self.table_extractor.extract_markdown_tables(raw_text, section_id=section_id)
        html_tables = self.table_extractor.extract_html_tables(raw_text, section_id=section_id)
        all_tables = md_tables + html_tables

        # Track text spans to exclude from paragraph chunking
        excluded_spans: List[Tuple[int, int]] = []
        for tbl in all_tables:
            if tbl.raw_markdown and tbl.raw_markdown in raw_text:
                start = raw_text.find(tbl.raw_markdown)
                excluded_spans.append((start, start + len(tbl.raw_markdown)))

            table_title = tbl.table_title or "Table"
            for row in tbl.rows:
                row_content = self.table_extractor.format_row_as_content(tbl, row)
                if not row_content.strip():
                    continue

                row_location = f"{table_title}, Row {row.row_index + 1}"
                row_path = f"{base_structure_path} > {table_title} > Row {row.row_index + 1}"
                norm_content = self._build_normalized_content(
                    chunk_content=row_content,
                    doc_name=document_name,
                    jurisdiction=doc_ctx.get("jurisdiction"),
                    active_ingredient=doc_ctx.get("active_ingredient"),
                    sec_num=sec_num,
                    sec_title=sec_title,
                    location=row_location,
                )

                chunk_id = self.generate_chunk_id(
                    document_id=document_id,
                    section_id=section_id,
                    chunk_type=RegulatoryChunkType.TABLE_ROW.value,
                    order_index=order_index,
                    content=row_content,
                )

                key_info = self._extract_key_info(row_content)

                chunk = RegulatoryChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    document_fingerprint=doc_ctx.get("document_fingerprint"),
                    section_id=section_id,
                    chunk_type=RegulatoryChunkType.TABLE_ROW.value,
                    order_index=order_index,
                    structure_path=row_path,
                    content=row_content,
                    normalized_content=norm_content,
                    document_name=document_name,
                    document_type=doc_ctx.get("document_type"),
                    jurisdiction=doc_ctx.get("jurisdiction"),
                    product=doc_ctx.get("product"),
                    active_ingredient=doc_ctx.get("active_ingredient"),
                    section_title=sec_title,
                    section_number=sec_num,
                    normalized_section=norm_sec,
                    key_information=key_info,
                    source=doc_ctx.get("source", "Internal"),
                    source_identifier=doc_ctx.get("source_identifier"),
                    source_url=doc_ctx.get("source_url"),
                    version=doc_ctx.get("version"),
                    publication_date=doc_ctx.get("publication_date"),
                    exact_location=row_location,
                    loinc_code=section.loinc_code,
                )
                chunks.append(chunk)
                order_index += 1

        # 2. Extract Bullet / Ordered List Groups
        bullet_groups = self.bullet_extractor.extract_bullets_and_lists(raw_text)
        for stem, items in bullet_groups:
            stem_chunk_id = None
            # If an introductory stem sentence exists, create a paragraph chunk for it
            if stem and len(stem.strip()) >= self.min_chunk_chars:
                stem_clean = stem.strip()
                stem_location = f"Paragraph (Stem)"
                stem_path = f"{base_structure_path} > Stem"
                norm_stem = self._build_normalized_content(
                    chunk_content=stem_clean,
                    doc_name=document_name,
                    jurisdiction=doc_ctx.get("jurisdiction"),
                    active_ingredient=doc_ctx.get("active_ingredient"),
                    sec_num=sec_num,
                    sec_title=sec_title,
                    location=stem_location,
                )
                stem_chunk_id = self.generate_chunk_id(
                    document_id=document_id,
                    section_id=section_id,
                    chunk_type=RegulatoryChunkType.PARAGRAPH.value,
                    order_index=order_index,
                    content=stem_clean,
                )
                stem_chunk = RegulatoryChunk(
                    chunk_id=stem_chunk_id,
                    document_id=document_id,
                    document_fingerprint=doc_ctx.get("document_fingerprint"),
                    section_id=section_id,
                    chunk_type=RegulatoryChunkType.PARAGRAPH.value,
                    order_index=order_index,
                    structure_path=stem_path,
                    content=stem_clean,
                    normalized_content=norm_stem,
                    document_name=document_name,
                    document_type=doc_ctx.get("document_type"),
                    jurisdiction=doc_ctx.get("jurisdiction"),
                    product=doc_ctx.get("product"),
                    active_ingredient=doc_ctx.get("active_ingredient"),
                    section_title=sec_title,
                    section_number=sec_num,
                    normalized_section=norm_sec,
                    key_information=self._extract_key_info(stem_clean),
                    source=doc_ctx.get("source", "Internal"),
                    source_identifier=doc_ctx.get("source_identifier"),
                    source_url=doc_ctx.get("source_url"),
                    version=doc_ctx.get("version"),
                    publication_date=doc_ctx.get("publication_date"),
                    exact_location=stem_location,
                    loinc_code=section.loinc_code,
                )
                chunks.append(stem_chunk)
                order_index += 1

            for item in items:
                item_content = item.content.strip()
                if not item_content:
                    continue

                item_location = f"List Item {item.marker}"
                item_path = f"{base_structure_path} > Item {item.marker}"
                norm_item = self._build_normalized_content(
                    chunk_content=f"{item.marker} {item_content}",
                    doc_name=document_name,
                    jurisdiction=doc_ctx.get("jurisdiction"),
                    active_ingredient=doc_ctx.get("active_ingredient"),
                    sec_num=sec_num,
                    sec_title=sec_title,
                    location=item_location,
                    stem_context=stem,
                )

                chunk_type = RegulatoryChunkType.BULLET.value if item.item_type == "bullet" else RegulatoryChunkType.NUMBERED_ITEM.value
                chunk_id = self.generate_chunk_id(
                    document_id=document_id,
                    section_id=section_id,
                    chunk_type=chunk_type,
                    order_index=order_index,
                    content=item_content,
                )

                item_chunk = RegulatoryChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    document_fingerprint=doc_ctx.get("document_fingerprint"),
                    section_id=section_id,
                    parent_chunk_id=stem_chunk_id,
                    chunk_type=chunk_type,
                    order_index=order_index,
                    structure_path=item_path,
                    content=item_content,
                    normalized_content=norm_item,
                    document_name=document_name,
                    document_type=doc_ctx.get("document_type"),
                    jurisdiction=doc_ctx.get("jurisdiction"),
                    product=doc_ctx.get("product"),
                    active_ingredient=doc_ctx.get("active_ingredient"),
                    section_title=sec_title,
                    section_number=sec_num,
                    normalized_section=norm_sec,
                    key_information=self._extract_key_info(item_content),
                    source=doc_ctx.get("source", "Internal"),
                    source_identifier=doc_ctx.get("source_identifier"),
                    source_url=doc_ctx.get("source_url"),
                    version=doc_ctx.get("version"),
                    publication_date=doc_ctx.get("publication_date"),
                    exact_location=item_location,
                    loinc_code=section.loinc_code,
                )
                chunks.append(item_chunk)
                order_index += 1

        # 3. Clean and isolate regular text paragraphs
        # If tables or bullet lists were extracted, exclude those lines to prevent duplication
        clean_paragraphs = self._extract_clean_paragraphs(raw_text, all_tables, bullet_groups)

        for p_idx, para in enumerate(clean_paragraphs):
            para_clean = para.strip()
            if not para_clean:
                continue

            # Check for structured field format: e.g. "NDC: 0000-0000" or "Route: Oral"
            is_structured = bool(re.match(r'^[A-Z0-9_\-\s]{2,30}\s*:\s*[^\n]+$', para_clean) and len(para_clean) < 120)
            if not is_structured and len(para_clean) < self.min_chunk_chars:
                continue

            if is_structured:
                field_location = f"Field ({para_clean.split(':')[0].strip()})"
                field_path = f"{base_structure_path} > {field_location}"
                norm_field = self._build_normalized_content(
                    chunk_content=para_clean,
                    doc_name=document_name,
                    jurisdiction=doc_ctx.get("jurisdiction"),
                    active_ingredient=doc_ctx.get("active_ingredient"),
                    sec_num=sec_num,
                    sec_title=sec_title,
                    location=field_location,
                )
                chunk_id = self.generate_chunk_id(
                    document_id=document_id,
                    section_id=section_id,
                    chunk_type=RegulatoryChunkType.STRUCTURED_FIELD.value,
                    order_index=order_index,
                    content=para_clean,
                )
                chunk = RegulatoryChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    document_fingerprint=doc_ctx.get("document_fingerprint"),
                    section_id=section_id,
                    chunk_type=RegulatoryChunkType.STRUCTURED_FIELD.value,
                    order_index=order_index,
                    structure_path=field_path,
                    content=para_clean,
                    normalized_content=norm_field,
                    document_name=document_name,
                    document_type=doc_ctx.get("document_type"),
                    jurisdiction=doc_ctx.get("jurisdiction"),
                    product=doc_ctx.get("product"),
                    active_ingredient=doc_ctx.get("active_ingredient"),
                    section_title=sec_title,
                    section_number=sec_num,
                    normalized_section=norm_sec,
                    key_information=self._extract_key_info(para_clean),
                    source=doc_ctx.get("source", "Internal"),
                    source_identifier=doc_ctx.get("source_identifier"),
                    source_url=doc_ctx.get("source_url"),
                    version=doc_ctx.get("version"),
                    publication_date=doc_ctx.get("publication_date"),
                    exact_location=field_location,
                    loinc_code=section.loinc_code,
                )
                chunks.append(chunk)
                order_index += 1
                continue

            # Standard paragraph processing: split at sentence boundaries if longer than max_chunk_chars
            sub_paragraphs = self._split_long_paragraph(para_clean)
            for sub_idx, sub_text in enumerate(sub_paragraphs):
                part_tag = f" (Part {sub_idx + 1})" if len(sub_paragraphs) > 1 else ""
                para_location = f"Paragraph {p_idx + 1}{part_tag}"
                para_path = f"{base_structure_path} > {para_location}"

                norm_para = self._build_normalized_content(
                    chunk_content=sub_text,
                    doc_name=document_name,
                    jurisdiction=doc_ctx.get("jurisdiction"),
                    active_ingredient=doc_ctx.get("active_ingredient"),
                    sec_num=sec_num,
                    sec_title=sec_title,
                    location=para_location,
                )

                chunk_id = self.generate_chunk_id(
                    document_id=document_id,
                    section_id=section_id,
                    chunk_type=RegulatoryChunkType.PARAGRAPH.value,
                    order_index=order_index,
                    content=sub_text,
                )

                chunk = RegulatoryChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    document_fingerprint=doc_ctx.get("document_fingerprint"),
                    section_id=section_id,
                    chunk_type=RegulatoryChunkType.PARAGRAPH.value,
                    order_index=order_index,
                    structure_path=para_path,
                    content=sub_text,
                    normalized_content=norm_para,
                    document_name=document_name,
                    document_type=doc_ctx.get("document_type"),
                    jurisdiction=doc_ctx.get("jurisdiction"),
                    product=doc_ctx.get("product"),
                    active_ingredient=doc_ctx.get("active_ingredient"),
                    section_title=sec_title,
                    section_number=sec_num,
                    normalized_section=norm_sec,
                    key_information=self._extract_key_info(sub_text),
                    source=doc_ctx.get("source", "Internal"),
                    source_identifier=doc_ctx.get("source_identifier"),
                    source_url=doc_ctx.get("source_url"),
                    version=doc_ctx.get("version"),
                    publication_date=doc_ctx.get("publication_date"),
                    exact_location=para_location,
                    loinc_code=section.loinc_code,
                )
                chunks.append(chunk)
                order_index += 1

        return chunks

    def chunk_text(
        self,
        text: str,
        document_id: str = "doc_default",
        document_name: Optional[str] = None,
        jurisdiction: str = "US_FDA",
        document_type: str = "REGULATORY_LABEL",
        product: Optional[str] = None,
        active_ingredient: Optional[str] = None,
        source: str = "Internal",
        provenance: Optional[RegulatoryProvenance] = None,
    ) -> List[RegulatoryChunk]:
        """Directly chunk raw regulatory text with automatic section outline detection."""
        clean_text = text.strip()
        if not clean_text:
            return []

        doc_name = document_name or "Regulatory Document"
        prov = provenance or RegulatoryProvenance(
            source_repository=source,
            source_identifier=document_id,
        )

        # 1. Parse text into sections using RegulatoryOutlineEngine
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

                    sec_tag = re.sub(r'[^a-zA-Z0-9]', '_', (sec_num or title).lower())[:20]
                    sec = RegulatorySection(
                        section_id=f"sec_{document_id}_{order_idx}_{sec_tag}",
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

            sec_tag = re.sub(r'[^a-zA-Z0-9]', '_', (sec_num or title).lower())[:20]
            sec = RegulatorySection(
                section_id=f"sec_{document_id}_{order_idx}_{sec_tag}",
                section_number=sec_num,
                heading_raw=title,
                heading_normalized=norm,
                order_index=order_idx,
                raw_text=body,
            )
            sections.append(sec)

        # Build document container
        doc = RegulatoryDocument(
            document_id=document_id,
            title=doc_name,
            document_type=document_type,
            jurisdiction=jurisdiction,
            product_name=product,
            active_ingredient=active_ingredient,
            provenance=prov,
            sections=sections,
            raw_content=clean_text,
        )

        return self.chunk_document(doc)

    def _split_long_paragraph(self, paragraph: str) -> List[str]:
        """Split a paragraph exceeding max_chunk_chars at sentence boundaries with controlled overlap."""
        if len(paragraph) <= self.max_chunk_chars:
            return [paragraph]

        sentences = self.tokenizer.tokenize(paragraph)
        if not sentences or len(sentences) <= 1:
            return [paragraph]

        chunks: List[str] = []
        current_sentences: List[str] = []
        current_len = 0

        for sentence in sentences:
            sentence_len = len(sentence)
            # If adding this sentence exceeds max_chunk_chars and we have at least one sentence
            if current_len + sentence_len > self.max_chunk_chars and current_sentences:
                chunks.append(" ".join(current_sentences))
                # Apply controlled sentence overlap
                if self.sentence_overlap > 0:
                    overlap_sentences = current_sentences[-self.sentence_overlap:]
                    current_sentences = list(overlap_sentences)
                    current_len = sum(len(s) for s in current_sentences) + len(current_sentences)
                else:
                    current_sentences = []
                    current_len = 0

            current_sentences.append(sentence)
            current_len += sentence_len + 1

        if current_sentences:
            chunks.append(" ".join(current_sentences))

        return chunks

    def _extract_clean_paragraphs(
        self,
        raw_text: str,
        tables: List[RegulatoryTable],
        bullet_groups: List[Tuple[Optional[str], Any]],
    ) -> List[str]:
        """Extract paragraphs while excluding lines belonging to tables and bullet lists."""
        text_copy = raw_text

        # 1. Remove table markdown blocks from paragraph stream
        for tbl in tables:
            if tbl.raw_markdown and tbl.raw_markdown in text_copy:
                text_copy = text_copy.replace(tbl.raw_markdown, "\n\n")

        # 2. Collect all bullet lines and stems to remove
        bullet_lines = set()
        for stem, items in bullet_groups:
            if stem:
                bullet_lines.add(stem.strip())
            for item in items:
                bullet_lines.add(item.raw_line.strip())

        filtered_lines = []
        for line in text_copy.splitlines():
            line_str = line.strip()
            if line_str in bullet_lines:
                continue
            filtered_lines.append(line)

        cleaned_text = "\n".join(filtered_lines)
        # Split on double newline paragraph boundaries
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', cleaned_text) if p.strip()]
        return paragraphs

    def _build_normalized_content(
        self,
        chunk_content: str,
        doc_name: str,
        jurisdiction: Optional[str] = None,
        active_ingredient: Optional[str] = None,
        sec_num: Optional[str] = None,
        sec_title: Optional[str] = None,
        location: Optional[str] = None,
        stem_context: Optional[str] = None,
    ) -> str:
        """Construct context-enriched normalized content for embedding/retrieval.

        Format:
        [Document: Title | Jurisdiction | Drug]
        [Section: Number Title > Location]
        Context stem (if bullet)
        Verbatim chunk content
        """
        doc_parts = [doc_name]
        if jurisdiction:
            doc_parts.append(jurisdiction)
        if active_ingredient:
            doc_parts.append(active_ingredient)
        doc_header = f"[Document: {' | '.join(doc_parts)}]"

        sec_name = f"{sec_num + ' ' if sec_num else ''}{sec_title or 'Section'}".strip()
        sec_parts = [sec_name]
        if location and location not in sec_name:
            sec_parts.append(location)
        sec_header = f"[Section: {' > '.join(sec_parts)}]"

        lines = [doc_header, sec_header]
        if stem_context:
            lines.append(stem_context.strip())
        lines.append(chunk_content.strip())

        return "\n".join(lines)

    def _extract_key_info(self, text: str) -> Optional[KeyInformation]:
        """Extract structured clinical entities using KeyInformationExtractor if enabled."""
        if not self.info_extractor:
            return None
        try:
            return self.info_extractor.extract(text)
        except Exception:
            return None
