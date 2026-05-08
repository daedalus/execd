"""CLI entry point for execd."""

import sys

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="execd CLI")
    subparsers = parser.add_subparsers(dest="component", help="Component to run")

    server_parser = subparsers.add_parser("server", help="Run execd server")
    server_parser.add_argument("--host", default="localhost", help="Host address")
    server_parser.add_argument("--port", type=int, default=8080, help="Port number")

    client_parser = subparsers.add_parser("client", help="Run execd client")
    client_subparsers = client_parser.add_subparsers(dest="command")

    submit_parser = client_subparsers.add_parser("submit", help="Submit a task")
    submit_parser.add_argument("code", help="Code to execute")

    args = parser.parse_args()

    if args.component == "server":
        from execd.server import main as server_main

        sys.exit(server_main())
    elif args.component == "client":
        from execd.client import main as client_main

        sys.exit(client_main())
    else:
        parser.print_help()
        sys.exit(1)
