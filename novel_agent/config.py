"""全局配置：从环境变量 / .env 读取，集中管理。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 包根目录的上一级（项目根）
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 每本书的存放根目录
BOOKS_DIR = PROJECT_ROOT / "books"

# 默认模型：用最新的 Opus。可被 NOVEL_MODEL 覆盖。
DEFAULT_MODEL = "claude-opus-4-8"

# 向量 embedding 默认配置（通义 text-embedding-v4，走 DashScope OpenAI 兼容端点）
DEFAULT_EMBED_MODEL = "text-embedding-v4"
DEFAULT_EMBED_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_EMBED_DIM = 1024

# 不同用途的默认模型分工（当前统一用 Opus 4.8，质量优先）
# 如需省钱可把 extract/review 换成更便宜的模型（如 Sonnet）。
DEFAULT_MODELS = {
    "write": "claude-opus-4-8",      # 正文：质量优先
    "outline": "claude-opus-4-8",    # 大纲：质量优先
    "extract": "claude-opus-4-8",    # 抽取：统一用 Opus
    "review": "claude-opus-4-8",     # 校验：统一用 Opus
}

# Prompt 上下文默认参数（可在配置页调整，存入 .env）
DEFAULT_RECENT_CHAPTERS = 3       # 注入最近几章的完整正文
DEFAULT_RECENT_CHAR_BUDGET = 12000  # 近章正文总字数预算
DEFAULT_SUMMARY_COUNT = 30        # 注入最多几条早期章节摘要
DEFAULT_RECALL_TOP_K = 4          # 向量召回片段条数
DEFAULT_RECALL_MIN_SCORE = 0.3    # 向量召回相似度阈值


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


@dataclass
class Config:
    """运行期配置。"""

    api_key: str
    base_url: str | None
    model: str
    books_dir: Path
    # 向量 embedding
    embed_api_key: str
    embed_base_url: str
    embed_model: str
    embed_dim: int
    # prompt 上下文参数
    recent_chapters: int
    recent_char_budget: int
    summary_count: int
    recall_top_k: int
    recall_min_score: float

    @classmethod
    def load(cls) -> "Config":
        """从 .env / 环境变量加载配置。"""
        load_dotenv(PROJECT_ROOT / ".env")

        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "").strip() or None
        model = os.environ.get("NOVEL_MODEL", "").strip() or DEFAULT_MODEL

        embed_api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
        embed_base_url = (
            os.environ.get("EMBED_BASE_URL", "").strip() or DEFAULT_EMBED_BASE_URL
        )
        embed_model = (
            os.environ.get("EMBED_MODEL", "").strip() or DEFAULT_EMBED_MODEL
        )
        embed_dim_raw = os.environ.get("EMBED_DIM", "").strip()
        embed_dim = int(embed_dim_raw) if embed_dim_raw.isdigit() else DEFAULT_EMBED_DIM

        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
            books_dir=BOOKS_DIR,
            embed_api_key=embed_api_key,
            embed_base_url=embed_base_url,
            embed_model=embed_model,
            embed_dim=embed_dim,
            recent_chapters=_env_int(
                "CTX_RECENT_CHAPTERS", DEFAULT_RECENT_CHAPTERS
            ),
            recent_char_budget=_env_int(
                "CTX_RECENT_CHAR_BUDGET", DEFAULT_RECENT_CHAR_BUDGET
            ),
            summary_count=_env_int("CTX_SUMMARY_COUNT", DEFAULT_SUMMARY_COUNT),
            recall_top_k=_env_int("CTX_RECALL_TOP_K", DEFAULT_RECALL_TOP_K),
            recall_min_score=_env_float(
                "CTX_RECALL_MIN_SCORE", DEFAULT_RECALL_MIN_SCORE
            ),
        )

    def require_api_key(self) -> str:
        """取 api key，缺失时给出清晰报错。"""
        if not self.api_key:
            raise RuntimeError(
                "缺少 ANTHROPIC_API_KEY。请复制 .env.example 为 .env 并填入 key。"
            )
        return self.api_key

    def require_embed_key(self) -> str:
        """取 embedding key，缺失时给出清晰报错。"""
        if not self.embed_api_key:
            raise RuntimeError(
                "缺少 DASHSCOPE_API_KEY（通义 embedding）。"
                "请在 .env 填入，或用 --no-vector 跳过向量召回。"
            )
        return self.embed_api_key

    def model_for(self, task: str) -> str:
        """按任务类型取模型；若用户显式设了 NOVEL_MODEL 则一律用它。"""
        if os.environ.get("NOVEL_MODEL", "").strip():
            return self.model
        return DEFAULT_MODELS.get(task, self.model)
