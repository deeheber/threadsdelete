"""Entry point for the Threads cleanup tool."""

import argparse
import sys
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="main.py",
        description=(
            "threadsdelete: remove your own old Threads content through the official "
            "Meta Threads API. Configuration is by environment variables, see README.md."
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    build_parser().parse_args(argv)
    print("cleanup is not implemented yet", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
