"""一致性校验：写完一章后，拿正文比对设定与世界状态，揪出连贯性矛盾。"""

from .models import Issue, ReviewResult, Severity
from .checker import review_chapter

__all__ = ["Issue", "ReviewResult", "Severity", "review_chapter"]
