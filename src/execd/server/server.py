"""Async HTTP REST API server for execd."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any

from execd.core import Task, TaskStatus

_STATUS_TEXTS: dict[int, str] = {
    200: "OK",
    201: "Created",
    204: "No Content",
    400: "Bad Request",
    404: "Not Found",
    500: "Internal Server Error",
}

# Maximum allowed request body size (1 MiB).
_MAX_BODY_BYTES = 1_048_576


class TaskNotFound(Exception):
    """Raised when a task is not found."""

    pass


class ExecServer:
    """Async HTTP REST API server for task execution."""

    def __init__(self, host: str = "localhost", port: int = 8080) -> None:
        """Initialize server.

        Args:
            host: Server host address.
            port: Server port number.
        """
        self.host = host
        self.port = port
        self.tasks: dict[str, Task] = {}
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: asyncio.Server | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public synchronous API (thread-safe)
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the async HTTP server in a background thread."""
        ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run_loop, args=(ready,), daemon=True
        )
        self._thread.start()
        if not ready.wait(timeout=5.0):
            raise RuntimeError("Server failed to start within timeout")

    def stop(self) -> None:
        """Stop the HTTP server."""
        if self._loop is not None:
            if self._server is not None:
                self._loop.call_soon_threadsafe(self._server.close)
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        self._loop = None
        self._server = None
        with self._lock:
            self.tasks.clear()

    def submit_task(self, code: str) -> str:
        """Submit a task for execution.

        Args:
            code: The shell command to execute.

        Returns:
            task_id of the submitted task.
        """
        task = Task(code)
        with self._lock:
            self.tasks[task.task_id] = task
        loop = self._loop
        if loop is not None and loop.is_running():
            asyncio.run_coroutine_threadsafe(self._execute_task(task), loop)
        return task.task_id

    def get_task(self, task_id: str) -> Task | None:
        """Get task by ID.

        Args:
            task_id: The task ID.

        Returns:
            Task if found, None otherwise.
        """
        with self._lock:
            return self.tasks.get(task_id)

    def delete_task(self, task_id: str) -> bool:
        """Delete a task.

        Args:
            task_id: The task ID.

        Returns:
            True if task was deleted, False if not found.
        """
        with self._lock:
            if task_id in self.tasks:
                del self.tasks[task_id]
                return True
            return False

    # ------------------------------------------------------------------
    # Async internals
    # ------------------------------------------------------------------

    def _run_loop(self, ready: threading.Event) -> None:
        """Entry point for the background thread: runs the asyncio event loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._start_serving(ready))
            loop.run_forever()
        finally:
            loop.close()

    async def _start_serving(self, ready: threading.Event) -> None:
        """Create the asyncio server and signal the ready event."""
        self._server = await asyncio.start_server(
            self._handle_connection, self.host, self.port
        )
        ready.set()

    async def _execute_task(self, task: Task) -> None:
        """Execute a task's command asynchronously.

        Args:
            task: The task to execute.
        """
        task.status = TaskStatus.RUNNING
        try:
            # execd is an execution daemon: running arbitrary shell commands is
            # its explicit purpose.  Callers are responsible for ensuring only
            # trusted input is submitted to the API.
            proc = await asyncio.create_subprocess_shell(
                task.code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            raw_stdout, raw_stderr = await proc.communicate()
            task.stdout = raw_stdout.decode("utf-8", errors="replace")
            task.stderr = raw_stderr.decode("utf-8", errors="replace")
            task.exit_code = proc.returncode if proc.returncode is not None else -1
            task.result = task.stdout
            task.status = (
                TaskStatus.COMPLETED if proc.returncode == 0 else TaskStatus.FAILED
            )
        except Exception as exc:
            task.error = str(exc)
            task.status = TaskStatus.FAILED
        finally:
            task.completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a single TCP connection as an HTTP/1.1 request.

        Args:
            reader: Async stream reader.
            writer: Async stream writer.
        """
        try:
            await self._process_request(reader, writer)
        except Exception:
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _read_headers(
        self, reader: asyncio.StreamReader
    ) -> dict[str, str]:
        """Read HTTP request headers until the blank line.

        Args:
            reader: Async stream reader.

        Returns:
            Dict of lower-cased header names to values.
        """
        headers: dict[str, str] = {}
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=10.0)
            if line in (b"\r\n", b"\n", b""):
                break
            decoded = line.decode("utf-8", errors="replace").strip()
            if ":" in decoded:
                name, _, value = decoded.partition(":")
                headers[name.strip().lower()] = value.strip()
        return headers

    async def _process_request(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Parse one HTTP request and send the response.

        Args:
            reader: Async stream reader.
            writer: Async stream writer.
        """
        # Request line
        raw_line = await asyncio.wait_for(reader.readline(), timeout=10.0)
        if not raw_line:
            return
        parts = raw_line.decode("utf-8", errors="replace").strip().split()
        if len(parts) < 2:
            return
        method, path = parts[0], parts[1]

        headers = await self._read_headers(reader)

        # Body
        body = b""
        if "content-length" in headers:
            length = int(headers["content-length"])
            if length > _MAX_BODY_BYTES:
                await self._send_response(
                    writer, 400, {"error": "Request body too large"}
                )
                return
            if length > 0:
                body = await asyncio.wait_for(
                    reader.readexactly(length), timeout=30.0
                )

        response_data, status_code = await self._route(method, path, body)
        await self._send_response(writer, status_code, response_data)

    async def _route(
        self, method: str, path: str, body: bytes
    ) -> tuple[dict[str, Any] | None, int]:
        """Route an HTTP request to its handler.

        Args:
            method: HTTP method string.
            path: Request path.
            body: Raw request body bytes.

        Returns:
            Tuple of (response dict or None, HTTP status code).
        """
        if method == "POST" and path == "/tasks":
            return await self._handle_submit(body)
        if method == "GET" and path.startswith("/tasks/"):
            task_id = path[len("/tasks/"):]
            return self._handle_get(task_id)
        if method == "DELETE" and path.startswith("/tasks/"):
            task_id = path[len("/tasks/"):]
            return self._handle_delete(task_id)
        return {"error": "Not found"}, 404

    async def _handle_submit(self, body: bytes) -> tuple[dict[str, Any], int]:
        """Handle POST /tasks.

        Args:
            body: Raw request body bytes.

        Returns:
            Tuple of (response dict, HTTP status code).
        """
        try:
            data: dict[str, Any] = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, ValueError):
            return {"error": "Invalid JSON"}, 400

        code: str = data.get("code", "")
        if not code:
            return {"error": "Code cannot be empty"}, 400

        task = Task(code)
        with self._lock:
            self.tasks[task.task_id] = task
        asyncio.create_task(self._execute_task(task))
        return {"task_id": task.task_id, "status": TaskStatus.PENDING}, 201

    def _handle_get(self, task_id: str) -> tuple[dict[str, Any], int]:
        """Handle GET /tasks/{task_id}.

        Args:
            task_id: The task ID to retrieve.

        Returns:
            Tuple of (response dict, HTTP status code).
        """
        with self._lock:
            task = self.tasks.get(task_id)
        if task is None:
            return {"error": "Task not found"}, 404
        return task.to_dict(), 200

    def _handle_delete(self, task_id: str) -> tuple[dict[str, Any] | None, int]:
        """Handle DELETE /tasks/{task_id}.

        Args:
            task_id: The task ID to delete.

        Returns:
            Tuple of (response dict or None, HTTP status code).
        """
        with self._lock:
            if task_id not in self.tasks:
                return {"error": "Task not found"}, 404
            del self.tasks[task_id]
        return None, 204

    async def _send_response(
        self,
        writer: asyncio.StreamWriter,
        status_code: int,
        data: dict[str, Any] | None,
    ) -> None:
        """Serialise and write an HTTP response.

        Args:
            writer: Async stream writer.
            status_code: HTTP status code.
            data: Response payload dict, or None for empty body.
        """
        status_text = _STATUS_TEXTS.get(status_code, "Unknown")
        body = json.dumps(data).encode("utf-8") if data is not None else b""
        header = (
            f"HTTP/1.1 {status_code} {status_text}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        writer.write(header.encode("utf-8"))
        if body:
            writer.write(body)
        await writer.drain()
