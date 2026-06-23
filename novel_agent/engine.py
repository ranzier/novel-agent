"""核心写作编排：写 + 召回 + 节奏 + 固化 + 校验 + 重写 + 索引。

独立于 CLI 与 Web，只依赖 Reporter 上报进度。CLI 传 ConsoleReporter，
Web 传 QueueReporter。这样同一套闭环逻辑两端复用，不重复。
"""

from __future__ import annotations

from .generate import chapter_writer
from .generate.pacing import compute_beat
from .llm import LLMError, LLMGateway
from .project import Project
from .reporting import ConsoleReporter, Reporter


def write_one_chapter(
    gateway: LLMGateway,
    project: Project,
    *,
    chapter: int,
    title: str,
    words: int,
    consolidate_mem: bool,
    do_review: bool,
    max_rewrites: int,
    use_vector: bool = True,
    reporter: Reporter | None = None,
) -> dict | None:
    """写一章的完整闭环。成功返回结果字典，失败返回 None。"""
    rep = reporter or ConsoleReporter()
    from .editor import review_chapter
    from .memory import consolidate, index_chapter, recall_block

    bible = project.load_bible()
    characters = project.load_characters()
    prev_state = project.load_state()
    ch = project.load_outline().chapter(chapter)

    # 向量召回：有 key 且未禁用时启用，缺 key 静默降级
    embedder = store = None
    recall_text = ""
    if use_vector:
        try:
            from .memory import Embedder

            embedder = Embedder(gateway.config)
            store = project.vector_store(embedder.dim)
        except RuntimeError:
            embedder = store = None
        if embedder is not None and store is not None and ch is not None:
            query = f"{ch.title}。{ch.summary} {ch.goal}"
            try:
                rep.step("向量召回相关历史片段")
                recall_text = recall_block(
                    store, embedder, query=query, before_chapter=chapter
                )
                if recall_text:
                    rep.info(f"召回 {recall_text.count('· [')} 段相关历史片段")
            except Exception as e:  # noqa: BLE001
                rep.warn(f"向量召回失败（已跳过）：{e}")
                recall_text = ""

    # 节奏引擎
    beat = compute_beat(project.load_outline(), chapter)
    pacing_text = beat.as_block()
    rep.info(
        f"节拍：{beat.beat_type.value}（紧张度 {beat.tension}/5）"
        + ("，应兑现爽点" if beat.expect_cool_point else ""),
        beat=beat.beat_type.value,
        tension=beat.tension,
    )

    revision_note = ""
    attempt = 0
    text = ""
    summary = new_state = None
    review = None

    while True:
        attempt += 1
        rep.step(
            ("重写" if revision_note else "写作")
            + f"第 {chapter} 章《{title}》（第 {attempt} 稿）",
            attempt=attempt,
        )
        try:
            text = chapter_writer.write_chapter(
                gateway, project, index=chapter, words=words,
                revision_note=revision_note, recall_text=recall_text,
                pacing_text=pacing_text,
            )
        except (LLMError, ValueError) as e:
            rep.error(f"写作失败：{e}")
            return None

        if consolidate_mem or do_review:
            rep.step("抽取摘要 / 更新世界状态")
            try:
                summary, new_state = consolidate(
                    gateway, title=bible.title, index=chapter,
                    chapter_title=title, body=text, prev_state=prev_state,
                )
            except LLMError as e:
                rep.warn(f"记忆固化失败：{e}")
                summary = new_state = None

        review = None
        if do_review and summary is not None and new_state is not None:
            rep.step("一致性校验")
            review = review_chapter(
                gateway, bible=bible, characters=characters,
                prev_state=prev_state, new_summary=summary,
                new_state=new_state, body=text,
            )

        if review is not None and review.has_errors and attempt <= max_rewrites:
            notes = "\n".join(f"- [{i.category}] {i.message}" for i in review.errors)
            rep.warn(f"发现 {len(review.errors)} 处硬伤，正在重写：\n{notes}")
            revision_note = notes
            continue
        break

    # 落盘
    content = f"# 第 {chapter} 章　{title}\n\n{text}\n"
    path = project.write_chapter(chapter, content)
    rep.done(
        f"第 {chapter} 章《{title}》已写完（约 {len(text)} 字）",
        chapter=chapter, chars=len(text), path=str(path),
    )

    has_unresolved_errors = review is not None and review.has_errors

    # 固化入库：有未解决硬伤则不写进记忆，保留上一章干净状态
    if consolidate_mem and new_state is not None and not has_unresolved_errors:
        project.upsert_summary(summary)
        project.save_state(new_state)
        tier = new_state.protagonist_tier or "—"
        fore = len(new_state.foreshadowing)
        dead = [c.name for c in new_state.characters if c.status == "死亡"]
        rep.info(
            f"记忆已更新：主角境界 {tier}；未回收伏笔 {fore} 条"
            + (f"；已故 {'、'.join(dead)}" if dead else "")
        )

    # 校验结果
    if review is not None:
        project.save_review(review.to_dict())
        if review.has_errors:
            rep.warn(f"仍存 {len(review.errors)} 处硬伤（重写额度已用尽，请人工处理）：")
            for i in review.errors:
                rep.warn(f"· [{i.category}] {i.message}")
            if consolidate_mem:
                rep.warn("→ 记忆未更新（保留上一章干净状态）。请修正后重写本章。")
        if review.warnings:
            rep.info(f"提示 {len(review.warnings)} 处疑点：")
            for i in review.warnings:
                rep.info(f"· [{i.category}] {i.message}")
        if not review.issues:
            rep.info("一致性校验通过，无矛盾")

    # 索引
    if store is not None and embedder is not None and not has_unresolved_errors:
        try:
            rep.step("索引到向量库")
            n = index_chapter(store, embedder, chapter=chapter, text=text)
            rep.info(f"已索引 {n} 段到向量库（共 {store.size} 段）")
        except Exception as e:  # noqa: BLE001
            rep.warn(f"向量索引失败（已跳过）：{e}")

    return {
        "chapter": chapter,
        "text": text,
        "review": review.to_dict() if review is not None else None,
        "has_errors": has_unresolved_errors,
        "chars": len(text),
    }
