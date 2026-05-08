"""Tests for execd server module."""

from __future__ import annotations

import threading
import time

import pytest

from execd.core import Task, TaskStatus
from execd.server import ExecServer, TaskNotFound


def test_server_init():
    """Test ExecServer initialization."""
    server = ExecServer(host="127.0.0.1", port=9000)
    assert server.host == "127.0.0.1"
    assert server.port == 9000
    assert len(server.tasks) == 0


def test_server_submit_task(server):
    """Test submitting a task to the server."""
    task_id = server.submit_task("print('hello')")
    assert task_id in server.tasks
    task = server.tasks[task_id]
    assert task.code == "print('hello')"

    # Wait for task to complete
    time.sleep(1)
    assert task.status == TaskStatus.COMPLETED


def test_server_get_task(server):
    """Test getting a task from the server."""
    task_id = server.submit_task("test code")
    time.sleep(1)

    task = server.get_task(task_id)
    assert task is not None
    assert task.task_id == task_id
    assert task.code == "test code"


def test_server_get_nonexistent_task(server):
    """Test getting a non-existent task returns None."""
    task = server.get_task("nonexistent-id")
    assert task is None


def test_server_delete_task(server):
    """Test deleting a task from the server."""
    task_id = server.submit_task("test code")
    assert task_id in server.tasks

    removed = server.delete_task(task_id)
    assert removed is True
    assert task_id not in server.tasks


def test_server_delete_nonexistent_task(server):
    """Test deleting a non-existent task returns False."""
    removed = server.delete_task("nonexistent-id")
    assert removed is False


def test_task_model():
    """Test Task model creation and serialization."""
    task = Task("test code")
    assert task.code == "test code"
    assert task.status == TaskStatus.PENDING
    assert task.result == ""
    assert task.error == ""

    task_dict = task.to_dict()
    assert "task_id" in task_dict
    assert task_dict["code"] == "test code"
    assert task_dict["status"] == TaskStatus.PENDING


def test_task_model_from_dict():
    """Test creating Task from dictionary."""
    data = {
        "task_id": "test-id",
        "status": TaskStatus.COMPLETED,
        "code": "test code",
        "result": "some result",
        "error": "",
        "created_at": "2026-05-07T12:00:00Z",
        "completed_at": "2026-05-07T12:00:01Z",
    }

    task = Task.from_dict(data)
    assert task.task_id == "test-id"
    assert task.status == TaskStatus.COMPLETED
    assert task.result == "some result"


def test_server_stop():
    """Test stopping the server."""
    server = ExecServer(host="localhost", port=9998)
    server.start()
    time.sleep(0.5)
    server.stop()
    assert server._server is None
    assert server._thread is None
    assert len(server.tasks) == 0


def test_server_submit_and_get():
    """Test submitting and then getting a task."""
    server = ExecServer(host="localhost", port=9997)
    server.start()
    time.sleep(0.5)

    task_id = server.submit_task("test code")
    task = server.get_task(task_id)
    assert task is not None
    assert task.code == "test code"

    server.stop()
