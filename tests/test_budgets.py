"""Offline measurements behind the tuned ASSUMPTION defaults (see CLAUDE.md tuning protocol)."""

import logging
import unittest
from datetime import UTC, datetime, timedelta

import httpx

from tests.fakes import FakeThreadsApi, make_client
from threadsdelete import config
from threadsdelete.api import ReadFailedError
from threadsdelete.cleanup import split_by_budget
from threadsdelete.core import Candidate, Category, Operation

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


# docs/RESEARCH.md, Contracts > Quota inspection and Removal: 100 deletes per rolling 24 hours.
DOCUMENTED_DELETE_QUOTA = 100
MAX_SIMULATED_RUNS = 1000


def simulate_weekly_drain(backlog: int, cap: int, quota_per_window: int | None) -> int:
    """Weekly runs needed to drain a backlog; -1 if no progress is possible.

    The quota window (24 h) is shorter than the weekly schedule, so it refreshes every run.
    """
    base = datetime(2020, 1, 1, tzinfo=UTC)
    pending = [
        Candidate(Category.POST, str(i), base + timedelta(minutes=i), None) for i in range(backlog)
    ]
    runs = 0
    while pending:
        if runs >= MAX_SIMULATED_RUNS:
            return -1
        allowed, deferred = split_by_budget(pending, cap, {Operation.DELETE: quota_per_window})
        if not allowed:
            return -1
        pending = deferred
        runs += 1
    return runs


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
    print()
    print(f"Weekly drain (documented delete quota: {DOCUMENTED_DELETE_QUOTA} per 24 h)")
    print("backlog  cap  quota  runs_to_drain")
    cap = config.DEFAULT_MAX_DELETIONS_PER_RUN
    settings: list[tuple[int, int | None]] = [
        (cap, DOCUMENTED_DELETE_QUOTA),
        (cap, None),
        (cap // 2, DOCUMENTED_DELETE_QUOTA),
        (cap * 5, DOCUMENTED_DELETE_QUOTA),
        (cap * 5, None),
    ]
    for backlog in (50, 500, 5000):
        for run_cap, quota in settings:
            runs = simulate_weekly_drain(backlog, run_cap, quota)
            print(f"{backlog:>7} {run_cap:>4} {str(quota):>6} {runs:>14}")


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


class CapBudgetTests(unittest.TestCase):
    def test_default_cap_does_not_exceed_documented_quota(self) -> None:
        self.assertGreater(config.DEFAULT_MAX_DELETIONS_PER_RUN, 0)
        self.assertLessEqual(config.DEFAULT_MAX_DELETIONS_PER_RUN, DOCUMENTED_DELETE_QUOTA)

    def test_zero_cap_never_drains_and_defers_everything(self) -> None:
        self.assertEqual(simulate_weekly_drain(10, 0, DOCUMENTED_DELETE_QUOTA), -1)
        base = datetime(2020, 1, 1, tzinfo=UTC)
        items = [Candidate(Category.POST, str(i), base + timedelta(days=i), None) for i in range(4)]
        allowed, deferred = split_by_budget(items, 0, {})
        self.assertEqual((len(allowed), len(deferred)), (0, 4))

    def test_drain_runs_monotonic_in_cap(self) -> None:
        previous: int | None = None
        for cap in (1, 10, 50, 100, 500):
            runs = simulate_weekly_drain(450, cap, None)
            self.assertGreater(runs, 0)
            if previous is not None:
                self.assertLessEqual(runs, previous)
            previous = runs

    def test_quota_bounds_each_run(self) -> None:
        # a cap above the quota cannot drain faster than the quota allows
        self.assertEqual(simulate_weekly_drain(500, 500, DOCUMENTED_DELETE_QUOTA), 5)
        self.assertEqual(simulate_weekly_drain(500, config.DEFAULT_MAX_DELETIONS_PER_RUN, None), 5)


if __name__ == "__main__":
    unittest.main()
