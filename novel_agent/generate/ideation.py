"""立项：从一句话创意 → 设定圣经 + 初始角色库。"""

from __future__ import annotations

from ..bible import Bible, CharacterBook
from ..llm import LLMGateway

_SYSTEM = """你是资深网文主编兼世界观架构师，精通各类中文网络小说的套路与爽点。
你的任务是把一个粗略的创意，扩展成结构完整、逻辑自洽、有商业卖点的设定。
要求：
- 设定要为"长篇连载"服务：要有清晰、可持续升级的"主角进阶维度"，给后续几百章留足成长空间。
  这个进阶维度【随题材而定】——玄幻修真是"境界"，历史是"官阶/权势"，都市是"地位/财富/事业"，
  game/网游是"等级"，悬疑/纯爱等若无可量化进阶则可不设。不要给非修真题材硬套"修炼境界"。
- 金手指要新颖且有明确限制（不能无敌），核心矛盾要能驱动长期冲突。
- 只输出 JSON，不要任何额外解释或代码块标记。"""

_BIBLE_PROMPT = """根据以下创意，设计一本中文网络小说的【设定圣经】。

创意：{idea}
{genre_line}
请输出如下结构的 JSON：
{{
  "title": "书名",
  "genre": "题材",
  "one_line": "一句话简介（突出卖点）",
  "selling_points": ["卖点1", "卖点2", "卖点3"],
  "golden_finger": "金手指描述（含获得方式）",
  "core_conflict": "贯穿全书的核心矛盾",
  "tone": "基调与文风（如：热血爽文/轻松诙谐/严肃史诗）",
  "worldview": "世界观综述（200字内）",
  "progression_label": "主角进阶维度的称谓，随题材而定：玄幻填'境界'、历史填'官阶'、都市填'地位'、网游填'等级'……若本题材没有可量化的进阶维度则填空字符串",
  "power_system": {{
    "name": "进阶体系名（如：修炼体系/官阶品级/事业版图；无则留空）",
    "summary": "一句话概述",
    "tiers": [
      {{"order": 1, "name": "最低层级名", "description": "特征"}},
      {{"order": 2, "name": "下一层级名", "description": "特征"}}
    ],
    "rules": ["升级/晋升的硬规则", "禁忌或代价"]
  }},
  "geography": ["重要地点1", "重要地点2"],
  "factions": [
    {{"name": "势力名", "kind": "类型", "description": "简介", "stance": "对主角立场"}}
  ],
  "rules": ["世界硬规则1", "金手指的限制条件"]
}}

要求：
- progression_label 与 power_system 必须贴合题材，不要给非修真题材硬套"修炼境界"黑话。
- 若题材有进阶维度，power_system.tiers 至少给 6 个层级，覆盖开局到后期；
  若题材确实没有可量化进阶（如纯爱情/纯悬疑），progression_label 留空、tiers 可只给少量或留空。"""

_CHARS_PROMPT = """这是一本中文网络小说的设定圣经：

{bible_json}

请基于该设定，设计【初始核心角色】（主角 1 名 + 关键配角/对手 3~5 名）。
只输出如下结构的 JSON：
{{
  "characters": [
    {{
      "name": "姓名",
      "role": "定位（主角/女主/导师/对手/反派）",
      "aliases": ["别称"],
      "gender": "性别",
      "age": "年龄",
      "appearance": "外貌（简洁）",
      "personality": ["性格标签1", "性格标签2"],
      "background": "出身来历",
      "goal": "核心目标/动机",
      "power_tier": "开局境界（必须是设定中 power_system.tiers 里的某个 name）",
      "faction": "所属势力（来自设定中的 factions，或留空）",
      "arc": "成长弧光（一句话）",
      "notes": "备注"
    }}
  ]
}}

主角的 power_tier 必须是体系中最低或较低的层级（要有成长空间）。"""


def generate_bible(gateway: LLMGateway, idea: str, genre: str = "") -> Bible:
    """从创意生成设定圣经。"""
    genre_line = f"指定题材：{genre}\n" if genre else ""
    prompt = _BIBLE_PROMPT.format(idea=idea, genre_line=genre_line)
    data = gateway.complete_json(
        prompt, system=_SYSTEM, task="outline", max_tokens=4096
    )
    bible = Bible.from_dict(data)
    if genre and not bible.genre:
        bible.genre = genre
    return bible


def generate_characters(gateway: LLMGateway, bible: Bible) -> CharacterBook:
    """基于设定圣经生成初始角色库。"""
    from ..storage import _to_plain
    import json

    bible_json = json.dumps(_to_plain(bible), ensure_ascii=False, indent=2)
    prompt = _CHARS_PROMPT.format(bible_json=bible_json)
    data = gateway.complete_json(
        prompt, system=_SYSTEM, task="outline", max_tokens=4096
    )
    return CharacterBook.from_dict(data)
