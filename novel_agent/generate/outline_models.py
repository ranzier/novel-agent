"""分层大纲数据模型：全书主线 → 卷 → 章节细纲。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChapterOutline:
    """单章细纲。"""

    index: int                       # 全书章节序号，从 1 开始
    title: str = ""
    summary: str = ""               # 本章主要情节
    goal: str = ""                  # 本章要达成的叙事目的
    hook: str = ""                  # 章末钩子
    characters: list[str] = field(default_factory=list)  # 出场角色
    cool_point: str = ""            # 爽点（如有）

    @classmethod
    def from_dict(cls, d: dict) -> "ChapterOutline":
        d = d or {}
        return cls(
            index=int(d.get("index", 0)),
            title=d.get("title", ""),
            summary=d.get("summary", ""),
            goal=d.get("goal", ""),
            hook=d.get("hook", ""),
            characters=list(d.get("characters", [])),
            cool_point=d.get("cool_point", ""),
        )


@dataclass
class Volume:
    """卷 / 篇章弧。"""

    index: int                       # 卷序号，从 1 开始
    title: str = ""
    arc: str = ""                    # 本卷弧光 / 核心情节
    goal: str = ""                   # 本卷要推进的主线目标
    climax: str = ""                 # 本卷高潮
    start_tier: str = ""            # 卷初主角境界
    end_tier: str = ""              # 卷末主角境界
    chapters: list[ChapterOutline] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Volume":
        d = d or {}
        return cls(
            index=int(d.get("index", 0)),
            title=d.get("title", ""),
            arc=d.get("arc", ""),
            goal=d.get("goal", ""),
            climax=d.get("climax", ""),
            start_tier=d.get("start_tier", ""),
            end_tier=d.get("end_tier", ""),
            chapters=[
                ChapterOutline.from_dict(c)
                for c in d.get("chapters", [])
                if isinstance(c, dict)
            ],
        )


@dataclass
class Outline:
    """分层大纲。

    - arc_plan：骨架的卷级弧光规划（仅作方向参考，不存章节）。
    - volumes：实际承载章节的卷，每个 = 一个滑动窗口生成的批次，按时间顺序追加。
    """

    premise: str = ""                # 全书核心立意
    main_plot: str = ""             # 全书主线（开端→发展→高潮→结局）
    themes: list[str] = field(default_factory=list)
    ending: str = ""                # 结局走向
    arc_plan: list[Volume] = field(default_factory=list)  # 骨架弧光（参考）
    volumes: list[Volume] = field(default_factory=list)   # 承载章节的卷

    @classmethod
    def from_dict(cls, d: dict) -> "Outline":
        d = d or {}
        return cls(
            premise=d.get("premise", ""),
            main_plot=d.get("main_plot", ""),
            themes=list(d.get("themes", [])),
            ending=d.get("ending", ""),
            arc_plan=[
                Volume.from_dict(v)
                for v in d.get("arc_plan", [])
                if isinstance(v, dict)
            ],
            volumes=[
                Volume.from_dict(v)
                for v in d.get("volumes", [])
                if isinstance(v, dict)
            ],
        )

    def all_chapters(self) -> list[ChapterOutline]:
        out: list[ChapterOutline] = []
        for v in self.volumes:
            out.extend(v.chapters)
        return out

    def chapter(self, index: int) -> ChapterOutline | None:
        for c in self.all_chapters():
            if c.index == index:
                return c
        return None

    def max_chapter_index(self) -> int:
        """已规划到第几章；无则 0。"""
        idxs = [c.index for c in self.all_chapters()]
        return max(idxs) if idxs else 0

    def add_window(
        self,
        chapters: list[dict],
        *,
        title: str = "",
        arc: str = "",
    ) -> int:
        """把一个窗口的章节作为【新的一卷】追加到末尾。

        每次续写 = 一个新卷，永远接在最后，绝不回填旧卷——避免后续剧情
        被塞进早已结束的开局卷。返回并入的章节数。
        """
        chs = [
            ChapterOutline.from_dict(raw)
            for raw in chapters
            if isinstance(raw, dict)
        ]
        if not chs:
            return 0
        new_index = (max((v.index for v in self.volumes), default=0)) + 1
        self.volumes.append(
            Volume(
                index=new_index,
                title=title or f"第{new_index}卷",
                arc=arc,
                chapters=chs,
            )
        )
        return len(chs)

