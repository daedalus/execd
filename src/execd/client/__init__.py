"""Client module for execd."""

from __future__ import annotations

import argparse
import asyncio
import json
import shlex
import sys
from typing import Any

from .client import AsyncExecClient, ExecClient, ServerError, TaskNotFound

__all__ = ["AsyncExecClient", "ExecClient", "ServerError", "TaskNotFound"]


async def _one_shot(client: AsyncExecClient, command: str) -> dict[str, Any]:
    """Submit a command, wait for it to finish, and return the task dict.

    Args:
        client: Async client instance.
        command: Shell command string to execute.

    Returns:
        Completed task dictionary.
    """
    task_id = await client.submit_task(command)
    return await client.wait_for_task(task_id)


def _cmd_submit(args: argparse.Namespace) -> int:
    """Handle the 'submit' sub-command.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Exit code.
    """
    client = ExecClient(host=args.host, port=args.port)
    try:
        task_id = client.submit_task(args.code)
        print(json.dumps({"task_id": task_id, "status": "pending"}, indent=2))
    except ServerError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


def _cmd_get(args: argparse.Namespace) -> int:
    """Handle the 'get' sub-command.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Exit code.
    """
    client = ExecClient(host=args.host, port=args.port)
    try:
        task = client.get_task(args.task_id)
        print(json.dumps(task, indent=2))
    except TaskNotFound:
        print(f"Task not found: {args.task_id}", file=sys.stderr)
        return 1
    except ServerError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


def _cmd_delete(args: argparse.Namespace) -> int:
    """Handle the 'delete' sub-command.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Exit code.
    """
    client = ExecClient(host=args.host, port=args.port)
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


def _cmd_run(args: argparse.Namespace) -> int:
    """Handle the 'run' one-shot sub-command.

    Submits a command to the server, waits for it to complete, and writes
    stdout/stderr transparently, exiting with the command's exit code.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Exit code from the executed command.
    """
    full_command = shlex.join([args.cmd] + args.args)
    async_client = AsyncExecClient(host=args.host, port=args.port)
    try:
        task = asyncio.run(_one_shot(async_client, full_command))
    except TaskNotFound:
        print("Task not found", file=sys.stderr)
        return 1
    except ServerError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if task.get("stdout"):
        sys.stdout.write(task["stdout"])
        sys.stdout.flush()
    if task.get("stderr"):
        sys.stderr.write(task["stderr"])
        sys.stderr.flush()
    exit_code = task.get("exit_code")
    return int(exit_code) if exit_code is not None else 0


def main() -> int:
    """Main entry point for execd client CLI.

    Returns:
        Exit code (0 for success)
    """

    parser = argparse.ArgumentParser(description="execd client CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # submit command
    submit_parser = subparsers.add_parser("submit", help="Submit a task")
    submit_parser.add_argument("code", help="Shell command to execute")
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

    # run command (one-shot mode)
    run_parser = subparsers.add_parser(
        "run",
        help="Run a command on the server and stream its output (one-shot mode)",
    )
    run_parser.add_argument("cmd", help="Command to run")
    run_parser.add_argument("args", nargs="*", help="Command arguments")
    run_parser.add_argument("--host", default="localhost", help="Server host")
    run_parser.add_argument("--port", type=int, default=8080, help="Server port")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    handlers = {
        "submit": _cmd_submit,
        "get": _cmd_get,
        "delete": _cmd_delete,
        "run": _cmd_run,
    }
    return handlers[args.command](args)
