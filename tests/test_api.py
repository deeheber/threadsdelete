import io
import logging
import unittest

import httpx

from tests.fakes import (
    FakeThreadsApi,
    error_response,
    json_response,
    load_fixture,
    make_client,
)
from threadsdelete.api import (
    API_HOST,
    AuthError,
    QuotaExceededError,
    ReadFailedError,
    RedactingFilter,
    ResponseError,
    redact,
)

TOKEN = "fake-token-value"


def page(ids: list[str], after: str | None = None, more: bool = False) -> httpx.Response:
    body: dict[str, object] = {"data": [{"id": i} for i in ids]}
    if after is not None:
        paging: dict[str, object] = {"cursors": {"after": after}}
        if more:
            paging["next"] = "https://graph.threads.com/v1.0/me/threads?after=" + after
        body["paging"] = paging
    return json_response(body)


class IdentityTests(unittest.TestCase):
    def test_identity_parsed_and_validated(self) -> None:
        fake = FakeThreadsApi()
        fake.add("GET", "me", json_response(load_fixture("me.json")))
        identity = make_client(fake).get_identity()
        self.assertEqual((identity.user_id, identity.username), ("1000001", "example_owner"))
        request = fake.requests[0]
        self.assertEqual(request.url.host, API_HOST)
        self.assertEqual(request.url.params["fields"], "id,username")
        self.assertEqual(request.url.params["access_token"], TOKEN)

        for body in ({"username": "x"}, {"id": "", "username": "x"}, {"id": "1"}, [1]):
            fake = FakeThreadsApi()
            fake.add("GET", "me", json_response(body))
            with self.assertRaises(ResponseError, msg=str(body)):
                make_client(fake).get_identity()


class PaginationTests(unittest.TestCase):
    def test_pagination_follows_cursors_including_empty_pages(self) -> None:
        fake = FakeThreadsApi()
        fake.add(
            "GET",
            "me/threads",
            page(["1", "2"], "c1", more=True),
            page([], "c2", more=True),
            page(["3"], "c3", more=False),
        )
        records = make_client(fake).get_all("me/threads", {"fields": "id", "limit": "100"})
        self.assertEqual([r["id"] for r in records], ["1", "2", "3"])
        afters = [r.url.params.get("after") for r in fake.requests]
        self.assertEqual(afters, [None, "c1", "c2"])
        self.assertTrue(all(r.url.params["limit"] == "100" for r in fake.requests))

    def test_repeated_cursor_rejected(self) -> None:
        fake = FakeThreadsApi()
        fake.add("GET", "me/threads", page(["1"], "c1", True), page(["2"], "c1", True))
        with self.assertRaisesRegex(ResponseError, "repeated"):
            make_client(fake).get_all("me/threads", {})

    def test_next_without_cursor_rejected(self) -> None:
        fake = FakeThreadsApi()
        body = {"data": [{"id": "1"}], "paging": {"next": "https://graph.threads.com/x"}}
        fake.add("GET", "me/threads", json_response(body))
        with self.assertRaisesRegex(ResponseError, "cursor"):
            make_client(fake).get_all("me/threads", {})

    def test_response_urls_are_never_followed(self) -> None:
        fake = FakeThreadsApi()
        body = {
            "data": [{"id": "1"}],
            "paging": {"cursors": {"after": "c1"}, "next": "https://evil.example/steal?x=1"},
        }
        fake.add("GET", "me/threads", json_response(body), page(["2"]))
        make_client(fake).get_all("me/threads", {})
        self.assertEqual({r.url.host for r in fake.requests}, {API_HOST})
        self.assertEqual(len(fake.requests), 2)

    def test_records_need_string_ids(self) -> None:
        for body in ({"data": [{"id": 5}]}, {"data": [{"id": ""}]}, {"data": [3]}, {}):
            fake = FakeThreadsApi()
            fake.add("GET", "me/threads", json_response(body))
            with self.assertRaises(ResponseError, msg=str(body)):
                make_client(fake).get_all("me/threads", {})


class RetryTests(unittest.TestCase):
    def test_read_retries_are_bounded_and_use_retry_after(self) -> None:
        fake = FakeThreadsApi()
        ok = json_response(load_fixture("me.json"))
        fake.add("GET", "me", httpx.ReadTimeout("slow"), httpx.ConnectError("down"), ok)
        make_client(fake).get_identity()
        self.assertEqual(len(fake.requests), 3)
        self.assertEqual(fake.sleeps, [1.0, 2.0])

        fake = FakeThreadsApi()
        busy = json_response({}, 503, {"Retry-After": "2"})
        fake.add("GET", "me", busy, ok)
        make_client(fake).get_identity()
        self.assertEqual(fake.sleeps, [2.0])

        fake = FakeThreadsApi()
        fake.add("GET", "me", httpx.ReadTimeout("slow"), repeat=True)
        with self.assertRaises(ReadFailedError):
            make_client(fake, max_read_retries=2).get_identity()
        self.assertEqual(len(fake.requests), 3)
        self.assertTrue(all(s <= 5.0 for s in fake.sleeps))

    def test_retry_after_above_maximum_stops(self) -> None:
        fake = FakeThreadsApi()
        fake.add("GET", "me", json_response({}, 429, {"Retry-After": "600"}), repeat=True)
        with self.assertRaises(ReadFailedError):
            make_client(fake).get_identity()
        self.assertEqual(len(fake.requests), 1)
        self.assertEqual(fake.sleeps, [])

    def test_http_date_retry_after_falls_back_to_backoff(self) -> None:
        fake = FakeThreadsApi()
        date = {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}
        fake.add("GET", "me", json_response({}, 503, date), json_response(load_fixture("me.json")))
        make_client(fake).get_identity()
        self.assertEqual(fake.sleeps, [1.0])

    def test_auth_and_permission_errors_classified(self) -> None:
        for reply in (error_response(190, 400), json_response({}, 401), error_response(10, 400)):
            fake = FakeThreadsApi()
            fake.add("GET", "me", reply, repeat=True)
            with self.assertRaises(AuthError):
                make_client(fake).get_identity()
            self.assertEqual(len(fake.requests), 1)
        fake = FakeThreadsApi()
        fake.add("GET", "me", error_response(210, 400))
        with self.assertRaises(AuthError):
            make_client(fake).get_identity()

    def test_unknown_error_is_not_quota_or_success(self) -> None:
        fake = FakeThreadsApi()
        fake.add("GET", "me", error_response(9999, 400), json_response({}, 418))
        for _ in range(2):
            with self.assertRaises(ResponseError) as raised:
                make_client(fake).get_identity()
            self.assertNotIsInstance(raised.exception, QuotaExceededError)
        fake = FakeThreadsApi()
        fake.add("GET", "me", error_response(17, 400))
        with self.assertRaises(QuotaExceededError):
            make_client(fake).get_identity()


class SafetyTests(unittest.TestCase):
    def test_token_redacted_from_errors_and_logs(self) -> None:
        fake = FakeThreadsApi()
        body = {"error": {"message": f"bad token {TOKEN}", "code": 9999}}
        fake.add("GET", "me", json_response(body, 400))
        with self.assertRaises(ResponseError) as raised:
            make_client(fake).get_identity()
        self.assertNotIn(TOKEN, str(raised.exception))

        self.assertEqual(
            redact(f"GET /me?access_token={TOKEN}&x=1", [TOKEN]),
            "GET /me?access_token=[REDACTED]&x=1",
        )
        self.assertEqual(redact(f"token {TOKEN}", [TOKEN]), "token [REDACTED]")
        self.assertEqual(redact("nothing", [""]), "nothing")

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.addFilter(RedactingFilter([TOKEN]))
        log = logging.getLogger("test-redaction")
        log.addHandler(handler)
        log.propagate = False
        log.warning("value %s and access_token=abc123", TOKEN)
        output = stream.getvalue()
        self.assertNotIn(TOKEN, output)
        self.assertNotIn("abc123", output)
        self.assertIn("[REDACTED]", output)

    def test_transport_errors_do_not_leak_token(self) -> None:
        fake = FakeThreadsApi()
        fake.add("GET", "me", httpx.ConnectError(f"https://x/?access_token={TOKEN}"), repeat=True)
        with self.assertRaises(ReadFailedError) as raised:
            make_client(fake).get_identity()
        self.assertNotIn(TOKEN, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
