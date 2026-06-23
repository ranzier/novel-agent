"""中期记忆 + 状态快照 数据模型。

- ChapterSummary：单章摘要（写完一章后抽取）
- WorldState：当前世界状态快照（随章节滚动更新）
这两者构成"中期记忆"，注入下一章写作，让连贯性从相邻几章扩展到全卷/全书。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChapterSummary:
    """单章摘要：写完一章后从正文抽取，供后续章节回顾。"""

    index: int
    title: str = ""
    summary: str = ""               # 本章发生了什么（100字内）
    events: list[str] = field(default_factory=list)   # 关键事件点
    characters: list[str] = field(default_factory=list)  # 实际出场角色
    foreshadowing: list[str] = field(default_factory=list)  # 本章埋下的伏笔

    @classmethod
    def from_dict(cls, d: dict) -> "ChapterSummary":
        d = d or {}
        return cls(
            index=int(d.get("index", 0)),
            title=d.get("title", ""),
            summary=d.get("summary", ""),
            events=list(d.get("events", [])),
            characters=list(d.get("characters", [])),
            foreshadowing=list(d.get("foreshadowing", [])),
        )


@dataclass
class CharacterState:
    """某角色在当前时点的状态。"""

    name: str
    power_tier: str = ""            # 当前境界
    status: str = "存活"           # 存活 / 重伤 / 死亡 / 失踪…
    location: str = ""             # 当前所在
    note: str = ""                 # 其它即时状态（如：被通缉）

    @classmethod
    def from_dict(cls, d: dict) -> "CharacterState":
        d = d or {}
        return cls(
            name=d.get("name", ""),
            power_tier=d.get("power_tier", ""),
            status=d.get("status", "存活"),
            location=d.get("location", ""),
            note=d.get("note", ""),
        )


@dataclass
class WorldState:
    """世界状态快照：截至最新已写章节的"当下"。

    这是写作时的硬事实来源之一：主角现在什么境界、在哪、谁在身边、
    谁已经死了、手里有什么。下一章生成时注入，避免境界倒退、死人复活等。
    """

    last_chapter: int = 0           # 快照对应到第几章末
    timeline: str = ""             # 故事内时间（如：入门第三年秋）
    protagonist_tier: str = ""     # 主角当前境界
    protagonist_location: str = "" # 主角当前位置
    characters: list[CharacterState] = field(default_factory=list)
    items: list[str] = field(default_factory=list)        # 主角持有的关键物品
    open_threads: list[str] = field(default_factory=list)  # 进行中的冲突/任务
    foreshadowing: list[str] = field(default_factory=list) # 未回收的伏笔

    @classmethod
    def from_dict(cls, d: dict) -> "WorldState":
        d = d or {}
        return cls(
            last_chapter=int(d.get("last_chapter", 0)),
            timeline=d.get("timeline", ""),
            protagonist_tier=d.get("protagonist_tier", ""),
            protagonist_location=d.get("protagonist_location", ""),
            characters=[
                CharacterState.from_dict(c)
                for c in d.get("characters", [])
                if isinstance(c, dict)
            ],
            items=list(d.get("items", [])),
            open_threads=list(d.get("open_threads", [])),
            foreshadowing=list(d.get("foreshadowing", [])),
        )

    def character(self, name: str) -> CharacterState | None:
        for c in self.characters:
            if c.name == name:
                return c
        return None
