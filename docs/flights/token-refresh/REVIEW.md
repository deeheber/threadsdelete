# Review: token-refresh flight
Round: 2

Branch `build/2026-10-27`, base `main` (a5ac889), head 9536616. Tasks: 7 done (P1-01 to P1-06, R1-01), 0 blocked, 0 skipped.

## Verdict

APPROVED

Round 1 reviewed the whole branch (P1-01 to P1-06). Its one finding was four surviving mutants in `scripts/refresh-token.sh`, queued as R1-01. Since `lastReviewCommit` 905374d, the only code change is `tests/test_refresh_token.py` (commit 3d737ec, signed). The rest is pipeline bookkeeping: `.kukulu/state.json`, `docs/HANDOFF.md` and `docs/PROGRESS.md`. `scripts/refresh-token.sh`, the workflows, docs, `threadsdelete/` and `main.py` have not changed since round 1.

- **PR checks:** `kukulu_status` reports `prChecks.state: pass`, with no failing checks.
- **Clean-room:** `kukulu_status` returned `cleanroom: null`, so there were no denials to audit.
- **`kukulu_verify`:** everything passes. That covers all 29 constraint rules (no fixture failures, no hits), `uv lock --check`, mypy, ruff check, ruff format (40 files), 127 offline tests (126 before, plus the new root-writability test), `main.py --help`, `bash -n scripts/run.sh` and `bash -n scripts/refresh-token.sh`.

## Findings

None.

R1-01 was checked against its PLAN acceptance tests and verification steps:

1. Category 3 (tests). I re-ran all four of the task's mutants myself with `kukulu_mutate` (file `scripts/refresh-token.sh`, targeted `unit`, filter `tests.test_refresh_token`, `confirmKill: true`). All four are now **killed**. In each case the failure tail names the test the task intended, and the unmutated re-run passes (16 tests OK).
   - (a) Deleting the duplicate-line check fails `test_invalid_env_file_fails_before_network` in all four duplicate cases. "two tokens, empty second" and "two users, empty second" exit 0 instead of 2. This is the shape that the whitespace and digits checks cannot catch.
   - (b) Deleting the `[ -w . ]` check fails `test_unwritable_repository_root_fails_before_network` with exit 1 instead of 2. The fake `curl` cannot create `calls.jsonl` under the read-only root, so the run fails rather than passing, which is what the task asked for.
   - (c) Replacing the recovery text with "Run again." fails `assert_recovery_text` in 30 subtests across `test_refresh_failures_stop_before_any_other_call` and `test_verify_failures_leave_destination_unchanged`.
   - (d) Making the Actions whitespace pattern never match fails `test_missing_input_fails_before_any_call` for `FAKE OLD` and `FAKE-OLD\r` (exit 0 instead of 2).
2. Category 2 (boundaries). The fix is limited to the task's one file. It imports only the stdlib (`collections.abc.Callable`). The `before_run` hook runs after the harness has checked that the fakes are first on PATH, so the SPEC 5 isolation rules hold. The new test skips only when `geteuid() == 0`. It registers `chmod 0o755` through `addCleanup` after the temporary directory's own cleanup, so it runs first and removal still works.
3. Category 1 (constraints). Nothing in the diff touches any rule in CLAUDE.md § Constraints, and the reading-only checks are unaffected. The fixtures stay synthetic (`FAKE-OLD…`, fake IDs).

## Spec issues

Carried from round 1. Neither one blocks approval.

- PLAN P1-04's verification grep (`grep -rn "8-expiry-and-manual-renewal" README.md docs/*.md`) can never come back empty, because `docs/PLAN.md` quotes the old anchor. Future planners should exclude PLAN.md from greps like this.
- `curl-q-first` over-matches `(curl` and `then curl` inside message strings. That is a false positive, not a blind spot. Its only effect was the harmless "failed, curl exit N." wording.

## Manual checks still owed

Copied from HANDOFF.md:

1. Create the PAT, add `SECRETS_WRITE_TOKEN`, and enable Actions failure notifications (docs/META_SETUP.md section 8).
2. With a token at least 24 hours old, dispatch "Refresh token". Check for the "saved to the repository secret" line, check that no token appears in the log, and check the update time in `gh secret list`.
3. Dispatch "Threads cleanup" with dry_run true and check that authentication succeeds.
4. Recommended: preview locally, then run `./scripts/refresh-token.sh`. Record in docs/RESEARCH.md as [live] whether the token string changed and whether the old token stayed valid.
5. Confirm CI is green on the pull request. At this review, `prChecks` reports `pass`.

## Notes

- In `test_unwritable_repository_root_fails_before_network`, the `r.calls == []` assertion cannot see a `curl` call while the root is read-only, because the fake cannot record it. The exit-code assertion carries the test, and mutant (b) confirms it does. This is advisory only.
- HANDOFF says `kukulu_mutate` was unavailable to the implementer, so the mutants were re-run by hand with `sed` and restored with `git checkout`. Running them through the tool here confirms the results, and the tree is clean.
- Round 1's advisory notes still apply and are unchanged: an unreadable `.env` exits non-zero without the `refresh-token:` prefix; `chmod 600` and `umask 077` overlap; `gh` args are compared with `[:3]`.
