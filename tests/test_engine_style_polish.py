from __future__ import annotations

import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from novel_agent.editor.style_polisher import PolishStats
from novel_agent.engine import write_one_chapter
from novel_agent.memory import MemoryValidationError


class FakeOutline:
    def chapter(self, index: int):
        return SimpleNamespace(
            index=index, title="测试章", summary="细纲", goal="推进剧情"
        )


class FakeProject:
    def __init__(self, root: Path):
        self.root = root
        self.saved_content = ""
        self.summary = None
        self.state = None
        self.reviews: list[dict] = []

    def load_bible(self):
        return SimpleNamespace(title="测试书", progression_label="境界")

    def load_characters(self):
        return SimpleNamespace()

    def load_state(self):
        return SimpleNamespace()

    def load_outline(self):
        return FakeOutline()

    def write_chapter(self, chapter: int, content: str):
        self.saved_content = content
        return self.root / f"ch{chapter:04d}.md"

    def upsert_summary(self, summary):
        self.summary = summary

    def save_state(self, state):
        self.state = state

    def sync_outline_from_summary(self, summary):
        return False

    def load_summaries(self):
        return []

    def save_characters(self, book):
        return None

    def save_review(self, review):
        self.reviews.append(review)


class FakePolisher:
    def polish_chapter(self, text: str):
        return "Qwen最终正文。", PolishStats(eligible=1, changed=1)


class EngineStylePolishTests(unittest.TestCase):
    def test_polished_text_is_used_for_memory_and_persistence(self) -> None:
        consolidated_bodies: list[str] = []
        summary = SimpleNamespace(summary="摘要", index=1)
        state = SimpleNamespace(
            protagonist_tier="一阶", foreshadowing=[], characters=[]
        )

        def consolidate(*args, **kwargs):
            consolidated_bodies.append(kwargs["body"])
            return summary, state

        beat = SimpleNamespace(
            beat_type=SimpleNamespace(value="铺垫"),
            tension=1,
            expect_cool_point=False,
            as_block=lambda: "节拍",
        )
        gateway = SimpleNamespace(
            config=SimpleNamespace(style_polish_enabled=True)
        )

        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            stack.enter_context(
                patch("novel_agent.engine.compute_beat", return_value=beat)
            )
            stack.enter_context(patch(
                "novel_agent.engine.chapter_writer.write_chapter",
                return_value="Claude初稿。",
            ))
            stack.enter_context(patch(
                "novel_agent.editor.StylePolisher.from_config",
                return_value=FakePolisher(),
            ))
            stack.enter_context(patch(
                "novel_agent.memory.consolidate", side_effect=consolidate
            ))
            stack.enter_context(patch(
                "novel_agent.memory.promote_characters", return_value=[]
            ))
            project = FakeProject(Path(tmp))
            result = write_one_chapter(
                gateway, project, chapter=1, title="测试章", words=1000,
                consolidate_mem=True, do_review=False, max_rewrites=0,
                use_vector=False, reporter=QuietReporter(),
            )

        self.assertEqual(consolidated_bodies, ["Qwen最终正文。"])
        self.assertIn("Qwen最终正文。", project.saved_content)
        self.assertNotIn("Claude初稿。", project.saved_content)
        self.assertEqual(result["text"], "Qwen最终正文。")
        self.assertEqual(result["polish"]["changed"], 1)

    def test_truncated_body_is_saved_but_never_consolidated(self) -> None:
        beat = fake_beat()
        gateway = SimpleNamespace(
            config=SimpleNamespace(style_polish_enabled=False)
        )

        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            stack.enter_context(
                patch("novel_agent.engine.compute_beat", return_value=beat)
            )
            stack.enter_context(patch(
                "novel_agent.engine.chapter_writer.write_chapter",
                return_value="回到城墙根，赵铁山再也压不住火",
            ))
            consolidate_mock = stack.enter_context(patch(
                "novel_agent.memory.consolidate"
            ))
            project = FakeProject(Path(tmp))
            result = write_one_chapter(
                gateway, project, chapter=7, title="以寡御众", words=3000,
                consolidate_mem=True, do_review=True, max_rewrites=0,
                use_vector=False, reporter=QuietReporter(),
            )

        consolidate_mock.assert_not_called()
        self.assertIn("赵铁山再也压不住火", project.saved_content)
        self.assertIsNone(project.summary)
        self.assertIsNone(project.state)
        self.assertTrue(result["has_errors"])
        self.assertEqual(project.reviews[0]["issues"][0]["category"], "完整性")

    def test_invalid_memory_is_not_committed_or_rewritten(self) -> None:
        gateway = SimpleNamespace(
            config=SimpleNamespace(style_polish_enabled=False)
        )
        writer_calls: list[str] = []

        def write_body(*args, **kwargs):
            writer_calls.append("called")
            return "秦烈收拢众人，命他们守住城门。"

        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            stack.enter_context(patch(
                "novel_agent.engine.compute_beat", return_value=fake_beat()
            ))
            stack.enter_context(patch(
                "novel_agent.engine.chapter_writer.write_chapter",
                side_effect=write_body,
            ))
            stack.enter_context(patch(
                "novel_agent.memory.consolidate",
                side_effect=MemoryValidationError("summary.summary 为空或过短"),
            ))
            project = FakeProject(Path(tmp))
            result = write_one_chapter(
                gateway, project, chapter=7, title="以寡御众", words=3000,
                consolidate_mem=True, do_review=True, max_rewrites=2,
                use_vector=False, reporter=QuietReporter(),
            )

        self.assertEqual(len(writer_calls), 1)
        self.assertIsNone(project.summary)
        self.assertIsNone(project.state)
        self.assertTrue(result["has_errors"])
        self.assertEqual(project.reviews[0]["issues"][0]["category"], "记忆固化")


def fake_beat():
    return SimpleNamespace(
        beat_type=SimpleNamespace(value="铺垫"),
        tension=1,
        expect_cool_point=False,
        as_block=lambda: "节拍",
    )


class QuietReporter:
    def step(self, message: str, **data): pass
    def info(self, message: str, **data): pass
    def warn(self, message: str, **data): pass
    def error(self, message: str, **data): pass
    def done(self, message: str = "", **data): pass
    def delta(self, text: str): pass


if __name__ == "__main__":
    unittest.main()
