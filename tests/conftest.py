"""Test configuration and fixtures for execd."""

from __future__ import annotations

import time

import pytest
from execd.server import ExecServer


@pytest.fixture
def server():
    """Create and start a test server."""
    srv = ExecServer(host="localhost", port=9999)
    srv.start()
    time.sleep(0.5)  # Give server time to start
    yield srv
    srv.stop()


@pytest.fixture
def client(server):
    """Create a test client."""
    from execd.client import ExecClient

    return ExecClient(host="localhost", port=9999)
