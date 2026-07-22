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
from ..memory.state_models import ChapterSummary
from ..project import Project

_SYSTEM = """你是顶尖中文网络小说写手，擅长用清楚、连贯、节奏明快的叙事持续推进剧情。
你严格遵守既定设定与大纲，绝不擅自更改人物境界、关系或世界规则。
写作要求：
- 【剧情推进优先·硬性】每个段落至少承担一项作用：推动事件、升级冲突、揭示有效信息、
  促成人物选择或改变关系。不能只为展示文笔、营造氛围或凑字数而停留在场景和人物描写上。
- 用第三人称、过去式叙事，对话自然。无论题材与基调如何，叙事都应以人物行动、对话、决策及其
  后果为主体。环境、外貌、衣着、神态、感官和心理描写只保留理解当前情节所需的少量关键细节，
  通常一两句点到为止；已经交代过的特征不要在后续章节反复介绍。
- 情绪与人物塑造优先通过事件中的选择、行动、对话和反应呈现，不写大段静态心理分析，
  不把一个瞬间拆成多段反复渲染。即使是言情或细腻基调，也要靠关系变化与实际事件承载情感。
- 目标字数是参考，不是必须填满的指标。若本章细纲不足以自然支撑目标字数，宁可略短，也不要
  用风景、外貌、动作分解、回忆或内心独白注水；同时不得越过下一章边界擅自提前剧情。
- 紧扣本章细纲的情节与目的，章末落在指定的钩子上。
- 与上一章的结尾自然衔接，不重复已写过的情节。
- 严守剧情边界：若给出了"下一章大纲边界"，本章只能推进到下一章开始之前，
  绝不能把下一章才该发生的关键情节、转折或高潮提前写出来。本章在钩子处收住即可。
- 若给出了"上一章收尾场景"，必须承接其中的人物即时状态（受伤、昏迷、在场、
  情绪、未完成的动作），不得让上一章受伤/在场的角色在本章凭空康复或消失。
- 【去AI腔·硬性】避免以下最典型的机器腔套路：
  · 禁止"不是X，是Y"式的情绪/事物定义句，尤其禁止其后再堆"…的、…的、…的那么一种X"；
    情绪用动作、神态或一句白描带出，不做解释。
    （反例：他声音发哽，不是哭，是累的、狠的、喘不上气的那么一种哽。
     正例：赵铁山嗓子发哑，像是嚎了半宿。）
  · 禁止套路化的陈词比喻，也不要给情绪/神态硬套"像X"的比喻；改用动作、神态、白描带出。
    （反例：赵铁山脸色沉得像锅底。／心如刀绞／冷汗如雨／眼睛瞪得像铜铃。
     正例：赵铁山把塘报看完，捏着纸的手紧了紧，半晌没吭声。）
    注意：比喻本身可用，但须新鲜、贴合明末语境、服务于具体画面，杜绝套话与为写而写。
  · 段末/章末不硬加"真正可怕的不是…而是…"这类似是而非的升华金句，让剧情自然收束。
  · 对话不要清一色 2-6 字的干练短句（满屏电报体是最明显的机器腔）。要因人因境、长短交错：
    命令/危急/主官口吻可短而促；诉苦、解释、盘算、闲聊则说成有语气词、有冗余、有半截话的
    自然口语，允许啰嗦。适度加活人碎音（娘的、俺、嗯、这等，按身份），不同人物口吻要有区别，
    不可千人一腔。
  · 叙述正文（非对话）也不要通篇孤立短句。"明快"不等于把句子切碎——要以中长句承载动作、
    因果与推进，用"一边…一边""…，却…""因…而…"等把连续动作和因果串起来，短句只在强调、
    紧张、收束时点睛。严禁句间缺乏黏合、一颗颗短句罗列导致行文破碎。目标是明快而连贯。
    （反例：那股尘烟。更散。更快。贴着地皮卷来。他数了距离。不过一里。前队乱。后队紧。
     正例：那股尘烟更散也更快，贴着地皮撵上来。他估了估距离，前后不过一里多地——前队跑得乱，
     后队咬得紧。是被追上了。）
  · 若本书提供了【写作风格】约束，严格遵守其中的禁用句式与去AI腔要求；若其中某项会导致
    大段静态描写或拖慢情节，则以本系统的“剧情推进优先”原则为准。
- 只输出正文本身，不要标题、不要大纲、不要任何解释或评论。"""

_PROMPT = """【设定摘要】
书名：{title}（{genre}）
基调：{tone}
金手指：{golden_finger}
力量体系：{tiers}
世界规则：{rules}

{writing_style}【本卷】第 {vol_index} 卷《{vol_title}》
弧光：{arc}；境界：{start_tier} → {end_tier}

【相关角色（仅作人设与细节一致性校对，不代表本章必须复述外貌或背景）】
{characters}

【全局记忆：世界状态与前情】
{mid_term}

{recall}
{continuity}【前情：最近章节正文】
{recent}

【本章细纲】第 {index} 章《{ch_title}》
情节：{summary}
叙事目的：{goal}
本章爽点：{cool_point}
章末钩子：{hook}
出场角色：{ch_chars}

{next_boundary}{author_note}{pacing}
【本章执行重点】
按“事件发生 → 人物应对/选择 → 局势或关系产生变化”的方式推进本章。优先写实际发生了什么、
人物做了什么以及造成什么后果；场景、外貌、姿态、感官和心理只在影响当前行动或判断时简短写。
写完后自查：删去纯描写段落，剧情是否几乎不受影响？若是，则删去或压缩该段。

请写出第 {index} 章的正文，目标约 {words} 字，但不得靠描写注水。直接开始写正文。"""


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


def _render_style(value, indent: int = 0) -> list[str]:
    """把任意结构（dict / list / 标量）递归渲染成可读行。"""
    pad = "  " * indent
    lines: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            if v is None or v == "" or v == [] or v == {}:
                continue  # 跳过空项，保持注入精简
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}{k}：")
                lines.extend(_render_style(v, indent + 1))
            else:
                lines.append(f"{pad}{k}：{v}")
    elif isinstance(value, list):
        scalars = [str(x) for x in value if not isinstance(x, (dict, list))]
        complex_items = [x for x in value if isinstance(x, (dict, list))]
        if scalars:
            lines.append(f"{pad}· " + "、".join(scalars))
        for item in complex_items:
            lines.extend(_render_style(item, indent))
    else:
        lines.append(f"{pad}{value}")
    return lines


def _writing_style_block(style: dict) -> str:
    """本书写作风格约束/建议，全书级高优先级注入。空则不注入。

    结构自由（用户可任意增删字段），递归渲染成可读文本块。
    """
    if not style or not isinstance(style, dict):
        return ""
    lines = _render_style(style)
    if not lines:
        return ""
    body = "\n".join(lines)
    return (
        "【写作风格（须贯穿全文遵守；不得覆盖系统的剧情推进优先原则）】\n"
        f"{body}\n\n"
    )


def _continuity_block(summary: "ChapterSummary | None") -> str:
    """上一章收尾场景态，高优先级注入，确保人物即时状态无缝衔接。空则不注入。"""
    if summary is None:
        return ""
    ending = (summary.scene_ending or "").strip()
    if not ending:
        return ""
    return (
        "【上一章收尾场景（必须承接，不得让此处受伤/在场的角色凭空康复或消失）】\n"
        f"{ending}\n\n"
    )


def _next_boundary_block(next_ch: ChapterOutline | None) -> str:
    """下一章大纲边界：告诉模型哪些情节属于下一章，本章不得提前写。空则不注入。"""
    if next_ch is None:
        return ""
    bits = []
    if next_ch.summary:
        bits.append(f"情节：{next_ch.summary}")
    if next_ch.cool_point:
        bits.append(f"爽点：{next_ch.cool_point}")
    if next_ch.goal:
        bits.append(f"目的：{next_ch.goal}")
    if not bits:
        return ""
    body = "；".join(bits)
    return (
        f"【下一章边界（属于第 {next_ch.index} 章，本章严禁提前写到这里）】\n"
        f"{body}\n"
        "本章只推进到这些情节发生之前，在本章钩子处收住，把高潮留给下一章。\n\n"
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
        head = f"· {c.name}"
        alias = "、".join(c.aliases)
        if alias:
            head += f"（又称{alias}）"
        head += f"（{c.role}"
        if c.power_tier:
            head += f"，{c.power_tier}"
        head += "）"
        lines.append(head)
        if c.appearance:
            lines.append(f"  外貌：{c.appearance}")
        traits = "/".join(c.personality)
        if traits or c.goal:
            seg = "  "
            if traits:
                seg += f"性格：{traits}"
            if c.goal:
                seg += ("；" if traits else "") + f"目标：{c.goal}"
            lines.append(seg)
        if c.speech_style:
            lines.append(f"  说话：{c.speech_style}")
        if c.signature:
            lines.append(f"  标志：{c.signature}")
        if c.arc:
            lines.append(f"  成长弧：{c.arc}")
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
    style = project.load_style()

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
        progression_label=bible.progression_label,
    )

    # 连续性摘要：上一章收尾场景态（瞬时在场/即时状态），高优先级衔接
    prev_summary = next((s for s in summaries if s.index == index - 1), None)
    continuity_text = _continuity_block(prev_summary)

    # 下一章边界：注入下一章大纲，禁止本章提前写到那里（可配置关闭）
    next_boundary_text = ""
    if cfg.inject_next_outline:
        next_ch = outline.chapter(index + 1)
        next_boundary_text = _next_boundary_block(next_ch)

    tiers = " → ".join(t.name for t in bible.power_system.tiers) or "（未定义）"
    prompt = _PROMPT.format(
        title=bible.title,
        genre=bible.genre,
        tone=bible.tone,
        golden_finger=bible.golden_finger,
        tiers=tiers,
        rules="；".join(bible.rules) or "（无）",
        writing_style=_writing_style_block(style),
        vol_index=vol.index if vol else 0,
        vol_title=vol.title if vol else "",
        arc=vol.arc if vol else "",
        start_tier=vol.start_tier if vol else "",
        end_tier=vol.end_tier if vol else "",
        characters=_relevant_characters(characters, ch),
        mid_term=mid_term or "（暂无全局记忆，这是开篇阶段）",
        recall=(recall_text + "\n") if recall_text else "",
        continuity=continuity_text,
        recent=recent.text or "（这是第一章，无前情）",
        index=index,
        ch_title=ch.title,
        summary=ch.summary,
        goal=ch.goal,
        cool_point=ch.cool_point or "（无）",
        hook=ch.hook,
        ch_chars="、".join(ch.characters) or "（见细纲）",
        next_boundary=next_boundary_text,
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
