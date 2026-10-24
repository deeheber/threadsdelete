# Review: build/2026-10-24
Round: 1

Verdict: **CHANGES REQUESTED**

Scope: the whole branch `c29457c..04e8f93` (24 tasks, all done, none blocked or skipped), read commit by commit against docs/SPEC.md v0.2, docs/PLAN.md and docs/RESEARCH.md § Contracts.

## Checks run

- `kukulu_verify`: all 19 constraints pass, every fixture self-test is clean, 0 hits. All verify commands exit 0: RESEARCH heading check, `uv lock --check`, mypy strict, ruff check, ruff format check, unittest discover (95 tests), and `main.py --help`.
- `prChecks`: pass. Clean-room mode is off (`cleanroom: null`).
- Pinned action SHAs checked against upstream with `git ls-remote`: actions/checkout `3d3c42e5…` is `v7.0.1` and astral-sh/setup-uv `07a047e6…` is `v10.3.2`. Both match.
- I read the structural reviewer checks myself:
  - Dry run builds `ThreadsClient(read_only=cfg.dry_run)` (main.py:99).
  - `discover_all` finishes before any `remove`.
  - `remove` is called once per candidate and is never wrapped in a retry.
  - `scripts/run.sh` uses `exec` and `set -euo pipefail`, has no logic, and is mode 100755.
  - No `${{ }}` appears inside a `run: |` block.
  - Fixtures are synthetic (`example_owner`, ids 1000001/9000001…).
  - No Bluesky source was adapted.
- No `.gitignore`, `.gitattributes`, editor config or CI edits outside their tasks. `.gitignore` was extended only in P2-01, as planned.

### Mutation sample (`kukulu_mutate`)

| File | Mutation | Result |
| --- | --- | --- |
| threadsdelete/core.py | `is_eligible` `<=` → `<` | killed (test_cutoff_boundary_before_at_after, test_zero_days…) |
| threadsdelete/config.py | accept `yes` as a boolean | killed (test_booleans_accept_only_true_false_any_case) |
| threadsdelete/api.py | read-only guard in `_send` disabled | killed (test_read_only_client_blocks_*) |
| threadsdelete/api.py | repeated-cursor check disabled | killed (test_repeated_cursor_rejected) |
| threadsdelete/api.py | `deleted_id` mismatch check disabled | killed (test_remove_success_requires_valid_body) |
| threadsdelete/api.py | reply username ownership check disabled | killed (test_reply_not_owned_aborts) |
| threadsdelete/api.py | 5xx with error body treated as ItemError | killed (test_remove_5xx_and_malformed_body_are_unknown) |
| threadsdelete/cleanup.py | keep removing after an unknown outcome | killed (test_unknown_outcome_stops_and_is_not_success) |
| threadsdelete/cleanup.py | quota-inspection failure re-raised instead of falling back | killed (test_quota_unavailable_falls_back…) |
| threadsdelete/cleanup.py | discovery continues after a category failure | killed (test_incomplete_discovery_*) |
| threadsdelete/cleanup.py | auth error not re-raised after the summary | killed (test_auth_failure_stops_globally) |
| threadsdelete/cleanup.py | quota checked even when nothing is eligible | killed (test_nothing_eligible_exits_0_without_mutation) |
| **threadsdelete/cleanup.py** | `SelectionError` leaves `discovery.complete = True` | **survived** |
| main.py | `return cleanup.exit_status(summary)` → `ExitCode.OK` | killed (CLI exit-1 tests) |
| main.py | filter and httpx pin both removed together | killed (test_token_never_printed, test_auth_loss_…_redacts_token) |
| **main.py** | `read_only=cfg.dry_run` → `read_only=False` | **survived** |
| **main.py** | `handler.addFilter(RedactingFilter(...))` removed | **survived** |
| **main.py** | httpx/httpcore pinned to DEBUG instead of WARNING | **survived** |
| **main.py** | generic `ApiError` branch returns `ExitCode.OK` | **survived** |
| .github/workflows/cleanup-feed.yml | summary step `if: always()` → `if: success()` | killed (test_cleanup_uses_same_entry_point_and_preserves_status) |

## Findings

### F1 — Category 3 (tests): main.py safety wiring has no test of its own (task R1-01)

- **Where:**
  - main.py:99 `read_only=cfg.dry_run,`
  - main.py:58 `handler.addFilter(RedactingFilter([token]))`
  - main.py:63-64, httpx/httpcore pinned to WARNING
  - main.py:108-110, the generic `ApiError`/`SelectionError`/`TimestampError` branch returning `ExitCode.FAILURE`
- **What is wrong:** each of these four lines can be inverted or deleted and all 95 tests still pass.
  - `read_only=False` in dry run survives because `cleanup.run` never calls `remove` in dry run. The second safety layer that SPEC §3 asks for ("Dry run performs no mutations, regardless of HTTP method") and PLAN's Decision requires ("Dry run → the ThreadsClient is constructed read_only=True") is never checked at the place it is wired.
  - Removing the `RedactingFilter`, or unpinning the httpx loggers, survives on its own. `test_token_never_printed` passes trivially: with the pin in place nothing logs a URL, and with the filter in place an unpinned httpx line is redacted. Only removing both together is caught. The two layers are tested jointly, never one at a time. SPEC §3 requires redacting credentials from all logs, and the token travels in every URL as `access_token=` (RESEARCH § Authentication transport).
  - Changing the generic `ApiError` exit from FAILURE to OK survives. No CLI test triggers a non-auth API error outside discovery, such as a failed identity read (ResponseError or ReadFailedError). SPEC §6 requires a nonzero exit for "unrecoverable API errors".
- **What would break:** a later edit could make dry runs depend on a single layer. It could also log the token in every request URL as soon as one of the two redaction layers regresses, or let a cron run that cannot even read the identity report success (exit 0). None of these would fail a test.
- **Minimal fix:** tests only, in tests/test_cli.py. Change main.py only if a new test exposes a real defect.
  1. Dry run: patch `main.cleanup.run` with a stub that calls `client.remove(<a post Candidate>)`. Assert `MutationBlockedError` is raised and the fake transport records no DELETE. With `DRY_RUN=false`, assert the client passed to `run` has `read_only is False`.
  2. Filter wiring: with `LOG_LEVEL=DEBUG`, have the stub (or the fake transport handler) log `logging.getLogger("threadsdelete.api").info("x %s", TOKEN)` during `main()`. Assert TOKEN is absent from `err` and `[REDACTED]` is present.
  3. httpx pin: with `LOG_LEVEL=DEBUG`, run the normal fixture preview and assert `"HTTP Request:"` does not appear in `err`.
  4. Generic error: `GET me` returns a 2xx body without `id` (ResponseError), or 503 on every attempt (ReadFailedError). Assert exit 1, `Error:` in `err`, and the token absent.

### F2 — Category 3 (tests): a conflicting duplicate never reaches the run report or exit status in any test (task R1-02)

- **Where:** threadsdelete/cleanup.py:183-187 (the `except SelectionError` branch in `run`).
- **What is wrong:** with `discovery.complete = False` mutated to `True`, all tests pass. Under that mutant a conflicting duplicate leaves `eligible == []` and nothing is removed, but the report prints `Discovery: complete` and the exit status is 0. That is silent success on ambiguous data. `test_conflicting_duplicate_timestamps_raise` covers only the pure `select_eligible` in core. Nothing covers what `run` does with the error.
- **SPEC:** §3 "Abort mutation on incomplete discovery or ambiguous ownership" and "Deduplicate by operation/type and ID". §6 requires a nonzero exit on incomplete discovery. §8 Phase 3 lists "duplicates" among the failure boundaries to cover.
- **Minimal fix:** in tests/test_cleanup.py, a removal-mode run with a fake where one id appears twice with different timestamps. Put it on both `/me/threads` pages, or give a reply and a post the same id, since the dedupe key is `(operation, id)` and both are DELETE. Assert:
  - `summary.discovery_complete is False`
  - `Discovery: INCOMPLETE` appears in the output
  - no DELETE request was recorded
  - `cleanup.exit_status(summary) == ExitCode.FAILURE`

  Optionally add a CLI exit-1 check.

### Other categories

- **1 Constraints:** clean. The tool reports no hits and my own reading of the diff found no violation the rules missed.
- **2 Boundaries:**
  - Only api.py imports httpx.
  - `config.py` takes a Mapping, and only main.py reads `os.environ`.
  - The ⚠️ ASSUMPTION literals live only in config.py.
  - URL literals appear only in api.py.
  - `core.py` is pure.
  - Clean.
- **4 Performance:** SPEC is silent. `/me/threads` is fetched once per client and shared by POST and QUOTE. Nothing is quadratic.
- **5 Spec drift:** none found. The one listed acceptance test that does not exist, `test_repost_uses_owner_action_time` (P2-05), was replaced by `test_repost_records_need_no_ownership_and_are_not_returned`. That is consistent with RESEARCH marking reposts unsupported, and PLAN tells implementers that RESEARCH wins on API facts.
- **7 Blocked and skipped tasks:** none.

## Interpretation choices (HANDOFF)

Each one is the reading most consistent with SPEC:

- **P1-01:** host `graph.threads.com` and token as the `access_token` query parameter. RESEARCH documents only that transport, and PLAN's Decision explicitly yields to RESEARCH. The consequence, URL redaction plus the httpx/httpcore WARNING pin, is the right mitigation. F1 asks for that mitigation to be tested.
- **P1-02 and P2-05:** reposts and likes are excluded with their reasons. This follows SPEC §1 ("document and omit unsupported optional categories"). Counting repost facades under POST `scanned` is documented and tested.
- **P1-03:** GO on documentation evidence alone. This matches PLAN's Decision that unretrievable pages are not a NO-GO.
- **P2-02:** no echoed values, and digits-only user id. Both are as planned.
- **P2-03:** conflicting duplicates raise before eligibility filtering. This is the stricter reading of "abort on ambiguous".
- **P2-04:** backoff of `2**attempt` from attempt 0. 429 is retried on reads, and 4/17/341 on reads raise `QuotaExceededError`, which discovery turns into incomplete discovery. Consistent with SPEC.
- **P2-07:** summary lines only for supported categories. Unsupported ones appear as `Excluded:` lines. Fine.
- **P3-01:** a `deleted_id` mismatch is an unknown outcome, and a 4xx with a well-formed Graph error body is an `ItemError`. Both are consistent with "never reinterpret unknown errors as success".
- **P3-02:** quota is read only when something is eligible. PLAN anticipated `Quota: not checked`, and SPEC only requires quota to bound removals. The failing item is deferred on a quota or auth error, and the auth error is re-raised after the summary. Consistent with SPEC.
- **P4-01 and P4-02:** pinned SHAs verified above. `PYTHONUNBUFFERED=1` is harmless and keeps the tee'd log in order.

## Spec issues

None new. PLAN's `## Spec issues` list still stands, and its resolutions are implemented as written:

- empty Actions Variables count as unset
- a documented quota error mid-run counts as deferral (exit 0)
- the run stops after an unknown outcome

## Manual checks still owed

Copied from HANDOFF.md:

- Phase 1: read `docs/RESEARCH.md`; confirm it states fees (none documented), what works, what is unsupported, what is untested.
- Phase 2: `uv run main.py --help` without credentials; the fixture tests; with credentials in `.env`, `DRY_RUN=true ./scripts/run.sh` prints a live preview and changes nothing.
- Phase 3: after authorizing specific disposable posts, preview, remove, confirm in Threads. Also confirm reply and quote deletion, the error raised at the deletion limit, and whether Threads-app-created content is enumerated.
- Phase 4: follow the README from a fresh checkout; set Secrets/Variables; run an owner-authorized `workflow_dispatch` preview and read the job summary; then set `DRY_RUN=false` for real scheduled cleanup. Record the first real run duration (timeout tuning).
- Unverified Meta steps (in `docs/META_SETUP.md`): whether `threads_delete` can be requested in the authorization `scope`, redirect URI behavior, the repost-removal call (would promote reposts to supported).
- ⚠️ ASSUMPTION keys: every live measurement is still pending (human). These are `MAX_DELETIONS_PER_RUN`, `HTTP_TIMEOUT_SECONDS`, `MAX_READ_RETRIES`, `MAX_RETRY_WAIT_SECONDS` and `jobs.cleanup.timeout-minutes`.

## Notes

- `OwnershipError` is redundant in `discover_all`'s `except (ApiError, TimestampError, OwnershipError)` tuple, because it is already an `ApiError` (cleanup.py:65). Harmless.
- POST's `scanned` count includes repost facades, so `post: scanned=5` in the fixture report counts one repost. This is documented in HANDOFF and in the `discover` docstring, but a reader of the summary line could find it surprising. Consider saying so in the README's report description.
- `api.py:387` uses the Python 3.14 unparenthesised `except A, B:` form (PEP 758). That is valid for the pinned 3.14 runtime but will not parse on older interpreters if anyone runs the code outside `uv`.
- Retry warnings print to stderr during the test run, as HANDOFF notes. Cosmetic.
