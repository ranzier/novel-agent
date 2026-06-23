"""长期记忆：向量库（语义召回历史片段）。

存储：每本书一个 vectors.npy（矩阵）+ vectors_meta.json（每行对应的元数据）。
检索：numpy 余弦相似度暴力检索。对单本书（几千段）足够快，零额外依赖、
不受 sqlite 扩展加载限制，Python 3.14 上稳定。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Chunk:
    """一个可检索的文本片段及其元数据。"""

    id: str              # 唯一 id，如 "ch3#2"
    chapter: int
    text: str
    kind: str = "chapter"  # chapter / summary 等


@dataclass
class SearchHit:
    chunk: Chunk
    score: float


class VectorStore:
    """基于 numpy 的本地向量库，按项目持久化。"""

    def __init__(self, vec_path: Path, meta_path: Path, dim: int):
        self.vec_path = vec_path
        self.meta_path = meta_path
        self.dim = dim
        self._vectors: np.ndarray | None = None
        self._meta: list[dict] = []
        self._load()

    def _load(self) -> None:
        if self.vec_path.exists() and self.meta_path.exists():
            self._vectors = np.load(self.vec_path)
            self._meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
        else:
            self._vectors = np.zeros((0, self.dim), dtype=np.float32)
            self._meta = []

    def _save(self) -> None:
        self.vec_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(self.vec_path, self._vectors)
        self.meta_path.write_text(
            json.dumps(self._meta, ensure_ascii=False), encoding="utf-8"
        )

    @property
    def size(self) -> int:
        return len(self._meta)

    def existing_chunk_ids(self) -> set[str]:
        return {m["id"] for m in self._meta}

    def chapters_indexed(self) -> set[int]:
        return {m["chapter"] for m in self._meta}

    def remove_chapter(self, chapter: int) -> None:
        """删除某章的所有片段（重写该章时先清旧的）。"""
        keep = [
            i for i, m in enumerate(self._meta) if m["chapter"] != chapter
        ]
        if len(keep) == len(self._meta):
            return
        self._vectors = (
            self._vectors[keep] if keep
            else np.zeros((0, self.dim), dtype=np.float32)
        )
        self._meta = [self._meta[i] for i in keep]
        self._save()

    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """添加片段及其向量。向量会做 L2 归一化以便用点积算余弦。"""
        if not chunks:
            return
        arr = np.asarray(vectors, dtype=np.float32)
        arr = _l2_normalize(arr)
        self._vectors = np.vstack([self._vectors, arr])
        for c in chunks:
            self._meta.append(
                {"id": c.id, "chapter": c.chapter, "text": c.text, "kind": c.kind}
            )
        self._save()

    def search(
        self,
        query_vec: list[float],
        *,
        top_k: int = 5,
        before_chapter: int | None = None,
        exclude_recent: int = 0,
    ) -> list[SearchHit]:
        """检索最相似的片段。

        before_chapter: 只在该章之前的片段里找（避免召回未来/当前章）
        exclude_recent: 额外排除最近这些章（它们已由短期记忆给原文）
        """
        if self.size == 0:
            return []
        q = _l2_normalize(np.asarray([query_vec], dtype=np.float32))[0]

        mask = np.ones(self.size, dtype=bool)
        if before_chapter is not None:
            cutoff = before_chapter - exclude_recent
            for i, m in enumerate(self._meta):
                if m["chapter"] >= cutoff:
                    mask[i] = False
        if not mask.any():
            return []

        sims = self._vectors @ q  # 余弦相似度（已归一化）
        sims = np.where(mask, sims, -np.inf)
        k = min(top_k, int(mask.sum()))
        top_idx = np.argpartition(-sims, k - 1)[:k]
        top_idx = top_idx[np.argsort(-sims[top_idx])]

        hits = []
        for i in top_idx:
            m = self._meta[i]
            hits.append(
                SearchHit(
                    chunk=Chunk(
                        id=m["id"], chapter=m["chapter"],
                        text=m["text"], kind=m.get("kind", "chapter"),
                    ),
                    score=float(sims[i]),
                )
            )
        return hits


def _l2_normalize(arr: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return arr / norms
