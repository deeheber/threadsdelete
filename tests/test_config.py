import re
import unittest
from pathlib import Path

from threadsdelete import config
from threadsdelete.config import ConfigError, load_config

TOKEN = "TOKENVALUE-not-a-real-secret"
BASE = {"THREADS_ACCESS_TOKEN": TOKEN, "THREADS_USER_ID": "1234567"}


def env(**overrides: str) -> dict[str, str]:
    return {**BASE, **overrides}


class DefaultsTests(unittest.TestCase):
    def test_defaults_apply_when_optional_keys_missing_or_empty(self) -> None:
        empty = {key: "" for key in config.ENV_KEYS if key not in BASE}
        for source in (dict(BASE), {**BASE, **empty}, {**BASE, "DRY_RUN": "  "}):
            cfg = load_config(source)
            self.assertIs(cfg.dry_run, True)
            self.assertEqual(cfg.days_ago, config.DEFAULT_DAYS_AGO)
            self.assertEqual(cfg.log_level, config.DEFAULT_LOG_LEVEL)
            self.assertEqual(cfg.api_version, config.DEFAULT_API_VERSION)
            self.assertEqual(cfg.max_deletions_per_run, config.DEFAULT_MAX_DELETIONS_PER_RUN)
            self.assertEqual(cfg.http_timeout_seconds, config.DEFAULT_HTTP_TIMEOUT_SECONDS)
            self.assertEqual(cfg.max_read_retries, config.DEFAULT_MAX_READ_RETRIES)
            self.assertEqual(cfg.max_retry_wait_seconds, config.DEFAULT_MAX_RETRY_WAIT_SECONDS)

    def test_booleans_accept_only_true_false_any_case(self) -> None:
        self.assertIs(load_config(env(DRY_RUN="TRUE")).dry_run, True)
        self.assertIs(load_config(env(DRY_RUN=" False ")).dry_run, False)
        for bad in ("yes", "1", "on", "0", "no"):
            with self.assertRaises(ConfigError, msg=bad) as raised:
                load_config(env(DRY_RUN=bad))
            self.assertIn("DRY_RUN", raised.exception.problems[0])

    def test_invalid_values_are_all_reported(self) -> None:
        with self.assertRaises(ConfigError) as raised:
            load_config(
                env(
                    DRY_RUN="maybe",
                    DAYS_AGO="ninety",
                    LOG_LEVEL="LOUD",
                    THREADS_API_VERSION="1.0",
                    THREADS_USER_ID="abc",
                )
            )
        text = "\n".join(raised.exception.problems)
        for key in ("DRY_RUN", "DAYS_AGO", "LOG_LEVEL", "THREADS_API_VERSION", "THREADS_USER_ID"):
            self.assertIn(key, text)
        self.assertEqual(len(raised.exception.problems), 5)

    def test_missing_required_keys_are_errors(self) -> None:
        with self.assertRaises(ConfigError) as raised:
            load_config({"THREADS_ACCESS_TOKEN": "  "})
        text = "\n".join(raised.exception.problems)
        self.assertIn("THREADS_ACCESS_TOKEN", text)
        self.assertIn("THREADS_USER_ID", text)

    def test_integer_and_float_bounds(self) -> None:
        for key, bad in (
            ("DAYS_AGO", "-1"),
            ("DAYS_AGO", "+5"),
            ("DAYS_AGO", "1e3"),
            ("DAYS_AGO", "1.0"),
            ("DAYS_AGO", str(config.MAX_DAYS_AGO + 1)),
            ("MAX_DELETIONS_PER_RUN", "-3"),
            ("MAX_READ_RETRIES", "2.5"),
            ("HTTP_TIMEOUT_SECONDS", "0"),
            ("HTTP_TIMEOUT_SECONDS", "1e2"),
            ("MAX_RETRY_WAIT_SECONDS", "-1"),
        ):
            with self.assertRaises(ConfigError, msg=f"{key}={bad}"):
                load_config(env(**{key: bad}))
        cfg = load_config(
            env(
                DAYS_AGO="0",
                MAX_DELETIONS_PER_RUN="0",
                MAX_READ_RETRIES="0",
                MAX_RETRY_WAIT_SECONDS="0",
                HTTP_TIMEOUT_SECONDS="0.5",
            )
        )
        self.assertEqual(cfg.days_ago, 0)
        self.assertEqual(cfg.max_deletions_per_run, 0)
        self.assertEqual(cfg.max_read_retries, 0)
        self.assertEqual(cfg.max_retry_wait_seconds, 0.0)
        self.assertEqual(cfg.http_timeout_seconds, 0.5)
        self.assertEqual(load_config(env(DAYS_AGO=str(config.MAX_DAYS_AGO))).days_ago, 36500)

    def test_log_level_is_case_insensitive_and_uppercased(self) -> None:
        self.assertEqual(load_config(env(LOG_LEVEL="debug")).log_level, "DEBUG")

    def test_error_messages_and_repr_never_contain_token(self) -> None:
        cfg = load_config(env())
        self.assertNotIn(TOKEN, repr(cfg))
        self.assertEqual(cfg.access_token, TOKEN)
        bad = {"THREADS_ACCESS_TOKEN": TOKEN, "THREADS_USER_ID": TOKEN, "DAYS_AGO": TOKEN}
        with self.assertRaises(ConfigError) as raised:
            load_config(bad)
        self.assertNotIn(TOKEN, str(raised.exception))
        self.assertNotIn(TOKEN, "\n".join(raised.exception.problems))


class EnvSampleTests(unittest.TestCase):
    def test_env_sample_matches_config(self) -> None:
        sample = Path(__file__).resolve().parent.parent / ".env.sample"
        values: dict[str, str] = {}
        for line in sample.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                key, _, value = line.partition("=")
                values[key] = value
        self.assertEqual(set(values), set(config.ENV_KEYS))
        self.assertEqual(len(values), len(config.ENV_KEYS))
        self.assertEqual(values["THREADS_ACCESS_TOKEN"], "replace-with-your-long-lived-user-token")
        self.assertEqual(values["THREADS_USER_ID"], "replace-with-your-numeric-threads-user-id")
        non_secret = {k: v for k, v in values.items() if not k.startswith("THREADS_ACC")}
        non_secret.pop("THREADS_USER_ID")
        cfg = load_config({**BASE, **non_secret})
        self.assertIs(cfg.dry_run, config.DEFAULT_DRY_RUN)
        self.assertEqual(cfg.days_ago, config.DEFAULT_DAYS_AGO)
        self.assertEqual(cfg.log_level, config.DEFAULT_LOG_LEVEL)
        self.assertEqual(cfg.api_version, config.DEFAULT_API_VERSION)
        self.assertEqual(cfg.max_deletions_per_run, config.DEFAULT_MAX_DELETIONS_PER_RUN)
        self.assertEqual(cfg.http_timeout_seconds, config.DEFAULT_HTTP_TIMEOUT_SECONDS)
        self.assertEqual(cfg.max_read_retries, config.DEFAULT_MAX_READ_RETRIES)
        self.assertEqual(cfg.max_retry_wait_seconds, config.DEFAULT_MAX_RETRY_WAIT_SECONDS)
        self.assertIsNotNone(re.match(r"^v[0-9]+\.[0-9]+$", values["THREADS_API_VERSION"]))


if __name__ == "__main__":
    unittest.main()
