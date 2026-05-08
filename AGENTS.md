# AGENTS.md — execd

## Overview

execd is an HTTP REST API execution daemon with a Python client library. It provides a server that exposes REST endpoints for managing and executing tasks, and a client library for programmatic interaction with the server.

## Commands

| Command | Description |
|---------|-------------|
| `pytest` | Run test suite |
| `ruff format` | Format code |
| `prospector --with-tool ruff --with-tool mypy src/` | Lint + type check (with blending) |
| `semgrep --config=auto src/` | Security and pattern scanning |

## Development

```bash
# Setup
pip install -e ".[test]"

# Test
pytest

# Format
ruff format src/ tests/

# Lint + type check (prospector runs ruff check + mypy together)
prospector --with-tool ruff --with-tool mypy src/
semgrep --config=auto --severity=ERROR src/
```

## Testing

Tests are written using pytest with coverage requirements of >=80%. The test suite covers:
- Server functionality (task submission, retrieval, deletion)
- Client functionality (submit, get, delete, wait)
- Task model creation and serialization
- Error handling and edge cases

Run tests with:
```bash
pytest -v
```

## Code Style

- Format: ruff format
- Lint + Type check: prospector (runs ruff check + mypy with blending)
- Docstrings: Google style

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/tasks` | POST | Submit a new task |
| `/tasks/{id}` | GET | Get task status and result |
| `/tasks/{id}` | DELETE | Cancel/remove a task |

## Release

```bash
# Bump version
bumpversion patch  # or minor/major
git tag v<version>
git push && git push --tags
```
