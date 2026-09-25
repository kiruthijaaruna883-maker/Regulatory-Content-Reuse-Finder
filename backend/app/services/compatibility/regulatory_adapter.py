"""Compatibility adapters bridging Phase 2 regulatory models with existing GPR services.

Provides deterministic, bi-directional adapters between:
- Phase 2 models: RegulatoryDocument, RegulatorySection, RegulatoryChunk
- Existing models: RegulatoryContentItem

Preserves complete traceability, document hierarchy, source provenance,
structure paths, table/bullet contexts, page boundaries, and clinical entities
without fabricating missing values.
"""

import re
from typing import Any, Dict, List, Optional, Sequence, Union
from uuid import uuid4

from app.models.content import KeyInformation, RegulatoryContentItem
from app.models.document import (
    RegulatoryChunk,
    RegulatoryDocument,
    RegulatoryProvenance,
    RegulatorySection,
)


def _extract_page_number(
    exact_location: Optional[str],
    content: Optional[str] = None,
    explicit_page: Optional[int] = None,
) -> Optional[int]:
    """Deterministically resolve page number if present in attributes or text without fabricating."""
    if explicit_page is not None:
        return explicit_page
    if exact_location:
        m = re.search(r"(?:Page|Pages|p\.)\s*(\d+)", exact_location, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
    if content:
        m = re.search(r"^\[Page\s+(\d+)\]", content.strip(), re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
    return None


def _extract_table_context(
    chunk_type: Optional[str],
    exact_location: Optional[str],
    structure_path: Optional[str],
) -> Dict[str, Any]:
    """Extract table/row context from chunk location and path if available."""
    table_meta: Dict[str, Any] = {}
    if chunk_type == "table_row" or (exact_location and "table" in exact_location.lower()):
        if exact_location:
            # e.g. "Table 1, Row 3" or "Table: Dosage Adjustments, Row 2"
            m = re.search(r"^(.*?),\s*Row\s+(\d+)", exact_location, re.IGNORECASE)
            if m:
                table_meta["table_title"] = m.group(1).strip()
                try:
                    table_meta["row_index"] = int(m.group(2))
                except ValueError:
                    pass
        if "table_title" not in table_meta and structure_path:
            # Check structure path breadcrumb: e.g. "Doc > Sec > Table 1 > Row 2"
            parts = [p.strip() for p in structure_path.split(">")]
            for part in parts:
                if re.search(r"^table\b", part, re.IGNORECASE):
                    table_meta["table_title"] = part
                    break
    return table_meta


def chunk_to_content_item(chunk: RegulatoryChunk) -> RegulatoryContentItem:
    """Deterministically adapt a Phase 2 RegulatoryChunk into a legacy RegulatoryContentItem.

    Preserves:
    - Chunk identity (chunk_id -> content_id)
    - Document identity and name
    - Section and subsection outline titles
    - Exact source location and LOINC codes
    - Verbatim content (content -> text)
    - Granular chunk type (chunk_type -> content_type)
    - Inherited product and active ingredient (drug)
    - Clinical entities (KeyInformation)
    - Authoritative source repository, URL, identifier, version, and publication date
    - Hierarchy and structure path (in metadata)
    - Parent chunk relationship (parent_chunk_id in metadata)
    - Page boundaries (page field and metadata)
    - Table/row context (in metadata)

    Does not fabricate missing values.
    """
    # 1. Base metadata preservation
    meta: Dict[str, Any] = {
        "chunk_id": chunk.chunk_id,
        "section_id": chunk.section_id,
        "parent_chunk_id": chunk.parent_chunk_id,
        "chunk_type": chunk.chunk_type,
        "structure_path": chunk.structure_path,
        "normalized_content": chunk.normalized_content,
        "normalized_section": chunk.normalized_section,
        "jurisdiction": chunk.jurisdiction,
        "document_type": chunk.document_type,
        "order_index": chunk.order_index,
        "exact_location": chunk.exact_location,
        "loinc_code": chunk.loinc_code,
    }

    # 2. Page number resolution
    explicit_page = getattr(chunk, "page", None)
    page_num = _extract_page_number(
        exact_location=chunk.exact_location,
        content=chunk.content,
        explicit_page=explicit_page,
    )
    if page_num is not None:
        meta["page"] = page_num

    # 3. Table / row context preservation
    tbl_ctx = _extract_table_context(
        chunk_type=chunk.chunk_type,
        exact_location=chunk.exact_location,
        structure_path=chunk.structure_path,
    )
    if tbl_ctx:
        meta.update(tbl_ctx)

    # 4. Clinical entity mapping from KeyInformation
    key_info = chunk.key_information
    population = key_info.population if key_info else None
    indication = key_info.indication if key_info else None
    dose = key_info.dose if key_info else None
    frequency = key_info.frequency if key_info else None
    route = key_info.route if key_info else None
    purpose = key_info.purpose if key_info else None

    return RegulatoryContentItem(
        content_id=chunk.chunk_id,
        document_id=chunk.document_id,
        document_name=chunk.document_name,
        source=chunk.source,
        source_url=chunk.source_url,
        source_identifier=chunk.source_identifier,
        version=chunk.version,
        date=chunk.publication_date,
        section=chunk.section_title,
        subsection=chunk.section_number,
        page=page_num,
        location=chunk.exact_location,
        loinc_code=chunk.loinc_code,
        content_type=chunk.chunk_type,
        product=chunk.product,
        drug=chunk.active_ingredient,
        population=population,
        indication=indication,
        dose=dose,
        frequency=frequency,
        route=route,
        purpose=purpose,
        text=chunk.content,
        key_information=key_info,
        metadata=meta,
    )


def chunks_to_content_items(chunks: Sequence[RegulatoryChunk]) -> List[RegulatoryContentItem]:
    """Deterministically adapt a sequence of RegulatoryChunks to a list of RegulatoryContentItems."""
    return [chunk_to_content_item(chunk) for chunk in chunks]


def section_to_content_item(
    section: RegulatorySection,
    document: Optional[RegulatoryDocument] = None,
    parent_path: str = "",
) -> RegulatoryContentItem:
    """Deterministically adapt an unsegmented or section-level RegulatorySection into a RegulatoryContentItem.

    Useful when existing services consume document sections directly before chunking.
    """
    doc_id = document.document_id if document else None
    doc_name = document.title if document else None
    doc_version = document.version if document else None
    doc_type = document.document_type if document else None
    jurisdiction = document.jurisdiction if document else None
    product_name = document.product_name if document else None
    active_ingredient = document.active_ingredient if document else None
    app_number = document.application_number if document else None
    manufacturer = document.manufacturer if document else None

    # Source provenance
    if document and document.provenance:
        source_repo = document.provenance.source_repository
        source_url = document.provenance.source_url
        source_identifier = document.provenance.source_identifier
        pub_date = document.effective_date or document.provenance.publication_date
        exact_location = document.provenance.exact_location
        loinc_code = section.loinc_code or document.provenance.loinc_code
    else:
        source_repo = "InternalDraft"
        source_url = None
        source_identifier = None
        pub_date = None
        exact_location = None
        loinc_code = section.loinc_code

    curr_path = f"{parent_path} > {section.heading_raw}" if parent_path else section.heading_raw

    # Metadata dictionary preservation
    meta: Dict[str, Any] = {
        "section_id": section.section_id,
        "parent_section_id": section.parent_section_id,
        "section_number": section.section_number,
        "heading_raw": section.heading_raw,
        "heading_normalized": section.heading_normalized,
        "order_index": section.order_index,
        "structure_path": curr_path,
        "loinc_code": loinc_code,
    }
    if doc_type:
        meta["document_type"] = doc_type
    if jurisdiction:
        meta["jurisdiction"] = jurisdiction
    if app_number:
        meta["application_number"] = app_number
    if manufacturer:
        meta["manufacturer"] = manufacturer

    # Determine location string
    loc_str = f"Section {section.section_number}" if section.section_number else section.heading_raw
    if exact_location:
        loc_str = f"{loc_str} ({exact_location})"

    page_num = _extract_page_number(
        exact_location=exact_location,
        content=section.raw_text,
    )
    if page_num is not None:
        meta["page"] = page_num

    body_text = section.raw_text if section.raw_text is not None else section.heading_raw

    return RegulatoryContentItem(
        content_id=section.section_id,
        document_id=doc_id,
        document_name=doc_name,
        source=source_repo,
        source_url=source_url,
        source_identifier=source_identifier,
        version=doc_version,
        date=pub_date,
        section=section.heading_raw,
        subsection=section.section_number,
        page=page_num,
        location=loc_str,
        loinc_code=loinc_code,
        content_type="regulatory_section",
        product=product_name,
        drug=active_ingredient,
        text=body_text,
        metadata=meta,
    )


def _collect_chunks_recursive(sections: Sequence[RegulatorySection]) -> List[RegulatoryChunk]:
    """Recursively collect chunks from sections and child subsections maintaining order."""
    collected: List[RegulatoryChunk] = []
    for sec in sorted(sections, key=lambda s: s.order_index):
        if sec.chunks:
            collected.extend(sec.chunks)
        if sec.subsections:
            collected.extend(_collect_chunks_recursive(sec.subsections))
    return collected


def _collect_sections_recursive(
    sections: Sequence[RegulatorySection],
    document: RegulatoryDocument,
    parent_path: str = "",
) -> List[RegulatoryContentItem]:
    """Recursively adapt sections and subsections to RegulatoryContentItems."""
    items: List[RegulatoryContentItem] = []
    for sec in sorted(sections, key=lambda s: s.order_index):
        curr_path = f"{parent_path} > {sec.heading_raw}" if parent_path else sec.heading_raw
        items.append(section_to_content_item(sec, document=document, parent_path=parent_path))
        if sec.subsections:
            items.extend(_collect_sections_recursive(sec.subsections, document=document, parent_path=curr_path))
    return items


def document_to_content_items(
    document: RegulatoryDocument,
    chunk_if_empty: bool = False,
    chunker: Optional[Any] = None,
) -> List[RegulatoryContentItem]:
    """Deterministically adapt a Phase 2 RegulatoryDocument into a list of RegulatoryContentItems.

    Resolution strategy:
    1. If sections contain atomic chunks, converts all chunks across all sections/subsections.
    2. If sections have NO chunks and `chunk_if_empty=True`, runs RegulatoryChunker to populate
       chunks and converts them.
    3. If sections have NO chunks and `chunk_if_empty=False`, converts each section/subsection
       into a section-level RegulatoryContentItem.
    4. If the document has NO sections but has `raw_content`, converts the document into a
       single document-level RegulatoryContentItem.

    Preserves full document identity, hierarchy breadcrumbs, and provenance without inventing data.
    """
    # 1. Check for existing chunks in section tree
    existing_chunks = _collect_chunks_recursive(document.sections)
    if existing_chunks:
        return chunks_to_content_items(existing_chunks)

    # 2. Chunk on demand if requested and sections are unchunked
    if chunk_if_empty and document.sections:
        if chunker is None:
            from app.services.chunking.regulatory_chunker import RegulatoryChunker
            chunker = RegulatoryChunker()
        generated_chunks = chunker.chunk_document(document)
        return chunks_to_content_items(generated_chunks)

    # 3. Section-level adaptation if sections exist
    if document.sections:
        return _collect_sections_recursive(
            sections=document.sections,
            document=document,
            parent_path=document.title,
        )

    # 4. Fallback for sectionless document with raw_content
    if document.raw_content and document.raw_content.strip():
        prov = document.provenance
        meta: Dict[str, Any] = {
            "document_id": document.document_id,
            "document_type": document.document_type,
            "jurisdiction": document.jurisdiction,
            "application_number": document.application_number,
            "manufacturer": document.manufacturer,
            "version": document.version,
        }
        page_num = _extract_page_number(
            exact_location=prov.exact_location,
            content=document.raw_content,
        )
        if page_num is not None:
            meta["page"] = page_num

        return [
            RegulatoryContentItem(
                content_id=f"rc_{document.document_id}",
                document_id=document.document_id,
                document_name=document.title,
                source=prov.source_repository,
                source_url=prov.source_url,
                source_identifier=prov.source_identifier,
                version=document.version,
                date=document.effective_date or prov.publication_date,
                section="General Content",
                subsection=None,
                page=page_num,
                location=prov.exact_location,
                loinc_code=prov.loinc_code,
                content_type="general_regulatory_content",
                product=document.product_name,
                drug=document.active_ingredient,
                text=document.raw_content.strip(),
                metadata=meta,
            )
        ]

    return []


def content_item_to_chunk(item: RegulatoryContentItem) -> RegulatoryChunk:
    """Deterministically reverse-adapt a legacy RegulatoryContentItem into a Phase 2 RegulatoryChunk.

    Preserves:
    - Content ID to Chunk ID
    - Verbatim text content
    - Section outline numbers and titles
    - Source provenance attributes (repository, url, identifier, version, date)
    - LOINC codes and physical locations
    - Clinical KeyInformation entities
    - Structure path and parent chunk if present in metadata
    - Granular chunk type
    """
    meta = item.metadata or {}

    chunk_id = meta.get("chunk_id") or item.content_id
    doc_id = item.document_id or meta.get("document_id") or f"doc_{item.content_id}"
    sec_id = meta.get("section_id") or f"sec_{item.content_id}"
    parent_chunk_id = meta.get("parent_chunk_id")
    chunk_type = meta.get("chunk_type") or item.content_type or "paragraph"
    order_idx = meta.get("order_index", 0)

    # Reconstruct structure path if not already in metadata
    if "structure_path" in meta and meta["structure_path"]:
        structure_path = meta["structure_path"]
    else:
        path_parts = []
        if item.document_name:
            path_parts.append(item.document_name)
        if item.section:
            sec_label = f"{item.subsection} {item.section}".strip() if item.subsection else item.section
            path_parts.append(sec_label)
        if item.location and item.location != item.section:
            path_parts.append(item.location)
        structure_path = " > ".join(path_parts) if path_parts else (item.section or "Document")

    # Inherited document metadata
    doc_type = meta.get("document_type", "REGULATORY_LABEL")
    jurisdiction = meta.get("jurisdiction", "US_FDA")
    norm_content = meta.get("normalized_content")
    norm_section = meta.get("normalized_section")

    explicit_page = item.page or meta.get("page")
    page_num = _extract_page_number(
        exact_location=item.location,
        content=item.text,
        explicit_page=explicit_page,
    )

    return RegulatoryChunk(
        chunk_id=chunk_id,
        document_id=doc_id,
        section_id=sec_id,
        parent_chunk_id=parent_chunk_id,
        chunk_type=chunk_type,
        order_index=order_idx,
        structure_path=structure_path,
        content=item.text,
        normalized_content=norm_content,
        document_name=item.document_name,
        document_type=doc_type,
        jurisdiction=jurisdiction,
        product=item.product,
        active_ingredient=item.drug,
        section_title=item.section,
        section_number=item.subsection,
        normalized_section=norm_section,
        key_information=item.key_information,
        source=item.source,
        source_identifier=item.source_identifier,
        source_url=item.source_url,
        version=item.version,
        publication_date=item.date,
        exact_location=item.location,
        loinc_code=item.loinc_code,
        page=page_num,
    )


def content_items_to_document(
    items: Sequence[RegulatoryContentItem],
    document_id: Optional[str] = None,
    title: Optional[str] = None,
) -> RegulatoryDocument:
    """Deterministically reconstruct a hierarchical Phase 2 RegulatoryDocument from RegulatoryContentItems.

    Groups items by section title into RegulatorySections, with atomic items converted
    to RegulatoryChunks. Reconstructs authoritative provenance from items.
    """
    if not items:
        # Minimal empty document container
        doc_id = document_id or f"doc_{uuid4().hex[:10]}"
        doc_title = title or "Empty Regulatory Document"
        prov = RegulatoryProvenance(source_repository="InternalDraft")
        return RegulatoryDocument(
            document_id=doc_id,
            title=doc_title,
            provenance=prov,
            sections=[],
        )

    first_item = items[0]
    meta = first_item.metadata or {}

    doc_id = document_id or first_item.document_id or meta.get("document_id") or f"doc_{uuid4().hex[:10]}"
    doc_title = title or first_item.document_name or meta.get("document_name") or "Regulatory Document"
    doc_type = meta.get("document_type", "REGULATORY_LABEL")
    jurisdiction = meta.get("jurisdiction", "US_FDA")
    product_name = first_item.product
    active_ingredient = first_item.drug
    version = first_item.version or meta.get("version", "1.0")
    effective_date = first_item.date

    # Reconstruct provenance from first item with source information
    prov_source = first_item.source or "InternalDraft"
    prov = RegulatoryProvenance(
        source_repository=prov_source,
        source_identifier=first_item.source_identifier,
        source_url=first_item.source_url,
        version=version,
        publication_date=effective_date,
        exact_location=first_item.location,
        loinc_code=first_item.loinc_code,
    )

    # Group items by section in order of appearance
    sections_map: Dict[str, List[RegulatoryContentItem]] = {}
    section_order: List[str] = []

    for item in items:
        sec_name = item.section or "General Content"
        if sec_name not in sections_map:
            sections_map[sec_name] = []
            section_order.append(sec_name)
        sections_map[sec_name].append(item)

    sections: List[RegulatorySection] = []
    for s_idx, sec_name in enumerate(section_order):
        sec_items = sections_map[sec_name]
        first_sec_item = sec_items[0]
        sec_meta = first_sec_item.metadata or {}

        sec_id = sec_meta.get("section_id") or f"sec_{doc_id}_{s_idx + 1}"
        sec_num = first_sec_item.subsection or sec_meta.get("section_number")
        norm_sec = sec_meta.get("normalized_section")
        loinc = first_sec_item.loinc_code or sec_meta.get("loinc_code")

        # Convert contained items to chunks
        chunks = [content_item_to_chunk(it) for it in sec_items]

        # Combine text for section body
        combined_text = "\n\n".join(it.text for it in sec_items if it.text)

        section = RegulatorySection(
            section_id=sec_id,
            section_number=sec_num,
            heading_raw=sec_name,
            heading_normalized=norm_sec,
            order_index=s_idx,
            loinc_code=loinc,
            raw_text=combined_text if combined_text else None,
            chunks=chunks,
            subsections=[],
        )
        sections.append(section)

    return RegulatoryDocument(
        document_id=doc_id,
        title=doc_title,
        document_type=doc_type,
        jurisdiction=jurisdiction,
        product_name=product_name,
        active_ingredient=active_ingredient,
        version=version,
        effective_date=effective_date,
        provenance=prov,
        sections=sections,
    )


def adapt_for_retrieval(
    candidates: Union[
        RegulatoryDocument,
        RegulatoryChunk,
        RegulatoryContentItem,
        Sequence[Union[RegulatoryDocument, RegulatoryChunk, RegulatoryContentItem, Any]],
    ],
) -> List[RegulatoryContentItem]:
    """Deterministically adapt any Phase 2 model or collection into List[RegulatoryContentItem]
    ready for VectorStore indexing, similarity matching, and candidate ranking.
    """
    if isinstance(candidates, RegulatoryDocument):
        return document_to_content_items(candidates)
    elif isinstance(candidates, RegulatoryChunk):
        return [chunk_to_content_item(candidates)]
    elif isinstance(candidates, RegulatoryContentItem):
        return [candidates]
    elif isinstance(candidates, (list, tuple)):
        result: List[RegulatoryContentItem] = []
        for item in candidates:
            if isinstance(item, RegulatoryContentItem):
                result.append(item)
            elif isinstance(item, RegulatoryChunk):
                result.append(chunk_to_content_item(item))
            elif isinstance(item, RegulatoryDocument):
                result.extend(document_to_content_items(item))
            elif hasattr(item, "to_content_item"):
                result.append(item.to_content_item())
            else:
                raise TypeError(f"Cannot adapt unsupported object for retrieval: {type(item)}")
        return result
    elif hasattr(candidates, "to_content_item"):
        return [candidates.to_content_item()]
    else:
        raise TypeError(f"Cannot adapt unsupported object for retrieval: {type(candidates)}")


def adapt_for_comparison(
    item: Union[RegulatoryContentItem, RegulatoryChunk, Any],
) -> RegulatoryContentItem:
    """Deterministically adapt a candidate or target into a RegulatoryContentItem for comparison."""
    if isinstance(item, RegulatoryContentItem):
        return item
    elif isinstance(item, RegulatoryChunk):
        return chunk_to_content_item(item)
    elif hasattr(item, "to_content_item"):
        return item.to_content_item()
    raise TypeError(f"Cannot adapt candidate for comparison: unsupported type {type(item)}")
