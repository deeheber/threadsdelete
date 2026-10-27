# Handoff: token-refresh flight

- Branch: `build/2026-10-27`; base: `main` (a5ac889); tasks: 6 done, 0 blocked, 0 skipped.

## Blocked / skipped
None.

## Interpretation choices
- P1-01: curl failure messages read "failed, curl exit N." so the `curl-q-first` rule does not match "(curl".
- P1-02: the four Actions inputs are checked with `eval` on fixed key names (no user-supplied names).
- P1-04: the old-anchor grep over `docs/*.md` still hits `docs/PLAN.md`, which quotes it; PLAN.md is not edited.
- P1-05: `SECRETS_WRITE_TOKEN` is its own numbered README step 3; later steps renumbered.
- P1-06: empty commit made so the task commit subject exists.

## ASSUMPTION keys
`MAX_DELETIONS_PER_RUN`, `HTTP_TIMEOUT_SECONDS`, `MAX_READ_RETRIES`, `MAX_RETRY_WAIT_SECONDS`: unchanged, not tuned (no Python changed).

## Manual checks (owner, after merge)
1. Create the PAT, add `SECRETS_WRITE_TOKEN`, enable Actions failure notifications (docs/META_SETUP.md section 8).
2. With a token at least 24 hours old, dispatch "Refresh token"; check the "saved to the repository secret" line, no token in the log, and `gh secret list` update time.
3. Dispatch "Threads cleanup" with dry_run true; check authentication succeeds.
4. Recommended: preview locally, then run `./scripts/refresh-token.sh`; record in docs/RESEARCH.md as [live] whether the token string changed and the old token stayed valid.
5. Confirm CI is green on the pull request.

## Codebase notes
- `tests/test_refresh_token.py` needs `jq` on PATH; it runs a copy of the script with fake `curl`/`gh` first on PATH and a from-scratch environment.
- `curl-q-first` matches any `(curl` or `then curl` text, including inside message strings.
- BSD `sed -i` needs an argument; use python for scripted edits on macOS.

## For the reviewer
No changes under `threadsdelete/` or `main.py`. The script was never run live.
