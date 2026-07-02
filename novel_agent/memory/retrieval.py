"""长期记忆的索引与召回：章节正文切块 → 向量化 → 入库 / 检索。"""

from __future__ import annotations

import re

from .embedder import Embedder
from .vector import Chunk, SearchHit, VectorStore


def split_chapter(text: str, *, target: int = 300, hard_max: int = 450) -> list[str]:
    """把一章正文按段落切成若干块，每块约 target 字。

    按段落聚合，尽量在段落边界切分，保持语义完整。
    块较小（~300字）以便召回时整块注入、粒度聚焦。
    """
    # 去掉标题行
    body = re.sub(r"^#.*\n", "", text).strip()
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]

    chunks: list[str] = []
    buf = ""
    for p in paras:
        if not buf:
            buf = p
        elif len(buf) + len(p) + 1 <= hard_max:
            buf += "\n" + p
        else:
            chunks.append(buf)
            buf = p
        if len(buf) >= target:
            chunks.append(buf)
            buf = ""
    if buf:
        chunks.append(buf)
    return chunks


def index_chapter(
    store: VectorStore,
    embedder: Embedder,
    *,
    chapter: int,
    text: str,
) -> int:
    """把一章切块、向量化并入库。返回入库的片段数。

    若该章已索引过（重写场景），先删旧片段再加新的。
    """
    store.remove_chapter(chapter)
    pieces = split_chapter(text)
    if not pieces:
        return 0
    chunks = [
        Chunk(id=f"ch{chapter}#{i}", chapter=chapter, text=piece)
        for i, piece in enumerate(pieces)
    ]
    vectors = embedder.embed([c.text for c in chunks])
    store.add(chunks, vectors)
    return len(chunks)


def recall_block(
    store: VectorStore,
    embedder: Embedder,
    *,
    query: str,
    before_chapter: int,
    exclude_recent: int = 3,
    top_k: int = 4,
    min_score: float = 0.3,
) -> str:
    """按 query 召回相关历史片段，组装成注入文本块。

    query 一般用"本章细纲"，召回语义相似的历史场景，保证细节一致。
    """
    if store.size == 0:
        return ""
    qvec = embedder.embed_one(query)
    hits = store.search(
        qvec,
        top_k=top_k,
        before_chapter=before_chapter,
        exclude_recent=exclude_recent,
    )
    hits = [h for h in hits if h.score >= min_score]
    if not hits:
        return ""

    lines = ["【相关历史片段（语义召回，供保持细节一致）】"]
    for h in hits:
        snippet = h.chunk.text.replace("\n", " ")
        lines.append(f"· [第{h.chunk.chapter}章] {snippet}")
    return "\n".join(lines)
