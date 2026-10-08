"""Document ingestion and candidate discovery routes module.

Exposes endpoints for:
1. POST /documents/ingest: Ingest multi-format regulatory documents (TXT, MD, JSON, XML, HTML, PDF, DOC, DOCX)
   or pasted text into the Phase 3 candidate store.
2. POST /candidates/search: On-demand candidate discovery across ingested documents and live sources
   (DailyMed, openFDA) with cross-source deduplication and full Phase 3 Step 4 traceability.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status

from app.models.content import KeyInformation, RegulatorySearchResult
from app.models.ingest import CandidateSearchRequest, DocumentIngestResponse
from app.services.candidate_store import get_candidate_store
from app.services.ingestion.unified_ingestion import ingest_and_chunk_document
from app.services.rag_retriever import LiveRAGRetriever

logger = logging.getLogger("candidate_discovery")

router = APIRouter(tags=["Document Ingestion & Candidate Discovery"])

ALLOWED_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".pdf",
    ".docx",
    ".doc",
}

ALLOWED_SOURCE_FILTERS = {"all", "ingested", "internal", "dailymed", "openfda"}

retriever = LiveRAGRetriever()


@router.post(
    "/documents/ingest",
    response_model=DocumentIngestResponse,
    summary="Ingest regulatory document or pasted text into candidate store",
)
async def ingest_regulatory_document(
    request: Request,
    file: Optional[UploadFile] = File(None),
    pasted_text: Optional[str] = Form(None),
    document_name: Optional[str] = Form(None),
    document_type: Optional[str] = Form("REGULATORY_LABEL"),
    jurisdiction: Optional[str] = Form("US_FDA"),
    product_name: Optional[str] = Form(None),
    active_ingredient: Optional[str] = Form(None),
    version: Optional[str] = Form("1.0"),
) -> DocumentIngestResponse:
    """Ingest a multi-format regulatory document or pasted text.

    Parses the document hierarchy, chunks it with RegulatoryChunker, and registers
    chunks in the session candidate store for reuse discovery.
    """
    # 1. Fallback inspection for JSON requests
    effective_pasted_text = pasted_text
    effective_doc_name = document_name
    effective_doc_type = document_type or "REGULATORY_LABEL"
    effective_jurisdiction = jurisdiction or "US_FDA"
    effective_product = product_name
    effective_ingredient = active_ingredient
    effective_version = version or "1.0"

    if file is None and (effective_pasted_text is None or not effective_pasted_text.strip()):
        ct = request.headers.get("content-type", "")
        if "application/json" in ct:
            try:
                body = await request.json()
                if isinstance(body, dict):
                    if "pasted_text" in body or "content" in body or "text" in body:
                        pasted_val = body.get("pasted_text") or body.get("content") or body.get("text")
                        if pasted_val is not None:
                            effective_pasted_text = pasted_val
                    effective_doc_name = effective_doc_name or body.get("document_name")
                    effective_doc_type = body.get("document_type") or effective_doc_type
                    effective_jurisdiction = body.get("jurisdiction") or effective_jurisdiction
                    effective_product = effective_product or body.get("product_name")
                    effective_ingredient = effective_ingredient or body.get("active_ingredient")
                    effective_version = body.get("version") or effective_version
            except Exception:
                pass

    # 2. Validation: Neither file nor pasted text provided
    if file is None and effective_pasted_text is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either file or pasted_text must be provided",
        )

    # 3. Validation: Empty pasted text
    if file is None and effective_pasted_text is not None:
        if not effective_pasted_text.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document content cannot be empty",
            )
        content_to_ingest = effective_pasted_text
        filename = "pasted_content.txt"
        mime_type = "text/plain"
        if not effective_doc_name:
            effective_doc_name = "Pasted Regulatory Content"

    # 4. Validation: File upload checks
    if file is not None:
        raw_bytes = await file.read()
        if len(raw_bytes) == 0 or (not raw_bytes.strip() and isinstance(raw_bytes, (str, bytes))):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document content cannot be empty",
            )

        filename = file.filename or "uploaded_document"
        ext = Path(filename).suffix.lower()
        if ext and ext not in ALLOWED_EXTENSIONS:
            supported = ", ".join(sorted(list(ALLOWED_EXTENSIONS)))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported document format '{ext}'. Supported formats are: {supported}",
            )

        content_to_ingest = raw_bytes
        mime_type = file.content_type
        if not effective_doc_name:
            effective_doc_name = Path(filename).stem.replace("_", " ").title()

    # 5. Metadata dictionary construction
    meta: Dict[str, Any] = {
        "document_type": effective_doc_type,
        "jurisdiction": effective_jurisdiction,
        "product_name": effective_product,
        "active_ingredient": effective_ingredient,
        "version": effective_version,
        "source": "InternalDraft",
    }

    # 6. Parse and chunk document
    try:
        doc, chunks = ingest_and_chunk_document(
            content=content_to_ingest,
            filename=filename,
            mime_type=mime_type,
            document_name=effective_doc_name,
            metadata=meta,
        )
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )
    except Exception as exc:
        logger.error("Document ingestion error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document parsing error: {str(exc)}",
        )

    # 6b. Automatic metadata extraction if not explicitly supplied by reviewer
    needs_product = not effective_product
    needs_ingredient = not effective_ingredient
    if (needs_product or needs_ingredient) and (doc.raw_content or chunks):
        from app.services.key_information_extractor import KeyInformationExtractor

        sample_text = doc.raw_content or " ".join(c.content for c in chunks[:5])
        extractor = KeyInformationExtractor()
        extracted_info = extractor.extract(sample_text)

        if needs_product and (extracted_info.product or extracted_info.drug):
            auto_product = extracted_info.product or extracted_info.drug
            doc.product_name = auto_product
            for chk in chunks:
                if not chk.product:
                    chk.product = auto_product

        if needs_ingredient and (extracted_info.active_ingredient or extracted_info.drug):
            auto_ingredient = extracted_info.active_ingredient or extracted_info.drug
            doc.active_ingredient = auto_ingredient
            for chk in chunks:
                if not chk.active_ingredient:
                    chk.active_ingredient = auto_ingredient

    # 7. Register in candidate store and retain original source bytes
    source_bytes_to_retain: Optional[bytes] = None
    if file is not None and isinstance(content_to_ingest, (bytes, bytearray)):
        source_bytes_to_retain = bytes(content_to_ingest)
    elif effective_pasted_text is not None:
        source_bytes_to_retain = effective_pasted_text.encode("utf-8")

    file_format_to_retain: Optional[str] = None
    if filename and "." in filename:
        file_format_to_retain = Path(filename).suffix.lower().lstrip(".")

    store = get_candidate_store()
    store.add_document(
        doc,
        chunks,
        source_bytes=source_bytes_to_retain,
        filename=filename,
        file_format=file_format_to_retain,
        mime_type=mime_type,
    )

    # 8. Retrieve registered candidate content items as sections
    content_items = store.list_content_items(doc.document_id)

    if not chunks:
        return DocumentIngestResponse(
            document_id=doc.document_id,
            document_fingerprint=doc.document_fingerprint,
            document_name=doc.title,
            document_type=doc.document_type,
            jurisdiction=doc.jurisdiction,
            sections_count=len(doc.sections),
            chunks_count=0,
            sections=[],
            source_repository=doc.provenance.source_repository if doc.provenance else "InternalDraft",
            message="Document ingested successfully, but produced 0 usable regulatory candidate chunks.",
        )

    return DocumentIngestResponse(
        document_id=doc.document_id,
        document_fingerprint=doc.document_fingerprint,
        document_name=doc.title,
        document_type=doc.document_type,
        jurisdiction=doc.jurisdiction,
        sections_count=len(doc.sections),
        chunks_count=len(chunks),
        sections=content_items,
        source_repository=doc.provenance.source_repository if doc.provenance else "InternalDraft",
        message=f"Successfully ingested and registered {len(chunks)} candidate chunk(s).",
    )


@router.post(
    "/candidates/search",
    response_model=RegulatorySearchResult,
    summary="Discover candidates across ingested documents and live sources",
)
async def search_candidates(payload: CandidateSearchRequest) -> RegulatorySearchResult:
    """Query candidates across ingested candidate store and live trusted sources.

    Preserves full Phase 3 Step 4 traceability and applies cross-source deduplication.
    """
    clean_query = (payload.query or "").strip()
    if not clean_query and payload.target_text and payload.target_text.strip():
        from app.services.key_information_extractor import KeyInformationExtractor
        _extractor = KeyInformationExtractor()
        _extracted = _extractor.extract(payload.target_text)
        clean_query = _extracted.drug or _extracted.active_ingredient or _extracted.indication or (payload.section or "").strip()
        if not clean_query:
            _words = [w for w in payload.target_text.split() if len(w) > 3 and w.isalpha()]
            clean_query = " ".join(_words[:3]) if _words else payload.target_text[:40].strip()

    if not clean_query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search query cannot be empty",
        )

    norm_filter = (payload.source_filter or "all").lower().strip()
    if norm_filter not in ALLOWED_SOURCE_FILTERS:
        allowed_list = ", ".join(sorted(list(ALLOWED_SOURCE_FILTERS)))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid source_filter '{payload.source_filter}'. Allowed: {allowed_list}",
        )

    if payload.top_k < 1 or payload.top_k > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="top_k must be between 1 and 50",
        )

    effective_target_text = payload.target_text or clean_query
    target_key_info = KeyInformation(drug=clean_query)
    effective_exclude_doc_id = payload.exclude_document_id or payload.document_id

    errors: List[str] = []
    try:
        results = await retriever.retrieve_candidates(
            target_text=effective_target_text,
            section_hint=payload.section,
            target_key_info=target_key_info,
            top_k=payload.top_k,
            source_filter=norm_filter,
            exclude_document_id=effective_exclude_doc_id,
            exclude_document_fingerprint=payload.exclude_document_fingerprint,
        )
        items = [r[0] for r in results]
    except Exception as exc:
        logger.warning("Candidate search query failed: %s", exc)
        errors.append(f"Candidate search query error: {str(exc)}")
        items = []

    return RegulatorySearchResult(
        query=clean_query,
        total_results=len(items),
        source=norm_filter,
        items=items,
        errors=errors if errors else None,
    )
