import unittest

import httpx

from tests.fakes import FakeThreadsApi, error_response, json_response, load_fixture, make_client
from threadsdelete.api import (
    AuthError,
    Identity,
    ItemError,
    MutationBlockedError,
    QuotaExceededError,
    ResponseError,
    UnknownOutcomeError,
)
from threadsdelete.core import Candidate, Category, Operation, parse_timestamp

POST = Candidate(Category.POST, "9000001", parse_timestamp("2026-01-05T10:00:00+0000"), None)
OWNER = Identity("1000001", "example_owner")


class RemoveTests(unittest.TestCase):
    def remove(self, *replies: httpx.Response | Exception) -> FakeThreadsApi:
        fake = FakeThreadsApi()
        fake.add("DELETE", POST.target_id, *replies)
        make_client(fake, read_only=False).remove(POST)
        return fake

    def fails(self, kind: type[Exception], *replies: httpx.Response | Exception) -> FakeThreadsApi:
        fake = FakeThreadsApi()
        fake.add("DELETE", POST.target_id, *replies, repeat=True)
        with self.assertRaises(kind) as raised:
            make_client(fake, read_only=False).remove(POST)
        self.assertIs(type(raised.exception), kind)
        self.assertEqual(len(fake.requests), 1, "a removal is attempted exactly once")
        return fake

    def test_remove_success_requires_valid_body(self) -> None:
        fake = self.remove(json_response(load_fixture("delete_success.json")))
        self.assertEqual(fake.requests[0].method, "DELETE")
        self.assertEqual(fake.requests[0].url.params["access_token"], "fake-token-value")
        self.remove(json_response({"success": True}))
        for body in ({}, {"success": "true"}, {"success": 1}, [True], {"deleted_id": "9000001"}):
            self.fails(UnknownOutcomeError, json_response(body))
        self.fails(UnknownOutcomeError, httpx.Response(200, content=b"not json"))
        self.fails(UnknownOutcomeError, json_response({"success": True, "deleted_id": "other"}))

    def test_remove_timeout_is_unknown_and_not_retried(self) -> None:
        fake = self.fails(UnknownOutcomeError, httpx.ReadTimeout("slow"))
        self.assertEqual(fake.sleeps, [])
        self.fails(UnknownOutcomeError, httpx.ConnectError("down"))

    def test_remove_5xx_and_malformed_body_are_unknown(self) -> None:
        for status in (500, 502, 503, 504):
            self.fails(UnknownOutcomeError, json_response({}, status))
        self.fails(UnknownOutcomeError, error_response(1, 500))
        self.fails(UnknownOutcomeError, httpx.Response(400, content=b"<html>"))
        self.fails(UnknownOutcomeError, json_response({"weird": 1}, 418))

    def test_remove_success_false_is_item_failure(self) -> None:
        self.fails(ItemError, json_response({"success": False}))

    def test_remove_item_level_rejection_is_item_error(self) -> None:
        self.fails(ItemError, error_response(100, 400))
        self.fails(ItemError, error_response(100, 404))

    def test_remove_auth_error_classified(self) -> None:
        self.fails(AuthError, json_response({}, 401))
        self.fails(AuthError, error_response(190, 400))
        self.fails(AuthError, error_response(10, 400))

    def test_remove_quota_error_only_for_documented_codes(self) -> None:
        self.fails(QuotaExceededError, error_response(4, 400))
        self.fails(QuotaExceededError, error_response(17, 400))
        self.fails(QuotaExceededError, error_response(341, 400))
        self.fails(QuotaExceededError, json_response({}, 429))
        # an undocumented 4xx is an item rejection, never quota exhaustion
        self.fails(ItemError, error_response(9999, 400))

    def test_read_only_client_blocks_every_mutation_method(self) -> None:
        fake = FakeThreadsApi()
        client = make_client(fake, read_only=True)
        for method in ("DELETE", "POST", "PUT", "PATCH"):
            with self.assertRaises(MutationBlockedError, msg=method):
                client._send(method, "123", {})
        with self.assertRaises(MutationBlockedError):
            client.remove(POST)
        self.assertEqual(fake.requests, [])

    def test_only_delete_operations_are_supported(self) -> None:
        fake = FakeThreadsApi()
        client = make_client(fake, read_only=False)
        for category in (Category.REPOST, Category.LIKE):
            with self.assertRaises(ValueError):
                client.remove(Candidate(category, "5", POST.action_at, None))
        self.assertEqual(fake.requests, [])


class QuotaTests(unittest.TestCase):
    def test_quota_parsed_from_fixture(self) -> None:
        fake = FakeThreadsApi()
        fake.add(
            "GET", "1000001/threads_publishing_limit", json_response(load_fixture("quota.json"))
        )
        quota = make_client(fake).get_quota(OWNER)
        self.assertEqual(quota.remaining, {Operation.DELETE: 63})
        self.assertEqual(quota.window_description, "rolling 24 hours")
        request = fake.requests[0]
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.url.params["fields"], "delete_quota_usage,delete_config")

    def test_quota_never_negative_and_malformed_rejected(self) -> None:
        over = {
            "data": [
                {
                    "delete_quota_usage": 120,
                    "delete_config": {"quota_total": 100, "quota_duration": 86400},
                }
            ]
        }
        fake = FakeThreadsApi()
        fake.add("GET", "1000001/threads_publishing_limit", json_response(over))
        quota = make_client(fake).get_quota(OWNER)
        self.assertEqual(quota.remaining[Operation.DELETE], 0)
        for body in (
            {},
            {"data": []},
            {"data": [{}]},
            {"data": [{"delete_quota_usage": "1", "delete_config": {}}]},
        ):
            fake = FakeThreadsApi()
            fake.add("GET", "1000001/threads_publishing_limit", json_response(body))
            with self.assertRaises(ResponseError, msg=str(body)):
                make_client(fake).get_quota(OWNER)


if __name__ == "__main__":
    unittest.main()
