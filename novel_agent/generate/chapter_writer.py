"""正文生成：按章节细纲 + 注入的上下文写出一章正文。

当前注入：设定摘要 + 相关角色 + 本卷信息 + 近 N 章原文 + 本章细纲。
（中期摘要、图谱约束、向量召回在后续步骤接入。）
"""

from __future__ import annotations

import re

from ..bible import Bible, CharacterBook
from ..generate.outline_models import ChapterOutline, Outline, Volume
from ..llm import LLMGateway
from ..memory import recent_context, mid_term_block
from ..project import Project

_SYSTEM = """你是顶尖中文网络小说写手，文笔流畅、画面感强、节奏明快。
你严格遵守既定设定与大纲，绝不擅自更改人物境界、关系或世界规则。
写作要求：
- 用第三人称、过去式叙事，对话自然。描写详略由"基调"决定——
  爽文偏紧凑明快、重情节推进与爽点；细腻向可多铺陈心理与场景。不堆砌无关细节。
- 紧扣本章细纲的情节与目的，章末落在指定的钩子上。
- 与上一章的结尾自然衔接，不重复已写过的情节。
- 只输出正文本身，不要标题、不要大纲、不要任何解释或评论。"""

_PROMPT = """【设定摘要】
书名：{title}（{genre}）
基调：{tone}
金手指：{golden_finger}
力量体系：{tiers}
世界规则：{rules}

【本卷】第 {vol_index} 卷《{vol_title}》
弧光：{arc}；境界：{start_tier} → {end_tier}

【相关角色】
{characters}

【全局记忆：世界状态与前情】
{mid_term}

{recall}
【前情：最近章节正文】
{recent}

【本章细纲】第 {index} 章《{ch_title}》
情节：{summary}
叙事目的：{goal}
本章爽点：{cool_point}
章末钩子：{hook}
出场角色：{ch_chars}

{author_note}{pacing}
请写出第 {index} 章的正文，约 {words} 字。直接开始写正文。"""


def _author_note_block(note: str) -> str:
    """作者对本章的思路/要求，高优先级注入。空则不注入。"""
    note = (note or "").strip()
    if not note:
        return ""
    return (
        "【作者本章要求（高优先级，须优先满足，可在不违背既定设定/世界状态的"
        "前提下灵活调整细纲情节以贴合作者意图）】\n"
        f"{note}\n\n"
    )


def _relevant_characters(
    characters: CharacterBook, ch: ChapterOutline
) -> str:
    """挑出本章出场角色的档案；没匹配上则给主角等核心角色。"""
    picked = []
    for name in ch.characters:
        c = characters.get(name)
        if c:
            picked.append(c)
    if not picked:
        # 退而求其次：给主角 + 女主
        picked = [
            c for c in characters.characters if c.role in ("主角", "女主")
        ] or characters.characters[:2]

    lines = []
    for c in picked:
        lines.append(
            f"· {c.name}（{c.role}，{c.power_tier}）"
            f"性格：{'/'.join(c.personality)}；目标：{c.goal}"
        )
    return "\n".join(lines)


def _find_volume(outline: Outline, ch_index: int) -> Volume | None:
    for v in outline.volumes:
        if any(c.index == ch_index for c in v.chapters):
            return v
    return None


def write_chapter(
    gateway: LLMGateway,
    project: Project,
    *,
    index: int,
    words: int = 2500,
    max_chapters_context: int = 3,
    revision_note: str = "",
    recall_text: str = "",
    pacing_text: str = "",
    author_note: str = "",
    on_delta=None,
) -> str:
    """生成第 index 章正文并返回文本（不落盘，由调用方决定保存）。

    revision_note: 重写时传入的修正要求（如校验发现的硬伤），会附加到 prompt。
    """
    bible: Bible = project.load_bible()
    characters = project.load_characters()
    outline = project.load_outline()

    ch = outline.chapter(index)
    if ch is None:
        raise ValueError(f"大纲里没有第 {index} 章，请先扩展大纲。")
    vol = _find_volume(outline, index)

    # 上下文参数来自配置（可在配置页调整）
    from ..config import Config

    cfg = Config.load()
    recent_n = cfg.recent_chapters

    recent = recent_context(
        project, index,
        max_chapters=recent_n, char_budget=cfg.recent_char_budget,
    )

    # 中期记忆：世界状态快照 + 早期章节摘要 + 未回收伏笔
    state = project.load_state()
    summaries = project.load_summaries()
    mid_term = mid_term_block(
        summaries, state, before_index=index,
        skip_recent=recent_n, max_summaries=cfg.summary_count,
    )

    tiers = " → ".join(t.name for t in bible.power_system.tiers) or "（未定义）"
    prompt = _PROMPT.format(
        title=bible.title,
        genre=bible.genre,
        tone=bible.tone,
        golden_finger=bible.golden_finger,
        tiers=tiers,
        rules="；".join(bible.rules) or "（无）",
        vol_index=vol.index if vol else 0,
        vol_title=vol.title if vol else "",
        arc=vol.arc if vol else "",
        start_tier=vol.start_tier if vol else "",
        end_tier=vol.end_tier if vol else "",
        characters=_relevant_characters(characters, ch),
        mid_term=mid_term or "（暂无全局记忆，这是开篇阶段）",
        recall=(recall_text + "\n") if recall_text else "",
        recent=recent.text or "（这是第一章，无前情）",
        index=index,
        ch_title=ch.title,
        summary=ch.summary,
        goal=ch.goal,
        cool_point=ch.cool_point or "（无）",
        hook=ch.hook,
        ch_chars="、".join(ch.characters) or "（见细纲）",
        author_note=_author_note_block(author_note),
        pacing=(pacing_text + "\n") if pacing_text else "",
        words=words,
    )

    if revision_note:
        prompt += (
            f"\n\n【重写要求】上一稿存在以下连贯性问题，请在重写时严格避免：\n"
            f"{revision_note}\n"
            f"务必使用既定角色名、不让已死角色出场、不让境界倒退。"
        )

    max_tokens = max(2048, int(words * 2.5))
    if on_delta is not None:
        # 流式：边生成边回调 on_delta(增量)，最后汇总
        parts = []
        for delta in gateway.complete_stream(
            prompt, system=_SYSTEM, task="write",
            max_tokens=max_tokens, temperature=1.0,
        ):
            parts.append(delta)
            try:
                on_delta(delta)
            except Exception:  # noqa: BLE001 - 回调出错不应中断生成
                pass
        text = "".join(parts)
    else:
        text = gateway.complete(
            prompt, system=_SYSTEM, task="write",
            max_tokens=max_tokens, temperature=1.0,
        )
    return _strip_leading_title(text, ch.title)


def _strip_leading_title(text: str, title: str) -> str:
    """去掉模型在正文开头偶尔重复写出的标题行。

    匹配如「第一章 废子退婚」「# 第1章　废子退婚」或单独的标题文字，
    可能带 markdown 的 # 前缀。最多剥除开头连续两行这样的标题。
    """
    lines = text.lstrip().split("\n")
    norm_title = title.replace(" ", "").replace("　", "") if title else ""

    def is_title(line: str) -> bool:
        head = line.lstrip("#＃ 　").strip()
        if not head or len(head) >= 40:
            return False
        if re.match(r"^第\s*[0-9零一二三四五六七八九十百千]+\s*章", head):
            return True
        compact = head.replace(" ", "").replace("　", "")
        return bool(norm_title) and compact == norm_title

    # 剥掉开头最多两行标题（应对「# 第X章」与纯标题各占一行）
    removed = 0
    while lines and removed < 2 and is_title(lines[0]):
        lines.pop(0)
        removed += 1
        # 跳过标题后的空行
        while lines and not lines[0].strip():
            lines.pop(0)

    result = "\n".join(lines).lstrip()
    return result or text
