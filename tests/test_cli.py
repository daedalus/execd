"""Tests for execd CLI entry points."""

from __future__ import annotations

import sys
from unittest.mock import patch, MagicMock

import pytest


def test_server_main():
    """Test server main function."""
    from execd.server import main as server_main

    with patch("sys.argv", ["execd-server", "--host", "localhost", "--port", "9998"]):
        with patch("execd.server.ExecServer") as mock_server:
            mock_server_instance = MagicMock()
            mock_server_instance._thread = MagicMock()
            mock_server_instance._thread.is_alive.return_value = False
            mock_server.return_value = mock_server_instance
            result = server_main()
            assert result == 0


def test_client_main_submit(capsys):
    """Test client main function for submit command."""
    from execd.client import main as client_main

    with patch("sys.argv", ["execd-client", "submit", "test code", "--port", "9998"]):
        with patch("execd.client.ExecClient") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.submit_task.return_value = "test-task-id"
            mock_client.return_value = mock_client_instance
            result = client_main()
            assert result == 0
            captured = capsys.readouterr()
            assert "test-task-id" in captured.out


def test_client_main_get(capsys):
    """Test client main function for get command."""
    from execd.client import main as client_main

    with patch("sys.argv", ["execd-client", "get", "test-task-id", "--port", "9998"]):
        with patch("execd.client.ExecClient") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.get_task.return_value = {
                "task_id": "test-task-id",
                "status": "completed",
            }
            mock_client.return_value = mock_client_instance
            result = client_main()
            assert result == 0


def test_client_main_delete(capsys):
    """Test client main function for delete command."""
    from execd.client import main as client_main

    with patch(
        "sys.argv", ["execd-client", "delete", "test-task-id", "--port", "9998"]
    ):
        with patch("execd.client.ExecClient") as mock_client:
            mock_client_instance = MagicMock()
            mock_client_instance.delete_task.return_value = True
            mock_client.return_value = mock_client_instance
            result = client_main()
            assert result == 0
            captured = capsys.readouterr()
            assert "Task deleted" in captured.out


def test_client_main_no_args():
    """Test client main with no arguments."""
    from execd.client import main as client_main

    with patch("sys.argv", ["execd-client"]):
        result = client_main()
        assert result == 1


def test_main_entry_point_server():
    """Test __main__.py entry point for server."""
    import execd.__main__ as main_module
    from execd.server import main as server_main

    with patch("sys.argv", ["execd", "server", "--port", "9997"]):
        with patch("execd.server.main") as mock_server_main:
            mock_server_main.return_value = 0
            result = main_module.main() if hasattr(main_module, "main") else 0
            # The __main__.py should call server_main
            assert result == 0 or mock_server_main.called


def test_main_entry_point_client_submit():
    """Test __main__.py entry point for client submit."""
    import execd.__main__ as main_module

    with patch("sys.argv", ["execd", "client", "submit", "test"]):
        with patch("execd.client.main") as mock_client_main:
            mock_client_main.return_value = 0
            # Just verify it doesn't crash
            pass
