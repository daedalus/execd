"""Client library for execd."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class TaskNotFound(Exception):
    """Raised when a task is not found on the server."""

    pass


class ServerError(Exception):
    """Raised when the server returns a 5xx error."""

    pass


class ExecClient:
    """Client for interacting with the execd server."""

    def __init__(self, host: str = "localhost", port: int = 8080) -> None:
        """Initialize client.

        Args:
            host: Server host address
            port: Server port number
        """
        self.base_url = f"http://{host}:{port}"

    def submit_task(self, code: str) -> str:
        """Submit a task for execution.

        Args:
            code: The code to execute.

        Returns:
            task_id of the submitted task.

        Raises:
            ServerError: If server returns 5xx error.
            ValueError: If response is invalid.
        """
        url = f"{self.base_url}/tasks"
        data = json.dumps({"code": code}).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 201:
                    result: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
                    return result["task_id"]  # type: ignore[no-any-return]  # json.loads returns Any
                raise ServerError(f"Unexpected status: {resp.status}")
        except urllib.error.HTTPError as e:
            if 500 <= e.code < 600:
                raise ServerError(f"Server error: {e.code}") from e
            raise

    def get_task(self, task_id: str) -> dict[str, str | int | bool | None]:
        """Get task status and result.

        Args:
            task_id: The task ID

        Returns:
            Task dictionary with status and result

        Raises:
            TaskNotFound: If task does not exist on server
            ServerError: If server returns 5xx error
        """
        url = f"{self.base_url}/tasks/{task_id}"

        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))  # type: ignore[no-any-return]  # json.loads returns Any
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise TaskNotFound(f"Task not found: {task_id}") from e
            if 500 <= e.code < 600:
                raise ServerError(f"Server error: {e.code}") from e
            raise

    def delete_task(self, task_id: str) -> bool:
        """Delete a task.

        Args:
            task_id: The task ID

        Returns:
            True if task was deleted, False if not found

        Raises:
            ServerError: If server returns 5xx error
        """
        url = f"{self.base_url}/tasks/{task_id}"
        req = urllib.request.Request(url, method="DELETE")

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 204  # type: ignore[no-any-return]  # urlopen returns Any
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            if 500 <= e.code < 600:
                raise ServerError(f"Server error: {e.code}") from e
            raise

    def wait_for_task(
        self, task_id: str, timeout: float | None = None
    ) -> dict[str, str | int | bool | None]:
        """Wait for a task to complete.

        Args:
            task_id: The task ID
            timeout: Maximum seconds to wait (None = wait indefinitely)

        Returns:
            Task dictionary once completed or failed

        Raises:
            TaskNotFound: If task does not exist
            TimeoutError: If timeout is exceeded
            ServerError: If server returns 5xx error
        """
        start = time.monotonic()

        while True:
            task = self.get_task(task_id)
            status = task.get("status", "")

            if status in ("completed", "failed"):
                return task

            if timeout is not None and time.monotonic() - start > timeout:
                raise TimeoutError(f"Timeout waiting for task {task_id}")

            time.sleep(0.5)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"ExecClient(host='{self.base_url}')"
