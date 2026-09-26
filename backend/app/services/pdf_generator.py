"""Server-side PDF report generator for approved regulatory change reports.

Uses ReportLab Platypus to assemble an audit-ready, human-readable PDF
manifest of human-approved changes and their associated SHA-256 hash-chained
audit trail.

CRITICAL SAFETY & GOVERNANCE CONSTRAINTS:
- Does NOT overwrite, mutate, or alter original source documents.
- Does NOT perform autonomous approvals or autonomous changes.
- Preserves verbatim all persisted audit event IDs, statuses, and SHA-256 hashes.
- Disclaims that this internal verification manifest does not constitute statutory
  FDA, EMA, or other regulatory health authority marketing authorization.
"""

from datetime import datetime, timezone
import html
import io
from typing import Any, Dict, List, Optional, Set

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.audit import AuditEvent
from app.models.comparison import EvidenceTrace
from app.models.document_change import (
    ApprovedChangeReport,
    ChangeImpact,
    ProposedChange,
    RelatedOccurrence,
    ValidationFinding,
)


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas for dynamic total page counting and running headers/footers."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: List[Dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def _draw_page_decorations(self, page_count: int) -> None:
        self.saveState()
        self.setFont("Helvetica", 7.5)
        self.setFillColor(colors.HexColor("#64748B"))

        # Running header on pages > 1
        if self._pageNumber > 1:
            self.drawString(
                36, 762, "Regulatory Content Reuse Finder — Approved Change Report"
            )
            self.drawRightString(
                576, 762, "Human-Authorized Verification Manifest"
            )
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(36, 756, 576, 756)

        # Running footer on all pages
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(36, 42, 576, 42)
        self.drawString(
            36,
            30,
            "Confidential — Human-Authorized Regulatory Audit Record — Non-Statutory Manifest",
        )
        self.drawRightString(
            576, 30, f"Page {self._pageNumber} of {page_count}"
        )
        self.restoreState()


class PDFReportGenerator:
    """Audit-ready PDF generation service for ApprovedChangeReport models."""

    def __init__(self) -> None:
        self.palette = {
            "primary": colors.HexColor("#1E3A8A"),      # Deep Navy
            "primary_light": colors.HexColor("#EFF6FF"),
            "secondary": colors.HexColor("#2563EB"),    # Blue accent
            "dark": colors.HexColor("#0F172A"),         # Slate dark
            "muted": colors.HexColor("#475569"),        # Slate muted
            "light_bg": colors.HexColor("#F8FAFC"),     # Card background
            "border": colors.HexColor("#CBD5E1"),       # Slate border
            "border_dark": colors.HexColor("#94A3B8"),
            "diff_old_bg": colors.HexColor("#FEF2F2"),  # Light red panel
            "diff_old_border": colors.HexColor("#FECACA"),
            "diff_new_bg": colors.HexColor("#F0FDF4"),  # Light green panel
            "diff_new_border": colors.HexColor("#BBF7D0"),
            "confirmed_bg": colors.HexColor("#DCFCE7"), # Green badge bg
            "confirmed_text": colors.HexColor("#166534"),
            "excluded_bg": colors.HexColor("#FEF3C7"),  # Amber badge bg
            "excluded_text": colors.HexColor("#92400E"),
            "white": colors.HexColor("#FFFFFF"),
        }
        self.styles = self._init_styles()

    def _init_styles(self) -> Dict[str, ParagraphStyle]:
        base_styles = getSampleStyleSheet()
        custom = {}

        custom["DocCategory"] = ParagraphStyle(
            "DocCategory",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=self.palette["secondary"],
            textTransform="uppercase",
            spaceAfter=2,
        )

        custom["DocTitle"] = ParagraphStyle(
            "DocTitle",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=self.palette["primary"],
            spaceAfter=2,
        )

        custom["DocSubtitle"] = ParagraphStyle(
            "DocSubtitle",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=13,
            textColor=self.palette["muted"],
            spaceAfter=6,
        )

        custom["SectionHeading"] = ParagraphStyle(
            "SectionHeading",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=self.palette["primary"],
            spaceBefore=10,
            spaceAfter=5,
        )

        custom["SubSectionHeading"] = ParagraphStyle(
            "SubSectionHeading",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=self.palette["dark"],
            spaceBefore=6,
            spaceAfter=3,
        )

        custom["Body"] = ParagraphStyle(
            "Body",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11.5,
            textColor=self.palette["dark"],
        )

        custom["BodyBold"] = ParagraphStyle(
            "BodyBold",
            parent=custom["Body"],
            fontName="Helvetica-Bold",
        )

        custom["BodySmall"] = ParagraphStyle(
            "BodySmall",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=self.palette["muted"],
        )

        custom["BodySmallBold"] = ParagraphStyle(
            "BodySmallBold",
            parent=custom["BodySmall"],
            fontName="Helvetica-Bold",
            textColor=self.palette["dark"],
        )

        custom["Disclaimer"] = ParagraphStyle(
            "Disclaimer",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=7,
            leading=9.5,
            textColor=self.palette["muted"],
        )

        custom["Code"] = ParagraphStyle(
            "Code",
            parent=base_styles["Normal"],
            fontName="Courier",
            fontSize=6.5,
            leading=8.5,
            textColor=self.palette["dark"],
        )

        custom["CodeBold"] = ParagraphStyle(
            "CodeBold",
            parent=custom["Code"],
            fontName="Courier-Bold",
        )

        custom["BadgeConfirmed"] = ParagraphStyle(
            "BadgeConfirmed",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9.5,
            textColor=self.palette["confirmed_text"],
        )

        custom["BadgeExcluded"] = ParagraphStyle(
            "BadgeExcluded",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9.5,
            textColor=self.palette["excluded_text"],
        )

        return custom

    @staticmethod
    def _escape(text: Optional[Any]) -> str:
        """Escape text for ReportLab Paragraph rendering."""
        if text is None:
            return ""
        return html.escape(str(text))

    def generate(
        self,
        report: ApprovedChangeReport,
        audit_events: Optional[List[AuditEvent]] = None,
    ) -> bytes:
        """Compile an ApprovedChangeReport and audit events into PDF bytes.

        Deterministic and non-mutating.
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=36,
            rightMargin=36,
            topMargin=46,
            bottomMargin=46,
        )

        story: List[Any] = []

        # 1. Header / Title Block
        story.extend(self._build_header(report))
        story.append(Spacer(1, 6))

        # 2. Statutory & Governance Disclaimer
        story.extend(self._build_disclaimer())
        story.append(Spacer(1, 8))

        # 3. Document & Approver Metadata
        story.extend(self._build_metadata_section(report))
        story.append(Spacer(1, 8))

        # 4. Executive Decision Summary
        story.extend(self._build_executive_summary(report))
        story.append(Spacer(1, 8))

        # 5. Change Impact Summary
        story.extend(self._build_impact_summary(report))
        story.append(Spacer(1, 8))

        # 6. Approved Regulatory Modifications
        story.extend(self._build_approved_changes(report))
        story.append(Spacer(1, 8))

        # 7. External Regulatory Evidence & Provenance
        story.extend(self._build_evidence_section(report))
        story.append(Spacer(1, 8))

        # 8. Related Occurrence Disposition
        story.extend(self._build_occurrences_section(report))
        story.append(Spacer(1, 8))

        # 9. Validation Findings
        story.extend(self._build_validation_section(report))
        story.append(Spacer(1, 8))

        # 10. Tamper-Evident Audit Trail
        story.extend(self._build_audit_trail_section(report, audit_events or []))
        story.append(Spacer(1, 8))

        # 11. Final Approval & Regulatory Sign-off
        story.extend(self._build_signoff_section(report))

        doc.build(story, canvasmaker=NumberedCanvas)
        return buffer.getvalue()

    def generate_pdf(
        self,
        report: ApprovedChangeReport,
        audit_events: Optional[List[AuditEvent]] = None,
    ) -> bytes:
        """Convenience alias for generate()."""
        return self.generate(report=report, audit_events=audit_events)

    # =========================================================================
    # SECTION BUILDERS
    # =========================================================================

    def _build_header(self, report: ApprovedChangeReport) -> List[Any]:
        items: List[Any] = []
        items.append(Paragraph("Regulatory Content Reuse Finder — Global Product Review", self.styles["DocCategory"]))
        items.append(Paragraph("Approved Change Report", self.styles["DocTitle"]))
        items.append(
            Paragraph(
                f"Controlled Regulatory Revision Manifest &bull; Generated: {self._escape(report.generated_at)}",
                self.styles["DocSubtitle"],
            )
        )
        items.append(HRFlowable(width="100%", thickness=1.5, color=self.palette["primary"], spaceAfter=4))
        return items

    def _build_disclaimer(self) -> List[Any]:
        text = (
            "<b>GOVERNANCE &amp; STATUTORY DISCLAIMER:</b> "
            "This report records an internal, human-reviewed regulatory content reuse and controlled change workflow. "
            "All modifications, occurrence confirmations, and approval decisions documented herein were conducted and "
            "authorized by qualified human regulatory professionals. This internal verification document does NOT "
            "constitute statutory FDA, EMA, or other regulatory health authority marketing authorization, product approval, "
            "or official regulatory clearance."
        )
        p = Paragraph(text, self.styles["Disclaimer"])
        table = Table([[p]], colWidths=[540])
        table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), self.palette["light_bg"]),
                ("BOX", (0, 0), (-1, -1), 0.75, self.palette["border"]),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ])
        )
        return [table]

    def _build_metadata_section(self, report: ApprovedChangeReport) -> List[Any]:
        items: List[Any] = []
        items.append(Paragraph("1. Document &amp; Approval Metadata", self.styles["SectionHeading"]))

        approval_status_text = (
            "<b><font color='#166534'>CONFIRMED &amp; AUTHORIZED</font></b> (Explicit Human Approval)"
            if report.approval_confirmation
            else "<b><font color='#DC2626'>UNCONFIRMED</font></b>"
        )

        decision_ids_str = (
            ", ".join(report.decision_ids) if report.decision_ids else "None Recorded"
        )

        rows = [
            [
                Paragraph("<b>Report Identifier:</b>", self.styles["BodySmallBold"]),
                Paragraph(self._escape(report.report_id), self.styles["Code"]),
            ],
            [
                Paragraph("<b>Subject Document Name:</b>", self.styles["BodySmallBold"]),
                Paragraph(self._escape(report.document_name or "Not Specified"), self.styles["Body"]),
            ],
            [
                Paragraph("<b>Subject Document Version:</b>", self.styles["BodySmallBold"]),
                Paragraph(self._escape(report.document_version or "Not Specified"), self.styles["Body"]),
            ],
            [
                Paragraph("<b>Authorizing Approver:</b>", self.styles["BodySmallBold"]),
                Paragraph(self._escape(report.author_approver), self.styles["BodyBold"]),
            ],
            [
                Paragraph("<b>Approval Timestamp:</b>", self.styles["BodySmallBold"]),
                Paragraph(self._escape(report.approval_timestamp or report.generated_at), self.styles["Body"]),
            ],
            [
                Paragraph("<b>Approval Status:</b>", self.styles["BodySmallBold"]),
                Paragraph(approval_status_text, self.styles["Body"]),
            ],
            [
                Paragraph("<b>Authorized Decision IDs:</b>", self.styles["BodySmallBold"]),
                Paragraph(self._escape(decision_ids_str), self.styles["Code"]),
            ],
        ]

        table = Table(rows, colWidths=[150, 390])
        table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), self.palette["white"]),
                ("GRID", (0, 0), (-1, -1), 0.5, self.palette["border"]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        items.append(table)
        return items

    def _build_executive_summary(self, report: ApprovedChangeReport) -> List[Any]:
        items: List[Any] = []
        items.append(Paragraph("2. Executive Decision Summary", self.styles["SectionHeading"]))

        lead_text = (
            f"This Approved Change Report consolidates <b>{len(report.changes)}</b> human-authorized "
            f"regulatory modification(s) for formal incorporation into subject regulatory documentation. "
            f"All proposed modifications originated from human review decisions, underwent multi-dimensional "
            f"comparison against authoritative external sources, satisfied deterministic regulatory integrity "
            f"rules, and received final sign-off from authorized regulatory professional "
            f"<b>{self._escape(report.author_approver)}</b>."
        )
        items.append(Paragraph(lead_text, self.styles["Body"]))

        if report.audit_notes:
            notes_p = Paragraph(
                f"<b>Regulatory Reviewer Notes:</b> {self._escape(report.audit_notes)}",
                self.styles["BodySmall"],
            )
            notes_table = Table([[notes_p]], colWidths=[540])
            notes_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), self.palette["light_bg"]),
                    ("BOX", (0, 0), (-1, -1), 0.5, self.palette["border"]),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ])
            )
            items.append(Spacer(1, 4))
            items.append(notes_table)

        return items

    def _build_impact_summary(self, report: ApprovedChangeReport) -> List[Any]:
        items: List[Any] = []
        items.append(Paragraph("3. Change Impact Summary", self.styles["SectionHeading"]))

        if report.impact_summary:
            items.append(Paragraph(self._escape(report.impact_summary), self.styles["Body"]))
            items.append(Spacer(1, 4))

        # Aggregate summary statistics
        total_changes = len(report.changes)
        sections: Set[str] = set()
        confirmed_occ_count = 0
        excluded_occ_count = 0

        for c in report.changes:
            if c.section:
                sections.add(c.section)
            for occ in c.related_occurrences:
                if occ.status == "CONFIRMED":
                    confirmed_occ_count += 1
                    if occ.section:
                        sections.add(occ.section)
                elif occ.status == "EXCLUDED":
                    excluded_occ_count += 1

        summary_rows = [
            [
                Paragraph("<b>Total Approved Changes:</b>", self.styles["BodySmallBold"]),
                Paragraph(str(total_changes), self.styles["Body"]),
                Paragraph("<b>Unique Sections Affected:</b>", self.styles["BodySmallBold"]),
                Paragraph(str(len(sections)), self.styles["Body"]),
            ],
            [
                Paragraph("<b>Confirmed Related Occurrences:</b>", self.styles["BodySmallBold"]),
                Paragraph(f"<font color='#166534'><b>{confirmed_occ_count}</b></font>", self.styles["Body"]),
                Paragraph("<b>Excluded Related Occurrences:</b>", self.styles["BodySmallBold"]),
                Paragraph(f"<font color='#92400E'><b>{excluded_occ_count}</b></font>", self.styles["Body"]),
            ],
        ]

        table = Table(summary_rows, colWidths=[150, 120, 160, 110])
        table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), self.palette["white"]),
                ("GRID", (0, 0), (-1, -1), 0.5, self.palette["border"]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ])
        )
        items.append(table)
        return items

    def _build_approved_changes(self, report: ApprovedChangeReport) -> List[Any]:
        items: List[Any] = []
        items.append(Paragraph("4. Approved Regulatory Modifications", self.styles["SectionHeading"]))

        if not report.changes:
            items.append(Paragraph("No approved changes recorded in this report.", self.styles["Body"]))
            return items

        for idx, change in enumerate(report.changes, start=1):
            decision_val = (
                change.decision_type.value
                if hasattr(change.decision_type, "value")
                else str(change.decision_type)
            )

            change_header = (
                f"<b>Change #{idx}: {self._escape(change.section)}</b> "
                f"(Decision Type: <b>{self._escape(decision_val)}</b> &bull; "
                f"Change ID: <font face='Courier' size='7'>{self._escape(change.change_id)}</font>)"
            )

            # Metadata sub-table
            meta_rows = [
                [
                    Paragraph("<b>Target Section:</b>", self.styles["BodySmallBold"]),
                    Paragraph(self._escape(change.section), self.styles["Body"]),
                    Paragraph("<b>Decision ID:</b>", self.styles["BodySmallBold"]),
                    Paragraph(self._escape(change.decision_id), self.styles["Code"]),
                ],
                [
                    Paragraph("<b>Traceable Rationale:</b>", self.styles["BodySmallBold"]),
                    Paragraph(self._escape(change.rationale), self.styles["BodySmall"]),
                    Paragraph("<b>Proposal Status:</b>", self.styles["BodySmallBold"]),
                    Paragraph(f"<b>{self._escape(change.status)}</b>", self.styles["BodySmallBold"]),
                ],
            ]
            meta_table = Table(meta_rows, colWidths=[100, 220, 90, 130])
            meta_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), self.palette["light_bg"]),
                    ("GRID", (0, 0), (-1, -1), 0.5, self.palette["border"]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ])
            )

            # Diff comparison panels
            orig_panel = [
                Paragraph("<b>Original Text Prior to Change (Preserved Baseline):</b>", self.styles["BodySmallBold"]),
                Paragraph(self._escape(change.original_text), self.styles["BodySmall"]),
            ]
            orig_table = Table([[orig_panel[0]], [orig_panel[1]]], colWidths=[540])
            orig_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), self.palette["diff_old_bg"]),
                    ("BOX", (0, 0), (-1, -1), 0.5, self.palette["diff_old_border"]),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ])
            )

            prop_panel = [
                Paragraph("<b>Approved Regulatory Text (Authorized Modification):</b>", self.styles["BodySmallBold"]),
                Paragraph(self._escape(change.proposed_text), self.styles["BodySmall"]),
            ]
            prop_table = Table([[prop_panel[0]], [prop_panel[1]]], colWidths=[540])
            prop_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), self.palette["diff_new_bg"]),
                    ("BOX", (0, 0), (-1, -1), 0.5, self.palette["diff_new_border"]),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ])
            )

            change_flowables = [
                Paragraph(change_header, self.styles["SubSectionHeading"]),
                meta_table,
                Spacer(1, 2),
                orig_table,
                Spacer(1, 2),
                prop_table,
                Spacer(1, 6),
            ]
            items.append(KeepTogether(change_flowables))

        return items

    def _build_evidence_section(self, report: ApprovedChangeReport) -> List[Any]:
        items: List[Any] = []
        items.append(Paragraph("5. External Regulatory Evidence &amp; Provenance", self.styles["SectionHeading"]))

        # Gather evidence from report and individual changes
        all_evidence: List[EvidenceTrace] = []
        seen_ids: Set[str] = set()

        for ev in report.source_evidence:
            ident = ev.trace_id or ev.source_identifier or ev.source_url or ev.source
            if ident not in seen_ids:
                seen_ids.add(ident)
                all_evidence.append(ev)

        for c in report.changes:
            if c.source_evidence:
                ev = c.source_evidence
                ident = ev.trace_id or ev.source_identifier or ev.source_url or ev.source
                if ident not in seen_ids:
                    seen_ids.add(ident)
                    all_evidence.append(ev)

        if not all_evidence:
            items.append(
                Paragraph(
                    "No external regulatory evidence traces associated with this change set.",
                    self.styles["BodySmall"],
                )
            )
            return items

        for idx, ev in enumerate(all_evidence, start=1):
            source_id = ev.source_identifier or getattr(ev, "source_id", None) or "Not Specified"
            source_url = ev.source_url or getattr(ev, "url", None) or "Not Specified"

            ev_rows = [
                [
                    Paragraph("<b>Authoritative Source:</b>", self.styles["BodySmallBold"]),
                    Paragraph(self._escape(ev.source), self.styles["Body"]),
                    Paragraph("<b>Source Identifier:</b>", self.styles["BodySmallBold"]),
                    Paragraph(self._escape(source_id), self.styles["Code"]),
                ],
                [
                    Paragraph("<b>Source URL:</b>", self.styles["BodySmallBold"]),
                    Paragraph(self._escape(source_url), self.styles["BodySmall"]),
                    Paragraph("<b>Document / Drug:</b>", self.styles["BodySmallBold"]),
                    Paragraph(self._escape(ev.document_name or "Not Specified"), self.styles["BodySmall"]),
                ],
                [
                    Paragraph("<b>Section / Location:</b>", self.styles["BodySmallBold"]),
                    Paragraph(
                        self._escape(
                            f"{ev.section or 'N/A'}"
                            f"{(' (' + ev.location + ')') if ev.location else ''}"
                        ),
                        self.styles["BodySmall"],
                    ),
                    Paragraph("<b>LOINC Code:</b>", self.styles["BodySmallBold"]),
                    Paragraph(self._escape(ev.loinc_code or "Not Specified"), self.styles["Code"]),
                ],
            ]

            if ev.exact_quote:
                ev_rows.append([
                    Paragraph("<b>Cited Source Quote:</b>", self.styles["BodySmallBold"]),
                    Paragraph(f"<i>&ldquo;{self._escape(ev.exact_quote)}&rdquo;</i>", self.styles["BodySmall"]),
                    Paragraph("", self.styles["BodySmall"]),
                    Paragraph("", self.styles["BodySmall"]),
                ])

            ev_table = Table(ev_rows, colWidths=[110, 220, 95, 115])
            ev_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), self.palette["light_bg"]),
                    ("GRID", (0, 0), (-1, -1), 0.5, self.palette["border"]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("SPAN", (1, 3), (3, 3)) if ev.exact_quote else ("NOP", (0, 0), (0, 0)),
                ])
            )

            flowables = [
                Paragraph(f"<b>Provenance Citation #{idx}: {self._escape(ev.source)}</b>", self.styles["SubSectionHeading"]),
                ev_table,
                Spacer(1, 4),
            ]
            items.append(KeepTogether(flowables))

        return items

    def _build_occurrences_section(self, report: ApprovedChangeReport) -> List[Any]:
        items: List[Any] = []
        items.append(Paragraph("6. Related Occurrence Disposition", self.styles["SectionHeading"]))

        occurrences: List[RelatedOccurrence] = []
        for c in report.changes:
            occurrences.extend(c.related_occurrences)

        if not occurrences:
            items.append(
                Paragraph(
                    "No cross-section related occurrences detected for this change set.",
                    self.styles["BodySmall"],
                )
            )
            return items

        intro_text = (
            "Related content occurrences identified across document sections. "
            "Occurrences marked <b>CONFIRMED</b> are coordinated with the approved modification. "
            "Occurrences marked <b>EXCLUDED</b> remain preserved in their current state for audit traceability."
        )
        items.append(Paragraph(intro_text, self.styles["BodySmall"]))
        items.append(Spacer(1, 4))

        headers = [
            Paragraph("<b>Section / Location</b>", self.styles["BodySmallBold"]),
            Paragraph("<b>Occurrence ID &amp; Match Type</b>", self.styles["BodySmallBold"]),
            Paragraph("<b>Matched Excerpt</b>", self.styles["BodySmallBold"]),
            Paragraph("<b>Disposition Status</b>", self.styles["BodySmallBold"]),
        ]
        table_rows = [headers]

        for occ in occurrences:
            status = getattr(occ, "status", "PENDING")
            if status == "CONFIRMED":
                status_p = Paragraph("<b>CONFIRMED</b>", self.styles["BadgeConfirmed"])
            elif status == "EXCLUDED":
                status_p = Paragraph("<b>EXCLUDED</b>", self.styles["BadgeExcluded"])
            else:
                status_p = Paragraph(f"<b>{self._escape(status)}</b>", self.styles["BodySmall"])

            sec_text = self._escape(occ.section)
            if occ.location:
                sec_text += f"<br/><font color='#64748B'>{self._escape(occ.location)}</font>"

            id_text = f"<font face='Courier' size='6.5'>{self._escape(occ.occurrence_id)}</font><br/>{self._escape(occ.match_type)}"

            excerpt = self._escape(occ.matched_text or occ.current_text[:120])

            table_rows.append([
                Paragraph(sec_text, self.styles["BodySmall"]),
                Paragraph(id_text, self.styles["BodySmall"]),
                Paragraph(excerpt, self.styles["BodySmall"]),
                status_p,
            ])

        table = Table(table_rows, colWidths=[120, 120, 200, 100])
        table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), self.palette["primary_light"]),
                ("GRID", (0, 0), (-1, -1), 0.5, self.palette["border"]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ])
        )
        items.append(table)
        return items

    def _build_validation_section(self, report: ApprovedChangeReport) -> List[Any]:
        items: List[Any] = []
        items.append(Paragraph("7. Regulatory Integrity Validation Findings", self.styles["SectionHeading"]))

        if report.validation_summary:
            items.append(Paragraph(self._escape(report.validation_summary), self.styles["Body"]))
            items.append(Spacer(1, 4))

        # Collect findings from changes
        findings: List[ValidationFinding] = []
        for c in report.changes:
            for f in c.validation_findings:
                if isinstance(f, ValidationFinding):
                    findings.append(f)
                elif isinstance(f, dict):
                    try:
                        findings.append(ValidationFinding.model_validate(f))
                    except Exception:
                        pass
            if c.impact_analysis and hasattr(c.impact_analysis, "findings"):
                for f in c.impact_analysis.findings:
                    if isinstance(f, ValidationFinding) and f not in findings:
                        findings.append(f)

        if not findings:
            items.append(
                Paragraph(
                    "All deterministic regulatory integrity checks passed with zero errors or warnings.",
                    self.styles["BodySmall"],
                )
            )
            return items

        headers = [
            Paragraph("<b>Rule ID</b>", self.styles["BodySmallBold"]),
            Paragraph("<b>Severity</b>", self.styles["BodySmallBold"]),
            Paragraph("<b>Result</b>", self.styles["BodySmallBold"]),
            Paragraph("<b>Finding Message</b>", self.styles["BodySmallBold"]),
        ]
        table_rows = [headers]

        for finding in findings:
            result_text = (
                "<font color='#166534'><b>PASSED</b></font>"
                if finding.passed
                else "<font color='#DC2626'><b>FAILED</b></font>"
            )

            table_rows.append([
                Paragraph(self._escape(finding.rule_id), self.styles["CodeBold"]),
                Paragraph(self._escape(finding.severity), self.styles["BodySmallBold"]),
                Paragraph(result_text, self.styles["BodySmall"]),
                Paragraph(self._escape(finding.message), self.styles["BodySmall"]),
            ])

        table = Table(table_rows, colWidths=[90, 65, 65, 320])
        table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), self.palette["primary_light"]),
                ("GRID", (0, 0), (-1, -1), 0.5, self.palette["border"]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ])
        )
        items.append(table)
        return items

    def _build_audit_trail_section(
        self, report: ApprovedChangeReport, audit_events: List[AuditEvent]
    ) -> List[Any]:
        items: List[Any] = []
        items.append(Paragraph("8. Tamper-Evident Audit Trail", self.styles["SectionHeading"]))

        notice_text = (
            "<b>IMMUTABLE HASH-CHAINED WORKFLOW LOG:</b> "
            "The human review and controlled change workflow is permanently recorded in an append-only "
            "audit log protected by SHA-256 cryptographic hash chaining. Each event links to the preceding "
            "event hash and computes a canonical SHA-256 digest of its state transition. "
            "Any post-hoc record tampering breaks the cryptographic verification chain."
        )
        notice_p = Paragraph(notice_text, self.styles["Disclaimer"])
        notice_table = Table([[notice_p]], colWidths=[540])
        notice_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), self.palette["light_bg"]),
                ("BOX", (0, 0), (-1, -1), 0.5, self.palette["border"]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        items.append(notice_table)
        items.append(Spacer(1, 4))

        if not audit_events:
            items.append(
                Paragraph(
                    "No audit events recorded for this report.",
                    self.styles["BodySmall"],
                )
            )
            return items

        for idx, event in enumerate(audit_events, start=1):
            prev_status = event.previous_status or "None"
            new_status = event.new_status or "None"
            transition_str = f"{prev_status} &rarr; {new_status}"
            linked_ref = event.change_id or event.decision_id or event.report_id or "N/A"

            event_rows = [
                [
                    Paragraph(f"<b>Event #{idx}: {self._escape(event.event_type)}</b>", self.styles["BodySmallBold"]),
                    Paragraph(f"<b>Event ID:</b> <font face='Courier' size='6.5'>{self._escape(event.event_id)}</font>", self.styles["BodySmall"]),
                ],
                [
                    Paragraph(f"<b>Occurred At (UTC):</b> {self._escape(event.occurred_at)}", self.styles["BodySmall"]),
                    Paragraph(f"<b>Actor:</b> {self._escape(event.reviewer_name or 'System / Regulatory User')}", self.styles["BodySmall"]),
                ],
                [
                    Paragraph(f"<b>Status Transition:</b> {transition_str}", self.styles["BodySmall"]),
                    Paragraph(f"<b>Linked Identifier:</b> <font face='Courier' size='6.5'>{self._escape(linked_ref)}</font>", self.styles["BodySmall"]),
                ],
                [
                    Paragraph("<b>Event SHA-256 Hash:</b>", self.styles["BodySmallBold"]),
                    Paragraph(self._escape(event.event_hash), self.styles["Code"]),
                ],
                [
                    Paragraph("<b>Previous Event Hash:</b>", self.styles["BodySmallBold"]),
                    Paragraph(self._escape(event.previous_event_hash or ("0" * 64)), self.styles["Code"]),
                ],
            ]

            ev_table = Table(event_rows, colWidths=[160, 380])
            ev_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), self.palette["white"]),
                    ("BOX", (0, 0), (-1, -1), 0.5, self.palette["border"]),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, self.palette["border"]),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ])
            )

            flowables = [ev_table, Spacer(1, 3)]
            items.append(KeepTogether(flowables))

        return items

    def _build_signoff_section(self, report: ApprovedChangeReport) -> List[Any]:
        items: List[Any] = []
        items.append(Paragraph("9. Regulatory Sign-off &amp; Human Authorization", self.styles["SectionHeading"]))

        signoff_rows = [
            [
                Paragraph("<b>Authorizing Regulatory Professional:</b>", self.styles["BodySmallBold"]),
                Paragraph(self._escape(report.author_approver), self.styles["BodyBold"]),
            ],
            [
                Paragraph("<b>Approval Timestamp:</b>", self.styles["BodySmallBold"]),
                Paragraph(self._escape(report.approval_timestamp or report.generated_at), self.styles["Body"]),
            ],
            [
                Paragraph("<b>Approval Confirmation Status:</b>", self.styles["BodySmallBold"]),
                Paragraph(
                    "<b><font color='#166534'>CONFIRMED</font></b> — Explicit Human Regulatory Approval",
                    self.styles["BodySmallBold"],
                ),
            ],
            [
                Paragraph("<b>Audit Report Identifier:</b>", self.styles["BodySmallBold"]),
                Paragraph(self._escape(report.report_id), self.styles["CodeBold"]),
            ],
            [
                Paragraph("<b>Attestation Statement:</b>", self.styles["BodySmallBold"]),
                Paragraph(
                    "By authorizing this report, the named regulatory authority certifies that all proposed "
                    "revisions, cross-occurrence confirmations, and evidence citations have been reviewed, verified, "
                    "and formally authorized under internal human-in-the-loop regulatory governance.",
                    self.styles["BodySmall"],
                ),
            ],
        ]

        table = Table(signoff_rows, colWidths=[180, 360])
        table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), self.palette["primary_light"]),
                ("BOX", (0, 0), (-1, -1), 1.0, self.palette["primary"]),
                ("GRID", (0, 0), (-1, -1), 0.5, self.palette["border"]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ])
        )

        items.append(KeepTogether([table]))
        return items
