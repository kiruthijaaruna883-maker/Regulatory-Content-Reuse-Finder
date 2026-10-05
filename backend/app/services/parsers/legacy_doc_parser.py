"""Legacy Microsoft Word (.doc) regulatory document parser.

Parses legacy Word 97-2003 (.doc) binary Compound Document files using olefile,
extracting document text, preserving paragraph boundaries and heading hierarchy,
and returning a standardized RegulatoryDocument container compatible with downstream
regulatory chunking and candidate discovery.
"""

import io
import logging
import re
import struct
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4

import olefile

from app.models.document import (
    RegulatoryDocument,
    RegulatoryProvenance,
    RegulatorySection,
)
from app.services.chunking.outline_engine import HeadingInfo, RegulatoryOutlineEngine
from app.services.parsers.base_parser import BaseDocumentParser

logger = logging.getLogger("legacy_doc_parser")

# Standard OLE Compound File Binary Format magic signature
OLE_HEADER_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

# Known Word MIME types
WORD_MIME_TYPES = (
    "application/msword",
    "application/vnd.ms-word",
    "application/x-msword",
    "application/doc",
)


class LegacyDocDocumentParser(BaseDocumentParser):
    """Deterministic, read-only parser for legacy Microsoft Word (.doc) documents."""

    def __init__(self):
        self.outline_engine = RegulatoryOutlineEngine()

    def can_parse(
        self,
        content: Union[str, bytes],
        filename: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> bool:
        """Evaluate if content, filename, or MIME type indicates a legacy .doc Word document."""
        # 1. Filename extension matching (explicitly .doc, not .docx)
        if filename:
            lower_name = filename.lower()
            if lower_name.endswith(".doc") and not lower_name.endswith(".docx"):
                return True

        # 2. MIME type matching
        if mime_type and mime_type.lower() in WORD_MIME_TYPES:
            return True

        # 3. Content signature inspection: OLE magic header and WordDocument stream
        raw_b = self._to_bytes(content)
        if raw_b.startswith(OLE_HEADER_MAGIC) and len(raw_b) >= 512:
            try:
                if olefile.isOleFile(io.BytesIO(raw_b)):
                    with olefile.OleFileIO(io.BytesIO(raw_b)) as ole:
                        return ole.exists("WordDocument")
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
        """Parse legacy .doc binary content into a structured RegulatoryDocument."""
        doc_bytes = self._to_bytes(content)

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

        # Handle empty document content gracefully
        if not doc_bytes or len(doc_bytes.strip()) == 0:
            prov.exact_location = "Paragraphs: 0, Tables: 0"
            return RegulatoryDocument(
                document_id=doc_id,
                title=doc_title or "Empty DOC Document",
                document_type=doc_type,
                jurisdiction=jurisdiction,
                product_name=product,
                active_ingredient=drug,
                version=version,
                provenance=prov,
                sections=[],
                raw_content="",
            )

        # Validate that the file is an OLE compound document
        if not doc_bytes.startswith(OLE_HEADER_MAGIC) or not olefile.isOleFile(io.BytesIO(doc_bytes)):
            raise ValueError("The Word document could not be read. Please verify that it is a valid legacy .DOC file.")

        # Read OLE streams passively and extract text
        try:
            with olefile.OleFileIO(io.BytesIO(doc_bytes)) as ole:
                if not ole.exists("WordDocument"):
                    raise ValueError(
                        "The Word document could not be read. Please verify that it is a valid legacy .DOC file."
                    )

                # Try to extract title from OLE SummaryInformation metadata if not provided
                if not doc_title:
                    try:
                        ole_meta = ole.get_metadata()
                        if ole_meta and ole_meta.title and ole_meta.title.strip():
                            doc_title = ole_meta.title.strip()
                    except Exception:
                        pass

                raw_extracted_text = self._extract_word_document_text(ole)

        except ValueError:
            raise
        except Exception as exc:
            logger.error("Failed to read OLE compound document: %s", exc)
            raise ValueError(
                "The Word document could not be read. Please verify that it is a valid legacy .DOC file."
            ) from exc

        if not doc_title:
            doc_title = "Legacy DOC Regulatory Document"

        # Clean and split into normalized paragraphs
        cleaned_paragraphs = self._split_paragraphs(raw_extracted_text)

        # Segment paragraphs into sections using RegulatoryOutlineEngine
        raw_sections_data: List[Dict[str, Any]] = []
        current_heading_info: Optional[HeadingInfo] = None
        current_heading_level: int = 1
        current_body_lines: List[str] = []
        order_idx = 0
        paragraph_count = 0

        for p_text in cleaned_paragraphs:
            if not p_text:
                continue

            paragraph_count += 1
            is_heading, level = self._detect_heading(p_text, order_idx)

            if is_heading:
                # Flush previous accumulated section
                if current_heading_info or current_body_lines:
                    sec_dict = self._package_raw_section(
                        heading_info=current_heading_info,
                        level=current_heading_level,
                        body_lines=current_body_lines,
                        order_index=order_idx,
                    )
                    raw_sections_data.append(sec_dict)
                    order_idx += 1
                    current_body_lines = []

                heading_info = self.outline_engine.parse_heading(p_text, order_index=order_idx)
                if not heading_info:
                    heading_info = HeadingInfo(
                        heading_raw=p_text,
                        heading_normalized=self.outline_engine.normalize_concept(p_text),
                        level=level,
                        order_index=order_idx,
                    )
                current_heading_info = heading_info
                current_heading_level = level
            else:
                current_body_lines.append(p_text)

        # Flush final remaining section
        if current_heading_info or current_body_lines:
            sec_dict = self._package_raw_section(
                heading_info=current_heading_info,
                level=current_heading_level,
                body_lines=current_body_lines,
                order_index=order_idx,
            )
            raw_sections_data.append(sec_dict)

        # Build hierarchical sections tree
        root_sections = self._build_hierarchical_sections(raw_sections_data, doc_id)

        # If title is still generic and first section is Level 1, infer title from heading
        if doc_title == "Legacy DOC Regulatory Document" and raw_sections_data and raw_sections_data[0]["level"] == 1:
            doc_title = raw_sections_data[0]["heading_raw"]

        # Reconstruct raw content for traceability
        all_blocks = []
        for s in raw_sections_data:
            block = f"## {s['heading_raw']}\n{s['raw_text']}"
            all_blocks.append(block)
        combined_raw = "\n\n".join(all_blocks) if all_blocks else raw_extracted_text.strip()

        prov.exact_location = f"Paragraphs: {paragraph_count}, Sections: {len(raw_sections_data)}"

        return RegulatoryDocument(
            document_id=doc_id,
            title=doc_title,
            document_type=doc_type,
            jurisdiction=jurisdiction,
            product_name=product,
            active_ingredient=drug,
            version=version,
            provenance=prov,
            sections=root_sections,
            raw_content=combined_raw,
        )

    def _extract_word_document_text(self, ole: olefile.OleFileIO) -> str:
        """Extract text runs from the WordDocument stream and piece table (Plcfpcd)."""
        word_stream = ole.openstream("WordDocument").read()
        if len(word_stream) < 68:
            return ""

        # Flags at offset 0x0A indicate whether 0Table or 1Table is used
        flags = struct.unpack_from("<H", word_stream, 0x0A)[0]
        f_which_tbl_stm = (flags & 0x0200) != 0
        tbl_stream_name = "1Table" if f_which_tbl_stm else "0Table"

        table_stream = b""
        if ole.exists(tbl_stream_name):
            try:
                table_stream = ole.openstream(tbl_stream_name).read()
            except Exception as exc:
                logger.debug("Could not read %s: %s", tbl_stream_name, exc)

        # 1. Attempt piece table extraction from Table stream (standard for Word 97-2003)
        if table_stream and len(word_stream) >= 426:
            try:
                fc_clx = struct.unpack_from("<I", word_stream, 0x01A2)[0]
                lcb_clx = struct.unpack_from("<I", word_stream, 0x01A6)[0]

                if 0 <= fc_clx < len(table_stream) and lcb_clx > 0:
                    clx = table_stream[fc_clx : min(len(table_stream), fc_clx + lcb_clx)]
                    text = self._parse_clx_piece_table(clx, word_stream)
                    if text and text.strip():
                        return text
            except Exception as exc:
                logger.debug("Piece table extraction exception: %s", exc)

        # 2. Fallback to File Information Block (FIB) text offsets (Word 6/95 or non-complex)
        if len(word_stream) >= 80:
            try:
                fc_min = struct.unpack_from("<I", word_stream, 0x18)[0]
                ccp_text = struct.unpack_from("<I", word_stream, 0x4C)[0]

                if 0 < fc_min < len(word_stream) and ccp_text > 0:
                    # Try UTF-16LE first
                    raw_slice = word_stream[fc_min : min(len(word_stream), fc_min + ccp_text * 2)]
                    try:
                        decoded = raw_slice.decode("utf-16le")
                        if self._is_mostly_readable(decoded):
                            return decoded
                    except Exception:
                        pass

                    # Try ANSI / cp1252
                    raw_slice_ansi = word_stream[fc_min : min(len(word_stream), fc_min + ccp_text)]
                    decoded_ansi = raw_slice_ansi.decode("cp1252", errors="replace")
                    if self._is_mostly_readable(decoded_ansi):
                        return decoded_ansi
            except Exception as exc:
                logger.debug("FIB direct text extraction exception: %s", exc)

        # 3. Fallback to scanning readable text runs across the entire WordDocument stream
        return self._extract_fallback_text_runs(word_stream)

    @staticmethod
    def _parse_clx_piece_table(clx: bytes, word_stream: bytes) -> str:
        """Parse Clx structure to extract text pieces (both compressed ANSI and UTF-16LE)."""
        offset = 0
        text_pieces: List[str] = []

        while offset < len(clx):
            clxt = clx[offset]

            if clxt == 0x01:  # Prc (property modifier)
                offset += 1
                if offset + 2 > len(clx):
                    break
                cb_grpprl = struct.unpack_from("<H", clx, offset)[0]
                offset += 2 + cb_grpprl

            elif clxt == 0x02:  # Plcfpcd (Piece Table)
                offset += 1
                if offset + 4 > len(clx):
                    break
                lcb = struct.unpack_from("<I", clx, offset)[0]
                offset += 4

                # Plcfpcd structure: (n + 1) CPs (4 bytes each) followed by n PCDs (8 bytes each)
                # lcb = 4 + 12 * n
                n = (lcb - 4) // 12
                if n <= 0 or offset + (n + 1) * 4 + n * 8 > len(clx):
                    break

                cp_array = [struct.unpack_from("<I", clx, offset + i * 4)[0] for i in range(n + 1)]
                pcd_offset = offset + (n + 1) * 4

                for i in range(n):
                    # PCD byte 2..5 is FcCompressed (uint32)
                    fc = struct.unpack_from("<I", clx, pcd_offset + i * 8 + 2)[0]
                    cp_len = cp_array[i + 1] - cp_array[i]
                    if cp_len <= 0:
                        continue

                    f_compressed = (fc & 0x40000000) != 0
                    actual_fc = fc & ~0x40000000

                    if f_compressed:
                        # 8-bit ANSI / Latin-1 text
                        file_offset = actual_fc // 2
                        raw_piece = word_stream[file_offset : file_offset + cp_len]
                        text_pieces.append(raw_piece.decode("cp1252", errors="replace"))
                    else:
                        # 16-bit UTF-16LE text
                        file_offset = actual_fc
                        raw_piece = word_stream[file_offset : file_offset + cp_len * 2]
                        text_pieces.append(raw_piece.decode("utf-16le", errors="replace"))

                break
            else:
                break

        return "".join(text_pieces)

    @staticmethod
    def _extract_fallback_text_runs(stream_bytes: bytes) -> str:
        """Scan raw stream for printable text runs if piece table cannot be resolved."""
        # Check for contiguous UTF-16LE strings (runs of 4+ characters)
        runs: List[str] = []
        utf16_pattern = re.compile(b"((?:[\x20-\x7e\x09\x0a\x0d]\x00){4,})")
        for match in utf16_pattern.finditer(stream_bytes):
            try:
                decoded = match.group(1).decode("utf-16le", errors="ignore")
                if len(decoded.strip()) >= 3:
                    runs.append(decoded)
            except Exception:
                pass

        if runs:
            return "\n".join(runs)

        # Check for contiguous ASCII/ANSI strings (runs of 5+ characters)
        ascii_pattern = re.compile(b"([\x20-\x7e\x09\x0a\x0d]{5,})")
        for match in ascii_pattern.finditer(stream_bytes):
            try:
                decoded = match.group(1).decode("latin-1", errors="ignore")
                if len(decoded.strip()) >= 4:
                    runs.append(decoded)
            except Exception:
                pass

        return "\n".join(runs)

    @staticmethod
    def _is_mostly_readable(text: str) -> bool:
        """Verify that string contains predominantly printable characters."""
        if not text or len(text.strip()) == 0:
            return False
        printable = sum(1 for c in text if c.isprintable() or c in "\r\n\t")
        return (printable / len(text)) > 0.75

    @staticmethod
    def _split_paragraphs(text: str) -> List[str]:
        """Normalize Word carriage returns and table delimiters into clean paragraph lines."""
        if not text:
            return []

        # Replace Word table cell delimiters (0x07) with column separators
        normalized = text.replace("\x07", " | ")
        # Replace Word soft breaks and page breaks
        normalized = normalized.replace("\x0b", "\n").replace("\x0c", "\n\n")
        # Replace Word paragraph breaks (\r\n or \r) with standard \n
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")

        # Filter out non-printable control characters except \t and \n
        cleaned_chars = []
        for ch in normalized:
            if ord(ch) >= 32 or ch in ("\n", "\t"):
                cleaned_chars.append(ch)
            else:
                cleaned_chars.append(" ")
        cleaned = "".join(cleaned_chars)

        # Split on newlines and trim whitespace
        lines = [line.strip() for line in cleaned.split("\n")]
        return [l for l in lines if l]

    def _detect_heading(self, text: str, order_idx: int) -> Tuple[bool, int]:
        """Detect whether text represents a regulatory heading based on outline numbering or concept patterns."""
        heading_info = self.outline_engine.parse_heading(text, order_index=order_idx)
        if heading_info and heading_info.section_number:
            level = heading_info.level or 1
            return True, level

        # Check common top-level all-caps clinical section titles (e.g. INDICATIONS AND USAGE)
        clean_upper = text.strip().upper()
        norm_concept = self.outline_engine.normalize_concept(clean_upper)
        if norm_concept and (text.isupper() or len(text.split()) <= 6):
            return True, 1

        return False, 1

    @staticmethod
    def _package_raw_section(
        heading_info: Optional[HeadingInfo],
        level: int,
        body_lines: List[str],
        order_index: int,
    ) -> Dict[str, Any]:
        """Bundle section attributes into intermediate dictionary."""
        title = heading_info.heading_raw if heading_info else "General Content"
        sec_num = heading_info.section_number if heading_info else None
        norm = heading_info.heading_normalized if heading_info else None
        body = "\n\n".join(b for b in body_lines if b).strip()

        return {
            "heading_raw": title,
            "section_number": sec_num,
            "heading_normalized": norm,
            "level": level,
            "raw_text": body,
            "order_index": order_index,
        }

    def _build_hierarchical_sections(
        self,
        raw_sections_data: List[Dict[str, Any]],
        doc_id: str,
    ) -> List[RegulatorySection]:
        """Convert list of section dictionaries into nested RegulatorySection hierarchy."""
        if not raw_sections_data:
            return []

        root_sections: List[RegulatorySection] = []
        stack: List[Tuple[int, RegulatorySection]] = []

        for data in raw_sections_data:
            level = data["level"]
            sec_num = data["section_number"]
            title = data["heading_raw"]
            sec_slug = re.sub(r"[^a-zA-Z0-9]", "_", (sec_num or title).lower())[:20]
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

    @staticmethod
    def _to_bytes(content: Union[str, bytes]) -> bytes:
        """Safely convert string or bytes input to raw bytes."""
        if isinstance(content, (bytes, bytearray)):
            return bytes(content)
        if isinstance(content, str):
            try:
                return content.encode("latin-1")
            except Exception:
                return content.encode("utf-8", errors="replace")
        return bytes(content)
