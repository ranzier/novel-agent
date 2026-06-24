"""通义 text-embedding（默认 v4）客户端（走 DashScope OpenAI 兼容端点）。

DashScope 的 embedding 接口对单次请求的文本条数有上限（通常 10 条），
这里自动分批。失败重试与超时复用 openai SDK 自带能力。
"""

from __future__ import annotations

import time

from ..config import Config

# DashScope text-embedding-v3 单次最多 10 条
_BATCH_SIZE = 10


class EmbedError(RuntimeError):
    """embedding 调用失败。"""


class Embedder:
    """文本向量化客户端。"""

    def __init__(self, config: Config | None = None, *, timeout: float = 60.0):
        from openai import OpenAI

        self.config = config or Config.load()
        self.config.require_embed_key()
        self.model = self.config.embed_model
        self.dim = self.config.embed_dim
        self._client = OpenAI(
            api_key=self.config.embed_api_key,
            base_url=self.config.embed_base_url,
            timeout=timeout,
            max_retries=3,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        """把一批文本转成向量，保持输入顺序。"""
        if not texts:
            return []
        out: list[list[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            batch = texts[i : i + _BATCH_SIZE]
            out.extend(self._embed_batch(batch))
        return out

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                resp = self._client.embeddings.create(
                    model=self.model,
                    input=batch,
                    dimensions=self.dim,
                    encoding_format="float",
                )
                # 按 index 排序，确保与输入顺序一致
                items = sorted(resp.data, key=lambda d: d.index)
                return [list(d.embedding) for d in items]
            except Exception as e:  # noqa: BLE001 - 统一兜底重试
                last_err = e
                if attempt < 2:
                    time.sleep(2**attempt)
        raise EmbedError(f"通义 embedding 调用失败：{last_err}") from last_err
