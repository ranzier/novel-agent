"""大纲规划：分层生成。

两阶段，避免一次性让模型规划几百章导致空泛/崩坏：
  1) 骨架：全书主线 + 各卷弧光（粗）
  2) 细化：按卷展开章节细纲（细），可逐卷按需生成
"""

from __future__ import annotations

import json

from ..bible import Bible
from ..llm import LLMGateway
from ..storage import _to_plain
from .outline_models import Outline, Volume

_SYSTEM = """你是资深网文主编，精通长篇连载的节奏与结构。
你设计的大纲要：主线清晰、卷与卷之间冲突层层升级、每卷有明确高潮、
主角实力随卷稳步成长。只输出 JSON，不要任何额外解释或代码块标记。"""

_SKELETON_PROMPT = """这是一本中文网络小说的设定圣经：

{bible_json}

请设计【全书骨架大纲】，规划 {volumes} 卷。
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


def generate_skeleton(
    gateway: LLMGateway, bible: Bible, volumes: int = 5
) -> Outline:
    """生成全书骨架（主线 + 各卷弧光，不含章节细纲）。"""
    bible_json = json.dumps(_to_plain(bible), ensure_ascii=False, indent=2)
    prompt = _SKELETON_PROMPT.format(bible_json=bible_json, volumes=volumes)
    data = gateway.complete_json(
        prompt, system=_SYSTEM, task="outline", max_tokens=4096
    )
    return Outline.from_dict(data)


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
