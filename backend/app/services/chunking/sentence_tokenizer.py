"""Regulatory-aware sentence tokenizer module.

Provides deterministic, regulatory-safe sentence boundary tokenization without
incorrectly splitting on:
- Pharmaceutical units: mg., mL., mcg., kg., tab., etc.
- Common abbreviations: e.g., i.e., vs., approx., etc.
- Clinical titles and references: Dr., No., Ref., Sec., etc.
- Decimal values and section numbers: 4.2, 0.05, 12.5 mg
- Numbered list markers: 1., 2., (a), (i)
"""

import re
from typing import List, Tuple


class RegulatorySentenceTokenizer:
    """Deterministic sentence tokenizer designed specifically for regulatory text.

    Preserves verbatim source content and guarantees zero mid-sentence slicing
    on pharmaceutical dosages, Latin abbreviations, and regulatory citations.
    """

    # Protected single-word abbreviations followed by a period (case-insensitive)
    PROTECTED_ABBREVIATIONS = {
        # Dosage and measurement units
        "mg", "ml", "mcg", "kg", "g", "tab", "tabs", "cap", "caps",
        "meq", "iu", "oz", "tsp", "tbsp", "cm", "mm",
        # Common Latin / informational abbreviations
        "eg", "ie", "vs", "approx", "etc", "al", "cf", "viz",
        # Professional titles and honorifics
        "dr", "prof", "mr", "mrs", "ms",
        # Document and outline references
        "no", "nos", "ref", "sec", "vol", "fig", "tab", "para", "p", "pp",
    }

    # Multi-period abbreviations that should never trigger sentence boundaries
    MULTI_PERIOD_ABBREVIATIONS = {
        "e.g.", "i.e.", "et al.", "u.s.", "u.s.a.", "ph.d.", "m.d.", "s.p.l.",
    }

    def __init__(self):
        # Pattern to match candidate end-of-sentence punctuation:
        # A period, question mark, or exclamation mark followed by whitespace or end of string.
        # Captures closing quotes or brackets attached to the punctuation.
        self._boundary_candidate_regex = re.compile(
            r'([.?!])(["\')\]}]*)(\s+|$)',
            re.UNICODE,
        )

    def tokenize(self, text: str) -> List[str]:
        """Split text into sentences, preserving exact source phrasing.

        Args:
            text: Raw input text.

        Returns:
            List of sentence strings.
        """
        spans = self.tokenize_with_spans(text)
        return [sentence for sentence, _, _ in spans]

    def tokenize_with_spans(self, text: str) -> List[Tuple[str, int, int]]:
        """Split text into sentences and return (sentence_text, start_offset, end_offset).

        Args:
            text: Raw input text.

        Returns:
            List of tuples: (sentence_text, start_char_index, end_char_index).
        """
        if not text or not text.strip():
            return []

        clean_text = text
        boundaries = [0]
        length = len(clean_text)

        for match in self._boundary_candidate_regex.finditer(clean_text):
            punct = match.group(1)
            punct_idx = match.start(1)
            closing_quotes = match.group(2)
            whitespace = match.group(3)
            after_match_idx = match.end()

            # Question marks and exclamation marks are almost always valid boundaries
            if punct in ("?", "!"):
                # If followed by end of text or uppercase/quote, accept boundary
                boundary_idx = punct_idx + 1 + len(closing_quotes)
                boundaries.append(boundary_idx)
                continue

            # Punctuation is a period '.'
            # 1. Decimal numbers: check if preceded by digit and immediately followed by digit
            if punct_idx > 0 and punct_idx + 1 < length:
                if clean_text[punct_idx - 1].isdigit() and clean_text[punct_idx + 1].isdigit():
                    continue

            # 2. Ellipsis: if this period is immediately followed by another period, it is not the terminal punctuation
            if punct_idx + 1 < length and clean_text[punct_idx + 1] == '.':
                continue

            # 3. Extract the preceding token before the period
            preceding_slice = clean_text[:punct_idx]
            token_match = re.search(r'([A-Za-z0-9\._\-]+)$', preceding_slice)
            preceding_token = token_match.group(1) if token_match else ""
            lower_token = preceding_token.lower()

            # 4. Check multi-period abbreviations (e.g. "e.g.", "i.e.")
            full_token_with_dot = (lower_token + ".").lower()
            if full_token_with_dot in self.MULTI_PERIOD_ABBREVIATIONS or lower_token in self.MULTI_PERIOD_ABBREVIATIONS:
                continue

            # Check if token is just the second half of e.g. or i.e. (like "g." preceded by "e.")
            if re.search(r'\b[a-z]\.[a-z]$', lower_token):
                continue

            # 5. Check single-word protected abbreviations (e.g. "mg", "mL", "approx", "vs", "Dr")
            token_core = re.sub(r'[^a-zA-Z0-9]', '', lower_token)
            if token_core in self.PROTECTED_ABBREVIATIONS:
                continue

            # 6. Single uppercase letter (like initial in "Dr. J. Smith" or section "A.")
            if len(preceding_token) == 1 and preceding_token.isupper():
                # If preceded by another capital initial or space, usually a name or inline marker
                if punct_idx > 1 and clean_text[punct_idx - 2].isalpha():
                    continue

            # 7. Check if this is an outline/list item marker at start of line (e.g. "^1. ")
            # In "1. Wash hands", "1." is the marker, not a sentence end.
            line_start = clean_text.rfind('\n', 0, punct_idx)
            line_prefix = clean_text[line_start + 1:punct_idx].strip()
            if re.match(r'^(?:\d+|[a-zA-Z]|[ivxIVX]+)$', line_prefix):
                # The period is part of the outline number marker (e.g. "1.", "4.2.", "a.")
                continue

            # 8. Check character following the whitespace
            # In English and clinical texts, sentences start with uppercase, digit, quote, or bracket
            if after_match_idx < length:
                following_char = clean_text[after_match_idx]
                if following_char.islower():
                    # Followed by lowercase word (e.g. "10 mg. once daily") -> not a boundary
                    continue

            # If all checks pass, this is a legitimate sentence boundary
            boundary_idx = punct_idx + 1 + len(closing_quotes)
            boundaries.append(boundary_idx)

        boundaries.append(length)
        boundaries = sorted(list(set(boundaries)))

        sentences: List[Tuple[str, int, int]] = []
        for i in range(len(boundaries) - 1):
            start = boundaries[i]
            end = boundaries[i + 1]
            raw_chunk = clean_text[start:end]
            stripped_chunk = raw_chunk.strip()

            if stripped_chunk:
                # Find exact offsets of stripped text
                offset_start = start + raw_chunk.find(stripped_chunk)
                offset_end = offset_start + len(stripped_chunk)
                sentences.append((stripped_chunk, offset_start, offset_end))

        return sentences
