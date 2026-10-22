"""记忆固化：模型抽取事实，程序确定性构造摘要并合并世界状态。

模型只填写本章内容和相对上一章的变化。最终 ChapterSummary / WorldState
的 schema、章节号、默认值和旧状态继承全部由程序控制。
"""

from __future__ import annotations

import json

from ..llm import LLMError, LLMGateway
from ..storage import _to_plain
from .state_models import ChapterSummary, WorldState


class MemoryValidationError(LLMError):
    """模型返回的事实不足以安全固化。"""


_SYSTEM = """你是小说事实抽取器。
只记录正文中明确发生的事实，不臆测、不脑补、不提前剧透。
只填写本章事实和相对上一章的状态变化，不要复制完整世界状态。
只输出 JSON，不要解释或代码块标记。"""

_FACTS_SCHEMA = """{
  "facts": [
    {"type": "summary", "text": "本章发生了什么（100~200字）"},
    {"type": "event", "text": "关键事件，可有多条"},
    {"type": "character", "text": "本章实际出场角色名，可有多条"},
    {"type": "foreshadowing", "text": "本章新埋下且尚未回收的伏笔，可无"},
    {"type": "scene_ending", "text": "最后一幕的地点、在场者、即时状态和未完成动作"}
  ],
  "state_changes": {
      "timeline": null,
      "protagonist_tier": null,
      "protagonist_location": null,
      "character_updates": [{
        "name": "角色名",
        "power_tier": null,
        "status": null,
        "location": null,
        "note": null
      }],
      "items_add": [],
      "items_remove": [],
      "open_threads_add": [],
      "open_threads_resolve": [],
      "foreshadowing_resolve": []
  }
}"""

_PROMPT = """这是小说《{title}》第 {index} 章《{ch_title}》。

【上一章末世界状态（只用于判断变化，不要原样复制）】
{prev_state}

【本章正文】
{body}

请抽取本章事实与相对上一章的状态变化，严格输出以下 JSON：
{schema}

规则：
- facts 是带 type/text 的事实列表；summary、event、scene_ending 必须依据正文填写。
- state_changes 只写正文明确发生的变化；无变化的标量填 null，数组填 []。
- character_updates 只列新出现或状态确有变化的角色；未变化角色不要重复。
- items_remove、open_threads_resolve、foreshadowing_resolve 必须照抄旧状态原文；不确定就不填。
- foreshadowing 事实会由程序加入摘要和未回收伏笔，无则不要输出该类型。
- 不要输出 index、title、last_chapter 或完整 new_state，这些由程序生成。
- {tier_label}等状态只在正文明确变化时填写。"""

_SUMMARY_PROMPT = """这是小说《{title}》第 {index} 章《{ch_title}》的正文。

【本章正文】
{body}

只抽取本章摘要事实，输出 JSON：
{{
  "facts": {{
    "summary_text": "本章发生了什么（100~200字）",
    "events": ["至少一个关键事件"],
    "characters_present": ["实际出场角色名"],
    "new_foreshadowing": [],
    "scene_ending": "最后一幕的地点、在场者、即时状态和未完成动作"
  }}
}}
只依据正文，只输出 JSON。"""

_REPAIR_PROMPT = """请重新执行下面的事实抽取任务。上一次 JSON 可以解析，但内容字段校验失败。

【原始任务】
{original_prompt}

【校验错误】
{error}

【上一次返回】
{payload}

必须输出顶层 facts 和 state_changes。facts 可以是带 type/text 的数组；只输出 JSON。"""


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
    """抽取本章事实，由程序将增量合并到上一章世界状态。"""
    tier_label = (progression_label or "").strip() or "身份/层级"
    prompt = _PROMPT.format(
        title=title,
        index=index,
        ch_title=chapter_title,
        prev_state=json.dumps(
            _to_plain(prev_state), ensure_ascii=False, indent=2
        ),
        body=body,
        schema=_FACTS_SCHEMA,
        tier_label=tier_label,
    )
    facts = _request_facts(
        gateway, prompt=prompt, require_changes=True, max_tokens=4096
    )
    summary = _build_summary(
        facts, index=index, chapter_title=chapter_title
    )
    new_state = _merge_world_state(
        prev_state, facts, index=index, summary=summary
    )
    return summary, new_state


def extract_summary_only(
    gateway: LLMGateway,
    *,
    title: str,
    index: int,
    chapter_title: str,
    body: str,
) -> ChapterSummary:
    """只抽取摘要内容；最终 ChapterSummary schema 由程序构造。"""
    prompt = _SUMMARY_PROMPT.format(
        title=title, index=index, ch_title=chapter_title, body=body
    )
    facts = _request_facts(
        gateway, prompt=prompt, require_changes=False, max_tokens=2048
    )
    return _build_summary(facts, index=index, chapter_title=chapter_title)


def _request_facts(
    gateway: LLMGateway,
    *,
    prompt: str,
    require_changes: bool,
    max_tokens: int,
) -> dict:
    data = gateway.complete_json(
        prompt, system=_SYSTEM, task="extract",
        max_tokens=max_tokens, temperature=0.0,
    )
    try:
        return _validate_facts(data, require_changes=require_changes)
    except MemoryValidationError as first_error:
        repaired = gateway.complete_json(
            _REPAIR_PROMPT.format(
                original_prompt=prompt,
                error=first_error,
                payload=_diagnostic_payload(data),
            ),
            system=_SYSTEM,
            task="extract",
            max_tokens=max_tokens,
            temperature=0.0,
        )
        try:
            return _validate_facts(repaired, require_changes=require_changes)
        except MemoryValidationError as second_error:
            raise MemoryValidationError(
                "事实抽取修复后仍无效："
                f"首次错误={first_error}；修复错误={second_error}；"
                f"{_top_level_shape(repaired)}"
            ) from second_error


def _validate_facts(data: object, *, require_changes: bool) -> dict:
    if not isinstance(data, dict):
        raise MemoryValidationError("事实抽取结果不是 JSON 对象")

    raw = data.get("facts", data)
    content = _normalize_fact_content(raw)

    # 兼容模型把 state_changes 放在 facts 内或与 facts 同级。
    nested_changes = raw.get("state_changes") if isinstance(raw, dict) else None
    changes = data.get("state_changes", nested_changes)
    if changes is None:
        changes = {}
    if require_changes and "state_changes" not in data and nested_changes is None:
        raise MemoryValidationError("facts 缺少 state_changes 对象")
    if not isinstance(changes, dict):
        raise MemoryValidationError("facts.state_changes 不是对象")

    return {
        **content,
        "state_changes": _normalize_changes(changes),
    }


def _normalize_fact_content(raw: object) -> dict:
    """接受事实对象或事实列表，输出程序内部固定的内容字段。"""
    if isinstance(raw, dict):
        return _normalize_fact_object(raw)
    if isinstance(raw, list):
        return _normalize_fact_list(raw)
    raise MemoryValidationError("facts 缺失，且不是对象或数组")


def _normalize_fact_object(raw: dict) -> dict:
    # 兼容 summary 为字符串或模型额外包一层 summary 对象。
    summary_value = raw.get(
        "summary_text",
        raw.get("summary", raw.get("chapter_summary", raw.get("overview"))),
    )
    if isinstance(summary_value, dict):
        summary_value = summary_value.get("text", summary_value.get("summary"))

    events = _fact_strings(
        raw.get("events", raw.get("key_events", raw.get("event_facts", []))),
        "facts.events",
    )
    characters = _fact_strings(
        raw.get(
            "characters_present",
            raw.get("characters", raw.get("present_characters", [])),
        ),
        "facts.characters_present",
    )
    foreshadowing = _fact_strings(
        raw.get(
            "new_foreshadowing",
            raw.get("foreshadowing", raw.get("new_clues", [])),
        ),
        "facts.new_foreshadowing",
    )
    scene_value = raw.get(
        "scene_ending",
        raw.get("ending", raw.get("final_scene", raw.get("scene_end"))),
    )
    if isinstance(scene_value, dict):
        scene_value = scene_value.get("text", scene_value.get("summary"))

    # Claude 偶尔会自行改成“本章事实”“结局状态”等字段名。
    # 字段名不属于最终 schema，因此只要值仍是模型返回的
    # 足够长的叙事文本，就可用于程序的确定性组装。
    fallback_facts = _fallback_narrative_facts(raw)
    if not events:
        events = fallback_facts

    # 如果模型只给出事件事实，摘要和结尾由这些事实确定性拼装，
    # 不新增任何模型未提供的信息。
    if not isinstance(summary_value, str) or not summary_value.strip():
        summary_value = "；".join(events)
    if not isinstance(scene_value, str) or not scene_value.strip():
        scene_value = events[-1] if events else ""
    return _validated_content(
        summary_value, events, characters, foreshadowing, scene_value
    )


def _fallback_narrative_facts(raw: dict) -> list[str]:
    """从自定义字段中只取模型已返回的叙事文本。

    这是输入兼容层，不会生成新内容，也不会把角色名、
    章节号或 state_changes 当成情节。
    """
    known_keys = {
        "summary_text", "summary", "chapter_summary", "overview",
        "events", "key_events", "event_facts",
        "characters_present", "characters", "present_characters",
        "new_foreshadowing", "foreshadowing", "new_clues",
        "scene_ending", "ending", "final_scene", "scene_end",
        "state_changes", "index", "title", "last_chapter",
    }
    values: list[str] = []
    for key, value in raw.items():
        if str(key).strip().lower() in known_keys:
            continue
        values.extend(_narrative_strings(value))
    return _dedupe(values)


def _narrative_strings(value: object) -> list[str]:
    """递归收集自定义事实字段里的长文本叶子。"""
    if isinstance(value, str):
        text = value.strip()
        return [text] if len(text) >= 10 else []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_narrative_strings(item))
        return result
    if isinstance(value, dict):
        result: list[str] = []
        for key, item in value.items():
            if str(key).strip().lower() in {
                "type", "kind", "category", "name", "id",
                "index", "chapter", "last_chapter",
            }:
                continue
            result.extend(_narrative_strings(item))
        return result
    return []


def _normalize_fact_list(raw: list) -> dict:
    grouped: dict[str, list[str]] = {
        "summary": [],
        "event": [],
        "character": [],
        "foreshadowing": [],
        "scene_ending": [],
    }
    untyped: list[str] = []
    aliases = {
        "summary": "summary", "摘要": "summary", "overview": "summary",
        "event": "event", "事件": "event", "fact": "event", "事实": "event",
        "character": "character", "人物": "character", "角色": "character",
        "foreshadowing": "foreshadowing", "伏笔": "foreshadowing", "clue": "foreshadowing",
        "scene_ending": "scene_ending", "ending": "scene_ending", "结尾": "scene_ending",
    }
    for pos, item in enumerate(raw):
        if isinstance(item, str):
            text = item.strip()
            if text:
                untyped.append(text)
            continue
        if not isinstance(item, dict):
            raise MemoryValidationError(f"facts[{pos}] 不是字符串或对象")
        kind = str(
            item.get("type", item.get("kind", item.get("category", "event")))
        ).strip().lower()
        value = item.get("text", item.get("content", item.get("value")))
        if not isinstance(value, str) or not value.strip():
            raise MemoryValidationError(f"facts[{pos}].text 为空")
        grouped[aliases.get(kind, "event")].append(value.strip())

    events = _dedupe(grouped["event"] + untyped)
    summary_parts = grouped["summary"]
    summary_text = summary_parts[0] if summary_parts else "；".join(events)
    ending_parts = grouped["scene_ending"]
    scene_ending = ending_parts[-1] if ending_parts else (events[-1] if events else "")
    return _validated_content(
        summary_text,
        events,
        _dedupe(grouped["character"]),
        _dedupe(grouped["foreshadowing"]),
        scene_ending,
    )


def _validated_content(
    summary_text: object,
    events: list[str],
    characters: list[str],
    foreshadowing: list[str],
    scene_ending: object,
) -> dict:
    if not isinstance(summary_text, str) or len(summary_text.strip()) < 20:
        raise MemoryValidationError("facts 中没有足够的摘要或事件事实")
    if not events:
        # 摘要本身也是模型内容，可安全作为单个关键事件使用。
        events = [summary_text.strip()]
    if not isinstance(scene_ending, str) or len(scene_ending.strip()) < 10:
        raise MemoryValidationError("facts 中没有足够的结尾场景事实")
    return {
        "summary_text": summary_text.strip(),
        "events": _dedupe(events),
        "characters_present": _dedupe(characters),
        "new_foreshadowing": _dedupe(foreshadowing),
        "scene_ending": scene_ending.strip(),
    }


def _fact_strings(value: object, field: str) -> list[str]:
    """兼容字符串数组以及 {text/content/value: ...} 事实数组。"""
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        raise MemoryValidationError(f"{field} 不是字符串或数组")
    result: list[str] = []
    for pos, item in enumerate(value):
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            candidate = item.get("text", item.get("content", item.get("value")))
            text = candidate.strip() if isinstance(candidate, str) else ""
        else:
            text = ""
        if not text:
            raise MemoryValidationError(f"{field}[{pos}] 没有文本内容")
        result.append(text)
    return _dedupe(result)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = _norm(value)
        if key and key not in seen:
            result.append(value)
            seen.add(key)
    return result


def _normalize_changes(changes: dict) -> dict:
    result: dict = {}
    for key in ("timeline", "protagonist_tier", "protagonist_location"):
        value = changes.get(key)
        if value is not None and not isinstance(value, str):
            raise MemoryValidationError(
                f"facts.state_changes.{key} 必须是字符串或 null"
            )
        result[key] = (
            value.strip()
            if isinstance(value, str) and value.strip()
            else None
        )

    raw_updates = changes.get("character_updates", [])
    if not isinstance(raw_updates, list):
        raise MemoryValidationError(
            "facts.state_changes.character_updates 不是数组"
        )
    updates: list[dict] = []
    for pos, update in enumerate(raw_updates):
        if not isinstance(update, dict):
            raise MemoryValidationError(
                f"character_updates[{pos}] 不是对象"
            )
        name = update.get("name")
        if not isinstance(name, str) or not name.strip():
            raise MemoryValidationError(
                f"character_updates[{pos}].name 为空"
            )
        normalized = {"name": name.strip()}
        for key in ("power_tier", "status", "location", "note"):
            value = update.get(key)
            if value is not None and not isinstance(value, str):
                raise MemoryValidationError(
                    f"character_updates[{pos}].{key} 必须是字符串或 null"
                )
            if isinstance(value, str) and value.strip():
                normalized[key] = value.strip()
        updates.append(normalized)
    result["character_updates"] = updates

    for key in (
        "items_add", "items_remove", "open_threads_add",
        "open_threads_resolve", "foreshadowing_resolve",
    ):
        result[key] = _string_list(
            changes.get(key, []), f"facts.state_changes.{key}"
        )
    return result


def _build_summary(
    facts: dict, *, index: int, chapter_title: str
) -> ChapterSummary:
    # 模型即使输出了同名字段，也无法改变 index/title/schema。
    return ChapterSummary(
        index=index,
        title=chapter_title,
        summary=facts["summary_text"],
        events=list(facts["events"]),
        characters=list(facts["characters_present"]),
        foreshadowing=list(facts["new_foreshadowing"]),
        scene_ending=facts["scene_ending"],
    )


def _merge_world_state(
    prev_state: WorldState,
    facts: dict,
    *,
    index: int,
    summary: ChapterSummary,
) -> WorldState:
    """复制旧状态，只应用模型明确给出的增量。"""
    plain = _to_plain(prev_state)
    state = dict(plain) if isinstance(plain, dict) else {}
    state["last_chapter"] = index
    state.setdefault("timeline", "")
    state.setdefault("protagonist_tier", "")
    state.setdefault("protagonist_location", "")
    for key in ("characters", "items", "open_threads", "foreshadowing"):
        if not isinstance(state.get(key), list):
            state[key] = []

    changes = facts["state_changes"]
    for key in ("timeline", "protagonist_tier", "protagonist_location"):
        if changes.get(key):
            state[key] = changes[key]

    _merge_characters(state["characters"], changes["character_updates"])
    _merge_strings(
        state["items"],
        additions=changes["items_add"],
        removals=changes["items_remove"],
    )
    _merge_threads(
        state["open_threads"],
        additions=changes["open_threads_add"],
        removals=changes["open_threads_resolve"],
        chapter=index,
    )
    _merge_threads(
        state["foreshadowing"],
        additions=summary.foreshadowing,
        removals=changes["foreshadowing_resolve"],
        chapter=index,
    )
    return WorldState.from_dict(state)


def _merge_characters(characters: list, updates: list[dict]) -> None:
    positions = {
        str(item.get("name", "")).strip(): pos
        for pos, item in enumerate(characters)
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    }
    for update in updates:
        name = update["name"]
        if name in positions:
            target = characters[positions[name]]
        else:
            target = {
                "name": name,
                "power_tier": "",
                "status": "存活",
                "location": "",
                "note": "",
            }
            characters.append(target)
            positions[name] = len(characters) - 1
        for key in ("power_tier", "status", "location", "note"):
            if key in update:
                target[key] = update[key]


def _merge_strings(
    values: list, *, additions: list[str], removals: list[str]
) -> None:
    remove_keys = {_norm(value) for value in removals}
    values[:] = [value for value in values if _norm(value) not in remove_keys]
    existing = {_norm(value) for value in values}
    for value in additions:
        key = _norm(value)
        if key and key not in existing:
            values.append(value)
            existing.add(key)


def _merge_threads(
    values: list,
    *,
    additions: list[str],
    removals: list[str],
    chapter: int,
) -> None:
    remove_keys = {_norm(value) for value in removals}
    values[:] = [
        value for value in values
        if _norm(_thread_text(value)) not in remove_keys
    ]
    existing = {_norm(_thread_text(value)) for value in values}
    for value in additions:
        key = _norm(value)
        if key and key not in existing:
            values.append({"text": value, "planted_chapter": chapter})
            existing.add(key)


def _thread_text(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("text", ""))
    return str(value)


def _norm(value: object) -> str:
    return "".join(str(value).split())


def _string_list(
    value: object, field: str, *, required: bool = False
) -> list[str]:
    if not isinstance(value, list):
        raise MemoryValidationError(f"{field} 不是数组")
    result: list[str] = []
    seen: set[str] = set()
    for pos, item in enumerate(value):
        if not isinstance(item, str):
            raise MemoryValidationError(f"{field}[{pos}] 不是字符串")
        text = item.strip()
        key = _norm(text)
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    if required and not result:
        raise MemoryValidationError(f"{field} 为空")
    return result


def _diagnostic_payload(data: object, *, limit: int = 6000) -> str:
    try:
        value = json.dumps(data, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        value = repr(data)
    if len(value) > limit:
        value = value[:limit] + " ...truncated"
    return value


def _top_level_shape(data: object) -> str:
    if isinstance(data, dict):
        return "顶层字段：" + ", ".join(map(str, data.keys()))
    return f"顶层类型：{type(data).__name__}"
