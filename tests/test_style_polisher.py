from __future__ import annotations

import unittest

from novel_agent.editor.style_polisher import (
    INSTRUCTION,
    SYSTEM_PROMPT,
    StylePolisher,
    validate_rewrite,
)


class FakeEditor:
    def __init__(self, outputs: dict[str, str | Exception]):
        self.outputs = outputs
        self.inputs: list[str] = []

    def check_available(self) -> None:
        return None

    def rewrite(self, paragraph: str) -> str:
        self.inputs.append(paragraph)
        output = self.outputs.get(paragraph, paragraph)
        if isinstance(output, Exception):
            raise output
        return output


class UnavailableEditor(FakeEditor):
    def check_available(self) -> None:
        raise RuntimeError("offline")


class StylePolisherTests(unittest.TestCase):
    def test_prompts_match_training_contract(self) -> None:
        self.assertIn("中文网络小说局部编辑器", SYSTEM_PROMPT)
        self.assertEqual(
            INSTRUCTION,
            "请对以下文本进行最小必要的去AI腔改写；仅在确有必要时修改，原文自然则保持原样。",
        )

    def test_preserves_layout_and_rolls_back_unsafe_paragraph(self) -> None:
        safe = "戍卒们围拢过来，七嘴八舌，又惊又喜。"
        unsafe = "李恒带着三十名戍卒赶到横浦关。"
        text = f"短句。\n\n{safe}\n\n---\n\n{unsafe}"
        editor = FakeEditor({
            safe: "戍卒们围拢上来，七嘴八舌地嚷着，又惊又喜。",
            unsafe: "李恒带着二十名戍卒赶到横浦关。",
        })
        polisher = StylePolisher(
            editor, protected_terms={"李恒", "横浦关"}, min_chars=15, max_chars=220
        )

        output, stats = polisher.polish_chapter(text)

        self.assertEqual(
            output,
            f"短句。\n\n戍卒们围拢上来，七嘴八舌地嚷着，又惊又喜。\n\n---\n\n{unsafe}",
        )
        self.assertEqual(stats.changed, 1)
        self.assertEqual(stats.rolled_back, 1)
        self.assertEqual(stats.skipped, 2)
        self.assertEqual(stats.reasons, {"numeric_token_changed": 1, "quantity_token_changed": 1})

    def test_paragraph_exception_uses_original(self) -> None:
        source = "他沿着泥泞的官道向前走去，脚步始终没有停下。"
        output, stats = StylePolisher(
            FakeEditor({source: RuntimeError("boom")})
        ).polish_chapter(source)
        self.assertEqual(output, source)
        self.assertEqual(stats.failed, 1)

    def test_service_failure_is_reported_to_caller(self) -> None:
        source = "他沿着泥泞的官道向前走去，脚步始终没有停下。"
        with self.assertRaisesRegex(RuntimeError, "offline"):
            StylePolisher(UnavailableEditor({})).polish_chapter(source)

    def test_validation_allows_training_example_style_changes(self) -> None:
        source = "这些日子，一点一点，全攒在这一刻里。"
        output = "这些日子，一点点，全攒到了这一刻。"
        self.assertEqual(validate_rewrite(source, output), ())

    def test_validation_rejects_fact_and_format_changes(self) -> None:
        source = "“军功。”李恒道，“斩首三级，可抵一条死罪。”"
        self.assertIn(
            "numeric_token_changed",
            validate_rewrite(source, "“军功。”李恒道，“斩首二级，可抵一条死罪。”"),
        )
        self.assertIn(
            "named_term_lost",
            validate_rewrite(source, "“军功。”他道，“斩首三级，可抵一条死罪。”", {"李恒"}),
        )
        self.assertIn(
            "metadata_or_reasoning",
            validate_rewrite(source, "改写结果：军功可抵罪。"),
        )


if __name__ == "__main__":
    unittest.main()
