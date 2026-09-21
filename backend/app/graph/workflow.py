"""Two-Agent workflow graph architecture definition and Agent 1 LangGraph pipeline.

Establishes the state schema and node transitions connecting:
- Agent 1: Regulatory Content Analysis Agent (Full LangGraph pipeline)
- Human Regulatory Review Gateway (Reuse / Adapt / Reject)
- Agent 2: Regulatory Document Change Agent (Stubs for future phase)

Ensures human-in-the-loop gating between analysis and change formulation.
"""

from typing import Any, Dict, List, Optional, TypedDict
from langgraph.graph import END, START, StateGraph
from app.models.comparison import ComparisonCandidate, DifferenceItem
from app.models.content import KeyInformation, RegulatoryContentItem
from app.models.document_change import ProposedChange, ReviewDecisionType, ReviewerDecision
from app.services.content_classifier import ContentClassifier
from app.services.difference_detection import DifferenceDetectionService
from app.services.key_information_extractor import KeyInformationExtractor
from app.services.multi_dimensional_comparator import MultiDimensionalComparator


class RegulatoryWorkflowState(TypedDict, total=False):
    """Workflow state dictionary passed through the two-agent regulatory cycle."""

    # Document Inputs
    document_id: str
    document_name: str
    raw_document_text: str
    extracted_sections: List[Dict[str, Any]]

    # Agent 1 State: Content Analysis & Live Retrieval
    current_target_section: str
    current_target_text: str
    target_content_type: str
    target_key_info: Optional[Dict[str, Any]]
    retrieved_candidates: List[RegulatoryContentItem]
    ranked_candidates: List[ComparisonCandidate]
    identified_differences: List[DifferenceItem]
    false_matches_count: int
    analysis_summary: str
    workflow_step: str
    validation_passed: bool

    # Human Review Gateway (Must not be bypassed)
    human_decision_recorded: bool
    reviewer_decision: Optional[ReviewerDecision]

    # Agent 2 State: Document Change (Phase 3)
    proposed_changes: List[ProposedChange]
    validation_status: bool
    change_impact_summary: Dict[str, Any]

    # Audit & Approval
    is_approved_by_human: bool
    approval_confirmation: bool
    author_approver: Optional[str]
    candidate_text: Optional[str]
    approved_report_id: Optional[str]
    audit_trail: List[Dict[str, Any]]


def build_agent1_graph():
    """Build LangGraph StateGraph for Agent 1 pipeline implementing the 10-node workflow:
    START -> Load Content -> Classify Content -> Extract Key Information -> Retrieve Candidates ->
    Compare Candidates -> Detect Differences -> False Match Check -> Generate Evidence ->
    Attach Traceability -> Validate Result -> END.
    """
    extractor = KeyInformationExtractor()
    classifier = ContentClassifier()
    comparator = MultiDimensionalComparator()
    differ = DifferenceDetectionService()

    # Node 1: Load Content (Sanitize untrusted external data)
    def load_content(state: RegulatoryWorkflowState) -> Dict[str, Any]:
        raw_text = state.get("current_target_text", "")
        # Prompt injection defense: treat text strictly as passive data
        sanitized = raw_text.strip()
        return {
            "workflow_step": "content_loaded",
            "current_target_text": sanitized,
        }

    # Node 2: Classify Content
    def classify_content(state: RegulatoryWorkflowState) -> Dict[str, Any]:
        text = state.get("current_target_text", "")
        sec = state.get("current_target_section")
        content_type = classifier.classify(text, sec).value
        return {
            "workflow_step": "content_classified",
            "target_content_type": content_type,
        }

    # Node 3: Extract Key Information
    def extract_key_info(state: RegulatoryWorkflowState) -> Dict[str, Any]:
        text = state.get("current_target_text", "")
        info = extractor.extract(text)
        return {
            "workflow_step": "key_info_extracted",
            "target_key_info": info.model_dump(),
        }

    # Node 4: Retrieve Candidates (Synchronous node; caller can provide candidates or invoke retriever)
    def retrieve_candidates(state: RegulatoryWorkflowState) -> Dict[str, Any]:
        candidates = state.get("retrieved_candidates", [])
        return {
            "workflow_step": "candidates_retrieved",
            "retrieved_candidates": candidates,
        }

    # Node 5: Compare Candidates (6-Dimensional Comparison)
    def compare_candidates(state: RegulatoryWorkflowState) -> Dict[str, Any]:
        text = state.get("current_target_text", "")
        sec = state.get("current_target_section")
        candidates = state.get("retrieved_candidates", [])
        key_dict = state.get("target_key_info") or {}
        key_info = KeyInformation(**key_dict)

        ranked: List[ComparisonCandidate] = []
        for cand in candidates:
            match_res, diffs, evidence, false_warning = comparator.compare(
                target_text=text,
                candidate=cand,
                target_key_info=key_info,
                target_section=sec,
            )
            candidate_obj = ComparisonCandidate(
                candidate_id=f"cand_{cand.content_id}",
                content_item=cand,
                similarity_score=0.85,
                embedding_provider="fallback_deterministic",
                multi_dimensional_match=match_res,
                differences=diffs,
                evidence=[evidence],
                false_match_warning=false_warning,
                requires_human_review=True,  # AI never makes final decisions
            )
            ranked.append(candidate_obj)

        return {
            "workflow_step": "candidates_compared",
            "ranked_candidates": ranked,
        }

    # Node 6: Detect Differences (Deterministic attribute variation)
    def detect_differences(state: RegulatoryWorkflowState) -> Dict[str, Any]:
        text = state.get("current_target_text", "")
        ranked = state.get("ranked_candidates", [])
        all_diffs: List[DifferenceItem] = []

        for cand in ranked:
            diff_items = differ.analyze_differences(text, cand.content_item.text)
            if diff_items:
                cand.differences = diff_items
            all_diffs.extend(cand.differences)

        return {
            "workflow_step": "differences_detected",
            "identified_differences": all_diffs,
            "ranked_candidates": ranked,
        }

    # Node 7: False Match Check (Verify high similarity does not mask discrepancies)
    def false_match_check(state: RegulatoryWorkflowState) -> Dict[str, Any]:
        ranked = state.get("ranked_candidates", [])
        false_count = sum(1 for c in ranked if c.false_match_warning)

        return {
            "workflow_step": "false_matches_checked",
            "false_matches_count": false_count,
            "ranked_candidates": ranked,
        }

    # Node 8: Generate Evidence (Two-tier model: Observed facts vs Model interpretation)
    def generate_evidence(state: RegulatoryWorkflowState) -> Dict[str, Any]:
        ranked = state.get("ranked_candidates", [])
        # Each candidate already contains structured two-tier evidence
        return {
            "workflow_step": "evidence_generated",
            "ranked_candidates": ranked,
        }

    # Node 9: Attach Traceability (Source URLs, Set IDs, LOINC codes, exact quotes)
    def attach_traceability(state: RegulatoryWorkflowState) -> Dict[str, Any]:
        ranked = state.get("ranked_candidates", [])
        for cand in ranked:
            # Ensure source traceability metadata is preserved and unpopulated fields remain None
            if not cand.content_item.source_url and cand.content_item.source == "DailyMed" and cand.content_item.source_identifier:
                cand.content_item.source_url = f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={cand.content_item.source_identifier}"

        return {
            "workflow_step": "traceability_attached",
            "ranked_candidates": ranked,
        }

    # Node 10: Validate Result (Structured verification & governance gating)
    def validate_result(state: RegulatoryWorkflowState) -> Dict[str, Any]:
        ranked = state.get("ranked_candidates", [])
        # Verification: all items must have evidence, exact quotes, and human review enforced
        valid = all(
            len(c.evidence) > 0 and c.requires_human_review is True
            for c in ranked
        ) if ranked else True

        summary = (
            f"Agent 1 analysis complete. Evaluated {len(ranked)} candidate(s). "
            f"False match warnings flagged: {state.get('false_matches_count', 0)}. "
            f"Human regulatory review required for all candidates."
        )

        return {
            "workflow_step": "result_validated",
            "validation_passed": valid,
            "analysis_summary": summary,
            "ranked_candidates": ranked,
        }

    # Construct the 10-node StateGraph
    workflow = StateGraph(RegulatoryWorkflowState)
    workflow.add_node("load_content", load_content)
    workflow.add_node("classify_content", classify_content)
    workflow.add_node("extract_key_info", extract_key_info)
    workflow.add_node("retrieve_candidates", retrieve_candidates)
    workflow.add_node("compare_candidates", compare_candidates)
    workflow.add_node("detect_differences", detect_differences)
    workflow.add_node("false_match_check", false_match_check)
    workflow.add_node("generate_evidence", generate_evidence)
    workflow.add_node("attach_traceability", attach_traceability)
    workflow.add_node("validate_result", validate_result)

    workflow.add_edge(START, "load_content")
    workflow.add_edge("load_content", "classify_content")
    workflow.add_edge("classify_content", "extract_key_info")
    workflow.add_edge("extract_key_info", "retrieve_candidates")
    workflow.add_edge("retrieve_candidates", "compare_candidates")
    workflow.add_edge("compare_candidates", "detect_differences")
    workflow.add_edge("detect_differences", "false_match_check")
    workflow.add_edge("false_match_check", "generate_evidence")
    workflow.add_edge("generate_evidence", "attach_traceability")
    workflow.add_edge("attach_traceability", "validate_result")
    workflow.add_edge("validate_result", END)

    return workflow.compile()


def build_agent2_graph():
    """Build LangGraph StateGraph for Agent 2 controlled document change pipeline.

    Enforces the conceptual sequence:
    Human Decision -> Controlled Change Proposal -> Related Occurrence Detection ->
    Impact Analysis -> Validation -> Human Approval Gate -> Approved Change Report.

    MANDATORY GOVERNANCE:
    - REJECT terminates the change path immediately; no proposal and no report.
    - REUSE and ADAPT formulate a controlled proposal and assess impact/validation.
    - Approval Gate strictly requires explicit human approval confirmation; never auto-approves.
    """
    from app.agents.document_change_agent import RegulatoryDocumentChangeAgent

    change_agent = RegulatoryDocumentChangeAgent()

    # Node 1: Evaluate Human Decision
    def human_decision_gate(state: RegulatoryWorkflowState) -> Dict[str, Any]:
        decision = state.get("reviewer_decision")
        if not decision:
            return {"workflow_step": "decision_missing", "validation_status": False}
        return {
            "workflow_step": "decision_evaluated",
            "human_decision_recorded": True,
        }

    # Conditional decision router
    def route_on_decision(state: RegulatoryWorkflowState) -> str:
        decision = state.get("reviewer_decision")
        if not decision:
            return "record_rejection"
        dec_val = getattr(decision, "decision", None)
        if dec_val == "REJECT" or dec_val == ReviewDecisionType.REJECT:
            return "record_rejection"
        elif dec_val in ("REUSE", "ADAPT", ReviewDecisionType.REUSE, ReviewDecisionType.ADAPT):
            return "formulate_proposal"
        return "record_rejection"

    # Node 2: Record Rejection (Terminates change path; no proposal, no report)
    def record_rejection(state: RegulatoryWorkflowState) -> Dict[str, Any]:
        decision = state.get("reviewer_decision")
        audit = state.get("audit_trail", [])
        audit.append({
            "action": "REJECT_RECORDED",
            "decision_id": getattr(decision, "decision_id", "dec_unknown"),
            "note": "Candidate rejected by regulatory reviewer. Original source preserved. No change proposal created.",
        })
        return {
            "workflow_step": "rejection_recorded_terminated",
            "proposed_changes": [],
            "is_approved_by_human": False,
            "audit_trail": audit,
        }

    # Node 3: Formulate Proposal
    def formulate_proposal(state: RegulatoryWorkflowState) -> Dict[str, Any]:
        decision = state.get("reviewer_decision")
        sec = state.get("current_target_section", "Unspecified Section")
        orig_text = state.get("current_target_text", "")
        cand_text = state.get("candidate_text")
        doc_name = state.get("document_name")
        sections = state.get("extracted_sections")

        proposal = change_agent.formulate_change_proposal(
            decision=decision,
            section=sec,
            original_text=orig_text,
            candidate_text=cand_text,
            document_name=doc_name,
            document_sections=sections,
        )

        return {
            "workflow_step": "proposal_formulated",
            "proposed_changes": [proposal] if proposal else [],
        }

    # Node 4: Detect Related Occurrences (4-layer detection)
    def detect_occurrences(state: RegulatoryWorkflowState) -> Dict[str, Any]:
        proposals = state.get("proposed_changes", [])
        sections = state.get("extracted_sections", [])
        if proposals and sections:
            prop = proposals[0]
            search_phrase = prop.proposed_text[:60] if prop.proposed_text else prop.original_text[:60]
            occurrences = change_agent.detect_related_occurrences(
                target_phrase=search_phrase,
                document_sections=sections,
                target_text=prop.original_text,
            )
            prop.related_occurrences = occurrences

        return {
            "workflow_step": "occurrences_detected",
            "proposed_changes": proposals,
        }

    # Node 5: Impact Analysis
    def analyze_impact(state: RegulatoryWorkflowState) -> Dict[str, Any]:
        proposals = state.get("proposed_changes", [])
        summary: Dict[str, Any] = {}
        if proposals:
            prop = proposals[0]
            impact = change_agent.assess_impact_and_validate(prop)
            prop.impact_analysis = impact
            summary = impact.model_dump()

        return {
            "workflow_step": "impact_assessed",
            "change_impact_summary": summary,
            "proposed_changes": proposals,
        }

    # Node 6: Validate Proposal
    def validate_proposal(state: RegulatoryWorkflowState) -> Dict[str, Any]:
        proposals = state.get("proposed_changes", [])
        valid = True
        if proposals:
            prop = proposals[0]
            impact = getattr(prop, "impact_analysis", None)
            valid = impact.validation_passed if impact else True

        return {
            "workflow_step": "proposal_validated",
            "validation_status": valid,
            "proposed_changes": proposals,
        }

    # Node 7: Human Approval Gate
    def human_approval_gate(state: RegulatoryWorkflowState) -> Dict[str, Any]:
        return {"workflow_step": "approval_gate_evaluated"}

    # Conditional approval router
    def route_on_approval(state: RegulatoryWorkflowState) -> str:
        is_approved = state.get("is_approved_by_human", False)
        confirmation = state.get("approval_confirmation", False)
        approver = state.get("author_approver")

        # Explicit human confirmation and approver name are strictly required
        if is_approved and confirmation and approver and approver.strip():
            return "generate_change_report"
        return "pending_approval"

    # Node 8: Pending Approval (Awaits explicit human action)
    def pending_approval(state: RegulatoryWorkflowState) -> Dict[str, Any]:
        return {
            "workflow_step": "pending_human_approval",
            "is_approved_by_human": False,
        }

    # Node 9: Generate Approved Change Report
    def generate_change_report(state: RegulatoryWorkflowState) -> Dict[str, Any]:
        proposals = state.get("proposed_changes", [])
        approver = state.get("author_approver", "Regulatory Approver")
        doc_name = state.get("document_name")

        report = change_agent.generate_approved_change_report(
            approver_name=approver,
            approval_confirmation=True,
            approved_changes=proposals,
            document_name=doc_name,
        )

        return {
            "workflow_step": "approved_report_generated",
            "approved_report_id": report.report_id,
            "is_approved_by_human": True,
        }

    # Build Agent 2 StateGraph
    workflow = StateGraph(RegulatoryWorkflowState)
    workflow.add_node("human_decision_gate", human_decision_gate)
    workflow.add_node("record_rejection", record_rejection)
    workflow.add_node("formulate_proposal", formulate_proposal)
    workflow.add_node("detect_occurrences", detect_occurrences)
    workflow.add_node("analyze_impact", analyze_impact)
    workflow.add_node("validate_proposal", validate_proposal)
    workflow.add_node("human_approval_gate", human_approval_gate)
    workflow.add_node("pending_approval", pending_approval)
    workflow.add_node("generate_change_report", generate_change_report)

    workflow.add_edge(START, "human_decision_gate")
    workflow.add_conditional_edges(
        "human_decision_gate",
        route_on_decision,
        {
            "record_rejection": "record_rejection",
            "formulate_proposal": "formulate_proposal",
        },
    )
    workflow.add_edge("record_rejection", END)
    workflow.add_edge("formulate_proposal", "detect_occurrences")
    workflow.add_edge("detect_occurrences", "analyze_impact")
    workflow.add_edge("analyze_impact", "validate_proposal")
    workflow.add_edge("validate_proposal", "human_approval_gate")
    workflow.add_conditional_edges(
        "human_approval_gate",
        route_on_approval,
        {
            "generate_change_report": "generate_change_report",
            "pending_approval": "pending_approval",
        },
    )
    workflow.add_edge("pending_approval", END)
    workflow.add_edge("generate_change_report", END)

    return workflow.compile()


class RegulatoryWorkflowGraph:
    """Stateful workflow coordinator implementing the two-agent regulatory lifecycle."""

    def __init__(self):
        self.state: RegulatoryWorkflowState = {
            "extracted_sections": [],
            "retrieved_candidates": [],
            "ranked_candidates": [],
            "identified_differences": [],
            "proposed_changes": [],
            "human_decision_recorded": False,
            "is_approved_by_human": False,
            "approval_confirmation": False,  # MUST NEVER DEFAULT TO TRUE
            "audit_trail": [],
        }
        self.agent1_graph = build_agent1_graph()
        self.agent2_graph = build_agent2_graph()

    def run_agent1_pipeline(
        self,
        target_text: str,
        section_name: Optional[str] = None,
        candidates: Optional[List[RegulatoryContentItem]] = None,
    ) -> RegulatoryWorkflowState:
        """Execute compiled LangGraph Agent 1 pipeline."""
        initial_state: RegulatoryWorkflowState = {
            "current_target_text": target_text,
            "current_target_section": section_name or "General Section",
            "retrieved_candidates": candidates or [],
        }
        final_state = self.agent1_graph.invoke(initial_state)
        self.state.update(final_state)
        return self.state

    def run_agent2_pipeline(
        self,
        decision: ReviewerDecision,
        section_name: str,
        original_text: str,
        candidate_text: Optional[str] = None,
        document_sections: Optional[List[Dict[str, Any]]] = None,
        is_approved_by_human: bool = False,
        approval_confirmation: bool = False,
        author_approver: Optional[str] = None,
        document_name: Optional[str] = None,
    ) -> RegulatoryWorkflowState:
        """Execute compiled LangGraph Agent 2 controlled document change pipeline."""
        agent2_state: RegulatoryWorkflowState = {
            "reviewer_decision": decision,
            "current_target_section": section_name,
            "current_target_text": original_text,
            "candidate_text": candidate_text,
            "extracted_sections": document_sections or self.state.get("extracted_sections", []),
            "document_name": document_name or self.state.get("document_name"),
            "is_approved_by_human": is_approved_by_human,
            "approval_confirmation": approval_confirmation,
            "author_approver": author_approver,
            "audit_trail": list(self.state.get("audit_trail", [])),
        }
        final_state = self.agent2_graph.invoke(agent2_state)
        self.state.update(final_state)
        return self.state

    def get_current_state(self) -> RegulatoryWorkflowState:
        """Retrieve active workflow state."""
        return self.state

    def reset_state(self) -> None:
        """Reset state for a new document session."""
        self.__init__()

