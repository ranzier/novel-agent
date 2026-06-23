"""FastAPI 应用与只读端点。"""

import queue

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from ..config import BOOKS_DIR, Config
from ..project import Project
from ..storage import _to_plain
from .tasks import TaskManager, sse_format


class InitBody(BaseModel):
    idea: str
    genre: str = ""
    title: str = ""


class OutlineBody(BaseModel):
    volumes: int = 5
    chapters: int = 10
    skeleton_only: bool = False


class WriteBody(BaseModel):
    chapter: int = 0
    words: int = 2500
    overwrite: bool = False
    no_review: bool = False
    no_vector: bool = False
    no_consolidate: bool = False
    max_rewrites: int = 1


class RunBody(BaseModel):
    count: int = 0
    start: int = 0
    words: int = 2500
    max_rewrites: int = 1
    stop_on_error: bool = False
    no_vector: bool = False


def create_app() -> FastAPI:
    app = FastAPI(
        title="novel-agent API",
        description="网文写作 Agent 的本地 Web API",
        version="0.1.0",
    )
    tasks = TaskManager()

    # ---- 通用工具 ----
    def _open_project(slug: str) -> Project:
        try:
            return Project.open(slug, BOOKS_DIR)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"项目不存在：{slug}")

    def _resp(data) -> JSONResponse:
        """序列化 dataclass → JSON。"""
        return JSONResponse(_to_plain(data))

    # ---- GET /api/books ----
    @app.get("/api/books")
    def list_books():
        slugs = Project.list_all(BOOKS_DIR)
        out = []
        for s in slugs:
            try:
                p = Project.open(s, BOOKS_DIR)
                bible = p.load_bible()
                written = len(p.existing_chapter_indices())
                total = 0
                if p.has_outline():
                    total = len(p.load_outline().all_chapters())
                out.append({
                    "slug": s,
                    "title": bible.title,
                    "genre": bible.genre,
                    "progress": {"written": written, "total": total},
                })
            except Exception:  # noqa: BLE001
                continue
        return out

    # ---- GET /api/books/{slug} ----
    @app.get("/api/books/{slug}")
    def get_book_overview(slug: str):
        p = _open_project(slug)
        bible = p.load_bible()
        written = p.existing_chapter_indices()
        total_ch = 0
        if p.has_outline():
            total_ch = len(p.load_outline().all_chapters())
        state = p.load_state()
        return _resp({
            "slug": slug,
            "title": bible.title,
            "genre": bible.genre,
            "tone": bible.tone,
            "golden_finger": bible.golden_finger,
            "core_conflict": bible.core_conflict,
            "progress": {"written": len(written), "total": total_ch},
            "state": state,
        })

    # ---- GET /api/books/{slug}/bible ----
    @app.get("/api/books/{slug}/bible")
    def get_bible(slug: str):
        p = _open_project(slug)
        return _resp(p.load_bible())

    # ---- GET /api/books/{slug}/characters ----
    @app.get("/api/books/{slug}/characters")
    def get_characters(slug: str):
        p = _open_project(slug)
        return _resp(p.load_characters())

    # ---- GET /api/books/{slug}/outline ----
    @app.get("/api/books/{slug}/outline")
    def get_outline(slug: str):
        p = _open_project(slug)
        if not p.has_outline():
            raise HTTPException(status_code=404, detail="大纲未生成")
        return _resp(p.load_outline())

    # ---- GET /api/books/{slug}/chapters ----
    @app.get("/api/books/{slug}/chapters")
    def list_chapters(slug: str):
        p = _open_project(slug)
        outline = None
        if p.has_outline():
            outline = p.load_outline()
        reviews_dict = {}
        if p.reviews_path.exists():
            from ..storage import read_json

            for r in read_json(p.reviews_path):
                reviews_dict[r.get("chapter")] = r
        items = []
        for idx in p.existing_chapter_indices():
            text = p.read_chapter(idx) or ""
            title = ""
            if outline:
                ch = outline.chapter(idx)
                title = ch.title if ch else ""
            review = reviews_dict.get(idx)
            has_errors = False
            if review:
                has_errors = any(
                    i.get("severity") == "error"
                    for i in review.get("issues", [])
                )
            items.append({
                "index": idx,
                "title": title,
                "chars": len(text),
                "has_errors": has_errors,
            })
        return items

    # ---- GET /api/books/{slug}/chapters/{n} ----
    @app.get("/api/books/{slug}/chapters/{n}")
    def get_chapter(slug: str, n: int):
        p = _open_project(slug)
        text = p.read_chapter(n)
        if text is None:
            raise HTTPException(status_code=404, detail=f"第 {n} 章不存在")
        title = ""
        if p.has_outline():
            ch = p.load_outline().chapter(n)
            title = ch.title if ch else ""
        return {"index": n, "title": title, "text": text}

    # ---- GET /api/books/{slug}/state ----
    @app.get("/api/books/{slug}/state")
    def get_state(slug: str):
        p = _open_project(slug)
        return _resp(p.load_state())

    # ---- GET /api/books/{slug}/reviews ----
    @app.get("/api/books/{slug}/reviews")
    def get_reviews(slug: str):
        p = _open_project(slug)
        if not p.reviews_path.exists():
            return []
        from ..storage import read_json

        return read_json(p.reviews_path)

    # ---- GET /api/books/{slug}/summaries ----
    @app.get("/api/books/{slug}/summaries")
    def get_summaries(slug: str):
        p = _open_project(slug)
        return _resp(p.load_summaries())

    # ============ 编辑保存（PUT） ============
    @app.put("/api/books/{slug}/bible")
    async def save_bible(slug: str, payload: dict):
        from ..bible import Bible

        p = _open_project(slug)
        p.save_bible(Bible.from_dict(payload))
        return {"ok": True}

    @app.put("/api/books/{slug}/characters")
    async def save_characters(slug: str, payload: dict):
        from ..bible import CharacterBook

        p = _open_project(slug)
        p.save_characters(CharacterBook.from_dict(payload))
        return {"ok": True}

    @app.put("/api/books/{slug}/outline")
    async def save_outline(slug: str, payload: dict):
        from ..generate.outline_models import Outline

        p = _open_project(slug)
        p.save_outline(Outline.from_dict(payload))
        return {"ok": True}

    @app.put("/api/books/{slug}/chapters/{n}")
    async def save_chapter(slug: str, n: int, payload: dict):
        p = _open_project(slug)
        text = payload.get("text", "")
        if not text.strip():
            raise HTTPException(status_code=400, detail="正文不能为空")
        p.write_chapter(n, text)
        return {"ok": True, "chars": len(text)}

    # ============ 长任务 ============
    def _gateway() -> "LLMGateway":  # noqa: F821
        from ..llm import LLMGateway

        return LLMGateway(Config.load())

    def _guard_busy(slug: str) -> None:
        if tasks.is_busy(slug):
            raise HTTPException(status_code=409, detail="该项目正有写任务进行中")

    # ---- POST /api/books  立项 ----
    @app.post("/api/books")
    def create_book(body: InitBody):
        from ..generate import ideation

        def work(rep):
            gw = _gateway()
            rep.step("设计设定圣经")
            bible = ideation.generate_bible(gw, body.idea, body.genre)
            if body.title:
                bible.title = body.title
            rep.step("设计核心角色")
            characters = ideation.generate_characters(gw, bible)
            project = Project.create(bible.title, BOOKS_DIR)
            project.save_bible(bible)
            project.save_characters(characters)
            rep.done(
                f"立项完成：《{bible.title}》",
                slug=project.slug, usage=gw.usage.as_dict(),
            )
            return {"slug": project.slug, "title": bible.title}

        task = tasks.start("init", "", work, exclusive=False)
        return {"task_id": task.id}

    # ---- POST /api/books/{slug}/outline ----
    @app.post("/api/books/{slug}/outline")
    def gen_outline(slug: str, body: OutlineBody):
        p = _open_project(slug)
        _guard_busy(slug)
        from ..generate import outline_planner

        def work(rep):
            gw = _gateway()
            bible = p.load_bible()
            characters = p.load_characters()
            char_names = [c.name for c in characters.characters]
            rep.step(f"规划 {body.volumes} 卷骨架")
            outline = outline_planner.generate_skeleton(gw, bible, body.volumes)
            rep.info(f"骨架完成：{len(outline.volumes)} 卷")
            if not body.skeleton_only:
                start_index = 1
                for vol in outline.volumes:
                    rep.step(f"细化第 {vol.index} 卷《{vol.title}》")
                    try:
                        filled = outline_planner.generate_volume_chapters(
                            gw, bible, vol, chapters=body.chapters,
                            start_index=start_index, character_names=char_names,
                        )
                    except Exception as e:  # noqa: BLE001
                        rep.warn(f"第 {vol.index} 卷细化失败：{e}，跳过")
                        continue
                    vol.chapters = filled.chapters
                    start_index += len(vol.chapters)
                    rep.info(f"第 {vol.index} 卷：{len(vol.chapters)} 章")
            p.save_outline(outline)
            rep.done(
                f"大纲已生成：{len(outline.volumes)} 卷 / "
                f"{len(outline.all_chapters())} 章",
                usage=gw.usage.as_dict(),
            )
            return {"volumes": len(outline.volumes)}

        task = tasks.start("outline", slug, work)
        return {"task_id": task.id}

    # ---- POST /api/books/{slug}/write ----
    @app.post("/api/books/{slug}/write")
    def write_chapter(slug: str, body: WriteBody):
        p = _open_project(slug)
        _guard_busy(slug)
        if not p.has_outline():
            raise HTTPException(status_code=400, detail="还没有大纲")
        from ..engine import write_one_chapter

        outline = p.load_outline()
        written = set(p.existing_chapter_indices())
        chapter = body.chapter
        if chapter == 0:
            todo = [c.index for c in outline.all_chapters() if c.index not in written]
            if not todo:
                raise HTTPException(status_code=400, detail="所有章节都已写完")
            chapter = todo[0]
        if chapter in written and not body.overwrite:
            raise HTTPException(status_code=409, detail=f"第 {chapter} 章已存在")
        ch = outline.chapter(chapter)
        if ch is None:
            raise HTTPException(status_code=400, detail=f"大纲里没有第 {chapter} 章")

        def work(rep):
            gw = _gateway()
            result = write_one_chapter(
                gw, p, chapter=chapter, title=ch.title, words=body.words,
                consolidate_mem=not body.no_consolidate,
                do_review=not body.no_review, max_rewrites=body.max_rewrites,
                use_vector=not body.no_vector, reporter=rep,
            )
            return result

        task = tasks.start("write", slug, work)
        return {"task_id": task.id, "chapter": chapter}

    # ---- POST /api/books/{slug}/run  批量续写 ----
    @app.post("/api/books/{slug}/run")
    def run_batch(slug: str, body: RunBody):
        p = _open_project(slug)
        _guard_busy(slug)
        if not p.has_outline():
            raise HTTPException(status_code=400, detail="还没有大纲")
        from ..engine import write_one_chapter

        def work(rep):
            gw = _gateway()
            outline = p.load_outline()
            all_idx = sorted(c.index for c in outline.all_chapters())
            written = set(p.existing_chapter_indices())
            begin = body.start if body.start > 0 else (
                (max(written) + 1) if written else all_idx[0]
            )
            todo = [i for i in all_idx if i >= begin and i not in written]
            if body.count > 0:
                todo = todo[: body.count]
            done = 0
            for n, idx in enumerate(todo, 1):
                ch = outline.chapter(idx)
                if ch is None:
                    continue
                rep.step(f"[{n}/{len(todo)}] 第 {idx} 章《{ch.title}》", chapter=idx)
                r = write_one_chapter(
                    gw, p, chapter=idx, title=ch.title, words=body.words,
                    consolidate_mem=True, do_review=True,
                    max_rewrites=body.max_rewrites,
                    use_vector=not body.no_vector, reporter=rep,
                )
                if r is None:
                    rep.warn("本章写作失败，中止批量续写")
                    break
                if r.get("has_errors") and body.stop_on_error:
                    rep.warn("本章仍有硬伤，按 stop_on_error 中止")
                    break
                done += 1
            rep.done(f"批量续写结束：成功 {done}/{len(todo)} 章", done=done)
            return {"done": done, "planned": len(todo)}

        task = tasks.start("run", slug, work)
        return {"task_id": task.id}

    # ---- POST /api/books/{slug}/reindex ----
    @app.post("/api/books/{slug}/reindex")
    def reindex(slug: str, rebuild: bool = False):
        p = _open_project(slug)
        _guard_busy(slug)

        def work(rep):
            from ..memory import Embedder, index_chapter

            embedder = Embedder(Config.load())
            store = p.vector_store(embedder.dim)
            indices = p.existing_chapter_indices()
            done = set() if rebuild else store.chapters_indexed()
            if rebuild:
                for i in indices:
                    store.remove_chapter(i)
            todo = [i for i in indices if i not in done]
            total = 0
            for i in todo:
                rep.step(f"索引第 {i} 章")
                total += index_chapter(
                    store, embedder, chapter=i, text=p.read_chapter(i) or ""
                )
            rep.done(f"共索引 {total} 段，向量库现有 {store.size} 段")
            return {"indexed": total, "size": store.size}

        task = tasks.start("reindex", slug, work)
        return {"task_id": task.id}

    # ---- GET /api/tasks/{id} ----
    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str):
        task = tasks.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return {
            "id": task.id, "kind": task.kind, "slug": task.slug,
            "status": task.status, "result": task.result, "error": task.error,
        }

    # ---- GET /api/tasks/{id}/events  SSE ----
    @app.get("/api/tasks/{task_id}/events")
    def task_events(task_id: str):
        task = tasks.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="任务不存在")

        def stream():
            # 队列会缓冲所有事件直到被消费，故即使订阅较晚也不会丢事件。
            # 单消费者场景：直接抽干队列即可。
            q = task.reporter.queue
            while True:
                try:
                    ev = q.get(timeout=30)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    continue
                if ev is None:  # 哨兵：结束
                    break
                yield sse_format(ev)

        return StreamingResponse(stream(), media_type="text/event-stream")

    # ---- 静态前端（build 后由 FastAPI 托管）----
    from pathlib import Path

    dist = Path(__file__).resolve().parent.parent.parent / "web" / "dist"
    if dist.exists():
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=str(dist), html=True), name="web")

    return app
