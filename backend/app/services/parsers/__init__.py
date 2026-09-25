"""Multi-format regulatory document parsers package.

Provides deterministic parsers for:
1. Plain TXT (TextDocumentParser)
2. Markdown (MarkdownDocumentParser)
3. JSON (JsonDocumentParser)
4. XML (XmlDocumentParser)
5. HTML (HtmlDocumentParser)

All parsers normalize input formats into Phase 1 RegulatoryDocument and
RegulatorySection structures for consistent downstream outline analysis,
table extraction, and regulatory chunking.
"""

from typing import Any, Dict, List, Optional, Union

from app.models.document import RegulatoryDocument, RegulatoryProvenance
from app.services.parsers.base_parser import BaseDocumentParser
from app.services.parsers.docx_parser import DocxDocumentParser
from app.services.parsers.html_parser import HtmlDocumentParser
from app.services.parsers.json_parser import JsonDocumentParser
from app.services.parsers.markdown_parser import MarkdownDocumentParser
from app.services.parsers.pdf_parser import PdfDocumentParser
from app.services.parsers.txt_parser import TextDocumentParser
from app.services.parsers.xml_parser import XmlDocumentParser

__all__ = [
    "BaseDocumentParser",
    "TextDocumentParser",
    "MarkdownDocumentParser",
    "JsonDocumentParser",
    "XmlDocumentParser",
    "HtmlDocumentParser",
    "PdfDocumentParser",
    "DocxDocumentParser",
    "get_parser",
    "parse_regulatory_document",
]


def get_parser(
    content: Union[str, bytes] = "",
    filename: Optional[str] = None,
    mime_type: Optional[str] = None,
    raise_on_unsupported: bool = True,
) -> BaseDocumentParser:
    """Identify and return the appropriate parser instance for the given input.

    Evaluates file extension, MIME type, and content signatures in priority order:
    1. PDF
    2. DOCX
    3. JSON
    4. HTML
    5. XML
    6. Markdown
    7. Plain TXT
    """
    parsers: List[BaseDocumentParser] = [
        PdfDocumentParser(),
        DocxDocumentParser(),
        JsonDocumentParser(),
        HtmlDocumentParser(),
        XmlDocumentParser(),
        MarkdownDocumentParser(),
        TextDocumentParser(),
    ]

    for parser in parsers:
        if parser.can_parse(content, filename=filename, mime_type=mime_type):
            return parser

    if raise_on_unsupported:
        ext = f".{filename.rsplit('.', 1)[-1]}" if filename and "." in filename else None
        target = ext or filename or mime_type or "unrecognized content"
        raise ValueError(f"Unsupported document format: {target}")

    # Fallback to plain text parser if raise_on_unsupported=False
    return TextDocumentParser()


def parse_regulatory_document(
    content: Union[str, bytes],
    filename: Optional[str] = None,
    mime_type: Optional[str] = None,
    document_id: Optional[str] = None,
    document_name: Optional[str] = None,
    provenance: Optional[RegulatoryProvenance] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> RegulatoryDocument:
    """Convenience function to parse any supported format into a RegulatoryDocument."""
    parser = get_parser(content, filename=filename, mime_type=mime_type)
    return parser.parse(
        content=content,
        document_id=document_id,
        document_name=document_name,
        provenance=provenance,
        metadata=metadata,
    )
