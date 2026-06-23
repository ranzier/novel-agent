"""进度上报抽象：把"打印进度"与"业务流程"解耦。

CLI 用 ConsoleReporter（rich 打印，行为不变）；
Web 用 QueueReporter（事件入队，供 SSE 推送给浏览器）。

编排逻辑（如批量写作）只调用 reporter.step()/info()/warn()/error()/done()，
不关心终端还是网页。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Event:
    """一条进度事件。"""

    kind: str            # step / info / warn / error / done
    message: str
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "message": self.message, "data": self.data}


class Reporter(Protocol):
    """进度上报接口。"""

    def step(self, message: str, **data) -> None:
        """一个主要步骤（如：正在写作 / 正在校验）。"""

    def info(self, message: str, **data) -> None:
        """一般信息（如：召回 N 段、记忆已更新）。"""

    def warn(self, message: str, **data) -> None:
        """警告（不致命，如：召回失败已跳过）。"""

    def error(self, message: str, **data) -> None:
        """错误（致命，如：写作失败）。"""

    def done(self, message: str = "", **data) -> None:
        """任务结束（携带最终结果数据，如用量/成本）。"""


class ConsoleReporter:
    """终端实现：保持原 CLI 观感。"""

    def __init__(self, console=None):
        if console is None:
            from rich.console import Console

            console = Console()
        self.console = console

    def step(self, message: str, **data) -> None:
        self.console.print(f"[cyan]›[/] {message}")

    def info(self, message: str, **data) -> None:
        self.console.print(f"  [dim]{message}[/]")

    def warn(self, message: str, **data) -> None:
        self.console.print(f"[yellow]{message}[/]")

    def error(self, message: str, **data) -> None:
        self.console.print(f"[bold red]{message}[/]")

    def done(self, message: str = "", **data) -> None:
        if message:
            self.console.print(f"[green]✓[/] {message}")


class QueueReporter:
    """队列实现：事件入队，SSE 端点消费后推给前端。"""

    def __init__(self) -> None:
        import queue

        self.queue: "queue.Queue[Event | None]" = queue.Queue()
        self.events: list[Event] = []

    def _emit(self, kind: str, message: str, data: dict) -> None:
        ev = Event(kind=kind, message=message, data=data)
        self.events.append(ev)
        self.queue.put(ev)

    def step(self, message: str, **data) -> None:
        self._emit("step", message, data)

    def info(self, message: str, **data) -> None:
        self._emit("info", message, data)

    def warn(self, message: str, **data) -> None:
        self._emit("warn", message, data)

    def error(self, message: str, **data) -> None:
        self._emit("error", message, data)

    def done(self, message: str = "", **data) -> None:
        self._emit("done", message, data)
        self.queue.put(None)  # 哨兵：通知 SSE 流结束

    def close(self) -> None:
        """异常兜底：确保 SSE 流能结束。"""
        self.queue.put(None)
