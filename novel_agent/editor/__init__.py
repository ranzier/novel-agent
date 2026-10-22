"""一致性校验：写完一章后，拿正文比对设定与世界状态，揪出连贯性矛盾。"""

from .models import Issue, ReviewResult, Severity
from .checker import body_integrity_checks, review_chapter
from .style_polisher import PolishStats, StylePolisher, validate_rewrite

__all__ = [
    "Issue", "ReviewResult", "Severity", "body_integrity_checks",
    "review_chapter",
    "PolishStats", "StylePolisher", "validate_rewrite",
]
