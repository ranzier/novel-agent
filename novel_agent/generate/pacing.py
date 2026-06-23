"""节奏引擎：为每一章计算"节拍"，注入写作以避免平铺直叙。

网文的命门是节奏：读者需要规律的爽点（多巴胺），又要张弛有度（高紧张章
与喘息章交替），且每卷向其高潮稳步推进。

本引擎是【确定性】的——只根据大纲结构（章在卷内的位置、本章有无爽点、
是否卷末高潮）推算节拍，不调用 LLM。产出的指引文本注入正文生成的 prompt。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .outline_models import Outline, Volume


class BeatType(str, Enum):
    """章节节拍类型。"""

    SETUP = "铺垫"        # 卷初/喘息：交代信息、埋线、积累
    BUILD = "蓄势"        # 冲突升级、危机逼近，张力上行
    PAYOFF = "爆发"       # 爽点兑现：打脸、突破、逆袭
    CLIMAX = "高潮"       # 卷末大高潮：本卷核心冲突总爆发
    AFTERMATH = "余韵"    # 高潮之后：收束、过渡、抛新钩子


# 各节拍给写作的指引
_DIRECTIVES: dict[BeatType, str] = {
    BeatType.SETUP: (
        "本章为铺垫节拍：放缓节奏，交代背景、推进关系、埋下伏笔，"
        "为后续冲突蓄力。可不强求爽点，但章末必须留下牵引力。"
    ),
    BeatType.BUILD: (
        "本章为蓄势节拍：张力持续上行，让冲突或危机步步逼近，"
        "把读者的期待推高。结尾把危机推到临界点。"
    ),
    BeatType.PAYOFF: (
        "本章为爆发节拍：兑现爽点（打脸/突破/逆袭/真相揭晓），"
        "情绪要给足、节奏要快、对抗要解决得干脆利落，让读者爽到。"
    ),
    BeatType.CLIMAX: (
        "本章为卷末高潮：本卷核心冲突的总爆发，是全卷最强的一击。"
        "篇幅可更饱满，调动前文铺垫一并引爆，兑现本卷最大爽点。"
    ),
    BeatType.AFTERMATH: (
        "本章为余韵节拍：高潮之后适度收束，结算战果、缓和情绪、"
        "处理遗留，并自然抛出指向下一段的新钩子。节奏可稍缓。"
    ),
}


@dataclass
class Beat:
    """单章节拍。"""

    chapter: int
    beat_type: BeatType
    tension: int          # 紧张度 1~5
    expect_cool_point: bool   # 本章是否应兑现爽点
    directive: str        # 注入写作的节奏指引

    def as_block(self) -> str:
        """组装成注入 prompt 的文本块。"""
        bar = "▁▂▃▅▇"[self.tension - 1] if 1 <= self.tension <= 5 else "▃"
        return (
            f"【节奏控制】节拍：{self.beat_type.value}（紧张度 {self.tension}/5 {bar}）\n"
            f"{self.directive}"
        )


def _volume_of(outline: Outline, chapter: int) -> tuple[Volume | None, int, int]:
    """返回 (所属卷, 卷内位置从1起, 卷内总章数)。"""
    for v in outline.volumes:
        idxs = [c.index for c in v.chapters]
        if chapter in idxs:
            ordered = sorted(idxs)
            return v, ordered.index(chapter) + 1, len(ordered)
    return None, 0, 0


def compute_beat(
    outline: Outline,
    chapter: int,
    *,
    payoff_period: int = 4,
) -> Beat:
    """为某章推算节拍。

    规则（按优先级）：
    1) 卷内最后一章 → 高潮(CLIMAX)
    2) 紧跟高潮之后的一章 → 余韵(AFTERMATH)
    3) 大纲本章标了爽点，或距上一个爽点已达 payoff_period 章 → 爆发(PAYOFF)
    4) 卷内位置靠后(>60%) → 蓄势(BUILD)
    5) 其余 → 铺垫(SETUP)
    """
    vol, pos, total = _volume_of(outline, chapter)
    ch = outline.chapter(chapter)
    has_cool = bool(ch and ch.cool_point.strip()) if ch else False

    # 1) 卷末高潮
    if vol and total > 0 and pos == total:
        return Beat(chapter, BeatType.CLIMAX, 5, True, _DIRECTIVES[BeatType.CLIMAX])

    # 2) 高潮余韵（卷首章，且不是第1卷第1章）
    if vol and pos == 1 and vol.index > 1:
        return Beat(
            chapter, BeatType.AFTERMATH, 2, False, _DIRECTIVES[BeatType.AFTERMATH]
        )

    # 3) 爆发：本章标了爽点，或距上次爽点够久
    chapters_since_payoff = _chapters_since_last_payoff(outline, chapter)
    if has_cool or (
        chapters_since_payoff is not None
        and chapters_since_payoff >= payoff_period
    ):
        return Beat(chapter, BeatType.PAYOFF, 4, True, _DIRECTIVES[BeatType.PAYOFF])

    # 4) 卷内靠后 → 蓄势
    if total > 0 and pos / total > 0.6:
        return Beat(chapter, BeatType.BUILD, 4, False, _DIRECTIVES[BeatType.BUILD])

    # 5) 铺垫
    return Beat(chapter, BeatType.SETUP, 2, False, _DIRECTIVES[BeatType.SETUP])


def _chapters_since_last_payoff(outline: Outline, chapter: int) -> int | None:
    """距上一个"标了爽点的章"过了几章；找不到返回 None。"""
    prev_payoffs = [
        c.index
        for c in outline.all_chapters()
        if c.index < chapter and c.cool_point.strip()
    ]
    if not prev_payoffs:
        return None
    return chapter - max(prev_payoffs)
