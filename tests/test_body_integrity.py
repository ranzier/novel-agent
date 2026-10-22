from __future__ import annotations

import unittest

from novel_agent.editor import body_integrity_checks


class BodyIntegrityTests(unittest.TestCase):
    def test_complete_quoted_ending_passes(self) -> None:
        body = "赵铁山问：“接下来怎么办？”"
        self.assertEqual(body_integrity_checks(index=1, body=body), [])

    def test_unclosed_quote_is_rejected(self) -> None:
        issues = body_integrity_checks(index=1, body="赵铁山问：“接下来怎么办？")
        self.assertTrue(any("未成对" in issue.message for issue in issues))

    def test_incomplete_chapter_tail_is_detected_as_truncated(self) -> None:
        body = "回到城墙根，赵铁山再也压不住火"
        issues = body_integrity_checks(index=7, body=body)
        self.assertTrue(any("疑似生成被截断" in issue.message for issue in issues))


if __name__ == "__main__":
    unittest.main()
