import unittest
from datetime import UTC, datetime
from typing import Any

from tests.fakes import FakeThreadsApi, json_response, load_fixture, make_client
from threadsdelete.api import (
    SUPPORTED_CATEGORIES,
    UNSUPPORTED_CATEGORIES,
    Identity,
    OwnershipError,
    ResponseError,
    ThreadsClient,
)
from threadsdelete.core import Category, TimestampError

OWNER = Identity("1000001", "example_owner")


def threads_fake(*records: dict[str, Any]) -> tuple[FakeThreadsApi, ThreadsClient]:
    fake = FakeThreadsApi()
    fake.add("GET", "me/threads", json_response({"data": list(records)}))
    return fake, make_client(fake)


def post(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": "1",
        "media_type": "TEXT_POST",
        "timestamp": "2026-01-01T00:00:00+0000",
        "owner": {"id": "1000001"},
        "is_quote_post": False,
    }
    record.update(overrides)
    return record


def repost(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": "5",
        "media_type": "REPOST_FACADE",
        "timestamp": "2026-01-01T00:00:00+0000",
        "owner": {"id": "1000001"},
    }
    record.update(overrides)
    return record


class ThreadsEdgeTests(unittest.TestCase):
    def fixture_client(self) -> tuple[FakeThreadsApi, ThreadsClient]:
        fake = FakeThreadsApi()
        fake.add(
            "GET",
            "me/threads",
            json_response(load_fixture("threads_page1.json")),
            json_response(load_fixture("threads_page2.json")),
        )
        return fake, make_client(fake)

    def test_posts_quotes_media_and_reposts_classified(self) -> None:
        fake, client = self.fixture_client()
        posts, post_scanned = client.discover(Category.POST, OWNER)
        quotes, quote_scanned = client.discover(Category.QUOTE, OWNER)
        reposts, repost_scanned = client.discover(Category.REPOST, OWNER)
        self.assertEqual([c.target_id for c in posts], ["9000001", "9000002", "9000003", "9000006"])
        self.assertTrue(all(c.category is Category.POST for c in posts))
        self.assertEqual([c.target_id for c in quotes], ["9000004"])
        self.assertEqual(quotes[0].category, Category.QUOTE)
        self.assertEqual([c.target_id for c in reposts], ["9000005"])
        self.assertEqual(reposts[0].category, Category.REPOST)
        self.assertEqual((post_scanned, quote_scanned, repost_scanned), (4, 1, 1))
        everything = {c.target_id for c in posts + quotes + reposts}
        self.assertNotIn("9000031", everything)  # carousel child
        self.assertEqual(len(fake.calls("GET", "me/threads")), 2)  # two pages, fetched once
        self.assertEqual(posts[0].permalink, "https://www.threads.com/@example_owner/post/AAA1")

    def test_repost_facade_wins_over_quote_flag(self) -> None:
        _, client = threads_fake(post(id="5", media_type="REPOST_FACADE", is_quote_post=True))
        reposts, scanned = client.discover(Category.REPOST, OWNER)
        self.assertEqual([(c.category, c.target_id) for c in reposts], [(Category.REPOST, "5")])
        self.assertEqual(scanned, 1)
        self.assertEqual(client.discover(Category.QUOTE, OWNER), ([], 0))

    def test_creation_time_is_the_action_time(self) -> None:
        _, client = self.fixture_client()
        posts, _ = client.discover(Category.POST, OWNER)
        self.assertEqual(posts[0].action_at, datetime(2026, 1, 5, 10, 0, tzinfo=UTC))

    def test_foreign_or_missing_owner_aborts(self) -> None:
        for owner in (
            {"owner": {"id": "42"}},
            {"owner": None},
            {"owner": {}},
            {"owner": "1000001"},
        ):
            _, client = threads_fake(post(**owner))
            with self.assertRaises(OwnershipError, msg=str(owner)):
                client.discover(Category.POST, OWNER)
        record = post()
        del record["owner"]
        _, client = threads_fake(record)
        with self.assertRaises(OwnershipError):
            client.discover(Category.POST, OWNER)

    def test_malformed_timestamp_aborts_discovery(self) -> None:
        for stamp in ("2026-01-01T00:00:00", "yesterday", None, 17):
            _, client = threads_fake(post(timestamp=stamp))
            with self.assertRaises(TimestampError, msg=str(stamp)):
                client.discover(Category.POST, OWNER)

    def test_repost_uses_repost_timestamp_and_own_id(self) -> None:
        record = repost(reposted_post={"id": "8000001"})
        _, client = threads_fake(record)
        found, scanned = client.discover(Category.REPOST, OWNER)
        self.assertEqual(scanned, 1)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].target_id, "5")
        self.assertIs(found[0].category, Category.REPOST)
        self.assertEqual(found[0].action_at, datetime(2026, 1, 1, tzinfo=UTC))
        self.assertIsNone(found[0].permalink)

    def test_repost_foreign_or_missing_owner_aborts(self) -> None:
        for owner in (
            {"owner": {"id": "42"}},
            {"owner": None},
            {"owner": {}},
            {"owner": "1000001"},
        ):
            _, client = threads_fake(repost(**owner))
            with self.assertRaises(OwnershipError, msg=str(owner)):
                client.discover(Category.REPOST, OWNER)
        record = repost()
        del record["owner"]
        _, client = threads_fake(record)
        with self.assertRaises(OwnershipError):
            client.discover(Category.REPOST, OWNER)

    def test_malformed_repost_timestamp_aborts(self) -> None:
        for stamp in ("2026-01-01T00:00:00", "yesterday", None):
            _, client = threads_fake(repost(timestamp=stamp))
            with self.assertRaises(TimestampError, msg=str(stamp)):
                client.discover(Category.REPOST, OWNER)

    def test_unclassifiable_record_aborts(self) -> None:
        record = post()
        del record["media_type"]
        _, client = threads_fake(record)
        with self.assertRaises(ResponseError) as raised:
            client.discover(Category.POST, OWNER)
        self.assertIn("media_type", str(raised.exception))

    def test_discovery_requests_never_ask_for_text(self) -> None:
        fake, client = self.fixture_client()
        fake.add("GET", "me/replies", json_response(load_fixture("replies.json")))
        client.discover(Category.POST, OWNER)
        client.discover(Category.REPOST, OWNER)
        client.discover(Category.REPLY, OWNER)
        self.assertGreaterEqual(len(fake.requests), 3)
        for request in fake.requests:
            fields = request.url.params["fields"].split(",")
            self.assertNotIn("text", fields)
            self.assertNotIn("reposted_post", fields)
            self.assertIn("timestamp", fields)


class RepliesTests(unittest.TestCase):
    def test_replies_discovered_with_creation_time(self) -> None:
        fake = FakeThreadsApi()
        fake.add("GET", "me/replies", json_response(load_fixture("replies.json")))
        found, scanned = make_client(fake).discover(Category.REPLY, OWNER)
        self.assertEqual(scanned, 2)
        self.assertEqual([c.target_id for c in found], ["7000001", "7000002"])
        self.assertEqual(found[0].category, Category.REPLY)
        self.assertEqual(found[0].action_at, datetime(2026, 1, 20, 10, 0, tzinfo=UTC))
        self.assertIsNone(found[1].permalink)

    def test_reply_not_owned_aborts(self) -> None:
        base = {"id": "7", "timestamp": "2026-01-01T00:00:00+0000", "username": "example_owner"}
        for extra in (
            {"is_reply_owned_by_me": False},
            {},
            {"is_reply_owned_by_me": "true"},
            {"is_reply_owned_by_me": True, "username": "someone_else"},
        ):
            fake = FakeThreadsApi()
            fake.add("GET", "me/replies", json_response({"data": [{**base, **extra}]}))
            with self.assertRaises(OwnershipError, msg=str(extra)):
                make_client(fake).discover(Category.REPLY, OWNER)


class CategoryCoverageTests(unittest.TestCase):
    def test_unsupported_categories_excluded_with_reason(self) -> None:
        self.assertEqual(
            sorted(SUPPORTED_CATEGORIES + tuple(UNSUPPORTED_CATEGORIES)), sorted(Category)
        )
        self.assertEqual(set(UNSUPPORTED_CATEGORIES), {Category.LIKE})
        self.assertIn(Category.REPOST, SUPPORTED_CATEGORIES)
        fake = FakeThreadsApi()
        client = make_client(fake)
        for category, reason in UNSUPPORTED_CATEGORIES.items():
            self.assertTrue(reason.strip())
            with self.assertRaises(ValueError):
                client.discover(category, OWNER)
        self.assertEqual(fake.requests, [])


if __name__ == "__main__":
    unittest.main()
