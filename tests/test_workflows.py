import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from threadsdelete import config

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
CLEANUP = (WORKFLOWS / "cleanup-feed.yml").read_text()
CI = (WORKFLOWS / "ci.yml").read_text()
REFRESH = (WORKFLOWS / "refresh-token.yml").read_text()
ALL = {
    path.name: path.read_text()
    for path in sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
}


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
                self.assertEqual(
                    value,
                    "${{ (github.event_name == 'workflow_dispatch' && "
                    "inputs.dry_run == 'true') && 'true' || vars.DRY_RUN }}",
                )
            elif key != "THREADS_ACCESS_TOKEN":
                self.assertEqual(value, f"${{{{ vars.{key} }}}}", key)
        self.assertEqual(set(mapping), set(config.ENV_KEYS))
        self.assertEqual(CLEANUP.count("secrets."), 1)

    def test_cleanup_uses_same_entry_point_and_preserves_status(self) -> None:
        run_step = CLEANUP.split("- name: Run cleanup")[1].split("- name:")[0]
        self.assertIn("shell: bash", run_step)
        commands = re.findall(r"(?m)^\s+run: (.+)$", run_step)
        self.assertEqual(len(commands), 1)
        command = commands[0]
        self.assertIn("uv run main.py", command)
        for status in (0, 1, 2, 3):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                result = subprocess.run(
                    [
                        "bash",
                        "--noprofile",
                        "--norc",
                        "-e",
                        "-o",
                        "pipefail",
                        "-c",
                        f"uv() {{ printf 'synthetic cleanup output\\n'; return {status}; }}\n"
                        + command,
                    ],
                    cwd=directory,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, status, result.stderr)
                self.assertIn("synthetic cleanup output", result.stdout)
                self.assertIn(
                    "synthetic cleanup output", Path(directory, "cleanup.log").read_text()
                )
        summary_step = CLEANUP.split("- name: Write summary")[1]
        self.assertIn("if: always()", summary_step)
        self.assertIn("GITHUB_STEP_SUMMARY", summary_step)
        self.assertIn("=== Summary ===", summary_step)
        self.assertIn("tail -n 20", summary_step)
        self.assertIn("No cleanup log was produced.", summary_step)


class SharedWorkflowTests(unittest.TestCase):
    def test_all_actions_pinned_to_full_sha(self) -> None:
        for name, text in ALL.items():
            with self.subTest(name=name):
                uses = re.findall(r"(?m)^\s*(?:- )?uses:\s*(\S+)", text)
                self.assertTrue(uses)
                for ref in uses:
                    self.assertRegex(ref, r"@[0-9a-f]{40}$", ref)

    def test_no_expressions_inside_run_scripts(self) -> None:
        for name, text in ALL.items():
            with self.subTest(name=name):
                for block in re.findall(
                    r"(?ms)^\s+run:.*?(?=^\s+(?:- |env:|shell:|with:|if:)|\Z)", text
                ):
                    self.assertNotIn("${{", block)

    def test_no_pull_request_target_in_any_workflow(self) -> None:
        for name, text in ALL.items():
            self.assertNotIn("pull_request_target", text, name)

    def test_every_workflow_is_covered(self) -> None:
        self.assertLessEqual({"ci.yml", "cleanup-feed.yml", "refresh-token.yml"}, set(ALL))

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


class RefreshWorkflowTests(unittest.TestCase):
    def test_schedule_dispatch_permissions_concurrency_and_timeout(self) -> None:
        self.assertIn("- cron: '17 6 1,15 * *'", REFRESH)
        self.assertRegex(REFRESH, r"(?m)^  workflow_dispatch:\s*$")
        self.assertNotIn("inputs:", REFRESH)
        self.assertRegex(REFRESH, r"(?m)^permissions:\n  contents: read$")
        self.assertIn("group: refresh-token", REFRESH)
        self.assertRegex(REFRESH, r"(?m)^  cancel-in-progress: false$")
        self.assertNotIn("cancel-in-progress: true", REFRESH)
        self.assertRegex(REFRESH, r"(?m)^    timeout-minutes: 5$")
        self.assertIn("runs-on: ubuntu-latest", REFRESH)
        self.assertNotIn("pull_request", REFRESH)

    def test_single_step_runs_script_with_exact_env(self) -> None:
        self.assertEqual(
            env_mappings(REFRESH),
            {
                "THREADS_ACCESS_TOKEN": "${{ secrets.THREADS_ACCESS_TOKEN }}",
                "THREADS_USER_ID": "${{ vars.THREADS_USER_ID }}",
                "GH_TOKEN": "${{ secrets.SECRETS_WRITE_TOKEN }}",
                "GH_REPO": "${{ github.repository }}",
            },
        )
        self.assertEqual(
            re.findall(r"(?m)^\s+(?:- )?run:\s*(.+)$", REFRESH), ["./scripts/refresh-token.sh"]
        )
        self.assertIn("shell: bash", REFRESH.split("- name: Refresh token")[1])
        for absent in ("GITHUB_ACTIONS", "setup-uv", "uv ", "python"):
            self.assertNotIn(absent, REFRESH)

    def test_checkout_pinned_like_other_workflows_without_credentials(self) -> None:
        pattern = r"(?m)^\s*(?:- )?uses:\s*(\S+)"
        uses = re.findall(pattern, REFRESH)
        cleanup_checkout = [
            u for u in re.findall(pattern, CLEANUP) if u.startswith("actions/checkout@")
        ]
        self.assertEqual(uses, cleanup_checkout)
        self.assertIn("persist-credentials: false", REFRESH)

    def test_only_named_secrets_used(self) -> None:
        self.assertEqual(
            sorted(re.findall(r"secrets\.(\w+)", REFRESH)),
            ["SECRETS_WRITE_TOKEN", "THREADS_ACCESS_TOKEN"],
        )


if __name__ == "__main__":
    unittest.main()
