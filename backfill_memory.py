"""一次性脚本：只为已存在的某章补记忆（摘要 / 世界状态 / 校验 / 向量索引），
不重新生成正文。用于正文已落盘但 consolidate 当时失败、记忆停在上一章的情况。

用法：
    .venv/bin/python backfill_memory.py <book_slug> <chapter_index>
例：
    .venv/bin/python backfill_memory.py "1642:南明北伐录" 6
"""

from __future__ import annotations

import re
import sys

from novel_agent.config import Config
from novel_agent.editor import review_chapter
from novel_agent.llm import LLMError, LLMGateway
from novel_agent.memory import consolidate, index_chapter
from novel_agent.project import Project


def strip_title_header(raw: str) -> str:
    """去掉 write_chapter 落盘时加的 '# 第 N 章　标题' 头，还原正文。"""
    lines = raw.splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        # 跳过标题行及其后的空行
        body = lines[1:]
        while body and not body[0].strip():
            body.pop(0)
        return "\n".join(body)
    return raw


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    slug, chapter = sys.argv[1], int(sys.argv[2])

    project = Project.open(slug)
    bible = project.load_bible()
    characters = project.load_characters()
    prev_state = project.load_state()
    outline = project.load_outline()

    ch = outline.chapter(chapter)
    if ch is None:
        print(f"大纲里没有第 {chapter} 章。")
        return 1

    raw = project.read_chapter(chapter)
    if raw is None:
        print(f"第 {chapter} 章正文不存在，无法补记忆。")
        return 1
    body = strip_title_header(raw)

    # 安全检查：确保当前记忆确实停在上一章，避免误覆盖
    if prev_state.last_chapter >= chapter:
        print(
            f"警告：当前 state.last_chapter={prev_state.last_chapter}，"
            f"不早于第 {chapter} 章。继续将覆盖已有记忆。"
        )
        if input("确认继续？(y/N) ").strip().lower() != "y":
            return 1

    gateway = LLMGateway(Config.load())

    print(f"[1/4] 抽取第 {chapter} 章摘要 / 世界状态 …")
    try:
        summary, new_state = consolidate(
            gateway, title=bible.title, index=chapter,
            chapter_title=ch.title, body=body, prev_state=prev_state,
            progression_label=bible.progression_label,
        )
    except LLMError as e:
        print(f"抽取失败：{e}")
        return 1
    print(f"  摘要：{summary.summary}")

    print(f"[2/4] 一致性校验 …")
    review = review_chapter(
        gateway, bible=bible, characters=characters,
        prev_state=prev_state, new_summary=summary,
        new_state=new_state, body=body,
    )
    project.save_review(review.to_dict())
    if review.has_errors:
        print(f"  发现 {len(review.errors)} 处硬伤（仅记录，不重写）：")
        for i in review.errors:
            print(f"    · [{i.category}] {i.message}")
    else:
        print("  无硬伤")

    print(f"[3/4] 写入摘要 / 世界状态 / 大纲同步 …")
    project.upsert_summary(summary)
    project.save_state(new_state)
    try:
        if project.sync_outline_from_summary(summary):
            print("  已据正文更新本章大纲摘要")
    except Exception as e:  # noqa: BLE001
        print(f"  大纲摘要同步失败（已跳过）：{e}")

    print(f"[4/4] 索引到向量库 …")
    try:
        from novel_agent.memory import Embedder

        embedder = Embedder(gateway.config)
        store = project.vector_store(embedder.dim)
        n = index_chapter(store, embedder, chapter=chapter, text=body)
        print(f"  已索引 {n} 段（共 {store.size} 段）")
    except Exception as e:  # noqa: BLE001
        print(f"  向量索引跳过：{e}")

    print(f"\n完成。记忆已推进到第 {chapter} 章。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
