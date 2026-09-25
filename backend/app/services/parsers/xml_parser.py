"""XML regulatory document parser.

Parses structured regulatory XML documents including HL7 SPL (Structured Product Labeling)
and arbitrary hierarchical regulatory XML formats safely using Python's standard library.
Preserves element hierarchy, attributes, text content, and element paths/locations.
"""

import re
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4
import xml.etree.ElementTree as ET

from app.models.document import (
    CanonicalSectionConcept,
    RegulatoryDocument,
    RegulatoryProvenance,
    RegulatorySection,
)
from app.services.chunking.outline_engine import RegulatoryOutlineEngine
from app.services.parsers.base_parser import BaseDocumentParser


def _local_tag(tag: str) -> str:
    """Extract local tag name by stripping XML namespaces."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


class XmlDocumentParser(BaseDocumentParser):
    """Deterministic parser for XML regulatory dossiers and SPL documents."""

    def __init__(self):
        self.outline_engine = RegulatoryOutlineEngine()

    def can_parse(
        self,
        content: Union[str, bytes],
        filename: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> bool:
        """Evaluate if content or filename indicates XML format."""
        if filename and filename.lower().endswith(".xml"):
            return True
        if mime_type and mime_type.lower() in ("application/xml", "text/xml"):
            return True

        text = self.decode_content(content).strip()
        lower = text.lower()
        if lower.startswith("<!doctype html") or "<html" in lower:
            return False

        if text.startswith("<?xml") or (text.startswith("<") and text.endswith(">")):
            try:
                # Quick verification that it is valid XML
                ET.fromstring(text)
                return True
            except Exception:
                return False
        return False

    def parse(
        self,
        content: Union[str, bytes],
        document_id: Optional[str] = None,
        document_name: Optional[str] = None,
        provenance: Optional[RegulatoryProvenance] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RegulatoryDocument:
        """Parse XML content into a structured RegulatoryDocument container."""
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
                title=doc_title or "Empty XML Document",
                document_type=doc_type,
                jurisdiction=jurisdiction,
                product_name=product,
                active_ingredient=drug,
                version=version,
                provenance=prov,
                sections=[],
                raw_content="",
            )

        try:
            root = ET.fromstring(clean_text)
        except Exception as exc:
            raise ValueError(f"Invalid XML content: {exc}") from exc

        # 1. Detect title from XML if not explicitly provided
        if not doc_title:
            doc_title = self._find_document_title(root) or "XML Regulatory Document"

        # 2. Detect product/drug if not provided
        if not product or not drug:
            inferred_prod, inferred_drug = self._infer_product_and_drug(root)
            product = product or inferred_prod
            drug = drug or inferred_drug

        # 3. Detect version or ID from root attributes or child elements
        root_id = root.attrib.get("id") or root.attrib.get("ID")
        if root_id and not document_id:
            doc_id = root_id
        if "version" in root.attrib:
            version = str(root.attrib["version"])

        # 4. Parse sections preserving hierarchy and element locations
        sections = self._parse_element_tree(root, doc_id)

        # Fallback if no sections were extracted
        if not sections:
            all_text = self._extract_clean_text(root)
            if all_text:
                sections.append(
                    RegulatorySection(
                        section_id=f"sec_{doc_id}_0_general",
                        heading_raw="General Content",
                        order_index=0,
                        raw_text=all_text,
                    )
                )

        return RegulatoryDocument(
            document_id=doc_id,
            title=doc_title,
            document_type=doc_type,
            jurisdiction=jurisdiction,
            product_name=product,
            active_ingredient=drug,
            version=str(version),
            provenance=prov,
            sections=sections,
            raw_content=raw_text,
        )

    def _find_document_title(self, root: ET.Element) -> Optional[str]:
        """Attempt to find document title from common XML locations."""
        # Check direct child or descendant title element
        for elem in root.iter():
            tag = _local_tag(elem.tag).lower()
            if tag in ("title", "document_title", "label_title") and elem.text and elem.text.strip():
                # Avoid section titles
                parent_tag = ""
                # If root or directly under root/header
                return elem.text.strip()
        # Check title attribute
        for attr in ("title", "name", "documentName"):
            if attr in root.attrib:
                return root.attrib[attr].strip()
        return None

    def _infer_product_and_drug(self, root: ET.Element) -> Tuple[Optional[str], Optional[Optional[str]]]:
        """Extract product and active ingredient names from known regulatory tags."""
        prod = None
        drug = None
        for elem in root.iter():
            tag = _local_tag(elem.tag).lower()
            text = "".join(elem.itertext()).strip()
            if not text:
                continue
            if tag in ("product", "product_name", "proprietaryname", "brand_name") and not prod:
                prod = text
            elif tag in ("active_ingredient", "substance_name", "generic_name", "nonproprietaryname", "drug") and not drug:
                drug = text
            if prod and drug:
                break
        return prod, drug

    def _parse_element_tree(self, root: ET.Element, doc_id: str) -> List[RegulatorySection]:
        """Identify structure: SPL/section-based vs generic hierarchical tags."""
        root_tag = _local_tag(root.tag).lower()
        root_path = f"/{_local_tag(root.tag)}"

        # Check if document has dedicated <section> elements (HL7 SPL or structured regulatory XML)
        section_elements = [el for el in root.iter() if _local_tag(el.tag).lower() == "section"]

        if section_elements:
            return self._parse_spl_or_structured_sections(root, doc_id, root_path)
        else:
            return self._parse_generic_xml_hierarchy(root, doc_id, root_path)

    def _parse_spl_or_structured_sections(
        self,
        root: ET.Element,
        doc_id: str,
        root_path: str,
    ) -> List[RegulatorySection]:
        """Parse structured sections preserving parent-child section nesting."""
        # Find top-level sections (sections that are not inside another section)
        sections: List[RegulatorySection] = []
        top_sections: List[ET.Element] = []

        def find_top_level_sections(elem: ET.Element):
            for child in elem:
                child_tag = _local_tag(child.tag).lower()
                if child_tag == "section":
                    top_sections.append(child)
                else:
                    find_top_level_sections(child)

        find_top_level_sections(root)

        for idx, sec_elem in enumerate(top_sections):
            sec = self._parse_section_node(
                sec_elem,
                doc_id=doc_id,
                order_index=idx,
                parent_path=root_path,
                parent_id=None,
            )
            if sec:
                sections.append(sec)

        return sections

    def _parse_section_node(
        self,
        sec_elem: ET.Element,
        doc_id: str,
        order_index: int,
        parent_path: str,
        parent_id: Optional[str] = None,
    ) -> Optional[RegulatorySection]:
        """Parse a single <section> element into a RegulatorySection, recursively handling subsections."""
        xpath = f"{parent_path}/section[{order_index + 1}]"
        attribs = dict(sec_elem.attrib)

        # 1. Extract heading and LOINC code
        heading_raw = None
        loinc_code = None
        sec_num = attribs.get("number") or attribs.get("section_number")

        # Check for child <code> element (SPL standard)
        code_elem = None
        for child in sec_elem:
            if _local_tag(child.tag).lower() == "code":
                code_elem = child
                break

        if code_elem is not None:
            heading_raw = code_elem.attrib.get("displayName")
            loinc_code = code_elem.attrib.get("code")

        # Check for child <title>
        title_elem = None
        for child in sec_elem:
            if _local_tag(child.tag).lower() == "title":
                title_elem = child
                break

        if title_elem is not None and title_elem.text:
            text_title = "".join(title_elem.itertext()).strip()
            if not heading_raw:
                heading_raw = text_title

        # Check attributes if still missing
        if not heading_raw:
            heading_raw = attribs.get("title") or attribs.get("heading") or attribs.get("name") or f"Section {order_index + 1}"

        # If heading starts with a section number (e.g. "4.2 Posology"), extract outline info
        heading_info = self.outline_engine.parse_heading(heading_raw, order_index=order_index)
        if heading_info and heading_info.section_number:
            sec_num = sec_num or heading_info.section_number
            norm_concept = heading_info.heading_normalized
        else:
            norm_concept = self.outline_engine.normalize_concept(heading_raw)

        # 2. Extract body text (excluding child <section> elements which become subsections)
        body_parts: List[str] = []
        nested_sections: List[RegulatorySection] = []
        sub_idx = 0

        sec_slug = re.sub(r'[^a-zA-Z0-9]', '_', (sec_num or heading_raw).lower())[:20]
        sec_id = f"sec_{doc_id}_{order_index}_{sec_slug}"

        # If ID attribute provided, store in metadata/id
        xml_id = attribs.get("ID") or attribs.get("id")

        for child in sec_elem:
            child_tag = _local_tag(child.tag).lower()
            if child_tag in ("code", "title"):
                continue
            elif child_tag == "section":
                # Subsection
                sub_sec = self._parse_section_node(
                    child,
                    doc_id=doc_id,
                    order_index=sub_idx,
                    parent_path=xpath,
                    parent_id=sec_id,
                )
                if sub_sec:
                    nested_sections.append(sub_sec)
                    sub_idx += 1
            else:
                # Text content container (e.g. <text>, <paragraph>, <table>, <list>, etc.)
                child_content = self._extract_clean_text(child)
                if child_content:
                    body_parts.append(child_content)

        raw_body = "\n\n".join(body_parts).strip()

        # Build RegulatorySection
        section = RegulatorySection(
            section_id=sec_id,
            parent_section_id=parent_id,
            section_number=str(sec_num) if sec_num else None,
            heading_raw=heading_raw,
            heading_normalized=norm_concept,
            order_index=order_index,
            loinc_code=loinc_code,
            raw_text=raw_body,
            subsections=nested_sections,
        )

        return section

    def _parse_generic_xml_hierarchy(
        self,
        root: ET.Element,
        doc_id: str,
        root_path: str,
    ) -> List[RegulatorySection]:
        """Parse arbitrary XML where child elements represent domain sections."""
        sections: List[RegulatorySection] = []
        order_idx = 0

        for child in root:
            child_tag = _local_tag(child.tag)
            tag_lower = child_tag.lower()

            # Skip metadata/header tags that aren't content sections
            if tag_lower in (
                "title", "version", "id", "metadata", "header",
                "product", "drug", "product_name", "active_ingredient",
                "jurisdiction", "document_type",
            ):
                continue

            xpath = f"{root_path}/{child_tag}[{order_idx + 1}]"
            attribs = dict(child.attrib)

            # Title from attribute or tag name
            title = attribs.get("title") or attribs.get("name")
            if not title:
                # Convert tag snake_case or camelCase to words
                title = re.sub(r'[_]+', ' ', child_tag).title()

            sec_num = attribs.get("number") or attribs.get("section_number")
            norm_concept = self.outline_engine.normalize_concept(title)

            # Check if this element has child elements with their own complex sub-trees
            has_complex_children = any(len(list(c)) > 0 for c in child) and not any(
                _local_tag(c.tag).lower() in ("paragraph", "p", "table", "list", "ul", "ol") for c in child
            )

            sec_slug = re.sub(r'[^a-zA-Z0-9]', '_', child_tag.lower())[:20]
            sec_id = f"sec_{doc_id}_{order_idx}_{sec_slug}"

            nested_subsections: List[RegulatorySection] = []
            if has_complex_children:
                sub_order = 0
                direct_body = []
                for sub_child in child:
                    sub_tag = _local_tag(sub_child.tag)
                    sub_xpath = f"{xpath}/{sub_tag}[{sub_order + 1}]"
                    sub_attribs = dict(sub_child.attrib)
                    sub_title = sub_attribs.get("title") or re.sub(r'[_]+', ' ', sub_tag).title()
                    sub_text = self._extract_clean_text(sub_child)

                    if sub_text:
                        sub_sec = RegulatorySection(
                            section_id=f"sec_{doc_id}_{order_idx}_{sub_order}_{sub_tag.lower()[:15]}",
                            parent_section_id=sec_id,
                            section_number=sub_attribs.get("number"),
                            heading_raw=sub_title,
                            heading_normalized=self.outline_engine.normalize_concept(sub_title),
                            order_index=sub_order,
                            raw_text=sub_text,
                        )
                        nested_subsections.append(sub_sec)
                        sub_order += 1
                body_text = "\n\n".join(direct_body).strip()
            else:
                body_text = self._extract_clean_text(child)

            if not body_text and not nested_subsections:
                continue

            sec = RegulatorySection(
                section_id=sec_id,
                section_number=str(sec_num) if sec_num else None,
                heading_raw=title,
                heading_normalized=norm_concept,
                order_index=order_idx,
                raw_text=body_text,
                subsections=nested_subsections,
            )
            sections.append(sec)
            order_idx += 1

        return sections

    def _extract_clean_text(self, elem: ET.Element) -> str:
        """Extract clean, structured text from an XML element preserving tables, lists, and paragraphs."""
        tag = _local_tag(elem.tag).lower()

        # Handle tables
        if tag == "table":
            return self._xml_table_to_markdown(elem)

        # Handle lists
        if tag in ("list", "ul", "ol"):
            return self._xml_list_to_markdown(elem)

        # Collect child blocks
        blocks: List[str] = []

        # If direct text
        if elem.text and elem.text.strip():
            blocks.append(elem.text.strip())

        for child in elem:
            c_tag = _local_tag(child.tag).lower()
            if c_tag == "table":
                md_table = self._xml_table_to_markdown(child)
                if md_table:
                    blocks.append(md_table)
            elif c_tag in ("list", "ul", "ol"):
                md_list = self._xml_list_to_markdown(child)
                if md_list:
                    blocks.append(md_list)
            elif c_tag in ("paragraph", "p"):
                p_text = " ".join("".join(child.itertext()).split())
                if p_text:
                    blocks.append(p_text)
            else:
                c_text = self._extract_clean_text(child)
                if c_text:
                    blocks.append(c_text)

            if child.tail and child.tail.strip():
                blocks.append(child.tail.strip())

        # If no blocks were built through children, fallback to itertext
        if not blocks:
            full_text = " ".join("".join(elem.itertext()).split())
            return full_text

        return "\n\n".join(blocks).strip()

    def _xml_table_to_markdown(self, table_elem: ET.Element) -> str:
        """Convert XML <table> element (HTML/SPL style) into Markdown table string."""
        rows: List[List[str]] = []
        for tr in table_elem.iter():
            if _local_tag(tr.tag).lower() == "tr":
                cells: List[str] = []
                for cell in tr:
                    if _local_tag(cell.tag).lower() in ("th", "td"):
                        cell_text = " ".join("".join(cell.itertext()).split())
                        cells.append(cell_text)
                if cells:
                    rows.append(cells)

        if not rows:
            return ""

        max_cols = max(len(r) for r in rows)
        if max_cols == 0:
            return ""

        # Normalize column counts
        for r in rows:
            while len(r) < max_cols:
                r.append("")

        header = rows[0]
        md_lines = ["| " + " | ".join(header) + " |"]
        md_lines.append("| " + " | ".join(["---"] * max_cols) + " |")
        for row in rows[1:]:
            md_lines.append("| " + " | ".join(row) + " |")

        return "\n".join(md_lines)

    def _xml_list_to_markdown(self, list_elem: ET.Element) -> str:
        """Convert XML <list>, <ul>, <ol> element into Markdown bullet/numbered list."""
        lines: List[str] = []
        is_ordered = _local_tag(list_elem.tag).lower() == "ol"
        idx = 1

        for child in list_elem:
            c_tag = _local_tag(child.tag).lower()
            if c_tag in ("item", "li"):
                item_text = " ".join("".join(child.itertext()).split())
                if item_text:
                    if is_ordered:
                        lines.append(f"{idx}. {item_text}")
                        idx += 1
                    else:
                        lines.append(f"* {item_text}")

        return "\n".join(lines)
