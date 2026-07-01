"""记忆固化：写完一章后，从正文抽取摘要并更新世界状态。

这是"写一章 → 巩固记忆 → 再写下一章"闭环的关键一环。
用较便宜的模型（task=extract）做结构化抽取。

抽取分两件事：
  1) 本章摘要（ChapterSummary）—— 滚动累积成中期记忆
  2) 在旧状态基础上，更新出新的世界状态快照（WorldState）
"""

from __future__ import annotations

import json

from ..llm import LLMGateway
from ..storage import _to_plain
from .state_models import ChapterSummary, WorldState

_SYSTEM = """你是小说连续性管理员，负责从正文中精确抽取事实，维护故事状态。
你只记录正文中【明确发生】的事，不臆测、不脑补、不提前剧透。
{tier_label}、生死、所在等状态，只在正文有明确依据时才改动。
只输出 JSON，不要任何解释或代码块标记。"""

_PROMPT = """这是小说《{title}》第 {index} 章《{ch_title}》的正文。

【上一章末的世界状态】
{prev_state}

【本章正文】
{body}

请完成两件事，输出一个 JSON 对象：

1. summary：本章摘要
2. new_state：在上一章末状态基础上，根据本章正文更新后的最新世界状态

输出结构：
{{
  "summary": {{
    "index": {index},
    "title": "{ch_title}",
    "summary": "本章发生了什么（100字内）",
    "events": ["关键事件1", "关键事件2"],
    "characters": ["本章实际出场的角色名"],
    "foreshadowing": ["本章新埋下的伏笔（无则空数组）"],
    "scene_ending": "本章结尾这一刻的瞬时场景态：地点、在场有谁、各自即时状态（受伤/昏迷/情绪/姿态）、未完成的动作或对话。供下一章无缝衔接用。"
  }},
  "new_state": {{
    "last_chapter": {index},
    "timeline": "故事内时间（若正文有交代，否则沿用旧值）",
    "protagonist_tier": "主角当前{tier_label}（{tier_hint}）",
    "protagonist_location": "主角当前所在",
    "characters": [
      {{"name": "角色名", "power_tier": "{tier_label}", "status": "存活/重伤/死亡/失踪", "location": "所在", "note": "即时状态"}}
    ],
    "items": ["主角当前持有的关键物品"],
    "open_threads": ["进行中的冲突/任务/目标"],
    "foreshadowing": ["截至本章仍未回收的伏笔"]
  }}
}}

注意：
- new_state 是【全量快照】，要把旧状态里仍然成立的内容一并带上，而非只写变化。
- 角色生死、{tier_label}等，必须以本章正文为准；正文没提到的角色，沿用旧状态。
- protagonist_tier / power_tier 填的是角色当前的{tier_label}（如无此维度可留空），不要硬套不属于本作设定的说法。
- 若某伏笔在本章被回收，则从 foreshadowing 中移除。
- scene_ending 只写本章【最后一幕】的即时态，不要复述全章；它是下一章的衔接锚点，
  务必交代清楚结尾在场角色的受伤/情绪/姿态与悬而未决的动作。"""


def _tier_terms(progression_label: str) -> tuple[str, str]:
    """按题材的进阶体系称谓，给出 (字段称谓, 填写提示)。

    玄幻=境界、历史=官职/权势、都市=地位…；留空则用中性的"状态/层级"。
    """
    label = (progression_label or "").strip()
    if not label:
        return "身份/层级", "正文明确变化时才改动，无量化体系可留空"
    return label, f"仅在正文明确变化（晋升/贬黜/突破等）时才改动，按本作的「{label}」维度描述"


def consolidate(
    gateway: LLMGateway,
    *,
    title: str,
    index: int,
    chapter_title: str,
    body: str,
    prev_state: WorldState,
    progression_label: str = "",
) -> tuple[ChapterSummary, WorldState]:
    """抽取本章摘要并更新世界状态。返回 (摘要, 新状态)。

    progression_label: 本作进阶体系的称谓（玄幻=境界、历史=官职/权势…），
    用于让抽取 prompt 按题材措辞，避免历史小说被硬塞"境界/凡人"这类修仙说法。
    """
    tier_label, tier_hint = _tier_terms(progression_label)
    prev_json = json.dumps(_to_plain(prev_state), ensure_ascii=False, indent=2)
    prompt = _PROMPT.format(
        title=title,
        index=index,
        ch_title=chapter_title,
        prev_state=prev_json,
        body=body,
        tier_label=tier_label,
        tier_hint=tier_hint,
    )
    data = gateway.complete_json(
        prompt, system=_SYSTEM.format(tier_label=tier_label),
        task="extract", max_tokens=4096,
    )
    summary = ChapterSummary.from_dict(data.get("summary", {}))
    new_state = WorldState.from_dict(data.get("new_state", {}))
    # 兜底：确保章节号正确
    summary.index = index
    if not summary.title:
        summary.title = chapter_title
    new_state.last_chapter = index
    return summary, new_state


_SUMMARY_ONLY_PROMPT = """这是小说《{title}》第 {index} 章《{ch_title}》的正文。

【本章正文】
{body}

请只抽取本章摘要，输出如下 JSON：
{{
  "index": {index},
  "title": "{ch_title}",
  "summary": "本章发生了什么（100字内）",
  "events": ["关键事件1", "关键事件2"],
  "characters": ["本章实际出场的角色名"],
  "foreshadowing": ["本章新埋下的伏笔（无则空数组）"],
  "scene_ending": "本章结尾这一刻的瞬时场景态：地点、在场有谁、各自即时状态、未完成的动作或对话"
}}

只依据正文，不臆测、不脑补、不提前剧透。只输出 JSON。"""


def extract_summary_only(
    gateway: LLMGateway,
    *,
    title: str,
    index: int,
    chapter_title: str,
    body: str,
) -> ChapterSummary:
    """仅从正文抽取章节摘要（不更新世界状态）。

    用于作者手改正文后重建摘要——只同步摘要层，不动当前世界状态快照
    （状态是截至最新章的当前快照，重抽中间章无干净的 prev_state 可依据）。
    """
    prompt = _SUMMARY_ONLY_PROMPT.format(
        title=title, index=index, ch_title=chapter_title, body=body
    )
    data = gateway.complete_json(
        prompt, system=_SYSTEM.format(tier_label="身份/层级"),
        task="extract", max_tokens=2048,
    )
    summary = ChapterSummary.from_dict(data)
    summary.index = index
    if not summary.title:
        summary.title = chapter_title
    return summary
