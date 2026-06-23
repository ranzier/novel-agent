"""设定圣经与角色库的数据结构。

设计原则：
- 字段尽量直白，JSON 落地后人能直接读、直接改。
- 力量体系用"分层(tier)"显式建模 —— 这是玄幻/系统流连贯性的关键，
  后续校验"境界不能倒退/跳级"全靠它。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PowerTier:
    """力量体系中的一个层级（如：炼气 → 筑基 → 金丹…）。"""

    order: int                       # 序号，越大越强，用于比较境界高低
    name: str                        # 层级名
    description: str = ""            # 这一层的特征 / 能做到什么


@dataclass
class PowerSystem:
    """力量 / 修炼体系。"""

    name: str = ""                   # 体系名（如"灵气修炼""武道"）
    summary: str = ""               # 一句话概述
    tiers: list[PowerTier] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)  # 硬规则（升级条件、禁忌等）

    @classmethod
    def from_dict(cls, d: dict) -> "PowerSystem":
        d = d or {}
        return cls(
            name=d.get("name", ""),
            summary=d.get("summary", ""),
            tiers=[PowerTier(**t) for t in d.get("tiers", []) if isinstance(t, dict)],
            rules=list(d.get("rules", [])),
        )


@dataclass
class Faction:
    """势力 / 组织。"""

    name: str
    kind: str = ""                   # 类型：宗门 / 家族 / 王朝 / 公司…
    description: str = ""
    stance: str = ""                # 对主角的立场：友好 / 敌对 / 中立


@dataclass
class Character:
    """角色档案。"""

    name: str
    role: str = ""                   # 定位：主角 / 女主 / 导师 / 反派…
    aliases: list[str] = field(default_factory=list)
    gender: str = ""
    age: str = ""
    appearance: str = ""            # 外貌
    personality: list[str] = field(default_factory=list)  # 性格标签
    background: str = ""            # 出身 / 来历
    goal: str = ""                  # 核心目标 / 动机
    power_tier: str = ""            # 当前境界（对应 PowerSystem.tiers 的某个 name）
    faction: str = ""               # 所属势力
    arc: str = ""                   # 成长弧光（一句话）
    notes: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Character":
        d = d or {}
        return cls(
            name=d.get("name", ""),
            role=d.get("role", ""),
            aliases=list(d.get("aliases", [])),
            gender=d.get("gender", ""),
            age=str(d.get("age", "")),
            appearance=d.get("appearance", ""),
            personality=list(d.get("personality", [])),
            background=d.get("background", ""),
            goal=d.get("goal", ""),
            power_tier=d.get("power_tier", ""),
            faction=d.get("faction", ""),
            arc=d.get("arc", ""),
            notes=d.get("notes", ""),
        )


@dataclass
class Bible:
    """设定圣经：一本书的世界观真相来源。"""

    title: str = ""                  # 书名
    genre: str = ""                  # 题材（玄幻 / 都市 / 系统流…）
    one_line: str = ""              # 一句话简介
    selling_points: list[str] = field(default_factory=list)  # 卖点
    golden_finger: str = ""         # 金手指
    core_conflict: str = ""         # 核心矛盾
    tone: str = ""                  # 基调 / 文风倾向
    worldview: str = ""             # 世界观综述
    power_system: PowerSystem = field(default_factory=PowerSystem)
    geography: list[str] = field(default_factory=list)   # 重要地点
    factions: list[Faction] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)       # 世界硬规则 / 金手指限制

    @classmethod
    def from_dict(cls, d: dict) -> "Bible":
        d = d or {}
        return cls(
            title=d.get("title", ""),
            genre=d.get("genre", ""),
            one_line=d.get("one_line", ""),
            selling_points=list(d.get("selling_points", [])),
            golden_finger=d.get("golden_finger", ""),
            core_conflict=d.get("core_conflict", ""),
            tone=d.get("tone", ""),
            worldview=d.get("worldview", ""),
            power_system=PowerSystem.from_dict(d.get("power_system", {})),
            geography=list(d.get("geography", [])),
            factions=[
                Faction(**f) for f in d.get("factions", []) if isinstance(f, dict)
            ],
            rules=list(d.get("rules", [])),
        )


@dataclass
class CharacterBook:
    """角色库：所有角色的集合。"""

    characters: list[Character] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "CharacterBook":
        d = d or {}
        return cls(
            characters=[
                Character.from_dict(c)
                for c in d.get("characters", [])
                if isinstance(c, dict)
            ]
        )

    def get(self, name: str) -> Character | None:
        for c in self.characters:
            if c.name == name or name in c.aliases:
                return c
        return None
