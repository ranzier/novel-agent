"""项目管理：一本书 = 一个自包含目录。

负责目录布局、各产物（设定圣经 / 角色库 / 大纲 / 正文）的读写与定位。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .bible import Bible, CharacterBook
from .config import BOOKS_DIR
from .generate.outline_models import Outline
from .memory.state_models import ChapterSummary, WorldState
from .storage import read_json, write_json


def slugify(name: str) -> str:
    """把书名转成安全的目录名；中文保留。"""
    s = name.strip().replace(" ", "_")
    s = re.sub(r"[^\w一-鿿_-]", "", s)
    return s or "untitled"


@dataclass
class Project:
    """一本书的项目。"""

    slug: str
    root: Path

    # ---- 工厂 ----
    @classmethod
    def create(cls, title: str, books_dir: Path = BOOKS_DIR) -> "Project":
        slug = slugify(title)
        root = books_dir / slug
        root.mkdir(parents=True, exist_ok=True)
        (root / "chapters").mkdir(exist_ok=True)
        (root / "summaries").mkdir(exist_ok=True)
        return cls(slug=slug, root=root)

    @classmethod
    def open(cls, slug: str, books_dir: Path = BOOKS_DIR) -> "Project":
        root = books_dir / slug
        if not root.exists():
            raise FileNotFoundError(f"项目不存在：{root}")
        return cls(slug=slug, root=root)

    @classmethod
    def list_all(cls, books_dir: Path = BOOKS_DIR) -> list[str]:
        if not books_dir.exists():
            return []
        return sorted(
            p.name for p in books_dir.iterdir()
            if p.is_dir() and (p / "bible.json").exists()
        )

    # ---- 路径 ----
    @property
    def bible_path(self) -> Path:
        return self.root / "bible.json"

    @property
    def characters_path(self) -> Path:
        return self.root / "characters.json"

    @property
    def outline_path(self) -> Path:
        return self.root / "outline.json"

    @property
    def state_path(self) -> Path:
        return self.root / "state.json"

    @property
    def summaries_path(self) -> Path:
        return self.summaries_dir / "chapters.json"

    @property
    def reviews_path(self) -> Path:
        return self.root / "reviews.json"

    @property
    def vectors_path(self) -> Path:
        return self.root / "vectors.npy"

    @property
    def vectors_meta_path(self) -> Path:
        return self.root / "vectors_meta.json"

    @property
    def chapters_dir(self) -> Path:
        return self.root / "chapters"

    @property
    def summaries_dir(self) -> Path:
        return self.root / "summaries"

    def chapter_path(self, index: int) -> Path:
        return self.chapters_dir / f"ch{index:04d}.md"

    # ---- 设定圣经 ----
    def has_bible(self) -> bool:
        return self.bible_path.exists()

    def load_bible(self) -> Bible:
        return Bible.from_dict(read_json(self.bible_path))

    def save_bible(self, bible: Bible) -> None:
        write_json(self.bible_path, bible)

    # ---- 角色库 ----
    def load_characters(self) -> CharacterBook:
        if not self.characters_path.exists():
            return CharacterBook()
        return CharacterBook.from_dict(read_json(self.characters_path))

    def save_characters(self, book: CharacterBook) -> None:
        write_json(self.characters_path, book)

    # ---- 大纲 ----
    def has_outline(self) -> bool:
        return self.outline_path.exists()

    def load_outline(self) -> Outline:
        return Outline.from_dict(read_json(self.outline_path))

    def save_outline(self, outline: Outline) -> None:
        write_json(self.outline_path, outline)

    # ---- 世界状态 + 章节摘要（中期记忆）----
    def load_state(self) -> WorldState:
        if not self.state_path.exists():
            return WorldState()
        return WorldState.from_dict(read_json(self.state_path))

    def save_state(self, state: WorldState) -> None:
        write_json(self.state_path, state)

    def load_summaries(self) -> list[ChapterSummary]:
        if not self.summaries_path.exists():
            return []
        data = read_json(self.summaries_path)
        return [ChapterSummary.from_dict(d) for d in data]

    def save_summaries(self, summaries: list[ChapterSummary]) -> None:
        write_json(self.summaries_path, summaries)

    def upsert_summary(self, summary: ChapterSummary) -> None:
        """新增或替换某章摘要，按章节号保持有序。"""
        summaries = [s for s in self.load_summaries() if s.index != summary.index]
        summaries.append(summary)
        summaries.sort(key=lambda s: s.index)
        self.save_summaries(summaries)

    def save_review(self, review_dict: dict) -> None:
        """记录某章的校验结果（按章节号覆盖）。"""
        chapter = review_dict.get("chapter")
        existing = []
        if self.reviews_path.exists():
            existing = [
                r for r in read_json(self.reviews_path)
                if r.get("chapter") != chapter
            ]
        existing.append(review_dict)
        existing.sort(key=lambda r: r.get("chapter", 0))
        write_json(self.reviews_path, existing)

    def vector_store(self, dim: int):
        """打开本项目的向量库。"""
        from .memory import VectorStore

        return VectorStore(self.vectors_path, self.vectors_meta_path, dim)

    # ---- 正文 ----
    def write_chapter(self, index: int, text: str) -> Path:
        path = self.chapter_path(index)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def read_chapter(self, index: int) -> str | None:
        path = self.chapter_path(index)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def existing_chapter_indices(self) -> list[int]:
        out = []
        for p in self.chapters_dir.glob("ch*.md"):
            m = re.match(r"ch(\d+)\.md", p.name)
            if m:
                out.append(int(m.group(1)))
        return sorted(out)
