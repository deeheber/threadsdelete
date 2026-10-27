# Build summary: token-refresh flight

**Merge line:** `build/2026-10-27` into `main`, a5ac889 → 4d8b0b0, 22 commits, 2 reviews, final verdict APPROVED (review 2).

## What was built

**Phase 1: Token refresh (P1-01 to P1-06, plus review fix R1-01).** A new bash script, `scripts/refresh-token.sh`, refreshes the long-lived Threads access token through Meta's documented `refresh_access_token` endpoint and checks the new token against `v1.0/me` before saving it. It saves to one of two places. Run locally, it rewrites the token line in `.env` atomically (P1-01). Under GitHub Actions, it masks the new token and writes it to the `THREADS_ACCESS_TOKEN` repository secret with `gh secret set` on stdin (P1-02). A new workflow, `.github/workflows/refresh-token.yml`, runs the script at 06:00 UTC on the 1st of every month and on manual dispatch. It uses a `SECRETS_WRITE_TOKEN` PAT and a pinned checkout (P1-03). `docs/META_SETUP.md` §8 is now titled "Expiry and refresh", and the anchors and `docs/RESEARCH.md` were updated to match (P1-04). The README and `.env.sample` describe the refresh, with `SECRETS_WRITE_TOKEN` as its own setup step (P1-05). P1-06 closed the phase and listed the manual checks. R1-01 added tests that kill four mutants of the script that had survived round 1. Nothing under `threadsdelete/` or `main.py` changed. There are 127 offline tests, with fake `curl` and `gh`.

## Decisions that shaped it

- Plan: one phase, "Token refresh", because no scaffold or polish phase was needed (plan).
- P1-01/P1-02: the shared steps and the local destination came first, then the Actions destination. Between the two, the Actions branch was an untested stub that exited with status 2.
- P1-01: the script reads `GITHUB_ACTIONS` exactly once and sets `mode=actions|local`. Later steps branch on `$mode`.
- P1-01: exit status 2 for any failure before the refresh request (nothing changed), 1 for any failure from the refresh on, 0 on success. SPEC asks only for "non-zero".
- P1-01: all messages go to stderr with the prefix `refresh-token: `. Failures before the refresh end with "Nothing was changed. Fix the cause and run again." Later failures say the token "may have changed", say that running again may not fix it, and point to a cleanup preview and to `docs/META_SETUP.md` §5 and §8.
- P1-01: every curl call has one fixed shape. `-q` comes first, then `--max-time 30`, and the token goes in on stdin through `--data-urlencode 'access_token@-'`. curl's stderr goes to a temp file and is never printed; only its exit code is printed.
- P1-01: the curl timeout is the literal `--max-time 30`, not a setting, and no variable is named after an ASSUMPTION key.
- P1-01: failure messages read "failed, curl exit N." so that the `curl-q-first` rule does not match "(curl" (interpretation).
- P1-02: `gh` stdout and stderr go to temp files. On failure the script prints only the exit code and a PAT hint.
- P1-02: the four Actions inputs are checked with `eval` on fixed key names. No user-supplied name reaches `eval` (interpretation).
- P1-01: `.env` parsing. A key line must start exactly with `KEY=`. Lines starting with `#`, `export ` or whitespace do not count. There is no quote stripping, unlike uv's `--env-file`. The local token is rejected if it contains whitespace (including CR) or a quote. The Actions token is rejected if it contains whitespace.
- P1-01: the new token is validated inside `jq -e` (non-empty string, no whitespace) before it is extracted, because command substitution would hide a trailing newline.
- P1-01: error code and subcode are read from either the `.error.*` shape or the top-level shape, and are printed only when they are digits.
- P1-01: the verify step compares `.id` as a string against `THREADS_USER_ID`, passed through `jq --arg`. The user ID is not a secret.
- P1-01: the script sets `umask 077` and a `trap cleanup EXIT`, keeps responses in `mktemp -d`, and rewrites `.env` through `mktemp .env.XXXXXX`, awk with `ENVIRON`, `chmod 600` and `mv -f`. The trap ends with `return 0`, because on bash 3.2 a failing last trap command turns exit 0 into 1.
- Tests: Python fakes for `curl` and `gh` live in `<tmp>/fakebin`, with paths baked into their text. PATH is `<tmp>/fakebin:/usr/bin:/bin`, with `jq` symlinked in, so the owner's real Homebrew `gh` is never reachable.
- Tests: CI's `ubuntu-latest` image already has `jq`, so `ci.yml` is unchanged.
- P1-03: the workflow and step are named `Refresh token`, the job id is `refresh`, and `cancel-in-progress` is false.
- The docs tasks depend on the script and workflow tasks, so the docs never describe something that did not land.
- Plan: the planner made the CLAUDE.md edits and set the constraints in the plan commit. No task edits CLAUDE.md.
- Plan: the constraints are SPEC 7's set plus five extra line rules: `curl-q-first`, `no-curl-redirects`, `no-secret-body-flag`, `no-awk-v` and `no-token-in-url-args`.
- Plan: `extraVerify` runs `bash -n` on both scripts, with no `test -f` guard.
- Plan: policies are `archive: true` and `finalize: "ready"`. No parallel streams, and no live commands in any task.
- P1-04: PLAN.md is not edited, even though it still quotes the old anchor (interpretation).
- P1-05: `SECRETS_WRITE_TOKEN` is its own numbered README step 3, and the later steps were renumbered (interpretation).
- P1-06: an empty commit was made so the task's commit subject exists (interpretation).
- R1-01: `Harness.prepare` gained an optional `before_run` hook, so the repository root can be made read-only after the files are written. The root-lock test skips only when running as root (interpretation).

## Assumptions still in play

- `MAX_DELETIONS_PER_RUN`: unchanged, still a guess (no Python changed).
- `HTTP_TIMEOUT_SECONDS`: unchanged, still a guess.
- `MAX_READ_RETRIES`: unchanged, still a guess.
- `MAX_RETRY_WAIT_SECONDS`: unchanged, still a guess.
- The script's `--max-time 30` is not an ASSUMPTION key, but it has not been measured either.

## Spec issues

From PLAN.md:
- SPEC 4.1 asks only for a "non-zero" exit status. The build uses 2 before the refresh and 1 from the refresh on. Consider writing this into SPEC.
- SPEC 4.1 step 1 does not say how `.env` is parsed. The script requires `KEY=` at the start of the line and does not strip quotes, which differs from `uv --env-file`. Consider specifying this.
- SPEC 4.1 relies on curl `--data-urlencode 'access_token@-'` reading stdin without a trailing newline. The real encoding is first exercised by the owner's SPEC 8 step 2.
- SPEC 4.1 says "-q first". The line rule can only see it on the same line as `curl`, so that layout is required.
- SPEC 5's "system directories" on the test PATH became `<tmp>/fakebin:/usr/bin:/bin` with `jq` symlinked in.
- SPEC 4.1's "one if/else on GITHUB_ACTIONS" became a single `mode` variable.
- SPEC 6 missed `docs/RESEARCH.md`'s "manually replaced" line in § Comparison with blueskydelete, and the old title of `docs/META_SETUP.md` §8. Both were updated in P1-04.
- SPEC 8 "CI is green" cannot be observed by the implementer, so the reviewer and manual checks cover it.
- The local writability test cannot run as root, so it skips under root.
- SPEC 7's constraint list did not cover SPEC 4.1's single-line mechanical rules, so five rules were added.

From REVIEW.md (rounds 1 and 2):
- PLAN P1-04's verification grep (`grep -rn "8-expiry-and-manual-renewal" README.md docs/*.md`) can never come back empty, because `docs/PLAN.md` quotes the old anchor. Future planners should exclude PLAN.md from greps like this.
- `curl-q-first` over-matches `(curl` and `then curl` inside message strings. This is a false positive, not a blind spot.

Known-gap candidates: the final REVIEW.md has no `Known-gap candidates` section, so there is nothing to copy.

## Manual checks owed

Phase 1 (owner, after merge, in this order):
1. Create the PAT, add the `SECRETS_WRITE_TOKEN` secret, and check that Actions failure notifications are on (`docs/META_SETUP.md` §8).
2. With a token at least 24 hours old, dispatch "Refresh token". Look for the "saved to the repository secret" line, check that no token appears in the log, and check that `gh secret list` shows `THREADS_ACCESS_TOKEN` just updated.
3. Dispatch "Threads cleanup" with `dry_run: true` and check that authentication succeeds.
4. Recommended: if the local `.env` shares the old secret's token, preview locally (`DRY_RUN=true ./scripts/run.sh`) to see whether that token survived the Actions refresh. Then run `./scripts/refresh-token.sh` locally, or give local its own token. Record in `docs/RESEARCH.md` as [live] whether the token string changed and whether the old token stayed valid, and update the shared-vs-separate guidance in META_SETUP §8.
5. Confirm CI is green on the PR. `prChecks` reported `pass` at the round 2 review.

## Review history

- Round 1: CHANGES REQUESTED. 1 finding (four surviving mutants in `scripts/refresh-token.sh`), 1 fix task (R1-01; sources: review 1, mutation 0, blocked 0). No recurrence, since this was the first round. Not non-converging.
- Round 2: APPROVED. 0 findings, 0 fix tasks. R1-01 did not recur: the reviewer re-ran all four mutants with `kukulu_mutate` and all are killed. This was a notes-only approval. Its `## Notes` section says the `r.calls == []` assertion in the read-only-root test cannot see a curl call, so the exit code carries that test. It also repeats round 1's advisory notes: an unreadable `.env` exits non-zero without the `refresh-token:` prefix, `chmod 600` and `umask 077` overlap, and `gh` args are compared with `[:3]`.

## Pipeline friction

The feedback log is empty (`feedbackCount` is 0), but HANDOFF.md records one pipeline issue:
- implement: `kukulu_mutate` was not available to the implementer, so R1-01's mutants were re-run by hand with `sed` and the script was restored with `git checkout`. The reviewer later confirmed them with the tool.

## Suggested CLAUDE.md additions

- `tests/test_refresh_token.py` needs `jq` on PATH. It runs a copy of the script with fake `curl`/`gh` first on PATH and a from-scratch environment.
- `curl-q-first` matches any `(curl` or `then curl` text, including inside message strings. Avoid that wording in messages.
- BSD `sed -i` on macOS needs an argument. Use Python for scripted edits.

## Advisory mutation survivors

None. Round 2's Notes list no survivors outside its diff. Round 1 called the `chmod 600`/`umask 077` mutants equivalent, not gaps.

## Breaking call

Breaking: yes. Merging adds a monthly scheduled workflow that rotates the `THREADS_ACCESS_TOKEN` secret, and it fails until `SECRETS_WRITE_TOKEN` is set up. If the owner's local `.env` shares that token, it may stop working after the first Actions refresh (not yet measured; SPEC 8 step 4). The cleanup code and its settings are unchanged. The PR should be merged by hand after manual check 1.
