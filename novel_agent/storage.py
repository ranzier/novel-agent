"""读写辅助：JSON / YAML，统一 UTF-8、中文不转义、格式化。

写入一律走 _atomic_write：先写同目录临时文件再 os.replace 原子替换，
避免进程在写入中途被打断（Ctrl+C / kill / 崩溃）导致文件半写损坏。
"""

from __future__ import annotations

import dataclasses
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, TypeVar

import yaml

T = TypeVar("T")


def _atomic_write(path: Path, write: Callable[[Any], None]) -> None:
    """原子写文件：临时文件写完 + fsync 后 os.replace 替换目标。

    write 接收一个已打开的文本句柄，负责把内容写进去。
    崩在写临时文件阶段时原文件不受影响；os.replace 在同一文件系统内是原子操作。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # 临时文件放在目标同目录，确保与目标同一文件系统，rename 才能原子
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            write(f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        # 出错清掉临时文件，绝不触碰原文件
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    payload = _to_plain(data)

    def _w(f: Any) -> None:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    _atomic_write(path, _w)


def read_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def write_yaml(path: Path, data: Any) -> None:
    payload = _to_plain(data)
    _atomic_write(
        path,
        lambda f: yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False),
    )


def write_text(path: Path, text: str) -> None:
    """原子写纯文本（如章节正文）。"""
    _atomic_write(path, lambda f: f.write(text))


def _to_plain(data: Any) -> Any:
    """把 dataclass 递归转成普通 dict/list，方便序列化。"""
    if dataclasses.is_dataclass(data) and not isinstance(data, type):
        return {k: _to_plain(v) for k, v in dataclasses.asdict(data).items()}
    if isinstance(data, dict):
        return {k: _to_plain(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_to_plain(v) for v in data]
    return data


def from_dict(cls: type[T], data: dict[str, Any]) -> T:
    """从 dict 构造 dataclass，忽略多余字段、缺失字段用默认值。

    对人手改过的 JSON 更宽容，不会因为多/少字段直接崩。
    仅处理一层；嵌套结构在各模型的 from_dict 里自行处理。
    """
    if not dataclasses.is_dataclass(cls):
        raise TypeError(f"{cls} 不是 dataclass")
    field_names = {f.name for f in dataclasses.fields(cls)}
    kwargs = {k: v for k, v in (data or {}).items() if k in field_names}
    return cls(**kwargs)  # type: ignore[return-value]
