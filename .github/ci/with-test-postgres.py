"""Run a command under Writer's private mandatory CI PostgreSQL context.

The retained run-in-sif owned process group supervises the complete test tree.
"""

from __future__ import annotations

import subprocess
import sys

from writer_ci_postgres import private_postgres_environment


def main(arguments: list[str]) -> int:
    command = arguments[1:] if arguments[:1] == ["--"] else arguments
    if not command:
        raise SystemExit("usage: with-test-postgres.py -- COMMAND [ARGS...]")
    with private_postgres_environment() as environment:
        status = subprocess.run(command, env=environment, check=False).returncode
        return status if status >= 0 else 128 - status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
