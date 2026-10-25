"""Entry point: configuration from the environment, redacted logging, one UTC run start."""

import argparse
import logging
import os
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import TextIO

from threadsdelete import cleanup, config
from threadsdelete.api import (
    ApiError,
    AuthError,
    RedactingFilter,
    ThreadsClient,
    Transport,
    redact,
)
from threadsdelete.cleanup import IdentityMismatchError
from threadsdelete.config import ConfigError, load_config
from threadsdelete.core import ExitCode, SelectionError, TimestampError


def _env_help() -> str:
    defaults = [
        ("DRY_RUN", str(config.DEFAULT_DRY_RUN).lower()),
        ("DAYS_AGO", str(config.DEFAULT_DAYS_AGO)),
        ("THREADS_ACCESS_TOKEN", "required"),
        ("THREADS_USER_ID", "required"),
        ("MAX_DELETIONS_PER_RUN", str(config.DEFAULT_MAX_DELETIONS_PER_RUN)),
    ]
    assert [name for name, _ in defaults] == list(config.ENV_KEYS)
    lines = [f"  {name:<24} {value}" for name, value in defaults]
    return "Environment variables (name, default):\n" + "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="main.py",
        description=(
            "threadsdelete: remove your own old Threads content through the official "
            "Meta Threads API. Configuration is by environment variables, see README.md."
        ),
        epilog=_env_help(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def _configure_logging(token: str, err: TextIO) -> tuple[logging.Handler, int]:
    handler = logging.StreamHandler(err)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactingFilter([token]))
    root = logging.getLogger()
    previous = root.level
    root.addHandler(handler)
    root.setLevel(config.LOG_LEVEL)
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return handler, previous


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    transport: Transport | None = None,
    now: datetime | None = None,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    build_parser().parse_args(argv)
    env = os.environ if env is None else env
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    run_started_at = datetime.now(UTC) if now is None else now

    try:
        cfg = load_config(env)
    except ConfigError as exc:
        for problem in exc.problems:
            print(f"Configuration error: {problem}", file=err)
        return ExitCode.CONFIG

    secrets = (cfg.access_token,)
    handler, previous_level = _configure_logging(cfg.access_token, err)
    try:
        client = ThreadsClient(
            access_token=cfg.access_token,
            api_version=config.API_VERSION,
            timeout_seconds=config.HTTP_TIMEOUT_SECONDS,
            max_read_retries=config.MAX_READ_RETRIES,
            max_retry_wait_seconds=config.MAX_RETRY_WAIT_SECONDS,
            read_only=cfg.dry_run,
            transport=transport,
        )
        with client:
            try:
                summary = cleanup.run(cfg, client, run_started_at, out)
            except (AuthError, IdentityMismatchError) as exc:
                print(f"Authentication failure: {redact(str(exc), secrets)}", file=err)
                return ExitCode.AUTH
            except (ApiError, SelectionError, TimestampError) as exc:
                print(f"Error: {redact(str(exc), secrets)}", file=err)
                return ExitCode.FAILURE
        return cleanup.exit_status(summary)
    finally:
        logging.getLogger().removeHandler(handler)
        logging.getLogger().setLevel(previous_level)


if __name__ == "__main__":
    sys.exit(main())
