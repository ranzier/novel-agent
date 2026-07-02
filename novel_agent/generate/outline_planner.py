"""大纲规划：骨架 + 滑动窗口式章节细纲。

设计：
  1) 骨架：全书主线 + 各卷弧光（粗，轻量，可规划多卷，不锁死细节）
  2) 章节细纲：滑动窗口式——只生成"从当前往后 N 章"，不一次铺满全书。
     这样后期剧情不会被早期规划绑架；写完一个窗口再基于实际进度续写下一窗口。
"""

from __future__ import annotations

import json

from ..bible import Bible
from ..llm import LLMGateway
from ..memory.state_models import ChapterSummary, WorldState
from ..storage import _to_plain
from .outline_models import Outline, Volume

_SYSTEM = """你是资深网文主编，精通长篇连载的节奏与结构。
你设计的大纲要：主线清晰、卷与卷之间冲突层层升级、每卷有明确高潮、
主角实力随卷稳步成长。只输出 JSON，不要任何额外解释或代码块标记。"""

_SKELETON_PROMPT = """这是一本中文网络小说的设定圣经：

{bible_json}

请设计【全书骨架大纲】。卷数由你按故事体量自行决定（通常 3~6 卷，长篇可更多），
每卷一段弧光，作为后续写作的方向蓝图。
只输出如下结构的 JSON：
{{
  "premise": "全书核心立意（一句话）",
  "main_plot": "全书主线：开端→发展→高潮→结局（200字内）",
  "themes": ["主题1", "主题2"],
  "ending": "结局走向",
  "volumes": [
    {{
      "index": 1,
      "title": "卷名",
      "arc": "本卷弧光/核心情节",
      "goal": "本卷推进的主线目标",
      "climax": "本卷高潮事件",
      "start_tier": "卷初主角境界",
      "end_tier": "卷末主角境界"
    }}
  ]
}}

要求：境界成长要连贯（后一卷 start_tier = 前一卷 end_tier），
且都必须是设定 power_system.tiers 里的层级名。"""

_CHAPTERS_PROMPT = """这是一本中文网络小说的设定与本卷信息。

【设定圣经摘要】
书名：{title}
题材：{genre}
基调：{tone}
力量体系层级：{tiers}

【本卷信息】
第 {vol_index} 卷《{vol_title}》
弧光：{arc}
目标：{goal}
高潮：{climax}
境界：{start_tier} → {end_tier}

【已知角色】
{characters}

请把本卷细化为 {chapters} 章的【章节细纲】。章节全书序号从 {start_index} 开始连续编号。
只输出如下结构的 JSON：
{{
  "chapters": [
    {{
      "index": {start_index},
      "title": "章节标题",
      "summary": "本章主要情节（80字内）",
      "goal": "本章叙事目的",
      "hook": "章末钩子（留悬念）",
      "characters": ["出场角色名"],
      "cool_point": "本章爽点（如有，无则留空）"
    }}
  ]
}}

要求：
- 章节之间情节连贯、层层推进，本卷最后一章对应高潮 {climax}。
- 每隔几章安排一个爽点，章末都要有钩子。
- 出场角色名尽量用【已知角色】里的名字。"""


def generate_skeleton(gateway: LLMGateway, bible: Bible) -> Outline:
    """生成全书骨架（主线 + 各卷弧光）。卷数由模型按故事体量自定。
    弧光存入 arc_plan 作方向参考，不直接承载章节——章节由滑动窗口生成后追加到 volumes。"""
    bible_json = json.dumps(_to_plain(bible), ensure_ascii=False, indent=2)
    prompt = _SKELETON_PROMPT.format(bible_json=bible_json)
    data = gateway.complete_json(
        prompt, system=_SYSTEM, task="outline", max_tokens=4096
    )
    outline = Outline.from_dict(data)
    # 模型按 _SKELETON_PROMPT 把卷弧光放在 volumes 里；移到 arc_plan。
    outline.arc_plan = outline.volumes
    outline.volumes = []
    return outline


def generate_volume_chapters(
    gateway: LLMGateway,
    bible: Bible,
    volume: Volume,
    *,
    chapters: int,
    start_index: int,
    character_names: list[str],
) -> Volume:
    """为某一卷生成章节细纲，返回填充了 chapters 的新 Volume。"""
    tiers = " → ".join(t.name for t in bible.power_system.tiers) or "（未定义）"
    prompt = _CHAPTERS_PROMPT.format(
        title=bible.title,
        genre=bible.genre,
        tone=bible.tone,
        tiers=tiers,
        vol_index=volume.index,
        vol_title=volume.title,
        arc=volume.arc,
        goal=volume.goal,
        climax=volume.climax,
        start_tier=volume.start_tier,
        end_tier=volume.end_tier,
        characters="、".join(character_names) or "（暂无）",
        chapters=chapters,
        start_index=start_index,
    )
    data = gateway.complete_json(
        prompt, system=_SYSTEM, task="outline", max_tokens=8192
    )
    filled = Volume.from_dict(
        {
            "index": volume.index,
            "title": volume.title,
            "arc": volume.arc,
            "goal": volume.goal,
            "climax": volume.climax,
            "start_tier": volume.start_tier,
            "end_tier": volume.end_tier,
            "chapters": data.get("chapters", []),
        }
    )
    return filled


# ---------------- 滑动窗口式章节细纲 ----------------

_WINDOW_PROMPT = """这是一本中文网络小说，现在要规划【接下来 {count} 章】的章节细纲。

【设定圣经摘要】
书名：{title}（{genre}）
基调：{tone}
力量体系层级：{tiers}

【全书主线】
{main_plot}

【卷级骨架】（章节要服务于当前所处卷的弧光，自然向其高潮推进）
{volumes_brief}

【当前进度与世界状态】
{progress}

【前情摘要】（最近若干章实际写出的剧情，新章须自然承接）
{recap}

【已知角色】
{characters}

{author_note}请规划从第 {start_index} 章开始、连续 {count} 章的细纲。章节序号从 {start_index} 连续编号。
这批章节会作为新的一卷，请同时为这一卷起个卷名、概括其弧光。
只输出如下结构的 JSON：
{{
  "volume_title": "这一卷的卷名",
  "volume_arc": "这一卷的弧光/核心情节（一句话）",
  "chapters": [
    {{
      "index": {start_index},
      "title": "章节标题",
      "summary": "本章主要情节（80字内）",
      "goal": "本章叙事目的",
      "hook": "章末钩子（留悬念）",
      "characters": ["出场角色名"],
      "cool_point": "本章爽点（如有，无则留空）"
    }}
  ]
}}

要求：
- 紧承"当前进度与世界状态"，与已发生的剧情自然衔接，不与既成事实矛盾。
- 若给出了【作者意图】，须作为最高优先级落实到这几章的走向中，在不违背既定设定与世界状态的前提下，优先按作者的想法编排情节、分配章节。
- 主角境界从当前状态出发稳步推进，不跳级、不倒退。
- 章节层层推进、每隔几章一个爽点、章末都要有钩子。
- 出场角色尽量用【已知角色】里的名字；已死亡角色不可再出场。"""


def _author_intent_block(note: str) -> str:
    """作者对接下来几章剧情走向的意图，最高优先级注入。空则不注入。"""
    note = (note or "").strip()
    if not note:
        return ""
    return (
        "【作者意图（最高优先级，须优先落实到本批章节的剧情走向中，"
        "可在不违背既定设定与世界状态的前提下灵活编排以贴合作者想法）】\n"
        f"{note}\n\n"
    )


def _volumes_brief(outline: Outline) -> str:
    lines = []
    for v in outline.arc_plan:
        lines.append(
            f"第{v.index}卷《{v.title}》：{v.arc}"
            f"（境界 {v.start_tier}→{v.end_tier}，高潮：{v.climax}）"
        )
    return "\n".join(lines) or "（暂无骨架）"


def _progress_brief(state: WorldState, last_written: int) -> str:
    if last_written <= 0 or state.last_chapter <= 0:
        return "尚未开写，这是开篇阶段。"
    parts = [f"已写到第 {last_written} 章。"]
    if state.timeline:
        parts.append(f"故事时间：{state.timeline}")
    if state.protagonist_tier:
        parts.append(f"主角当前境界：{state.protagonist_tier}")
    if state.protagonist_location:
        parts.append(f"主角当前位置：{state.protagonist_location}")
    dead = [c.name for c in state.characters if c.status == "死亡"]
    if dead:
        parts.append(f"已死亡角色（不可再出场）：{'、'.join(dead)}")
    if state.open_threads:
        parts.append("进行中的冲突/任务：" + "；".join(t.text for t in state.open_threads))
    if state.foreshadowing:
        parts.append("未回收伏笔：" + "；".join(f.text for f in state.foreshadowing))
    return "\n".join(parts)


def _recap_brief(summaries: list[ChapterSummary]) -> str:
    """把最近若干章摘要渲染成前情块，复用与写章一致的格式。"""
    if not summaries:
        return "（暂无前情摘要，或开篇阶段）"
    ordered = sorted(summaries, key=lambda s: s.index)
    lines = [f"第{s.index}章《{s.title}》：{s.summary}" for s in ordered]
    return "\n".join(lines)


def generate_chapter_window(
    gateway: LLMGateway,
    bible: Bible,
    outline: Outline,
    *,
    start_index: int,
    count: int,
    character_names: list[str],
    state: WorldState | None = None,
    recap_summaries: list[ChapterSummary] | None = None,
    author_note: str = "",
) -> dict:
    """滑动窗口：生成从 start_index 起连续 count 章的细纲。

    基于设定 + 卷骨架 + 当前进度/世界状态 + 最近若干章前情摘要，让新章节贴合
    实际剧情走向，而非被早期一次性规划绑架。返回 {title, arc, chapters}，
    由调用方作为「新的一卷」并入大纲。

    recap_summaries：最近 N 章摘要（由调用方按配置切好传入），渲染为前情块。
    author_note：作者对接下来几章剧情走向的意图，最高优先级注入。
    """
    tiers = " → ".join(t.name for t in bible.power_system.tiers) or "（未定义）"
    last_written = (state.last_chapter if state else 0)
    prompt = _WINDOW_PROMPT.format(
        title=bible.title,
        genre=bible.genre,
        tone=bible.tone,
        tiers=tiers,
        main_plot=outline.main_plot or "（未定义）",
        volumes_brief=_volumes_brief(outline),
        progress=_progress_brief(state or WorldState(), last_written),
        recap=_recap_brief(recap_summaries or []),
        characters="、".join(character_names) or "（暂无）",
        author_note=_author_intent_block(author_note),
        count=count,
        start_index=start_index,
    )
    data = gateway.complete_json(
        prompt, system=_SYSTEM, task="outline", max_tokens=8192
    )
    if not isinstance(data, dict):
        data = {}
    chapters = data.get("chapters", [])
    # 兜底：强制章节号连续，防止模型编错号
    for offset, ch in enumerate(chapters):
        if isinstance(ch, dict):
            ch["index"] = start_index + offset
    return {
        "title": data.get("volume_title", ""),
        "arc": data.get("volume_arc", ""),
        "chapters": chapters[:count],
    }
