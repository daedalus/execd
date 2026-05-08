"""Client module for execd."""

from __future__ import annotations

import argparse
import json
import sys

from .client import ExecClient, ServerError, TaskNotFound

__all__ = ["ExecClient", "ServerError", "TaskNotFound"]


def main() -> int:
    """Main entry point for execd client CLI.

    Returns:
        Exit code (0 for success)
    """

    parser = argparse.ArgumentParser(description="execd client CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # submit command
    submit_parser = subparsers.add_parser("submit", help="Submit a task")
    submit_parser.add_argument("code", help="Code to execute")
    submit_parser.add_argument("--host", default="localhost", help="Server host")
    submit_parser.add_argument("--port", type=int, default=8080, help="Server port")

    # get command
    get_parser = subparsers.add_parser("get", help="Get task status")
    get_parser.add_argument("task_id", help="Task ID")
    get_parser.add_argument("--host", default="localhost", help="Server host")
    get_parser.add_argument("--port", type=int, default=8080, help="Server port")

    # delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a task")
    delete_parser.add_argument("task_id", help="Task ID")
    delete_parser.add_argument("--host", default="localhost", help="Server host")
    delete_parser.add_argument("--port", type=int, default=8080, help="Server port")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    client = ExecClient(host=args.host, port=args.port)

    if args.command == "submit":
        try:
            task_id = client.submit_task(args.code)
            print(json.dumps({"task_id": task_id, "status": "pending"}, indent=2))
        except ServerError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    elif args.command == "get":
        try:
            task = client.get_task(args.task_id)
            print(json.dumps(task, indent=2))
        except TaskNotFound:
            print(f"Task not found: {args.task_id}", file=sys.stderr)
            return 1
        except ServerError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    elif args.command == "delete":
        try:
            removed = client.delete_task(args.task_id)
            if removed:
                print("Task deleted")
            else:
                print(f"Task not found: {args.task_id}", file=sys.stderr)
                return 1
        except ServerError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    return 0
