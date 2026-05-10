"""execd - HTTP REST API execution daemon with Python client library."""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = [
    "__version__",
    "AsyncExecClient",
    "ExecClient",
    "ExecServer",
    "ServerError",
    "Task",
    "TaskNotFound",
    "TaskStatus",
]

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import AsyncExecClient, ExecClient, ServerError, TaskNotFound
    from .core import Task, TaskStatus
    from .server import ExecServer
else:
    from .client import AsyncExecClient, ExecClient, ServerError, TaskNotFound
    from .core import Task, TaskStatus
    from .server import ExecServer
