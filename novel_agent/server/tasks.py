"""长任务管理：后台线程跑写作/大纲/立项，进度经 QueueReporter 入队，SSE 推送。

单机自用，用内存任务表即可。同一本书同时只允许一个写任务（共享 state.json）。
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Callable

from ..reporting import Event, QueueReporter


@dataclass
class Task:
    """一个后台任务。"""

    id: str
    kind: str                       # write / run / reindex / init / outline
    slug: str
    status: str = "running"         # running / done / error
    reporter: QueueReporter = field(default_factory=QueueReporter)
    result: dict | None = None
    error: str | None = None
    thread: threading.Thread | None = None


class TaskManager:
    """内存任务表 + per-slug 写锁。"""

    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock_for(self, slug: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(slug, threading.Lock())

    def is_busy(self, slug: str) -> bool:
        lock = self._lock_for(slug)
        locked = lock.acquire(blocking=False)
        if locked:
            lock.release()
            return False
        return True

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def start(
        self,
        kind: str,
        slug: str,
        work: Callable[[QueueReporter], dict | None],
        *,
        exclusive: bool = True,
    ) -> Task:
        """创建任务并在后台线程执行 work(reporter)。

        exclusive=True 时占用 per-slug 写锁，防止并发写同一本书。
        """
        task = Task(id=uuid.uuid4().hex[:12], kind=kind, slug=slug)
        self._tasks[task.id] = task

        def _run() -> None:
            lock = self._lock_for(slug) if exclusive else None
            if lock is not None:
                lock.acquire()
            try:
                result = work(task.reporter)
                task.result = result
                task.status = "done"
                # work 内部通常已 done()；兜底确保流能结束
                task.reporter.close()
            except Exception as e:  # noqa: BLE001
                task.status = "error"
                task.error = str(e)
                task.reporter.error(f"任务失败：{e}")
                task.reporter.close()
            finally:
                if lock is not None:
                    lock.release()

        t = threading.Thread(target=_run, daemon=True)
        task.thread = t
        t.start()
        return task


def sse_format(event: Event) -> str:
    """把事件编码成 SSE 数据帧。"""
    import json

    payload = json.dumps(event.to_dict(), ensure_ascii=False)
    return f"event: {event.kind}\ndata: {payload}\n\n"
