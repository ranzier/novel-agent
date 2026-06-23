"""从 LLM 文本响应里稳健地抽取 JSON。

模型有时会用 ```json 代码块包裹，或在 JSON 前后加说明文字。
这里尽量把真正的 JSON 提取出来并解析。
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class JSONExtractError(ValueError):
    """无法从响应中解析出 JSON。"""


def extract_json(text: str) -> Any:
    """从文本中提取并解析 JSON。失败抛 JSONExtractError。"""
    candidates: list[str] = []

    # 1) 代码块里的内容优先
    fenced = _FENCE_RE.findall(text)
    candidates.extend(block.strip() for block in fenced)

    # 2) 整段文本本身
    candidates.append(text.strip())

    # 3) 第一个 { 到最后一个 } / 第一个 [ 到最后一个 ]
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            candidates.append(text[start : end + 1])

    for cand in candidates:
        if not cand:
            continue
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue

    raise JSONExtractError(
        f"无法从响应中解析 JSON。响应前 200 字：\n{text[:200]}"
    )
