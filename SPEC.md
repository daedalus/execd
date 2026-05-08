# SPEC.md — execd

## Purpose
execd is an HTTP REST API execution daemon with a Python client library. It provides a server that exposes REST endpoints for managing and executing tasks, and a client library for programmatic interaction with the server.

## Scope
- **In scope:**
  - HTTP REST API server (server.py) with endpoints for task execution and status queries
  - Python client library (client.py) for interacting with the server
  - Task submission, status checking, and result retrieval
  - JSON-based request/response format
  - In-memory task storage with unique task IDs
  - Basic error handling and HTTP status codes

- **Out of scope:**
  - Authentication/authorization
  - Persistent task storage (database)
  - WebSocket or streaming responses
  - HTTPS/TLS support
  - Task queueing or prioritization
  - Distributed server setup

## Public API / Interface

### Server (server.py)

#### `ExecServer` Class
HTTP REST API server for task execution.

- **Attributes:**
  - `host: str`: Server host address
  - `port: int`: Server port number
  - `tasks: dict`: In-memory task storage (task_id -> task_info)

- **Methods:**
  - `__init__(host: str = "localhost", port: int = 8080) -> None`: Initialize server
  - `start() -> None`: Start the HTTP server
  - `stop() -> None`: Stop the server
  - `submit_task(code: str) -> str`: Submit a task for execution, returns task_id
  - `get_task(task_id: str) -> dict | None`: Get task status/result, returns task dict or None
  - `handle_request(handler: BaseHTTPRequestHandler) -> None`: Handle incoming HTTP requests

- **REST Endpoints:**
  - `POST /tasks` - Submit a new task
    - Request body: `{"code": "python code or command"}`
    - Response: `{"task_id": "...", "status": "pending"}` (201 Created)
  - `GET /tasks/{task_id}` - Get task status and result
    - Response: `{"task_id": "...", "status": "running|completed|failed", "result": "...", "error": "..."}` (200 OK)
    - 404 if task not found
  - `DELETE /tasks/{task_id}` - Cancel/remove a task
    - Response: 204 No Content
    - 404 if task not found

### Client (client.py)

#### `ExecClient` Class
Client for interacting with the execd server.

- **Methods:**
  - `__init__(host: str = "localhost", port: int = 8080) -> None`: Initialize client
  - `submit_task(code: str) -> str`: Submit task, returns task_id
  - `get_task(task_id: str) -> dict`: Get task status, raises TaskNotFound if not found
  - `delete_task(task_id: str) -> bool`: Delete task, returns True if successful
  - `wait_for_task(task_id: str, timeout: float | None = None) -> dict`: Wait for task completion

- **Exceptions:**
  - `TaskNotFound`: Raised when task_id does not exist on server
  - `ServerError`: Raised when server returns 5xx error

## Data Formats
- **Request format:** JSON with `Content-Type: application/json`
- **Response format:** JSON with `Content-Type: application/json`
- **Task status values:** `"pending"`, `"running"`, `"completed"`, `"failed"`
- **Task dict structure:**
  ```json
  {
    "task_id": "uuid-string",
    "status": "pending|running|completed|failed",
    "code": "original code string",
    "result": "execution result (if completed)",
    "error": "error message (if failed)",
    "created_at": "ISO timestamp",
    "completed_at": "ISO timestamp (if finished)"
  }
  ```

## Edge Cases
1. **Submit empty code:** Server returns 400 Bad Request with `{"error": "Code cannot be empty"}`
2. **Get non-existent task:** Server returns 404 with `{"error": "Task not found"}`
3. **Delete non-existent task:** Server returns 404 with `{"error": "Task not found"}`
4. **Invalid JSON in request:** Server returns 400 with `{"error": "Invalid JSON"}`
5. **Client connects to offline server:** Client raises `ConnectionError`
6. **Wait for task with timeout:** `wait_for_task()` raises `TimeoutError` if timeout exceeded
7. **Wait for non-existent task:** `wait_for_task()` raises `TaskNotFound`

## Performance & Constraints
- **Dependencies:** Core functionality uses only Python stdlib (`http.server`, `json`, `uuid`, `threading`, `urllib.request`)
- **Python version:** 3.11+ required
- **Task storage:** In-memory only (lost on server restart)
- **Concurrency:** Tasks execute in separate threads
- **Forbidden:** No third-party dependencies for core functionality (no flask, requests, etc.)
