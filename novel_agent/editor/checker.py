"""一致性校验器。

两层校验：
  1) 确定性规则（rule）：代码层比对，免费且精确
     - 未定义角色：正文/抽取出现了设定库外的"新角色名"
     - 境界倒退：主角或角色境界比上一章末更低
     - 死人复活：上一章已死的角色又出场
  2) LLM 语义校验（llm）：便宜模型查规则覆盖不到的
     - 时间线矛盾、世界规则违背、伏笔逻辑、金手指越界

校验在"写正文 → 校验 → 固化入库"之间，避免把错误状态写进记忆。
"""

from __future__ import annotations

from ..bible import Bible, CharacterBook
from ..bible.models import PowerSystem
from ..llm import LLMGateway, LLMError
from ..memory.state_models import ChapterSummary, WorldState
from .models import Issue, ReviewResult, Severity


# ---------------- 确定性规则校验 ----------------

def _tier_rank(power_system: PowerSystem, tier_name: str) -> int | None:
    """把境界名映射到序号；模糊匹配（境界名可能带后缀如'凝灵境三层'）。"""
    if not tier_name:
        return None
    best: int | None = None
    for t in power_system.tiers:
        if t.name and t.name in tier_name:
            # 取匹配到的层级里 order 最大的（最具体）
            if best is None or t.order > best:
                best = t.order
    return best


def _known_names(characters: CharacterBook) -> set[str]:
    names: set[str] = set()
    for c in characters.characters:
        names.add(c.name)
        names.update(c.aliases)
    return names


def rule_checks(
    *,
    bible: Bible,
    characters: CharacterBook,
    prev_state: WorldState,
    new_summary: ChapterSummary,
    new_state: WorldState,
) -> list[Issue]:
    """基于抽取出的结构化数据做确定性比对。"""
    issues: list[Issue] = []
    known = _known_names(characters)

    # 1) 未定义角色：本章出场角色不在设定库（排除明显的群众/称谓）
    for name in new_summary.characters:
        clean = name.split("（")[0].strip()  # 去掉"（提及，未出场）"等后缀
        if not clean or clean in known:
            continue
        # 已在世界状态里登记过的也算已知（可能是前几章引入的）
        if any(c.name == clean for c in prev_state.characters):
            continue
        issues.append(
            Issue(
                severity=Severity.WARN,
                category="角色",
                message=f"出现设定库外的新角色「{clean}」，请确认是有意引入还是角色名漂移",
                source="rule",
            )
        )

    # 2) 境界倒退（主角）
    old_rank = _tier_rank(bible.power_system, prev_state.protagonist_tier)
    new_rank = _tier_rank(bible.power_system, new_state.protagonist_tier)
    if old_rank is not None and new_rank is not None and new_rank < old_rank:
        issues.append(
            Issue(
                severity=Severity.ERROR,
                category="境界",
                message=(
                    f"主角境界倒退：上一章「{prev_state.protagonist_tier}」"
                    f"→ 本章「{new_state.protagonist_tier}」"
                ),
                source="rule",
            )
        )

    # 3) 死人复活：上一章已死，本章又出场
    dead_before = {
        c.name for c in prev_state.characters if c.status == "死亡"
    }
    for name in new_summary.characters:
        clean = name.split("（")[0].strip()
        if clean in dead_before:
            issues.append(
                Issue(
                    severity=Severity.ERROR,
                    category="生死",
                    message=f"已死亡角色「{clean}」在本章再次出场（死人复活）",
                    source="rule",
                )
            )

    # 4) 角色境界倒退（配角）
    for cs in new_state.characters:
        prev = prev_state.character(cs.name)
        if not prev:
            continue
        r_old = _tier_rank(bible.power_system, prev.power_tier)
        r_new = _tier_rank(bible.power_system, cs.power_tier)
        if r_old is not None and r_new is not None and r_new < r_old:
            issues.append(
                Issue(
                    severity=Severity.WARN,
                    category="境界",
                    message=(
                        f"角色「{cs.name}」境界疑似倒退："
                        f"{prev.power_tier} → {cs.power_tier}"
                    ),
                    source="rule",
                )
            )

    return issues


# ---------------- LLM 语义校验 ----------------

_SYSTEM = """你是小说连续性审校员。你的唯一职责是发现【本章正文与既定设定/前文状态的矛盾】。
只报告确有依据的矛盾，不做文学评价，不提改进建议，不臆测。
若没有任何矛盾，返回空的 issues 数组。只输出 JSON。"""

_PROMPT = """核对小说《{title}》第 {index} 章是否与既定设定、世界状态存在矛盾。

【世界硬规则】
力量体系：{tiers}
世界规则：{rules}
金手指及其限制：{golden_finger}

【上一章末世界状态】
主角境界：{prev_tier}
已死亡角色：{dead}
未回收伏笔：{foreshadowing}

【本章正文】
{body}

请只找出【矛盾】，按以下类别检查：
- 时间线：与已知时间顺序冲突
- 设定：违背力量体系层级或世界硬规则
- 金手指：能力越界、突破了既定限制
- 生死：与已死亡名单冲突
- 伏笔：与已埋伏笔逻辑冲突

输出 JSON：
{{
  "issues": [
    {{
      "severity": "error 或 warn",
      "category": "时间线/设定/金手指/生死/伏笔",
      "message": "矛盾的具体描述",
      "evidence": "正文中引发矛盾的片段（20字内）"
    }}
  ]
}}

severity 规则：直接违背硬设定/死亡名单=error；模糊或疑似=warn。
没有矛盾则 issues 为空数组。"""


def llm_checks(
    gateway: LLMGateway,
    *,
    bible: Bible,
    prev_state: WorldState,
    index: int,
    body: str,
) -> list[Issue]:
    tiers = " → ".join(t.name for t in bible.power_system.tiers) or "（未定义）"
    dead = (
        "、".join(c.name for c in prev_state.characters if c.status == "死亡")
        or "（无）"
    )
    prompt = _PROMPT.format(
        title=bible.title,
        index=index,
        tiers=tiers,
        rules="；".join(bible.rules) or "（无）",
        golden_finger=bible.golden_finger,
        prev_tier=prev_state.protagonist_tier or "（未知）",
        dead=dead,
        foreshadowing="；".join(f.text for f in prev_state.foreshadowing) or "（无）",
        body=body,
    )
    try:
        data = gateway.complete_json(
            prompt, system=_SYSTEM, task="review", max_tokens=2048
        )
    except LLMError:
        # 语义校验失败不阻断主流程
        return []
    raw = data.get("issues", []) if isinstance(data, dict) else []
    issues = []
    for d in raw:
        if isinstance(d, dict):
            issue = Issue.from_dict(d)
            issue.source = "llm"
            issues.append(issue)
    return issues


# ---------------- 统一入口 ----------------

def review_chapter(
    gateway: LLMGateway,
    *,
    bible: Bible,
    characters: CharacterBook,
    prev_state: WorldState,
    new_summary: ChapterSummary,
    new_state: WorldState,
    body: str,
    use_llm: bool = True,
) -> ReviewResult:
    """对一章做完整校验：确定性规则 + LLM 语义。"""
    issues = rule_checks(
        bible=bible,
        characters=characters,
        prev_state=prev_state,
        new_summary=new_summary,
        new_state=new_state,
    )
    if use_llm:
        issues.extend(
            llm_checks(
                gateway,
                bible=bible,
                prev_state=prev_state,
                index=new_summary.index,
                body=body,
            )
        )
    return ReviewResult(chapter=new_summary.index, issues=issues)
