# Review: build/2026-10-24
Round: 2

Verdict: **APPROVED**

Scope: the whole branch `c29457c..aedd38e`, 26 tasks, all done, none blocked or skipped. Round 1 reviewed the 24 plan tasks commit by commit; this round re-checked the branch state and read the two fix commits in full against docs/SPEC.md, docs/PLAN.md § Review fixes (round 1), and the round-1 findings:

- `0385198` (R1-01)
- `076de4c` (R1-02)

`git diff --name-only 7b78c6e..HEAD` lists only these files:

- `tests/test_cli.py`
- `tests/test_cleanup.py`
- `docs/PROGRESS.md`
- `docs/HANDOFF.md`
- `.kukulu/state.json`

No production code changed.

## Checks run

- **`kukulu_verify`:** all 19 constraints pass, every fixture self-test is clean, and there are 0 hits. Every verify command exits 0:
  - the RESEARCH heading check
  - `uv lock --check`
  - mypy strict (6 files)
  - ruff check
  - ruff format check (26 files)
  - unittest discover (101 tests, up from 95)
  - `main.py --help`
- **`prChecks`:** `pending`, with no failing checks. CI had not finished on the PR when I read it, so this is not a finding.
- **Clean-room mode:** off (`cleanroom: null`).
- **Edits outside the tasks:** none. `.gitignore`, `.gitattributes`, editor config and CI files are untouched by this round. `main.py` and `threadsdelete/` are byte-identical to `7b78c6e`. The implementer says it mutated `main.py` by hand while checking its tests, and nothing of that was left behind.

### Mutation sample (`kukulu_mutate`, targeted `unit`, `confirmKill: true`)

I re-ran each round-1 survivor against the module that the new tests live in. I also ran two mutants of the new tests themselves, to check that each test depends on the condition it claims to test.

| File | Mutation | Result |
| --- | --- | --- |
| main.py | `read_only=cfg.dry_run` → `read_only=False` | killed (`test_dry_run_client_blocks_mutation`: an unexpected DELETE reaches the fake transport) |
| main.py | `handler.addFilter(RedactingFilter([token]))` removed | killed (`test_log_records_are_redacted_by_handler_filter`: the token appears in stderr) |
| main.py | httpx/httpcore pinned to DEBUG instead of WARNING | killed (`test_httpx_request_logs_suppressed_at_debug`) |
| main.py | generic `ApiError` branch returns `ExitCode.OK` | killed (`test_identity_read_failure_exits_1`, `test_dry_run_client_blocks_mutation`) |
| threadsdelete/cleanup.py | `SelectionError` branch sets `discovery.complete = True` | killed (`test_conflicting_duplicate_marks_discovery_incomplete`) |
| tests/test_cleanup.py | clash timestamp made equal to the post's timestamp, so the records are no longer a conflict | killed (the test depends on the conflict) |
| tests/test_cli.py | dry-run loop's second env `DRY_RUN=true` → `false` | killed (the test depends on dry-run mode) |

On the unmutated tree, every confirm re-run passed, so every kill is real.

## Findings

None.

- **1 Constraints:** clean. The tool reports no hits. The new test code adds no `print` or logger call that takes the access token. The token is logged only through a literal test constant, to prove that it gets redacted. The new tests build no real transport.
- **2 Boundaries:** clean. This round changed tests only.
- **3 Tests:** clean.
  - Every acceptance test named in R1-01 and R1-02 exists, and each one exercises its mechanic at the place where it is wired. For example, `main.cleanup.run` is stubbed so that the client built by `main` is the one under test.
  - Every round-1 survivor is now killed.
  - `test_removal_mode_client_is_not_read_only` covers the `DRY_RUN=false` half of the plan's dry-run test.
- **4 Performance:** SPEC is silent, and this round has no production change.
- **5 Spec drift:** none. Both tasks stayed inside their files and their out-of-scope lists.
- **6 Interpretation choices:**
  - Round 1's new choice is that `MutationBlockedError` surfaces as exit 1 through main's `ApiError` mapping. This matches R1-01's acceptance text ("exit 1 or raised, per main's mapping"). It is also consistent with SPEC §6, which requires a nonzero exit for unrecoverable API errors.
  - The earlier choices were assessed in round 1 and still stand.
- **7 Blocked and skipped tasks:** none.

## Spec issues

None new. PLAN's `## Spec issues` resolutions stand as implemented:

- empty Actions Variables count as unset
- a documented quota error mid-run counts as deferral
- the run stops after an unknown outcome

## Manual checks still owed

Copied from HANDOFF.md:

- **Phase 1:** read `docs/RESEARCH.md` and confirm it states the fees (none documented), what works, what is unsupported, and what is untested.
- **Phase 2:**
  - `uv run main.py --help` works without credentials.
  - The fixture tests pass.
  - With credentials in `.env`, `DRY_RUN=true ./scripts/run.sh` prints a live preview and changes nothing.
- **Phase 3:**
  - After authorizing specific disposable posts: preview, remove, then confirm in Threads.
  - Also confirm that reply and quote deletion work.
  - Record the error raised at the deletion limit.
  - Check whether content created in the Threads app is enumerated.
- **Phase 4:**
  - Follow the README from a fresh checkout.
  - Set the Secrets and Variables.
  - Run an owner-authorized `workflow_dispatch` preview and read the job summary.
  - Set `DRY_RUN=false` for real scheduled cleanup.
  - Record how long the first real run takes, for timeout tuning.
- **Unverified Meta steps** (in `docs/META_SETUP.md`):
  - whether `threads_delete` can be requested in the authorization `scope`
  - how the redirect URI behaves
  - the repost-removal call, which would promote reposts to supported
- **⚠️ ASSUMPTION keys:** every live measurement is still pending (human). This covers:
  - `MAX_DELETIONS_PER_RUN`
  - `HTTP_TIMEOUT_SECONDS`
  - `MAX_READ_RETRIES`
  - `MAX_RETRY_WAIT_SECONDS`
  - `jobs.cleanup.timeout-minutes`
- **CI (added by this review, not from HANDOFF):** confirm the PR's checks finish green. They were `pending` at review time.

## Notes

- `test_removal_mode_client_is_not_read_only` also asserts `issubclass(MutationBlockedError, ApiError)`. That is a type-hierarchy check unrelated to the test's subject, and `MutationBlockedError` is the test file's only use of that import. Harmless, but it could be dropped.
- Two things in the new stubs in `tests/test_cli.py` are harmless:
  - The stubs carry `# type: ignore[no-untyped-def]`. The verify command runs mypy on the explicit paths `threadsdelete main.py`, which do not include tests, so these comments have no effect there.
  - Under the `read_only=False` mutant, `test_dry_run_client_blocks_mutation` fails with an ERROR (the fake rejects the unexpected DELETE) rather than with an assertion. It still kills the mutant.
- The round-1 notes still apply:
  - `OwnershipError` is redundant in `discover_all`'s exception tuple.
  - POST's `scanned` count includes repost facades.
  - `api.py` uses the Python 3.14 unparenthesised `except A, B:` form.
  - Retry warnings print to stderr during the test run.
