import dataclasses
import io
import unittest
from datetime import UTC, datetime, timedelta

import httpx

from tests.fakes import (
    FakeThreadsApi,
    json_response,
    load_fixture,
    make_client,
)
from threadsdelete import cleanup
from threadsdelete.api import ThreadsClient
from threadsdelete.cleanup import IdentityMismatchError, split_by_budget
from threadsdelete.config import load_config
from threadsdelete.core import Candidate, Category, Operation

RUN_START = datetime(2026, 10, 23, 5, 0, 0, tzinfo=UTC)
CONFIG = load_config({"THREADS_ACCESS_TOKEN": "fake-token-value", "THREADS_USER_ID": "1000001"})


def full_fake() -> FakeThreadsApi:
    fake = FakeThreadsApi()
    fake.add("GET", "me", json_response(load_fixture("me.json")))
    fake.add(
        "GET",
        "me/threads",
        json_response(load_fixture("threads_page1.json")),
        json_response(load_fixture("threads_page2.json")),
    )
    fake.add("GET", "me/replies", json_response(load_fixture("replies.json")))
    return fake


def preview(fake: FakeThreadsApi, cap: int | None = None) -> tuple[str, cleanup.RunSummary]:
    config = CONFIG if cap is None else dataclasses.replace(CONFIG, max_deletions_per_run=cap)
    out = io.StringIO()
    client: ThreadsClient = make_client(fake)
    summary = cleanup.run(config, client, RUN_START, out)
    return out.getvalue(), summary


def lines_starting(text: str, *prefixes: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith(prefixes)]


class PreviewTests(unittest.TestCase):
    def test_preview_lists_eligible_candidates_from_fixtures(self) -> None:
        text, summary = preview(full_fake())
        self.assertIn("Account: @example_owner (1000001)", text)
        self.assertIn("Cutoff (UTC): 2026-07-25T05:00:00Z", text)
        self.assertIn("Mode: DRY RUN (no changes will be made)", text)
        self.assertIn("Excluded: repost", text)
        self.assertIn("Excluded: like", text)
        listed = lines_starting(text, "would remove", "deferred")
        self.assertEqual(
            [line.split("  ")[2] for line in listed],
            ["9000001", "7000001", "9000002", "9000003", "9000004"],
        )
        self.assertIn("https://www.threads.com/@example_owner/post/AAA1", listed[0])
        self.assertTrue(listed[0].startswith("would remove  post  9000001"))
        counts = {c: (v.scanned, v.eligible, v.would_remove) for c, v in summary.counts.items()}
        self.assertEqual(
            counts,
            {Category.POST: (5, 3, 3), Category.QUOTE: (1, 1, 1), Category.REPLY: (2, 1, 1)},
        )
        self.assertIn("=== Summary ===", text)
        self.assertIn("post: scanned=5 eligible=3 would_remove=3", text)
        self.assertIn("Discovery: complete", text)
        self.assertIn("Quota: not checked", text)
        self.assertTrue(summary.discovery_complete)

    def test_identity_mismatch_stops_before_discovery(self) -> None:
        fake = FakeThreadsApi()
        fake.add("GET", "me", json_response({"id": "999", "username": "someone_else"}))
        with self.assertRaises(IdentityMismatchError):
            preview(fake)
        self.assertEqual(fake.paths(), ["me"])

    def test_incomplete_discovery_is_labelled_and_selects_nothing(self) -> None:
        fake = FakeThreadsApi()
        fake.add("GET", "me", json_response(load_fixture("me.json")))
        fake.add(
            "GET",
            "me/threads",
            json_response(load_fixture("threads_page1.json")),
            json_response({}, 503),
            json_response({}, 503),
            json_response({}, 503),
        )
        text, summary = preview(fake)
        self.assertFalse(summary.discovery_complete)
        self.assertIn("Discovery: INCOMPLETE", text)
        self.assertIn("(no changes made)", text)
        self.assertEqual(lines_starting(text, "would remove", "deferred"), [])
        self.assertIn("=== Summary ===", text)
        self.assertEqual(fake.calls("GET", "me/replies"), [])

    def test_cap_splits_would_remove_and_deferred(self) -> None:
        text, summary = preview(full_fake(), cap=2)
        listed = lines_starting(text, "would remove", "deferred")
        self.assertEqual(
            [(line.split("  ")[0], line.split("  ")[2]) for line in listed],
            [
                ("would remove", "9000001"),
                ("would remove", "7000001"),
                ("deferred", "9000002"),
                ("deferred", "9000003"),
                ("deferred", "9000004"),
            ],
        )
        self.assertEqual(sum(c.would_remove for c in summary.counts.values()), 2)
        self.assertEqual(sum(c.deferred for c in summary.counts.values()), 3)

        text, summary = preview(full_fake(), cap=0)
        self.assertEqual(sum(c.would_remove for c in summary.counts.values()), 0)
        self.assertEqual(sum(c.deferred for c in summary.counts.values()), 5)
        self.assertEqual(len(lines_starting(text, "deferred")), 5)

    def test_preview_sends_only_get_requests(self) -> None:
        fake = full_fake()
        preview(fake)
        self.assertTrue(fake.requests)
        self.assertEqual({r.method for r in fake.requests}, {"GET"})
        self.assertTrue(all(isinstance(r, httpx.Request) for r in fake.requests))


class SplitByBudgetTests(unittest.TestCase):
    def items(self, count: int) -> list[Candidate]:
        base = RUN_START - timedelta(days=200)
        return [
            Candidate(Category.POST, str(i), base + timedelta(days=i), None) for i in range(count)
        ]

    def test_split_by_budget_respects_operation_quota(self) -> None:
        items = self.items(5)
        allowed, deferred = split_by_budget(items, 4, {Operation.DELETE: 2})
        self.assertEqual([c.target_id for c in allowed], ["0", "1"])
        self.assertEqual([c.target_id for c in deferred], ["2", "3", "4"])
        allowed, deferred = split_by_budget(items, 4, {Operation.DELETE: None})
        self.assertEqual(len(allowed), 4)
        self.assertEqual(len(deferred), 1)
        allowed, deferred = split_by_budget(items, 10, {})
        self.assertEqual((len(allowed), len(deferred)), (5, 0))
        allowed, deferred = split_by_budget(items, 3, {Operation.DELETE: 0})
        self.assertEqual((len(allowed), len(deferred)), (0, 5))


if __name__ == "__main__":
    unittest.main()
