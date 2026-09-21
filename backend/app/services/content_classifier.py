"""Content classification module for regulatory texts.

Classifies regulatory units into standardized RegulatoryContentType values.
"""

import re
from typing import Optional
from app.models.content import RegulatoryContentType


class ContentClassifier:
    """Classifies regulatory text units using deterministic clinical heuristics."""

    def classify(self, text: str, section_hint: Optional[str] = None) -> RegulatoryContentType:
        """Assign standardized RegulatoryContentType to given regulatory content."""
        clean_text = text.strip().lower()
        hint = (section_hint or "").lower()

        # Structured field check (e.g. "NDC: ...", "Strength: ...")
        if re.match(r"^[A-Z0-9_\-\s]{2,20}\s*:\s*[^\n]+$", text.strip()):
            return RegulatoryContentType.STRUCTURED_FIELD

        # Table content check
        if "|" in text or "\t" in text:
            return RegulatoryContentType.TABLE_CONTENT

        # Section hint alignment
        if "dosage" in hint or "administration" in hint:
            return RegulatoryContentType.DOSAGE_STATEMENT
        if "indication" in hint or "usage" in hint:
            return RegulatoryContentType.INDICATION_STATEMENT
        if "contraindication" in hint or "warning" in hint or "adverse" in hint:
            return RegulatoryContentType.SAFETY_STATEMENT
        if "clinical" in hint or "study" in hint or "pharmacology" in hint:
            return RegulatoryContentType.CLINICAL_STATEMENT

        # Text content pattern matching
        # 1. Safety / Contraindications
        if re.search(r"\b(contraindicated|warning|caution|boxed warning|do not use|adverse reaction|black box)\b", clean_text):
            return RegulatoryContentType.SAFETY_STATEMENT

        # 2. Dosage & Administration
        if re.search(r"\b(dose|dosage|administer|take\s+\d+|daily|every\s+\d+\s+hours?|mg|tablets?|capsules?)\b", clean_text):
            return RegulatoryContentType.DOSAGE_STATEMENT

        # 3. Indication & Usage
        if re.search(r"\b(indicated for|treatment of|relief of|to treat|management of|indicated as)\b", clean_text):
            return RegulatoryContentType.INDICATION_STATEMENT

        # 4. Population Statement
        if re.search(r"\b(pediatric|children|neonates|infants|geriatric|elderly|adults\s+only|age\s+group)\b", clean_text):
            return RegulatoryContentType.POPULATION_STATEMENT

        # 5. Clinical / Study Statement
        if re.search(r"\b(in\s+clinical\s+trials?|randomized|placebo|study\s+\d+|efficacy|pharmacokinetics)\b", clean_text):
            return RegulatoryContentType.CLINICAL_STATEMENT

        # 6. Regulatory Statement
        if re.search(r"\b(prescribing information|fda approved|spl|package insert|how supplied|storage)\b", clean_text):
            return RegulatoryContentType.REGULATORY_STATEMENT

        return RegulatoryContentType.GENERAL_REGULATORY_CONTENT
