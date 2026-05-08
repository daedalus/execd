"""Server module for execd."""

from __future__ import annotations

import argparse
import time

from .server import ExecServer, TaskNotFound

__all__ = ["ExecServer", "TaskNotFound"]


def main() -> int:
    """Main entry point for execd server CLI.

    Returns:
        Exit code (0 for success)
    """

    parser = argparse.ArgumentParser(description="execd HTTP REST API server")
    parser.add_argument(
        "--host", default="localhost", help="Host address (default: localhost)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port number (default: 8080)"
    )

    args = parser.parse_args()

    server = ExecServer(host=args.host, port=args.port)
    print(f"Starting execd server on {args.host}:{args.port}...")

    try:
        server.start()
        # Keep main thread alive
        import threading

        while server._thread and server._thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.stop()

    return 0
