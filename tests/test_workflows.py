import re
import unittest
from pathlib import Path

from threadsdelete import config

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
CLEANUP = (WORKFLOWS / "cleanup-feed.yml").read_text()
CI = (WORKFLOWS / "ci.yml").read_text()


def env_mappings(text: str) -> dict[str, str]:
    return {
        match.group(1): match.group(2)
        for match in re.finditer(r"^\s+([A-Z][A-Z_]+):\s*(\$\{\{.*\}\})\s*$", text, re.MULTILINE)
    }


class CleanupWorkflowTests(unittest.TestCase):
    def test_cleanup_schedule_dispatch_and_concurrency(self) -> None:
        self.assertIn("- cron: '0 5 * * 5'", CLEANUP)
        self.assertRegex(CLEANUP, r"(?m)^  workflow_dispatch:")
        self.assertRegex(CLEANUP, r"(?m)^  cancel-in-progress: false$")
        self.assertNotIn("cancel-in-progress: true", CLEANUP)
        self.assertRegex(CLEANUP, r"(?m)^permissions:\n  contents: read$")
        self.assertRegex(CLEANUP, r"(?m)^    timeout-minutes: \d+$")
        self.assertNotIn("pull_request", CLEANUP)

    def test_manual_dispatch_defaults_to_preview(self) -> None:
        self.assertRegex(
            CLEANUP, r"(?s)dry_run:.*options:.*- 'true'.*- 'variable'.*default: 'true'"
        )

    def test_cleanup_maps_every_config_key_without_inline_defaults(self) -> None:
        mapping = env_mappings(CLEANUP)
        for key in config.ENV_KEYS:
            self.assertIn(key, mapping, key)
        self.assertEqual(mapping["THREADS_ACCESS_TOKEN"], "${{ secrets.THREADS_ACCESS_TOKEN }}")
        for key, value in mapping.items():
            if key == "DRY_RUN":
                self.assertIn("github.event_name == 'workflow_dispatch'", value)
                self.assertTrue(value.endswith("|| vars.DRY_RUN }}"))
            elif key != "THREADS_ACCESS_TOKEN":
                self.assertEqual(value, f"${{{{ vars.{key} }}}}", key)
        self.assertEqual(CLEANUP.count("secrets."), 1)

    def test_cleanup_uses_same_entry_point_and_preserves_status(self) -> None:
        self.assertIn("run: uv run main.py 2>&1 | tee cleanup.log", CLEANUP)
        run_step = CLEANUP.split("- name: Run cleanup")[1].split("- name:")[0]
        self.assertIn("shell: bash", run_step)
        summary_step = CLEANUP.split("- name: Write summary")[1]
        self.assertIn("if: always()", summary_step)
        self.assertIn("GITHUB_STEP_SUMMARY", summary_step)
        self.assertIn("=== Summary ===", summary_step)
        self.assertIn("tail -n 20", summary_step)
        self.assertIn("No cleanup log was produced.", summary_step)

    def test_no_expressions_inside_run_scripts(self) -> None:
        for text in (CLEANUP, CI):
            for block in re.findall(
                r"(?ms)^\s+run:.*?(?=^\s+(?:- |env:|shell:|with:|if:)|\Z)", text
            ):
                self.assertNotIn("${{", block)


class SharedWorkflowTests(unittest.TestCase):
    def test_all_actions_pinned_to_full_sha(self) -> None:
        for text in (CLEANUP, CI):
            uses = re.findall(r"(?m)^\s*(?:- )?uses:\s*(\S+)", text)
            self.assertTrue(uses)
            for ref in uses:
                self.assertRegex(ref, r"@[0-9a-f]{40}$", ref)

    def test_ci_runs_offline_checks_without_secrets(self) -> None:
        for command in (
            "uv sync --locked",
            "uv run mypy threadsdelete main.py",
            "uv run ruff check .",
            "uv run ruff format --check .",
            "uv run python -m unittest discover -s tests -v",
            "uv run python -m compileall -q threadsdelete main.py",
            "uv run main.py --help",
        ):
            self.assertIn(f"run: {command}", CI)
        self.assertNotIn("secrets.", CI)
        self.assertNotIn("pull_request_target", CI)
        self.assertNotIn("--fix", CI)
        self.assertRegex(CI, r"(?m)^permissions:\n  contents: read$")


if __name__ == "__main__":
    unittest.main()
