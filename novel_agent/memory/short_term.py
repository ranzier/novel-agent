"""短期记忆：取最近若干章正文原文，作为写作的直接上下文。

原则：离笔尖越近保真度越高。最近的章给原文，但受字数预算约束，
预算不够时优先保留更近的章，且对最早的那一章做尾部截断（保留结尾，
因为新章紧接的是上一章的结尾）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..project import Project


@dataclass
class RecentContext:
    """组装好的近章上下文。"""

    text: str                # 拼好的近章正文（含分隔标记）
    chapters: list[int]      # 实际纳入的章节序号
    truncated: bool          # 是否发生过截断


def recent_context(
    project: Project,
    before_index: int,
    *,
    max_chapters: int = 3,
    char_budget: int = 12000,
) -> RecentContext:
    """取 before_index 之前最近 max_chapters 章的正文。

    before_index: 即将要写的章节序号；取它之前已存在的章。
    char_budget: 总字数预算（近似 token 控制）。
    """
    indices = [
        i for i in project.existing_chapter_indices() if i < before_index
    ]
    indices = sorted(indices)[-max_chapters:]
    if not indices:
        return RecentContext(text="", chapters=[], truncated=False)

    # 从最近的章往前累加，受预算约束
    blocks: list[tuple[int, str]] = []
    used = 0
    truncated = False
    for idx in reversed(indices):  # 先放最近的
        body = project.read_chapter(idx) or ""
        remaining = char_budget - used
        if remaining <= 0:
            truncated = True
            break
        if len(body) > remaining:
            # 截断：保留结尾部分（紧接新章）
            body = "……（前文略）\n" + body[-remaining:]
            truncated = True
        blocks.append((idx, body))
        used += len(body)

    blocks.reverse()  # 恢复时间顺序
    included = [idx for idx, _ in blocks]
    parts = [f"【第 {idx} 章 正文】\n{body}" for idx, body in blocks]
    return RecentContext(
        text="\n\n".join(parts),
        chapters=included,
        truncated=truncated,
    )
