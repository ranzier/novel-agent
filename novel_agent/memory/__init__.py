"""记忆系统：短期(近章原文) / 中期(摘要+状态) / 长期(向量召回)。

短期 + 中期 + 写后固化(抽取) + 长期向量召回均已接入。知识图谱在后续步骤。
"""

from .short_term import recent_context, RecentContext
from .mid_term import mid_term_block
from .state_models import ChapterSummary, CharacterState, WorldState
from .extractor import consolidate
from .embedder import Embedder, EmbedError
from .vector import VectorStore, Chunk, SearchHit
from .retrieval import split_chapter, index_chapter, recall_block
from .promote import promote_characters

__all__ = [
    "recent_context",
    "RecentContext",
    "mid_term_block",
    "ChapterSummary",
    "CharacterState",
    "WorldState",
    "consolidate",
    "Embedder",
    "EmbedError",
    "VectorStore",
    "Chunk",
    "SearchHit",
    "split_chapter",
    "index_chapter",
    "recall_block",
    "promote_characters",
]
