"""Offline tests for scripts/refresh-token.sh, run against fake curl and gh."""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any

import tests  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "refresh-token.sh"
MODES = ("local", "actions")
PAT = "FAKE-PAT-cccc3333"
UNSET: Any = object()

OLD = "FAKE-OLD-TOKEN-aaaa1111"
NEW = "FAKE-NEW-TOKEN-bbbb2222"
ENV_TEXT = (
    "# synthetic test file\n"
    "DRY_RUN=true\n"
    f"THREADS_ACCESS_TOKEN={OLD}\n"
    "THREADS_USER_ID=1000001\n"
    "DAYS_AGO=90\n"
)
REFRESH_URL = "https://graph.threads.com/refresh_access_token?grant_type=th_refresh_token"
ME_URL = "https://graph.threads.com/v1.0/me?fields=id"

FAKE_CURL = """#!{py}
import json, sys
argv = sys.argv[1:]
stdin = sys.stdin.read()
endpoint = "unknown"
if any("refresh_access_token" in a for a in argv):
    endpoint = "refresh"
elif any("/v1.0/me" in a for a in argv):
    endpoint = "me"
with open({calls!r}, "a") as f:
    rec = {{"tool": "curl", "args": argv, "stdin": stdin, "endpoint": endpoint}}
    f.write(json.dumps(rec) + "\\n")
try:
    with open({resp!r} + endpoint + ".json") as f:
        r = json.load(f)
except OSError:
    sys.exit(99)
if r.get("exit", 0) != 0:
    sys.exit(r["exit"])
for flag in ("--output", "-o"):
    if flag in argv:
        with open(argv[argv.index(flag) + 1], "w") as f:
            f.write(r["body"])
        break
for flag in ("--write-out", "-w"):
    if flag in argv:
        sys.stdout.write(str(r["status"]))
        break
"""

FAKE_GH = """#!{py}
import json, sys
argv = sys.argv[1:]
stdin = sys.stdin.read()
with open({calls!r}, "a") as f:
    f.write(json.dumps({{"tool": "gh", "args": argv, "stdin": stdin}}) + "\\n")
try:
    with open({resp!r} + "gh.json") as f:
        r = json.load(f)
except OSError:
    r = {{}}
if argv[:2] == ["secret", "list"]:
    print("THREADS_ACCESS_TOKEN\\t2026-01-01T00:00:00Z")
    sys.exit(r.get("list_exit", 0))
if argv[:2] == ["secret", "set"]:
    sys.exit(r.get("set_exit", 0))
sys.exit(99)
"""

DEFAULT_RESPONSES: dict[str, dict[str, Any]] = {
    "refresh": {
        "status": 200,
        "body": json.dumps({"access_token": NEW, "token_type": "bearer", "expires_in": 5183944}),
        "exit": 0,
    },
    "me": {"status": 200, "body": json.dumps({"id": "1000001"}), "exit": 0},
}


def resp(status: int, body: str) -> dict[str, Any]:
    return {"status": status, "body": body, "exit": 0}


def curl_exit(code: int) -> dict[str, Any]:
    return {"status": 0, "body": "", "exit": code}


class Result:
    def __init__(self, proc: subprocess.CompletedProcess[str], calls: list[dict[str, Any]]):
        self.code = proc.returncode
        self.out = proc.stdout
        self.err = proc.stderr
        self.calls = calls

    def curls(self) -> list[dict[str, Any]]:
        return [c for c in self.calls if c["tool"] == "curl"]


class Harness(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def prepare(
        self,
        mode: str = "local",
        env_text: Any = UNSET,
        responses: dict[str, dict[str, Any]] | None = None,
        extra_env: dict[str, str | None] | None = None,
        env_mode: int = 0o644,
        before_run: Callable[[], None] | None = None,
    ) -> Result:
        tmp = self.tmp
        for d in ("scripts", "home", "tmp", "xdg", "fakebin", "responses"):
            (tmp / d).mkdir(exist_ok=True)
        script = tmp / "scripts" / "refresh-token.sh"
        shutil.copyfile(SCRIPT, script)
        script.chmod(0o755)
        jq = shutil.which("jq")
        if jq is None:
            self.fail(
                "jq must be on PATH to run tests/test_refresh_token.py (see CLAUDE.md Commands)"
            )
        jq_link = tmp / "fakebin" / "jq"
        if not jq_link.exists():
            jq_link.symlink_to(jq)
        calls = tmp / "calls.jsonl"
        resp_dir = str(tmp / "responses") + "/"
        for name, template in (("curl", FAKE_CURL), ("gh", FAKE_GH)):
            path = tmp / "fakebin" / name
            path.write_text(template.format(py=sys.executable, calls=str(calls), resp=resp_dir))
            path.chmod(0o755)
        merged = dict(DEFAULT_RESPONSES)
        merged.update(responses or {})
        for name, value in merged.items():
            (tmp / "responses" / f"{name}.json").write_text(json.dumps(value))
        env_file = tmp / ".env"
        if env_text is UNSET:
            env_text = ENV_TEXT if mode == "local" else None
        if env_file.exists():
            env_file.unlink()
        for leftover in tmp.glob(".env.*"):
            leftover.unlink()
        if env_text is not None:
            env_file.write_text(env_text)
            env_file.chmod(env_mode)
        path_var = f"{tmp / 'fakebin'}:/usr/bin:/bin"
        env = {
            "PATH": path_var,
            "HOME": str(tmp / "home"),
            "TMPDIR": str(tmp / "tmp"),
            "XDG_CONFIG_HOME": str(tmp / "xdg"),
        }
        if mode == "actions":
            env.update(
                {
                    "GITHUB_ACTIONS": "true",
                    "THREADS_ACCESS_TOKEN": OLD,
                    "THREADS_USER_ID": "1000001",
                    "GH_TOKEN": PAT,
                    "GH_REPO": "example-owner/threadsdelete",
                }
            )
        for k, v in (extra_env or {}).items():
            if v is None:
                env.pop(k, None)
            else:
                env[k] = v
        self.assertEqual(shutil.which("curl", path=path_var), str(tmp / "fakebin" / "curl"))
        self.assertEqual(shutil.which("gh", path=path_var), str(tmp / "fakebin" / "gh"))
        bash = shutil.which("bash", path=path_var)
        assert bash is not None
        if before_run is not None:
            before_run()
        proc = subprocess.run(
            [bash, str(script)],
            env=env,
            cwd=tmp / "home",
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        records: list[dict[str, Any]] = []
        if calls.exists():
            records = [json.loads(line) for line in calls.read_text().splitlines()]
            calls.unlink()
        return Result(proc, records)

    def env_bytes(self) -> bytes | None:
        p = self.tmp / ".env"
        return p.read_bytes() if p.exists() else None

    def assert_recovery_text(self, r: Result) -> None:
        self.assertIn("docs/META_SETUP.md", r.err)
        self.assertIn("cleanup preview", r.err)
        self.assertNotIn("run again", r.err.lower())

    @staticmethod
    def mask_lines(r: Result) -> list[str]:
        return [x for x in r.out.splitlines() if x.startswith("::add-mask::")]

    def assert_no_env_temp(self) -> None:
        self.assertEqual(list(self.tmp.glob(".env.*")), [])

    def assert_unchanged(self, mode: str, before: bytes | None, r: Result) -> None:
        if mode == "local":
            self.assertEqual(self.env_bytes(), before)
            self.assert_no_env_temp()
        else:
            self.assertEqual([c for c in r.calls if c["args"][:2] == ["secret", "set"]], [])
            self.assertIsNone(self.env_bytes())


class ScriptFileTests(unittest.TestCase):
    def test_script_is_executable_and_strict(self) -> None:
        self.assertTrue(os.access(SCRIPT, os.X_OK))
        self.assertIn("set -euo pipefail", SCRIPT.read_text())


class LocalRefreshTests(Harness):
    def test_success_rewrites_only_token_line(self) -> None:
        r = self.prepare()
        self.assertEqual(r.code, 0, r.err)
        self.assertIn("Token refreshed and saved to .env", r.out)
        old_lines = ENV_TEXT.splitlines()
        new_lines = (self.tmp / ".env").read_text().splitlines()
        expected = [
            f"THREADS_ACCESS_TOKEN={NEW}" if x.startswith("THREADS_ACCESS_TOKEN=") else x
            for x in old_lines
        ]
        self.assertEqual(new_lines, expected)
        self.assertEqual(stat.S_IMODE((self.tmp / ".env").stat().st_mode), 0o600)
        curls = r.curls()
        self.assertEqual(
            [(c["endpoint"], c["stdin"]) for c in curls], [("refresh", OLD), ("me", NEW)]
        )
        self.assertEqual([c for c in r.calls if c["tool"] == "gh"], [])
        self.assertNotIn("::add-mask::", r.out)
        for text in (r.out, r.err):
            self.assertNotIn(OLD, text)
            self.assertNotIn(NEW, text)
        self.assertEqual(list((self.tmp / "tmp").iterdir()), [])
        self.assert_no_env_temp()

    def test_missing_final_newline_is_added(self) -> None:
        r = self.prepare(env_text=ENV_TEXT.rstrip("\n"))
        self.assertEqual(r.code, 0, r.err)
        text = (self.tmp / ".env").read_text()
        self.assertTrue(text.endswith("\n"))
        self.assertIn(f"THREADS_ACCESS_TOKEN={NEW}", text.splitlines())

    def test_environment_values_are_ignored(self) -> None:
        r = self.prepare(
            extra_env={
                "THREADS_ACCESS_TOKEN": "FAKE-ENV-TOKEN-dddd4444",
                "THREADS_USER_ID": "2000002",
            }
        )
        self.assertEqual(r.code, 0, r.err)
        self.assertEqual(r.curls()[0]["stdin"], OLD)
        self.assertNotIn("FAKE-ENV-TOKEN-dddd4444", json.dumps(r.calls))

    def test_invalid_env_file_fails_before_network(self) -> None:
        tok = f"THREADS_ACCESS_TOKEN={OLD}\n"
        uid = "THREADS_USER_ID=1000001\n"
        cases = {
            "no env": None,
            "no token": uid,
            "two tokens": tok + tok + uid,
            "two tokens, empty second": tok + "THREADS_ACCESS_TOKEN=\n" + uid,
            "empty token": "THREADS_ACCESS_TOKEN=\n" + uid,
            "space": "THREADS_ACCESS_TOKEN=FAKE OLD\n" + uid,
            "quoted": 'THREADS_ACCESS_TOKEN="FAKE-OLD-TOKEN-aaaa1111"\n' + uid,
            "cr": f"THREADS_ACCESS_TOKEN={OLD}\r\n" + uid,
            "no user": tok,
            "two users": tok + uid + uid,
            "two users, empty second": tok + uid + "THREADS_USER_ID=\n",
            "empty user": tok + "THREADS_USER_ID=\n",
            "bad user": tok + "THREADS_USER_ID=12a4\n",
        }
        for name, text in cases.items():
            with self.subTest(case=name):
                if (self.tmp / ".env").exists():
                    (self.tmp / ".env").unlink()
                r = self.prepare(env_text=text)
                self.assertEqual(r.code, 2, r.err)
                self.assertEqual(r.calls, [])
                self.assertEqual(self.env_bytes(), None if text is None else text.encode())
                self.assertIn("Nothing was changed", r.err)
                self.assertNotIn("may have changed", r.err)
                self.assertNotIn(OLD, r.err)
                if name.startswith("two "):
                    self.assertIn("more than one", r.err)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores file modes")
    def test_unwritable_env_fails_before_network(self) -> None:
        r = self.prepare(env_mode=0o444)
        self.assertEqual(r.code, 2, r.err)
        self.assertEqual(r.calls, [])
        self.assertEqual(self.env_bytes(), ENV_TEXT.encode())

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores directory modes")
    def test_unwritable_repository_root_fails_before_network(self) -> None:
        def lock_root() -> None:
            self.tmp.chmod(0o555)

        # Registered last so it runs first, before TemporaryDirectory removal.
        self.addCleanup(self.tmp.chmod, 0o755)
        r = self.prepare(before_run=lock_root)
        self.assertEqual(r.code, 2, r.err)
        self.assertEqual(r.calls, [])
        self.assertEqual(self.env_bytes(), ENV_TEXT.encode())
        self.assertIn("Nothing was changed", r.err)


class BothDestinationTests(Harness):
    def test_refresh_failures_stop_before_any_other_call(self) -> None:
        cases: dict[str, dict[str, Any]] = {
            "oauth": resp(
                400,
                json.dumps(
                    {"error_type": "OAuthException", "code": 190, "error_message": "Invalid token"}
                ),
            ),
            "graph": resp(
                400,
                json.dumps(
                    {
                        "error": {
                            "message": "x",
                            "type": "OAuthException",
                            "code": 190,
                            "error_subcode": 460,
                        }
                    }
                ),
            ),
            "truncated": resp(200, '{"access_token": '),
            "array": resp(200, "[]"),
            "no token": resp(200, json.dumps({"token_type": "bearer", "expires_in": 5183944})),
            "newline": resp(200, '{"access_token": "FAKE-NEW-TOKEN\\nbbbb2222"}'),
            "empty": resp(200, '{"access_token": ""}'),
            "curl 28": curl_exit(28),
            "curl 7": curl_exit(7),
        }
        for mode in MODES:
            for name, response in cases.items():
                with self.subTest(mode=mode, case=name):
                    before = ENV_TEXT.encode()
                    r = self.prepare(mode=mode, responses={"refresh": response})
                    self.assertEqual(r.code, 1, r.err)
                    self.assertEqual([c["endpoint"] for c in r.curls()], ["refresh"])
                    self.assertEqual(len([c for c in r.calls if c["tool"] == "curl"]), 1)
                    if mode == "actions":
                        self.assertEqual(
                            [c["args"] for c in r.calls if c["tool"] == "gh"], [["secret", "list"]]
                        )
                    self.assert_unchanged(mode, before, r)
                    self.assertIn("may have changed", r.err)
                    self.assert_recovery_text(r)
                    self.assertNotIn("::add-mask::", r.out)
                    if name in ("oauth", "graph"):
                        self.assertIn("HTTP 400", r.err)
                        self.assertIn("190", r.err)
                    if name == "graph":
                        self.assertIn("460", r.err)
                    if name.startswith("curl"):
                        self.assertIn(f"curl exit {name.split()[1]}", r.err)

    def test_error_message_text_is_never_printed(self) -> None:
        leak = (
            "Invalid token FAKE-LEAK-TOKEN-eeee5555 "
            "see https://graph.threads.com/x?access_token=FAKE-LEAK-TOKEN-eeee5555"
        )
        bodies = [
            {"error_type": "OAuthException", "code": 190, "error_message": leak},
            {"error": {"message": leak, "error_user_msg": leak, "code": 190}},
            {"error": {"code": 190, "error_subcode": "FAKE-LEAK-TOKEN-eeee5555"}},
            {"error": {"code": 190, "error_subcode": -1}},
            {"error": {"code": 190, "error_subcode": "123456"}},
            {"error": {"code": 190, "error_subcode": 2.5}},
        ]
        for mode in MODES:
            for i, body in enumerate(bodies):
                with self.subTest(mode=mode, shape=i):
                    r = self.prepare(mode=mode, responses={"refresh": resp(400, json.dumps(body))})
                    combined = r.out + r.err
                    self.assertNotIn("FAKE-LEAK-TOKEN", combined)
                    self.assertNotIn("access_token=", combined)
                    self.assertIn("190", r.err)
                    self.assertNotIn("subcode", r.err)

    def test_verify_failures_leave_destination_unchanged(self) -> None:
        cases: dict[str, dict[str, Any]] = {
            "other id": resp(200, json.dumps({"id": "2000002"})),
            "no id": resp(200, "{}"),
            "numeric id": resp(200, json.dumps({"id": 1000001})),
            "http 400": resp(400, json.dumps({"error": {"code": 190}})),
            "not json": resp(200, "not json"),
            "curl 28": curl_exit(28),
        }
        for mode in MODES:
            for name, response in cases.items():
                with self.subTest(mode=mode, case=name):
                    before = ENV_TEXT.encode()
                    r = self.prepare(mode=mode, responses={"me": response})
                    self.assertEqual(r.code, 1, r.err)
                    self.assertEqual(len(r.curls()), 2)
                    self.assert_unchanged(mode, before, r)
                    self.assertIn("may have changed", r.err)
                    self.assert_recovery_text(r)
                    if name in ("other id", "no id", "numeric id"):
                        self.assertIn("differs", r.err)
                        self.assertNotIn("2000002", r.err)
                        self.assertNotIn("1000001", r.err)
                    if mode == "local":
                        self.assertNotIn(NEW, r.out + r.err)
                    else:
                        self.assertEqual(self.mask_lines(r), [f"::add-mask::{NEW}"])
                        rest = [
                            x for x in (r.out + r.err).splitlines() if x != f"::add-mask::{NEW}"
                        ]
                        self.assertFalse([x for x in rest if NEW in x])

    def test_tokens_never_in_arguments(self) -> None:
        for mode in MODES:
            with self.subTest(mode=mode):
                r = self.prepare(mode=mode)
                self.assertEqual(r.code, 0, r.err)
                for call in r.calls:
                    for arg in call["args"]:
                        for secret in (OLD, NEW, PAT):
                            self.assertNotIn(secret, arg)
                curls = r.curls()
                self.assertEqual(len(curls), 2)
                for c in curls:
                    args = c["args"]
                    self.assertIn("--max-time", args)
                    self.assertEqual(args[args.index("--data-urlencode") + 1], "access_token@-")
                self.assertIn(REFRESH_URL, curls[0]["args"])
                self.assertIn(ME_URL, curls[1]["args"])
                self.assertNotIn(OLD, r.out + r.err)


class ActionsRefreshTests(Harness):
    def test_success_sets_secret_from_stdin(self) -> None:
        r = self.prepare(mode="actions")
        self.assertEqual(r.code, 0, r.err)
        shape = [
            (c["tool"], c["args"][:3] if c["tool"] == "gh" else c["endpoint"], c["stdin"])
            for c in r.calls
        ]
        self.assertEqual(
            shape,
            [
                ("gh", ["secret", "list"], ""),
                ("curl", "refresh", OLD),
                ("curl", "me", NEW),
                ("gh", ["secret", "set", "THREADS_ACCESS_TOKEN"], NEW),
            ],
        )
        self.assertIn("Token refreshed and saved to the repository secret", r.out)
        lines = [x for x in (r.out + r.err).splitlines() if NEW in x]
        self.assertEqual(lines, [f"::add-mask::{NEW}"])
        for secret in (OLD, PAT):
            self.assertNotIn(secret, r.out + r.err)
        self.assertIsNone(self.env_bytes())
        self.assertEqual(list((self.tmp / "tmp").iterdir()), [])

    def test_env_file_is_ignored_in_actions(self) -> None:
        text = "THREADS_ACCESS_TOKEN=FAKE-ENV-TOKEN-dddd4444\nTHREADS_USER_ID=1000001\n"
        r = self.prepare(mode="actions", env_text=text)
        self.assertEqual(r.code, 0, r.err)
        self.assertEqual(r.curls()[0]["stdin"], OLD)
        self.assertEqual(self.env_bytes(), text.encode())
        self.assertNotIn("FAKE-ENV-TOKEN-dddd4444", json.dumps(r.calls))

    def test_missing_input_fails_before_any_call(self) -> None:
        names = ("THREADS_ACCESS_TOKEN", "THREADS_USER_ID", "GH_TOKEN", "GH_REPO")
        cases: list[tuple[str, str | None]] = [(n, v) for n in names for v in (None, "")]
        cases.append(("THREADS_USER_ID", "12a4"))
        cases.append(("THREADS_ACCESS_TOKEN", "FAKE OLD"))
        cases.append(("THREADS_ACCESS_TOKEN", "FAKE-OLD\r"))
        for name, value in cases:
            with self.subTest(name=name, value=value):
                r = self.prepare(mode="actions", extra_env={name: value})
                self.assertEqual(r.code, 2, r.err)
                self.assertEqual(r.calls, [])
                self.assertIn("Nothing was changed", r.err)
                self.assertIn(name, r.err)

    def test_failed_secret_list_stops_before_refresh(self) -> None:
        r = self.prepare(mode="actions", responses={"gh": {"list_exit": 1}})
        self.assertEqual(r.code, 2, r.err)
        self.assertEqual([c["args"] for c in r.calls], [["secret", "list"]])
        self.assertIn("Nothing was changed", r.err)

    def test_failed_secret_set_exits_non_zero(self) -> None:
        r = self.prepare(mode="actions", responses={"gh": {"set_exit": 1}})
        self.assertEqual(r.code, 1, r.err)
        self.assertIn("may have changed", r.err)
        self.assertIn("gh secret set failed", r.err)
        lines = [x for x in (r.out + r.err).splitlines() if NEW in x]
        self.assertEqual(lines, [f"::add-mask::{NEW}"])


if __name__ == "__main__":
    unittest.main()
