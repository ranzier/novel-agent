"""读写 .env 配置文件。供 Web 配置管理页使用。

设计：
- 已知的配置项白名单，避免任意写入。
- 写回时整体重写 .env（带分组注释），逻辑简单可控。
- key 类字段对外只回显脱敏值（尾部 4 位），不裸传完整 key。
- 写回后同步刷新 os.environ，使同进程后续 Config.load() 立即生效。
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from ..config import (
    DEFAULT_EMBED_BASE_URL,
    DEFAULT_EMBED_DIM,
    DEFAULT_EMBED_MODEL,
    DEFAULT_MODEL,
    DEFAULT_RECENT_CHAPTERS,
    DEFAULT_RECENT_CHAR_BUDGET,
    DEFAULT_SUMMARY_COUNT,
    DEFAULT_RECALL_TOP_K,
    DEFAULT_RECALL_MIN_SCORE,
    PROJECT_ROOT,
)


ENV_PATH = PROJECT_ROOT / ".env"

# 配置项白名单：键 → 是否为敏感（key 类）
_FIELDS = {
    "ANTHROPIC_API_KEY": True,
    "ANTHROPIC_BASE_URL": False,
    "NOVEL_MODEL": False,
    "DASHSCOPE_API_KEY": True,
    "EMBED_BASE_URL": False,
    "EMBED_MODEL": False,
    "EMBED_DIM": False,
    "CTX_RECENT_CHAPTERS": False,
    "CTX_RECENT_CHAR_BUDGET": False,
    "CTX_SUMMARY_COUNT": False,
    "CTX_RECALL_TOP_K": False,
    "CTX_RECALL_MIN_SCORE": False,
}


def _mask(value: str) -> str:
    """脱敏：只保留尾部 4 位，前面用 • 代替。空值返回空。"""
    v = (value or "").strip()
    if not v:
        return ""
    if len(v) <= 4:
        return "•" * len(v)
    return "•••••••• " + v[-4:]


def _read_raw() -> dict[str, str]:
    """从环境（已 load_dotenv）读出当前各项原始值。"""
    load_dotenv(ENV_PATH)
    return {k: os.environ.get(k, "").strip() for k in _FIELDS}


def get_config_view() -> dict:
    """返回给前端的配置视图：敏感项脱敏 + 是否已设置 + 默认值提示。"""
    raw = _read_raw()
    out: dict[str, dict] = {}
    for k, sensitive in _FIELDS.items():
        val = raw.get(k, "")
        out[k] = {
            "sensitive": sensitive,
            "is_set": bool(val),
            "value": _mask(val) if sensitive else val,
        }
    out["_defaults"] = {
        "NOVEL_MODEL": DEFAULT_MODEL,
        "EMBED_BASE_URL": DEFAULT_EMBED_BASE_URL,
        "EMBED_MODEL": DEFAULT_EMBED_MODEL,
        "EMBED_DIM": str(DEFAULT_EMBED_DIM),
        "CTX_RECENT_CHAPTERS": str(DEFAULT_RECENT_CHAPTERS),
        "CTX_RECENT_CHAR_BUDGET": str(DEFAULT_RECENT_CHAR_BUDGET),
        "CTX_SUMMARY_COUNT": str(DEFAULT_SUMMARY_COUNT),
        "CTX_RECALL_TOP_K": str(DEFAULT_RECALL_TOP_K),
        "CTX_RECALL_MIN_SCORE": str(DEFAULT_RECALL_MIN_SCORE),
    }
    return out


def save_config(updates: dict[str, str]) -> None:
    """把提交的配置写回 .env，并刷新 os.environ 使其即时生效。

    updates：键→值。只接受白名单内的键。
    - 敏感字段：值为空或为脱敏占位（含 •）时，视为"不修改"，保留原值。
    - 非敏感字段：值为空表示清空该项。
    """
    current = _read_raw()
    merged = dict(current)

    for k, v in (updates or {}).items():
        if k not in _FIELDS:
            continue
        v = (v or "").strip()
        if _FIELDS[k]:  # 敏感：空 / 含脱敏符号 → 不动原值
            if not v or "•" in v:
                continue
            merged[k] = v
        else:
            merged[k] = v

    _write_env(merged)

    # 同步进程环境，确保后续 Config.load() 立即读到新值
    for k, v in merged.items():
        if v:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)


def _write_env(values: dict[str, str]) -> None:
    """带分组注释地整体重写 .env。"""
    lines = [
        "# Anthropic Claude API key（必填）",
        f"ANTHROPIC_API_KEY={values.get('ANTHROPIC_API_KEY', '')}",
        "",
        "# 可选：自定义 API base url（走代理或兼容网关时填）",
        f"ANTHROPIC_BASE_URL={values.get('ANTHROPIC_BASE_URL', '')}",
        "",
        "# 可选：默认模型，不填用内置默认",
        _kv_or_comment("NOVEL_MODEL", values.get("NOVEL_MODEL", "")),
        "",
        "# 通义 text-embedding 的 key（向量召回，走 DashScope）",
        f"DASHSCOPE_API_KEY={values.get('DASHSCOPE_API_KEY', '')}",
        "",
        "# 可选：embedding 端点 / 模型 / 维度，不填用内置默认",
        _kv_or_comment("EMBED_BASE_URL", values.get("EMBED_BASE_URL", "")),
        _kv_or_comment("EMBED_MODEL", values.get("EMBED_MODEL", "")),
        _kv_or_comment("EMBED_DIM", values.get("EMBED_DIM", "")),
        "",
        "# 可选：prompt 上下文参数，不填用内置默认",
        _kv_or_comment(
            "CTX_RECENT_CHAPTERS", values.get("CTX_RECENT_CHAPTERS", "")
        ),
        _kv_or_comment(
            "CTX_RECENT_CHAR_BUDGET", values.get("CTX_RECENT_CHAR_BUDGET", "")
        ),
        _kv_or_comment("CTX_SUMMARY_COUNT", values.get("CTX_SUMMARY_COUNT", "")),
        _kv_or_comment("CTX_RECALL_TOP_K", values.get("CTX_RECALL_TOP_K", "")),
        _kv_or_comment(
            "CTX_RECALL_MIN_SCORE", values.get("CTX_RECALL_MIN_SCORE", "")
        ),
        "",
    ]
    ENV_PATH.write_text("\n".join(lines), encoding="utf-8")


def _kv_or_comment(key: str, value: str) -> str:
    """有值则写 KEY=value；无值则写成注释占位，保持文件可读。"""
    value = (value or "").strip()
    return f"{key}={value}" if value else f"# {key}="
