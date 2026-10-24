import contextlib
import io
import os
import unittest
from datetime import UTC, datetime
from unittest import mock

import main
from tests.fakes import FakeThreadsApi, fixture_api, json_response, load_fixture

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


if __name__ == "__main__":
    unittest.main()
