"""Unit tests for core deterministic business logic services."""

from app.models.content import RegulatoryContentItem
from app.models.document_change import ProposedChange, ReviewDecisionType, ReviewerDecision
from app.services.change_manager import ChangeManagerService
from app.services.change_report import ChangeReportService
from app.services.content_extraction import ContentExtractionService
from app.services.content_matching import ContentMatchingService
from app.services.difference_detection import DifferenceDetectionService
from app.services.validation import ValidationService


def test_content_extraction_standard_headings():
    """Verify standard regulatory headings are segmented accurately."""
    service = ContentExtractionService()
    text = """
    INDICATIONS AND USAGE
    Indicated for relief of mild to moderate pain.

    DOSAGE AND ADMINISTRATION
    Take 500 mg orally every 6 hours. Do not exceed 4000 mg in 24 hours.

    CONTRAINDICATIONS
    Hypersensitivity to the active substance.
    """
    sections = service.extract_sections_from_text(text, document_name="Clinical Insert")
    assert len(sections) == 3
    section_titles = [s.section for s in sections]
    assert "Indications And Usage" in section_titles
    assert "Dosage And Administration" in section_titles
    assert "Contraindications" in section_titles


def test_content_matching_jaccard_ranking():
    """Verify Jaccard token overlap ranking orders candidates appropriately."""
    service = ContentMatchingService()
    target_text = "Take 100 mg orally once daily with food."

    c1 = RegulatoryContentItem(source="DailyMed", text="Take 100 mg orally once daily with food for hypertension.")
    c2 = RegulatoryContentItem(source="openFDA", text="Apply topically to the affected skin twice per week.")

    ranked = service.rank_candidates(target_text, [c1, c2])
    assert len(ranked) == 2
    assert ranked[0].content_item.source == "DailyMed"
    assert ranked[0].similarity_score > ranked[1].similarity_score


def test_difference_detection_numerical_variation():
    """Verify difference detection flags numeric dosage changes as MAJOR impact."""
    service = DifferenceDetectionService()
    current = "Adults: Take 200 mg orally every 8 hours."
    candidate = "Adults: Take 400 mg orally every 12 hours."

    diffs = service.analyze_differences(current, candidate)
    assert len(diffs) > 0
    key_info_diff = next((d for d in diffs if d.aspect == "key_information"), None)
    assert key_info_diff is not None
    assert key_info_diff.regulatory_impact == "MAJOR"


def test_change_manager_lifecycle():
    """Verify human decision recording and proposal creation."""
    manager = ChangeManagerService()
    decision = ReviewerDecision(
        target_content_id="rc_target_1",
        decision=ReviewDecisionType.REUSE,
        reviewer_name="Dr. Smith",
    )
    saved_dec = manager.record_decision(decision)
    assert saved_dec.decision_id == decision.decision_id

    proposal = manager.create_change_proposal(
        decision=saved_dec,
        section="Warnings",
        original_text="Old warning text.",
        proposed_text="New standardized regulatory warning text.",
        rationale="Approved direct reuse from DailyMed standard.",
    )
    assert proposal.decision_id == decision.decision_id
    assert len(manager.list_proposals()) == 1


def test_validation_service_error_handling():
    """Verify validation engine catches incomplete text or missing rationale."""
    validator = ValidationService()
    invalid_proposal = ProposedChange(
        decision_id="dec_1",
        section="Dosage",
        original_text="Some text",
        proposed_text="",  # Empty text should trigger ERROR
        decision_type=ReviewDecisionType.REUSE,
        rationale="",  # Empty rationale should trigger ERROR
    )

    impact = validator.validate_proposal(invalid_proposal)
    assert impact.validation_passed is False
    assert impact.risk_level == "HIGH"
    error_rules = [f.rule_id for f in impact.findings if f.severity == "ERROR"]
    assert "REG-VAL-001" in error_rules
    assert "REG-VAL-002" in error_rules


def test_change_report_generation():
    """Verify change report assembler compiles audit-ready reports."""
    reporter = ChangeReportService()
    proposal = ProposedChange(
        decision_id="dec_100",
        section="Dosage",
        original_text="Old",
        proposed_text="New validated dosage",
        decision_type=ReviewDecisionType.ADAPT,
        rationale="Pediatric adjustment",
    )
    report = reporter.generate_report(
        document_name="Pediatric Label",
        document_version="2.1",
        author_approver="Senior Director RA",
        changes=[proposal],
        approval_confirmation=True,
    )
    assert report.document_name == "Pediatric Label"
    assert report.author_approver == "Senior Director RA"
    assert len(report.changes) == 1
