"""Offline measurements behind the tuned ASSUMPTION defaults (see CLAUDE.md tuning protocol)."""

import logging
import re
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from tests.fakes import FakeThreadsApi, make_client
from threadsdelete import config
from threadsdelete.api import ReadFailedError
from threadsdelete.cleanup import split_by_budget
from threadsdelete.core import Candidate, Category, Operation

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "cleanup-feed.yml"


def job_timeout_minutes() -> int:
    """jobs.cleanup.timeout-minutes (SPEC section 5 assumption) read from the workflow text."""
    match = re.search(r"(?m)^    timeout-minutes:\s*(\d+)\s*$", WORKFLOW.read_text())
    if match is None:
        raise AssertionError("cleanup-feed.yml has no jobs.cleanup.timeout-minutes")
    return int(match.group(1))


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
    print(f"Job timeout assumed: {job_timeout_minutes()} min ({job_timeout_minutes() * 60} s)")
    print("variant        timeout retries maxwait attempts total_sleep worst_case_s")
    for name, timeout, retries, wait in rows:
        m = measure_read_chain(timeout, retries, wait)
        print(
            f"{name:<14} {timeout:>7.0f} {retries:>7} {wait:>7.0f} {m['attempts']:>8.0f} "
            f"{m['total_sleep']:>11.0f} {m['worst_case_seconds']:>13.0f}"
        )
    print()
    job_seconds = job_timeout_minutes() * 60
    chain = measure_read_chain(
        config.DEFAULT_HTTP_TIMEOUT_SECONDS,
        config.DEFAULT_MAX_READ_RETRIES,
        config.DEFAULT_MAX_RETRY_WAIT_SECONDS,
    )["worst_case_seconds"]
    print(f"Job budget {job_seconds} s; one fully retried read chain {chain:.0f} s")
    print("Upper bound if every request needs its whole retry chain (identity + quota + N pages)")
    print("pages  requests  upper_bound_s  fits")
    for pages in (1, 10, 40):
        bound = (2 + pages) * chain
        print(f"{pages:>5} {2 + pages:>9} {bound:>14.0f}  {'yes' if bound < job_seconds else 'no'}")
    fits = int(job_seconds // chain)
    print(f"Requests covered when every one needs its whole chain: {fits} (pages: {fits - 2})")
    removal = config.DEFAULT_MAX_DELETIONS_PER_RUN * config.DEFAULT_HTTP_TIMEOUT_SECONDS
    print(f"Removal upper bound (cap x timeout, no retries): {removal:.0f} s")
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


class JobTimeoutTests(unittest.TestCase):
    def test_job_timeout_is_valid_github_value(self) -> None:
        minutes = job_timeout_minutes()
        self.assertGreater(minutes, 0)
        self.assertLessEqual(minutes, 360)

    def test_job_covers_identity_quota_and_a_page_per_category(self) -> None:
        chain = measure_read_chain(
            config.DEFAULT_HTTP_TIMEOUT_SECONDS,
            config.DEFAULT_MAX_READ_RETRIES,
            config.DEFAULT_MAX_RETRY_WAIT_SECONDS,
        )["worst_case_seconds"]
        categories = 3  # posts/quotes share one edge; replies another: 3 is a safe upper bound
        self.assertLess((2 + categories) * chain, job_timeout_minutes() * 60)


class CapBudgetTests(unittest.TestCase):
    def test_default_cap_does_not_exceed_documented_quota(self) -> None:
        self.assertGreater(config.DEFAULT_MAX_DELETIONS_PER_RUN, 0)
        self.assertLessEqual(config.DEFAULT_MAX_DELETIONS_PER_RUN, DOCUMENTED_DELETE_QUOTA)


if __name__ == "__main__":
    unittest.main()
