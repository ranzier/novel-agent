"""题材模板的持久化存储层。

题材模板原本是 genre_templates.py 里硬编码的 SEED_PROFILES。为支持前端增删改，
这里把它落到 app_data/genres.json：首次运行用种子写入，之后 JSON 即唯一真相源。

设计要点：
- GenreProfile 仍是 frozen dataclass；本模块只持有不可变快照 + 预建索引，
  写操作整体重写文件并失效缓存。
- mtime 缓存：文件极小（~7 条），但 resolve_genre 每章都调、known_genres 每次请求都调，
  按 st_mtime_ns 缓存避免重复读盘，写入后 mtime 变化自动失效。
- JSON 只有数组没有元组，load 时把 aliases/archetypes 归一回 tuple，保持 dataclass 诚实。
- 文件损坏时退回内存 SEED_PROFILES，不覆盖用户文件，保证 ideation 不崩。
"""

from __future__ import annotations

import dataclasses
import logging

from ..config import GENRES_PATH
from ..storage import from_dict, read_json, write_json
from .genre_templates import (
    SEED_PROFILES,
    GenreProfile,
    build_index,
)

logger = logging.getLogger(__name__)

# (mtime_ns, 有序 profiles, 索引)；None 表示未加载
_cache: tuple[int, list[GenreProfile], dict[str, GenreProfile]] | None = None


def _normalize(p: GenreProfile) -> GenreProfile:
    """把 JSON 反序列化得到的 list 字段归一回 tuple。"""
    return dataclasses.replace(
        p, aliases=tuple(p.aliases), archetypes=tuple(p.archetypes)
    )


def _profiles_to_payload(profiles: list[GenreProfile]) -> dict:
    """落盘结构：带 version，便于将来演进。"""
    return {
        "version": 1,
        "genres": [dataclasses.asdict(p) for p in profiles],
    }


def _seed() -> list[GenreProfile]:
    """把内置种子写入文件并返回。"""
    profiles = [_normalize(p) for p in SEED_PROFILES]
    write_json(GENRES_PATH, _profiles_to_payload(profiles))
    return profiles


def _read_file() -> list[GenreProfile]:
    """读文件 → profiles；缺失则种子；损坏则退回内存种子（不覆盖文件）。"""
    if not GENRES_PATH.exists():
        return _seed()
    try:
        raw = read_json(GENRES_PATH)
        items = raw.get("genres", []) if isinstance(raw, dict) else []
        profiles: list[GenreProfile] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            p = _normalize(from_dict(GenreProfile, item))
            if p.key.strip():  # 跳过空 key（_GENERIC 不入库）
                profiles.append(p)
        return profiles
    except Exception as e:  # noqa: BLE001 - 损坏不应让 ideation 崩溃
        logger.warning("genres.json 解析失败，临时退回内置种子：%s", e)
        return [_normalize(p) for p in SEED_PROFILES]


def _load() -> tuple[list[GenreProfile], dict[str, GenreProfile]]:
    """带 mtime 缓存地加载 profiles + 索引。"""
    global _cache
    # 文件不存在时先种子，确保有 mtime 可读
    if not GENRES_PATH.exists():
        _seed()
    mtime = GENRES_PATH.stat().st_mtime_ns if GENRES_PATH.exists() else 0
    if _cache is not None and _cache[0] == mtime:
        return _cache[1], _cache[2]
    profiles = _read_file()
    index = build_index(profiles)
    _cache = (mtime, profiles, index)
    return profiles, index


def _invalidate() -> None:
    global _cache
    _cache = None


# ---------------- 公开 API ----------------

def load_profiles() -> list[GenreProfile]:
    """按存储顺序返回全部题材模板。"""
    return _load()[0]


def current_index() -> dict[str, GenreProfile]:
    """key + alias → profile 索引，供 resolve_genre 用。"""
    return _load()[1]


def get_profile(key: str) -> GenreProfile | None:
    """按精确 key 查（不走别名）。"""
    k = (key or "").strip()
    for p in load_profiles():
        if p.key == k:
            return p
    return None


def upsert_profile(profile: GenreProfile) -> GenreProfile:
    """按 key 新建或整体替换；key 存在则原位更新，否则追加。空 key 拒绝。"""
    p = _normalize(profile)
    if not p.key.strip():
        raise ValueError("题材 key 不能为空")
    profiles = list(load_profiles())
    for i, existing in enumerate(profiles):
        if existing.key == p.key:
            profiles[i] = p
            break
    else:
        profiles.append(p)
    write_json(GENRES_PATH, _profiles_to_payload(profiles))
    _invalidate()
    return p


def delete_profile(key: str) -> bool:
    """按精确 key 删除。返回是否删到。"""
    k = (key or "").strip()
    profiles = list(load_profiles())
    kept = [p for p in profiles if p.key != k]
    if len(kept) == len(profiles):
        return False
    write_json(GENRES_PATH, _profiles_to_payload(kept))
    _invalidate()
    return True


def reset_to_seed() -> list[GenreProfile]:
    """用内置种子覆盖文件，恢复默认题材。"""
    profiles = _seed()
    _invalidate()
    return profiles
