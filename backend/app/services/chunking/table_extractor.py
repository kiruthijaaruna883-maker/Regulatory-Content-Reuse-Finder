"""Regulatory table and bullet list extraction engine.

Provides deterministic extraction for:
- Markdown tables (| Col 1 | Col 2 |)
- HTML tables (<table>, <tr>, <th>, <td>)
- TSV-style tabular data
- Bullet lists (-, *, •) and numbered/lettered list structures

Converts tabular content into Phase 1 models:
- RegulatoryTable
- RegulatoryTableRow
Preserves column header to cell value relationships and content integrity.
"""

import re
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple
from uuid import uuid4
from app.models.document import RegulatoryTable, RegulatoryTableRow
from app.services.chunking.outline_engine import ListItemInfo, RegulatoryOutlineEngine


class HTMLTableParser(HTMLParser):
    """Safe, standard-library HTML parser extracting table headers and cell rows."""

    def __init__(self):
        super().__init__()
        self.tables: List[Dict[str, any]] = []
        self._current_table: Optional[Dict[str, any]] = None
        self._current_row: Optional[List[str]] = None
        self._current_cell: Optional[List[str]] = None
        self._current_tag: Optional[str] = None
        self._is_header_cell: bool = False
        self._current_headers: List[str] = []
        self._current_rows: List[List[str]] = []
        self._caption: Optional[str] = None
        self._in_caption: bool = False

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        tag_lower = tag.lower()
        self._current_tag = tag_lower

        if tag_lower == "table":
            self._current_table = {}
            self._current_headers = []
            self._current_rows = []
            self._caption = None
        elif tag_lower == "caption":
            self._in_caption = True
            self._current_cell = []
        elif tag_lower == "tr":
            self._current_row = []
        elif tag_lower in ("th", "td"):
            self._is_header_cell = (tag_lower == "th")
            self._current_cell = []

    def handle_endtag(self, tag: str):
        tag_lower = tag.lower()

        if tag_lower == "caption" and self._in_caption:
            self._in_caption = False
            self._caption = "".join(self._current_cell or []).strip()
            self._current_cell = None
        elif tag_lower in ("th", "td"):
            cell_text = "".join(self._current_cell or []).strip()
            if self._current_row is not None:
                self._current_row.append(cell_text)
            self._current_cell = None
        elif tag_lower == "tr":
            if self._current_row:
                # If row contains only TH tags or we have no headers yet and all were TH
                if self._is_header_cell and not self._current_headers:
                    self._current_headers = self._current_row
                else:
                    self._current_rows.append(self._current_row)
            self._current_row = None
            self._is_header_cell = False
        elif tag_lower == "table":
            if self._current_rows or self._current_headers:
                self.tables.append({
                    "caption": self._caption,
                    "headers": self._current_headers,
                    "rows": self._current_rows,
                })
            self._current_table = None

    def handle_data(self, data: str):
        if self._current_cell is not None:
            self._current_cell.append(data)


class RegulatoryTableExtractor:
    """Deterministic extractor for Markdown, HTML, and TSV tables in regulatory text."""

    # Markdown table separator row regex: e.g. | --- | :---: | ---: |
    MD_SEPARATOR_PATTERN = re.compile(
        r'^\s*\|?(?:\s*:?-+:?\s*\|)+\s*(?::?-+:?)?\s*\|?\s*$'
    )

    def extract_markdown_tables(
        self,
        text: str,
        section_id: str = "sec_default",
    ) -> List[RegulatoryTable]:
        """Extract Markdown tables conforming to standard pipe syntax."""
        lines = text.splitlines()
        tables: List[RegulatoryTable] = []
        i = 0
        n = len(lines)

        while i < n:
            line = lines[i].strip()
            # A markdown table requires at least header row, separator row, and 1+ data rows
            if "|" in line and i + 1 < n and self.MD_SEPARATOR_PATTERN.match(lines[i + 1].strip()):
                raw_headers = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                headers = [h for h in raw_headers if h or len(raw_headers) == 1]
                table_lines = [lines[i], lines[i + 1]]
                i += 2  # Skip header and separator

                rows: List[RegulatoryTableRow] = []
                row_idx = 0

                while i < n and "|" in lines[i].strip() and not lines[i].strip().startswith("#"):
                    row_line = lines[i].strip()
                    table_lines.append(row_line)
                    raw_cells = [c.strip() for c in row_line.strip("|").split("|")]

                    # Pad or align cells to header length
                    if len(raw_cells) < len(headers):
                        raw_cells.extend([""] * (len(headers) - len(raw_cells)))

                    row_dict = {}
                    for col_idx, h in enumerate(headers):
                        row_dict[h] = raw_cells[col_idx] if col_idx < len(raw_cells) else ""

                    rows.append(RegulatoryTableRow(
                        row_index=row_idx,
                        cells=raw_cells[:len(headers)],
                        row_dict=row_dict,
                    ))
                    row_idx += 1
                    i += 1

                if headers and rows:
                    raw_md = "\n".join(table_lines)
                    tables.append(RegulatoryTable(
                        table_id=f"tbl_{uuid4().hex[:8]}",
                        section_id=section_id,
                        headers=headers,
                        raw_markdown=raw_md,
                        rows=rows,
                    ))
            else:
                i += 1

        return tables

    def extract_html_tables(
        self,
        text: str,
        section_id: str = "sec_default",
    ) -> List[RegulatoryTable]:
        """Extract HTML tables using standard HTML parser."""
        if "<table" not in text.lower():
            return []

        parser = HTMLTableParser()
        try:
            parser.feed(text)
        except Exception:
            return []

        tables: List[RegulatoryTable] = []
        for t_dict in parser.tables:
            headers = t_dict.get("headers") or []
            raw_rows = t_dict.get("rows") or []
            caption = t_dict.get("caption")

            # If no explicit TH header, treat first row as header if multiple rows exist
            if not headers and len(raw_rows) > 1:
                headers = raw_rows[0]
                raw_rows = raw_rows[1:]

            if not headers and not raw_rows:
                continue

            # Fallback headers if table has data but no header
            if not headers and raw_rows:
                col_count = len(raw_rows[0])
                headers = [f"Column {j + 1}" for j in range(col_count)]

            structured_rows: List[RegulatoryTableRow] = []
            for row_idx, r_cells in enumerate(raw_rows):
                row_dict = {}
                for col_idx, h in enumerate(headers):
                    row_dict[h] = r_cells[col_idx] if col_idx < len(r_cells) else ""

                structured_rows.append(RegulatoryTableRow(
                    row_index=row_idx,
                    cells=r_cells,
                    row_dict=row_dict,
                ))

            # Build markdown representation for traceability
            md_lines = []
            if headers:
                md_lines.append("| " + " | ".join(headers) + " |")
                md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
            for r in structured_rows:
                md_lines.append("| " + " | ".join(r.cells) + " |")

            tables.append(RegulatoryTable(
                table_id=f"tbl_{uuid4().hex[:8]}",
                section_id=section_id,
                table_title=caption,
                headers=headers,
                raw_markdown="\n".join(md_lines) if md_lines else None,
                rows=structured_rows,
            ))

        return tables

    def extract_tsv_tables(
        self,
        text: str,
        section_id: str = "sec_default",
    ) -> List[RegulatoryTable]:
        """Extract TSV formatted tabular sections where tab density indicates structured columns."""
        lines = [line for line in text.splitlines() if line.strip()]
        if len(lines) < 2:
            return []

        # Check if consecutive lines share the same tab count (>= 2 columns)
        tables: List[RegulatoryTable] = []
        current_tsv_block: List[str] = []
        expected_cols = None

        for line in lines:
            if "\t" in line:
                cols = [c.strip() for c in line.split("\t")]
                col_count = len(cols)
                if col_count >= 2:
                    if expected_cols is None:
                        expected_cols = col_count
                        current_tsv_block.append(line)
                    elif col_count == expected_cols:
                        current_tsv_block.append(line)
                    else:
                        # Column mismatch -> flush current block
                        if len(current_tsv_block) >= 2:
                            tables.append(self._build_tsv_table(current_tsv_block, section_id))
                        current_tsv_block = [line]
                        expected_cols = col_count
                else:
                    if len(current_tsv_block) >= 2:
                        tables.append(self._build_tsv_table(current_tsv_block, section_id))
                    current_tsv_block = []
                    expected_cols = None
            else:
                if len(current_tsv_block) >= 2:
                    tables.append(self._build_tsv_table(current_tsv_block, section_id))
                current_tsv_block = []
                expected_cols = None

        if len(current_tsv_block) >= 2:
            tables.append(self._build_tsv_table(current_tsv_block, section_id))

        return tables

    def _build_tsv_table(self, lines: List[str], section_id: str) -> RegulatoryTable:
        """Helper to build RegulatoryTable from TSV block."""
        headers = [c.strip() for c in lines[0].split("\t")]
        structured_rows: List[RegulatoryTableRow] = []

        for row_idx, line in enumerate(lines[1:]):
            cells = [c.strip() for c in line.split("\t")]
            row_dict = {}
            for col_idx, h in enumerate(headers):
                row_dict[h] = cells[col_idx] if col_idx < len(cells) else ""

            structured_rows.append(RegulatoryTableRow(
                row_index=row_idx,
                cells=cells,
                row_dict=row_dict,
            ))

        md_lines = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
        ]
        for r in structured_rows:
            md_lines.append("| " + " | ".join(r.cells) + " |")

        return RegulatoryTable(
            table_id=f"tbl_{uuid4().hex[:8]}",
            section_id=section_id,
            headers=headers,
            raw_markdown="\n".join(md_lines),
            rows=structured_rows,
        )

    @staticmethod
    def format_row_as_content(table: RegulatoryTable, row: RegulatoryTableRow) -> str:
        """Format a single table row as key-value pairs suitable for a table_row chunk.

        Example: 'Creatinine Clearance: < 30 mL/min | Recommended Starting Dose: 25 mg once daily'
        """
        parts = []
        for header, val in row.row_dict.items():
            if val:
                parts.append(f"{header}: {val}")
            else:
                parts.append(header)
        return " | ".join(parts)


class RegulatoryBulletExtractor:
    """Deterministic extractor for regulatory bullet points and ordered list structures."""

    def __init__(self):
        self.outline_engine = RegulatoryOutlineEngine()

    def extract_bullets_and_lists(
        self,
        text: str,
    ) -> List[Tuple[Optional[str], List[ListItemInfo]]]:
        """Extract bullet groups along with their preceding introductory stem sentence, if present.

        Returns:
            List of tuples: (stem_sentence_or_none, list_of_bullet_items).
        """
        lines = text.splitlines()
        groups: List[Tuple[Optional[str], List[ListItemInfo]]] = []

        current_items: List[ListItemInfo] = []
        current_stem: Optional[str] = None
        last_non_empty_line: Optional[str] = None
        item_order = 0

        for line in lines:
            clean = line.strip()
            if not clean:
                continue

            item_info = self.outline_engine.parse_list_item(clean, order_index=item_order)

            if item_info:
                # If starting a new bullet group and previous line ended with a colon, it's a stem sentence
                if not current_items and last_non_empty_line and last_non_empty_line.endswith(":"):
                    current_stem = last_non_empty_line

                current_items.append(item_info)
                item_order += 1
            else:
                # Line is not a list item
                if current_items:
                    groups.append((current_stem, current_items))
                    current_items = []
                    current_stem = None
                    item_order = 0

                last_non_empty_line = clean

        if current_items:
            groups.append((current_stem, current_items))

        return groups
