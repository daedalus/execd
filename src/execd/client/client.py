"""Client library for execd."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any


class TaskNotFound(Exception):
    """Raised when a task is not found on the server."""

    pass


class ServerError(Exception):
    """Raised when the server returns a 5xx error."""

    pass


class AsyncExecClient:
    """Async client for interacting with the execd server."""

    def __init__(self, host: str = "localhost", port: int = 8080) -> None:
        """Initialize async client.

        Args:
            host: Server host address
            port: Server port number
        """
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"

    async def _read_response(
        self, reader: asyncio.StreamReader
    ) -> tuple[int, dict[str, Any] | None]:
        """Read and parse an HTTP response from the server.

        Args:
            reader: Async stream reader positioned after the request.

        Returns:
            Tuple of (HTTP status code, parsed JSON body or None).
        """
        status_line = await reader.readline()
        parts = status_line.decode("utf-8", errors="replace").split()
        status_code = int(parts[1])

        content_length = 0
        while True:
            line = await reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break
            decoded = line.decode("utf-8", errors="replace").strip()
            if decoded.lower().startswith("content-length:"):
                content_length = int(decoded.split(":", 1)[1].strip())

        resp_body: dict[str, Any] | None = None
        if content_length > 0:
            raw = await reader.readexactly(content_length)
            resp_body = json.loads(raw.decode("utf-8"))

        return status_code, resp_body

    async def _request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any] | None]:
        """Open a connection, send one HTTP request, and return the response.

        Args:
            method: HTTP verb (GET, POST, DELETE).
            path: Request path (e.g. "/tasks").
            data: Optional JSON payload.

        Returns:
            Tuple of (HTTP status code, parsed JSON body or None).

        Raises:
            ServerError: If the server returns a 5xx status.
            ConnectionError: If the connection is refused or lost.
        """
        body = json.dumps(data).encode("utf-8") if data is not None else b""
        reader, writer = await asyncio.open_connection(self.host, self.port)
        try:
            header_lines = (
                f"{method} {path} HTTP/1.1\r\n"
                f"Host: {self.host}:{self.port}\r\n"
                f"Connection: close\r\n"
            )
            if body:
                header_lines += (
                    f"Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                )
            header_lines += "\r\n"
            writer.write(header_lines.encode("utf-8"))
            if body:
                writer.write(body)
            await writer.drain()

            return await self._read_response(reader)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def submit_task(self, code: str) -> str:
        """Submit a task for execution.

        Args:
            code: The shell command to execute.

        Returns:
            task_id of the submitted task.

        Raises:
            ServerError: If the server returns a 5xx error.
        """
        status, data = await self._request("POST", "/tasks", {"code": code})
        if 500 <= status < 600:
            raise ServerError(f"Server error: {status}")
        if status == 201 and data:
            return str(data["task_id"])
        raise ServerError(f"Unexpected status: {status}")

    async def get_task(self, task_id: str) -> dict[str, Any]:
        """Get task status and result.

        Args:
            task_id: The task ID.

        Returns:
            Task dictionary with status and result.

        Raises:
            TaskNotFound: If the task does not exist on the server.
            ServerError: If the server returns a 5xx error.
        """
        status, data = await self._request("GET", f"/tasks/{task_id}")
        if status == 404:
            raise TaskNotFound(f"Task not found: {task_id}")
        if 500 <= status < 600:
            raise ServerError(f"Server error: {status}")
        return data or {}

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task.

        Args:
            task_id: The task ID.

        Returns:
            True if task was deleted, False if not found.

        Raises:
            ServerError: If the server returns a 5xx error.
        """
        status, _ = await self._request("DELETE", f"/tasks/{task_id}")
        if status == 404:
            return False
        if 500 <= status < 600:
            raise ServerError(f"Server error: {status}")
        return status == 204

    async def wait_for_task(
        self,
        task_id: str,
        timeout: float | None = None,
        poll_interval: float = 0.5,
    ) -> dict[str, Any]:
        """Wait for a task to reach a terminal state.

        Args:
            task_id: The task ID.
            timeout: Maximum seconds to wait (None = wait indefinitely).
            poll_interval: Seconds between status polls.

        Returns:
            Task dictionary once completed or failed.

        Raises:
            TaskNotFound: If the task does not exist.
            TimeoutError: If the timeout is exceeded.
            ServerError: If the server returns a 5xx error.
        """
        start = time.monotonic()
        while True:
            task = await self.get_task(task_id)
            if task.get("status") in ("completed", "failed"):
                return task
            if timeout is not None and time.monotonic() - start > timeout:
                raise TimeoutError(f"Timeout waiting for task {task_id}")
            await asyncio.sleep(poll_interval)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"AsyncExecClient(host='{self.base_url}')"


class ExecClient:
    """Synchronous client for interacting with the execd server.

    Wraps :class:`AsyncExecClient` and runs each operation in a fresh
    ``asyncio`` event loop, making it safe to call from any synchronous
    context.
    """

    def __init__(self, host: str = "localhost", port: int = 8080) -> None:
        """Initialize client.

        Args:
            host: Server host address
            port: Server port number
        """
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self._async = AsyncExecClient(host, port)

    def submit_task(self, code: str) -> str:
        """Submit a task for execution.

        Args:
            code: The shell command to execute.

        Returns:
            task_id of the submitted task.

        Raises:
            ServerError: If server returns 5xx error.
        """
        return asyncio.run(self._async.submit_task(code))

    def get_task(self, task_id: str) -> dict[str, Any]:
        """Get task status and result.

        Args:
            task_id: The task ID

        Returns:
            Task dictionary with status and result

        Raises:
            TaskNotFound: If task does not exist on server
            ServerError: If server returns 5xx error
        """
        return asyncio.run(self._async.get_task(task_id))

    def delete_task(self, task_id: str) -> bool:
        """Delete a task.

        Args:
            task_id: The task ID

        Returns:
            True if task was deleted, False if not found

        Raises:
            ServerError: If server returns 5xx error
        """
        return asyncio.run(self._async.delete_task(task_id))

    def wait_for_task(
        self, task_id: str, timeout: float | None = None
    ) -> dict[str, Any]:
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
        return asyncio.run(self._async.wait_for_task(task_id, timeout))

    def __repr__(self) -> str:
        """Return string representation."""
        return f"ExecClient(host='{self.base_url}')"
