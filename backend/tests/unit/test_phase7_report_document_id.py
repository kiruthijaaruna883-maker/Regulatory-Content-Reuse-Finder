"""Unit and integration tests for Phase 7.3: Connecting Approved Change Report to source document_id.

Proves:
1. Newly approved report contains the correct authoritative document_id.
2. The report's document_id maps to the correct retained source document in candidate_store.
3. Multiple documents in different workflows remain isolated and cannot resolve to the same source.
4. Backward compatibility is preserved for reports predating the document_id field.
5. Legacy text upload flow links to retained source bytes and populates report document_id.
6. Explicit document_id overrides in approval payloads are honored.
7. Audit event details accurately capture document_id transitions without altering event types.
"""

import io
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from app.main import app
from app.models.audit import AuditEventType
from app.models.document import RegulatoryDocument, RegulatoryChunk
from app.models.document_change import (
    ApprovedChangeReport,
    ProposedChange,
    ReviewDecisionType,
    ReviewerDecision,
)
from app.persistence.sqlite_store import WorkflowSQLiteStore
from app.routes.document_review import change_manager
from app.services.candidate_store import (
    get_candidate_store,
    reset_candidate_store,
)
from app.services.change_manager import ChangeManagerService
from app.services.change_report import ChangeReportService

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_stores():
    """Reset candidate store and sqlite store for clean test isolation."""
    reset_candidate_store()
    change_manager.clear_session()
    yield
    reset_candidate_store()
    change_manager.clear_session()


def test_approved_report_contains_document_id_direct_service():
    """Direct service flow: ChangeReportService resolves document_id and links to retained bytes."""
    store = get_candidate_store()
    raw_content = b"ORIGINAL SOURCE BYTES 1: Direct Service Test Content"
    doc, chunks = store.ingest_and_store(
        content=raw_content,
        filename="cardiology_guide.txt",
        document_id="doc_cardio_101",
    )

    assert doc.document_id == "doc_cardio_101"
    assert store.has_source_document("doc_cardio_101")

    # 1. Reviewer decision
    decision = ReviewerDecision(
        target_content_id=chunks[0].chunk_id,
        decision=ReviewDecisionType.REUSE,
        reviewer_name="Dr. Sarah Connor",
        reviewer_notes="Standard clinical reuse rationale.",
    )
    change_manager.record_decision(decision)

    # 2. Proposal
    proposal = change_manager.create_change_proposal(
        decision=decision,
        section="Dosage and Administration",
        original_text="Old dosage text",
        proposed_text="Updated dosage text per guidelines",
        rationale="Traceable rationale",
        document_name="Cardiology Clinical Guide",
    )
    assert proposal.document_id == "doc_cardio_101"

    # 3. Compile report
    reporter = ChangeReportService()
    report = reporter.generate_report(
        author_approver="Dr. Sarah Connor",
        changes=[proposal],
        approval_confirmation=True,
    )

    assert report.document_id == "doc_cardio_101"

    # 4. Connect report -> document_id -> retained source document
    retained = store.get_source_document(report.document_id)
    assert retained is not None
    assert retained.document_id == "doc_cardio_101"
    assert retained.filename == "cardiology_guide.txt"
    assert retained.file_format == "txt"
    assert retained.source_bytes == raw_content


def test_approved_report_contains_document_id_api_workflow():
    """API workflow: Ingest -> Decision -> Analyze -> Approve resolves document_id."""
    store = get_candidate_store()
    sample_file_bytes = b"REGULATORY CORE SHEET: High-potency formulation 50mg daily."
    files = {
        "file": (
            "pediatric_label.txt",
            io.BytesIO(sample_file_bytes),
            "text/plain",
        )
    }

    # 1. Ingest
    res_ingest = client.post("/documents/ingest", files=files)
    assert res_ingest.status_code == 200
    ingest_data = res_ingest.json()
    doc_id = ingest_data["document_id"]
    assert doc_id is not None
    assert store.has_source_document(doc_id)

    # Chunks are in store
    chunks = store.list_chunks(doc_id)
    assert len(chunks) > 0
    target_chunk_id = chunks[0].chunk_id

    # 2. Record Decision
    res_dec = client.post(
        "/review/decision",
        json={
            "target_content_id": target_chunk_id,
            "decision": "ADAPT",
            "reviewer_name": "Dr. Angela Martin",
            "reviewer_notes": "Pediatric weight-based adaptation required.",
            "adaptation_instructions": "Adjust to 0.5 mg/kg once daily.",
        },
    )
    assert res_dec.status_code == 200
    dec_data = res_dec.json()
    assert dec_data["document_id"] == doc_id

    # 3. Analyze change proposal
    res_prop = client.post(
        "/changes/analyze",
        json={
            "decision_id": dec_data["decision_id"],
            "section": "DOSAGE",
            "original_text": "High-potency formulation 50mg daily.",
            "candidate_text": "Pediatric formulation 0.5 mg/kg daily.",
            "document_name": "Pediatric Core Label",
        },
    )
    assert res_prop.status_code == 200
    prop_data = res_prop.json()
    assert prop_data["document_id"] == doc_id

    # 4. Validate
    res_val = client.post("/changes/validate", json=prop_data)
    assert res_val.status_code == 200

    # 5. Approve
    res_app = client.post(
        "/changes/approve",
        json={
            "approver_name": "Dr. Angela Martin",
            "approval_confirmation": True,
            "proposal_ids": [prop_data["change_id"]],
        },
    )
    assert res_app.status_code == 200
    report_data = res_app.json()

    # The Approved Change Report reliably identifies the source document ID
    assert report_data["document_id"] == doc_id

    # Resolve retained original bytes
    retained = store.get_source_document(report_data["document_id"])
    assert retained is not None
    assert retained.source_bytes == sample_file_bytes
    assert retained.filename == "pediatric_label.txt"


def test_two_documents_isolation_cannot_resolve_to_same_source():
    """Verify multiple documents remain strictly isolated and never cross-resolve."""
    store = get_candidate_store()

    # Document A
    bytes_a = b"INDICATIONS AND USAGE\nDocument A Oncology clinical indication with adequate detail."
    doc_a, chunks_a = store.ingest_and_store(
        content=bytes_a,
        filename="oncology_protocol.txt",
        document_id="doc_onc_001",
    )

    # Document B
    bytes_b = b"INDICATIONS AND USAGE\nDocument B Neurology clinical indication with adequate detail."
    doc_b, chunks_b = store.ingest_and_store(
        content=bytes_b,
        filename="neurology_protocol.txt",
        document_id="doc_neuro_002",
    )

    assert doc_a.document_id != doc_b.document_id

    # Decision A and Proposal A
    dec_a = ReviewerDecision(
        target_content_id=chunks_a[0].chunk_id,
        decision=ReviewDecisionType.REUSE,
        reviewer_name="Reviewer A",
    )
    change_manager.record_decision(dec_a)
    prop_a = change_manager.create_change_proposal(
        decision=dec_a,
        section="Dosage",
        original_text="Doc A original",
        proposed_text="Doc A proposed",
        rationale="Doc A rationale",
    )

    # Decision B and Proposal B
    dec_b = ReviewerDecision(
        target_content_id=chunks_b[0].chunk_id,
        decision=ReviewDecisionType.REUSE,
        reviewer_name="Reviewer B",
    )
    change_manager.record_decision(dec_b)
    prop_b = change_manager.create_change_proposal(
        decision=dec_b,
        section="Dosage",
        original_text="Doc B original",
        proposed_text="Doc B proposed",
        rationale="Doc B rationale",
    )

    # Generate Report A
    reporter = ChangeReportService()
    report_a = reporter.generate_report(
        author_approver="Approver A",
        changes=[prop_a],
        approval_confirmation=True,
    )

    # Generate Report B
    report_b = reporter.generate_report(
        author_approver="Approver B",
        changes=[prop_b],
        approval_confirmation=True,
    )

    # Reports must have distinct document_ids
    assert report_a.document_id == "doc_onc_001"
    assert report_b.document_id == "doc_neuro_002"
    assert report_a.document_id != report_b.document_id

    # Each report resolves ONLY to its own retained source document
    retained_a = store.get_source_document(report_a.document_id)
    retained_b = store.get_source_document(report_b.document_id)

    assert retained_a.source_bytes == bytes_a
    assert retained_b.source_bytes == bytes_b
    assert retained_a.source_bytes != retained_b.source_bytes
    assert retained_a.filename == "oncology_protocol.txt"
    assert retained_b.filename == "neurology_protocol.txt"


def test_approved_report_backward_compatibility_predating_document_id():
    """Verify legacy ApprovedChangeReport JSON predating document_id deserializes cleanly with None."""
    legacy_json = """{
        "report_id": "rep_legacy_9999",
        "document_name": "Legacy Product Monograph",
        "document_version": "1.0",
        "generated_at": "2026-01-01T00:00:00Z",
        "author_approver": "Dr. Legacy Approver",
        "decision_ids": ["dec_legacy_1"],
        "changes": [],
        "approval_confirmation": true
    }"""

    report = ApprovedChangeReport.model_validate_json(legacy_json)
    assert report.report_id == "rep_legacy_9999"
    assert report.document_name == "Legacy Product Monograph"
    assert report.document_id is None
    assert report.approval_confirmation is True

    # Test round-trip persistence in sqlite_store
    wf_store = WorkflowSQLiteStore(db_path=":memory:")
    wf_store.save_report(report)
    loaded = wf_store.get_report("rep_legacy_9999")
    assert loaded is not None
    assert loaded.report_id == "rep_legacy_9999"
    assert loaded.document_id is None


def test_legacy_upload_route_retains_source_and_links_to_report():
    """Verify legacy /documents/upload retains source text and links to ApprovedChangeReport."""
    store = get_candidate_store()
    source_text = (
        "INDICATIONS AND USAGE\n"
        "Indicated for acute musculoskeletal pain.\n\n"
        "DOSAGE AND ADMINISTRATION\n"
        "Take 200 mg every 6 hours."
    )

    # 1. Upload
    res_upload = client.post(
        "/documents/upload",
        json={"document_name": "Musculoskeletal Guide", "content": source_text},
    )
    assert res_upload.status_code == 200
    sections = res_upload.json()
    assert len(sections) == 2
    doc_id = sections[0]["document_id"]
    assert doc_id is not None
    assert store.has_source_document(doc_id)

    # 2. Decision
    res_dec = client.post(
        "/review/decision",
        json={
            "target_content_id": sections[0]["content_id"],
            "decision": "REUSE",
            "reviewer_name": "Dr. Ortho",
        },
    )
    assert res_dec.status_code == 200

    # 3. Analyze
    res_prop = client.post(
        "/changes/analyze",
        json={
            "decision_id": res_dec.json()["decision_id"],
            "section": sections[0]["section"],
            "original_text": sections[0]["text"],
            "candidate_text": "Updated indications text.",
        },
    )
    assert res_prop.status_code == 200
    prop_id = res_prop.json()["change_id"]

    # 4. Approve
    res_app = client.post(
        "/changes/approve",
        json={
            "approver_name": "Dr. Lead Approver",
            "approval_confirmation": True,
            "proposal_ids": [prop_id],
        },
    )
    assert res_app.status_code == 200
    report_json = res_app.json()

    assert report_json["document_id"] == doc_id
    retained = store.get_source_document(report_json["document_id"])
    assert retained is not None
    assert retained.source_bytes == source_text.encode("utf-8")


def test_explicit_document_id_override_in_approval_request():
    """Verify explicit document_id in ApproveReportRequest is honored."""
    prop = ProposedChange(
        decision_id="dec_override_01",
        section="Precautions",
        original_text="Old precaution",
        proposed_text="New precaution",
        decision_type=ReviewDecisionType.REUSE,
        rationale="Clinical rationale",
    )
    change_manager.save_proposal(prop)

    res_app = client.post(
        "/changes/approve",
        json={
            "approver_name": "Regulatory Director",
            "approval_confirmation": True,
            "document_id": "doc_explicit_override_456",
            "proposal_ids": [prop.change_id],
        },
    )
    assert res_app.status_code == 200
    report_json = res_app.json()
    assert report_json["document_id"] == "doc_explicit_override_456"


def test_report_document_id_recorded_in_audit_event():
    """Verify APPROVED_REPORT_CREATED audit event records document_id."""
    report = ApprovedChangeReport(
        document_id="doc_audit_test_789",
        document_name="Audit Test Document",
        author_approver="Compliance Officer",
        approval_confirmation=True,
        changes=[
            ProposedChange(
                decision_id="dec_audit_1",
                section="Indications",
                original_text="Orig",
                proposed_text="Prop",
                decision_type=ReviewDecisionType.REUSE,
                rationale="Audit test",
            )
        ],
    )
    change_manager.record_approved_report(report)

    events = change_manager.list_audit_events_for_report(report)
    report_events = [e for e in events if e.event_type == AuditEventType.APPROVED_REPORT_CREATED.value]
    assert len(report_events) == 1
    evt = report_events[0]
    assert evt.details["document_id"] == "doc_audit_test_789"
    assert evt.new_state["document_id"] == "doc_audit_test_789"


# ==============================================================================
# PHASE 7 BUG FIX: SYNTHETIC _item SUFFIX DEFENSIVE RESOLUTION TESTS
# ==============================================================================


def test_item_suffix_direct_fallback_resolution():
    """Test A: Verify that doc_test_123_item resolves to doc_test_123 when source document exists."""
    store = get_candidate_store()
    raw_content = b"ORIGINAL SOURCE CONTENT FOR TEST A"
    store.store_source_document(
        document_id="doc_test_123",
        source_bytes=raw_content,
        filename="test_a_doc.txt",
        file_format="txt",
    )

    dec = ReviewerDecision(
        target_content_id="doc_test_123_item",
        document_id=None,
        decision=ReviewDecisionType.REUSE,
        reviewer_name="Dr. Alex Vance",
        reviewer_notes="Test A note",
    )
    res = client.post(
        "/review/decision",
        json=dec.model_dump(),
    )
    assert res.status_code == 200
    saved_dec = res.json()
    assert saved_dec["document_id"] == "doc_test_123"


def test_decision_workflow_item_suffix_resolution():
    """Test B: Simulate browser-style request where target_content_id has _item suffix and no document_id."""
    store = get_candidate_store()
    store.store_source_document(
        document_id="doc_browser_sim_456",
        source_bytes=b"Browser simulation source text",
        filename="browser_doc.txt",
        file_format="txt",
    )

    res = client.post(
        "/review/decision",
        json={
            "target_content_id": "doc_browser_sim_456_item",
            "candidate_id": "cand_ref_01",
            "decision": "ADAPT",
            "reviewer_name": "Reviewer B",
            "reviewer_notes": "Clinical adaptation rationale",
            "adaptation_instructions": "Adapted instruction text",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["document_id"] == "doc_browser_sim_456"


def test_proposal_workflow_item_suffix_resolution():
    """Test C: Verify that proposal receives the authoritative source document_id from decision."""
    store = get_candidate_store()
    store.store_source_document(
        document_id="doc_browser_sim_789",
        source_bytes=b"Proposal test source content",
        filename="proposal_doc.txt",
        file_format="txt",
    )

    # 1. Record decision with _item target_content_id
    res_dec = client.post(
        "/review/decision",
        json={
            "target_content_id": "doc_browser_sim_789_item",
            "decision": "REUSE",
            "reviewer_name": "Reviewer C",
            "reviewer_notes": "Reuse rationale",
        },
    )
    assert res_dec.status_code == 200
    dec_id = res_dec.json()["decision_id"]

    # 2. Formulate proposal without explicit document_id
    res_prop = client.post(
        "/changes/analyze",
        json={
            "decision_id": dec_id,
            "section": "Warnings",
            "original_text": "Proposal test source content",
            "document_name": "Test Document 789",
        },
    )
    assert res_prop.status_code == 200
    prop_data = res_prop.json()
    assert prop_data["document_id"] == "doc_browser_sim_789"


def test_approval_report_workflow_item_suffix_resolution():
    """Test D: Verify that resulting ApprovedChangeReport.document_id is populated correctly."""
    store = get_candidate_store()
    store.store_source_document(
        document_id="doc_browser_full_flow",
        source_bytes=b"Complete flow source content",
        filename="complete_flow.txt",
        file_format="txt",
    )

    # 1. Decision with _item target
    res_dec = client.post(
        "/review/decision",
        json={
            "target_content_id": "doc_browser_full_flow_item",
            "decision": "REUSE",
            "reviewer_name": "Reviewer D",
            "reviewer_notes": "Workflow note",
        },
    )
    assert res_dec.status_code == 200
    dec_id = res_dec.json()["decision_id"]

    # 2. Proposal without explicit document_id
    res_prop = client.post(
        "/changes/analyze",
        json={
            "decision_id": dec_id,
            "section": "Clinical Pharmacology",
            "original_text": "Complete flow source content",
            "document_name": "Flow Monograph",
        },
    )
    assert res_prop.status_code == 200
    prop_id = res_prop.json()["change_id"]

    # 3. Approve report without explicit document_id
    res_rep = client.post(
        "/changes/approve",
        json={
            "approver_name": "Director of Regulatory Affairs",
            "approval_confirmation": True,
            "proposal_ids": [prop_id],
            "document_name": "Flow Monograph",
        },
    )
    assert res_rep.status_code == 200
    rep_data = res_rep.json()
    assert rep_data["document_id"] == "doc_browser_full_flow"


def test_explicit_document_id_precedence_over_item_fallback():
    """Test E: Verify that explicit document_id remains authoritative and is not overwritten by _item fallback."""
    store = get_candidate_store()
    store.store_source_document(
        document_id="doc_fallback_source",
        source_bytes=b"Fallback source",
        filename="fallback.txt",
        file_format="txt",
    )
    store.store_source_document(
        document_id="doc_explicit_priority",
        source_bytes=b"Explicit priority source",
        filename="priority.txt",
        file_format="txt",
    )

    # Supply explicit document_id while target_content_id has _item
    res = client.post(
        "/review/decision",
        json={
            "target_content_id": "doc_fallback_source_item",
            "document_id": "doc_explicit_priority",
            "decision": "REUSE",
            "reviewer_name": "Priority Tester",
            "reviewer_notes": "Testing precedence",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["document_id"] == "doc_explicit_priority"


def test_pdf_workflow_corrected_document_generation():
    """Test F: For a PDF workflow whose report resolves document_id, verify corrected PDF is successfully generated and original source remains immutable."""
    import hashlib
    import pypdf
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    c.setFont("Helvetica", 12)
    c.drawString(72, 720, "1. INDICATIONS")
    c.drawString(72, 690, "Drug is indicated for hypertension.")
    c.save()
    pdf_bytes = buf.getvalue()
    pre_hash = hashlib.sha256(pdf_bytes).hexdigest()

    store = get_candidate_store()
    store.store_source_document(
        document_id="doc_pdf_safety_guard",
        source_bytes=pdf_bytes,
        filename="SYN-ACET-001_Synthetic_Regulatory_Test.pdf",
        file_format="pdf",
    )

    # 1. Decision via _item target
    res_dec = client.post(
        "/review/decision",
        json={
            "target_content_id": "doc_pdf_safety_guard_item",
            "decision": "ADAPT",
            "reviewer_name": "Safety Reviewer",
            "reviewer_notes": "Adaptation note",
            "adaptation_instructions": "Drug is indicated for severe hypertension.",
        },
    )
    assert res_dec.status_code == 200
    dec_id = res_dec.json()["decision_id"]

    # 2. Proposal
    res_prop = client.post(
        "/changes/analyze",
        json={
            "decision_id": dec_id,
            "section": "Indications",
            "original_text": "Drug is indicated for hypertension.",
            "document_name": "SYN ACET 001 Synthetic Regulatory Test",
        },
    )
    assert res_prop.status_code == 200
    prop_id = res_prop.json()["change_id"]

    # 3. Approve report
    res_rep = client.post(
        "/changes/approve",
        json={
            "approver_name": "Safety Officer",
            "approval_confirmation": True,
            "proposal_ids": [prop_id],
            "document_name": "SYN ACET 001 Synthetic Regulatory Test",
        },
    )
    assert res_rep.status_code == 200
    rep_id = res_rep.json()["report_id"]
    assert res_rep.json()["document_id"] == "doc_pdf_safety_guard"

    # 4. Successfully generate and download corrected document for PDF
    res_corr = client.post(f"/changes/report/{rep_id}/corrected-document")
    assert res_corr.status_code == 200
    assert res_corr.headers["content-type"] == "application/pdf"
    assert res_corr.content.startswith(b"%PDF-")

    # 5. Verify source document immutability
    retained_after = store.get_source_document("doc_pdf_safety_guard")
    assert hashlib.sha256(bytes(retained_after.source_bytes)).hexdigest() == pre_hash

    # 6. Verify replacement in generated PDF
    reader = pypdf.PdfReader(io.BytesIO(res_corr.content))
    out_text = reader.pages[0].extract_text()
    assert "severe hypertension" in out_text
