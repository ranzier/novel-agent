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
    use_style_polish: bool | None = None,
    author_note: str = "",
    update_world_state: bool = True,
    reporter: Reporter | None = None,
) -> dict | None:
    """写一章的完整闭环。成功返回结果字典，失败返回 None。

    update_world_state=False 时跳过 state.json 的覆盖（其余记忆照常更新）。
    用于重写非最新章：避免用旧章状态覆盖反映后续进度的世界快照。
    """
    rep = reporter or ConsoleReporter()
    from .editor import (
        Issue, ReviewResult, Severity, body_integrity_checks, review_chapter,
    )
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
                    store, embedder, query=query, before_chapter=chapter,
                    exclude_recent=gateway.config.recent_chapters,
                    top_k=gateway.config.recall_top_k,
                    min_score=gateway.config.recall_min_score,
                )
                if recall_text:
                    rep.info(f"召回 {recall_text.count('· [')} 段相关历史片段")
                    # 把召回的具体内容发出来，便于在前端展开查看
                    rep.info(recall_text)
                else:
                    rep.info("无相关历史片段（开篇阶段或语义不匹配）")
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
    polish_stats = None
    polisher = None
    polish_enabled = (
        gateway.config.style_polish_enabled
        if use_style_polish is None
        else use_style_polish
    )
    if polish_enabled:
        from .editor import PolishStats, StylePolisher

        try:
            polisher = StylePolisher.from_config(gateway.config, project)
        except Exception as e:  # noqa: BLE001 - 配置/初始化失败也必须安全降级
            polish_stats = PolishStats(service_error=str(e))
            rep.warn(f"本地去 AI 腔初始化失败，本章将保留 Claude 初稿：{e}")

    while True:
        attempt += 1
        # 每一稿都是独立候选稿，不能沿用上一稿的抽取或校验结果。
        summary = new_state = None
        review = None
        rep.step(
            ("重写" if revision_note else "写作")
            + f"第 {chapter} 章《{title}》（第 {attempt} 稿）",
            attempt=attempt,
        )
        try:
            text = chapter_writer.write_chapter(
                gateway, project, index=chapter, words=words,
                revision_note=revision_note, recall_text=recall_text,
                pacing_text=pacing_text, author_note=author_note,
                on_delta=getattr(rep, "delta", None),
            )
        except (LLMError, ValueError) as e:
            rep.error(f"写作失败：{e}")
            return None

        # 语言后处理必须在记忆抽取和一致性校验之前。单段失败由
        # StylePolisher 回退原段；服务整体不可用时保留整章 Claude 初稿。
        if polisher is not None:
            rep.step("本地 Qwen 正在按段落去 AI 腔")
            try:
                text, polish_stats = polisher.polish_chapter(text)
                stats = polish_stats.as_dict()
                rep.info(
                    f"去 AI 腔完成：改写 {stats['changed']} 段，"
                    f"原样保留 {stats['unchanged']} 段，"
                    f"安全回退 {stats['rolled_back'] + stats['failed']} 段"
                )
                if stats["reasons"]:
                    rep.info(
                        "回退原因："
                        + "、".join(
                            f"{reason} {count}"
                            for reason, count in stats["reasons"].items()
                        )
                    )
            except Exception as e:  # noqa: BLE001 - 本地编辑不得阻断写章
                from .editor.style_polisher import PolishStats

                polish_stats = PolishStats(service_error=str(e))
                rep.warn(f"本地去 AI 腔不可用，已保留 Claude 初稿：{e}")
                polisher = None

        # 正文末尾截断、引号未闭合等结构性硬伤必须在摘要调用前发现。
        # 否则抽取器可能基于残稿返回空对象，并被误当成成功状态提交。
        integrity_issues = body_integrity_checks(index=chapter, body=text)
        if integrity_issues:
            review = ReviewResult(chapter=chapter, issues=integrity_issues)
            summary = new_state = None
            if attempt <= max_rewrites:
                notes = "\n".join(
                    f"- [{i.category}] {i.message}" for i in integrity_issues
                )
                rep.warn(f"正文疑似不完整，正在重写：\n{notes}")
                revision_note = notes
                continue
            break

        if consolidate_mem or do_review:
            rep.step("抽取摘要 / 更新世界状态")
            try:
                summary, new_state = consolidate(
                    gateway, title=bible.title, index=chapter,
                    chapter_title=title, body=text, prev_state=prev_state,
                    progression_label=bible.progression_label,
                )
                # 把抽取出的摘要发出来，便于前端展开查看
                if summary is not None and summary.summary:
                    rep.info(f"本章摘要：{summary.summary}")
            except LLMError as e:
                rep.warn(f"记忆固化失败：{e}")
                summary = new_state = None
                review = ReviewResult(
                    chapter=chapter,
                    issues=[Issue(
                        severity=Severity.ERROR,
                        category="记忆固化",
                        message=f"摘要或世界状态抽取无效，已阻止提交：{e}",
                        source="system",
                    )],
                )

        if do_review and summary is not None and new_state is not None:
            rep.step("一致性校验")
            review = review_chapter(
                gateway, bible=bible, characters=characters,
                prev_state=prev_state, new_summary=summary,
                new_state=new_state, body=text,
            )

        # 只有正文/设定硬伤才值得重写。抽取 API 或 payload 失败属于技术故障，
        # 重写正文无济于事，应保留正文并阻止记忆与索引提交。
        if (
            review is not None
            and review.has_errors
            and summary is not None
            and new_state is not None
            and attempt <= max_rewrites
        ):
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
    if (
        consolidate_mem
        and summary is not None
        and new_state is not None
        and not has_unresolved_errors
    ):
        project.upsert_summary(summary)
        if update_world_state:
            project.save_state(new_state)
        else:
            rep.info("重写的不是最新章，已跳过世界状态更新（state.json 保持不变）")
        # 用实际写出的内容回写大纲细纲，使大纲与正文一致
        try:
            if project.sync_outline_from_summary(summary):
                rep.info("已据正文更新本章大纲摘要")
        except Exception as e:  # noqa: BLE001 - 同步失败不影响主流程
            rep.warn(f"大纲摘要同步失败（已跳过）：{e}")
        if update_world_state:
            tier = new_state.protagonist_tier or "—"
            tier_label = bible.progression_label or "状态"
            fore = len(new_state.foreshadowing)
            dead = [c.name for c in new_state.characters if c.status == "死亡"]
            rep.info(
                f"记忆已更新：主角{tier_label} {tier}；未回收伏笔 {fore} 条"
                + (f"；已故 {'、'.join(dead)}" if dead else "")
            )

        # 角色库自动晋升：把反复出场且被状态追踪的新角色补进角色库
        from .memory import promote_characters

        try:
            book = project.load_characters()
            added = promote_characters(
                book, project.load_summaries(), new_state
            )
            if added:
                project.save_characters(book)
                rep.info(f"角色库新增：{'、'.join(added)}")
        except Exception as e:  # noqa: BLE001 - 晋升失败不影响主流程
            rep.warn(f"角色库自动收录失败（已跳过）：{e}")

    # 校验结果
    if review is not None:
        project.save_review(review.to_dict())
        if review.has_errors:
            memory_failed = any(
                issue.category == "记忆固化" for issue in review.errors
            )
            if memory_failed:
                rep.warn(
                    f"记忆固化存在 {len(review.errors)} 处错误，"
                    "正文已保存，但摘要、世界状态和向量索引均未提交："
                )
            else:
                rep.warn(
                    f"仍存 {len(review.errors)} 处硬伤"
                    "（重写额度已用尽，请人工处理）："
                )
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
    if (
        store is not None
        and embedder is not None
        and not has_unresolved_errors
        and (not consolidate_mem or (summary is not None and new_state is not None))
    ):
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
        "polish": polish_stats.as_dict() if polish_stats is not None else None,
    }
