#!/usr/bin/env python3
"""Build a conservative Chinese novel style-editing dataset.

The source chapters contain no human-edited reference version.  Therefore the
rewrite suggestions made here are deliberately small, deterministic edits and
are exported with ``review_required`` metadata in ``annotations.json``.  The
four-field JSON files are suitable for inspecting in an Alpaca-compatible
loader, but must still be signed off by a human before training.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Sequence


SYSTEM_PROMPT = (
    "你是中文网络小说局部编辑器。仅修改语言表达，不得新增、遗漏或改变任何事实信息，包括剧情、人物关系、专名、数字、时间、地点、境界、道具、因果关系和对白归属。不得续写、扩写或解释。只输出可以直接替换原文的最终文本。"
)
INSTRUCTION = "请对以下文本进行最小必要的去AI腔改写；仅在确有必要时修改，原文自然则保持原样。"

DATASET_VERSION = "2026-08-31.v4"
TARGETS = {"train": 800, "val": 100, "test": 100}
# Keep samples are deliberately retained at roughly one third of each split.
# The remaining records are rewrite drafts and still require human review.
KEEP_TARGETS = {"train": 280, "val": 35, "test": 35}

# Chapter-level split.  A chapter never occurs in more than one split.
SPLIT_RANGES = {
    "1642:南明北伐录": {"train": range(1, 5), "val": range(5, 6), "test": range(6, 7)},
    "大秦我在岭南种田称霸": {
        "train": range(1, 21),
        "val": range(21, 26),
        "test": range(26, 31),
    },
}

TITLE_RE = re.compile(r"^\s*#{1,6}\s*第\s*\d+\s*章[^\n]*$", re.UNICODE)
REPEAT_TITLE_RE = re.compile(
    r"^[【\[]?\s*第\s*\d+\s*章[^。！？\n]{0,100}[】\]]?\s*$", re.UNICODE
)
DECORATION_RE = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$")
ITALIC_END_RE = re.compile(r"^\s*\*[^*]+\*\s*$")
THINK_RE = re.compile(r"<\s*/?\s*think\s*>", re.IGNORECASE)
METADATA_PREFIX_RE = re.compile(r"^(?:改写结果|修改后|以下是|说明|答案)\s*[:：]", re.UNICODE)
CODE_FENCE_RE = re.compile(r"```|~~~")
TERMINAL_RE = re.compile(r"[。！？!?…]$")
CLOSERS = "”\"’'）)]】》」』"

# These are intentionally high-confidence language-only substitutions.  The
# order matters: longer phrases are handled before their shorter components.
# Each tuple is (source, replacement, issue label).
REWRITE_RULES: tuple[tuple[str, str, str], ...] = (
    # Mixed ASCII punctuation in a subset of the source chapters.
    (",", "，", "标点混用"),
    (";", "；", "标点混用"),
    (":", "：", "标点混用"),
    ("?", "？", "标点混用"),
    ("!", "！", "标点混用"),
    # Mechanical connectors and filler.
    ("就在这时", "这时", "机械转折"),
    ("与此同时", "同时", "机械转折"),
    ("然后站起身", "随后站起身", "机械转折"),
    ("这一刻", "此刻", "机械转折"),
    ("不管是哪种情况", "无论哪种情况", "机械转折"),
    ("不管是", "无论是", "机械转折"),
    ("这也就给了", "这给了", "冗余表达"),
    ("这也就", "这就", "冗余表达"),
    ("一股子", "一股", "冗余表达"),
    # Repeated verbal beats.
    ("他顿了顿", "他停了停", "重复动作"),
    ("李恒顿了顿", "李恒停了停", "重复动作"),
    ("秦烈顿了顿", "秦烈停了停", "重复动作"),
    ("停顿了一下", "停了停", "重复动作"),
    ("顿了一下", "顿了顿", "重复动作"),
    # Keep ``地`` when dropping it would leave a dangling adverb.  The
    # replacements below are conservative lexical smoothing, not a blanket
    # deletion rule: phrases such as ``静静地听`` and ``一勺一勺地灌`` are
    # already grammatical and are intentionally left for ``keep`` samples.
    ("不慌不乱地", "不慌不忙地", "冗余程度副词"),
    ("不动声色地", "若无其事地", "冗余程度副词"),
    ("慢条斯理地", "不紧不慢地", "冗余程度副词"),
    ("半信半疑地", "将信将疑地", "冗余程度副词"),
    ("极慢地", "缓缓地", "冗余程度副词"),
    ("极轻地", "轻轻地", "冗余程度副词"),
    ("秦烈缓慢地", "秦烈缓缓地", "冗余程度副词"),
    ("缓慢地", "缓缓地", "冗余程度副词"),
    ("慢慢地", "缓缓地", "冗余程度副词"),
    ("静静地", "安静地", "冗余程度副词"),
    ("飞快地", "迅速地", "冗余程度副词"),
    ("成片成片地", "大片大片地", "冗余程度副词"),
    ("真真切切地", "真切地", "冗余程度副词"),
    ("悻悻地", "悻悻然", "冗余程度副词"),
    ("乱糟糟地", "杂乱地", "冗余程度副词"),
    # Common aspect/verb redundancies.
    ("没有马上", "没马上", "冗余表达"),
    ("没有立刻", "没立刻", "冗余表达"),
    ("没有立即", "没立即", "冗余表达"),
    ("他没有马上", "他没马上", "冗余表达"),
    ("他没有立刻", "他没立刻", "冗余表达"),
    ("他没有立即", "他没立即", "冗余表达"),
    ("抬起头来", "抬头", "冗余表达"),
    ("低下头去", "低头", "冗余表达"),
    # Aspect-bearing forms such as ``站了起来`` are intentionally kept out:
    # dropping ``了`` can change completion/aspect, which is a fact-level edit.
    ("沉默了片刻", "沉默片刻", "冗余表达"),
    ("沉默了一会儿", "沉默一会儿", "冗余表达"),
    ("开始动手", "动手", "冗余表达"),
    ("开始行动", "行动", "冗余表达"),
    ("开始让", "让", "冗余表达"),
    ("开始把", "把", "冗余表达"),
    # Quantifier expansions (``一颗一颗`` -> ``一颗接一颗``) are not
    # automatic rewrites: ``接`` adds a sequential relation.
    # A small set of high-confidence lexical smoothing edits.
    ("眼睛里的", "眼里的", "冗余表达"),
    ("眼睛里", "眼里", "冗余表达"),
    # Do not collapse ``脸上的表情``/``脸上的神色``: the location modifier
    # can carry emphasis and removing it is more than a purely mechanical fix.
    ("开口说道", "说道", "冗余表达"),
    ("开口说", "说", "冗余表达"),
    ("开口问", "问", "冗余表达"),
    ("开口道", "说道", "冗余表达"),
    ("盯着他看", "盯着他", "冗余表达"),
    ("盯着李恒看", "盯着李恒", "冗余表达"),
    ("盯着秦烈看", "盯着秦烈", "冗余表达"),
    ("大口大口地喘气", "大口喘气", "重复表达"),
    ("大口大口喘气", "大口喘气", "重复表达"),
    ("听得出来", "听得出", "冗余表达"),
    ("看得出来", "看得出", "冗余表达"),
    ("拿得出来", "拿得出", "冗余表达"),
    ("说不清的神色", "难辨的神色", "空泛心理"),
    ("说不清的东西", "难辨的东西", "空泛心理"),
    ("说不清是", "分不清是", "空泛心理"),
    ("不知道在想些什么", "不知在想什么", "过度解释"),
    ("不知道在想什么", "不知在想什么", "过度解释"),
    ("不知道该", "不知该", "过度解释"),
)

# Contrast constructions explicitly called out in the style files.  These
# preserve both sides of the contrast and are only applied when the exact
# phrase occurs, so they cannot silently rewrite an unrelated sentence.
CONTRAST_RULES: tuple[tuple[str, str, str], ...] = (
    ("不是寻常公文，是封查抄来的塘报", "并非寻常公文，而是封查抄来的塘报", "句式调整"),
    ("不是砖石墙，是粗木桩", "并非砖石墙，而是粗木桩", "句式调整"),
    ("不是一寨,是几寨合着", "不止一寨，是几寨合着", "句式调整"),
    ("不是一寨，是几寨合着", "不止一寨，是几寨合着", "句式调整"),
    ("不是开源活命,是逾矩", "不是开源活命，而是逾矩", "句式调整"),
    ("不是开源活命，是逾矩", "不是开源活命，而是逾矩", "句式调整"),
    ("不是莽撞,是步步都量过的", "不是莽撞，而是步步都量过的", "句式调整"),
    ("不是莽撞，是步步都量过的", "不是莽撞，而是步步都量过的", "句式调整"),
    ("不是一时起意", "并非一时起意", "句式调整"),
    ("不是来拼命的,是来抢食活命的", "不是来拼命的，而是来抢食活命的", "句式调整"),
    ("不是来拼命的，是来抢食活命的", "不是来拼命的，而是来抢食活命的", "句式调整"),
)


# Additional, one-way rules for paragraphs that do not contain one of the
# original high-signal AI-style markers above.  These are deliberately kept
# separate from ``REWRITE_RULES`` so a reviewer can distinguish the expanded
# candidate pool from the first-pass rules.  Every replacement is language
# only: it does not add/remove a count, named term, action, or dialogue span.
# Do not add inverse pairs here (for example ``看着`` -> ``望着`` and the
# reverse), since applying both in one pass would either cancel the edit or
# make the result depend on tuple order.
EXTRA_REWRITE_RULES: tuple[tuple[str, str, str], ...] = (
    # Aspect/time and other genuinely redundant function words.
    ("此时此刻", "此刻", "冗余时间"),
    ("并没有", "并未", "冗余表达"),
    ("已经", "已", "冗余表达"),
    ("仍然", "仍", "冗余表达"),
    # Temporal and connective smoothing.  These preserve the same relation;
    # no rule here rewrites a causal/contrastive connector to a different one.
    ("如今", "眼下", "时间表达"),
    ("此时", "这时", "时间表达"),
    ("紧接着", "随即", "机械转折"),
    ("忽然", "突然", "机械转折"),
    ("终于", "总算", "同义替换"),
    ("果然", "果真", "同义替换"),
    ("不由得", "不禁", "空泛心理"),
    ("仿佛", "像是", "同义替换"),
    ("似乎", "像是", "同义替换"),
    ("当即", "立刻", "机械转折"),
    ("立时", "当即", "机械转折"),
    ("此后", "之后", "时间表达"),
    # Perception/mental nouns.  These are one-way to avoid oscillating edits.
    ("神色", "神情", "同义替换"),
    ("脸色", "面色", "同义替换"),
    ("心底", "心头", "同义替换"),
    ("脑子里", "脑海里", "同义替换"),
    ("看向", "望向", "同义替换"),
    ("看见", "看到", "同义替换"),
    ("听见", "听到", "同义替换"),
    ("说道", "道", "冗余表达"),
    ("回道", "答道", "同义替换"),
    # Repeated directional complements.  ``伸出手`` is guarded below so
    # ``伸出手指`` (a distinct action) is never turned into ``伸手指``.
    ("抬起头", "抬头", "重复动作"),
    ("低下头", "低头", "重复动作"),
    ("抬起眼", "抬眼", "重复动作"),
    ("站起来", "站起身", "重复动作"),
    ("坐下来", "坐下", "重复动作"),
    ("蹲下来", "蹲下", "重复动作"),
    ("跪下来", "跪下", "重复动作"),
    ("转过身", "转身", "重复动作"),
    ("回过头", "回头", "重复动作"),
    # Forms containing ``了`` are left unchanged because removing the aspect
    # marker can alter event timing.  ``伸出手`` is likewise left for review
    # when it appears in a context where a finger/hand distinction matters.
    # Low-risk adverb/phrase smoothing.  ``片刻`` is intentionally absent:
    # replacing it with ``半晌`` would subtly alter a time expression.
    ("渐渐", "逐渐", "同义替换"),
    ("慢慢", "缓缓", "同义替换"),
    ("微微", "略微", "同义替换"),
    # ``悄悄`` describes visibility while ``暗暗`` describes inner intent;
    # they are not interchangeable without context.
    ("不疾不徐", "不紧不慢", "同义替换"),
    ("清清楚楚", "明明白白", "同义替换"),
    ("稀稀拉拉", "稀稀落落", "同义替换"),
    ("拖拖沓沓", "拖拖拉拉", "同义替换"),
    # Time spans such as ``一瞬`` and ``许久`` are retained verbatim.
    ("复杂得很", "很复杂", "冗余表达"),
    # Conjunction/preposition contractions and exact equivalents.
    ("并且", "而且", "机械转折"),
    ("但是", "可是", "机械转折"),
    ("由于", "因为", "因果连接"),
    ("如果", "若", "句式调整"),
    ("虽然", "虽", "冗余表达"),
    ("不必", "不用", "冗余表达"),
    ("一向", "向来", "同义替换"),
    ("从来", "向来", "同义替换"),
    ("约莫", "大约", "同义替换"),
    ("直到", "直至", "同义替换"),
    # ``为了`` can introduce a purpose clause whose scope is significant.
    ("对于", "对", "冗余表达"),
    ("按照", "按", "冗余表达"),
    # Colloquial spatial equivalents.  Keep these one-way and do not use the
    # shorter ``便``/``就`` style substitution, which can hit ``轻便``.
    ("外头", "外面", "同义替换"),
    ("里头", "里面", "同义替换"),
    ("后头", "后面", "同义替换"),
    ("前头", "前面", "同义替换"),
    ("底下", "下面", "同义替换"),
    ("上头", "上面", "同义替换"),
)


@dataclass(frozen=True)
class SourceParagraph:
    book: str
    chapter: int
    paragraph: int
    text: str
    source_path: str
    split: str


@dataclass
class Annotation:
    id: str
    book: str
    chapter: int
    paragraph: int
    input: str
    output: str
    label: str
    issue_types: list[str]
    review_status: str
    source_path: str
    split: str
    validation: dict[str, object]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def chapter_split(book: str, chapter: int) -> str | None:
    ranges = SPLIT_RANGES.get(book)
    if not ranges:
        return None
    for split, chapters in ranges.items():
        if chapter in chapters:
            return split
    return None


def split_policy_json() -> dict[str, dict[str, list[int]]]:
    """Return the chapter split map in a JSON-serializable form."""
    return {
        book: {split: list(chapters) for split, chapters in ranges.items()}
        for book, ranges in SPLIT_RANGES.items()
    }


def is_end_marker(text: str) -> bool:
    if "第一卷《屯田求生》终" in text:
        return True
    if ITALIC_END_RE.fullmatch(text) and "终" in text:
        return True
    return False


def iter_source_paragraphs(books_dir: Path) -> Iterator[SourceParagraph]:
    files = sorted(books_dir.glob("*/chapters/ch[0-9][0-9][0-9][0-9].md"))
    for path in files:
        book = path.parent.parent.name
        match = re.fullmatch(r"ch(\d{4})\.md", path.name)
        if not match:
            continue
        chapter = int(match.group(1))
        split = chapter_split(book, chapter)
        if split is None:
            continue
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n").lstrip("\ufeff")
        paragraph_no = 0
        for block in re.split(r"\n\s*\n", text):
            block = unicodedata.normalize("NFC", block.strip())
            if not block:
                continue
            if TITLE_RE.fullmatch(block) or DECORATION_RE.fullmatch(block):
                continue
            if REPEAT_TITLE_RE.fullmatch(block) or is_end_marker(block):
                continue
            # A volume marker can be attached to the end of a real sentence.
            block = re.sub(r"\s*《[^》]+》第[一二三四五六七八九十百]+卷《[^》]+》终。?\s*$", "", block)
            block = block.strip()
            if not block or TITLE_RE.fullmatch(block) or DECORATION_RE.fullmatch(block):
                continue
            paragraph_no += 1
            # Keep complete, reasonably sized blocks.  The source is already
            # paragraphized; this threshold only removes fragments and giant
            # accidental blocks, never truncates a sentence.
            if len(block) < 15 or len(block) > 220:
                continue
            terminal = block.rstrip(CLOSERS)
            if not terminal or not TERMINAL_RE.search(terminal):
                continue
            yield SourceParagraph(
                book=book,
                chapter=chapter,
                paragraph=paragraph_no,
                text=block,
                source_path=str(path),
                split=split,
            )


def normalize_for_dedup(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    return re.sub(r"\s+", "", text)


def convert_ascii_quotes(text: str) -> tuple[str, bool]:
    count = text.count('"')
    if count == 0 or count % 2:
        return text, False
    result: list[str] = []
    index = 0
    for char in text:
        if char == '"':
            result.append("“" if index % 2 == 0 else "”")
            index += 1
        else:
            result.append(char)
    return "".join(result), True


def _replace_spatial_token(text: str, source: str, replacement: str) -> str:
    """Rewrite spatial ``底下``/``上头`` without damaging fixed expressions."""
    if source == "底下":
        # These compounds are more natural with a shorter locative, and a
        # blind ``底下`` -> ``下面`` replacement would produce forms such as
        # ``天下面`` or ``地下面``.
        for phrase, value in (
            ("天底下", "天下"),
            ("地底下", "地下"),
            ("脚底下", "脚下"),
            ("栅栏根底下", "栅栏根下"),
            ("根底下", "根下"),
            # ``城底下`` can mean literally beneath the city; unlike a
            # physical fence root, collapsing it to ``城下`` may change the
            # location (below the city vs. outside/at the city walls).
            ("能耐底下", "能耐之下"),
            ("痛快底下", "痛快背后"),
            ("神色底下", "神色之下"),
            ("神情底下", "神情之下"),
            ("赏识底下", "赏识之下"),
        ):
            text = text.replace(phrase, value)

        def replace_bottom(match: re.Match[str]) -> str:
            start, end = match.span()
            left = text[max(0, start - 8) : start]
            right = text[end : min(len(text), end + 12)]
            # Idioms and institutional references retain their established
            # ``底下`` wording; physical locatives use the smoother form.
            if left.endswith(("眼皮", "城")) or right.startswith(("压着", "做手脚")):
                return match.group()
            return replacement

        return re.sub(re.escape(source), replace_bottom, text)

    if source == "上头":
        for phrase, value in (
            ("溪上头", "溪上游"),
            ("茅溷上头", "茅溷上游"),
        ):
            text = text.replace(phrase, value)

        def replace_top(match: re.Match[str]) -> str:
            start, end = match.span()
            left = text[max(0, start - 8) : start]
            right = text[end : min(len(text), end + 12)]
            # ``上头`` also means a superior authority in these chapters.
            # Preserve that register instead of turning it into ``上面``.
            if left.endswith(("给", "攥在", "这")) or right.startswith(
                ("的风向", "怪罪", "一道", "胡赖")
            ):
                return match.group()
            return replacement

        return re.sub(re.escape(source), replace_top, text)

    return text.replace(source, replacement)


def apply_extra_replacement(text: str, source: str, replacement: str) -> str:
    """Apply an expanded-pool rule with the few context guards it needs."""
    if source in {"底下", "上头"}:
        return _replace_spatial_token(text, source, replacement)
    if source in {"盯着他看", "盯着李恒看", "盯着秦烈看"}:
        # Only drop the redundant final ``看`` when it ends the clause.  In
        # ``盯着秦烈看了两息`` the following aspect/duration phrase is part
        # of the verb and must be retained.
        return re.sub(
            re.escape(source) + r"(?=[，。！？；、”\"）)]|$)",
            replacement,
            text,
        )
    return text.replace(source, replacement)


def apply_rewrite_rules(text: str) -> tuple[str, list[str]]:
    output = text
    issues: list[str] = []

    # Punctuation is safe to normalize even inside dialogue; it does not alter
    # words, numbers, attribution, or the sequence of events.
    for source, replacement, issue in REWRITE_RULES[:5]:
        if source in output:
            new_output = output.replace(source, replacement)
            if new_output != output:
                output = new_output
                issues.append(issue)

    converted, changed = convert_ascii_quotes(output)
    if changed:
        output = converted
        issues.append("引号规范")

    for source, replacement, issue in (
        REWRITE_RULES[5:] + CONTRAST_RULES + EXTRA_REWRITE_RULES
    ):
        if source not in output or source == replacement:
            continue
        new_output = apply_extra_replacement(output, source, replacement)
        if new_output != output:
            output = new_output
            issues.append(issue)

    # Keep labels unique while retaining rule order for readable metadata.
    return output, list(dict.fromkeys(issues))


ARABIC_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
CHINESE_NUMBER_CHARS = "零〇○一二两三四五六七八九十百千万亿兆壹贰叁肆伍陆柒捌玖拾佰仟萬億"
CHINESE_NUMBER_RE = re.compile(rf"[{CHINESE_NUMBER_CHARS}]+")
# A bare ``一`` in these lexicalized expressions is not a count.  Masking
# only these phrases lets ``这一刻`` -> ``此刻`` and ``一瞬间`` remain valid
# while still checking explicit quantities such as ``一百人`` or ``三十步``.
LEXICAL_ONE_PHRASES = (
    "一刻",
    "一瞬",
    "一向",
    "一直",
    "一时",
    "一下",
    "一会儿",
    "一旁",
    "一边",
    "一旦",
    "一共",
    "一同",
    "一味",
    "一再",
    "一概",
    "一经",
    "一度",
    "一贯",
    "一连",
)

# Number-bearing measure/time suffixes.  Comparing the whole number+unit
# token catches edits such as ``三十步`` -> ``三十里`` even when the numeric
# characters themselves remain unchanged.  The list intentionally omits
# ordinary lexical words (``一刻``/``一向``/``一旁`` etc.), which are handled
# by ``LEXICAL_ONE_PHRASES`` above.
QUANTITY_UNITS = (
    "时辰",
    "炷香",
    "盏茶",
    "公里",
    "分钟",
    "小时",
    "秒钟",
    "年月",
    "年",
    "月",
    "日",
    "天",
    "夜",
    "时",
    "刻",
    "里",
    "步",
    "丈",
    "尺",
    "寸",
    "斤",
    "两",
    "石",
    "斗",
    "升",
    "合",
    "担",
    "亩",
    "户",
    "口",
    "人",
    "名",
    "个",
    "件",
    "具",
    "门",
    "支",
    "把",
    "匹",
    "骑",
    "级",
    "成",
    "分",
    "岁",
    "回",
    "次",
    "层",
    "处",
    "道",
    "声",
    "阵",
    "拨",
    "批",
    "队",
    "轮",
    "枚",
    "张",
    "株",
    "方",
)
QUANTITY_UNIT_RE = re.compile(
    rf"(\d+(?:\.\d+)?|[{CHINESE_NUMBER_CHARS}]+)(?:\s*)("
    rf"{'|'.join(map(re.escape, sorted(QUANTITY_UNITS, key=len, reverse=True)))})"
)


def numeric_tokens(text: str) -> list[str]:
    """Return numeric facts in source order, excluding lexical ``一`` phrases."""
    spans: list[tuple[int, str]] = [
        (match.start(), match.group()) for match in ARABIC_NUMBER_RE.finditer(text)
    ]
    for match in CHINESE_NUMBER_RE.finditer(text):
        token = match.group()
        if token == "一" and any(text.startswith(phrase, match.start()) for phrase in LEXICAL_ONE_PHRASES):
            continue
        spans.append((match.start(), token))
    spans.sort(key=lambda item: item[0])
    return [token for _, token in spans]


def quantity_tokens(text: str) -> list[str]:
    """Return number-plus-unit facts in source order.

    A bare ``一`` in lexicalized expressions is not a quantity.  For example,
    ``这一刻`` may be smoothed to ``此刻`` without changing a measured time;
    that pair should still pass this check.  Explicit counts such as ``一刻
    钟`` remain visible because the following ``钟`` prevents the lexical
    masking.
    """
    tokens: list[str] = []
    for match in QUANTITY_UNIT_RE.finditer(text):
        number = match.group(1)
        start = match.start(1)
        if number == "一" and any(
            text.startswith(phrase, start)
            and not text.startswith(f"{phrase}钟", start)
            for phrase in LEXICAL_ONE_PHRASES
        ):
            continue
        tokens.append(match.group().replace(" ", ""))
    return tokens


def latin_tokens(text: str) -> list[str]:
    # Preserve order: swapping two fact-bearing identifiers must not pass
    # validation merely because their sorted multisets are equal.
    return re.findall(r"[A-Za-z][A-Za-z0-9_.-]*", text)


def quote_structure_signature(
    text: str,
) -> tuple[int, tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]]:
    """Return dialogue structure and its fact-bearing tokens.

    A rewrite is allowed to change wording inside dialogue (that is still
    language editing), but it must not change the number of quoted spans or
    their numeric/name-bearing tokens.  Comparing the complete payload would
    incorrectly reject legitimate punctuation and wording fixes.
    """
    normalized = text.replace("“", '"').replace("”", '"')
    payloads = re.findall(r'"([^"\n]*)"', normalized)
    return (
        normalized.count('"'),
        tuple((tuple(numeric_tokens(item)), tuple(latin_tokens(item))) for item in payloads),
    )


TERM_KEY_RE = re.compile(
    r"(?:name|names|alias|aliases|title|power[_-]?tier|character|location|place|"
    r"faction|item|artifact|weapon|book|volume|人名|姓名|别名|书名|卷名|人物|"
    r"地点|地名|势力|道具|法器|境界|官职)",
    re.IGNORECASE,
)


def known_terms(books_dir: Path) -> set[str]:
    """Collect conservative named-term candidates from book metadata.

    There is no separate entity annotation in the source corpus.  Only short
    strings below name-like keys are collected; free-form descriptions are
    deliberately ignored so ordinary vocabulary is not mistaken for a name.
    """
    terms: set[str] = set()
    metadata_names = {"characters.json", "bible.json", "outline.json"}
    for path in books_dir.glob("*/*.json"):
        if path.name not in metadata_names:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        def visit(value: object, key: str | None = None) -> None:
            if isinstance(value, str):
                if (
                    key
                    and TERM_KEY_RE.search(key)
                    and 2 <= len(value) <= 20
                    and re.search(r"[\u3400-\u9fff]", value)
                    and not re.search(r"[\n\r,，。；：:;！？!?]", value)
                ):
                    terms.add(value.strip())
                return
            if isinstance(value, dict):
                for child_key, child_value in value.items():
                    visit(child_value, str(child_key))
            elif isinstance(value, list):
                for child in value:
                    visit(child, key)

        visit(payload)
    # Terms visible in every relevant chapter and easy to verify exactly.
    terms.update(
        {
            "秦烈",
            "李恒",
            "赵铁山",
            "王守田",
            "刘顺",
            "马回子",
            "孟老汉",
            "阿筠",
            "王戊",
            "陈广",
            "赵佗",
            "任嚣",
            "冯恪",
            "周吏",
            "松山",
            "宁远",
            "博罗",
            "龙川",
            "横浦关",
            "黑石口",
            "五岭",
            "百越",
            "秦军",
            "清军",
        }
    )
    return {term for term in terms if len(term) >= 2}


def validate_pair(source: str, output: str, terms: set[str]) -> dict[str, object]:
    problems: list[str] = []
    warnings: list[str] = []
    if not source.strip() or not output.strip():
        problems.append("empty")
    if source != source.strip() or output != output.strip():
        problems.append("outer_whitespace")
    for candidate, side in ((source, "input"), (output, "output")):
        if (
            TITLE_RE.match(candidate)
            or REPEAT_TITLE_RE.fullmatch(candidate)
            or DECORATION_RE.fullmatch(candidate)
            or CODE_FENCE_RE.search(candidate)
            or THINK_RE.search(candidate)
        ):
            problems.append(f"metadata_or_think:{side}")
    if METADATA_PREFIX_RE.match(output):
        problems.append("explanation_prefix")
    if not TERMINAL_RE.search(output.rstrip(CLOSERS)):
        problems.append("incomplete_terminal")
    if numeric_tokens(source) != numeric_tokens(output):
        problems.append("numeric_token_changed")
    if quantity_tokens(source) != quantity_tokens(output):
        problems.append("quantity_token_changed")
    if latin_tokens(source) != latin_tokens(output):
        problems.append("latin_token_changed")
    if quote_structure_signature(source) != quote_structure_signature(output):
        problems.append("dialogue_structure_changed")
    source_terms = {term for term in terms if term in source}
    output_terms = {term for term in terms if term in output}
    for term in sorted(source_terms - output_terms):
        problems.append(f"named_term_lost:{term}")
    added_terms = sorted(output_terms - source_terms)
    if added_terms:
        # A rewrite must not introduce a controlled proper name or other
        # fact-bearing term that was absent from its source paragraph.
        problems.append("named_term_added")

    # Regression guards for rule mistakes that would otherwise look like a
    # valid token-preserving rewrite.  A future rule may only add a sequential
    # marker when the source already contains the same construction.
    forbidden = (
        ("脚步不止一个人", "bad_contrast"),
        ("不见凶意", "bad_contrast"),
        ("要的要的是", "duplicated_phrase"),
        ("恰恰所以", "connector_error"),
        ("传出一声", "subject_change"),
        ("正残破", "missing_locative"),
        ("正渠头", "missing_locative"),
        ("正某条", "missing_locative"),
        ("低不可闻哼", "dangling_adverb"),
        ("悄没声爬", "dangling_adverb"),
        ("灼灼烧", "dangling_adverb"),
        ("成股堵", "dangling_adverb"),
        ("成股走", "dangling_adverb"),
        ("成股候", "dangling_adverb"),
        ("一线一线轮", "dangling_adverb"),
        ("一处一处标", "dangling_adverb"),
        ("七嘴八舌嚷", "dangling_adverb"),
    )
    for phrase, code in forbidden:
        if phrase in output:
            problems.append(code)
    sequential_re = re.compile(r"一(?:个|颗|条|处|层|阵|股|波|拨|队|批|声|寸|勺|日)接一")
    if sequential_re.search(output) and not sequential_re.search(source):
        problems.append("added_sequential_marker")
    # A conservative diff warning.  It is recorded for human review, but is
    # not by itself a rejection: a one-character fix in a short paragraph can
    # have a large percentage diff while remaining perfectly safe.
    common = sum(1 for a, b in zip(source, output) if a == b)
    denominator = max(len(source), len(output), 1)
    diff_ratio = 1.0 - common / denominator
    if diff_ratio > 0.45 or len(output) > len(source) * 1.5:
        warnings.append("large_diff")
    return {
        "ok": not problems,
        "problems": problems,
        "warnings": warnings,
        "added_named_terms": added_terms,
        "diff_ratio": round(diff_ratio, 4),
        "source_numbers": numeric_tokens(source),
        "output_numbers": numeric_tokens(output),
        "source_quantities": quantity_tokens(source),
        "output_quantities": quantity_tokens(output),
    }


def stable_rank(text: str, seed: int) -> int:
    digest = hashlib.sha256(f"{seed}:{text}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def select_balanced(items: Sequence[SourceParagraph], count: int, seed: int) -> list[SourceParagraph]:
    """Pick a deterministic, chapter-balanced subset."""
    by_chapter: dict[tuple[str, int], list[SourceParagraph]] = defaultdict(list)
    for item in items:
        by_chapter[(item.book, item.chapter)].append(item)
    for values in by_chapter.values():
        values.sort(key=lambda item: stable_rank(item.text, seed))
    keys = sorted(by_chapter, key=lambda key: stable_rank(f"{key[0]}:{key[1]}", seed))
    selected: list[SourceParagraph] = []
    while len(selected) < count and keys:
        next_keys: list[tuple[str, int]] = []
        for key in keys:
            values = by_chapter[key]
            if values:
                selected.append(values.pop(0))
                if len(selected) >= count:
                    break
            if values:
                next_keys.append(key)
        keys = next_keys
    return selected


def build_annotations(books_dir: Path, seed: int) -> tuple[dict[str, list[Annotation]], dict[str, object]]:
    terms = known_terms(books_dir)
    raw = list(iter_source_paragraphs(books_dir))

    # Keep the earliest copy of exact/normalized duplicate paragraphs.  This
    # also prevents train/validation/test leakage through repeated short lines.
    seen: set[str] = set()
    unique: list[SourceParagraph] = []
    duplicate_count = 0
    for item in raw:
        key = normalize_for_dedup(item.text)
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        unique.append(item)

    by_split: dict[str, list[SourceParagraph]] = defaultdict(list)
    for item in unique:
        by_split[item.split].append(item)

    rewrite_pool: dict[str, list[tuple[SourceParagraph, str, list[str], dict[str, object]]]] = defaultdict(list)
    keep_pool: dict[str, list[SourceParagraph]] = defaultdict(list)
    rejected_pairs = 0
    issue_counts: Counter[str] = Counter()
    for split, items in by_split.items():
        for item in items:
            output, issues = apply_rewrite_rules(item.text)
            if output == item.text:
                keep_pool[split].append(item)
                continue
            validation = validate_pair(item.text, output, terms)
            if not validation["ok"]:
                rejected_pairs += 1
                continue
            rewrite_pool[split].append((item, output, issues, validation))
            issue_counts.update(issues)

    annotations: dict[str, list[Annotation]] = {}
    for split, target in TARGETS.items():
        keep_count = KEEP_TARGETS[split]
        rewrite_count = target - keep_count
        keeps = select_balanced(keep_pool[split], keep_count, seed + 11)
        rewrites_raw = rewrite_pool[split]
        rewrite_items = [entry[0] for entry in rewrites_raw]
        selected_rewrite_sources = select_balanced(rewrite_items, rewrite_count, seed + 29)
        rewrite_map = {entry[0].text: entry for entry in rewrites_raw}
        if len(keeps) != keep_count or len(selected_rewrite_sources) != rewrite_count:
            raise RuntimeError(
                f"{split} has insufficient candidates: keep {len(keeps)}/{keep_count}, "
                f"rewrite {len(selected_rewrite_sources)}/{rewrite_count}"
            )

        records: list[Annotation] = []
        for item in keeps:
            validation = validate_pair(item.text, item.text, terms)
            records.append(
                Annotation(
                    id=f"{item.book}/ch{item.chapter:04d}/p{item.paragraph:03d}",
                    book=item.book,
                    chapter=item.chapter,
                    paragraph=item.paragraph,
                    input=item.text,
                    output=item.text,
                    label="keep",
                    issue_types=[],
                    review_status="review_required",
                    source_path=item.source_path,
                    split=split,
                    validation=validation,
                )
            )
        for item in selected_rewrite_sources:
            _, output, issues, validation = rewrite_map[item.text]
            records.append(
                Annotation(
                    id=f"{item.book}/ch{item.chapter:04d}/p{item.paragraph:03d}",
                    book=item.book,
                    chapter=item.chapter,
                    paragraph=item.paragraph,
                    input=item.text,
                    output=output,
                    label="rewrite",
                    issue_types=issues,
                    review_status="review_required",
                    source_path=item.source_path,
                    split=split,
                    validation=validation,
                )
            )
        # Shuffle deterministically after balanced selection so the exported
        # files do not begin with a run of keep or rewrite labels.
        records.sort(key=lambda record: stable_rank(record.id, seed + 101))
        annotations[split] = records

    stats = {
        "raw_candidates": len(raw),
        "unique_candidates": len(unique),
        "duplicates_removed": duplicate_count,
        "rejected_rewrite_pairs": rejected_pairs,
        "source_files": sorted({item.source_path for item in raw}),
        "issue_counts_in_rewrite_pool": dict(issue_counts),
    }
    return annotations, stats


def alpaca_record(annotation: Annotation) -> dict[str, str]:
    return {
        "system": SYSTEM_PROMPT,
        "instruction": INSTRUCTION,
        "input": annotation.input,
        "output": annotation.output,
    }


def json_dump(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def validate_export(annotations: dict[str, list[Annotation]]) -> dict[str, object]:
    all_ids: set[str] = set()
    all_inputs: set[str] = set()
    counts: dict[str, dict[str, int]] = {}
    warning_counts: Counter[str] = Counter()
    warning_ids: list[str] = []
    for split, records in annotations.items():
        if len(records) != TARGETS[split]:
            raise RuntimeError(f"{split} count is {len(records)}, expected {TARGETS[split]}")
        split_counts = Counter(record.label for record in records)
        counts[split] = dict(split_counts)
        for record in records:
            if record.id in all_ids:
                raise RuntimeError(f"duplicate id: {record.id}")
            all_ids.add(record.id)
            key = normalize_for_dedup(record.input)
            if key in all_inputs:
                raise RuntimeError(f"duplicate input across exports: {record.id}")
            all_inputs.add(key)
            exported = alpaca_record(record)
            if list(exported) != ["system", "instruction", "input", "output"]:
                raise RuntimeError(f"invalid field order: {record.id}")
            if exported["system"] != SYSTEM_PROMPT or exported["instruction"] != INSTRUCTION:
                raise RuntimeError(f"constant prompt changed: {record.id}")
            if record.label == "keep" and record.input != record.output:
                raise RuntimeError(f"keep mismatch: {record.id}")
            if record.label == "rewrite" and record.input == record.output:
                raise RuntimeError(f"rewrite mismatch: {record.id}")
            if not record.validation.get("ok"):
                raise RuntimeError(f"validation failure: {record.id}")
            warnings = record.validation.get("warnings", [])
            if isinstance(warnings, list) and warnings:
                warning_ids.append(record.id)
                warning_counts.update(str(warning) for warning in warnings)
    if sum(len(records) for records in annotations.values()) != 1000:
        raise RuntimeError("total is not 1000")
    return {
        "counts": counts,
        "total": len(all_ids),
        "unique_inputs": len(all_inputs),
        "warning_counts": dict(warning_counts),
        "warning_record_ids": warning_ids,
    }


def write_outputs(
    output_dir: Path,
    annotations: dict[str, list[Annotation]],
    books_dir: Path,
    stats: dict[str, object],
    seed: int,
    refresh_test: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    existing_manifest = output_dir / "manifest.json"
    if existing_manifest.exists() and not refresh_test:
        try:
            previous = json.loads(existing_manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = {}
        previous_test_hash = previous.get("files", {}).get("test.json", {}).get("sha256")
        current_test = output_dir / "test.json"
        if previous_test_hash and current_test.exists() and sha256_file(current_test) != previous_test_hash:
            raise RuntimeError(
                "test.json is frozen and differs from manifest; use --refresh-test only when intentionally refreshing it"
            )

    # Serialize all split payloads before writing anything.  This makes the
    # frozen-test check transactional: a changed test set cannot leave train
    # or val partially updated before the command fails.
    serialized_splits = {
        split: json.dumps(
            [alpaca_record(record) for record in annotations[split]],
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
        for split in ("train", "val", "test")
    }
    if existing_manifest.exists() and not refresh_test:
        current_test = output_dir / "test.json"
        if current_test.exists():
            old_test = current_test.read_text(encoding="utf-8")
            if old_test != serialized_splits["test"]:
                raise RuntimeError(
                    "deterministic test set changed; pass --refresh-test to replace it"
                )

    export_hashes: dict[str, dict[str, object]] = {}
    for split in ("train", "val", "test"):
        path = output_dir / f"{split}.json"
        # Preserve the frozen test file's mtime when its content is unchanged.
        if not (
            split == "test"
            and existing_manifest.exists()
            and not refresh_test
            and path.exists()
            and path.read_text(encoding="utf-8") == serialized_splits[split]
        ):
            path.write_text(serialized_splits[split], encoding="utf-8")
        export_hashes[path.name] = {
            "sha256": sha256_file(path),
            "records": len(annotations[split]),
        }

    all_records = [record for split in ("train", "val", "test") for record in annotations[split]]
    json_dump(output_dir / "annotations.json", [asdict(record) for record in all_records])
    export_hashes["annotations.json"] = {
        "sha256": sha256_file(output_dir / "annotations.json"),
        "records": len(all_records),
    }

    source_hashes = {
        str(path.relative_to(books_dir.parent)): sha256_file(path)
        for path in sorted(books_dir.glob("*/chapters/ch[0-9][0-9][0-9][0-9].md"))
    }
    review_counts = {
        split: dict(Counter(record.label for record in records))
        for split, records in annotations.items()
    }
    manifest = {
        "dataset_version": DATASET_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "format": "llamafactory_alpaca_json",
        "schema": ["system", "instruction", "input", "output"],
        "review_status": "review_required",
        "human_confirmation": False,
        "training_ready": False,
        "warning": "源章节没有人工修订对照；rewrite output 是保守机器草稿，逐条人工确认后才可作为金标准训练数据。",
        "issue_categories": {
            "style_edit": [
                "空泛心理",
                "机械转折",
                "重复动作",
                "冗余程度副词",
                "冗余表达",
                "重复表达",
                "时间表达",
                "句式调整",
                "同义替换",
                "过度解释",
            ],
            "format_cleanup": ["标点混用", "引号规范"],
        },
        "split_policy": split_policy_json(),
        "targets": TARGETS,
        "keep_targets": KEEP_TARGETS,
        "actual_label_counts": review_counts,
        "stats": stats,
        "files": export_hashes,
        "source_files_sha256": source_hashes,
        "test_frozen": True,
        "test_freeze_note": "后续标注迭代不得修改 test.json；如确需刷新，显式传 --refresh-test 并更新本清单。",
    }
    json_dump(output_dir / "manifest.json", manifest)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--books-dir", type=Path, default=Path("books"))
    parser.add_argument("--output-dir", type=Path, default=Path("datasets/ai_style_editing"))
    parser.add_argument("--seed", type=int, default=20260828)
    parser.add_argument(
        "--refresh-test",
        action="store_true",
        help="允许在已有 manifest 时有意刷新冻结的 test.json",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if not args.books_dir.is_dir():
        print(f"books directory not found: {args.books_dir}", file=sys.stderr)
        return 2
    try:
        annotations, stats = build_annotations(args.books_dir, args.seed)
        summary = validate_export(annotations)
        stats["export_validation"] = summary
        write_outputs(
            args.output_dir,
            annotations,
            args.books_dir,
            stats,
            args.seed,
            args.refresh_test,
        )
    except (RuntimeError, OSError, UnicodeError) as exc:
        print(f"dataset build failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"output_dir": str(args.output_dir), **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
