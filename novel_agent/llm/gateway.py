"""Claude 网关：统一封装调用、重试、超时、token 与成本统计。

所有对 LLM 的调用都走这里，业务代码不直接碰 anthropic SDK，
方便后续换模型 / 加缓存 / 统一限流。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import anthropic

from ..config import Config
from .json_utils import JSONExtractError, extract_json

# 各模型每百万 token 价格（美元），用于成本估算。
# 价格可能变动，仅作参考；未知模型按 Opus 估。
_PRICING = {
    "claude-opus-4-8": {"in": 5.0, "out": 25.0},
    "claude-opus-4-7": {"in": 5.0, "out": 25.0},
    "claude-opus-4-6": {"in": 5.0, "out": 25.0},
    "claude-sonnet-4-6": {"in": 3.0, "out": 15.0},
    "claude-haiku-4-5-20251001": {"in": 1.0, "out": 5.0},
}
_DEFAULT_PRICE = {"in": 5.0, "out": 25.0}


class LLMError(RuntimeError):
    """LLM 调用失败（重试耗尽后）。"""


@dataclass
class Usage:
    """累计 token 用量与成本估算。"""

    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    cost_usd: float = 0.0
    # 按模型分别累计
    by_model: dict[str, dict[str, float]] = field(default_factory=dict)

    def add(self, model: str, in_tok: int, out_tok: int) -> float:
        """累加一次调用，返回本次成本。"""
        price = _PRICING.get(model, _DEFAULT_PRICE)
        cost = in_tok / 1_000_000 * price["in"] + out_tok / 1_000_000 * price["out"]

        self.input_tokens += in_tok
        self.output_tokens += out_tok
        self.calls += 1
        self.cost_usd += cost

        m = self.by_model.setdefault(
            model, {"input_tokens": 0, "output_tokens": 0, "calls": 0, "cost_usd": 0.0}
        )
        m["input_tokens"] += in_tok
        m["output_tokens"] += out_tok
        m["calls"] += 1
        m["cost_usd"] += cost
        return cost

    def summary(self) -> str:
        return (
            f"调用 {self.calls} 次 | "
            f"输入 {self.input_tokens:,} tok | "
            f"输出 {self.output_tokens:,} tok | "
            f"约 ${self.cost_usd:.4f}"
        )

    def as_dict(self) -> dict:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 4),
        }


# 这些错误值得重试（瞬时 / 限流 / 过载）
_RETRIABLE = (
    anthropic.RateLimitError,
    anthropic.APITimeoutError,
    anthropic.APIConnectionError,
    anthropic.InternalServerError,
)


class LLMGateway:
    """对 Claude 的薄封装。"""

    def __init__(
        self,
        config: Config | None = None,
        *,
        max_retries: int = 4,
        timeout: float = 600.0,
    ):
        self.config = config or Config.load()
        self.config.require_api_key()
        self.max_retries = max_retries
        self.usage = Usage()
        self._client = anthropic.Anthropic(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=timeout,
            # SDK 自带重试关掉，由我们统一控制以便记录日志
            max_retries=0,
        )

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        task: str = "write",
        model: str | None = None,
        max_tokens: int = 8192,
        temperature: float = 1.0,
    ) -> str:
        """单轮补全：给 prompt 拿文本。带指数退避重试与用量统计。"""
        model = model or self.config.model_for(task)
        messages = [{"role": "user", "content": prompt}]

        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system or anthropic.NOT_GIVEN,
                    messages=messages,
                )
                self.usage.add(
                    model,
                    resp.usage.input_tokens,
                    resp.usage.output_tokens,
                )
                return _extract_text(resp)
            except _RETRIABLE as e:
                last_err = e
                if attempt < self.max_retries:
                    # 指数退避：1s, 2s, 4s, 8s …
                    time.sleep(2**attempt)
                    continue
                break
            except anthropic.APIStatusError as e:
                # 4xx（鉴权 / 参数错误等）不重试
                raise LLMError(f"Claude API 错误 [{e.status_code}]: {e.message}") from e

        raise LLMError(
            f"Claude 调用失败，已重试 {self.max_retries} 次：{last_err}"
        ) from last_err

    def complete_stream(
        self,
        prompt: str,
        *,
        system: str | None = None,
        task: str = "write",
        model: str | None = None,
        max_tokens: int = 8192,
        temperature: float = 1.0,
    ):
        """流式补全：逐段 yield 文本增量（生成器）。

        与 complete 行为一致（同样统计用量、对瞬时错误重试），但边生成
        边产出 token，供上层做流式展示。注意：为简化，仅在「首个 token 到达前」
        的连接/限流错误才重试；一旦开始产出文本就不再重试（避免重复输出）。
        """
        model = model or self.config.model_for(task)
        messages = [{"role": "user", "content": prompt}]

        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            started = False
            try:
                with self._client.messages.stream(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system or anthropic.NOT_GIVEN,
                    messages=messages,
                ) as stream:
                    for text in stream.text_stream:
                        started = True
                        yield text
                    final = stream.get_final_message()
                self.usage.add(
                    model, final.usage.input_tokens, final.usage.output_tokens
                )
                return
            except _RETRIABLE as e:
                last_err = e
                if not started and attempt < self.max_retries:
                    time.sleep(2**attempt)
                    continue
                break
            except anthropic.APIStatusError as e:
                raise LLMError(
                    f"Claude API 错误 [{e.status_code}]: {e.message}"
                ) from e

        raise LLMError(
            f"Claude 流式调用失败：{last_err}"
        ) from last_err

    def complete_json(
        self,
        prompt: str,
        *,
        system: str | None = None,
        task: str = "write",
        model: str | None = None,
        max_tokens: int = 8192,
        temperature: float = 1.0,
        repair_attempts: int = 1,
    ):
        """要求模型返回 JSON，并解析成 Python 对象。

        解析失败时，把错误回传给模型让它修正（最多 repair_attempts 次）。
        """
        text = self.complete(
            prompt,
            system=system,
            task=task,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        try:
            return extract_json(text)
        except JSONExtractError as e:
            last_err: Exception = e
            for _ in range(repair_attempts):
                repair = (
                    f"上一次的输出无法解析为合法 JSON（错误：{last_err}）。"
                    f"请只输出合法的 JSON，不要任何解释或代码块标记。\n\n"
                    f"上次输出：\n{text}"
                )
                text = self.complete(
                    repair,
                    system=system,
                    task=task,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                try:
                    return extract_json(text)
                except JSONExtractError as e2:
                    last_err = e2
            raise LLMError(f"模型未能返回合法 JSON：{last_err}") from last_err


def _extract_text(resp: anthropic.types.Message) -> str:
    """从响应里抽出纯文本。"""
    parts = [block.text for block in resp.content if block.type == "text"]
    return "".join(parts).strip()
