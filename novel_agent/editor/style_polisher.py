"""Local, paragraph-level prose polishing with conservative rollback guards.

The fine-tuned model is deliberately kept separate from ``LLMGateway``: the
main gateway speaks Anthropic's API and owns creative generation, while this
module talks to llama.cpp's OpenAI-compatible endpoint and may only edit
surface wording.
"""

from __future__ import annotations

import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Iterable, Protocol

from ..config import Config
from ..project import Project
from ..storage import _to_plain

SYSTEM_PROMPT = (
    "你是中文网络小说局部编辑器。仅修改语言表达，不得新增、遗漏或改变任何事实信息，包括剧情、人物关系、专名、数字、时间、地点、境界、道具、因果关系和对白归属。"
    "不得续写、扩写或解释。只输出可以直接替换原文的最终文本。"
)
INSTRUCTION = "请对以下文本进行最小必要的去AI腔改写；仅在确有必要时修改，原文自然则保持原样。"

_BLOCK_SPLIT_RE = re.compile(r"(\n[ \t]*\n+)")
_DECORATION_RE = re.compile(r"(?:[-*_]\s*){3,}")
_TITLE_RE = re.compile(r"#{1,6}\s+.+")
_TERMINAL_RE = re.compile(r"[。！？!?…]$")
_CLOSERS = "\"'”’」』】》）)]"
_META_RE = re.compile(
    r"^(?:改写(?:结果|后)?|优化(?:结果|后)?|最终文本|以下是)\s*[:：]",
    re.IGNORECASE,
)
_FORBIDDEN_OUTPUT_RE = re.compile(r"<\/?think>|```|^#{1,6}\s", re.IGNORECASE | re.MULTILINE)

_ARABIC_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_CHINESE_NUMBER_CHARS = "零〇○一二两三四五六七八九十百千万亿兆壹贰叁肆伍陆柒捌玖拾佰仟萬億"
_CHINESE_NUMBER_RE = re.compile(rf"[{_CHINESE_NUMBER_CHARS}]+")
_LEXICAL_ONE_PHRASES = (
    "一刻", "一瞬", "一向", "一直", "一时", "一下", "一会儿", "一旁",
    "一边", "一旦", "一共", "一同", "一味", "一再", "一概", "一经", "一度",
    "一贯", "一连", "一点",
)
_QUANTITY_UNITS = (
    "时辰", "炷香", "盏茶", "公里", "分钟", "小时", "秒钟", "年", "月", "日", "天", "夜",
    "时", "刻", "里", "步", "丈", "尺", "寸", "斤", "两", "石", "斗", "升", "合", "担",
    "亩", "户", "口", "人", "名", "个", "件", "具", "门", "支", "把", "匹", "骑", "级",
    "成", "分", "岁", "回", "次", "层", "处", "道", "声", "阵", "拨", "批", "队", "轮",
    "枚", "张", "株", "方",
)
_QUANTITY_RE = re.compile(
    rf"(\d+(?:\.\d+)?|[{_CHINESE_NUMBER_CHARS}]+)\s*"
    rf"({'|'.join(map(re.escape, sorted(_QUANTITY_UNITS, key=len, reverse=True)))})"
)
_TERM_KEY_RE = re.compile(
    r"(?:name|alias|title|tier|location|place|faction|item|artifact|weapon|"
    r"人名|姓名|别名|书名|卷名|地点|地名|势力|道具|法器|境界|官职)",
    re.IGNORECASE,
)
_NEGATION_RE = re.compile(r"不得|不能|不会|并未|尚未|未曾|没有|无法|不|没|未|无|非|莫|勿|否")
_LEXICAL_NEGATION_PHRASES = (
    "不由得", "不禁", "不过", "不料", "不免", "无论",
)


class StylePolishError(RuntimeError):
    """The local editing service is unavailable or returned no usable text."""


class ParagraphEditor(Protocol):
    def check_available(self) -> None: ...

    def rewrite(self, paragraph: str) -> str: ...


@dataclass
class PolishStats:
    eligible: int = 0
    changed: int = 0
    unchanged: int = 0
    rolled_back: int = 0
    failed: int = 0
    skipped: int = 0
    reasons: dict[str, int] = field(default_factory=dict)
    service_error: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


class LocalStyleClient:
    """Thin llama.cpp client using its OpenAI-compatible chat endpoint."""

    def __init__(self, config: Config):
        from openai import OpenAI

        self.model = config.style_polish_model
        self.max_tokens = config.style_polish_max_tokens
        self.temperature = config.style_polish_temperature
        self._client = OpenAI(
            base_url=config.style_polish_base_url.rstrip("/") + "/",
            api_key="local",
            timeout=config.style_polish_timeout,
            max_retries=0,
        )
        self._availability_error: StylePolishError | None = None
        self._available = False

    def check_available(self) -> None:
        if self._available:
            return
        if self._availability_error is not None:
            raise self._availability_error
        try:
            models = list(self._client.models.list().data)
            model_ids = [item.id for item in models if getattr(item, "id", "")]
            # llama-server 未设 --alias 时会暴露 GGUF 路径/文件名。
            # 单模型服务可以安全自动采用唯一 id，免去强制改启动命令。
            if self.model not in model_ids and len(model_ids) == 1:
                self.model = model_ids[0]
            self._available = True
        except Exception as exc:  # noqa: BLE001 - normalized at this boundary
            self._availability_error = StylePolishError(
                f"无法连接本地去 AI 腔服务：{exc}"
            )
            raise self._availability_error from exc

    def rewrite(self, paragraph: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"{INSTRUCTION}\n\n{paragraph}",
                    },
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            content = response.choices[0].message.content
        except Exception as exc:  # noqa: BLE001 - a paragraph failure must roll back
            raise StylePolishError(str(exc)) from exc
        if not isinstance(content, str) or not content.strip():
            raise StylePolishError("本地模型返回了空文本")
        return content.strip()


class StylePolisher:
    def __init__(
        self,
        editor: ParagraphEditor,
        *,
        protected_terms: Iterable[str] = (),
        min_chars: int = 15,
        max_chars: int = 220,
        concurrency: int = 2,
    ):
        self.editor = editor
        self.protected_terms = frozenset(protected_terms)
        self.min_chars = max(1, min_chars)
        self.max_chars = max(self.min_chars, max_chars)
        self.concurrency = max(1, concurrency)

    @classmethod
    def from_config(cls, config: Config, project: Project) -> "StylePolisher":
        return cls(
            LocalStyleClient(config),
            protected_terms=collect_protected_terms(project),
            min_chars=config.style_polish_min_chars,
            max_chars=config.style_polish_max_chars,
            concurrency=config.style_polish_concurrency,
        )

    def polish_chapter(self, text: str) -> tuple[str, PolishStats]:
        parts = _BLOCK_SPLIT_RE.split(text)
        indices = [
            i for i in range(0, len(parts), 2)
            if self._eligible(parts[i])
        ]
        stats = PolishStats(eligible=len(indices), skipped=(len(parts) + 1) // 2 - len(indices))
        if not indices:
            return text, stats

        self.editor.check_available()

        def process(index: int) -> tuple[int, str, str, tuple[str, ...]]:
            source = parts[index]
            try:
                candidate = self.editor.rewrite(source)
            except Exception as exc:  # noqa: BLE001 - rollback is intentional
                return index, source, "failed", (type(exc).__name__,)
            problems = validate_rewrite(source, candidate, self.protected_terms)
            if problems:
                return index, source, "rolled_back", problems
            status = "unchanged" if candidate == source else "changed"
            return index, candidate, status, ()

        with ThreadPoolExecutor(
            max_workers=min(self.concurrency, len(indices)),
            thread_name_prefix="style-polish",
        ) as pool:
            results = list(pool.map(process, indices))

        reasons: Counter[str] = Counter()
        for index, output, status, problems in results:
            parts[index] = output
            setattr(stats, status, getattr(stats, status) + 1)
            reasons.update(problems)
        stats.reasons = dict(sorted(reasons.items()))
        return "".join(parts), stats

    def _eligible(self, paragraph: str) -> bool:
        if paragraph != paragraph.strip():
            return False
        if not self.min_chars <= len(paragraph) <= self.max_chars:
            return False
        if "\n" in paragraph or _TITLE_RE.fullmatch(paragraph):
            return False
        if _DECORATION_RE.fullmatch(paragraph):
            return False
        terminal = paragraph.rstrip(_CLOSERS)
        return bool(terminal and _TERMINAL_RE.search(terminal))


def validate_rewrite(
    source: str, output: str, protected_terms: Iterable[str] = ()
) -> tuple[str, ...]:
    """Return hard validation failures; any result means use the source."""
    problems: list[str] = []
    if not output or output != output.strip():
        problems.append("outer_whitespace")
    if "\n" in output:
        problems.append("paragraph_structure_changed")
    if _FORBIDDEN_OUTPUT_RE.search(output) or _META_RE.match(output):
        problems.append("metadata_or_reasoning")
    terminal = output.rstrip(_CLOSERS)
    if not terminal or not _TERMINAL_RE.search(terminal):
        problems.append("incomplete_output")
    if _numeric_tokens(source) != _numeric_tokens(output):
        problems.append("numeric_token_changed")
    if _quantity_tokens(source) != _quantity_tokens(output):
        problems.append("quantity_token_changed")
    if _latin_tokens(source) != _latin_tokens(output):
        problems.append("latin_token_changed")
    if _quote_signature(source) != _quote_signature(output):
        problems.append("dialogue_structure_changed")
    if _negation_count(source) != _negation_count(output):
        problems.append("negation_changed")

    terms = set(protected_terms)
    source_terms = {term for term in terms if term in source}
    output_terms = {term for term in terms if term in output}
    if source_terms - output_terms:
        problems.append("named_term_lost")
    if output_terms - source_terms:
        problems.append("named_term_added")

    if source:
        ratio = len(output) / len(source)
        diff_ratio = 1.0 - SequenceMatcher(None, source, output).ratio()
        if ratio < 0.6 or ratio > 1.5 or diff_ratio > 0.65:
            problems.append("change_too_large")
    return tuple(dict.fromkeys(problems))


def collect_protected_terms(project: Project) -> set[str]:
    """Collect conservative fact-bearing terms from this book's metadata."""
    terms: set[str] = set()

    def visit(value: object, key: str = "") -> None:
        if isinstance(value, str):
            candidate = value.strip()
            if (
                _TERM_KEY_RE.search(key)
                and 2 <= len(candidate) <= 20
                and re.search(r"[\u3400-\u9fff]", candidate)
                and not re.search(r"[\n\r,，。；：:;！？!?]", candidate)
            ):
                terms.add(candidate)
            return
        if isinstance(value, dict):
            for child_key, child in value.items():
                visit(child, str(child_key))
        elif isinstance(value, list):
            for child in value:
                visit(child, key)

    visit(_to_plain(project.load_bible()))
    visit(_to_plain(project.load_characters()))
    if project.has_outline():
        visit(_to_plain(project.load_outline()))
    return terms


def _numeric_tokens(text: str) -> list[str]:
    spans: list[tuple[int, str]] = [
        (match.start(), match.group()) for match in _ARABIC_NUMBER_RE.finditer(text)
    ]
    for match in _CHINESE_NUMBER_RE.finditer(text):
        token = match.group()
        if token == "一" and any(
            text.startswith(phrase, match.start()) for phrase in _LEXICAL_ONE_PHRASES
        ):
            continue
        spans.append((match.start(), token))
    return [token for _, token in sorted(spans)]


def _quantity_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for match in _QUANTITY_RE.finditer(text):
        number = match.group(1)
        start = match.start(1)
        if number == "一" and any(
            text.startswith(phrase, start)
            and not text.startswith(f"{phrase}钟", start)
            for phrase in _LEXICAL_ONE_PHRASES
        ):
            continue
        tokens.append(match.group().replace(" ", ""))
    return tokens


def _latin_tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9_.-]*", text)


def _negation_count(text: str) -> int:
    masked = text
    for phrase in _LEXICAL_NEGATION_PHRASES:
        masked = masked.replace(phrase, "")
    return len(_NEGATION_RE.findall(masked))


def _quote_signature(text: str) -> tuple[int, tuple[tuple[str, ...], ...]]:
    normalized = (
        text.replace("“", '"').replace("”", '"')
        .replace("「", '"').replace("」", '"')
    )
    payloads = re.findall(r'"([^"\n]*)"', normalized)
    return normalized.count('"'), tuple(tuple(_numeric_tokens(p)) for p in payloads)
