"""角色库自动晋升：把剧情中反复出场、且被世界状态追踪的新角色，
追加进 characters.json。

两道闸 + 阈值，避免把"路人甲"塞进角色库：
  1) 必须在 state.json 的 characters 里被登记（= 重要到要追踪状态，路人通常不进）
  2) 跨章累计出场章数 ≥ min_chapters（默认 2，过滤只闪现一章的）
  3) 角色库里尚不存在（按名字 / 别名去重）

统计数据来自 summaries（每章的 characters 列表），零额外 LLM 调用。
"""

from __future__ import annotations

from ..bible.models import Character, CharacterBook
from .state_models import ChapterSummary, WorldState


def _clean_name(name: str) -> str:
    """去掉抽取时可能带的后缀，如「苏婉清（提及，未出场）」。"""
    return name.split("（")[0].split("(")[0].strip()


def promote_characters(
    book: CharacterBook,
    summaries: list[ChapterSummary],
    state: WorldState,
    *,
    min_chapters: int = 2,
) -> list[str]:
    """就地把够格的新角色追加进 book.characters。返回新增的角色名列表。"""
    # 已知角色（含别名），用于去重
    known: set[str] = set()
    for c in book.characters:
        known.add(c.name)
        known.update(c.aliases)

    # 闸1：被世界状态追踪的角色（按名字索引其状态）
    tracked = {c.name: c for c in state.characters if c.name}

    # 统计每个角色的累计出场章数（按章去重）
    appear_count: dict[str, int] = {}
    for s in summaries:
        seen_in_ch: set[str] = set()
        for raw in s.characters:
            nm = _clean_name(raw)
            if nm:
                seen_in_ch.add(nm)
        for nm in seen_in_ch:
            appear_count[nm] = appear_count.get(nm, 0) + 1

    added: list[str] = []
    for name, count in appear_count.items():
        if name in known:
            continue                      # 闸3：已在库
        if name not in tracked:
            continue                      # 闸1：未被状态追踪 → 视为路人
        if count < min_chapters:
            continue                      # 闸2：出场太少 → 路人甲
        cs = tracked[name]
        book.characters.append(
            Character(
                name=name,
                role="（剧情登场）",
                power_tier=cs.power_tier,
                background=cs.note,
                notes=f"自动收录：累计出场 {count} 章；状态 {cs.status}"
                + (f"，所在 {cs.location}" if cs.location else ""),
            )
        )
        known.add(name)
        added.append(name)

    return added
