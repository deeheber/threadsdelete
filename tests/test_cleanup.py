import dataclasses
import io
import unittest
from datetime import UTC, datetime, timedelta

import httpx

from tests.fakes import (
    FakeThreadsApi,
    error_response,
    fixture_api,
    json_response,
    load_fixture,
    make_client,
)
from threadsdelete import cleanup
from threadsdelete.api import AuthError, ThreadsClient
from threadsdelete.cleanup import IdentityMismatchError, split_by_budget
from threadsdelete.config import load_config
from threadsdelete.core import (
    Candidate,
    Category,
    CategoryCounts,
    ExitCode,
    Operation,
    RunSummary,
)

RUN_START = datetime(2026, 10, 23, 5, 0, 0, tzinfo=UTC)
CONFIG = load_config({"THREADS_ACCESS_TOKEN": "fake-token-value", "THREADS_USER_ID": "1000001"})


def preview(fake: FakeThreadsApi, cap: int | None = None) -> tuple[str, cleanup.RunSummary]:
    config = CONFIG if cap is None else dataclasses.replace(CONFIG, max_deletions_per_run=cap)
    out = io.StringIO()
    client: ThreadsClient = make_client(fake)
    summary = cleanup.run(config, client, RUN_START, out)
    return out.getvalue(), summary


ELIGIBLE_ORDER = ["9000001", "7000001", "9000002", "9000003", "9000004"]
OK = json_response({"success": True})


def real_run(
    fake: FakeThreadsApi, cap: int | None = None
) -> tuple[str, cleanup.RunSummary | None, Exception | None]:
    """Run in removal mode; returns output, summary and any exception raised after printing."""
    config = dataclasses.replace(CONFIG, dry_run=False)
    if cap is not None:
        config = dataclasses.replace(config, max_deletions_per_run=cap)
    out = io.StringIO()
    client = make_client(fake, read_only=False)
    try:
        summary = cleanup.run(config, client, RUN_START, out)
    except AuthError as exc:
        return out.getvalue(), None, exc
    return out.getvalue(), summary, None


def deletes(fake: FakeThreadsApi) -> list[str]:
    return [r.url.path.rsplit("/", 1)[-1] for r in fake.requests if r.method == "DELETE"]


def lines_starting(text: str, *prefixes: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith(prefixes)]


class PreviewTests(unittest.TestCase):
    def test_preview_lists_eligible_candidates_from_fixtures(self) -> None:
        text, summary = preview(fixture_api())
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
        self.assertIn("Quota: available (delete: 63 remaining, rolling 24 hours)", text)
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
        text, summary = preview(fixture_api(), cap=2)
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

        text, summary = preview(fixture_api(), cap=0)
        self.assertEqual(sum(c.would_remove for c in summary.counts.values()), 0)
        self.assertEqual(sum(c.deferred for c in summary.counts.values()), 5)
        self.assertEqual(len(lines_starting(text, "deferred")), 5)

    def test_preview_sends_only_get_requests(self) -> None:
        fake = fixture_api()
        preview(fake)
        self.assertTrue(fake.requests)
        self.assertEqual({r.method for r in fake.requests}, {"GET"})
        self.assertTrue(all(isinstance(r, httpx.Request) for r in fake.requests))


class RemovalTests(unittest.TestCase):
    def test_dry_run_sends_no_mutation_for_any_category(self) -> None:
        fake = fixture_api()
        text, summary = preview(fake)
        self.assertEqual({r.method for r in fake.requests}, {"GET"})
        self.assertEqual(len(fake.calls("GET", "1000001/threads_publishing_limit")), 1)
        self.assertEqual({c for c, v in summary.counts.items() if v.eligible}, set(summary.counts))
        self.assertEqual(sum(v.removed for v in summary.counts.values()), 0)
        self.assertNotIn("removed  ", text)

    def test_real_run_removes_oldest_first_within_cap(self) -> None:
        fake = fixture_api()
        for item in ELIGIBLE_ORDER:
            fake.add("DELETE", item, OK)
        text, summary, error = real_run(fake, cap=3)
        assert summary is not None
        self.assertIsNone(error)
        self.assertEqual(deletes(fake), ELIGIBLE_ORDER[:3])
        self.assertIn("Mode: REMOVAL", text)
        self.assertEqual(len(lines_starting(text, "removed")), 3)
        self.assertEqual(len(lines_starting(text, "deferred")), 2)
        self.assertEqual(sum(v.removed for v in summary.counts.values()), 3)

    def test_quota_smaller_than_cap_defers_rest(self) -> None:
        fake = fixture_api(quota=False)
        low = {
            "data": [
                {
                    "delete_quota_usage": 98,
                    "delete_config": {"quota_total": 100, "quota_duration": 86400},
                }
            ]
        }
        fake.add("GET", "1000001/threads_publishing_limit", json_response(low))
        for item in ELIGIBLE_ORDER[:2]:
            fake.add("DELETE", item, OK)
        text, summary, _ = real_run(fake)
        assert summary is not None
        self.assertEqual(deletes(fake), ELIGIBLE_ORDER[:2])
        self.assertIn("Quota: available (delete: 2 remaining", text)
        self.assertEqual(sum(v.deferred for v in summary.counts.values()), 3)

    def test_quota_unavailable_falls_back_to_cap_and_is_labelled(self) -> None:
        fake = fixture_api(quota=False)
        fake.add("GET", "1000001/threads_publishing_limit", json_response({"data": []}))
        for item in ELIGIBLE_ORDER[:2]:
            fake.add("DELETE", item, OK)
        text, summary, _ = real_run(fake, cap=2)
        assert summary is not None
        self.assertEqual(deletes(fake), ELIGIBLE_ORDER[:2])
        self.assertIn("Quota: unavailable", text)
        self.assertIn("MAX_DELETIONS_PER_RUN", text)
        self.assertEqual(summary.quota_status.value, "unavailable")

    def test_item_failure_continues_and_is_counted(self) -> None:
        fake = fixture_api()
        fake.add("DELETE", "9000001", OK)
        fake.add("DELETE", "7000001", error_response(100, 400))
        for item in ELIGIBLE_ORDER[2:]:
            fake.add("DELETE", item, OK)
        text, summary, _ = real_run(fake)
        assert summary is not None
        self.assertEqual(deletes(fake), ELIGIBLE_ORDER)
        self.assertEqual(summary.counts[Category.REPLY].failed, 1)
        self.assertEqual(sum(v.removed for v in summary.counts.values()), 4)
        self.assertEqual(len(lines_starting(text, "failed")), 1)

    def test_unknown_outcome_stops_and_is_not_success(self) -> None:
        fake = fixture_api()
        fake.add("DELETE", "9000001", OK)
        fake.add("DELETE", "7000001", httpx.ReadTimeout("slow"), repeat=True)
        text, summary, _ = real_run(fake)
        assert summary is not None
        self.assertEqual(deletes(fake), ["9000001", "7000001"])
        self.assertEqual(summary.counts[Category.REPLY].unknown_outcome, 1)
        self.assertEqual(sum(v.removed for v in summary.counts.values()), 1)
        self.assertEqual(sum(v.deferred for v in summary.counts.values()), 3)
        self.assertIn("will rediscover next run", text)
        self.assertEqual(len(lines_starting(text, "removed")), 1)

    def test_auth_failure_stops_globally(self) -> None:
        fake = fixture_api()
        fake.add("DELETE", "9000001", OK)
        fake.add("DELETE", "7000001", json_response({}, 401))
        text, summary, error = real_run(fake)
        self.assertIsNone(summary)
        self.assertIsInstance(error, AuthError)
        self.assertEqual(deletes(fake), ["9000001", "7000001"])
        self.assertIn("=== Summary ===", text)
        self.assertIn("deferred  reply  7000001", text)

    def test_quota_error_mid_run_defers_rest(self) -> None:
        fake = fixture_api()
        fake.add("DELETE", "9000001", OK)
        fake.add("DELETE", "7000001", error_response(4, 400))
        text, summary, _ = real_run(fake)
        assert summary is not None
        self.assertEqual(deletes(fake), ["9000001", "7000001"])
        self.assertEqual(sum(v.removed for v in summary.counts.values()), 1)
        self.assertEqual(sum(v.deferred for v in summary.counts.values()), 4)
        self.assertEqual(sum(v.failed + v.unknown_outcome for v in summary.counts.values()), 0)

    def test_incomplete_discovery_prevents_all_mutation(self) -> None:
        fake = FakeThreadsApi()
        fake.add("GET", "me", json_response(load_fixture("me.json")))
        fake.add("GET", "me/threads", json_response(load_fixture("threads_page1.json")))
        fake.add("GET", "me/threads", json_response({}, 503), repeat=True)
        text, summary, _ = real_run(fake)
        assert summary is not None
        self.assertFalse(summary.discovery_complete)
        self.assertEqual(deletes(fake), [])
        self.assertEqual({r.method for r in fake.requests}, {"GET"})
        self.assertIn("Discovery: INCOMPLETE", text)

    def test_counts_add_up(self) -> None:
        fake = fixture_api()
        fake.add("DELETE", "9000001", OK)
        fake.add("DELETE", "7000001", error_response(100, 400))
        fake.add("DELETE", "9000002", OK)
        fake.add("DELETE", "9000003", httpx.ConnectError("down"))
        _, summary, _ = real_run(fake, cap=4)
        assert summary is not None
        for category, c in summary.counts.items():
            self.assertEqual(
                c.eligible, c.removed + c.failed + c.unknown_outcome + c.deferred, category
            )
        self.assertEqual(sum(c.would_remove for c in summary.counts.values()), 4)
        _, dry = preview(fixture_api(), cap=2)
        for category, c in dry.counts.items():
            self.assertEqual(c.eligible, c.would_remove + c.deferred, category)
        self.assertEqual(sum(c.would_remove for c in dry.counts.values()), 2)


class ExitStatusTests(unittest.TestCase):
    def summary(self, **changes: object) -> RunSummary:
        summary = RunSummary(
            counts={Category.POST: CategoryCounts(), Category.REPLY: CategoryCounts()}
        )
        for key, value in changes.items():
            setattr(summary, key, value)
        return summary

    def test_exit_status_matrix(self) -> None:
        ok = self.summary()
        self.assertEqual(cleanup.exit_status(ok), ExitCode.OK)  # nothing eligible
        deferred = self.summary()
        deferred.counts[Category.POST].eligible = 3
        deferred.counts[Category.POST].deferred = 3
        self.assertEqual(cleanup.exit_status(deferred), ExitCode.OK)
        failed = self.summary()
        failed.counts[Category.REPLY].failed = 1
        self.assertEqual(cleanup.exit_status(failed), ExitCode.FAILURE)
        unknown = self.summary()
        unknown.counts[Category.POST].unknown_outcome = 1
        self.assertEqual(cleanup.exit_status(unknown), ExitCode.FAILURE)
        self.assertEqual(
            cleanup.exit_status(self.summary(discovery_complete=False)), ExitCode.FAILURE
        )
        self.assertEqual(cleanup.exit_status(self.summary(auth_failed=True)), ExitCode.AUTH)
        both = self.summary(auth_failed=True, discovery_complete=False)
        self.assertEqual(cleanup.exit_status(both), ExitCode.AUTH)


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
