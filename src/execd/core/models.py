"""Core models for execd."""

from __future__ import annotations

import time
import uuid
from typing import Any


class TaskStatus:
    """Task status constants."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Task:
    """Represents a task in the execution daemon."""

    def __init__(self, code: str) -> None:
        """Initialize a task.

        Args:
            code: The command or code to execute
        """
        self.task_id: str = str(uuid.uuid4())
        self.code: str = code
        self.status: str = TaskStatus.PENDING
        self.result: str = ""
        self.error: str = ""
        self.stdout: str = ""
        self.stderr: str = ""
        self.exit_code: int | None = None
        self.created_at: str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.completed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert task to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the task
        """
        return {
            "task_id": self.task_id,
            "status": self.status,
            "code": self.code,
            "result": self.result,
            "error": self.error,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        """Create a Task from dictionary.

        Args:
            data: Dictionary containing task data.

        Returns:
            Task instance.
        """
        code = data.get("code", "")
        if code is None:
            code = ""
        task = cls(code)
        task.task_id = data.get("task_id") or str(uuid.uuid4())
        task.status = data.get("status") or TaskStatus.PENDING
        task.result = data.get("result") or ""
        task.error = data.get("error") or ""
        task.stdout = data.get("stdout") or ""
        task.stderr = data.get("stderr") or ""
        task.exit_code = data.get("exit_code")
        task.created_at = data.get("created_at") or ""
        task.completed_at = data.get("completed_at") or ""
        return task
