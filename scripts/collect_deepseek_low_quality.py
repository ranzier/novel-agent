"""Build a manual-review queue for weak train-deepseek rewrite pairs.

The source dataset is never modified. Reviewers edit the ``output`` fields in
the generated JSON and can later merge them back by ``source_index``.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "datasets" / "ai_style_editing"
SOURCE = DATA_DIR / "train-deepseek.json"
DESTINATION = DATA_DIR / "train-deepseek-low-quality-review.json"


# These are deliberately high-confidence findings rather than every automatic
# warning. Each note states what a human reviewer should preserve or repair.
CONTENT_FINDINGS: dict[int, tuple[str, list[str], str]] = {
    0: (
        "P1",
        ["新增原文信息", "过度改写"],
        "“尖锐刺耳”被改成“扎得人耳朵生疼”，新增人物身体感受；整段也被强行口语化。",
    ),
    8: (
        "P1",
        ["新增比喻", "标点节奏受损"],
        "凭空加入“从阎王手里”这一比喻，并删除“北边、西边”等处的必要停顿。",
    ),
    15: (
        "P2",
        ["过度解释", "改写幅度过大"],
        "原句凝练，输出把“审视与惋惜”拆开解释，变长且更像模型扩写。",
    ),
    24: (
        "P1",
        ["术语泛化", "过度改写"],
        "大段改写教范内容，把“临时防御、迟滞”等术语泛化，并把“身体”换成带额外色彩的“躯壳”。",
    ),
    33: (
        "P1",
        ["语义扩大", "无必要改写"],
        "“散人”被改成含义更强的“散兵游勇”，“场中”被机械扩成“场地中央”。",
    ),
    37: (
        "P1",
        ["指代可能变化", "强行口语化"],
        "“不是一个寨子的”改成“不是本寨”改变叙述参照，“探看”改“打探”也强化了目的性。",
    ),
    64: (
        "P0",
        ["事实表达不精确", "语义变化"],
        "“全部阵亡”改成口语化的“全打光”，“没有二两”改成“掏不出来”，事实表达不再严格等价。",
    ),
    637: (
        "P1",
        ["语义阶段变化", "标点受损"],
        "“这一泄之机”是气势开始泄，改成“这一溃之机”把状态推进到已经溃败。",
    ),
    642: (
        "P1",
        ["新增材质信息", "标点受损"],
        "“牍”被具体化为“木牍”，加入原文未说明的材质；多处停顿也被删除。",
    ),
    649: (
        "P0",
        ["信息遗漏", "语病"],
        "删掉“下到地里”这一层信息，“渗进土里地下的还在”搭配也不通顺。",
    ),
    675: (
        "P0",
        ["输入损坏"],
        "当前 input 自身误删“来得”；应先恢复为 train.json 中的原始 input，再检查 output。",
    ),
    696: (
        "P0",
        ["专名称谓变化", "新增动作"],
        "“严某那老东西”被改成“严老头”，称谓关系改变；“想破脑袋”也属新增表达。",
    ),
    701: (
        "P0",
        ["表达生硬", "搭配错误"],
        "“透出青劲儿来”不是自然搭配，“苗垂着的头”改成“耷拉着的脑袋”也过度拟人。",
    ),
    708: (
        "P0",
        ["确定程度变化", "词义不当"],
        "“不会干透”改成“不至于干透”降低确定性；“这一套”改成“这套路”带贬义且搭配不当。",
    ),
    712: (
        "P1",
        ["判断强度变化"],
        "“确认不会漏气”改成“觉着不漏气”，把确认过的事实降成主观感觉。",
    ),
    729: (
        "P1",
        ["概念泛化", "语义变化"],
        "“步兵”泛化成“当兵的”，“最后才看自己”改成“最后才顾得上自个儿”，侧重点变化。",
    ),
    731: (
        "P0",
        ["语序错误", "表达退化"],
        "“一盘散沙”被倒装成不自然的“散沙一盘”，输出明显差于输入。",
    ),
    733: (
        "P0",
        ["概率强度变化"],
        "“很可能”改成“十有八九”，无依据地提高事件发生概率。",
    ),
    747: (
        "P0",
        ["数量逻辑丢失"],
        "“至少”是数量下界，改成“好歹”后失去原有的数量逻辑。",
    ),
    761: (
        "P1",
        ["新增态度", "强行口语化"],
        "“鼻子里出了口气”改成“哼了一声”，额外赋予人物不满或轻蔑态度。",
    ),
    847: (
        "P0",
        ["语法退化"],
        "删除结构助词后形成“成股堵住”的生硬搭配，应恢复或重新组织句子。",
    ),
    872: (
        "P0",
        ["关键信息遗漏"],
        "“伤亡”同时包含伤和死，输出“伤了多少”遗漏死亡信息。",
    ),
    912: (
        "P0",
        ["专业术语误改"],
        "“闷尾”指炮声尾音状态，不能改成描述声音本体的“闷响”。",
    ),
}


# Five or more normalized punctuation marks were deleted. These records are
# kept as a separate tier because the main task is often to restore syntax and
# rhythm rather than rewrite every word.
SEVERE_PUNCTUATION = [
    513, 526, 537, 544, 557, 565, 585, 591, 606, 607, 617, 627, 628, 634,
    640, 649, 651, 659, 666, 677, 678, 686, 687, 940, 942, 953, 963, 970,
    973, 982, 986, 988, 998, 999,
]


# These are not automatically wrong, but their outputs show the dataset's
# strongest register-homogenization pattern. They deserve manual comparison.
REGISTER_REVIEW = [
    693, 695, 702, 703, 718, 721, 729, 732, 735, 736, 741, 752, 756, 757,
    760, 761, 765, 775, 808, 815, 823, 831, 847, 857, 920, 926, 944, 946,
    962, 968, 969, 985, 992, 997,
]

STRONG_COLLOQUIAL_WORDS = (
    "瞅",
    "自个儿",
    "玩意儿",
    "一宿",
    "里头",
    "外头",
    "前头",
    "后头",
    "叫唤",
    "撵",
    "火星子",
    "一块儿",
)

PUNCT_TRANSLATION = str.maketrans({
    ",": "，",
    ";": "；",
    ":": "：",
    "!": "！",
    "?": "？",
})
PUNCTUATION = "，、；：！？。"
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def punctuation_loss(source: str, output: str) -> int:
    source = source.translate(PUNCT_TRANSLATION)
    output = output.translate(PUNCT_TRANSLATION)
    return sum(max(0, source.count(mark) - output.count(mark)) for mark in PUNCTUATION)


def added_colloquialisms(source: str, output: str) -> list[str]:
    return [word for word in STRONG_COLLOQUIAL_WORDS if word not in source and word in output]


def merge_finding(
    findings: dict[int, dict[str, object]],
    index: int,
    priority: str,
    issue_types: list[str],
    note: str,
) -> None:
    finding = findings.setdefault(
        index,
        {"priority": priority, "issue_types": [], "review_notes": []},
    )
    if PRIORITY_ORDER[priority] < PRIORITY_ORDER[str(finding["priority"])]:
        finding["priority"] = priority
    for issue_type in issue_types:
        if issue_type not in finding["issue_types"]:
            finding["issue_types"].append(issue_type)
    if note not in finding["review_notes"]:
        finding["review_notes"].append(note)


def main() -> None:
    source_records = json.loads(SOURCE.read_text(encoding="utf-8"))
    findings: dict[int, dict[str, object]] = {}

    for index, (priority, issue_types, note) in CONTENT_FINDINGS.items():
        merge_finding(findings, index, priority, issue_types, note)

    for index in SEVERE_PUNCTUATION:
        record = source_records[index]
        loss = punctuation_loss(record["input"], record["output"])
        merge_finding(
            findings,
            index,
            "P2",
            ["严重删除标点"],
            f"归一化后净删约 {loss} 个标点，句法边界、并列关系或叙述节奏受损；手改时不要机械照抄原标点，但应恢复必要停顿。",
        )

    for index in REGISTER_REVIEW:
        record = source_records[index]
        words = added_colloquialisms(record["input"], record["output"])
        detail = "、".join(words) if words else "偏市井化措辞"
        merge_finding(
            findings,
            index,
            "P3",
            ["口吻同质化风险"],
            f"新增或强化了“{detail}”等口语表达；请结合人物身份和叙述语体判断，避免所有角色、旁白都变成同一种北方市井口吻。",
        )

    ordered_indices = sorted(
        findings,
        key=lambda index: (
            PRIORITY_ORDER[str(findings[index]["priority"])],
            index,
        ),
    )
    review_records = [
        {
            "system": source_records[index]["system"],
            "instruction": source_records[index]["instruction"],
            "input": source_records[index]["input"],
            "output": source_records[index]["output"],
        }
        for index in ordered_indices
    ]
    DESTINATION.write_text(
        json.dumps(review_records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    counts = {priority: 0 for priority in PRIORITY_ORDER}
    for finding in findings.values():
        counts[str(finding["priority"])] += 1
    print(json.dumps({"output": str(DESTINATION), "total": len(review_records), "priorities": counts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
