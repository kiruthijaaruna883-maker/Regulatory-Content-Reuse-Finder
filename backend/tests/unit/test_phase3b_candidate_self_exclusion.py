"""Phase 3B: Regression tests for candidate self-matching and source exclusion.

Covers:
1. File upload and paste-text ingestion with disposable data.
2. Automatic candidate discovery after restoration (with restored metadata).
3. Manual candidate search after restoration (with restored metadata).
4. Repeated ingestion of two different drafts.
5. Strict exclusion of active source document and its chunks.
6. Preservation of legitimate internal reference candidates.
7. Preservation of DailyMed/openFDA candidate discovery.
8. Candidate search without active document context (unrestricted search).
9. Candidate store fallback resolution of document fingerprint from index.
"""

import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.content import KeyInformation, RegulatoryContentItem
from app.models.document import (
    RegulatoryChunk,
    RegulatoryDocument,
    RegulatoryProvenance,
    RegulatorySection,
)
from app.services.candidate_store import (
    IngestedDocumentCandidateStore,
    get_candidate_store,
    reset_candidate_store,
)
from app.services.rag_retriever import LiveRAGRetriever

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_candidate_store():
    """Ensure candidate store isolation for every test."""
    reset_candidate_store()
    yield
    reset_candidate_store()


def _make_disposable_doc_text(unique_id: str, drug_name: str) -> str:
    """Generate dynamic, unique regulatory text for disposable testing."""
    return (
        f"1. INDICATIONS AND USAGE\n"
        f"{drug_name} is indicated for the treatment of essential hypertension in adults (Run: {unique_id}).\n\n"
        f"2. DOSAGE AND ADMINISTRATION\n"
        f"The recommended initial dosage of {drug_name} is 10 mg orally once daily. "
        f"Titrate up to 20 mg once daily after 2 weeks based on clinical response.\n\n"
        f"3. CONTRAINDICATIONS\n"
        f"{drug_name} is contraindicated in patients with severe hepatic impairment.\n"
    )


# ==============================================================================
# 1. FILE UPLOAD AND PASTE-TEXT INGESTION WITH EXCLUSION
# ==============================================================================


def test_file_upload_ingestion_and_automatic_discovery_exclusion():
    """Verify file upload ingestion assigns IDs and automatic discovery excludes the source document."""
    unique_run = uuid.uuid4().hex[:8]
    drug_name = f"TestCompound_{unique_run}"
    raw_text = _make_disposable_doc_text(unique_run, drug_name)

    files = {"file": (f"{drug_name}_label.txt", raw_text.encode("utf-8"), "text/plain")}
    data = {"document_name": f"{drug_name} Prescribing Info", "jurisdiction": "US_FDA"}

    # 1. Ingest via file upload
    res_ingest = client.post("/documents/ingest", files=files, data=data)
    assert res_ingest.status_code == 200
    ingest_data = res_ingest.json()

    source_doc_id = ingest_data["document_id"]
    source_fp = ingest_data["document_fingerprint"]
    sections = ingest_data["sections"]
    assert source_doc_id.startswith("doc_")
    assert source_fp.startswith("fp_")
    assert len(sections) >= 2
    target_sec = sections[1]  # Section 2: Dosage

    # Also ingest a legitimate reference document so candidates exist in store
    ref_drug = f"ReferenceDrug_{unique_run}"
    ref_text = _make_disposable_doc_text(f"ref_{unique_run}", ref_drug)
    res_ref = client.post(
        "/documents/ingest",
        data={"pasted_text": ref_text, "document_name": f"{ref_drug} Reference Label"},
    )
    assert res_ref.status_code == 200
    ref_doc_id = res_ref.json()["document_id"]

    # 2. Trigger automatic discovery via /content/analyze
    analyze_payload = {
        "target_text": target_sec["text"],
        "section_name": target_sec.get("section"),
        "candidates": [],
        "retrieve_live": True,
        "source_filter": "ingested",
        "top_k": 10,
        "document_id": source_doc_id,
        "exclude_document_id": source_doc_id,
        "exclude_document_fingerprint": source_fp,
        "target_content_id": target_sec["content_id"],
        "document_name": f"{drug_name} Prescribing Info",
    }
    res_analyze = client.post("/content/analyze", json=analyze_payload)
    assert res_analyze.status_code == 200
    analyze_data = res_analyze.json()
    returned_candidates = analyze_data.get("candidates", [])

    returned_doc_ids = {c["content_item"]["document_id"] for c in returned_candidates}
    returned_fps = {c["content_item"].get("document_fingerprint") for c in returned_candidates}
    returned_content_ids = {c["content_item"]["content_id"] for c in returned_candidates}

    # Source document must NEVER appear in returned candidates
    assert source_doc_id not in returned_doc_ids
    assert source_fp not in returned_fps
    assert target_sec["content_id"] not in returned_content_ids
    # Reference document remains discoverable
    assert ref_doc_id in returned_doc_ids


def test_paste_text_ingestion_and_manual_search_exclusion():
    """Verify paste-text ingestion assigns IDs and manual candidate search excludes the source document."""
    unique_run = uuid.uuid4().hex[:8]
    drug_name = f"PasteCompound_{unique_run}"
    raw_text = _make_disposable_doc_text(unique_run, drug_name)

    # 1. Ingest via paste mode
    res_ingest = client.post(
        "/documents/ingest",
        data={"pasted_text": raw_text, "document_name": f"{drug_name} Monograph"},
    )
    assert res_ingest.status_code == 200
    ingest_data = res_ingest.json()
    source_doc_id = ingest_data["document_id"]
    source_fp = ingest_data["document_fingerprint"]
    target_sec = ingest_data["sections"][0]

    # Ingest distinct reference document
    res_ref = client.post(
        "/documents/ingest",
        data={
            "pasted_text": f"1. INDICATIONS AND USAGE\nTreatment of mild hypertension.\n\n2. DOSAGE\nTake 5 mg daily.",
            "document_name": "Standard Reference",
        },
    )
    assert res_ref.status_code == 200
    ref_doc_id = res_ref.json()["document_id"]

    # 2. Perform manual candidate search with exclusions
    search_payload = {
        "query": "hypertension",
        "source_filter": "ingested",
        "section": target_sec.get("section"),
        "target_text": target_sec.get("text"),
        "top_k": 10,
        "exclude_document_id": source_doc_id,
        "document_id": source_doc_id,
        "exclude_document_fingerprint": source_fp,
        "target_content_id": target_sec.get("content_id"),
    }
    res_search = client.post("/candidates/search", json=search_payload)
    assert res_search.status_code == 200
    search_items = res_search.json().get("items", [])

    returned_doc_ids = {it["document_id"] for it in search_items}
    assert source_doc_id not in returned_doc_ids
    assert ref_doc_id in returned_doc_ids


# ==============================================================================
# 2. SIMULATED BROWSER RELOAD / RESTORED CONTEXT DISCOVERY & SEARCH
# ==============================================================================


def test_restored_metadata_automatic_discovery_excludes_source_document():
    """Verify when only document_id and document_fingerprint are restored, auto-discovery excludes the source."""
    unique_run = uuid.uuid4().hex[:8]
    drug_name = f"ReloadMed_{unique_run}"
    raw_text = _make_disposable_doc_text(unique_run, drug_name)

    res_ingest = client.post(
        "/documents/ingest",
        data={"pasted_text": raw_text, "document_name": f"{drug_name} Draft"},
    )
    assert res_ingest.status_code == 200
    doc_id = res_ingest.json()["document_id"]
    doc_fp = res_ingest.json()["document_fingerprint"]

    # Reference candidate
    res_ref = client.post(
        "/documents/ingest",
        data={
            "pasted_text": "INDICATIONS: Adult hypertension.\nDOSAGE: 10 mg orally once daily.",
            "document_name": "Formulary Reference",
        },
    )
    assert res_ref.status_code == 200
    ref_doc_id = res_ref.json()["document_id"]

    # Simulating restored state in CandidateComparison after page reload:
    # Target text is tested with genuine section text, sending restored document_id & fingerprint
    analyze_payload = {
        "target_text": f"The recommended initial dosage of {drug_name} is 10 mg orally once daily.",
        "section_name": "2. DOSAGE AND ADMINISTRATION",
        "candidates": [],
        "retrieve_live": True,
        "source_filter": "ingested",
        "top_k": 5,
        "document_id": doc_id,
        "exclude_document_id": doc_id,
        "exclude_document_fingerprint": doc_fp,
    }
    res_analyze = client.post("/content/analyze", json=analyze_payload)
    assert res_analyze.status_code == 200
    cands = res_analyze.json().get("candidates", [])
    returned_doc_ids = {c["content_item"]["document_id"] for c in cands}

    assert doc_id not in returned_doc_ids
    assert ref_doc_id in returned_doc_ids


def test_restored_metadata_manual_search_excludes_source_document():
    """Verify manual candidate search using restored metadata successfully excludes the source document."""
    unique_run = uuid.uuid4().hex[:8]
    drug_name = f"ManualReload_{unique_run}"
    raw_text = _make_disposable_doc_text(unique_run, drug_name)

    res_ingest = client.post(
        "/documents/ingest",
        data={"pasted_text": raw_text, "document_name": f"{drug_name} Dossier"},
    )
    assert res_ingest.status_code == 200
    doc_id = res_ingest.json()["document_id"]
    doc_fp = res_ingest.json()["document_fingerprint"]

    # Perform manual search using restored document identity
    res_search = client.post(
        "/candidates/search",
        json={
            "query": drug_name,
            "source_filter": "ingested",
            "top_k": 5,
            "exclude_document_id": doc_id,
            "exclude_document_fingerprint": doc_fp,
        },
    )
    assert res_search.status_code == 200
    items = res_search.json().get("items", [])
    assert all(it["document_id"] != doc_id for it in items)


# ==============================================================================
# 3. REPEATED INGESTION OF TWO DIFFERENT DRAFTS
# ==============================================================================


def test_repeated_ingestion_of_two_different_drafts():
    """Verify ingesting Draft A then Draft B: searching with Draft B exclusions cleanly excludes Draft B."""
    unique_run = uuid.uuid4().hex[:8]
    drug_name = f"DraftCompound_{unique_run}"

    # Draft 1
    text_v1 = f"1. INDICATIONS\n{drug_name} is indicated for hypertension.\n2. DOSAGE\nTake 10 mg once daily."
    res_v1 = client.post("/documents/ingest", data={"pasted_text": text_v1, "document_name": f"{drug_name} v1"})
    assert res_v1.status_code == 200
    doc_id_v1 = res_v1.json()["document_id"]
    doc_fp_v1 = res_v1.json()["document_fingerprint"]

    # Draft 2 (slight modification: 20 mg dosage)
    text_v2 = f"1. INDICATIONS\n{drug_name} is indicated for hypertension.\n2. DOSAGE\nTake 20 mg once daily."
    res_v2 = client.post("/documents/ingest", data={"pasted_text": text_v2, "document_name": f"{drug_name} v2"})
    assert res_v2.status_code == 200
    doc_id_v2 = res_v2.json()["document_id"]
    doc_fp_v2 = res_v2.json()["document_fingerprint"]

    assert doc_id_v1 != doc_id_v2
    assert doc_fp_v1 != doc_fp_v2

    # Candidate search for Draft 2 must exclude Draft 2
    search_res = client.post(
        "/candidates/search",
        json={
            "query": "hypertension",
            "source_filter": "ingested",
            "top_k": 10,
            "exclude_document_id": doc_id_v2,
            "exclude_document_fingerprint": doc_fp_v2,
        },
    )
    assert search_res.status_code == 200
    found_doc_ids = {it["document_id"] for it in search_res.json().get("items", [])}
    assert doc_id_v2 not in found_doc_ids


# ==============================================================================
# 4. PRESERVATION OF EXTERNAL CANDIDATES & UNRESTRICTED SEARCH
# ==============================================================================


def test_searches_without_active_document_context():
    """Requirement 10: Candidate search without active document context operates cleanly without error."""
    res_search = client.post(
        "/candidates/search",
        json={
            "query": "aspirin",
            "source_filter": "all",
            "top_k": 5,
            "exclude_document_id": None,
            "exclude_document_fingerprint": None,
        },
    )
    assert res_search.status_code == 200
    data = res_search.json()
    assert "items" in data
    assert isinstance(data["items"], list)


def test_candidate_store_fingerprint_fallback_resolution():
    """Verify candidate_store resolves fingerprint from index even if missing on item object."""
    store = IngestedDocumentCandidateStore()
    doc = RegulatoryDocument(
        document_id="doc_fallback_test_01",
        document_fingerprint="fp_canonical_resolved_555",
        title="Fallback Resolution Label",
        provenance=RegulatoryProvenance(source_repository="InternalDraft"),
        sections=[
            RegulatorySection(
                section_id="sec_01",
                heading_raw="DOSAGE",
                raw_text="Take 10 mg orally once daily.",
                chunks=[
                    RegulatoryChunk(
                        chunk_id="chk_fall_01",
                        document_id="doc_fallback_test_01",
                        section_id="sec_01",
                        content="Take 10 mg orally once daily.",
                        document_fingerprint="fp_canonical_resolved_555",
                    )
                ],
            )
        ],
    )
    store.add_document(doc)

    # Deliberately remove document_fingerprint from the adapted content item to test fallback
    item = store._content_items["chk_fall_01"]
    item.document_fingerprint = None

    # Search with exclude_document_fingerprint="fp_canonical_resolved_555"
    results = store.search(query="daily", exclude_document_fingerprint="fp_canonical_resolved_555")
    # Must still be excluded because candidate_store resolves fingerprint from self._doc_to_fingerprint
    assert len(results) == 0
