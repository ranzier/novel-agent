"""本地 Web 服务：把 novel-agent 的能力包成 HTTP API + 静态前端。

单机自用，无鉴权。业务逻辑全部复用 novel_agent 现有模块，
server 层只做编排、序列化与长任务/进度推送。
"""

from .app import create_app

__all__ = ["create_app"]
