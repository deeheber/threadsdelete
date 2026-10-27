# Review: token-refresh flight
Round: 1

Branch `build/2026-10-27`, base `main` (a5ac889), head 5668744. Tasks: 6 done, 0 blocked, 0 skipped.

## Verdict

CHANGES REQUESTED

The script, workflow and docs match SPEC 4.1, 4.2 and 6. `kukulu_verify` passes: all 29 constraint rules are green with no fixture failures, along with lockfile, mypy, ruff lint and format, 126 offline tests, `--help`, and `bash -n` on both scripts. PR checks: `pass`. Clean-room: `kukulu_status` returned `cleanroom: null`, so there was nothing to audit. The remaining problem is in category 3: four mutants of `scripts/refresh-token.sh` survive the suite, and three of them leave SPEC requirements untested.

## Findings

### 1. Category 3 (tests): four surviving mutants in `scripts/refresh-token.sh` (fixed in R1-01)

Each mutant was run with `kukulu_mutate` (targeted `unit`, filter `tests.test_refresh_token`). The script is correct in every case. The tests just don't check these mechanics.

1. **Duplicate-line check** (`scripts/refresh-token.sh:47`, `if [ "$n" -gt 1 ]; then die_before ".env has more than one $key line."; fi`). Deleting it **survives**. The "two tokens" and "two users" cases in `test_invalid_env_file_fails_before_network` (`tests/test_refresh_token.py:277`, `:283`) still exit 2, but for a different reason: `sed -n 's/^KEY=//p'` returns `OLD\nOLD`, and the whitespace check or the digits-only check rejects that embedded newline. A duplicate whose second value is empty (`THREADS_ACCESS_TOKEN=OLD\nTHREADS_ACCESS_TOKEN=\n`) gives `OLD` once command substitution strips the trailing newline (checked in a scratch shell). Without the check, the script would send a refresh request and awk would then write the new token into both lines. This breaks SPEC 4.1 step 1 ("exactly one `THREADS_ACCESS_TOKEN=` line and exactly one `THREADS_USER_ID=` line") and SPEC 5 Local ("a ... duplicated ... line ... fails before any `curl` call").
2. **Repository-root writability** (`scripts/refresh-token.sh:80`, `[ -w . ] || die_before "the repository root is not writable."`). Deleting it **survives**. No test makes the root unwritable. This breaks SPEC 4.1 step 2 ("Local: `.env` and the repository root are writable").
3. **Recovery text after a refresh** (`scripts/refresh-token.sh:27`). Replacing "Check the stored token with a cleanup preview ... replace it by hand (docs/META_SETUP.md sections 5 and 8)." with "Run again." **survives**. Tests assert only `may have changed`. This breaks SPEC 4.1 Failure messages (check the stored token with a cleanup preview, replace by hand via `docs/META_SETUP.md` §5 and §8; never promise that running again fixes it). PLAN Decisions also says "Tests assert `Nothing was changed`, `may have changed` and `docs/META_SETUP.md`", and no test asserts `docs/META_SETUP.md`. The mutant swaps in exactly the promise SPEC forbids, and nothing notices.
4. **Actions whitespace check** (`scripts/refresh-token.sh:40`, `*[[:space:]]*) die_before "THREADS_ACCESS_TOKEN must not contain whitespace."`). Turning it into a never-matching pattern **survives**. `test_missing_input_fails_before_any_call` never passes a token containing whitespace. This is a PLAN P1-02 step 1 rule. It exists so a bad secret fails at exit 2 before a refresh request is wasted.

Controls that were **killed** (failures confirmed with `confirmKill`): removing the `::add-mask::` line (caught by the Actions verify-failure and success tests), reading `.error.code` as top-level `.code` (caught by the Graph-shape `190`/`460` assertions), and switching `cancel-in-progress: false` to `true` in `.github/workflows/refresh-token.yml` (caught by `RefreshWorkflowTests`).

**What would break:** if any of these four mechanics regressed, a future round would still pass. Without mechanic 1, a duplicated `.env` line goes to Meta and gets rewritten twice. Without mechanic 3, the owner would be told to rerun after a refresh that may already have rotated the token.

**Minimal fix (tests only, `tests/test_refresh_token.py`):**
- In `test_invalid_env_file_fails_before_network`, assert `more than one` in stderr for the "two tokens" and "two users" cases. Add the cases `tok + "THREADS_ACCESS_TOKEN=\n" + uid` and `tok + uid + "THREADS_USER_ID=\n"`, each expecting exit 2, no records, the file unchanged, and `more than one` in stderr.
- Add a local test that makes `<tmp>` mode `0o555` after `prepare` writes the files. Register `addCleanup` to set `0o755` back first, so `TemporaryDirectory` cleanup works. Expect exit 2, no curl record, `.env` unchanged and `Nothing was changed`. Use the same `geteuid() == 0` skip. The harness must create `.env` before the chmod. Records go to `<tmp>/calls.jsonl`, so the test should prepare that file, or check that no record exists afterwards, while the root is read-only.
- In `test_refresh_failures_stop_before_any_other_call` and `test_verify_failures_leave_destination_unchanged`, assert that stderr contains `docs/META_SETUP.md` and `cleanup preview`, and does not contain `run again` (case-insensitive). `Nothing was changed. Fix the cause and run again.` is the exit-2 wording. In `test_invalid_env_file_fails_before_network`, also assert that stderr does not contain `may have changed`.
- In `test_missing_input_fails_before_any_call`, add `THREADS_ACCESS_TOKEN` values `FAKE OLD` and `FAKE-OLD\r`, each expecting exit 2, no records, and `THREADS_ACCESS_TOKEN` in stderr.

Task: R1-01.

## Spec issues

- PLAN P1-04's verification grep (`grep -rn "8-expiry-and-manual-renewal" README.md docs/*.md`) can never print nothing, because `docs/PLAN.md` quotes the old anchor. The implementer was right to leave PLAN.md alone. The planner should exclude PLAN.md in future greps of this kind.
- `curl-q-first` over-matches `(curl` and `then curl` inside message strings (HANDOFF codebase note). This is a false positive, not a blind spot. It made the implementer reword messages ("failed, curl exit N."), which is harmless.

## Manual checks still owed

Copied from HANDOFF.md:

1. Create the PAT, add `SECRETS_WRITE_TOKEN`, enable Actions failure notifications (docs/META_SETUP.md section 8).
2. With a token at least 24 hours old, dispatch "Refresh token"; check the "saved to the repository secret" line, no token in the log, and `gh secret list` update time.
3. Dispatch "Threads cleanup" with dry_run true; check authentication succeeds.
4. Recommended: preview locally, then run `./scripts/refresh-token.sh`; record in docs/RESEARCH.md as [live] whether the token string changed and the old token stayed valid.
5. Confirm CI is green on the pull request. (At this review, `prChecks` reports `pass`.)

## Notes

- Interpretation choices in HANDOFF.md. The P1-01 "curl exit N" wording, P1-02's `eval` on four fixed key names (no user input reaches `eval`; the value is assigned, not expanded into an argument), P1-04 leaving PLAN.md alone, P1-05's numbered `SECRETS_WRITE_TOKEN` step, and P1-06's empty commit each match the reading of SPEC most consistent with the rest of it. None is a finding.
- `git check-ignore -v .env.abc123` gives `.gitignore:8:.env.*`, so the local temp file `.env.XXXXXX` is ignored, as SPEC 4.1 step 6 assumes. `.gitignore`, `.gitattributes`, `ci.yml`, `cleanup-feed.yml`, `scripts/run.sh`, `threadsdelete/` and `main.py` are unchanged against `main`. Only `.env.sample` is tracked.
- An unreadable `.env` (for example mode `000`) passes `[ -f .env ]`. `grep -c` then fails, the `-eq`/`-gt` tests print "integer expression expected", and `sed` fails under `set -e`. The script exits non-zero (1 with BSD sed) before any network call, without the `refresh-token:` prefix or "Nothing was changed". SPEC does not require a readability check, so this is advisory only.
- `chmod 600 "$env_tmp"` and `umask 077` overlap, because `mktemp` already creates files with mode 600. Mutating either one alone is equivalent, so neither counts as a test gap.
- `test_success_sets_secret_from_stdin` compares `gh` args with `[:3]`, so a trailing extra flag would not fail that test. `no-secret-body-flag` and the no-token-in-arguments test cover the dangerous case (`--body`/`-b`).
