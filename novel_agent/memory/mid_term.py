"""中期记忆：章节摘要的存取 + 组装注入上下文。

写作第 N 章时，短期记忆给近几章原文，中期记忆给更早章节的摘要 +
当前世界状态快照 + 未回收伏笔，让模型在不读全文的情况下保持全局连贯。
"""

from __future__ import annotations

from .state_models import ChapterSummary, WorldState


def mid_term_block(
    summaries: list[ChapterSummary],
    state: WorldState | None,
    *,
    before_index: int,
    skip_recent: int = 3,
    max_summaries: int = 30,
    progression_label: str = "",
) -> str:
    """组装中期记忆文本块。

    before_index: 即将写的章节号
    skip_recent: 最近这些章已由短期记忆给原文，这里不再重复其摘要
    max_summaries: 最多纳入多少条早期摘要（防止过长）
    progression_label: 进阶体系称谓（玄幻=境界、历史=官职/权势…），用于状态显示
    """
    parts: list[str] = []

    # 1) 世界状态快照（硬事实）
    if state and state.last_chapter > 0:
        parts.append(_format_state(state, progression_label))

    # 2) 早期章节摘要（跳过最近 skip_recent 章）
    cutoff = before_index - skip_recent
    earlier = [s for s in summaries if s.index < cutoff]
    earlier = sorted(earlier, key=lambda s: s.index)[-max_summaries:]
    if earlier:
        lines = ["【前情摘要】"]
        for s in earlier:
            line = f"第{s.index}章《{s.title}》：{s.summary}"
            lines.append(line)
        parts.append("\n".join(lines))

    return "\n\n".join(parts)


def _format_state(state: WorldState, progression_label: str = "") -> str:
    tier_label = (progression_label or "").strip() or "状态"
    lines = [f"【当前世界状态】（截至第 {state.last_chapter} 章）"]
    if state.timeline:
        lines.append(f"时间：{state.timeline}")
    if state.protagonist_tier:
        lines.append(f"主角{tier_label}：{state.protagonist_tier}")
    if state.protagonist_location:
        lines.append(f"主角位置：{state.protagonist_location}")
    if state.items:
        lines.append(f"主角持有：{'、'.join(state.items)}")

    living = [c for c in state.characters if c.status != "死亡"]
    dead = [c for c in state.characters if c.status == "死亡"]
    if living:
        lines.append("在场/相关角色：")
        for c in living:
            seg = f"  · {c.name}（{c.power_tier}，{c.status}）"
            if c.location:
                seg += f" 位于{c.location}"
            if c.note:
                seg += f"；{c.note}"
            lines.append(seg)
    if dead:
        # 显式列出已死角色 —— 防止"死人复活"
        lines.append(f"已死亡（不可再出场）：{'、'.join(c.name for c in dead)}")
    if state.open_threads:
        lines.append("进行中的冲突/任务：")
        for t in state.open_threads:
            lines.append(f"  · {t}")
    if state.foreshadowing:
        lines.append("未回收伏笔：")
        for f in state.foreshadowing:
            lines.append(f"  · {f}")
    return "\n".join(lines)
