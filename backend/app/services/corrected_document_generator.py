"""Deterministic corrected regulatory document generator service.

Produces a NEW in-memory byte stream from the retained original source document
bytes without ever mutating or modifying the original source document.

CRITICAL SAFETY & GOVERNANCE CONSTRAINTS:
- NEVER overwrites or mutates original source bytes in candidate store.
- Strictly enforces final human approval gate (approval_confirmation=True).
- Strictly rejects generation if any unresolved PENDING occurrences remain.
- Modifies ONLY confirmed occurrences (and confirmed primary changes).
- Leaves EXCLUDED occurrences 100% unaltered.
- Enforces unambiguous target resolution: zero matches or multiple ambiguous
  matches immediately fail generation.
- Operates transactionally in memory: returns no artifact if any target fails.
- Preserves document formatting and structure (run-level formatting for DOCX,
  UTF-8 encoding for TXT).
- Rejects input-only formats (PDF, legacy binary .doc) cleanly.
"""

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import io
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import unicodedata

import docx
import pypdf
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas
from pydantic import BaseModel, Field

from app.models.document_change import (
    ApprovedChangeReport,
    ProposedChange,
    RelatedOccurrence,
)
from app.services.candidate_store import (
    IngestedDocumentCandidateStore,
    get_candidate_store,
)

logger = logging.getLogger("corrected_document_generator")


class CorrectedDocumentError(Exception):
    """Base exception for corrected document generation errors."""
    pass


class UnsupportedFormatError(CorrectedDocumentError, ValueError):
    """Raised when document format is unsupported or input-only (e.g., PDF or legacy binary DOC)."""
    pass


class UnapprovedReportError(CorrectedDocumentError, ValueError):
    """Raised when report or change proposals have not received final human regulatory approval."""
    pass


class UnresolvedOccurrencesError(CorrectedDocumentError, ValueError):
    """Raised when unresolved PENDING occurrences exist."""
    pass


class TargetResolutionError(CorrectedDocumentError, ValueError):
    """Raised when target text has zero matches or multiple ambiguous matches."""
    pass


class CorrectedDocumentResult(BaseModel):
    """Artifact metadata and byte payload for a generated corrected regulatory document."""

    document_id: str = Field(..., description="Source regulatory document identifier")
    original_filename: str = Field(..., description="Original uploaded filename")
    output_filename: str = Field(..., description="Derived output filename")
    input_format: str = Field(..., description="Input format (e.g., 'docx', 'txt')")
    output_format: str = Field(..., description="Output format (e.g., 'docx', 'txt')")
    corrected_bytes: bytes = Field(..., description="New in-memory corrected document bytes")
    size_bytes: int = Field(..., description="Byte length of corrected document")
    sha256_hash: str = Field(..., description="SHA-256 hash of the corrected document bytes")

    @property
    def size(self) -> int:
        return self.size_bytes


@dataclass
class ModificationTarget:
    """Internal representation of a validated modification target."""
    source_text: str
    replacement_text: str
    section: Optional[str] = None
    location: Optional[str] = None
    occurrence_id: Optional[str] = None
    proposal_id: Optional[str] = None

# ==============================================================================
# PDF Deterministic Text Normalization & Target Disaggregation Utilities
# ==============================================================================

_CURLY_SINGLE_QUOTES = frozenset(['\u2018', '\u2019', '\u201a', '\u201b', '\u2032', '`', '´'])
_CURLY_DOUBLE_QUOTES = frozenset(['\u201c', '\u201d', '\u201e', '\u201f', '\u2033', '«', '»'])
_TYPOGRAPHIC_DASHES = frozenset(['\u2013', '\u2014', '\u2015', '\u2212', '\u2010', '\u2011'])
_INVISIBLE_CHARS = frozenset(['\u200b', '\u200c', '\u200d', '\ufeff', '\u200e', '\u200f', '\u00ad'])
_UNICODE_SPACES = frozenset(
    ['\u00a0', '\u202f', '\u205f', '\u3000']
    + [chr(c) for c in range(0x2000, 0x200b)]
)

_PAGE_BREADCRUMB_RE = re.compile(
    r"^\s*(?:---\s*)?\[\s*[Pp]age\s+(\d+)\s*\](?:\s*---)?[\s:\-]*"
)


def _disaggregate_pdf_target(target: ModificationTarget) -> Tuple[str, Optional[int]]:
    """Separate ingestion/review metadata from actual target content.

    Detects leading [Page N] breadcrumbs, extracts N as page_hint, and returns
    the cleaned target string for physical PDF matching. Also inspects location
    and section for reliable page hints if not present in the prefix.

    Does NOT mutate target.source_text or target.replacement_text.

    Returns:
        (clean_target, page_hint)
    """
    raw_src = target.source_text or ""
    page_hint: Optional[int] = None
    clean_target = raw_src.strip()

    m_bc = _PAGE_BREADCRUMB_RE.match(raw_src)
    if m_bc:
        try:
            page_hint = int(m_bc.group(1))
            clean_target = raw_src[m_bc.end():].strip()
        except (ValueError, TypeError):
            page_hint = None

    if page_hint is None and target.location:
        m_loc = re.search(r"\b[Pp]age\s+(\d+)\b", target.location)
        if m_loc:
            try:
                page_hint = int(m_loc.group(1))
            except (ValueError, TypeError):
                page_hint = None

    if page_hint is None and target.section:
        m_sec = re.search(r"(?:_p|\b[Pp]age\s*)(\d+)(?:_|\b)", target.section)
        if m_sec:
            try:
                page_hint = int(m_sec.group(1))
            except (ValueError, TypeError):
                page_hint = None

    return clean_target, page_hint


def _normalize_pdf_char(ch: str) -> str:
    """Normalize a single character using deterministic rules.

    - Unicode NFKD (expands ligatures like fi -> fi).
    - Maps curly quotes to straight quotes.
    - Maps typographic dashes/minus to '-'.
    - Maps Unicode/non-breaking spaces to ' '.
    - Strips invisible/zero-width formatting characters.
    - Preserves case, numbers, units, and clinical terminology.
    """
    nfkd = unicodedata.normalize("NFKD", ch)
    res = []
    for c in nfkd:
        if c in _INVISIBLE_CHARS:
            continue
        elif c in _CURLY_SINGLE_QUOTES:
            res.append("'")
        elif c in _CURLY_DOUBLE_QUOTES:
            res.append('"')
        elif c in _TYPOGRAPHIC_DASHES:
            res.append("-")
        elif c in _UNICODE_SPACES or c in ("\t", "\r", "\f", "\v"):
            res.append(" ")
        else:
            res.append(c)
    return "".join(res)


def _normalize_pdf_text(text: str) -> str:
    """Deterministically normalize string for PDF target matching."""
    return "".join(_normalize_pdf_char(c) for c in text)


def _build_visitor_stream_and_mapping(
    chunks: List[Dict[str, Any]]
) -> Tuple[str, List[Tuple[int, int]]]:
    """Construct a normalized character stream with explicit mapping to visitor chunks.

    Returns:
        (norm_stream, mapping)
        where mapping[k] is (chunk_idx, char_idx_in_chunk).
        Virtual whitespace separators have char_idx = -1.
    """
    norm_stream_chars: List[str] = []
    mapping: List[Tuple[int, int]] = []

    for c_idx, ch in enumerate(chunks):
        raw_text = ch["text"]
        if not raw_text:
            continue

        # Check boundary with previous chunk
        if c_idx > 0:
            prev = chunks[c_idx - 1]
            prev_raw = prev["text"]
            prev_has_ws = bool(prev_raw and prev_raw[-1].isspace())
            curr_has_ws = bool(raw_text and raw_text[0].isspace())

            if not prev_has_ws and not curr_has_ws:
                # If on different lines, insert virtual newline
                if abs(ch["y"] - prev["y"]) > 2.5:
                    norm_stream_chars.append("\n")
                    mapping.append((c_idx - 1, -1))
                else:
                    # Same line: check if there is a physical visual gap
                    prev_w = pdfmetrics.stringWidth(prev_raw, "Helvetica", prev["fs"])
                    gap = ch["x"] - (prev["x"] + prev_w)
                    if gap >= 1.5:
                        norm_stream_chars.append(" ")
                        mapping.append((c_idx - 1, -1))

        # Normalize each character in current chunk
        for char_idx, c in enumerate(raw_text):
            norm_c = _normalize_pdf_char(c)
            for nc in norm_c:
                norm_stream_chars.append(nc)
                mapping.append((c_idx, char_idx))

    return "".join(norm_stream_chars), mapping


def _build_pdf_target_pattern(clean_target: str) -> re.Pattern:
    """Build deterministic regex pattern from clean target text.

    Normalizes whitespace and supports line wraps and varying whitespace between words.
    Matching remains strictly exact (no fuzzy matching, case-sensitive).
    """
    norm_target = _normalize_pdf_text(clean_target).strip()
    words = norm_target.split()
    if not words:
        raise ValueError("Cannot search for empty target text.")

    pattern_str = r"\s+".join(re.escape(w) for w in words)
    return re.compile(pattern_str)


def _extract_page_chunks(page: Any) -> List[Dict[str, Any]]:
    """Extract text chunks with coordinates from a PDF page via visitor_text."""
    chunks: List[Dict[str, Any]] = []
    def _visitor(text: str, cm: Any, tm: Any, font_dict: Any, font_size: Any) -> None:
        if text:
            chunks.append({
                "text": text,
                "x": float(tm[4]),
                "y": float(tm[5]),
                "fs": float(font_size or 10.0),
            })

    try:
        page.extract_text(visitor_text=_visitor)
    except Exception as exc:
        logger.warning("visitor_text extraction failed on PDF page: %s", exc)
        return []
    return chunks


def _find_matches_on_page(
    page: Any,
    pattern: re.Pattern,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], str]:
    """Find occurrences of pattern on a page with explicit chunk mapping.

    Returns:
        (resolved_matches, chunks, full_stream)
    """
    chunks = _extract_page_chunks(page)
    if not chunks:
        return [], [], ""

    full_stream, mapping = _build_visitor_stream_and_mapping(chunks)
    raw_matches = list(pattern.finditer(full_stream))
    if not raw_matches:
        return [], chunks, full_stream

    resolved_matches: List[Dict[str, Any]] = []
    for m in raw_matches:
        m_start, m_end = m.span()
        chunk_char_spans: Dict[int, List[int]] = {}
        for k in range(m_start, m_end):
            c_idx, char_idx = mapping[k]
            if char_idx >= 0:
                if c_idx not in chunk_char_spans:
                    chunk_char_spans[c_idx] = [char_idx, char_idx]
                else:
                    chunk_char_spans[c_idx][0] = min(chunk_char_spans[c_idx][0], char_idx)
                    chunk_char_spans[c_idx][1] = max(chunk_char_spans[c_idx][1], char_idx)

        if not chunk_char_spans:
            continue

        part_items: List[Dict[str, Any]] = []
        for c_idx in sorted(chunk_char_spans.keys()):
            ch = chunks[c_idx]
            raw_text = ch["text"]
            min_c, max_c = chunk_char_spans[c_idx]
            prefix_str = raw_text[:min_c]
            matched_str = raw_text[min_c:max_c + 1].rstrip("\r\n")

            prefix_w = pdfmetrics.stringWidth(prefix_str, "Helvetica", ch["fs"]) if prefix_str else 0.0
            matched_w = pdfmetrics.stringWidth(matched_str, "Helvetica", ch["fs"]) if matched_str else 0.0

            part_min_x = ch["x"] + prefix_w
            part_max_x = part_min_x + matched_w
            part_items.append({
                "chunk_idx": c_idx,
                "ch": ch,
                "min_c": min_c,
                "max_c": max_c,
                "matched_str": matched_str,
                "part_min_x": part_min_x,
                "part_max_x": part_max_x,
                "matched_w": matched_w,
                "fs": ch["fs"],
                "y": ch["y"],
            })

        line_clusters: List[Dict[str, Any]] = []
        for item in sorted(part_items, key=lambda it: it["y"], reverse=True):
            matched_cluster = None
            for cl in line_clusters:
                if abs(cl["baseline_y"] - item["y"]) <= 3.0:
                    matched_cluster = cl
                    break
            if matched_cluster is not None:
                matched_cluster["items"].append(item)
            else:
                line_clusters.append({
                    "baseline_y": item["y"],
                    "items": [item],
                })

        sorted_lines: List[Dict[str, Any]] = []
        for cl in line_clusters:
            l_y = cl["baseline_y"]
            l_items = sorted(cl["items"], key=lambda it: it["part_min_x"])
            active_items = [it for it in l_items if it["matched_w"] > 0 or it["matched_str"].strip()]
            if not active_items:
                active_items = l_items
            l_min_x = min(it["part_min_x"] for it in active_items)
            l_max_x = max(it["part_max_x"] for it in active_items)
            l_fs = max(it["fs"] for it in active_items)
            sorted_lines.append({
                "line_y": l_y,
                "min_x": l_min_x,
                "max_x": l_max_x,
                "line_w": max(l_max_x - l_min_x, 10.0),
                "line_fs": l_fs,
                "items": l_items,
            })

        sorted_lines.sort(key=lambda sl: sl["line_y"], reverse=True)
        min_x = min(sl["min_x"] for sl in sorted_lines)
        max_x = max(sl["max_x"] for sl in sorted_lines)
        min_y = sorted_lines[-1]["line_y"]
        max_y = sorted_lines[0]["line_y"]
        target_fs = max(sl["line_fs"] for sl in sorted_lines)

        resolved_matches.append({
            "span": (m_start, m_end),
            "chunk_char_spans": chunk_char_spans,
            "sorted_lines": sorted_lines,
            "min_x": min_x,
            "max_x": max_x,
            "min_y": min_y,
            "max_y": max_y,
            "target_fs": target_fs,
            "chunks": chunks,
        })

    return resolved_matches, chunks, full_stream


def _compute_pdf_multiline_safe_layout(
    target: ModificationTarget,
    sorted_lines: List[Dict[str, Any]],
    chunks: List[Dict[str, Any]],
    target_page: Any,
    target_fs: float,
    min_x: float,
    max_x: float,
    min_fs: float = 8.0,
) -> Tuple[float, List[Dict[str, Any]]]:
    """Calculate a deterministic, page-preserving layout for multi-line replacement text.

    Guarantees:
    - Preserves the original target location and existing line baselines.
    - Inspects downstream visitor chunks below the target to determine nearest real content.
    - Calculates verified vertical clearance and respects safe page bottom margin (36pt).
    - Never writes into occupied downstream content.
    - For each line, uses verified safe horizontal span up to page margin or obstacle.
    - Wraps onto additional lines ONLY when those lines are verified safe.
    - Scales font size from target_fs down to min_fs (8.0pt floor).
    - If replacement cannot fit safely within verified region, raises TargetResolutionError.
    """
    page_w = float(target_page.mediabox.width)
    page_h = float(target_page.mediabox.height)
    margin_bottom = 36.0
    margin_right = 36.0
    margin_left = 36.0
    page_right_limit = max(page_w - margin_right, min_x + 50.0)
    target_left_x = min_x

    # Determine baseline spacing from existing matched lines
    num_orig = len(sorted_lines)
    deltas = [sorted_lines[i]["line_y"] - sorted_lines[i + 1]["line_y"] for i in range(num_orig - 1)]
    pos_deltas = [d for d in deltas if d > 0]
    line_spacing = (sum(pos_deltas) / len(pos_deltas)) if pos_deltas else (target_fs * 1.2)
    if line_spacing < target_fs * 1.0:
        line_spacing = target_fs * 1.2

    # 1. Candidate slots for existing lines (preserving baselines and checking horizontal obstacles)
    candidate_slots: List[Dict[str, Any]] = []
    for sl in sorted_lines:
        l_y = sl["line_y"]
        l_min_x = sl["min_x"]
        l_max_x = sl["max_x"]
        l_w = sl["line_w"]

        same_line_obs = [
            c for c in chunks
            if abs(c["y"] - l_y) < 3.0 and c["x"] > l_max_x + 1.0 and c.get("text", "").strip()
        ]
        if same_line_obs:
            obs_x = min(c["x"] for c in same_line_obs)
            avail_line_w = max(obs_x - l_min_x - 4.0, l_w)
        else:
            avail_line_w = max(page_right_limit - l_min_x, l_w)

        candidate_slots.append({
            "line_y": l_y,
            "min_x": l_min_x,
            "line_w": avail_line_w,
            "is_extra": False,
        })

    # 2. Inspect downstream chunks below target to compute verified vertical clearance
    last_line_y = sorted_lines[-1]["line_y"]
    downstream_obstacles = []
    for c in chunks:
        if c["y"] < last_line_y - 2.0 and c.get("text", "").strip():
            c_left = c["x"]
            c_fs = float(c.get("fs", target_fs))
            c_w = pdfmetrics.stringWidth(c["text"], "Helvetica", c_fs)
            c_right = c_left + c_w
            # Relevant if it intersects the horizontal column of the target block
            if c_right >= target_left_x - 5.0 and c_left <= page_right_limit + 5.0:
                downstream_obstacles.append(c)

    if downstream_obstacles:
        nearest_obs_top = max(c["y"] + float(c.get("fs", target_fs)) + 2.0 for c in downstream_obstacles)
    else:
        nearest_obs_top = margin_bottom
    safe_bottom_limit = max(nearest_obs_top, margin_bottom)

    # 3. Add candidate slots for extra lines ONLY where verified safe
    for k in range(1, 100):
        cand_y = last_line_y - (k * line_spacing)
        # Check text bottom clearance against safe_bottom_limit
        if cand_y - (target_fs * 0.3) < safe_bottom_limit:
            break

        cand_min_x = target_left_x
        obs_on_cand = [
            c for c in chunks
            if abs(c["y"] - cand_y) < 3.0 and c["x"] > cand_min_x + 1.0 and c.get("text", "").strip()
        ]
        if obs_on_cand:
            cand_max_x = min(c["x"] for c in obs_on_cand) - 4.0
        else:
            cand_max_x = page_right_limit

        cand_w = cand_max_x - cand_min_x
        if cand_w < 20.0:
            break

        candidate_slots.append({
            "line_y": cand_y,
            "min_x": cand_min_x,
            "line_w": cand_w,
            "is_extra": True,
        })

    # 4. Word-wrap simulation across candidate slots
    words = target.replacement_text.split()
    if not words:
        return target_fs, []

    def _try_wrap(slots: List[Dict[str, Any]], fs: float) -> Optional[List[Dict[str, Any]]]:
        lines_out = []
        w_idx = 0
        for slot in slots:
            if w_idx >= len(words):
                break
            cur_words = []
            while w_idx < len(words):
                next_w = words[w_idx]
                cand_str = " ".join(cur_words + [next_w])
                if pdfmetrics.stringWidth(cand_str, "Helvetica", fs) <= slot["line_w"] + 5.0 or not cur_words:
                    cur_words.append(next_w)
                    w_idx += 1
                else:
                    break
            if cur_words:
                txt = " ".join(cur_words)
                lines_out.append({
                    "line_y": slot["line_y"],
                    "min_x": slot["min_x"],
                    "line_w": slot["line_w"],
                    "text_w": pdfmetrics.stringWidth(txt, "Helvetica", fs),
                    "text": txt,
                    "fs": fs,
                    "is_extra": slot.get("is_extra", False),
                })
        if w_idx >= len(words):
            return lines_out
        return None

    # Test target_fs first
    res = _try_wrap(candidate_slots, target_fs)
    if res is not None:
        return target_fs, res

    # Test descending font sizes down to min_fs
    curr_fs = target_fs - 0.25
    while curr_fs >= min_fs - 0.01:
        res = _try_wrap(candidate_slots, round(curr_fs, 2))
        if res is not None:
            return round(curr_fs, 2), res
        curr_fs -= 0.25

    raise TargetResolutionError(
        f"Replacement text for occurrence '{target.occurrence_id}' cannot safely fit within "
        f"the resolved target region without automatic page reflow or overlapping adjacent content."
    )


class CorrectedDocumentGenerator:
    """Deterministic in-memory generator for corrected regulatory documents."""

    def __init__(
        self,
        candidate_store: Optional[IngestedDocumentCandidateStore] = None,
    ) -> None:
        self.candidate_store = candidate_store or get_candidate_store()

    def generate_corrected_document(
        self,
        report: Optional[ApprovedChangeReport] = None,
        document_id: Optional[str] = None,
        proposals: Optional[List[ProposedChange]] = None,
        output_filename: Optional[str] = None,
        approval_confirmation: Optional[bool] = None,
    ) -> CorrectedDocumentResult:
        """Generate a new corrected document from retained source bytes.

        Args:
            report: Authorized ApprovedChangeReport.
            document_id: Optional source document ID override.
            proposals: Optional list of approved ProposedChange objects.
            output_filename: Optional explicit output filename.
            approval_confirmation: Optional approval confirmation override if passing proposals directly.

        Returns:
            CorrectedDocumentResult with newly generated bytes and SHA-256 hash.

        Raises:
            UnapprovedReportError: If report or proposals lack final human approval confirmation.
            UnresolvedOccurrencesError: If any unresolved PENDING occurrences exist.
            UnsupportedFormatError: If source document is PDF, legacy DOC, or unsupported.
            TargetResolutionError: If any target has zero matches or multiple ambiguous matches.
            ValueError: If source document is missing or invalid.
        """
        # 1. Resolve authoritative document_id and proposals
        eff_doc_id = document_id or (report.document_id if report else None)
        if not eff_doc_id:
            raise ValueError("Document correction rejected: document_id is missing and could not be determined.")

        eff_proposals: List[ProposedChange] = []
        if report is not None:
            # Enforce report-level approval confirmation gate
            if not report.approval_confirmation:
                raise UnapprovedReportError(
                    "Document correction rejected: Change report has not received explicit human approval confirmation "
                    "(approval_confirmation=true)."
                )
            if not report.author_approver or not report.author_approver.strip():
                raise UnapprovedReportError(
                    "Document correction rejected: Valid human regulatory approver identity is required."
                )
            eff_proposals = list(report.changes or [])
        elif proposals is not None:
            # Enforce direct proposal approval confirmation gate
            is_confirmed = approval_confirmation is True or all(
                getattr(p, "status", None) == "APPROVED" for p in proposals
            )
            if not is_confirmed:
                raise UnapprovedReportError(
                    "Document correction rejected: Change proposals have not received final human approval."
                )
            eff_proposals = list(proposals)
        else:
            raise ValueError("Document correction rejected: Either 'report' or 'proposals' must be provided.")

        if not eff_proposals:
            raise ValueError("Document correction rejected: No change proposals available for correction generation.")

        # 2. Strict occurrence safety checks
        for prop in eff_proposals:
            for occ in prop.related_occurrences:
                if occ.status == "PENDING":
                    raise UnresolvedOccurrencesError(
                        f"Unresolved PENDING occurrence '{occ.occurrence_id}' detected in proposal '{prop.change_id}'. "
                        f"All occurrences must be explicitly reviewed (CONFIRMED or EXCLUDED) before corrected document generation."
                    )

        # 3. Retrieve retained original source document
        source_doc = self.candidate_store.get_source_document(eff_doc_id)
        if source_doc is None:
            raise ValueError(f"Source document '{eff_doc_id}' not found in candidate store.")

        orig_bytes = bytes(source_doc.source_bytes)
        if not orig_bytes:
            raise ValueError(f"Source document '{eff_doc_id}' contains empty source bytes.")

        eff_format = (source_doc.file_format or "").strip().lower().lstrip(".")
        if not eff_format and "." in source_doc.filename:
            eff_format = Path(source_doc.filename).suffix.strip().lower().lstrip(".")

        # 4. Check supported formats & reject input-only formats
        if eff_format == "doc":
            raise UnsupportedFormatError(
                "Legacy DOC (.doc) format is input-only; direct binary .doc modification is not supported "
                "without external dependencies. Please use DOCX."
            )
        if eff_format not in ("docx", "txt", "text", "md", "pdf"):
            raise UnsupportedFormatError(
                f"Unsupported format '{eff_format}' for corrected document generation. Supported formats: DOCX, TXT, PDF."
            )

        # 5. Collect modification targets
        targets: List[ModificationTarget] = []
        for prop in eff_proposals:
            has_primary = False
            primary_src = (prop.original_text or "").strip()
            primary_rep = (prop.proposed_text or "").strip()

            # 5a. Primary target from ProposedChange (considered independently)
            if primary_src and primary_rep and primary_src != primary_rep:
                targets.append(
                    ModificationTarget(
                        source_text=primary_src,
                        replacement_text=primary_rep,
                        section=prop.section,
                        occurrence_id=prop.change_id,
                        proposal_id=prop.change_id,
                    )
                )
                has_primary = True

            # 5b. Additionally process CONFIRMED related occurrences
            for occ in (prop.related_occurrences or []):
                if occ.status == "CONFIRMED":
                    occ_src = (occ.matched_text or occ.current_text or "").strip()
                    if not occ_src:
                        raise ValueError(f"Occurrence '{occ.occurrence_id}' has empty source text.")
                    occ_rep = primary_rep if primary_rep else (prop.proposed_text or "").strip()
                    # Deduplicate if this confirmed occurrence targets the exact same text in the same section as primary
                    if has_primary and occ_src == primary_src and (occ.section or "").strip().lower() == (prop.section or "").strip().lower():
                        continue
                    targets.append(
                        ModificationTarget(
                            source_text=occ_src,
                            replacement_text=occ_rep,
                            section=occ.section,
                            location=occ.location,
                            occurrence_id=occ.occurrence_id,
                            proposal_id=prop.change_id,
                        )
                    )
                # EXCLUDED occurrences are intentionally skipped (remain untouched)

        if not targets:
            raise TargetResolutionError(
                "Document correction rejected: No textual modifications to apply. "
                "The approved change proposed text identical to the original content, "
                "or all related occurrences were excluded."
            )

        # 6. Generate NEW corrected byte stream transactionally
        if eff_format in ("txt", "text", "md"):
            corrected_bytes = self._generate_corrected_txt(orig_bytes, targets)
            out_fmt = "txt" if eff_format in ("txt", "text") else "md"
        elif eff_format == "docx":
            corrected_bytes = self._generate_corrected_docx(orig_bytes, targets)
            out_fmt = "docx"
        elif eff_format == "pdf":
            corrected_bytes = self._generate_corrected_pdf(orig_bytes, targets)
            out_fmt = "pdf"
        else:
            raise UnsupportedFormatError(f"Unsupported format '{eff_format}'.")

        # 7. Resolve output filename
        if output_filename and output_filename.strip():
            final_out_fn = output_filename.strip()
        else:
            stem = Path(source_doc.filename).stem
            ext = Path(source_doc.filename).suffix or f".{out_fmt}"
            final_out_fn = f"Corrected_{stem}{ext}"

        # 8. Compute artifact metadata and SHA-256 hash
        sha256 = hashlib.sha256(corrected_bytes).hexdigest()

        return CorrectedDocumentResult(
            document_id=eff_doc_id,
            original_filename=source_doc.filename,
            output_filename=final_out_fn,
            input_format=eff_format,
            output_format=out_fmt,
            corrected_bytes=corrected_bytes,
            size_bytes=len(corrected_bytes),
            sha256_hash=sha256,
        )

    def _generate_corrected_txt(
        self,
        source_bytes: bytes,
        targets: List[ModificationTarget],
    ) -> bytes:
        """Deterministically apply target replacements to plain text content."""
        content = source_bytes.decode("utf-8")

        if not targets:
            raise TargetResolutionError("Document correction rejected: No modification targets provided.")

        # Phase 1: Validate and resolve all targets to exact unique character spans (start, end)
        resolved_spans: List[Tuple[int, int, str, ModificationTarget]] = []
        is_crlf = "\r\n" in content

        for target in targets:
            src = target.source_text.strip()
            span: Optional[Tuple[int, int]] = None

            # Build regex pattern supporting both LF and CRLF in source text
            src_parts = re.split(r"\r\n|\r|\n", src)
            src_pattern = r"\r?\n".join(re.escape(p) for p in src_parts)

            # Try section-bounded search if section context is present
            if target.section:
                sec_bounds = self._find_txt_section_bounds(content, target.section)
                if sec_bounds:
                    sec_start, sec_end = sec_bounds
                    sec_text = content[sec_start:sec_end]
                    sec_matches = list(re.finditer(src_pattern, sec_text))
                    if len(sec_matches) == 1:
                        m = sec_matches[0]
                        span = (sec_start + m.start(), sec_start + m.end())
                    elif len(sec_matches) > 1:
                        raise TargetResolutionError(
                            f"Multiple ambiguous matches ({len(sec_matches)}) found for occurrence '{target.occurrence_id}' "
                            f"in section '{target.section}'. Target text: '{src}'"
                        )

            # Fall back to document-wide matching if section search yielded no span
            if span is None:
                doc_matches = list(re.finditer(src_pattern, content))
                if len(doc_matches) == 0:
                    raise TargetResolutionError(
                        f"Zero matches found for occurrence '{target.occurrence_id}' in document. "
                        f"Expected target text: '{src}'"
                    )
                elif len(doc_matches) > 1:
                    raise TargetResolutionError(
                        f"Multiple ambiguous matches ({len(doc_matches)}) found for occurrence '{target.occurrence_id}' "
                        f"in document. Target text: '{src}'"
                    )
                m = doc_matches[0]
                span = (m.start(), m.end())

            # Normalize replacement line endings to match document convention
            rep_text = target.replacement_text
            if is_crlf:
                norm_rep = rep_text.replace("\r\n", "\n").replace("\n", "\r\n")
            else:
                norm_rep = rep_text.replace("\r\n", "\n")

            resolved_spans.append((span[0], span[1], norm_rep, target))

        # Check for overlapping spans
        sorted_spans = sorted(resolved_spans, key=lambda s: s[0])
        for i in range(len(sorted_spans) - 1):
            if sorted_spans[i][1] > sorted_spans[i + 1][0]:
                raise TargetResolutionError(
                    f"Conflicting overlapping occurrence targets detected: "
                    f"'{sorted_spans[i][3].occurrence_id}' and '{sorted_spans[i+1][3].occurrence_id}'."
                )

        # Phase 2: Apply replacements in reverse order of start index to avoid offset shifting
        sorted_reverse = sorted(resolved_spans, key=lambda s: s[0], reverse=True)
        corrected_content = content
        for start, end, rep, _ in sorted_reverse:
            corrected_content = corrected_content[:start] + rep + corrected_content[end:]

        return corrected_content.encode("utf-8")

    def _find_txt_section_bounds(self, content: str, section_name: str) -> Optional[Tuple[int, int]]:
        """Find the start and end character offsets of a named section in plain text."""
        clean_sec = section_name.strip()
        pattern = rf"(?im)^\s*(?:[0-9]+\s+)?(?:#+\s*)?{re.escape(clean_sec)}\b.*$"
        match = re.search(pattern, content)
        if not match:
            return None

        sec_start = match.end()
        # Find subsequent section header
        next_heading_pattern = r"(?m)^\s*(?:[0-9]+\s+)?(?:#+\s*|[A-Z][A-Z0-9\s,/-]{3,}\b.*$)"
        rest = content[sec_start:]
        next_match = re.search(next_heading_pattern, rest)
        sec_end = sec_start + next_match.start() if next_match else len(content)
        return (sec_start, sec_end)

    def _generate_corrected_docx(
        self,
        source_bytes: bytes,
        targets: List[ModificationTarget],
    ) -> bytes:
        """Deterministically apply target replacements to DOCX content preserving runs/formatting."""
        import docx

        doc = docx.Document(io.BytesIO(source_bytes))

        if not targets:
            raise TargetResolutionError("Document correction rejected: No modification targets provided.")

        # Collect all paragraphs from body and table cells with section context
        all_paras = self._collect_docx_paragraphs(doc)

        # Phase 1: Validate and resolve all targets to specific paragraph elements
        resolutions: List[Tuple[Any, ModificationTarget]] = []

        for target in targets:
            src = target.source_text.strip()
            matching_paras = []
            for p, sec_name in all_paras:
                if src in p.text:
                    cnt = p.text.count(src)
                    if cnt > 1:
                        raise TargetResolutionError(
                            f"Multiple ambiguous matches ({cnt}) found for occurrence '{target.occurrence_id}' "
                            f"within a single paragraph: '{p.text[:60]}...'"
                        )
                    matching_paras.append((p, sec_name))

            if len(matching_paras) == 0:
                raise TargetResolutionError(
                    f"Zero matches found for occurrence '{target.occurrence_id}' in DOCX document. "
                    f"Expected target text: '{src}'"
                )
            elif len(matching_paras) == 1:
                resolutions.append((matching_paras[0][0], target))
            else:
                # Multiple paragraphs contain src. Attempt disambiguation using target.section
                disambiguated = []
                if target.section:
                    t_sec_lower = target.section.strip().lower()
                    for p, sec_name in matching_paras:
                        if sec_name and (t_sec_lower in sec_name.lower() or sec_name.lower() in t_sec_lower):
                            disambiguated.append((p, sec_name))

                if len(disambiguated) == 1:
                    resolutions.append((disambiguated[0][0], target))
                else:
                    raise TargetResolutionError(
                        f"Multiple ambiguous matches ({len(matching_paras)}) found for occurrence '{target.occurrence_id}' "
                        f"in DOCX document. Target text: '{src}'"
                    )

        # Phase 2: Apply targeted replacements preserving run formatting
        for p, target in resolutions:
            self._replace_in_docx_paragraph(p, target.source_text.strip(), target.replacement_text)

        out_buf = io.BytesIO()
        doc.save(out_buf)
        return out_buf.getvalue()

    def _collect_docx_paragraphs(self, doc: Any) -> List[Tuple[Any, Optional[str]]]:
        """Collect all paragraphs from body and table cells with tracked section context."""
        results: List[Tuple[Any, Optional[str]]] = []
        current_section: Optional[str] = None

        # 1. Document body paragraphs
        for p in doc.paragraphs:
            txt = p.text.strip()
            if p.style and hasattr(p.style, "name") and ("heading" in p.style.name.lower() or "title" in p.style.name.lower()):
                current_section = txt
            elif txt.isupper() and len(txt) > 3 and "\n" not in txt:
                current_section = txt
            results.append((p, current_section))

        # 2. Table cell paragraphs
        for tbl in doc.tables:
            for row in tbl.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        results.append((p, current_section))

        return results

    def _replace_in_docx_paragraph(self, paragraph: Any, source_text: str, replacement_text: str) -> None:
        """Targeted replacement within a DOCX paragraph preserving run-level formatting."""
        # 1. Check if source_text is contained entirely within a single run
        for run in paragraph.runs:
            if source_text in run.text:
                run.text = run.text.replace(source_text, replacement_text, 1)
                return

        # 2. Multi-run replacement
        full_text = paragraph.text
        if source_text not in full_text:
            return

        start_idx = full_text.find(source_text)
        end_idx = start_idx + len(source_text)

        run_spans = []
        curr = 0
        for run in paragraph.runs:
            r_len = len(run.text)
            run_spans.append((curr, curr + r_len, run))
            curr += r_len

        overlapping = [span for span in run_spans if span[0] < end_idx and span[1] > start_idx]
        if not overlapping:
            paragraph.text = full_text.replace(source_text, replacement_text, 1)
            return

        first_start, _, first_run = overlapping[0]
        last_start, _, last_run = overlapping[-1]

        if len(overlapping) == 1:
            prefix = first_run.text[:start_idx - first_start]
            suffix = first_run.text[end_idx - first_start:]
            first_run.text = prefix + replacement_text + suffix
        else:
            prefix = first_run.text[:start_idx - first_start]
            first_run.text = prefix + replacement_text
            for _, _, mid_run in overlapping[1:-1]:
                mid_run.text = ""
            suffix = last_run.text[end_idx - last_start:]
            last_run.text = suffix

    def _generate_corrected_pdf(
        self,
        source_bytes: bytes,
        targets: List[ModificationTarget],
    ) -> bytes:
        """Deterministically apply target replacements to PDF content.

        Preserves unaffected pages verbatim without re-encoding.
        For pages containing confirmed target replacements:
        - Separates review metadata (e.g., [Page N] breadcrumb) from target text.
        - Normalizes Unicode characters and whitespace deterministically.
        - Resolves target occurrence with explicit chunk and coordinate mapping.
        - Verifies that replacement safely fits within the resolved target region.
        - Masks only the target text region using an opaque rectangle on a ReportLab overlay.
        - Draws the approved replacement text.
        - Merges the overlay onto a copy of the target page.
        - Emits a newly generated, separate PDF byte stream.
        Original source bytes are completely unmodified.
        """
        if not targets:
            raise TargetResolutionError("Document correction rejected: No modification targets provided.")

        try:
            reader = pypdf.PdfReader(io.BytesIO(source_bytes))
        except Exception as exc:
            raise ValueError(f"Failed to read source PDF document: {exc}") from exc

        num_pages = len(reader.pages)
        if num_pages == 0:
            raise ValueError("Source PDF document contains 0 pages.")

        # Phase 1: Resolve all targets to specific pages and exact coordinates
        resolved_by_page: Dict[int, List[Dict[str, Any]]] = {}

        for target in targets:
            clean_target, page_hint = _disaggregate_pdf_target(target)
            if not clean_target:
                raise ValueError(f"Modification target '{target.occurrence_id}' has empty source text.")

            pattern = _build_pdf_target_pattern(clean_target)

            resolved_page_idx: int
            resolved_match: Dict[str, Any]
            chunks: List[Dict[str, Any]]

            # Deterministic page resolution
            if page_hint is not None:
                if page_hint < 1 or page_hint > num_pages:
                    raise TargetResolutionError(
                        f"Page hint [Page {page_hint}] for occurrence '{target.occurrence_id}' is outside "
                        f"valid document page range (1 to {num_pages})."
                    )
                p_idx = page_hint - 1
                page = reader.pages[p_idx]
                matches_on_page, chunks_on_page, _ = _find_matches_on_page(page, pattern)

                if len(matches_on_page) == 0:
                    raise TargetResolutionError(
                        f"Zero matches found for occurrence '{target.occurrence_id}' on bound page {page_hint} "
                        f"of PDF document. Expected target text: '{clean_target}'"
                    )
                elif len(matches_on_page) > 1:
                    raise TargetResolutionError(
                        f"Multiple ambiguous matches ({len(matches_on_page)}) found for occurrence '{target.occurrence_id}' "
                        f"within page {page_hint} of PDF document with no unique location metadata to disambiguate. "
                        f"Target text: '{clean_target}'"
                    )
                else:
                    resolved_page_idx = p_idx
                    resolved_match = matches_on_page[0]
                    chunks = chunks_on_page
            else:
                # Search all pages
                all_matches: List[Tuple[int, Dict[str, Any], List[Dict[str, Any]]]] = []
                for p_idx, page in enumerate(reader.pages):
                    m_list, ch_list, _ = _find_matches_on_page(page, pattern)
                    for m in m_list:
                        all_matches.append((p_idx, m, ch_list))

                if len(all_matches) == 0:
                    raise TargetResolutionError(
                        f"Zero matches found for occurrence '{target.occurrence_id}' in PDF document. "
                        f"Expected target text: '{clean_target}'"
                    )
                elif len(all_matches) == 1:
                    resolved_page_idx, resolved_match, chunks = all_matches[0]
                else:
                    # Multiple matches across pages. Attempt section/location disambiguation.
                    disambiguated = []
                    if target.section:
                        t_sec_lower = target.section.strip().lower()
                        for p_idx, m_info, ch_list in all_matches:
                            p_text = (reader.pages[p_idx].extract_text() or "").lower()
                            if t_sec_lower in p_text or f"_p{p_idx + 1}" in t_sec_lower:
                                disambiguated.append((p_idx, m_info, ch_list))

                    if len(disambiguated) == 1:
                        resolved_page_idx, resolved_match, chunks = disambiguated[0]
                    else:
                        raise TargetResolutionError(
                            f"Multiple ambiguous matches ({len(all_matches)}) found for occurrence '{target.occurrence_id}' "
                            f"across PDF document. Target text: '{clean_target}'"
                        )

            # Safe-fit validation
            sorted_lines = resolved_match["sorted_lines"]
            target_page = reader.pages[resolved_page_idx]
            rep_text = target.replacement_text
            target_fs = resolved_match["target_fs"]
            min_x = resolved_match["min_x"]
            max_x = resolved_match["max_x"]
            min_y = resolved_match["min_y"]
            max_y = resolved_match["max_y"]
            target_w = max(max_x - min_x, 10.0)

            effective_fs = target_fs
            rep_w = pdfmetrics.stringWidth(rep_text, "Helvetica", target_fs)

            if len(sorted_lines) == 1:
                first_line_y = sorted_lines[0]["line_y"]
                same_line_chunks_to_right = [
                    c for c in chunks
                    if abs(c["y"] - first_line_y) < 3.0 and c["x"] > max_x + 1.0 and c["text"].strip()
                ]
                if same_line_chunks_to_right:
                    obstacle_x = min(c["x"] for c in same_line_chunks_to_right)
                    avail_line_w = max(obstacle_x - min_x - 4.0, target_w)
                else:
                    page_w = float(target_page.mediabox.width)
                    avail_line_w = max(page_w - min_x - 36.0, target_w)

                if rep_w <= target_w + 5.0:
                    effective_fs = target_fs
                else:
                    scale = target_w / rep_w
                    scaled_fs = max(8.0, target_fs * scale)
                    if pdfmetrics.stringWidth(rep_text, "Helvetica", scaled_fs) <= target_w + 5.0:
                        effective_fs = scaled_fs
                    elif rep_w <= avail_line_w:
                        effective_fs = target_fs
                    else:
                        avail_scale = avail_line_w / rep_w
                        scaled_fs_avail = max(8.0, target_fs * avail_scale)
                        if pdfmetrics.stringWidth(rep_text, "Helvetica", scaled_fs_avail) <= avail_line_w:
                            effective_fs = scaled_fs_avail
                        else:
                            raise TargetResolutionError(
                                f"Replacement text for occurrence '{target.occurrence_id}' cannot safely fit within "
                                f"the resolved target region ({avail_line_w:.1f}pt available, requires {rep_w:.1f}pt) "
                                f"without automatic page reflow or overlapping adjacent content."
                            )

                placed_lines = [{
                    "line_y": first_line_y,
                    "min_x": sorted_lines[0]["min_x"],
                    "line_w": avail_line_w,
                    "text_w": pdfmetrics.stringWidth(rep_text, "Helvetica", effective_fs),
                    "text": rep_text,
                    "fs": effective_fs,
                    "is_extra": False,
                }]
            else:
                effective_fs, placed_lines = _compute_pdf_multiline_safe_layout(
                    target=target,
                    sorted_lines=sorted_lines,
                    chunks=chunks,
                    target_page=target_page,
                    target_fs=target_fs,
                    min_x=min_x,
                    max_x=max_x,
                    min_fs=8.0,
                )

            if resolved_page_idx not in resolved_by_page:
                resolved_by_page[resolved_page_idx] = []

            resolved_by_page[resolved_page_idx].append({
                "target": target,
                "min_x": min_x,
                "max_x": max_x,
                "min_y": min_y,
                "max_y": max_y,
                "target_fs": effective_fs,
                "sorted_lines": sorted_lines,
                "placed_lines": placed_lines,
            })

        # Phase 2: Transactionally assemble the new PDF byte stream
        writer = pypdf.PdfWriter()

        for idx, page in enumerate(reader.pages):
            if idx not in resolved_by_page:
                writer.add_page(page)
            else:
                page_w = float(page.mediabox.width)
                page_h = float(page.mediabox.height)
                overlay_buf = io.BytesIO()
                oc = canvas.Canvas(overlay_buf, pagesize=(page_w, page_h))

                for item in resolved_by_page[idx]:
                    t_item = item["target"]
                    fs = item["target_fs"]
                    lines = item["sorted_lines"]
                    placed = item["placed_lines"]

                    # Mask each original line occupied by the target text
                    oc.setFillColor(colors.white)
                    for sl in lines:
                        pl_matching = [p for p in placed if abs(p["line_y"] - sl["line_y"]) < 2.0]
                        extra_w = max([p["text_w"] for p in pl_matching], default=0.0)
                        mask_w = max(sl["line_w"], extra_w)
                        oc.rect(
                            sl["min_x"] - 1.5,
                            sl["line_y"] - 2.5,
                            mask_w + 3.0,
                            max(sl.get("line_fs", fs), fs) + 5.0,
                            fill=1,
                            stroke=0,
                        )

                    # Mask any extra lines placed in safe blank space
                    for pl in placed:
                        if pl.get("is_extra"):
                            oc.rect(
                                pl["min_x"] - 1.5,
                                pl["line_y"] - 2.5,
                                pl["text_w"] + 3.0,
                                fs + 5.0,
                                fill=1,
                                stroke=0,
                            )

                    # Draw replacement text using the validated layout
                    oc.setFillColor(colors.black)
                    oc.setFont("Helvetica", fs)
                    for pl in placed:
                        oc.drawString(pl["min_x"], pl["line_y"], pl["text"])

                oc.save()

                new_page = writer.add_page(page)
                overlay_reader = pypdf.PdfReader(io.BytesIO(overlay_buf.getvalue()))
                new_page.merge_page(overlay_reader.pages[0])

        out_buf = io.BytesIO()
        writer.write(out_buf)
        return out_buf.getvalue()
