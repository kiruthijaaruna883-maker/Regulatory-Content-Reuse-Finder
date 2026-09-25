"""HTML regulatory document parser.

Parses HTML regulatory dossiers and drug labeling pages using Python's standard library.
Preserves headings (h1-h6), paragraphs, bullet/numbered lists, tables, and hierarchical structure.
Strips non-regulatory page chrome (scripts, styles, navigation, headers, footers).
"""

from html.parser import HTMLParser
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4

from app.models.document import (
    CanonicalSectionConcept,
    RegulatoryDocument,
    RegulatoryProvenance,
    RegulatorySection,
)
from app.services.chunking.outline_engine import HeadingInfo, RegulatoryOutlineEngine
from app.services.parsers.base_parser import BaseDocumentParser


class _RegulatoryHtmlExtractor(HTMLParser):
    """Event-driven HTML parser extracting structured sections, tables, lists, and headings."""

    # Page chrome and non-content elements to ignore
    SKIP_TAGS = frozenset([
        "script", "style", "noscript", "nav", "header",
        "footer", "aside", "svg", "iframe", "form", "meta", "link",
    ])

    HEADING_TAGS = frozenset(["h1", "h2", "h3", "h4", "h5", "h6"])

    def __init__(self, outline_engine: RegulatoryOutlineEngine):
        super().__init__()
        self.outline_engine = outline_engine

        self.skip_depth = 0
        self.in_head = False
        self.in_title = False
        self.document_title: Optional[str] = None

        # Sections tracking
        self.raw_sections: List[Dict[str, Any]] = []
        self.current_heading_tag: Optional[str] = None
        self.current_heading_text: List[str] = []
        self.current_body_lines: List[str] = []
        self.order_index = 0

        # List tracking: stack of (is_ordered, current_counter)
        self.list_stack: List[Tuple[bool, int]] = []
        self.in_list_item = False
        self.current_item_text: List[str] = []

        # Table tracking: stack of tables (rows of cells)
        self.in_table = False
        self.current_table_rows: List[List[str]] = []
        self.current_row_cells: List[str] = []
        self.in_cell = False
        self.current_cell_text: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        tag_lower = tag.lower()

        if tag_lower in self.SKIP_TAGS:
            self.skip_depth += 1
            return

        if self.skip_depth > 0:
            return

        if tag_lower == "head":
            self.in_head = True
            return

        if tag_lower == "title":
            self.in_title = True
            return

        # Headings
        if tag_lower in self.HEADING_TAGS:
            self._flush_current_section()
            self.current_heading_tag = tag_lower
            self.current_heading_text = []
            return

        # Lists
        if tag_lower == "ul":
            self.list_stack.append((False, 0))
            return
        elif tag_lower == "ol":
            self.list_stack.append((True, 1))
            return
        elif tag_lower == "li":
            self.in_list_item = True
            self.current_item_text = []
            return

        # Tables
        if tag_lower == "table":
            self.in_table = True
            self.current_table_rows = []
            return
        elif tag_lower == "tr":
            if self.in_table:
                self.current_row_cells = []
            return
        elif tag_lower in ("th", "td"):
            if self.in_table:
                self.in_cell = True
                self.current_cell_text = []
            return

        # Line breaks
        if tag_lower == "br":
            if self.in_cell:
                self.current_cell_text.append(" ")
            elif self.in_list_item:
                self.current_item_text.append(" ")
            else:
                self.current_body_lines.append("\n")

    def handle_endtag(self, tag: str):
        tag_lower = tag.lower()

        if tag_lower in self.SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return

        if self.skip_depth > 0:
            return

        if tag_lower == "head":
            self.in_head = False
            return

        if tag_lower == "title":
            self.in_title = False
            return

        # Headings
        if tag_lower in self.HEADING_TAGS:
            heading_str = " ".join("".join(self.current_heading_text).split()).strip()
            level = int(tag_lower[1])
            self._start_new_section(heading_str, level)
            self.current_heading_tag = None
            self.current_heading_text = []
            return

        # Lists
        if tag_lower in ("ul", "ol"):
            if self.list_stack:
                self.list_stack.pop()
            return
        elif tag_lower == "li":
            self.in_list_item = False
            item_str = " ".join("".join(self.current_item_text).split()).strip()
            if item_str and self.list_stack:
                is_ordered, counter = self.list_stack[-1]
                if is_ordered:
                    self.current_body_lines.append(f"{counter}. {item_str}")
                    # Increment counter
                    self.list_stack[-1] = (True, counter + 1)
                else:
                    self.current_body_lines.append(f"* {item_str}")
            return

        # Tables
        if tag_lower in ("th", "td"):
            self.in_cell = False
            cell_str = " ".join("".join(self.current_cell_text).split()).strip()
            self.current_row_cells.append(cell_str)
            return
        elif tag_lower == "tr":
            if self.in_table and self.current_row_cells:
                self.current_table_rows.append(self.current_row_cells)
                self.current_row_cells = []
            return
        elif tag_lower == "table":
            self.in_table = False
            md_table = self._build_markdown_table(self.current_table_rows)
            if md_table:
                self.current_body_lines.append("\n" + md_table + "\n")
            self.current_table_rows = []
            return

        # Paragraphs and block elements
        if tag_lower in ("p", "div", "blockquote", "section", "article"):
            self.current_body_lines.append("\n")

    def handle_data(self, data: str):
        if self.skip_depth > 0:
            return

        if self.in_head:
            if self.in_title:
                if not self.document_title:
                    self.document_title = data.strip()
                else:
                    self.document_title += " " + data.strip()
            return

        if self.current_heading_tag:
            self.current_heading_text.append(data)
            return

        if self.in_cell:
            self.current_cell_text.append(data)
            return

        if self.in_list_item:
            self.current_item_text.append(data)
            return

        if not self.in_table:
            self.current_body_lines.append(data)

    def _flush_current_section(self):
        """Append accumulated body text into the active section dictionary."""
        body = "".join(self.current_body_lines).strip()
        # Clean consecutive newlines
        body = re.sub(r'\n{3,}', '\n\n', body)

        if self.raw_sections:
            if body:
                if self.raw_sections[-1]["raw_text"]:
                    self.raw_sections[-1]["raw_text"] += "\n\n" + body
                else:
                    self.raw_sections[-1]["raw_text"] = body
        elif body:
            # Body text before any heading: create initial section
            self.raw_sections.append({
                "heading_raw": "General Content",
                "section_number": None,
                "heading_normalized": None,
                "level": 1,
                "raw_text": body,
                "order_index": self.order_index,
            })
            self.order_index += 1

        self.current_body_lines = []

    def _start_new_section(self, heading_str: str, level: int):
        """Initialize a new section header."""
        if not heading_str:
            heading_str = f"Section {self.order_index + 1}"

        heading_info = self.outline_engine.parse_heading(heading_str, order_index=self.order_index)
        sec_num = heading_info.section_number if heading_info else None
        norm_concept = heading_info.heading_normalized if heading_info else self.outline_engine.normalize_concept(heading_str)

        self.raw_sections.append({
            "heading_raw": heading_str,
            "section_number": sec_num,
            "heading_normalized": norm_concept,
            "level": level,
            "raw_text": "",
            "order_index": self.order_index,
        })
        self.order_index += 1

    def finish(self) -> List[Dict[str, Any]]:
        """Finalize parsing and return raw sections."""
        self._flush_current_section()
        return self.raw_sections

    @staticmethod
    def _build_markdown_table(rows: List[List[str]]) -> str:
        """Convert 2D list of cells into a GitHub Markdown table string."""
        if not rows:
            return ""

        max_cols = max(len(r) for r in rows)
        if max_cols == 0:
            return ""

        for r in rows:
            while len(r) < max_cols:
                r.append("")

        header = rows[0]
        md_lines = ["| " + " | ".join(header) + " |"]
        md_lines.append("| " + " | ".join(["---"] * max_cols) + " |")
        for row in rows[1:]:
            md_lines.append("| " + " | ".join(row) + " |")

        return "\n".join(md_lines)


class HtmlDocumentParser(BaseDocumentParser):
    """Deterministic parser for HTML regulatory dossiers, labels, and notices."""

    def __init__(self):
        self.outline_engine = RegulatoryOutlineEngine()

    def can_parse(
        self,
        content: Union[str, bytes],
        filename: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> bool:
        """Evaluate if content or filename indicates HTML format."""
        if filename and filename.lower().endswith((".html", ".htm", ".xhtml")):
            return True
        if mime_type and mime_type.lower() in ("text/html", "application/xhtml+xml"):
            return True

        text = self.decode_content(content).strip()
        lower = text.lower()
        if (
            lower.startswith("<!doctype html")
            or "<html" in lower
            or "<body" in lower
            or ("<h1" in lower and "</h1" in lower)
            or ("<table" in lower and "</table" in lower)
        ):
            return True
        return False

    def parse(
        self,
        content: Union[str, bytes],
        document_id: Optional[str] = None,
        document_name: Optional[str] = None,
        provenance: Optional[RegulatoryProvenance] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RegulatoryDocument:
        """Parse HTML content into a hierarchical RegulatoryDocument."""
        raw_text = self.decode_content(content)
        clean_text = raw_text.strip()

        meta = metadata or {}
        doc_id = document_id or meta.get("document_id") or f"doc_{uuid4().hex[:10]}"
        doc_title = document_name or meta.get("document_name") or meta.get("title")
        doc_type = meta.get("document_type", "REGULATORY_LABEL")
        jurisdiction = meta.get("jurisdiction", "US_FDA")
        product = meta.get("product_name") or meta.get("product")
        drug = meta.get("active_ingredient") or meta.get("drug")
        version = meta.get("version", "1.0")

        prov = provenance or self.default_provenance(
            source_repo=meta.get("source", "InternalDraft"),
            identifier=meta.get("source_identifier", doc_id),
            url=meta.get("source_url"),
        )

        if not clean_text:
            return RegulatoryDocument(
                document_id=doc_id,
                title=doc_title or "Empty HTML Document",
                document_type=doc_type,
                jurisdiction=jurisdiction,
                product_name=product,
                active_ingredient=drug,
                version=version,
                provenance=prov,
                sections=[],
                raw_content="",
            )

        extractor = _RegulatoryHtmlExtractor(self.outline_engine)
        try:
            extractor.feed(clean_text)
            raw_sections = extractor.finish()
        except Exception as exc:
            # HTMLParser rarely raises, but if it does, wrap cleanly
            raise ValueError(f"Invalid HTML content: {exc}") from exc

        # Set title from HTML if not provided
        if not doc_title:
            doc_title = extractor.document_title or "HTML Regulatory Document"

        # If document title is still generic and first section is h1, infer title
        if doc_title == "HTML Regulatory Document" and raw_sections and raw_sections[0]["level"] == 1:
            doc_title = raw_sections[0]["heading_raw"]

        root_sections = self._build_hierarchical_sections(raw_sections, doc_id)

        return RegulatoryDocument(
            document_id=doc_id,
            title=doc_title,
            document_type=doc_type,
            jurisdiction=jurisdiction,
            product_name=product,
            active_ingredient=drug,
            version=str(version),
            provenance=prov,
            sections=root_sections,
            raw_content=raw_text,
        )

    def _build_hierarchical_sections(
        self,
        raw_sections_data: List[Dict[str, Any]],
        doc_id: str,
    ) -> List[RegulatorySection]:
        """Convert list of section dictionaries into nested RegulatorySection hierarchy based on heading level."""
        if not raw_sections_data:
            return []

        root_sections: List[RegulatorySection] = []
        stack: List[Tuple[int, RegulatorySection]] = []

        for data in raw_sections_data:
            level = data["level"]
            sec_num = data["section_number"]
            title = data["heading_raw"]
            sec_slug = re.sub(r'[^a-zA-Z0-9]', '_', (sec_num or title).lower())[:20]
            sec_id = f"sec_{doc_id}_{data['order_index']}_{sec_slug}"

            section = RegulatorySection(
                section_id=sec_id,
                section_number=sec_num,
                heading_raw=title,
                heading_normalized=data["heading_normalized"],
                order_index=data["order_index"],
                raw_text=data["raw_text"],
                subsections=[],
            )

            # Pop elements from stack that are deeper or at same level
            while stack and stack[-1][0] >= level:
                stack.pop()

            if stack:
                parent_sec = stack[-1][1]
                section.parent_section_id = parent_sec.section_id
                parent_sec.subsections.append(section)
            else:
                root_sections.append(section)

            stack.append((level, section))

        return root_sections
