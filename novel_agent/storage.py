"""读写辅助：JSON / YAML，统一 UTF-8、中文不转义、格式化。"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any, TypeVar

import yaml

T = TypeVar("T")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _to_plain(data)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def read_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _to_plain(data)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False)


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
