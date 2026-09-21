"""Regulatory validation service module.

Applies deterministic validation rules to ensure proposed changes comply with
regulatory documentation integrity and do not introduce unvalidated anomalies.
"""

from typing import List, Optional
from app.models.document_change import ChangeImpact, ProposedChange, ValidationFinding


class ValidationService:
    """Deterministic validation engine for regulatory change proposals."""

    def validate_proposal(self, proposal: ProposedChange) -> ChangeImpact:
        """Run validation rules against a proposed document change and evaluate impact."""
        findings: List[ValidationFinding] = []

        # Rule 1: Text completeness check
        if not proposal.proposed_text or len(proposal.proposed_text.strip()) < 10:
            findings.append(
                ValidationFinding(
                    rule_id="REG-VAL-001",
                    rule_name="Text Completeness",
                    severity="ERROR",
                    status="FAILED",
                    field="proposed_text",
                    message="Proposed text must not be empty and must provide meaningful regulatory content.",
                    passed=False,
                )
            )
        else:
            findings.append(
                ValidationFinding(
                    rule_id="REG-VAL-001",
                    rule_name="Text Completeness",
                    severity="INFO",
                    status="PASSED",
                    field="proposed_text",
                    message="Proposed text completeness satisfied.",
                    passed=True,
                )
            )

        # Rule 2: Rationale presence check
        if not proposal.rationale or len(proposal.rationale.strip()) < 5:
            findings.append(
                ValidationFinding(
                    rule_id="REG-VAL-002",
                    rule_name="Rationale Presence",
                    severity="ERROR",
                    status="FAILED",
                    field="rationale",
                    message="A documented clinical/regulatory rationale is required for every proposed change.",
                    passed=False,
                )
            )
        else:
            findings.append(
                ValidationFinding(
                    rule_id="REG-VAL-002",
                    rule_name="Rationale Presence",
                    severity="INFO",
                    status="PASSED",
                    field="rationale",
                    message="Regulatory rationale validated.",
                    passed=True,
                )
            )

        # Rule 3: Provenance check
        if proposal.source_evidence is None:
            findings.append(
                ValidationFinding(
                    rule_id="REG-VAL-003",
                    rule_name="Provenance Citation",
                    severity="WARNING",
                    status="PASSED",
                    field="source_evidence",
                    message="Change does not link to an external regulatory evidence trace.",
                    passed=True,
                )
            )
        else:
            findings.append(
                ValidationFinding(
                    rule_id="REG-VAL-003",
                    rule_name="Provenance Citation",
                    severity="INFO",
                    status="PASSED",
                    field="source_evidence",
                    message="External regulatory evidence trace verified.",
                    passed=True,
                )
            )

        # Rule 4: Decision Linkage check
        if not proposal.decision_id or not proposal.decision_id.strip():
            findings.append(
                ValidationFinding(
                    rule_id="REG-VAL-004",
                    rule_name="Decision Linkage",
                    severity="ERROR",
                    status="FAILED",
                    field="decision_id",
                    message="Proposal is not linked to a valid human reviewer decision ID.",
                    passed=False,
                )
            )
        else:
            findings.append(
                ValidationFinding(
                    rule_id="REG-VAL-004",
                    rule_name="Decision Linkage",
                    severity="INFO",
                    status="PASSED",
                    field="decision_id",
                    message="Human reviewer decision linkage verified.",
                    passed=True,
                )
            )

        all_passed = not any(f.severity == "ERROR" and not f.passed for f in findings)
        risk_level = "LOW" if all_passed else "HIGH"

        # Separate observed impact from potential impacts requiring reviewer verification
        observed_impacts: List[str] = [
            f"Direct replacement in target section '{proposal.section}'",
        ]
        potential_impacts: List[str] = []

        affected_sections_set = {proposal.section}
        affected_docs_set = set()
        if proposal.document_name:
            affected_docs_set.add(proposal.document_name)

        for occ in proposal.related_occurrences:
            affected_sections_set.add(occ.section)
            if occ.document_name:
                affected_docs_set.add(occ.document_name)
            if occ.match_type == "exact_match":
                observed_impacts.append(
                    f"Exact text match in section '{occ.section}' ({occ.document_name or 'Current Document'})"
                )
            else:
                potential_impacts.append(
                    f"{occ.match_type.replace('_', ' ').title()} in section '{occ.section}' requires reviewer verification: {occ.reason or occ.current_text[:80]}"
                )

        if not proposal.source_evidence:
            potential_impacts.append("No external source evidence trace cited; reviewer verification recommended.")

        reviewer_attention = bool(any(f.severity in ("WARNING", "ERROR") for f in findings) or potential_impacts)

        return ChangeImpact(
            risk_level=risk_level,
            affected_sections_count=len(affected_sections_set),
            affected_sections=sorted(list(affected_sections_set)),
            affected_occurrences=proposal.related_occurrences,
            affected_documents=sorted(list(affected_docs_set)),
            affected_content_count=1 + len(proposal.related_occurrences),
            observed_impacts=observed_impacts,
            potential_impacts=potential_impacts,
            reviewer_attention_required=reviewer_attention,
            findings=findings,
            validation_passed=all_passed,
            validation_status=all_passed,
        )

    def validate_approval(
        self,
        approver_name: Optional[str],
        approval_confirmation: bool,
        proposals: List[ProposedChange],
    ) -> List[ValidationFinding]:
        """Validate human approval gate requirements before generating an Approved Change Report."""
        findings: List[ValidationFinding] = []

        # Check explicit confirmation (MUST NEVER DEFAULT TO TRUE)
        if not approval_confirmation:
            findings.append(
                ValidationFinding(
                    rule_id="REG-VAL-005",
                    rule_name="Human Approval Confirmation",
                    severity="ERROR",
                    status="FAILED",
                    field="approval_confirmation",
                    message="Explicit human approval confirmation (approval_confirmation=true) is strictly required.",
                    passed=False,
                )
            )
        else:
            findings.append(
                ValidationFinding(
                    rule_id="REG-VAL-005",
                    rule_name="Human Approval Confirmation",
                    severity="INFO",
                    status="PASSED",
                    field="approval_confirmation",
                    message="Explicit human approval confirmation provided.",
                    passed=True,
                )
            )

        # Check approver identity
        if not approver_name or not approver_name.strip():
            findings.append(
                ValidationFinding(
                    rule_id="REG-VAL-005",
                    rule_name="Approver Identity",
                    severity="ERROR",
                    status="FAILED",
                    field="author_approver",
                    message="Valid regulatory approver identity is required for authorization.",
                    passed=False,
                )
            )
        else:
            findings.append(
                ValidationFinding(
                    rule_id="REG-VAL-005",
                    rule_name="Approver Identity",
                    severity="INFO",
                    status="PASSED",
                    field="author_approver",
                    message="Approver identity verified.",
                    passed=True,
                )
            )

        # Check that proposals list is not empty and contains no rejected items
        if not proposals:
            findings.append(
                ValidationFinding(
                    rule_id="REG-VAL-005",
                    rule_name="Approved Proposals Presence",
                    severity="ERROR",
                    status="FAILED",
                    field="changes",
                    message="Cannot generate an Approved Change Report without authorized proposals.",
                    passed=False,
                )
            )
        else:
            rejected_proposals = [p for p in proposals if getattr(p, "decision_type", None) == "REJECT" or getattr(p, "status", None) == "REJECTED"]
            if rejected_proposals:
                findings.append(
                    ValidationFinding(
                        rule_id="REG-VAL-005",
                        rule_name="No Rejected Proposals in Approval",
                        severity="ERROR",
                        status="FAILED",
                        field="changes",
                        message="Rejected decisions must not be included in an Approved Change Report.",
                        passed=False,
                    )
                )

        return findings
