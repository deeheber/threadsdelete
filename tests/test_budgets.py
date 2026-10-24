"""Offline measurements behind the tuned ASSUMPTION defaults (see CLAUDE.md tuning protocol)."""

import logging
import unittest

import httpx

from tests.fakes import FakeThreadsApi, make_client
from threadsdelete import config
from threadsdelete.api import ReadFailedError

# SPEC section 5 workflow assumption (jobs.cleanup.timeout-minutes) until P4-03 reads the YAML.
JOB_TIMEOUT_MINUTES_ASSUMED = 15


def measure_read_chain(
    timeout_seconds: float, max_read_retries: int, max_retry_wait_seconds: float
) -> dict[str, float]:
    """Worst case of one read chain: every attempt times out, every wait is taken."""
    fake = FakeThreadsApi()
    fake.add("GET", "me", httpx.ReadTimeout("slow"), repeat=True)
    client = make_client(
        fake,
        timeout_seconds=timeout_seconds,
        max_read_retries=max_read_retries,
        max_retry_wait_seconds=max_retry_wait_seconds,
    )
    logger = logging.getLogger("threadsdelete.api")
    previous = logger.level
    logger.setLevel(logging.CRITICAL)
    try:
        client.get_identity()
    except ReadFailedError:
        pass
    finally:
        logger.setLevel(previous)
    attempts = float(len(fake.requests))
    total_sleep = float(sum(fake.sleeps))
    return {
        "attempts": attempts,
        "total_sleep": total_sleep,
        "max_single_sleep": max(fake.sleeps, default=0.0),
        "worst_case_seconds": attempts * timeout_seconds + total_sleep,
    }


def report() -> None:
    rows = [
        (
            "default",
            config.DEFAULT_HTTP_TIMEOUT_SECONDS,
            config.DEFAULT_MAX_READ_RETRIES,
            config.DEFAULT_MAX_RETRY_WAIT_SECONDS,
        ),
        (
            "fewer retries",
            config.DEFAULT_HTTP_TIMEOUT_SECONDS,
            2,
            config.DEFAULT_MAX_RETRY_WAIT_SECONDS,
        ),
        (
            "more retries",
            config.DEFAULT_HTTP_TIMEOUT_SECONDS,
            5,
            config.DEFAULT_MAX_RETRY_WAIT_SECONDS,
        ),
        (
            "short timeout",
            15.0,
            config.DEFAULT_MAX_READ_RETRIES,
            config.DEFAULT_MAX_RETRY_WAIT_SECONDS,
        ),
        (
            "long timeout",
            60.0,
            config.DEFAULT_MAX_READ_RETRIES,
            config.DEFAULT_MAX_RETRY_WAIT_SECONDS,
        ),
    ]
    print(
        f"Job timeout assumed: {JOB_TIMEOUT_MINUTES_ASSUMED} min "
        f"({JOB_TIMEOUT_MINUTES_ASSUMED * 60} s)"
    )
    print("variant        timeout retries maxwait attempts total_sleep worst_case_s")
    for name, timeout, retries, wait in rows:
        m = measure_read_chain(timeout, retries, wait)
        print(
            f"{name:<14} {timeout:>7.0f} {retries:>7} {wait:>7.0f} {m['attempts']:>8.0f} "
            f"{m['total_sleep']:>11.0f} {m['worst_case_seconds']:>13.0f}"
        )


class ReadChainBudgetTests(unittest.TestCase):
    def test_read_chain_attempts_and_waits_are_bounded(self) -> None:
        result = measure_read_chain(
            config.DEFAULT_HTTP_TIMEOUT_SECONDS,
            config.DEFAULT_MAX_READ_RETRIES,
            config.DEFAULT_MAX_RETRY_WAIT_SECONDS,
        )
        self.assertEqual(result["attempts"], config.DEFAULT_MAX_READ_RETRIES + 1)
        self.assertLessEqual(result["max_single_sleep"], config.DEFAULT_MAX_RETRY_WAIT_SECONDS)

    def test_default_read_chain_fits_job_timeout(self) -> None:
        result = measure_read_chain(
            config.DEFAULT_HTTP_TIMEOUT_SECONDS,
            config.DEFAULT_MAX_READ_RETRIES,
            config.DEFAULT_MAX_RETRY_WAIT_SECONDS,
        )
        self.assertLess(result["worst_case_seconds"], JOB_TIMEOUT_MINUTES_ASSUMED * 60)


if __name__ == "__main__":
    unittest.main()
