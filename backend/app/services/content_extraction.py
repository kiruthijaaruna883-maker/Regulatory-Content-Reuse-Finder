"""Document content extraction service module.

Extracts structured regulatory sections, tables, and paragraphs from uploaded
documents or text inputs. Provides deterministic baseline extraction.
"""

import re
from typing import Dict, List, Optional
from uuid import uuid4
from app.models.content import RegulatoryContentItem


class ContentExtractionService:
    """Service for extracting and segmenting regulatory content from documents."""

    # Standard regulatory headings to segment text deterministically
    REGULATORY_HEADERS = [
        r"INDICATIONS\s+AND\s+USAGE",
        r"DOSAGE\s+AND\s+ADMINISTRATION",
        r"DOSAGE\s+FORMS\s+AND\s+STRENGTHS",
        r"CONTRAINDICATIONS",
        r"WARNINGS\s+AND\s+PRECAUTIONS",
        r"ADVERSE\s+REACTIONS",
        r"DRUG\s+INTERACTIONS",
        r"USE\s+IN\s+SPECIFIC\s+POPULATIONS",
        r"OVERDOSAGE",
        r"DESCRIPTION",
        r"CLINICAL\s+PHARMACOLOGY",
        r"NONCLINICAL\s+TOXICOLOGY",
        r"CLINICAL\s+STUDIES",
        r"HOW\s+SUPPLIED/STORAGE\s+AND\s+HANDLING",
        r"PATIENT\s+COUNSELING\s+INFORMATION",
    ]

    def extract_sections_from_text(
        self,
        text: str,
        document_name: str = "Uploaded Document",
    ) -> List[RegulatoryContentItem]:
        """Parse raw document text into recognized regulatory sections."""
        clean_text = text.strip()
        if not clean_text:
            return []

        pattern = r"(?im)^\s*(?:[0-9]+\s+)?(" + "|".join(self.REGULATORY_HEADERS) + r")[:\.]?\s*$"
        matches = list(re.finditer(pattern, clean_text))

        if not matches:
            # Fallback: treat entire document as one general section
            return [
                RegulatoryContentItem(
                    content_id=f"ext_{uuid4().hex[:8]}",
                    document_name=document_name,
                    source="Internal Document",
                    section="General Content",
                    text=clean_text[:5000],
                )
            ]

        sections: List[RegulatoryContentItem] = []
        for i, match in enumerate(matches):
            section_name = match.group(1).title()
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(clean_text)

            section_text = clean_text[start_pos:end_pos].strip()
            if section_text:
                sections.append(
                    RegulatoryContentItem(
                        content_id=f"ext_{uuid4().hex[:8]}",
                        document_name=document_name,
                        source="Internal Document",
                        section=section_name,
                        text=section_text[:5000],
                    )
                )

        return sections
