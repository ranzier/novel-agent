"""命令行入口。

当前命令：
  novel version              显示版本
  novel ping                 测试 Claude 连通性
  novel init                 立项：创意 → 设定圣经 + 角色库
  novel outline              生成分层大纲（骨架 + 章节细纲）
  novel list                 列出所有项目
  novel status               查看某本书的进度
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import Config
from .engine import write_one_chapter
from .generate import ideation, outline_planner
from .generate import chapter_writer
from .llm import LLMError, LLMGateway
from .project import Project
from .reporting import ConsoleReporter

app = typer.Typer(
    name="novel",
    help="网文写作 Agent —— 半自动/自动写作长篇小说。",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


def _gateway() -> LLMGateway:
    try:
        return LLMGateway(Config.load())
    except RuntimeError as e:
        console.print(f"[bold red]配置错误：[/]{e}")
        raise typer.Exit(code=1)


@app.command()
def version() -> None:
    """显示版本。"""
    console.print(f"novel-agent [bold cyan]v{__version__}[/]")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="监听地址"),
    port: int = typer.Option(8000, "--port", "-p", help="监听端口"),
) -> None:
    """启动本地 Web 服务（浏览器界面）。

    开发期前端跑 `cd web && npm run dev`（:5173 自动代理到本服务）；
    交付期 `cd web && npm run build` 后，本命令直接托管静态前端。
    """
    import uvicorn

    from .server import create_app

    console.print(
        f"[green]✓[/] Web 服务启动：[bold]http://{host}:{port}[/]\n"
        f"[dim]开发前端：cd web && npm run dev（http://localhost:5173）[/]"
    )
    uvicorn.run(create_app(), host=host, port=port, log_level="info")


@app.command()
def ping(
    prompt: str = typer.Option(
        "用一句话证明你在线，并说出你的模型名。", "--prompt", "-p", help="测试用提示词"
    ),
) -> None:
    """测试与 Claude 的连通性，并打印 token 用量与成本。"""
    gateway = _gateway()
    console.print(f"[dim]模型：{gateway.config.model_for('write')}[/]")
    try:
        with console.status("正在调用 Claude…"):
            text = gateway.complete(prompt, max_tokens=256)
    except LLMError as e:
        console.print(f"[bold red]调用失败：[/]{e}")
        raise typer.Exit(code=1)
    console.print(f"\n[green]✓[/] {text}\n")
    console.print(f"[dim]{gateway.usage.summary()}[/]")


@app.command()
def init(
    idea: str = typer.Option(
        ..., "--idea", "-i", help="一句话创意，如：废柴觉醒吞噬天赋，靠吃怪物升级"
    ),
    genre: str = typer.Option("", "--genre", "-g", help="题材，如：玄幻/都市/系统流"),
    title: str = typer.Option("", "--title", "-t", help="书名（留空则用 AI 起的名）"),
) -> None:
    """立项：把创意扩展成设定圣经 + 初始角色库。"""
    gateway = _gateway()

    with console.status("正在设计设定圣经…"):
        try:
            bible = ideation.generate_bible(gateway, idea, genre)
        except LLMError as e:
            console.print(f"[bold red]生成失败：[/]{e}")
            raise typer.Exit(code=1)

    if title:
        bible.title = title

    with console.status("正在设计核心角色…"):
        try:
            characters = ideation.generate_characters(gateway, bible)
        except LLMError as e:
            console.print(f"[bold red]生成失败：[/]{e}")
            raise typer.Exit(code=1)

    project = Project.create(bible.title or "untitled")
    project.save_bible(bible)
    project.save_characters(characters)

    console.print(f"\n[green]✓[/] 立项完成：[bold]{bible.title}[/]（{bible.genre}）")
    console.print(f"  一句话：{bible.one_line}")
    console.print(f"  金手指：{bible.golden_finger}")
    console.print(
        f"  力量体系：{bible.power_system.name}"
        f"（{len(bible.power_system.tiers)} 层）"
    )
    console.print(f"  角色：{len(characters.characters)} 名")
    console.print(f"  目录：[dim]{project.root}[/]")
    console.print(f"\n[dim]{gateway.usage.summary()}[/]")
    console.print(
        f"\n下一步：[cyan]novel outline --book {project.slug}[/] 生成大纲"
        f"（可先打开 {project.bible_path.name} 审阅修改）"
    )


@app.command()
def outline(
    book: str = typer.Option(..., "--book", "-b", help="项目 slug（见 novel list）"),
    volumes: int = typer.Option(5, "--volumes", "-v", help="规划卷数（骨架）"),
    window: int = typer.Option(
        10, "--window", "-w", help="先生成未来多少章的细纲（滑动窗口）"
    ),
    skeleton_only: bool = typer.Option(
        False, "--skeleton-only", help="只生成骨架，不展开章节细纲"
    ),
) -> None:
    """生成大纲：先骨架（卷弧光），再只展开未来 N 章细纲（滑动窗口）。

    不一次铺满全书——后期剧情不被早期规划绑架。写完已规划章节后，
    用 `novel extend-outline` 基于实际进度续写下一窗口。
    """
    try:
        project = Project.open(book)
    except FileNotFoundError as e:
        console.print(f"[bold red]{e}[/]")
        raise typer.Exit(code=1)
    if not project.has_bible():
        console.print("[bold red]该项目还没有设定圣经，请先 novel init。[/]")
        raise typer.Exit(code=1)

    gateway = _gateway()
    bible = project.load_bible()
    characters = project.load_characters()
    char_names = [c.name for c in characters.characters]

    with console.status(f"正在规划 {volumes} 卷骨架…"):
        try:
            outline_obj = outline_planner.generate_skeleton(gateway, bible, volumes)
        except LLMError as e:
            console.print(f"[bold red]生成失败：[/]{e}")
            raise typer.Exit(code=1)

    console.print(f"[green]✓[/] 骨架完成：{len(outline_obj.arc_plan)} 卷弧光")

    if not skeleton_only:
        with console.status(f"正在规划接下来 {window} 章细纲…"):
            try:
                win = outline_planner.generate_chapter_window(
                    gateway, bible, outline_obj,
                    start_index=1, count=window,
                    character_names=char_names,
                    state=project.load_state(),
                )
            except LLMError as e:
                console.print(f"[bold red]章节细纲生成失败：[/]{e}")
                raise typer.Exit(code=1)
        added = outline_obj.add_window(
            win["chapters"], title=win["title"], arc=win["arc"]
        )
        console.print(f"  [green]✓[/] 已规划 {added} 章细纲（第 1~{added} 章）")

    project.save_outline(outline_obj)
    total = len(outline_obj.all_chapters())
    console.print(
        f"\n[green]✓[/] 大纲已保存：{len(outline_obj.arc_plan)} 卷弧光 / "
        f"{total} 章细纲"
    )
    console.print(f"  文件：[dim]{project.outline_path}[/]")
    console.print(f"\n[dim]{gateway.usage.summary()}[/]")


@app.command(name="extend-outline")
def extend_outline(
    book: str = typer.Option(..., "--book", "-b", help="项目 slug"),
    count: int = typer.Option(10, "--count", "-n", help="续写多少章细纲"),
) -> None:
    """续写大纲：基于当前进度与世界状态，增量追加下一窗口的章节细纲。"""
    try:
        project = Project.open(book)
    except FileNotFoundError as e:
        console.print(f"[bold red]{e}[/]")
        raise typer.Exit(code=1)
    if not project.has_outline():
        console.print("[bold red]还没有大纲，请先 novel outline。[/]")
        raise typer.Exit(code=1)

    gateway = _gateway()
    bible = project.load_bible()
    characters = project.load_characters()
    char_names = [c.name for c in characters.characters]
    outline_obj = project.load_outline()
    start_index = outline_obj.max_chapter_index() + 1

    with console.status(f"正在续写第 {start_index} 起 {count} 章细纲…"):
        try:
            win = outline_planner.generate_chapter_window(
                gateway, bible, outline_obj,
                start_index=start_index, count=count,
                character_names=char_names,
                state=project.load_state(),
            )
        except LLMError as e:
            console.print(f"[bold red]续写失败：[/]{e}")
            raise typer.Exit(code=1)

    added = outline_obj.add_window(
        win["chapters"], title=win["title"], arc=win["arc"]
    )
    project.save_outline(outline_obj)
    console.print(
        f"[green]✓[/] 已续写 {added} 章细纲（新卷《{win['title'] or '未命名'}》，"
        f"第 {start_index}~{start_index + added - 1} 章）"
    )
    console.print(f"\n[dim]{gateway.usage.summary()}[/]")


@app.command()
def write(
    book: str = typer.Option(..., "--book", "-b", help="项目 slug"),
    chapter: int = typer.Option(
        0, "--chapter", "-c", help="要写的章节序号；0=自动写下一章"
    ),
    words: int = typer.Option(2500, "--words", "-w", help="目标字数"),
    overwrite: bool = typer.Option(
        False, "--overwrite", help="若该章已存在则覆盖"
    ),
    no_consolidate: bool = typer.Option(
        False, "--no-consolidate", help="跳过写后记忆固化（不更新状态/摘要）"
    ),
    no_review: bool = typer.Option(
        False, "--no-review", help="跳过一致性校验"
    ),
    max_rewrites: int = typer.Option(
        1, "--max-rewrites", help="发现硬伤时最多自动重写次数"
    ),
    no_vector: bool = typer.Option(
        False, "--no-vector", help="跳过向量召回与索引"
    ),
    note: str = typer.Option(
        "", "--note", help="作者对本章的思路/要求（高优先级注入写作）"
    ),
) -> None:
    """写一章正文：注入设定+角色+本卷+近章原文+全局记忆，按细纲生成。

    流程：写正文 → 固化抽取 → 一致性校验 →（有硬伤则重写）→ 保存。
    """
    try:
        project = Project.open(book)
    except FileNotFoundError as e:
        console.print(f"[bold red]{e}[/]")
        raise typer.Exit(code=1)
    if not project.has_outline():
        console.print("[bold red]还没有大纲，请先 novel outline。[/]")
        raise typer.Exit(code=1)

    outline_obj = project.load_outline()
    written = project.existing_chapter_indices()

    # 决定写第几章
    if chapter == 0:
        all_idx = [c.index for c in outline_obj.all_chapters()]
        todo = [i for i in all_idx if i not in written]
        if not todo:
            console.print("[green]大纲内所有章节都已写完。[/]")
            raise typer.Exit(code=0)
        chapter = todo[0]

    if chapter in written and not overwrite:
        console.print(
            f"[yellow]第 {chapter} 章已存在。用 --overwrite 覆盖，或指定其它章节。[/]"
        )
        raise typer.Exit(code=1)

    ch = outline_obj.chapter(chapter)
    if ch is None:
        console.print(f"[bold red]大纲里没有第 {chapter} 章。[/]")
        raise typer.Exit(code=1)

    gateway = _gateway()
    result = write_one_chapter(
        gateway,
        project,
        chapter=chapter,
        title=ch.title,
        words=words,
        consolidate_mem=not no_consolidate,
        do_review=not no_review,
        max_rewrites=max_rewrites,
        use_vector=not no_vector,
        author_note=note,
        reporter=ConsoleReporter(console),
    )
    if result is None:
        raise typer.Exit(code=1)

    console.print(f"\n[dim]{gateway.usage.summary()}[/]")


@app.command()
def run(
    book: str = typer.Option(..., "--book", "-b", help="项目 slug"),
    count: int = typer.Option(
        0, "--count", "-n", help="连写多少章；0=写到大纲末尾"
    ),
    start: int = typer.Option(
        0, "--start", "-s", help="从第几章开始；0=接着最后已写章"
    ),
    words: int = typer.Option(2500, "--words", "-w", help="每章目标字数"),
    max_rewrites: int = typer.Option(
        1, "--max-rewrites", help="每章发现硬伤时最多自动重写次数"
    ),
    stop_on_error: bool = typer.Option(
        False, "--stop-on-error", help="某章重写后仍有硬伤就停止（默认继续）"
    ),
    no_vector: bool = typer.Option(False, "--no-vector", help="跳过向量召回与索引"),
    note: str = typer.Option(
        "", "--note", help="作者对这批章节的思路/要求（每章都会注入）"
    ),
) -> None:
    """无人值守批量续写：按大纲连写多章，每章走完整闭环（节奏→写→召回→校验→固化→索引）。"""
    try:
        project = Project.open(book)
    except FileNotFoundError as e:
        console.print(f"[bold red]{e}[/]")
        raise typer.Exit(code=1)
    if not project.has_outline():
        console.print("[bold red]还没有大纲，请先 novel outline。[/]")
        raise typer.Exit(code=1)

    outline_obj = project.load_outline()
    all_idx = sorted(c.index for c in outline_obj.all_chapters())
    if not all_idx:
        console.print("[bold red]大纲里没有章节细纲，请先 novel outline。[/]")
        raise typer.Exit(code=1)

    written = set(project.existing_chapter_indices())

    # 起点
    if start > 0:
        begin = start
    else:
        begin = (max(written) + 1) if written else all_idx[0]

    # 待写章列表：从 begin 起、在大纲内、尚未写的
    todo = [i for i in all_idx if i >= begin and i not in written]
    if count > 0:
        todo = todo[:count]
    if not todo:
        console.print("[green]没有需要写的章节（可能已写完或起点超出大纲）。[/]")
        raise typer.Exit(code=0)

    gateway = _gateway()
    console.print(
        f"[bold]批量续写[/]：{book}，计划写 {len(todo)} 章"
        f"（第 {todo[0]}~{todo[-1]} 章）\n"
    )

    done = 0
    for n, idx in enumerate(todo, 1):
        ch = outline_obj.chapter(idx)
        if ch is None:
            console.print(f"[yellow]跳过第 {idx} 章（大纲缺细纲）[/]")
            continue
        console.print(
            f"[bold cyan]── [{n}/{len(todo)}] 第 {idx} 章《{ch.title}》──[/]"
        )
        result = write_one_chapter(
            gateway,
            project,
            chapter=idx,
            title=ch.title,
            words=words,
            consolidate_mem=True,
            do_review=True,
            max_rewrites=max_rewrites,
            use_vector=not no_vector,
            author_note=note,
            reporter=ConsoleReporter(console),
        )
        if result is None:
            console.print("[bold red]本章写作失败，中止批量续写。[/]")
            break

        if result.get("has_errors"):
            if stop_on_error:
                console.print(
                    "[bold red]本章重写后仍有硬伤，按 --stop-on-error 中止。[/]"
                )
                break
            console.print("[yellow]本章带硬伤记入待办，继续下一章。[/]")
        done += 1
        console.print()  # 章节间空行

    console.print(
        f"[bold green]批量续写结束[/]：成功 {done}/{len(todo)} 章。"
    )
    console.print(f"[dim]{gateway.usage.summary()}[/]")

@app.command()
def reindex(
    book: str = typer.Option(..., "--book", "-b", help="项目 slug"),
    rebuild: bool = typer.Option(
        False, "--rebuild", help="清空后重建（默认只补未索引的章）"
    ),
) -> None:
    """把已写章节批量索引进向量库（为旧章节补建索引）。"""
    try:
        project = Project.open(book)
    except FileNotFoundError as e:
        console.print(f"[bold red]{e}[/]")
        raise typer.Exit(code=1)

    from .memory import Embedder, index_chapter

    try:
        embedder = Embedder(Config.load())
    except RuntimeError as e:
        console.print(f"[bold red]{e}[/]")
        raise typer.Exit(code=1)

    store = project.vector_store(embedder.dim)
    indices = project.existing_chapter_indices()
    if not indices:
        console.print("[yellow]还没有已写章节。[/]")
        raise typer.Exit(code=0)

    done = set() if rebuild else store.chapters_indexed()
    todo = [i for i in indices if i not in done]
    if rebuild:
        for i in indices:
            store.remove_chapter(i)
    if not todo:
        console.print("[green]所有章节都已索引。[/]")
        raise typer.Exit(code=0)

    total = 0
    for i in todo:
        text = project.read_chapter(i) or ""
        with console.status(f"索引第 {i} 章…"):
            try:
                n = index_chapter(store, embedder, chapter=i, text=text)
            except Exception as e:  # noqa: BLE001
                console.print(f"[yellow]第 {i} 章索引失败：{e}[/]")
                continue
        total += n
        console.print(f"  [green]✓[/] 第 {i} 章：{n} 段")
    console.print(f"\n[green]✓[/] 共索引 {total} 段，向量库现有 {store.size} 段")


@app.command(name="list")
def list_books() -> None:
    """列出所有项目。"""
    slugs = Project.list_all()
    if not slugs:
        console.print("[dim]还没有项目。用 novel init 立项。[/]")
        return
    table = Table(title="项目列表")
    table.add_column("slug", style="cyan")
    table.add_column("书名")
    table.add_column("题材")
    table.add_column("大纲")
    table.add_column("已写章节", justify="right")
    for slug in slugs:
        p = Project.open(slug)
        bible = p.load_bible()
        has_outline = "✓" if p.has_outline() else "—"
        written = len(p.existing_chapter_indices())
        table.add_row(slug, bible.title, bible.genre, has_outline, str(written))
    console.print(table)


@app.command()
def status(
    book: str = typer.Option(..., "--book", "-b", help="项目 slug"),
) -> None:
    """查看某本书的设定与进度。"""
    try:
        project = Project.open(book)
    except FileNotFoundError as e:
        console.print(f"[bold red]{e}[/]")
        raise typer.Exit(code=1)

    bible = project.load_bible()
    characters = project.load_characters()
    console.print(f"[bold]{bible.title}[/]（{bible.genre}）")
    console.print(f"  一句话：{bible.one_line}")
    console.print(f"  金手指：{bible.golden_finger}")
    console.print(f"  核心矛盾：{bible.core_conflict}")
    console.print(
        f"  力量体系：{bible.power_system.name} —— "
        + " → ".join(t.name for t in bible.power_system.tiers)
    )
    console.print(f"  角色（{len(characters.characters)}）：")
    for c in characters.characters:
        console.print(f"    · {c.name}（{c.role}）— {c.power_tier}　{c.goal}")

    if project.has_outline():
        outline_obj = project.load_outline()
        total = len(outline_obj.all_chapters())
        written = len(project.existing_chapter_indices())
        console.print(
            f"  大纲：{len(outline_obj.volumes)} 卷 / {total} 章；"
            f"已写正文 {written} 章"
        )
    else:
        console.print("  大纲：[dim]未生成[/]")

    # 世界状态快照（中期记忆）
    state = project.load_state()
    if state.last_chapter > 0:
        console.print(f"\n  [bold]世界状态[/]（截至第 {state.last_chapter} 章）")
        console.print(f"    主角境界：{state.protagonist_tier or '—'}")
        console.print(f"    主角位置：{state.protagonist_location or '—'}")
        dead = [c.name for c in state.characters if c.status == "死亡"]
        if dead:
            console.print(f"    已故角色：{'、'.join(dead)}")
        if state.open_threads:
            console.print(f"    进行中线索（{len(state.open_threads)}）：")
            for t in state.open_threads:
                console.print(f"      · {t}")
        if state.foreshadowing:
            console.print(f"    未回收伏笔（{len(state.foreshadowing)}）：")
            for f in state.foreshadowing:
                console.print(f"      · {f}")


@app.command()
def export(
    book: str = typer.Option(..., "--book", "-b", help="项目 slug"),
    output: str = typer.Option(
        "", "--output", "-o", help="输出文件路径（默认 <book>/全文.md）"
    ),
) -> None:
    """把已写章节合并导出为单个 markdown 文件。"""
    try:
        project = Project.open(book)
    except FileNotFoundError as e:
        console.print(f"[bold red]{e}[/]")
        raise typer.Exit(code=1)

    indices = project.existing_chapter_indices()
    if not indices:
        console.print("[yellow]还没有已写章节。[/]")
        raise typer.Exit(code=1)

    bible = project.load_bible()
    parts = [f"# {bible.title}\n\n> {bible.one_line}\n"]
    for i in indices:
        parts.append((project.read_chapter(i) or "").rstrip())

    from pathlib import Path

    out_path = Path(output) if output else (project.root / "全文.md")
    out_path.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
    total_chars = sum(len(project.read_chapter(i) or "") for i in indices)
    console.print(
        f"[green]✓[/] 已导出 {len(indices)} 章（约 {total_chars} 字）"
        f" → [dim]{out_path}[/]"
    )


if __name__ == "__main__":
    app()
