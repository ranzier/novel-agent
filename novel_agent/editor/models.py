"""校验结果数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    """问题严重度。"""

    ERROR = "error"      # 硬伤：境界倒退、死人复活、未定义角色 —— 建议重写
    WARN = "warn"        # 疑似：时间线模糊、设定边缘冲突 —— 提醒人工看
    INFO = "info"        # 提示：文风/重复等小问题


@dataclass
class Issue:
    """单条一致性问题。"""

    severity: Severity
    category: str        # 分类：角色 / 境界 / 生死 / 设定 / 时间线 / 伏笔…
    message: str         # 问题描述
    evidence: str = ""   # 正文中的依据片段
    source: str = "rule" # 来源：rule（确定性规则）/ llm（语义校验）

    def to_dict(self) -> dict:
        return {
            "severity": self.severity.value,
            "category": self.category,
            "message": self.message,
            "evidence": self.evidence,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Issue":
        d = d or {}
        sev = d.get("severity", "warn")
        try:
            severity = Severity(sev)
        except ValueError:
            severity = Severity.WARN
        return cls(
            severity=severity,
            category=d.get("category", ""),
            message=d.get("message", ""),
            evidence=d.get("evidence", ""),
            source=d.get("source", "llm"),
        )


@dataclass
class ReviewResult:
    """一章的校验结果。"""

    chapter: int
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == Severity.WARN]

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def to_dict(self) -> dict:
        return {
            "chapter": self.chapter,
            "issues": [i.to_dict() for i in self.issues],
        }
