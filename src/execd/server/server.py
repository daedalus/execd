"""HTTP REST API server for execd."""

from __future__ import annotations

import http.server
import json
import threading
import time
from typing import Any  # noqa: F401

from execd.core import Task, TaskStatus


class TaskNotFound(Exception):
    """Raised when a task is not found."""

    pass


class ExecHTTPServer(http.server.HTTPServer):
    """HTTP server with exec_server reference."""

    exec_server: ExecServer | None = None


class ExecHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for execd server."""

    exec_server: ExecServer | None = None  # noqa: UP045

    def _set_headers(
        self, status_code: int = 200, content_type: str = "application/json"
    ) -> None:
        """Set response headers."""
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.end_headers()

    def _read_json_body(self) -> dict[str, Any]:
        """Read and parse JSON request body.

        Returns:
            Parsed JSON dictionary

        Raises:
            ValueError: If JSON is invalid
        """
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length).decode("utf-8")
        return json.loads(body)  # type: ignore[no-any-return]

    def _send_json_response(self, data: dict[str, Any], status_code: int = 200) -> None:
        """Send JSON response."""
        self._set_headers(status_code)
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def do_POST(self) -> None:
        """Handle POST requests."""
        parsed_path = self.path

        if parsed_path == "/tasks":
            self._handle_submit_task()
        else:
            self._send_json_response({"error": "Not found"}, 404)

    def do_GET(self) -> None:
        """Handle GET requests."""
        prefix = "/tasks/"
        if self.path.startswith(prefix):
            task_id = self.path[len(prefix) :]
            self._handle_get_task(task_id)
        else:
            self._send_json_response({"error": "Not found"}, 404)

    def do_DELETE(self) -> None:
        """Handle DELETE requests."""
        prefix = "/tasks/"
        if self.path.startswith(prefix):
            task_id = self.path[len(prefix) :]
            self._handle_delete_task(task_id)
        else:
            self._send_json_response({"error": "Not found"}, 404)

    def _handle_submit_task(self) -> None:
        """Handle POST /tasks - submit a new task."""
        try:
            body: dict[str, Any] = self._read_json_body()
        except (json.JSONDecodeError, ValueError):
            self._send_json_response({"error": "Invalid JSON"}, 400)
            return

        code = body.get("code", "")
        if not code:
            self._send_json_response({"error": "Code cannot be empty"}, 400)
            return

        if self.server.exec_server is None:
            self._send_json_response({"error": "Server not initialized"}, 500)
            return

        task_id = self.server.exec_server.submit_task(code)
        self._send_json_response(
            {"task_id": task_id, "status": TaskStatus.PENDING}, 201
        )

    def _handle_get_task(self, task_id: str) -> None:
        """Handle GET /tasks/{task_id} - get task status."""
        if self.server.exec_server is None:
            self._send_json_response({"error": "Server not initialized"}, 500)
            return

        task = self.server.exec_server.get_task(task_id)
        if task is None:
            self._send_json_response({"error": "Task not found"}, 404)
            return

        self._send_json_response(task.to_dict(), 200)

    def _handle_delete_task(self, task_id: str) -> None:
        """Handle DELETE /tasks/{task_id} - cancel/remove task."""
        if self.server.exec_server is None:
            self._send_json_response({"error": "Server not initialized"}, 500)
            return

        removed = self.server.exec_server.delete_task(task_id)
        if not removed:
            self._send_json_response({"error": "Task not found"}, 404)
            return

        self._set_headers(204)
        self.wfile.write(b"")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: ANN401
        """Suppress default logging."""
        pass


class ExecServer:
    """HTTP REST API server for task execution."""

    def __init__(self, host: str = "localhost", port: int = 8080) -> None:
        """Initialize server.

        Args:
            host: Server host address
            port: Server port number
        """
        self.host = host
        self.port = port
        self.tasks: dict[str, Task] = {}  # noqa: A003
        self._server: ExecHTTPServer | None = None  # noqa: UP045
        self._thread: threading.Thread | None = None  # noqa: UP045

    def start(self) -> None:
        """Start the HTTP server in a separate thread."""
        self._server = ExecHTTPServer((self.host, self.port), ExecHTTPRequestHandler)
        self._server.exec_server = self  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the HTTP server."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        self.tasks.clear()

    def submit_task(self, code: str) -> str:
        """Submit a task for execution.

        Args:
            code: The code to execute

        Returns:
            task_id of the submitted task
        """
        task = Task(code)
        self.tasks[task.task_id] = task
        # Execute task in a separate thread
        thread = threading.Thread(target=self._execute_task, args=(task,), daemon=True)
        thread.start()
        return task.task_id

    def get_task(self, task_id: str) -> Task | None:
        """Get task by ID.

        Args:
            task_id: The task ID

        Returns:
            Task if found, None otherwise
        """
        return self.tasks.get(task_id)

    def delete_task(self, task_id: str) -> bool:
        """Delete a task.

        Args:
            task_id: The task ID

        Returns:
            True if task was deleted, False if not found
        """
        if task_id in self.tasks:
            del self.tasks[task_id]
            return True
        return False

    def _execute_task(self, task: Task) -> None:
        """Execute a task.

        Args:
            task: The task to execute
        """
        task.status = TaskStatus.RUNNING
        try:
            # For now, just store the code as result (placeholder for actual execution)
            task.result = f"Executed: {task.code}"
            task.status = TaskStatus.COMPLETED
        except Exception as e:
            task.error = str(e)
            task.status = TaskStatus.FAILED
        finally:
            task.completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
