# threadsdelete - token refresh specification

Version: 1.0 | Status: ready for implementation | Updated: 2026-10-25 | Tracks: issue #5

## 1. Context

threadsdelete removes the owner's old Threads posts, quotes, replies and reposts, locally and from a weekly GitHub Actions run (`.github/workflows/cleanup-feed.yml`). See `README.md`, `CLAUDE.md` and `docs/RESEARCH.md`. The original build specification is archived in `docs/flights/threadsdelete/SPEC.md`; everything in it still applies unless this document changes it.

Long-lived Threads tokens expire 60 days after their last refresh. Today the owner refreshes them by hand (`docs/META_SETUP.md` §8). This flight adds one script, `scripts/refresh-token.sh`, that refreshes a token, checks it, and saves it either to the `THREADS_ACCESS_TOKEN` repository secret or to a local `.env` file. It also adds a monthly GitHub Actions workflow that runs the script.

Keep every rule in `CLAUDE.md` except where §6 changes one. No live account actions, GitHub-secret writes or real `.env` changes during the build.

## 2. Facts this relies on

From `docs/RESEARCH.md` (Authentication and token lifecycle) and the Meta long-lived-tokens page (re-read 2026-10-25):

- `GET https://graph.threads.com/refresh_access_token?grant_type=th_refresh_token&access_token=<token>` refreshes a long-lived token. No app secret. Requires a token at least 24 hours old and not expired, with `threads_basic` granted.
- Success response: `access_token`, `token_type`, `expires_in` (seconds). The refreshed token is valid for 60 days from the refresh.
- The Threads OAuth endpoints use the error shape `{"error_type", "code", "error_message"}`, not the Graph `{"error": {...}}` shape. Handle both.
- **Unknown:** whether refresh returns a different token string, and whether the old token stays valid afterwards. The design must not depend on either answer.
- `GITHUB_TOKEN` cannot write repository secrets. A fine-grained personal access token (PAT) limited to this repository with "Secrets: read and write" can.
- Permission grants last 90 days. For a public profile, which the owner's is, refreshing the token extends the grant, so regular refreshes need no re-authorization. A private profile's grant can't be extended, so docs still tell private-profile users to re-authorize every 90 days.

## 3. Goals and non-goals

- Goals: refresh the Actions token monthly (plus manual dispatch) and save it to the secret; let the owner refresh the local `.env` token with one command. Both check the new token before saving and fail loudly on any problem.
- Non-goals: any change to `threadsdelete/` or `main.py`; storing or using the app secret; token exchange; syncing one destination from the other; working around GitHub's 60-day inactivity disable; retries.

## 4. Behavior

### 4.1 `scripts/refresh-token.sh`

Bash, committed executable (mode 100755, like `scripts/run.sh`), `set -euo pipefail`, never `set -x`. Must run under bash 3.2 (macOS `/bin/bash`, which runs the tests locally) as well as Ubuntu's bash: no `mapfile`, associative arrays, `${var,,}`, or empty-array expansion under `set -u`.

**Modes:**

| Invocation | Destination | Inputs |
| --- | --- | --- |
| `refresh-token.sh` | repository secret `THREADS_ACCESS_TOKEN`, via `gh` | environment: `THREADS_ACCESS_TOKEN`, `THREADS_USER_ID`, `GH_TOKEN` (PAT), `GH_REPO` (`owner/repo`) |
| `refresh-token.sh --env-file FILE` | the `THREADS_ACCESS_TOKEN` line in `FILE` | the file's `THREADS_ACCESS_TOKEN=` and `THREADS_USER_ID=` lines. The environment's values are ignored, because the file is what gets refreshed. No `gh` or PAT needed. |

Any other arguments print a usage line and exit 2.

**Token handling (both modes):**
- No token ever appears in any process's arguments. Send it through stdin (`printf '%s' "$token" | curl --get --data-urlencode access_token@- ...`, with no trailing newline) or the environment (for example awk's `ENVIRON`, never `awk -v`).
- No token is ever printed, with one exception: when `GITHUB_ACTIONS=true`, print `::add-mask::<new token>` right after the refresh response is parsed, before any other use. Never print it in local mode.
- Response bodies are written to files in a `mktemp -d` directory, never to stdout. Temporary files are removed on exit (`trap`).
- `curl`, `jq` and `gh` are called by name from `PATH`, with a timeout on every `curl` and no redirect-following flag.

**Steps, in order.** Any failure exits non-zero right away, and nothing later runs. The destination is never touched before step 6.

1. **Validate inputs.** No network call yet. Messages name the variable, line or file, never a value.
   - Secret mode: all four variables are set and non-empty.
   - File mode: `FILE` is an existing regular file with exactly one `THREADS_ACCESS_TOKEN=` line and one `THREADS_USER_ID=` line. Their values are non-empty and unquoted (`KEY=value`, as in `.env.sample`).
   - Both modes: `THREADS_USER_ID` is digits only, and `curl` and `jq` (plus `gh` in secret mode) are on `PATH`.
2. **Check the destination.**
   - Secret mode: `gh secret list` succeeds. This catches a missing, expired or wrong-repository PAT before Meta is called. It can't prove write access, though: a read-only PAT passes here and fails at step 6.
   - File mode: the file and its directory are writable.
3. **Refresh** (exactly one request, never retried). Success needs all of these:
   - `curl` exited 0 and the status is HTTP 200;
   - the body is a JSON object;
   - `access_token` is a non-empty string with no whitespace or newline.

   Anything else fails. The only response details ever printed are the HTTP status and the integer `code`/`error_subcode` from either error shape, the same as `threadsdelete/api.py` reports. Never print `error_message`, `error.message`, other response text or the raw body. Then work out the report's days from `expires_in` if it's a positive integer; otherwise the report says "expiry not reported". A missing expiry doesn't fail the run, because the token itself is fine.
4. **Mask** (Actions only; see Token handling above).
5. **Verify.** `GET https://graph.threads.com/v1.0/me?fields=id` with the new token. Require `curl` exit 0, HTTP 200, a JSON object, and `id` equal to the expected user ID. On a mismatch, report only that the IDs differ.
6. **Save.**
   - Secret mode: pipe the new token on stdin to `gh secret set THREADS_ACCESS_TOKEN`. Never use `--body` or `-b`.
   - File mode: write a new file in the same directory with the `THREADS_ACCESS_TOKEN=` line replaced. Every other line stays byte-for-byte the same, including a missing final newline. Set mode 600, then `mv` it over the original, so a failure never leaves a half-written file.
7. **Report.** Print the destination ("repository secret" or the file path), the refresh time (UTC) and `expires_in` in whole days. In Actions, also append that line to `$GITHUB_STEP_SUMMARY`. Never print the token.

**Failure messages** depend on when the failure happened:
- **Before the refresh request (steps 1 and 2):** nothing changed. Fix the named cause, then run again.
- **During or after the refresh request (steps 3 to 6, including a `curl` error or timeout in step 3, when Meta may have processed it anyway):** the token's state may have changed, and the new value was not saved. Don't promise that running again fixes it. A refresh needs a token at least 24 hours old, and the old token may no longer work (§2). Tell the owner to check the stored token with a cleanup preview. If it fails authentication, replace the token by hand (`docs/META_SETUP.md` §5 and §8).

### 4.2 `.github/workflows/refresh-token.yml`

- `on`: `schedule` with cron `'0 6 1 * *'` (1st of each month, 06:00 UTC, never during the Friday 05:00 cleanup) and `workflow_dispatch` with no inputs. No `pull_request` or `pull_request_target`.
- Top-level `permissions: contents: read`, as in the other workflows. The secret write uses the PAT, not `GITHUB_TOKEN`.
- `concurrency: group: refresh-token`, `cancel-in-progress: false`.
- One job on `ubuntu-latest` with `timeout-minutes: 5`.
- Steps: `actions/checkout` pinned to the same SHA as the other workflows, with `persist-credentials: false`; then one step `name: Refresh token`, `shell: bash`, `run: ./scripts/refresh-token.sh`. No setup-uv and no Python.
- The step's `env` has exactly `THREADS_ACCESS_TOKEN: ${{ secrets.THREADS_ACCESS_TOKEN }}`, `THREADS_USER_ID: ${{ vars.THREADS_USER_ID }}`, `GH_TOKEN: ${{ secrets.SECRETS_WRITE_TOKEN }}` and `GH_REPO: ${{ github.repository }}`. No `${{ }}` inside `run`.
- The alert is GitHub's failed-workflow notification. It only arrives if the owner's Actions notifications are on. Scheduled runs notify whoever created the workflow, last changed its cron line, or last re-enabled it. Setup docs cover this (§6). No custom notification service.

## 5. Tests (offline)

New `tests/test_refresh_token.py` runs `scripts/refresh-token.sh` with `bash` in a temporary directory. The tests write fake `curl` and `gh` executables that record their arguments and stdin and return canned synthetic responses. Fake tokens, IDs and `.env` files only.

Isolation (the `tests/__init__.py` socket guard only covers Python, not subprocesses):
- Each run gets an environment built from scratch, never copied from `os.environ`. It contains only `PATH` (the fakes directory first, then system directories for `bash`, `jq` and coreutils), `HOME`, `TMPDIR` and `XDG_CONFIG_HOME` pointing into the temporary directory, and the case's synthetic inputs. So the owner's `gh` login, real tokens and `GITHUB_*` variables can't leak in.
- Before running a case, the test checks that `curl` and `gh` on that `PATH` resolve to the fakes.
- `jq` is a test prerequisite (§6). If it's missing, the test fails with a message saying so; it doesn't skip.

Both modes:
- No token appears in any recorded `curl` or `gh` argument, and the old token never appears in stdout or stderr.
- Refresh failures, each followed by no further operations, `curl` called once (no retry), and the destination unchanged:
  - an HTTP error in either error shape;
  - malformed JSON;
  - 200 without `access_token`;
  - an `access_token` containing a newline;
  - the fake `curl` exiting non-zero (transport error or timeout).
- An error body whose message contains a fake token-like string and a URL with `access_token=`: neither appears in output; the integer code does.
- A missing or non-integer `expires_in`: still saves, and the report says "expiry not reported".
- Verify failures (a different `id`, a non-200 status, malformed JSON, `curl` failing): fail, destination unchanged.
- Unknown arguments: exit 2, no `curl` or `gh` call.
- After success and after a failed refresh, `TMPDIR` holds no files the script left behind.

Secret mode:
- Success: `gh secret set THREADS_ACCESS_TOKEN` gets the new token on stdin; exit 0. With `GITHUB_ACTIONS=true` and `GITHUB_STEP_SUMMARY` set, the new token appears in output only in the single `::add-mask::` line, and the summary file has the days line.
- A missing input fails before any `curl` or `gh` call. A failed `gh secret list` fails with no `curl` call. A failed `gh secret set` exits non-zero.

File mode:
- Success: only the token line changes, all other lines are byte-for-byte the same (including a file with no final newline), the mode is 600, exit 0, no `gh` call, and no `::add-mask::` line. The new token never appears in output.
- A missing, duplicated or quoted `THREADS_ACCESS_TOKEN` or `THREADS_USER_ID` line, or a missing file, fails before any `curl` call, with the file unchanged.
- Environment values of `THREADS_ACCESS_TOKEN` and `THREADS_USER_ID` are ignored in favor of the file's.

`tests/test_workflows.py`:
- The shared tests (pinned SHAs, no expressions in `run`, no `pull_request_target`) cover every file in `.github/workflows/` instead of a fixed tuple.
- New refresh-workflow tests: schedule and dispatch, `permissions: contents: read`, `cancel-in-progress: false`, timeout, no `pull_request`, the exact four-key `env` mapping, a single `run: ./scripts/refresh-token.sh`, `persist-credentials: false`, and `secrets.` used only for the two named secrets.
- The cleanup and CI workflows stay unchanged. `ci.yml` still has no `secrets.`.

## 6. Rule and documentation changes

- `CLAUDE.md`:
  - Replace the `no-token-renewal-or-app-secret` bullet with the rules from §7.
  - Principles: "the Python package never refreshes tokens; only `scripts/refresh-token.sh` does".
  - Add `./scripts/refresh-token.sh` to the live commands that need the owner's say-so.
  - Under Commands, note that the offline tests need `jq` on `PATH`.
  - Add to "Checks by reading": no token in any process argument or output except the Actions `::add-mask::` line; mask before any other use; verify before saving; never retry the refresh; only this script writes `.env`, and only its `THREADS_ACCESS_TOKEN` line.
- `docs/RESEARCH.md`: update "This tool never exchanges or refreshes tokens", the "Consequence for v1" token line, and "this tool never calls them" (OAuth error shape) to match. Add an Unknown: refresh token-string rotation and old-token validity, to be recorded as `[live]` after the first runs. Keep every existing source, date and tag.
- `docs/META_SETUP.md` §8:
  - Automatic refresh in Actions as the default.
  - PAT setup: fine-grained, this repository only, "Secrets: read and write", expiry at most 1 year (calendar the renewal), saved as the `SECRETS_WRITE_TOKEN` repository secret. The PAT is a second credential that expires and is renewed by hand.
  - Failure alerts: in GitHub's notification settings, turn on Actions notifications (failed workflows only is enough). Scheduled-run alerts go to whoever created the workflow, last changed its cron line, or last re-enabled it.
  - The first manual dispatch: the current token must be at least 24 hours old. How to check it worked: `gh secret list` update time.
  - What to do after a failure, matching §4.1's failure messages.
  - Local refresh with `./scripts/refresh-token.sh --env-file .env`.
  - Shared vs separate tokens: until rotation behavior is known, refresh a shared token in only one place, or give local its own token by repeating §5. Keep the manual `curl` refresh as a fallback.
- `README.md`: the Token maintenance section (both commands), a GitHub Actions setup line for `SECRETS_WRITE_TOKEN`, and an inactivity note saying the refresh schedule is disabled too.
- `.env.sample`: the `THREADS_ACCESS_TOKEN` comment points to `./scripts/refresh-token.sh --env-file .env` instead of "Replace manually". No new keys.
- No change to `threadsdelete/` or `main.py`.

## 7. Kūkulu settings

In `docs/kukulu.json`, set `policies.archive` to `true` and `policies.finalize` to `"ready"`; keep the other policies at their defaults.

Copy `constraints` from `docs/flights/repost-removal/kukulu.json`, with these changes:
- Drop `"from": "P1-01"` from `no-unrepost-operation`.
- Replace `no-token-renewal-or-app-secret` with:
  - `no-token-refresh-outside-script`: `refresh_access_token|th_refresh_token` in `threadsdelete/`, `main.py`, `scripts/`, `.github/workflows/`, excluding `scripts/refresh-token.sh`.
  - `no-app-secret-or-exchange`: `th_exchange_token|client_secret|APP_SECRET` in `threadsdelete/`, `main.py`, `scripts/`, `.github/workflows/`.
- Add:
  - `secret-write-only-in-refresh-script`: `gh secret set` only in `scripts/refresh-token.sh`.
  - `no-shell-trace`: no `set -x`, `set -o xtrace` or `bash -x` in `scripts/` or `.github/workflows/`.
- Add `bash -n scripts/refresh-token.sh` to `extraVerify` under `scripts/`.

## 8. Done when

Build (checked during the flight):
- All commands in `CLAUDE.md` → Commands pass, `bash -n scripts/refresh-token.sh` passes, and CI is green.
- The §5 tests exist and pass. `threadsdelete/` and `main.py` are unchanged.

Owner, after merge (manual and live; not part of the flight's acceptance; in this order):
1. Create the PAT, add the `SECRETS_WRITE_TOKEN` secret, and check that Actions failure notifications are on (`docs/META_SETUP.md` §8).
2. With the current token at least 24 hours old, run "Refresh token" by manual dispatch. It succeeds, the summary shows the days line, no token appears in the log, and `gh secret list` shows `THREADS_ACCESS_TOKEN` just updated.
3. Run "Threads cleanup" by manual dispatch with `dry_run: true`. Authentication succeeds.

Steps 4 to 6 are recommended. They decide the shared-vs-separate token guidance, not whether the flight passes.

4. If the local `.env` holds the same token the secret held before step 2, run `DRY_RUN=true ./scripts/run.sh` with it, before refreshing it. This shows whether the old token survived the Actions refresh.
5. If it did, run `./scripts/refresh-token.sh --env-file .env` (the token must be at least 24 hours old), then preview locally again. If it didn't, give local its own token (`docs/META_SETUP.md` §5).
6. Record in `docs/RESEARCH.md` as `[live]` whether the token string changed and whether the old token stayed valid, and update the shared-vs-separate guidance in `docs/META_SETUP.md` §8 to match.
