"""Chunking and outline recognition sub-package for regulatory content.

Provides:
- RegulatorySentenceTokenizer: deterministic, abbreviation-safe sentence splitter
- RegulatoryOutlineEngine: multi-jurisdictional heading and numbered section detector
- RegulatoryTableExtractor: Markdown, HTML, and TSV table extractor
- RegulatoryBulletExtractor: bullet and ordered list group extractor
"""

from app.services.chunking.outline_engine import (
    HeadingInfo,
    ListItemInfo,
    RegulatoryOutlineEngine,
)
from app.services.chunking.regulatory_chunker import RegulatoryChunker
from app.services.chunking.sentence_tokenizer import RegulatorySentenceTokenizer
from app.services.chunking.table_extractor import (
    HTMLTableParser,
    RegulatoryBulletExtractor,
    RegulatoryTableExtractor,
)

__all__ = [
    "RegulatorySentenceTokenizer",
    "RegulatoryOutlineEngine",
    "HeadingInfo",
    "ListItemInfo",
    "RegulatoryTableExtractor",
    "RegulatoryBulletExtractor",
    "HTMLTableParser",
    "RegulatoryChunker",
]

