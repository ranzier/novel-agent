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
from .storage import read_json, write_json, write_text


# 新建书时写入的默认写作风格模板：自由结构，值为通用建议，供用户按书改写。
DEFAULT_STYLE: dict = {
    "整体基调": "",
    "文笔风格": "清楚连贯、简洁明快，少堆砌辞藻，不为展示文笔而延长描写",
    "叙事节奏": "剧情推进优先，每章必须发生有效事件并改变局势、信息或人物关系",
    "对话风格": "口语自然，符合人设，避免书面腔",
    "描写原则": "环境、外貌、衣着、感官和心理只写影响当前情节的关键点，通常一两句带过",
    "内容侧重": ["人物行动与选择", "冲突升级与结果", "有效信息揭示", "关系变化"],
    "禁忌": ["大段静态场景或外貌描写", "无意义的长段心理独白", "为凑字数拆解动作或反复渲染情绪"],
    "建议技巧": ["用行动和对话塑造人物", "让每个场景产生剧情变化", "章末留钩子"],
    "备注": "",
}


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

    def delete(self, books_dir: Path = BOOKS_DIR) -> None:
        """彻底删除本书的整个目录（不可逆）。

        安全校验：root 必须确实位于 books_dir 之下，且不等于 books_dir 本身，
        防止配置异常时误删其它路径。
        """
        import shutil

        root = self.root.resolve()
        base = books_dir.resolve()
        if base not in root.parents or root == base:
            raise RuntimeError(f"拒绝删除：{root} 不在书库目录内")
        if root.exists():
            shutil.rmtree(root)

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
    def style_path(self) -> Path:
        return self.root / "style.json"

    @property
    def notes_path(self) -> Path:
        return self.root / "notes.json"

    @property
    def legacy_notes_path(self) -> Path:
        return self.root / "notes.md"

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

    # ---- 写作风格（自由结构 JSON）----
    def has_style(self) -> bool:
        return self.style_path.exists()

    def load_style(self) -> dict:
        """读取本书写作风格约束/建议。文件不存在返回空 dict（向后兼容旧书）。"""
        if not self.style_path.exists():
            return {}
        data = read_json(self.style_path)
        return data if isinstance(data, dict) else {}

    def save_style(self, style: dict) -> None:
        write_json(self.style_path, style)

    # ---- 作者笔记（多份，纯文本内容，不参与写作）----
    def load_notes(self) -> list[dict]:
        """读取作者笔记列表。每条为 {id, title, content, updated_at}。

        兼容迁移：若不存在 notes.json 但存在旧的 notes.md，则把旧单份笔记
        转成列表里的一条返回（不落盘，首次保存时自然写成新格式）。
        """
        if self.notes_path.exists():
            data = read_json(self.notes_path)
            return data if isinstance(data, list) else []
        # 迁移旧的单份 notes.md
        if self.legacy_notes_path.exists():
            old = self.legacy_notes_path.read_text(encoding="utf-8")
            if old.strip():
                return [{
                    "id": "legacy",
                    "title": "笔记",
                    "content": old,
                    "updated_at": "",
                }]
        return []

    def save_notes(self, notes: list[dict]) -> None:
        write_json(self.notes_path, notes)

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

    def sync_outline_from_summary(self, summary: ChapterSummary) -> bool:
        """用写后抽取的章节摘要回写大纲细纲，使大纲反映实际写出的内容。

        正文可能偏离原细纲（尤其作者注入思路后），这里把该章的
        summary/characters 同步成实际内容。title/goal/hook/cool_point 不动
        （它们是规划意图，保留）。返回是否有改动。
        """
        if not self.has_outline() or summary is None:
            return False
        outline = self.load_outline()
        ch = outline.chapter(summary.index)
        if ch is None:
            return False
        changed = False
        if summary.summary and summary.summary != ch.summary:
            ch.summary = summary.summary
            changed = True
        if summary.characters and summary.characters != ch.characters:
            ch.characters = list(summary.characters)
            changed = True
        if changed:
            self.save_outline(outline)
        return changed

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
        write_text(path, text)
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

    def delete_chapter(self, index: int) -> None:
        """删除某章正文，并清理与之绑定的记忆产物（摘要 / 校验 / 世界状态）。

        向量库片段由调用方（需 Embedder 拿到 dim）另行清理，这里不依赖 embedding。
        world state 是快照而非逐章历史：仅把 last_chapter 回退到剩余最大章号，
        其它字段维持现状（重写该章时 consolidate 会基于 prev_state 重算）。
        """
        # 1) 正文
        self.chapter_path(index).unlink(missing_ok=True)

        # 2) 章节摘要
        summaries = [s for s in self.load_summaries() if s.index != index]
        self.save_summaries(summaries)

        # 3) 校验记录
        if self.reviews_path.exists():
            kept = [
                r for r in read_json(self.reviews_path)
                if r.get("chapter") != index
            ]
            write_json(self.reviews_path, kept)

        # 4) 世界状态快照：回退 last_chapter
        state = self.load_state()
        if state.last_chapter == index:
            remaining = self.existing_chapter_indices()
            state.last_chapter = max(remaining) if remaining else 0
            self.save_state(state)
