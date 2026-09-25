"""Base document parser interface module.

Defines the abstract interface and common utilities for format-specific regulatory parsers:
- TXT
- Markdown
- JSON
- XML
- HTML
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Union
from uuid import uuid4
from app.models.document import RegulatoryDocument, RegulatoryProvenance


class BaseDocumentParser(ABC):
    """Abstract base class for all format-specific regulatory document parsers."""

    @abstractmethod
    def can_parse(
        self,
        content: Union[str, bytes],
        filename: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> bool:
        """Evaluate whether this parser can process the given content, file extension, or MIME type."""
        pass

    @abstractmethod
    def parse(
        self,
        content: Union[str, bytes],
        document_id: Optional[str] = None,
        document_name: Optional[str] = None,
        provenance: Optional[RegulatoryProvenance] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RegulatoryDocument:
        """Parse raw content into a structured RegulatoryDocument container."""
        pass

    @staticmethod
    def decode_content(content: Union[str, bytes]) -> str:
        """Safely decode bytes or strings into a clean UTF-8 string."""
        if isinstance(content, str):
            return content
        if not isinstance(content, (bytes, bytearray)):
            return str(content)

        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return content.decode("latin-1")
            except Exception:
                return content.decode("utf-8", errors="replace")

    @staticmethod
    def default_provenance(
        source_repo: str = "InternalDraft",
        identifier: Optional[str] = None,
        url: Optional[str] = None,
    ) -> RegulatoryProvenance:
        """Construct standard fallback provenance without fabricating external data."""
        return RegulatoryProvenance(
            source_repository=source_repo,
            source_identifier=identifier,
            source_url=url,
        )
