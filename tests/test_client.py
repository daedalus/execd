"""Tests for execd client module."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from execd.client import AsyncExecClient, ExecClient, ServerError, TaskNotFound
from execd.core import TaskStatus


def test_client_init():
    """Test ExecClient initialization."""
    client = ExecClient(host="127.0.0.1", port=9000)
    assert "127.0.0.1:9000" in client.base_url


def test_async_client_init():
    """Test AsyncExecClient initialization."""
    client = AsyncExecClient(host="127.0.0.1", port=9000)
    assert "127.0.0.1:9000" in client.base_url


def test_client_submit_task(server, client):
    """Test submitting a task via client."""
    task_id = client.submit_task("echo hello")
    assert isinstance(task_id, str)
    assert len(task_id) > 0


def test_client_get_task(server, client):
    """Test getting a task via client."""
    task_id = client.submit_task("true")
    time.sleep(0.5)

    task = client.get_task(task_id)
    assert task["task_id"] == task_id
    assert task["status"] in (TaskStatus.COMPLETED, TaskStatus.RUNNING)


def test_client_get_nonexistent_task(server, client):
    """Test getting non-existent task raises TaskNotFound."""
    with pytest.raises(TaskNotFound):
        client.get_task("nonexistent-id")


def test_client_delete_task(server, client):
    """Test deleting a task via client."""
    task_id = client.submit_task("true")
    result = client.delete_task(task_id)
    assert result is True


def test_client_delete_nonexistent_task(server, client):
    """Test deleting non-existent task returns False."""
    result = client.delete_task("nonexistent-id")
    assert result is False


def test_client_wait_for_task(server, client):
    """Test waiting for task completion."""
    task_id = client.submit_task("true")
    task = client.wait_for_task(task_id)
    assert task["status"] in (TaskStatus.COMPLETED, TaskStatus.FAILED)


def test_client_wait_for_nonexistent_task(server, client):
    """Test waiting for non-existent task raises TaskNotFound."""
    with pytest.raises(TaskNotFound):
        client.wait_for_task("nonexistent-id")


def test_client_wait_for_task_timeout(server, client):
    """Test wait_for_task with timeout."""
    task_id = client.submit_task("sleep 10")
    start = time.monotonic()
    try:
        client.wait_for_task(task_id, timeout=0.5)
    except TimeoutError:
        elapsed = time.monotonic() - start
        assert elapsed < 2.0  # Should timeout quickly
    # Clean up
    client.delete_task(task_id)


def test_exec_client_repr(server, client):
    """Test ExecClient string representation."""
    result = repr(client)
    assert "ExecClient" in result
    assert "localhost" in result


def test_async_client_repr():
    """Test AsyncExecClient string representation."""
    client = AsyncExecClient(host="localhost", port=8080)
    result = repr(client)
    assert "AsyncExecClient" in result
    assert "localhost" in result


def test_client_task_has_stdout_stderr(server, client):
    """Test that completed task contains stdout and stderr fields."""
    task_id = client.submit_task("echo hello")
    task = client.wait_for_task(task_id)
    assert task["status"] == TaskStatus.COMPLETED
    assert "hello" in task["stdout"]
    assert task["exit_code"] == 0


def test_client_task_stderr_captured(server, client):
    """Test that stderr output is captured in the task."""
    task_id = client.submit_task("echo error_msg >&2")
    task = client.wait_for_task(task_id)
    assert "error_msg" in task["stderr"]


def test_client_server_error_submit():
    """Test submit_task raises ServerError on 5xx."""
    import asyncio

    client = AsyncExecClient(host="localhost", port=19999)

    async def _test() -> None:
        with patch.object(client, "_request", new=AsyncMock(return_value=(500, None))):
            with pytest.raises(ServerError):
                await client.submit_task("true")

    asyncio.run(_test())


def test_client_server_error_get():
    """Test get_task raises ServerError on 5xx."""
    import asyncio

    client = AsyncExecClient(host="localhost", port=19999)

    async def _test() -> None:
        with patch.object(client, "_request", new=AsyncMock(return_value=(500, None))):
            with pytest.raises(ServerError):
                await client.get_task("task-id")

    asyncio.run(_test())
