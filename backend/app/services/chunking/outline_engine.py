"""Regulatory outline and heading detection engine.

Detects and segments multi-jurisdictional regulatory document structures:
- Numbered sections (e.g. 1, 1.1, 4.2, 4.2.1)
- Numbered and lettered list items (e.g. 1., 2., (a), (b), (i), (ii))
- Unnumbered structural headings (US PLR, EU SmPC, Investigator's Brochure)
- Markdown outline headers (#, ##, ###)
- Maps recognized headings to CanonicalSectionConcept while preserving heading_raw
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional
from app.models.document import CanonicalSectionConcept


@dataclass
class HeadingInfo:
    """Structured representation of a recognized regulatory heading."""

    heading_raw: str
    section_number: Optional[str] = None
    title: str = ""
    level: int = 1
    heading_normalized: Optional[str] = None
    parent_section_number: Optional[str] = None
    is_canonical: bool = False
    order_index: int = 0


@dataclass
class ListItemInfo:
    """Structured representation of an inline list item (bullet or numbered)."""

    raw_line: str
    marker: str
    content: str
    item_type: str  # 'bullet', 'numbered_item', 'lettered_item', 'roman_item'
    order_index: int = 0


class RegulatoryOutlineEngine:
    """Deterministic engine for parsing multi-jurisdictional regulatory outlines."""

    # Decimal outline numbering: e.g. "4.2", "4.2.1", "1", "1.1"
    # Matches lines like: "4.2 Posology and method of administration", "Section 2. Dosage", "1. Name"
    NUMBERED_SECTION_PATTERN = re.compile(
        r'^\s*(?:Section\s+)?(\d+(?:\.\d+)*)[:\.\-]?\s+(.+)$',
        re.IGNORECASE,
    )

    # Markdown headers: e.g. "# Heading 1", "## Heading 2"
    MARKDOWN_HEADER_PATTERN = re.compile(
        r'^\s*(#{1,6})\s+(.+)$'
    )

    # Numbered / lettered list items: e.g. "1.", "2.", "(a)", "(b)", "(i)", "(ii)", "A."
    NUMBERED_ITEM_PATTERN = re.compile(
        r'^\s*(?:\(([0-9]+|[a-zA-Z]|[ivxcdmIVXCDM]+)\)|([0-9]+|[a-zA-Z]|[ivxcdmIVXCDM]+)[\.\)])\s+(.+)$'
    )

    # Bullet markers: "-", "*", "•", "–", "—"
    BULLET_PATTERN = re.compile(
        r'^\s*([*\-•–—])\s+(.+)$'
    )

    # Canonical mapping table: regex pattern -> CanonicalSectionConcept
    CANONICAL_PATTERNS = [
        # Indications
        (
            re.compile(r'\b(indications?\s+and\s+usage|therapeutic\s+indications?|indications?)\b', re.I),
            CanonicalSectionConcept.CONCEPT_INDICATIONS,
        ),
        # Posology / Dosage / Administration
        (
            re.compile(r'\b(posology\s+and\s+method\s+of\s+administration|dosage\s+and\s+administration|posology|dosage|method\s+of\s+administration|dosing)\b', re.I),
            CanonicalSectionConcept.CONCEPT_POSOLOGY_DOSAGE,
        ),
        # Dosage Forms & Strengths / Pharmaceutical Form
        (
            re.compile(r'\b(dosage\s+forms\s+and\s+strengths|pharmaceutical\s+form|qualitative\s+and\s+quantitative\s+composition)\b', re.I),
            CanonicalSectionConcept.CONCEPT_DOSAGE_FORMS,
        ),
        # Contraindications
        (
            re.compile(r'\b(contraindications?|contra-indications?)\b', re.I),
            CanonicalSectionConcept.CONCEPT_CONTRAINDICATIONS,
        ),
        # Warnings & Precautions
        (
            re.compile(r'\b(special\s+warnings\s+and\s+precautions\s+for\s+use|warnings\s+and\s+precautions|boxed\s+warning|black\s+box\s+warning|warnings?)\b', re.I),
            CanonicalSectionConcept.CONCEPT_WARNINGS,
        ),
        # Adverse Reactions / Undesirable Effects
        (
            re.compile(r'\b(undesirable\s+effects?|adverse\s+reactions?|side\s+effects?|adverse\s+events?)\b', re.I),
            CanonicalSectionConcept.CONCEPT_ADVERSE_REACTIONS,
        ),
        # Drug Interactions
        (
            re.compile(r'\b(interaction\s+with\s+other\s+medicinal\s+products|drug\s+interactions?|interactions?)\b', re.I),
            CanonicalSectionConcept.CONCEPT_DRUG_INTERACTIONS,
        ),
        # Populations (Pregnancy, Pediatric, Geriatric)
        (
            re.compile(r'\b(fertility[,\s]+pregnancy\s+and\s+lactation|use\s+in\s+specific\s+populations|pediatric\s+use|geriatric\s+use|pregnancy|lactation|special\s+populations)\b', re.I),
            CanonicalSectionConcept.CONCEPT_POPULATIONS,
        ),
        # Overdosage
        (
            re.compile(r'\b(overdosage|overdose|toxicity)\b', re.I),
            CanonicalSectionConcept.CONCEPT_OVERDOSAGE,
        ),
        # Clinical Pharmacology / Pharmacological Properties
        (
            re.compile(r'\b(pharmacological\s+properties|clinical\s+pharmacology|pharmacodynamics?|pharmacokinetics?|nonclinical\s+toxicology|clinical\s+particulars)\b', re.I),
            CanonicalSectionConcept.CONCEPT_CLINICAL_PHARM,
        ),
        # Storage & Handling / How Supplied
        (
            re.compile(r'\b(how\s+supplied[\s/]+storage\s+and\s+handling|pharmaceutical\s+particulars|special\s+precautions\s+for\s+storage|shelf\s+life|storage\s+and\s+handling|how\s+supplied)\b', re.I),
            CanonicalSectionConcept.CONCEPT_STORAGE_HANDLING,
        ),
    ]

    # Standard unnumbered regulatory heading titles across US PLR, EU SmPC, and IB
    STANDARD_UNNUMBERED_HEADINGS = {
        # US FDA PLR
        "indications and usage",
        "dosage and administration",
        "dosage forms and strengths",
        "contraindications",
        "warnings and precautions",
        "adverse reactions",
        "drug interactions",
        "use in specific populations",
        "overdosage",
        "description",
        "clinical pharmacology",
        "nonclinical toxicology",
        "clinical studies",
        "how supplied/storage and handling",
        "patient counseling information",
        "boxed warning",
        "highlights of prescribing information",
        # EU SmPC Headings
        "name of the medicinal product",
        "qualitative and quantitative composition",
        "pharmaceutical form",
        "clinical particulars",
        "therapeutic indications",
        "posology and method of administration",
        "contraindications",
        "special warnings and precautions for use",
        "interaction with other medicinal products and other forms of interaction",
        "fertility, pregnancy and lactation",
        "effects on ability to drive and use machines",
        "undesirable effects",
        "overdose",
        "pharmacological properties",
        "pharmacodynamic properties",
        "pharmacokinetic properties",
        "preclinical safety data",
        "pharmaceutical particulars",
        "list of excipients",
        "incompatibilities",
        "shelf life",
        "special precautions for storage",
        "nature and contents of container",
        "special precautions for disposal",
        # Investigator's Brochure (ICH GCP E6)
        "summary",
        "introduction",
        "physical, chemical, and pharmaceutical properties and formulation",
        "nonclinical studies",
        "nonclinical pharmacology",
        "pharmacokinetics and product metabolism in animals",
        "toxicology",
        "effects in humans",
        "pharmacokinetics and product metabolism in humans",
        "safety and efficacy",
        "marketing experience",
        "summary of data and guidance for the investigator",
    }

    def normalize_concept(self, text: str) -> Optional[str]:
        """Map raw heading text to a CanonicalSectionConcept, if applicable."""
        clean = text.strip()
        for pattern, concept in self.CANONICAL_PATTERNS:
            if pattern.search(clean):
                return concept
        return None

    def is_heading(self, line: str) -> bool:
        """Evaluate whether a line represents a regulatory heading."""
        return self.parse_heading(line) is not None

    def parse_heading(self, line: str, order_index: int = 0) -> Optional[HeadingInfo]:
        """Parse a candidate line into HeadingInfo if it qualifies as a heading."""
        clean = line.strip()
        if not clean or len(clean) > 200:
            return None

        # 1. Markdown Header check: e.g. "# Heading", "## Subheading"
        md_match = self.MARKDOWN_HEADER_PATTERN.match(clean)
        if md_match:
            hashes = md_match.group(1)
            title = md_match.group(2).strip()
            level = len(hashes)

            # Check if title itself has numbering: e.g. "## 4.2 Posology"
            num_match = self.NUMBERED_SECTION_PATTERN.match(title)
            sec_num = num_match.group(1) if num_match else None
            clean_title = num_match.group(2).strip() if num_match else title

            canonical = self.normalize_concept(clean_title)
            return HeadingInfo(
                heading_raw=clean,
                section_number=sec_num,
                title=clean_title,
                level=level,
                heading_normalized=canonical,
                is_canonical=canonical is not None,
                order_index=order_index,
            )

        # 2. Numbered Section check: e.g. "4.2 Posology and method of administration", "1. Name"
        num_match = self.NUMBERED_SECTION_PATTERN.match(clean)
        if num_match:
            sec_num = num_match.group(1)
            title = num_match.group(2).strip()
            # Outline level based on dot depth (e.g. "4" -> 1, "4.2" -> 2, "4.2.1" -> 3)
            level = len(sec_num.split("."))
            parent_num = ".".join(sec_num.split(".")[:-1]) if level > 1 else None

            canonical = self.normalize_concept(title)
            return HeadingInfo(
                heading_raw=clean,
                section_number=sec_num,
                title=title,
                level=level,
                heading_normalized=canonical,
                parent_section_number=parent_num,
                is_canonical=canonical is not None,
                order_index=order_index,
            )

        # 3. Unnumbered Standard Heading check
        # Check against normalized standard heading set (e.g. "INDICATIONS AND USAGE", "Therapeutic indications")
        clean_no_colon = clean.rstrip(":")
        lower_line = clean_no_colon.lower()

        if lower_line in self.STANDARD_UNNUMBERED_HEADINGS:
            canonical = self.normalize_concept(clean_no_colon)
            return HeadingInfo(
                heading_raw=clean,
                section_number=None,
                title=clean_no_colon,
                level=1,
                heading_normalized=canonical,
                is_canonical=canonical is not None,
                order_index=order_index,
            )

        # 4. Uppercase Heading heuristic
        # Must be uppercase, between 2 and 10 words, under 80 characters, no terminal punctuation other than colon
        words = clean_no_colon.split()
        if clean_no_colon.isupper() and 1 <= len(words) <= 10 and len(clean_no_colon) <= 80:
            # Avoid single common words like "ADULTS" or "ORAL" unless matching a canonical concept
            canonical = self.normalize_concept(clean_no_colon)
            if canonical or len(words) >= 2:
                return HeadingInfo(
                    heading_raw=clean,
                    section_number=None,
                    title=clean_no_colon,
                    level=1,
                    heading_normalized=canonical,
                    is_canonical=canonical is not None,
                    order_index=order_index,
                )

        return None

    def is_list_item(self, line: str) -> bool:
        """Determine if a line is an inline list item (bullet or numbered)."""
        return self.parse_list_item(line) is not None

    def parse_list_item(self, line: str, order_index: int = 0) -> Optional[ListItemInfo]:
        """Parse a candidate line into ListItemInfo if it represents a bullet or list item."""
        clean = line.strip()
        if not clean:
            return None

        # Check standard bullet markers
        bullet_match = self.BULLET_PATTERN.match(clean)
        if bullet_match:
            marker = bullet_match.group(1)
            content = bullet_match.group(2).strip()
            return ListItemInfo(
                raw_line=clean,
                marker=marker,
                content=content,
                item_type="bullet",
                order_index=order_index,
            )

        # Check numbered / lettered items (e.g. "1.", "(a)", "(i)")
        item_match = self.NUMBERED_ITEM_PATTERN.match(clean)
        if item_match:
            m1 = item_match.group(1) or item_match.group(2)
            content = item_match.group(3).strip()

            if m1.isdigit():
                item_type = "numbered_item"
            elif re.match(r'^[ivxcdmIVXCDM]+$', m1):
                item_type = "roman_item"
            else:
                item_type = "lettered_item"

            # Determine marker string
            marker_str = f"({m1})" if item_match.group(1) else f"{m1}."

            return ListItemInfo(
                raw_line=clean,
                marker=marker_str,
                content=content,
                item_type=item_type,
                order_index=order_index,
            )

        return None

    def build_hierarchy(self, headings: List[HeadingInfo]) -> List[HeadingInfo]:
        """Compute parent section relationships for an ordered list of parsed headings."""
        stack: List[HeadingInfo] = []

        for h in headings:
            # Pop elements from stack that are at same or deeper level
            while stack and stack[-1].level >= h.level:
                stack.pop()

            if stack:
                h.parent_section_number = stack[-1].section_number

            stack.append(h)

        return headings
