from __future__ import annotations

import unittest

from novel_agent.memory import (
    MemoryValidationError,
    WorldState,
    consolidate,
    extract_summary_only,
)


class FakeGateway:
    def __init__(self, payload):
        self.payloads = list(payload) if isinstance(payload, list) else [payload]
        self.calls = []

    def complete_json(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.payloads.pop(0)


def facts_payload(*, with_changes: bool = True) -> dict:
    facts = {
        "summary_text": "秦烈整顿城中兵马，并与众人商定守城方略，为接下来的战事做好准备。",
        "events": ["秦烈整顿兵马并部署守城"],
        "characters_present": ["秦烈", "赵铁山"],
        "new_foreshadowing": ["清军偏师即将逼近宁远城"],
        "scene_ending": "宁远城墙下，秦烈与众人完成部署，等待下一步军令。",
    }
    if with_changes:
        facts["state_changes"] = {
            "timeline": "崇祯十五年春次日",
            "protagonist_tier": None,
            "protagonist_location": "宁远城墙下",
            "character_updates": [
                {
                    "name": "秦烈",
                    "power_tier": None,
                    "status": None,
                    "location": "宁远城墙下",
                    "note": "正在部署守城",
                },
                {
                    "name": "赵铁山",
                    "power_tier": None,
                    "status": "存活",
                    "location": "宁远城墙下",
                    "note": None,
                },
            ],
            "items_add": ["守城军令"],
            "items_remove": ["旧令牌"],
            "open_threads_add": ["抵御逼近宁远的清军偏师"],
            "open_threads_resolve": ["查明城门异动"],
            "foreshadowing_resolve": ["旧伏笔"],
        }
    return {"facts": facts}


def previous_state() -> WorldState:
    return WorldState.from_dict({
        "last_chapter": 6,
        "timeline": "崇祯十五年春",
        "protagonist_tier": "试百户",
        "protagonist_location": "宁远城",
        "characters": [{
            "name": "秦烈",
            "power_tier": "试百户",
            "status": "存活",
            "location": "宁远城",
            "note": "右肩有伤",
        }],
        "items": ["旧令牌", "火药"],
        "open_threads": [
            {"text": "查明城门异动", "planted_chapter": 5},
            {"text": "保住匠户班底", "planted_chapter": 6},
        ],
        "foreshadowing": [
            {"text": "旧伏笔", "planted_chapter": 3},
            {"text": "钱文焕暗中提防秦烈", "planted_chapter": 6},
        ],
    })


class MemoryValidationTests(unittest.TestCase):
    def test_program_constructs_schema_and_merges_explicit_changes(self) -> None:
        summary, state = consolidate(
            FakeGateway(facts_payload()),
            title="南明北伐录",
            index=7,
            chapter_title="以寡御众",
            body="完整正文。",
            prev_state=previous_state(),
        )

        self.assertEqual(summary.index, 7)
        self.assertEqual(summary.title, "以寡御众")
        self.assertEqual(summary.events, ["秦烈整顿兵马并部署守城"])
        self.assertEqual(state.last_chapter, 7)
        self.assertEqual(state.protagonist_tier, "试百户")
        self.assertEqual(state.protagonist_location, "宁远城墙下")
        self.assertEqual(state.character("秦烈").power_tier, "试百户")
        self.assertEqual(state.character("秦烈").note, "正在部署守城")
        self.assertEqual(state.character("赵铁山").status, "存活")
        self.assertEqual(state.items, ["火药", "守城军令"])
        self.assertEqual(
            [thread.text for thread in state.open_threads],
            ["保住匠户班底", "抵御逼近宁远的清军偏师"],
        )
        self.assertEqual(state.open_threads[-1].planted_chapter, 7)
        self.assertEqual(
            [thread.text for thread in state.foreshadowing],
            ["钱文焕暗中提防秦烈", "清军偏师即将逼近宁远城"],
        )

    def test_omitted_changes_cannot_erase_old_state(self) -> None:
        payload = facts_payload()
        payload["facts"]["state_changes"] = {
            "timeline": None,
            "protagonist_tier": None,
            "protagonist_location": None,
            "character_updates": [],
            "items_add": [],
            "items_remove": [],
            "open_threads_add": [],
            "open_threads_resolve": [],
            "foreshadowing_resolve": [],
        }
        _summary, state = consolidate(
            FakeGateway(payload),
            title="南明北伐录",
            index=7,
            chapter_title="以寡御众",
            body="完整正文。",
            prev_state=previous_state(),
        )

        self.assertEqual(state.items, ["旧令牌", "火药"])
        self.assertEqual(state.character("秦烈").note, "右肩有伤")
        self.assertEqual(
            [thread.text for thread in state.open_threads],
            ["查明城门异动", "保住匠户班底"],
        )
        self.assertIn("钱文焕暗中提防秦烈", [x.text for x in state.foreshadowing])

    def test_model_cannot_override_program_owned_chapter_fields(self) -> None:
        payload = facts_payload()
        payload["facts"].update({
            "index": 999,
            "title": "错误标题",
            "last_chapter": 999,
        })
        summary, state = consolidate(
            FakeGateway(payload),
            title="南明北伐录",
            index=7,
            chapter_title="以寡御众",
            body="完整正文。",
            prev_state=previous_state(),
        )
        self.assertEqual(summary.index, 7)
        self.assertEqual(summary.title, "以寡御众")
        self.assertEqual(state.last_chapter, 7)

    def test_accepts_direct_facts_object_without_wrapper(self) -> None:
        payload = facts_payload()["facts"]
        summary, state = consolidate(
            FakeGateway(payload),
            title="南明北伐录",
            index=7,
            chapter_title="以寡御众",
            body="完整正文。",
            prev_state=previous_state(),
        )
        self.assertEqual(summary.index, 7)
        self.assertEqual(state.last_chapter, 7)

    def test_accepts_fact_list_with_sibling_state_changes(self) -> None:
        payload = {
            "facts": [
                {
                    "type": "summary",
                    "text": "秦烈清点城中兵马，重新分配守城位置，并命众人防备即将到来的清军偏师。",
                },
                {"type": "event", "text": "秦烈完成守城兵力部署。"},
                {"type": "character", "text": "秦烈"},
                {
                    "type": "scene_ending",
                    "text": "宁远城墙下，秦烈完成部署，等待下一步军令。",
                },
            ],
            "state_changes": {
                "protagonist_location": "宁远城墙下",
                "open_threads_add": ["抵御逼近宁远的清军偏师"],
            },
        }
        summary, state = consolidate(
            FakeGateway(payload),
            title="南明北伐录",
            index=7,
            chapter_title="以寡御众",
            body="完整正文。",
            prev_state=previous_state(),
        )

        self.assertEqual(summary.characters, ["秦烈"])
        self.assertEqual(state.protagonist_location, "宁远城墙下")
        self.assertEqual(state.items, ["旧令牌", "火药"])

    def test_custom_fact_fields_are_composed_from_returned_text(self) -> None:
        payload = {
            "facts": {
                "本章事实": [
                    "秦烈清点城中兵马，重新分配城墙各段守军。",
                    "赵铁山领命前往北门，准备接应后续军令。",
                ],
                "收束场景": {
                    "description": "宁远城墙下，秦烈目送赵铁山离开，继续等候军报。"
                },
            },
            "state_changes": {},
        }
        summary, state = consolidate(
            FakeGateway(payload),
            title="南明北伐录",
            index=7,
            chapter_title="以寡御众",
            body="完整正文。",
            prev_state=previous_state(),
        )

        self.assertIn("秦烈清点城中兵马", summary.summary)
        self.assertEqual(
            summary.scene_ending,
            "宁远城墙下，秦烈目送赵铁山离开，继续等候军报。",
        )
        self.assertEqual(state.last_chapter, 7)
        self.assertEqual(state.items, ["旧令牌", "火药"])

    def test_invalid_facts_are_retried_once(self) -> None:
        gateway = FakeGateway([
            {"facts": {"summary_text": "太短"}},
            facts_payload(),
        ])
        summary, state = consolidate(
            gateway,
            title="南明北伐录",
            index=7,
            chapter_title="以寡御众",
            body="完整正文。",
            prev_state=previous_state(),
        )
        self.assertEqual(len(gateway.calls), 2)
        self.assertIn("【原始任务】", gateway.calls[1][0][0])
        self.assertEqual(summary.index, 7)
        self.assertEqual(state.last_chapter, 7)

    def test_invalid_facts_after_repair_are_rejected(self) -> None:
        with self.assertRaises(MemoryValidationError):
            consolidate(
                FakeGateway([{"facts": {}}, {"facts": {}}]),
                title="南明北伐录",
                index=7,
                chapter_title="以寡御众",
                body="完整正文。",
                prev_state=previous_state(),
            )

    def test_summary_only_uses_program_owned_schema(self) -> None:
        payload = facts_payload(with_changes=False)
        payload["facts"]["index"] = 999
        summary = extract_summary_only(
            FakeGateway(payload),
            title="南明北伐录",
            index=7,
            chapter_title="以寡御众",
            body="完整正文。",
        )
        self.assertEqual(summary.index, 7)
        self.assertEqual(summary.title, "以寡御众")


if __name__ == "__main__":
    unittest.main()
