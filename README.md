**execd** — HTTP REST API execution daemon with Python client library.

[![PyPI](https://img.shields.io/pypi/v/execd.svg)](https://pypi.org/project/execd/)
[![Python](https://img.shields.io/pypi/pyversions/execd.svg)](https://pypi.org/project/execd/)
[![Coverage](https://codecov.io/gh/daedalus/execd/branch/master/graph/badge.svg)](https://codecov.io/gh/daedalus/execd)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/master/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/daedalus/execd)

## Install

```bash
pip install execd
```

## Usage

### Start the Server

```bash
execd-server --host localhost --port 8080
```

### Use the Client

```python
from execd import ExecClient

client = ExecClient(host="localhost", port=8080)

# Submit a task
task_id = client.submit_task("print('hello world')")

# Wait for completion
task = client.wait_for_task(task_id)
print(task["status"])  # "completed"
print(task["result"])  # "Executed: print('hello world')"

# Get task status
task = client.get_task(task_id)

# Delete task
client.delete_task(task_id)
```

### CLI Client

```bash
# Submit a task
execd-client submit "print('hello')"

# Get task status
execd-client get <task_id>

# Delete a task
execd-client delete <task_id>
```

## API

### REST Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/tasks` | POST | Submit a new task |
| `/tasks/{id}` | GET | Get task status and result |
| `/tasks/{id}` | DELETE | Cancel/remove a task |

### Python API

- `ExecServer(host, port)` - HTTP REST API server
- `ExecClient(host, port)` - Client for interacting with server
- `submit_task(code)` - Submit task, returns task_id
- `get_task(task_id)` - Get task status
- `delete_task(task_id)` - Delete task
- `wait_for_task(task_id, timeout)` - Wait for task completion

## Development

```bash
git clone https://github.com/daedalus/execd.git
cd execd
pip install -e ".[test]"

# run tests
pytest

# format
ruff format src/ tests/

# lint + type check (prospector runs ruff check + mypy together)
prospector --with-tool ruff --with-tool mypy src/
semgrep --config=auto --severity=ERROR src/
```
