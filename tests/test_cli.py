import contextlib
import io
import logging
import os
import unittest
from datetime import UTC, datetime, timedelta
from unittest import mock

import httpx

import main
from tests.fakes import FakeThreadsApi, error_response, fixture_api, json_response, load_fixture
from threadsdelete.api import ApiError
from threadsdelete.core import Candidate, Category

TOKEN = "fake-token-value-for-cli"
RUN_START = datetime(2026, 10, 23, 5, 0, 0, tzinfo=UTC)
ENV = {"THREADS_ACCESS_TOKEN": TOKEN, "THREADS_USER_ID": "1000001"}


class HelpTests(unittest.TestCase):
    def test_help_needs_no_credentials(self) -> None:
        out = io.StringIO()
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            contextlib.redirect_stdout(out),
            self.assertRaises(SystemExit) as raised,
        ):
            main.main(["--help"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("usage:", out.getvalue())
        self.assertIn("DRY_RUN", out.getvalue())
        self.assertIn("MAX_DELETIONS_PER_RUN", out.getvalue())


def run_main(fake: FakeThreadsApi, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main.main(
        [],
        env=ENV if env is None else env,
        transport=fake.transport,
        now=RUN_START,
        out=out,
        err=err,
    )
    return code, out.getvalue(), err.getvalue()


class CliPreviewTests(unittest.TestCase):
    def test_preview_with_fake_transport_exits_zero(self) -> None:
        code, out, _ = run_main(fixture_api(), {**ENV, "DRY_RUN": "true"})
        self.assertEqual(code, 0)
        self.assertIn("Mode: DRY RUN", out)
        self.assertIn("=== Summary ===", out)
        self.assertIn("would remove  post  9000001", out)

    def test_preview_lists_eligible_repost(self) -> None:
        fake = fixture_api(eligible_repost=True)
        code, out, _ = run_main(fake)
        self.assertEqual(code, 0)
        self.assertIn("would remove  repost  9000007", out)
        self.assertIn("repost: scanned=2 eligible=1 would_remove=1", out)
        self.assertNotIn("Excluded: repost", out)
        self.assertIn("Excluded: like", out)
        self.assertEqual({r.method for r in fake.requests}, {"GET"})

    def test_missing_dry_run_defaults_to_preview(self) -> None:
        fake = fixture_api()
        code, out, _ = run_main(fake)
        self.assertEqual(code, 0)
        self.assertIn("Mode: DRY RUN", out)
        self.assertEqual({r.method for r in fake.requests}, {"GET"})

    def test_invalid_config_exits_2_without_network(self) -> None:
        fake = fixture_api()
        code, out, err = run_main(fake, {**ENV, "DAYS_AGO": "-3", "DRY_RUN": "maybe"})
        self.assertEqual(code, 2)
        self.assertEqual(fake.requests, [])
        self.assertIn("DAYS_AGO", err)
        self.assertIn("DRY_RUN", err)
        self.assertEqual(out, "")

    def test_identity_mismatch_exits_3(self) -> None:
        fake = FakeThreadsApi()
        fake.add("GET", "me", json_response({"id": "424242", "username": "someone_else"}))
        code, _, err = run_main(fake)
        self.assertEqual(code, 3)
        self.assertEqual(fake.paths(), ["me"])
        self.assertIn("THREADS_USER_ID", err)

    def test_incomplete_discovery_exits_1(self) -> None:
        fake = FakeThreadsApi()
        fake.add("GET", "me", json_response(load_fixture("me.json")))
        fake.add("GET", "me/threads", json_response({"data": [{"id": "1", "media_type": "X"}]}))
        code, out, _ = run_main(fake)
        self.assertEqual(code, 1)
        self.assertIn("Discovery: INCOMPLETE", out)

    def test_token_never_printed(self) -> None:
        fake = fixture_api()
        code, out, err = run_main(fake, {**ENV, "LOG_LEVEL": "DEBUG"})
        self.assertEqual(code, 0)
        self.assertNotIn(TOKEN, out + err)

        fake = FakeThreadsApi()
        body = {"error": {"message": f"Invalid token {TOKEN}", "code": 190}}
        fake.add("GET", "me", json_response(body, 401))
        code, out, err = run_main(fake, {**ENV, "LOG_LEVEL": "DEBUG"})
        self.assertEqual(code, 3)
        self.assertNotIn(TOKEN, out + err)


REMOVE_ENV = {**ENV, "DRY_RUN": "false"}


class CliRemovalTests(unittest.TestCase):
    def test_removal_run_with_partial_failure_exits_1(self) -> None:
        fake = fixture_api()
        ok = json_response({"success": True})
        fake.add("DELETE", "9000001", ok)
        fake.add("DELETE", "7000001", error_response(100, 400))
        for item in ("9000002", "9000003", "9000004"):
            fake.add("DELETE", item, ok)
        code, out, _ = run_main(fake, REMOVE_ENV)
        self.assertEqual(code, 1)
        self.assertIn("Mode: REMOVAL", out)
        self.assertIn("removed  post  9000001", out)
        self.assertIn("failed  reply  7000001", out)
        self.assertIn("reply: scanned=2 eligible=1 would_remove=1 removed=0 failed=1", out)

    def test_removal_unknown_outcome_exits_1_and_is_not_reported_removed(self) -> None:
        fake = fixture_api()
        fake.add("DELETE", "9000001", httpx.ReadTimeout("slow"), repeat=True)
        code, out, _ = run_main(fake, REMOVE_ENV)
        self.assertEqual(code, 1)
        self.assertEqual(fake.paths("DELETE"), ["9000001"])
        self.assertNotIn("removed  post", out)
        self.assertIn("unknown  post  9000001", out)
        self.assertIn("will rediscover next run", out)

    def test_cap_deferral_exits_0(self) -> None:
        fake = fixture_api()
        ok = json_response({"success": True})
        fake.add("DELETE", "9000001", ok)
        code, out, _ = run_main(fake, {**REMOVE_ENV, "MAX_DELETIONS_PER_RUN": "1"})
        self.assertEqual(code, 0)
        self.assertEqual(fake.paths("DELETE"), ["9000001"])
        self.assertIn("deferred  reply  7000001", out)

    def test_auth_loss_during_removal_exits_3_and_redacts_token(self) -> None:
        fake = fixture_api()
        body = {"error": {"message": f"token {TOKEN} expired", "code": 190}}
        fake.add("DELETE", "9000001", json_response(body, 401))
        code, out, err = run_main(fake, {**REMOVE_ENV, "LOG_LEVEL": "DEBUG"})
        self.assertEqual(code, 3)
        self.assertNotIn(TOKEN, out + err)
        self.assertIn("=== Summary ===", out)
        self.assertEqual(fake.paths("DELETE"), ["9000001"])

    def test_nothing_eligible_exits_0_without_mutation(self) -> None:
        fake = fixture_api(quota=False)
        code, out, _ = run_main(fake, {**REMOVE_ENV, "DAYS_AGO": "36500"})
        self.assertEqual(code, 0)
        self.assertEqual({r.method for r in fake.requests}, {"GET"})
        self.assertIn("Quota: not checked", out)


class CliSafetyWiringTests(unittest.TestCase):
    def _candidate(self) -> Candidate:
        return Candidate(Category.POST, "9000001", RUN_START - timedelta(days=400), None)

    def test_dry_run_client_blocks_mutation(self) -> None:
        candidate = self._candidate()
        for env in ({**ENV}, {**ENV, "DRY_RUN": "true"}):
            fake = FakeThreadsApi()

            def stub(cfg, client, started, out):  # type: ignore[no-untyped-def]
                client.remove(candidate)

            with mock.patch.object(main.cleanup, "run", stub):
                code, _, err = run_main(fake, env)
            self.assertEqual(code, 1)
            self.assertIn("Error:", err)
            self.assertEqual(fake.paths("DELETE"), [])
            self.assertEqual(fake.requests, [])

    def test_removal_mode_client_is_not_read_only(self) -> None:
        seen: list[bool] = []

        def stub(cfg, client, started, out):  # type: ignore[no-untyped-def]
            seen.append(client.read_only)
            raise ApiError("stop")

        with mock.patch.object(main.cleanup, "run", stub):
            run_main(FakeThreadsApi(), REMOVE_ENV)
        self.assertEqual(seen, [False])

    def test_log_records_are_redacted_by_handler_filter(self) -> None:
        def stub(cfg, client, started, out):  # type: ignore[no-untyped-def]
            logging.getLogger("threadsdelete.api").info("x %s", TOKEN)
            raise ApiError("stop")

        with mock.patch.object(main.cleanup, "run", stub):
            _, out, err = run_main(FakeThreadsApi(), {**ENV, "LOG_LEVEL": "DEBUG"})
        self.assertNotIn(TOKEN, out + err)
        self.assertIn("[REDACTED]", err)

    def test_httpx_request_logs_suppressed_at_debug(self) -> None:
        _, _, err = run_main(fixture_api(), {**ENV, "LOG_LEVEL": "DEBUG"})
        self.assertNotIn("HTTP Request:", err)

    def test_identity_read_failure_exits_1(self) -> None:
        bodyless = FakeThreadsApi()
        bodyless.add("GET", "me", json_response({"username": "x"}))
        down = FakeThreadsApi()
        down.add("GET", "me", error_response(2, 503), repeat=True)
        for fake in (bodyless, down):
            code, out, err = run_main(fake, {**ENV, "MAX_RETRY_WAIT_SECONDS": "0"})
            self.assertEqual(code, 1)
            self.assertIn("Error:", err)
            self.assertNotIn(TOKEN, out + err)


if __name__ == "__main__":
    unittest.main()
