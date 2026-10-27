# threadsdelete token refresh build plan

Derived from docs/SPEC.md v1.0 on 2026-10-26. SPEC.md wins over this file.

## Decisions

- Phases → SPEC defines none, so the plan derives one phase, "Phase 1 — Token refresh": script with the local destination, then the Actions destination, then the workflow, then documentation, then the phase-end push. Rationale: the change is one bash script, one workflow and docs; a scaffold or polish phase would be empty.
- Task split → P1-01 builds every shared step of `scripts/refresh-token.sh` plus the local `.env` destination, and P1-02 adds the Actions destination (`gh`, mask). Both touch only the script and `tests/test_refresh_token.py`. Rationale: each task is a complete, testable destination, and a smaller commit is easier to review. Between the two tasks, the Actions branch fails at step 1 with exit 2 and a "not available yet" message, and nothing tests that stub.
- "One `if`/`else` on `GITHUB_ACTIONS`" (SPEC 4.1) → the script sets `mode=actions` or `mode=local` once, at the top, with a single `if [ "${GITHUB_ACTIONS:-}" = "true" ]; then ... else ... fi`. Later steps branch on `$mode`, and nothing else reads `GITHUB_ACTIONS`. Rationale: the destination is decided in exactly one place.
- Exit statuses → 2 for every failure before the refresh request (steps 1 and 2: nothing changed), 1 for every failure from step 3 on, 0 on success. Rationale: SPEC says only "non-zero". Using 2 matches `main.py`'s "invalid configuration, nothing used". Tests assert these exact codes.
- Failure messages → all go to stderr, prefixed `refresh-token: `. A step 1 or 2 failure ends with the sentence `Nothing was changed. Fix the cause and run again.` A step 3 to 6 failure ends with a fixed text that contains `may have changed`, says any new token was not saved, says that running again may not fix it (a refresh needs a token at least 24 hours old, and the old token may no longer work), and tells the owner to check the stored token with a cleanup preview and, if it fails authentication, replace it by hand (`docs/META_SETUP.md` sections 5 and 8). Tests assert `Nothing was changed`, `may have changed` and `docs/META_SETUP.md`.
- curl shape → every call is `printf '%s' "$token" | curl -q --silent --show-error --max-time 30 --get --data-urlencode 'access_token@-' --output "$work/<name>.json" --write-out '%{http_code}' '<URL>' 2>"$work/<name>.err"`. The status is captured from stdout. The URLs are the literals `https://graph.threads.com/refresh_access_token?grant_type=th_refresh_token` and `https://graph.threads.com/v1.0/me?fields=id`. curl's stderr goes to a file in the temporary directory and is never printed, because curl's own messages are the one place a URL could leak. Only curl's exit code is printed. Rationale: SPEC 4.1 token handling. A fixed shape also lets the test fakes interpret calls without guessing.
- curl timeout → the literal `--max-time 30` on each call. No variable is named after an ASSUMPTION key (`no-hardcoded-assumption-defaults` scans `scripts/`). Rationale: SPEC 4.1 requires a timeout but marks no ⚠️ ASSUMPTION and adds no setting, and the script cannot read `threadsdelete/config.py`.
- `gh` output → `gh secret list` and `gh secret set` write their stdout and stderr to files in the temporary directory, never to the log. On failure the script prints the `gh` exit code and a hint about the PAT. Rationale: the same "print nothing you did not choose" rule as curl.
- `.env` parsing → a key line is one that starts exactly with `THREADS_ACCESS_TOKEN=` or `THREADS_USER_ID=`. Lines starting with `#`, `export ` or whitespace do not count. The value is the raw text after the first `=`, with no quote stripping. The local token value must not contain whitespace (this includes a CR from CRLF line endings) or a `"` or `'` character. In Actions, the token must not contain whitespace. Rationale: SPEC 4.1 step 1 says exactly one line with a non-empty value. Rejecting a quoted or CRLF value before the network avoids a wasted refresh, which would print the misleading "may have changed" message.
- New-token validation → done inside `jq -e` (`(.access_token|type)=="string" and (.access_token|length)>0 and (.access_token|test("\\s")|not)`) before the value is extracted with `jq -r`. Rationale: command substitution strips trailing newlines, so a check after extraction would miss a token that ends in a newline.
- Error details → the code comes from `.error.code` when `.error` is an object, otherwise from the top-level `.code`. The subcode comes from `.error.error_subcode` or `.error_subcode` in the same way. Each is printed only if jq yields an integer and the bash value matches digits only. Rationale: SPEC 4.1 step 3, with both error shapes.
- Verify comparison → `jq -e --arg id "$user_id" '(.id|type)=="string" and .id == $id'`. The user ID is not a secret (it is a repository Variable), so passing it as an argument is allowed. Rationale: Graph returns `id` as a string, and a number fails loudly.
- Temporary files → `umask 077` first. `trap cleanup EXIT` is set before anything is created. `work=$(mktemp -d)` holds every response. The `.env` rewrite uses `env_tmp=$(mktemp .env.XXXXXX)` in the repository root, then `NEW_TOKEN="$new_token" awk '...ENVIRON["NEW_TOKEN"]...' .env >"$env_tmp"`, `chmod 600`, `mv -f "$env_tmp" .env`. `cleanup` uses only `if` blocks and `rm -f`/`rm -rf`, and ends with `return 0`. Rationale: under `set -e`, a trap whose last command fails turns exit 0 into exit 1 (checked on bash 3.2: `[ -n "" ] && rm -f x` as the last line of the trap makes a successful run exit 1).
- Test harness → Python fakes for `curl` and `gh`, written into `<tmp>/fakebin/` with an absolute shebang (`#!` + `sys.executable`). The record-file and response-file paths are baked into the fake's text, because SPEC's environment allowlist has no slot for a helper variable. The test `PATH` is `<tmp>/fakebin:/usr/bin:/bin`, with a symlink `<tmp>/fakebin/jq` pointing at `shutil.which("jq")`. bash is `shutil.which("bash", path=PATH)`, which is macOS `/bin/bash` 3.2 locally. Rationale: SPEC 5 isolation. Symlinking jq avoids putting a directory that also holds the owner's real `gh` (such as `/opt/homebrew/bin`) on `PATH`.
- `jq` in CI → `ubuntu-latest` images ship `jq`, so `.github/workflows/ci.yml` stays unchanged, as SPEC 5 requires.
- Workflow → workflow name and step name `Refresh token`, job id `refresh`. P1-03 gives the full file text. P1-03 depends on nothing: its tests read YAML text only.
- Docs depend on P1-02 and P1-03, so the README and setup guide never describe a script or workflow that did not land (as in the last flight).
- CLAUDE.md → SPEC 6's CLAUDE.md edits are made by the planner in this plan commit, together with `docs/kukulu.json`'s constraints, so rules and checks agree from the first task. No task edits CLAUDE.md.
- Constraints → copied from `docs/flights/repost-removal/kukulu.json` with SPEC 7's changes: `from` dropped on `no-unrepost-operation`, `no-url-outside-api` widened to `scripts/` with `scripts/refresh-token.sh` excluded, `no-token-renewal-or-app-secret` replaced by `no-token-refresh-outside-script` and `no-app-secret-or-exchange`, and `secret-write-only-in-refresh-script` and `no-shell-trace` added. Five more line rules turn SPEC 4.1's mechanical token-transport rules into checks: `curl-q-first`, `no-curl-redirects`, `no-secret-body-flag`, `no-awk-v` and `no-token-in-url-args`. Rationale: a rule stated only in prose has to be grepped by hand every round. The other SPEC 4.1 rules stay "checks by reading".
- `extraVerify["scripts/"]` → `bash -n scripts/run.sh` and `{ "cmd": "bash -n scripts/refresh-token.sh", "from": "P1-01" }`, with no `test -f` guard.
- `docs/kukulu.json` policies → `archive: true`, `finalize: "ready"` (SPEC 7). Every other policy keeps its default.
- ⚠️ ASSUMPTION keys → SPEC adds none and changes none, so there are no tuning tasks.
- Parallel streams → none. Two tasks share the script and its test file, and the rest are small.
- Live commands → none in any task. A real `.env` with the owner's credentials sits in the repository root. No task runs `./scripts/refresh-token.sh`, `./scripts/run.sh`, `uv run --env-file .env main.py`, `gh secret ...` or any request to Meta or GitHub. Only `bash -n` and the tests (which run a temporary copy against fakes) touch the script.

## Conventions

- Commit title `<ID>: <title>`; body per `CLAUDE.md` § Flight token-refresh notes → Commit template.
- "SPEC 4.1" etc. means a section of `docs/SPEC.md` (token refresh). "Original SPEC section N" means `docs/flights/threadsdelete/SPEC.md`.
- Synthetic values used throughout: old token `FAKE-OLD-TOKEN-aaaa1111`, new token `FAKE-NEW-TOKEN-bbbb2222`, PAT `FAKE-PAT-cccc3333`, environment-only token `FAKE-ENV-TOKEN-dddd4444`, leak probe `FAKE-LEAK-TOKEN-eeee5555`, user ID `1000001`, other user ID `2000002`, repository `example-owner/threadsdelete`.

## Phase 1 — Token refresh

### P1-01: Refresh script with the local .env destination

**Goal:** Add `scripts/refresh-token.sh` with every shared step and the local `.env` destination, plus the offline fake-`curl` test harness and the local and shared tests.
**Files touched:** `scripts/refresh-token.sh` (new, mode 100755), `tests/test_refresh_token.py` (new)
**Design constraints:** SPEC 4.1 (all of it) and SPEC 5 (Isolation, Both destinations, Local). Follow the refresh-script protocol in `CLAUDE.md` § Flight token-refresh notes; the essentials are restated here.

Script shape, in this order:
1. `#!/usr/bin/env bash`, `set -euo pipefail`, `umask 077`, `cd "$(dirname "$0")/.."`. No arguments. Never `set -x`; do not even write `set -x`, `xtrace` or `bash -x` in a comment (`no-shell-trace`).
2. `REFRESH_URL='https://graph.threads.com/refresh_access_token?grant_type=th_refresh_token'` and `ME_URL='https://graph.threads.com/v1.0/me?fields=id'`. These are the only URLs.
3. `if [ "${GITHUB_ACTIONS:-}" = "true" ]; then mode=actions; else mode=local; fi`. This is the only read of `GITHUB_ACTIONS`. In this task, `mode=actions` fails at step 1 with `die_before "GitHub Actions mode is not available yet."` (P1-02 replaces it).
4. `work=""`, `env_tmp=""`, then `cleanup()`: `if [ -n "$env_tmp" ]; then rm -f "$env_tmp"; fi`, `if [ -n "$work" ]; then rm -rf "$work"; fi`, `return 0`. Then `trap cleanup EXIT`. Never use `[ ... ] && ...` as a trap line: under `set -e` it turns exit 0 into 1.
5. `die_before MSG`: prints `refresh-token: MSG Nothing was changed. Fix the cause and run again.` to stderr and exits 2. `die_after MSG`: prints `refresh-token: MSG` followed by this text, then exits 1: "The token's state may have changed, and any new token was not saved. Running again may not fix it: a refresh needs a token at least 24 hours old, and the old token may no longer work. Check the stored token with a cleanup preview (DRY_RUN=true ./scripts/run.sh locally, or the Threads cleanup workflow with dry_run true); if it fails authentication, replace it by hand (docs/META_SETUP.md sections 5 and 8)." Messages name a variable, line or file, never a value.
6. Step 1, local: `.env` must exist (`.env not found in the repository root.`). For each of `THREADS_ACCESS_TOKEN` and `THREADS_USER_ID`, count `^KEY=` lines with `n=$(grep -c '^KEY=' .env || true)`; it must be exactly 1 (message names the key and says "missing" or "more than one ... line"). Read the value with `sed -n 's/^KEY=//p' .env`. It must be non-empty. The token value must not contain whitespace, `"` or `'` (`case` with `*[[:space:]\"\']*`); the message says it must be one unquoted value with no spaces. Environment values of these two keys are ignored. Both modes: `THREADS_USER_ID` is digits only (`case $id in ''|*[!0-9]*)`). `command -v curl` and `command -v jq` must succeed (`curl is not on PATH.`).
7. `work=$(mktemp -d)`.
8. Step 2, local: `[ -w .env ]` and `[ -w . ]`, else `die_before`.
9. Step 3, refresh, exactly once and never retried: `rc=0; status=$(printf '%s' "$old_token" | curl -q --silent --show-error --max-time 30 --get --data-urlencode 'access_token@-' --output "$work/refresh.json" --write-out '%{http_code}' "$REFRESH_URL" 2>"$work/refresh.err") || rc=$?`. Fail with `die_after` when `rc` is not 0 (`Refresh request failed (curl exit N).`), the status is not `200` (`Refresh failed: HTTP S` plus `, error code C` and ` subcode X` when present), the body is not a JSON object (`jq -e 'type=="object"'`), or the `jq -e` token check fails (`(.access_token|type)=="string" and (.access_token|length)>0 and (.access_token|test("\\s")|not)`). Only after the check passes, read `new_token=$(jq -r '.access_token' "$work/refresh.json")`. Error codes: `jq -r '(if (.error|type)=="object" then .error.code else .code end) | if type=="number" and .==floor and .>=0 then tostring else empty end' FILE 2>/dev/null || true`, and the same with `error_subcode`. Keep a value only if it is all digits. Never print `error_message`, `error.message`, any other body text, or the curl stderr file. `expires_in` is not read. Send all jq stderr to `/dev/null`.
10. Step 4, mask: `if [ "$mode" = actions ]; then printf '::add-mask::%s\n' "$new_token"; fi` (stdout). This never runs locally.
11. Step 5, verify: the same curl shape with `"$new_token"` on stdin, `$ME_URL`, `$work/me.json` and `$work/me.err`. It requires curl exit 0, status `200`, a JSON object, and `jq -e --arg id "$user_id" '(.id|type)=="string" and .id == $id'`. On a mismatch, the message is `Verify failed: the new token's account ID differs from THREADS_USER_ID.` and names neither ID. Every verify failure uses `die_after`.
12. Step 6, local save: `env_tmp=$(mktemp .env.XXXXXX)`; `NEW_TOKEN="$new_token" awk '/^THREADS_ACCESS_TOKEN=/ { print "THREADS_ACCESS_TOKEN=" ENVIRON["NEW_TOKEN"]; next } { print }' .env >"$env_tmp"`; `chmod 600 "$env_tmp"`; `mv -f "$env_tmp" .env`; then `env_tmp=""`. Each command `|| die_after "Saving to .env failed."`. Never `awk -v` (`no-awk-v`).
13. Step 7: `printf 'Token refreshed and saved to .env\n'` (stdout), with no period.

Capture every external exit code with `rc=0; cmd || rc=$?`, never with `if ! cmd; then rc=$?`, because `$?` is then 0. Bash 3.2 rules: no `mapfile`/`readarray`, `declare -A`, `${var,,}`/`${var^^}`, `[[ =~ ]]` captures, or `"${arr[@]}"` on a possibly empty array. Prefer plain variables and `case`. The token never appears in any argument: no `access_token=$...` and no `--data "...$token"` (`no-token-in-url-args`), and `-q` is the first argument of every `curl`, on the same line as `curl` (`curl-q-first`). No `-L`/`--location` (`no-curl-redirects`). Keep the script under about 200 lines.

Test harness in `tests/test_refresh_token.py` (stdlib only: `unittest`, `subprocess`, `tempfile`, `shutil`, `json`, `os`, `stat`, `sys`, `pathlib`). Start with `import tests  # noqa: F401` so `tests/__init__.py`'s socket guard loads (`discover -s tests` imports the module as `test_refresh_token`, not through the package).
- Each case gets `tmp = tempfile.TemporaryDirectory()`. Copy the real script to `<tmp>/scripts/refresh-token.sh` (mode 0o755). Create `<tmp>/home`, `<tmp>/tmp`, `<tmp>/xdg` and `<tmp>/fakebin`. Symlink `<tmp>/fakebin/jq` to `shutil.which("jq")`. If that is `None`, call `self.fail("jq must be on PATH to run tests/test_refresh_token.py (see CLAUDE.md Commands)")`; never skip.
- Fake `curl` (`<tmp>/fakebin/curl`, mode 0o755, first line `#!` + `sys.executable`; the absolute paths of `<tmp>/calls.jsonl` and `<tmp>/responses/` are written into its text as string literals). It reads all of stdin. It names the endpoint `refresh` if any argument contains `refresh_access_token`, `me` if any argument contains `/v1.0/me`, otherwise `unknown`. It appends `{"tool": "curl", "args": argv[1:], "stdin": ..., "endpoint": ...}` as one JSON line, then loads `<tmp>/responses/<endpoint>.json` (`{"status": int, "body": str, "exit": int}`; exit 99 if missing). If `exit` is non-zero, it exits with that code and writes nothing. Otherwise it writes `body` to the path after `--output` or `-o`, prints the status (no newline) if `--write-out` or `-w` was given, and exits 0.
- Fake `gh` (written in P1-01 so that `PATH` checks pass in both modes; used from P1-02 on). It records `{"tool": "gh", "args", "stdin"}` the same way. For `secret list` it prints a synthetic line and exits with `responses/gh.json`'s `list_exit` (default 0). For `secret set` it exits with `set_exit` (default 0). Anything else exits 99.
- Environment built from scratch, never from `os.environ`. `PATH=<tmp>/fakebin:/usr/bin:/bin`; `HOME`, `TMPDIR` and `XDG_CONFIG_HOME` point at the three directories; then the case's inputs. Local cases leave `GITHUB_ACTIONS` unset. Before each run, assert `shutil.which("curl", path=PATH)` and `shutil.which("gh", path=PATH)` equal the fakes. Never remove a fake from `PATH`: a real `gh` or `curl` would then be reached.
- Run `subprocess.run([shutil.which("bash", path=PATH), "<tmp>/scripts/refresh-token.sh"], env=env, cwd=<tmp>/home, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, check=False)`. `cwd` is not the root, which proves the `cd`. Return the exit code, stdout, stderr and the parsed call records.
- Write a helper that takes `mode` (`"local"` now, `"actions"` from P1-02) so the shared tests can loop over a module-level `MODES = ("local",)`. Local "destination unchanged" means the `.env` bytes are identical and no `<tmp>/.env.*` file exists.
- Synthetic `.env` (default): `# synthetic test file\nDRY_RUN=true\nTHREADS_ACCESS_TOKEN=FAKE-OLD-TOKEN-aaaa1111\nTHREADS_USER_ID=1000001\nDAYS_AGO=90\n`, mode 0o644. Default responses: refresh `200` `{"access_token": "FAKE-NEW-TOKEN-bbbb2222", "token_type": "bearer", "expires_in": 5183944}`, me `200` `{"id": "1000001"}`.
**Acceptance tests:** all in `tests/test_refresh_token.py`.

`ScriptFileTests::test_script_is_executable_and_strict`: the real `scripts/refresh-token.sh` has its owner execute bit set (`os.access(..., os.X_OK)`) and contains `set -euo pipefail`.

`LocalRefreshTests`:
- `test_success_rewrites_only_token_line`. Expect:
  - exit 0, and stdout contains `Token refreshed and saved to .env`;
  - the new `.env` lines equal the old ones, except that the token line is `THREADS_ACCESS_TOKEN=FAKE-NEW-TOKEN-bbbb2222`, and the mode is `0o600`;
  - exactly two curl calls: `refresh` with stdin `FAKE-OLD-TOKEN-aaaa1111`, then `me` with stdin `FAKE-NEW-TOKEN-bbbb2222`;
  - no `gh` call, no `::add-mask::` in stdout, and neither token in stdout or stderr;
  - `<tmp>/tmp` is empty, and there is no `<tmp>/.env.*` file.
- `test_missing_final_newline_is_added`: the default file without its final `\n` gives the same lines, and the result ends with `\n`.
- `test_environment_values_are_ignored`: the environment sets `THREADS_ACCESS_TOKEN=FAKE-ENV-TOKEN-dddd4444` and `THREADS_USER_ID=2000002`. The run succeeds, the refresh stdin is the file's old token, and `FAKE-ENV-TOKEN-dddd4444` appears in no record.
- `test_invalid_env_file_fails_before_network`: one subTest per case:
  - no `.env`;
  - no token line;
  - two token lines;
  - `THREADS_ACCESS_TOKEN=` with an empty value;
  - a token containing a space;
  - a token in double quotes;
  - a token line ending in `\r`;
  - no user ID line;
  - two user ID lines;
  - an empty user ID;
  - user ID `12a4`.

  Each case: exit 2, no `curl` or `gh` record, `.env` bytes unchanged (or still absent), stderr contains `Nothing was changed`, and the old token is not in stderr.
- `test_unwritable_env_fails_before_network`: `.env` mode `0o444`. Expect exit 2, no record, and the file unchanged. Skip only when `os.geteuid() == 0`, because root ignores file modes.

`BothDestinationTests` (loops `for mode in MODES` with `subTest(mode=mode)`):
- `test_refresh_failures_stop_before_any_other_call`: one subTest per refresh response:
  - HTTP 400 `{"error_type": "OAuthException", "code": 190, "error_message": "Invalid token"}`;
  - HTTP 400 `{"error": {"message": "x", "type": "OAuthException", "code": 190, "error_subcode": 460}}`;
  - HTTP 200 body `{"access_token": `;
  - HTTP 200 `[]`;
  - HTTP 200 `{"token_type": "bearer", "expires_in": 5183944}`;
  - HTTP 200 `{"access_token": "FAKE-NEW-TOKEN\nbbbb2222"}` (a JSON `\n` escape);
  - HTTP 200 `{"access_token": ""}`;
  - fake curl exit 28;
  - fake curl exit 7.

  Each case: exit 1, exactly one curl record (`refresh`) and nothing after it, the destination unchanged, stderr contains `may have changed`, and no `::add-mask::` line. For the two error shapes, stderr also contains `HTTP 400` and `190` (and `460` for the Graph shape). For the curl exits, stderr contains `curl exit 28` or `curl exit 7`.
- `test_error_message_text_is_never_printed`: each of the two error shapes, with message text (`error_message`, or `error.message` and `error.error_user_msg`) of `Invalid token FAKE-LEAK-TOKEN-eeee5555 see https://graph.threads.com/x?access_token=FAKE-LEAK-TOKEN-eeee5555` and code 190. Stdout plus stderr contain neither `FAKE-LEAK-TOKEN` nor `access_token=`, and stderr contains `190`.
- `test_verify_failures_leave_destination_unchanged`: the refresh succeeds and the `me` response is one of:
  - `200 {"id": "2000002"}`;
  - `200 {}`;
  - `200 {"id": 1000001}`;
  - `400 {"error": {"code": 190}}`;
  - `200` with body `not json`;
  - fake curl exit 28.

  Each case: exit 1, exactly two curl records, the destination unchanged, and stderr contains `may have changed`. The mismatch cases mention `differs`, and stderr contains neither `2000002` nor `1000001`. Locally, the new token is not in the output.
- `test_tokens_never_in_arguments_and_curl_starts_with_q`, on a successful run:
  - no argument of any record contains either token (or the PAT);
  - every curl record's `args[0] == "-q"`;
  - every curl call includes `--max-time`, `--get` and `--data-urlencode` followed by `access_token@-`, and includes neither `-L` nor `--location`;
  - the refresh URL argument is exactly `https://graph.threads.com/refresh_access_token?grant_type=th_refresh_token`, and the `me` URL argument is exactly `https://graph.threads.com/v1.0/me?fields=id`;
  - the old token is in neither stdout nor stderr.
**Out of scope:** the Actions destination (`gh secret list`/`set`, mask; P1-02); workflows; docs; `.env.sample`; `threadsdelete/`, `main.py`, `scripts/run.sh`, `tests/fakes.py` and every other test file. Never run `./scripts/refresh-token.sh` from the checkout (it would read the real `.env` and call Meta). Only `bash -n` and the tests touch it.
**Verification:** before committing, `chmod +x scripts/refresh-token.sh`, then `git add` and check that `git ls-files -s scripts/refresh-token.sh` starts with `100755`. Run the full verify set (`kukulu_verify`, including `bash -n scripts/refresh-token.sh` and the `curl-q-first`, `no-curl-redirects`, `no-awk-v`, `no-token-in-url-args`, `no-shell-trace` rules), then `uv run python -m unittest tests.test_refresh_token -v` (under macOS `/bin/bash` 3.2 locally). Never run the script itself.
**Depends on:** none

### P1-02: Actions destination for the refresh script

**Goal:** Make `scripts/refresh-token.sh` refresh the `THREADS_ACCESS_TOKEN` repository secret when `GITHUB_ACTIONS=true`: validate the four inputs, check the PAT with `gh secret list`, mask the new token, and save it with `gh secret set` on stdin.
**Files touched:** `scripts/refresh-token.sh`, `tests/test_refresh_token.py`
**Design constraints:** SPEC 4.1 (Where it saves, Token handling, steps 1, 2, 4, 6 and 7 for Actions) and SPEC 5 (Actions, Both destinations). Follow the refresh-script protocol in `CLAUDE.md` § Flight token-refresh notes. The script from P1-01 already has `mode` set once from `GITHUB_ACTIONS`, `die_before` (exit 2, "Nothing was changed") and `die_after` (exit 1, "may have changed"), a `trap cleanup EXIT` that ends with `return 0`, the refresh and verify curl calls, and the step 4 mask line. Replace the `GitHub Actions mode is not available yet.` stub with:
- Step 1, Actions: `THREADS_ACCESS_TOKEN`, `THREADS_USER_ID`, `GH_TOKEN` and `GH_REPO` must each be set and non-empty (`${VAR:-}`). The message names the variable. The token must not contain whitespace. `THREADS_USER_ID` is digits only (shared check). `command -v gh` must succeed, as well as curl and jq. `.env` is never read or written in Actions mode.
- Step 2, Actions: `rc=0; gh secret list >"$work/gh-list.out" 2>&1 || rc=$?`. A non-zero `rc` calls `die_before "gh secret list failed (exit N). Check that the SECRETS_WRITE_TOKEN secret holds an unexpired fine-grained PAT for this repository with Secrets: read and write."`. This runs before any curl call. `GH_REPO` selects the repository; pass no `--repo` flag.
- Step 4: the existing `printf '::add-mask::%s\n' "$new_token"` runs right after the refresh response passes its checks, before the verify call. It is the only place a token is printed.
- Step 6, Actions: `rc=0; printf '%s' "$new_token" | gh secret set THREADS_ACCESS_TOKEN >"$work/gh-set.out" 2>&1 || rc=$?`. The arguments are exactly `secret set THREADS_ACCESS_TOKEN`, never `--body` or `-b` (`no-secret-body-flag`). A non-zero `rc` calls `die_after "gh secret set failed (exit N); the PAT may lack Secrets: read and write."`.
- Step 7, Actions: `printf 'Token refreshed and saved to the repository secret\n'`.

`gh` output files are never printed. Bash 3.2 rules and the curl rules from P1-01 still apply. Never write `set -x` or `xtrace`, not even in a comment.

Tests: set `MODES = ("local", "actions")`, so every `BothDestinationTests` test also runs in Actions mode. In Actions mode, "destination unchanged" means that no `gh secret set` record exists and no `<tmp>/.env` was created. The record list begins with `gh secret list`, so the "exactly one curl record" assertions count curl records only. A refresh failure prints no `::add-mask::` line. A verify failure prints exactly one `::add-mask::` line, and the new token appears in no other output line. The Actions environment adds `GITHUB_ACTIONS=true`, `THREADS_ACCESS_TOKEN=FAKE-OLD-TOKEN-aaaa1111`, `THREADS_USER_ID=1000001`, `GH_TOKEN=FAKE-PAT-cccc3333` and `GH_REPO=example-owner/threadsdelete`. Write no `.env` unless a test says so.
**Acceptance tests:** in `tests/test_refresh_token.py`:

`ActionsRefreshTests`:
- `test_success_sets_secret_from_stdin`:
  - the records are, in order: `gh` `["secret", "list"]`, curl `refresh` (stdin old token), curl `me` (stdin new token), `gh` `["secret", "set", "THREADS_ACCESS_TOKEN"]` with stdin exactly `FAKE-NEW-TOKEN-bbbb2222`;
  - exit 0, and stdout contains `Token refreshed and saved to the repository secret`;
  - the only stdout or stderr line containing the new token is exactly `::add-mask::FAKE-NEW-TOKEN-bbbb2222`;
  - neither the old token nor the PAT appears in the output;
  - `<tmp>/.env` does not exist, and `<tmp>/tmp` is empty.
- `test_env_file_is_ignored_in_actions`: a synthetic `.env` with `THREADS_ACCESS_TOKEN=FAKE-ENV-TOKEN-dddd4444` exists. The run succeeds, the refresh stdin is the environment's old token, and the `.env` bytes are unchanged.
- `test_missing_input_fails_before_any_call`: for each of the four variables, unset and set to an empty string, plus `THREADS_USER_ID=12a4`. Each case exits 2 with no records, and stderr contains `Nothing was changed` and the variable's name.
- `test_failed_secret_list_stops_before_refresh`: with `list_exit` 1, the run exits 2, the records are exactly one `gh secret list`, and stderr contains `Nothing was changed`.
- `test_failed_secret_set_exits_non_zero`: with `set_exit` 1, the run exits 1, and stderr contains `may have changed` and `gh secret set failed`. The new token appears only in the single `::add-mask::` line.

`BothDestinationTests`: all four tests from P1-01 pass for both modes.
**Out of scope:** the workflow file and `tests/test_workflows.py` (P1-03); docs; `threadsdelete/`, `main.py`, `scripts/run.sh`. Never call the real `gh` or run the script from the checkout. Never remove the fake `gh` from the test `PATH`.
**Verification:** the full verify set (`kukulu_verify`, including `bash -n scripts/refresh-token.sh`, `secret-write-only-in-refresh-script`, `no-secret-body-flag`), then `uv run python -m unittest tests.test_refresh_token -v`. `git ls-files -s scripts/refresh-token.sh` still shows `100755`.
**Depends on:** P1-01

### P1-03: Monthly refresh workflow

**Goal:** Add `.github/workflows/refresh-token.yml`, which runs `./scripts/refresh-token.sh` monthly and on manual dispatch, and make the shared workflow tests cover every workflow file.
**Files touched:** `.github/workflows/refresh-token.yml` (new), `tests/test_workflows.py`
**Design constraints:** SPEC 4.2 and SPEC 5 (`tests/test_workflows.py`). Original SPEC section 6 (GitHub Actions). Constraints `actions-pinned-sha`, `no-expression-in-run`, `no-pull-request-target`, `no-shell-trace`, `no-token-refresh-outside-script` (the workflow must not contain `refresh_access_token` or `th_refresh_token`), `no-app-secret-or-exchange` and `secret-write-only-in-refresh-script` apply. Use exactly this file content. The checkout SHA is the one already used by the other workflows; never look up or change it.

```yaml
name: Refresh token

on:
  schedule:
    - cron: '0 6 1 * *'
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: refresh-token
  cancel-in-progress: false

jobs:
  refresh:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - name: Refresh token
        shell: bash
        run: ./scripts/refresh-token.sh
        env:
          THREADS_ACCESS_TOKEN: ${{ secrets.THREADS_ACCESS_TOKEN }}
          THREADS_USER_ID: ${{ vars.THREADS_USER_ID }}
          GH_TOKEN: ${{ secrets.SECRETS_WRITE_TOKEN }}
          GH_REPO: ${{ github.repository }}
```

`tests/test_workflows.py` changes:
- Add `REFRESH = (WORKFLOWS / "refresh-token.yml").read_text()` and `ALL = {path.name: path.read_text() for path in sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])}`.
- Move `test_no_expressions_inside_run_scripts` from `CleanupWorkflowTests` to `SharedWorkflowTests`, unchanged except that it loops over `ALL.items()` with `subTest(name=...)`.
- Make `test_all_actions_pinned_to_full_sha` loop over `ALL`.
- Keep every cleanup and CI assertion. `.github/workflows/cleanup-feed.yml` and `ci.yml` are not edited.
**Acceptance tests:** in `tests/test_workflows.py`:

`SharedWorkflowTests`:
- `test_all_actions_pinned_to_full_sha` (updated: every file in `ALL`).
- `test_no_expressions_inside_run_scripts` (moved: every file in `ALL`).
- `test_no_pull_request_target_in_any_workflow` (new): `pull_request_target` is in no file of `ALL`.
- `test_every_workflow_is_covered` (new): `{"ci.yml", "cleanup-feed.yml", "refresh-token.yml"} <= set(ALL)`.
- `test_ci_runs_offline_checks_without_secrets` (unchanged; `ci.yml` still has no `secrets.`).

`RefreshWorkflowTests`:
- `test_schedule_dispatch_permissions_concurrency_and_timeout`:
  - `- cron: '0 6 1 * *'` is present;
  - `(?m)^  workflow_dispatch:\s*$` matches, and `inputs:` is absent;
  - `(?m)^permissions:\n  contents: read$` matches;
  - `group: refresh-token` and `(?m)^  cancel-in-progress: false$` match, and `cancel-in-progress: true` is absent;
  - `(?m)^    timeout-minutes: 5$` and `runs-on: ubuntu-latest` match;
  - `pull_request` is absent.
- `test_single_step_runs_script_with_exact_env`:
  - `env_mappings(REFRESH)` equals `{"THREADS_ACCESS_TOKEN": "${{ secrets.THREADS_ACCESS_TOKEN }}", "THREADS_USER_ID": "${{ vars.THREADS_USER_ID }}", "GH_TOKEN": "${{ secrets.SECRETS_WRITE_TOKEN }}", "GH_REPO": "${{ github.repository }}"}`;
  - `re.findall(r"(?m)^\s+(?:- )?run:\s*(.+)$", REFRESH) == ["./scripts/refresh-token.sh"]`;
  - the step after `- name: Refresh token` contains `shell: bash`;
  - `GITHUB_ACTIONS`, `setup-uv`, `uv ` and `python` are absent.
- `test_checkout_pinned_like_other_workflows_without_credentials`: the `uses:` references in `REFRESH` are exactly one, equal to the `actions/checkout@...` reference in `cleanup-feed.yml`, and `persist-credentials: false` is present.
- `test_only_named_secrets_used`: `sorted(re.findall(r"secrets\.(\w+)", REFRESH)) == ["SECRETS_WRITE_TOKEN", "THREADS_ACCESS_TOKEN"]`.
**Out of scope:** `scripts/refresh-token.sh`; `cleanup-feed.yml` and `ci.yml`; docs; any `gh workflow` or `gh secret` command, or any push of secrets. Never look up a new action SHA.
**Verification:** the full verify set (`kukulu_verify`, including `actions-pinned-sha`, `no-expression-in-run`, `no-pull-request-target`), then `uv run python -m unittest tests.test_workflows -v`. `git diff --stat main -- .github/workflows/ci.yml .github/workflows/cleanup-feed.yml` prints nothing.
**Depends on:** none

### P1-04: Setup guide and research notes for automatic refresh

**Goal:** Update `docs/META_SETUP.md` §8 and `docs/RESEARCH.md` to describe the refresh script and workflow, the PAT, failure alerts and recovery, and record the open rotation question.
**Files touched:** `docs/META_SETUP.md`, `docs/RESEARCH.md`, `README.md` (the one §8 anchor link only)
**Design constraints:** SPEC 6 (`docs/RESEARCH.md` and `docs/META_SETUP.md` §8 bullets), SPEC 2 (facts), SPEC 4.1 (failure messages), SPEC 4.2 (alerts). Use placeholders only (`<LONG_LIVED_TOKEN>`, `<APP_SECRET>`), never real IDs or tokens. The current behavior to describe:
- the workflow is "Refresh token" (`.github/workflows/refresh-token.yml`): cron `0 6 1 * *`, the 1st of each month at 06:00 UTC, plus manual dispatch;
- the script is `scripts/refresh-token.sh`. In Actions it saves to the `THREADS_ACCESS_TOKEN` secret. Locally it rewrites only the `THREADS_ACCESS_TOKEN=` line of the repository's `.env`, and needs `curl` and `jq`;
- exit 2 means nothing changed (fix and rerun), and exit 1 means the token's state may have changed.

`docs/META_SETUP.md`:
1. Retitle §8 to `## 8. Expiry and refresh`, and change the one link to the old anchor (`README.md` § Token maintenance: `docs/META_SETUP.md#8-expiry-and-manual-renewal`) to `docs/META_SETUP.md#8-expiry-and-refresh`. Change nothing else in `README.md` (P1-05 rewrites that section).
2. Automatic refresh in Actions is the default.
3. PAT setup: a fine-grained token, this repository only, repository permission "Secrets: read and write", expiry at most 1 year (calendar the renewal), saved as the repository secret `SECRETS_WRITE_TOKEN`. The PAT is a second credential that expires and is renewed by hand.
4. Failure alerts: in GitHub's notification settings, turn on Actions notifications (failed workflows only is enough). Scheduled-run alerts go to whoever created the workflow, last changed its cron line, or last re-enabled it.
5. The first manual dispatch needs a current token at least 24 hours old. Check that it worked from the run log's "Token refreshed and saved to the repository secret" line and the `gh secret list` update time of `THREADS_ACCESS_TOKEN`.
6. After a failure, follow the two cases of SPEC 4.1's failure messages: before the refresh request (fix the named cause, then run again), or during or after it (check the stored token with a cleanup preview; if it fails authentication, replace it by hand via §5 and the manual refresh below).
7. Local refresh: run `./scripts/refresh-token.sh`; it rewrites the token line in the repository's `.env`. To refresh the repository secret, run the workflow instead.
8. Shared versus separate tokens: until rotation behavior is known, refresh a shared token in only one place, or give local its own token by repeating §5.
9. Keep the manual `curl` refresh as a fallback.
10. Keep the 90-day grant note: public profiles are extended by refreshing; private-profile users re-authorize every 90 days (step 5a).
11. Update the intro line ("Steps 8 and 9 come from Meta's documentation") to say that automatic refresh is not yet live-verified.

`docs/RESEARCH.md`, keeping every existing source, date and `[doc]`/`[live]` tag:
1. Replace "This tool never exchanges or refreshes tokens (SPEC non-goal) ..." with: the cleanup tool never exchanges or refreshes tokens; `scripts/refresh-token.sh` calls the refresh endpoint (monthly in Actions, or on demand locally), and the exchange stays a manual step in `docs/META_SETUP.md`.
2. Replace the "Consequence for v1" token line: the "Refresh token" workflow refreshes the Actions secret monthly, `./scripts/refresh-token.sh` refreshes the local `.env`, and an expired or unrefreshed token still makes the cleanup exit 3.
3. In § Contracts → Errors, replace "but this tool never calls them" with: `scripts/refresh-token.sh` calls the refresh endpoint and reads both shapes, printing only the HTTP status and the integer `code`/`error_subcode`.
4. In § Comparison with blueskydelete, change "Threads needs a manually replaced long-lived user token (60 days)" to say that the token is refreshed monthly by the workflow (or locally by the script).
5. Add under § Untested and pending: whether refresh returns a different token string, and whether the old token stays valid afterwards. Record as `[live]` after the first runs.
6. Record SPEC 2's re-read: the long-lived-tokens page (re-read 2026-10-25) confirms the refresh endpoint and success fields (`access_token`, `token_type`, `expires_in`). Also record GitHub's facts as documentation findings: `GITHUB_TOKEN` cannot write repository secrets, a fine-grained PAT with "Secrets: read and write" can, and Actions sets `GITHUB_ACTIONS=true`.
**Acceptance tests:** none (documentation task).
**Out of scope:** `README.md` beyond the §8 anchor fix; `.env.sample`; code, scripts, workflows, tests; `docs/flights/`; recording any live result (the owner does that after merge, per SPEC 8 step 6).
**Verification:** the full verify set; `grep -n "never exchanges or refreshes\|this tool never calls them" docs/RESEARCH.md` prints nothing; `grep -rn "8-expiry-and-manual-renewal" README.md docs/*.md` prints nothing; `grep -n "SECRETS_WRITE_TOKEN" docs/META_SETUP.md` shows the PAT setup.
**Depends on:** P1-02, P1-03

### P1-05: README and .env.sample for token refresh

**Goal:** Update `README.md` (Token maintenance, Actions setup, inactivity note) and the `.env.sample` token comment for the refresh script and workflow.
**Files touched:** `README.md`, `.env.sample`
**Design constraints:** SPEC 6 (`README.md` and `.env.sample` bullets), SPEC 4.2. Facts to use: the workflow "Refresh token" runs on the 1st of each month at 06:00 UTC (`cron: '0 6 1 * *'`), and also on manual dispatch. It needs the repository secret `SECRETS_WRITE_TOKEN` (a fine-grained PAT, this repository only, "Secrets: read and write"; see `docs/META_SETUP.md` §8). The local command is `./scripts/refresh-token.sh`; it needs `curl` and `jq`, and rewrites only the token line of `.env`. Edits:
1. `## Token maintenance`: replace "the tool does not renew them" with: the "Refresh token" workflow refreshes the Actions secret monthly, and `./scripts/refresh-token.sh` refreshes the local `.env` (it is live: it calls Meta and rewrites `.env`). Link to `docs/META_SETUP.md#8-expiry-and-refresh` (the anchor P1-04 created) and keep the revocation link.
2. `## Scheduled cleanup with GitHub Actions`: "Two workflows" becomes three, adding `refresh-token.yml` (monthly token refresh). After the Secret step, add a step for the repository Secret `SECRETS_WRITE_TOKEN`.
3. The inactivity bullet ("scheduled workflows are disabled after 60 days without repository activity") also says that the refresh schedule is disabled too, so a token can then expire. Re-enable both workflows.
4. `.env.sample`: the `THREADS_ACCESS_TOKEN` comment says to refresh it with `./scripts/refresh-token.sh` before it expires (60 days), instead of "Replace manually". Add no new keys, and keep every other line unchanged.

No real IDs or tokens. Keep every other section as it is.
**Acceptance tests:** none (documentation task). The existing tests must still pass (`tests/test_config.py` may read `.env.sample`).
**Out of scope:** `docs/META_SETUP.md`, `docs/RESEARCH.md`, code, scripts, workflows, tests, `docs/flights/`.
**Verification:** the full verify set; `grep -n "does not renew" README.md` prints nothing; `grep -n "Replace manually" .env.sample` prints nothing; `grep -n "SECRETS_WRITE_TOKEN" README.md` shows the setup step; `git diff main -- .env.sample` changes only the one comment line.
**Depends on:** P1-02, P1-03

### P1-06: Phase 1 close — push and manual checks

**Goal:** Run the build check, push the branch, and record the owner's manual checks from SPEC 8.
**Files touched:** `docs/PROGRESS.md` (log entry only)
**Design constraints:** SPEC 8 (Done when). Follow the phase-end protocol in `CLAUDE.md` § Flight token-refresh notes. Never run a live command: a real `.env` exists in the checkout.
**Acceptance tests:** none.
**Out of scope:** code or doc changes; fixing a failing check (block the task with the failing command instead); running `./scripts/refresh-token.sh`, `./scripts/run.sh`, `uv run --env-file .env main.py`, or any `gh secret`/`gh workflow` command.
**Verification:**
1. Run the full verify set, `uv run python -m compileall -q threadsdelete main.py` and `bash -n scripts/refresh-token.sh`. Check that `git diff --stat main -- threadsdelete main.py` prints nothing (SPEC 8: unchanged).
2. Run `git push -u origin HEAD`, and record a failure in the log if it fails.
3. Write a log entry that lists, verbatim, the following, then `Manual check: NOT VERIFIED (human)`:
   "Owner, after merge, in order:
   (1) create the PAT, add the SECRETS_WRITE_TOKEN secret, and check that Actions failure notifications are on (docs/META_SETUP.md §8);
   (2) with the current token at least 24 hours old, run "Refresh token" by manual dispatch and check that the log shows the "saved to the repository secret" line and no token, and that gh secret list shows THREADS_ACCESS_TOKEN just updated;
   (3) run "Threads cleanup" by manual dispatch with dry_run true and check that authentication succeeds.
   Recommended:
   (4) if the local .env held the same token, run DRY_RUN=true ./scripts/run.sh before refreshing it locally;
   (5) if that worked, run ./scripts/refresh-token.sh locally and preview again; otherwise give local its own token (§5);
   (6) record in docs/RESEARCH.md as [live] whether the token string changed and the old token stayed valid, and update the shared-vs-separate guidance in docs/META_SETUP.md §8.
   Also confirm CI is green on the pull request."
**Depends on:** none

## Spec issues

- SPEC 4.1 requires only a "non-zero" exit status. Resolution: 2 before the refresh request (nothing changed), 1 from the refresh on (see Decisions).
- SPEC 4.1 step 1 does not say how `.env` values are parsed. `uv`'s `--env-file` strips quotes and accepts `export`, but this script reads the raw text after `KEY=`. Resolution: lines must start exactly with `KEY=`. A token value with whitespace (including a CRLF `\r`) or a quote character fails step 1, so a mismatch fails before any request instead of after it.
- SPEC 4.1 relies on `curl --data-urlencode 'access_token@-'` reading the token from stdin without a trailing newline. This is documented curl behavior. The tests prove only that the script pipes the right stdin to the fake; the real encoding is first exercised by the owner's SPEC 8 step 2.
- SPEC 4.1 says "every `curl` call starts with `-q` as its first argument". The `curl-q-first` line rule can only see `-q` on the same line as `curl`, so the plan requires that layout. The tests check the real argument order.
- SPEC 5 says the test `PATH` holds "system directories for bash, jq and coreutils". Resolution: `<tmp>/fakebin:/usr/bin:/bin`, with `jq` symlinked into `fakebin`. This avoids putting a directory that also holds the owner's real `gh` (Homebrew) on `PATH`.
- SPEC 4.1 says "One `if`/`else` on `GITHUB_ACTIONS`", but several steps differ by destination. Resolution: `mode` is set once from that single `if`/`else`, and later steps branch on `$mode`.
- SPEC 6 lists three `docs/RESEARCH.md` edits. § Comparison with blueskydelete also says the token is "manually replaced", which would then be wrong. Resolution: P1-04 updates that line too.
- SPEC 6 does not mention `docs/META_SETUP.md`'s §8 heading ("Expiry and manual renewal"), which no longer fits. Resolution: P1-04 retitles it "Expiry and refresh" and fixes the anchor links.
- SPEC 8 "CI is green" cannot be observed by the implementer. Resolution: the reviewer checks the pull request's CI, and P1-06 lists it as a manual check.
- The local step 2 writability check cannot be tested as root. Resolution: that one test skips when `os.geteuid() == 0` (CI runners are not root). This is not the `jq` prerequisite, which never skips.
- SPEC 7's constraint list does not cover SPEC 4.1's `-q`, redirect, `--body` and `awk -v` rules, or tokens in URLs, although each is a single-line pattern. Resolution: five extra rules (see Decisions). The rest of SPEC 4.1 stays "checks by reading" in `CLAUDE.md`.

## Review fixes (round 1)

### R1-01: Refresh-script tests for duplicate lines, root writability, recovery text and Actions whitespace

**Goal:** Make tests/test_refresh_token.py kill four surviving mutants of scripts/refresh-token.sh, so these SPEC requirements are actually tested: SPEC 4.1 step 1, exactly one THREADS_ACCESS_TOKEN= and THREADS_USER_ID= line (SPEC 5 Local, duplicated line); SPEC 4.1 step 2, the repository root is writable; SPEC 4.1 Failure messages, where a step 3 to 6 failure tells the owner to check with a cleanup preview and replace by hand via docs/META_SETUP.md and does not promise that running again fixes it (PLAN Decisions: tests assert docs/META_SETUP.md); PLAN P1-02 step 1, the Actions token must not contain whitespace. The script is correct for all four. Change tests only.
**Files touched:** tests/test_refresh_token.py
**Design constraints:** SPEC 4.1 and SPEC 5 isolation rules, unchanged: the environment is built from scratch, the fakes stay first on PATH and are checked before each run, synthetic values only, and jq missing means fail, never skip. Never run scripts/refresh-token.sh from the checkout. Only `import tests  # noqa: F401` plus the stdlib.
**Acceptance tests:** In tests/test_refresh_token.py: (1) test_invalid_env_file_fails_before_network: the 'two tokens' and 'two users' subtests also assert 'more than one' in stderr. Add the cases f'THREADS_ACCESS_TOKEN={OLD}\nTHREADS_ACCESS_TOKEN=\n' + uid and tok + uid + 'THREADS_USER_ID=\n' (a duplicate whose second value is empty, which the whitespace and digits checks cannot catch). Each exits 2 with no records, the file unchanged, and 'more than one' in stderr. Every case also asserts 'may have changed' is not in stderr. (2) New LocalRefreshTests.test_unwritable_repository_root_fails_before_network: after the files are written, chmod <tmp> to 0o555. Register addCleanup to set 0o755 back before any other cleanup runs, so TemporaryDirectory removal works. Expect exit 2, no curl or gh record (the harness may need to read records safely while the root is read-only; a fake that cannot write calls.jsonl must make the run fail, not pass), .env bytes unchanged and 'Nothing was changed' in stderr. Skip only when os.geteuid() == 0. (3) test_refresh_failures_stop_before_any_other_call and test_verify_failures_leave_destination_unchanged: stderr contains 'docs/META_SETUP.md' and 'cleanup preview', and does not contain 'run again' (case-insensitive). (4) ActionsRefreshTests.test_missing_input_fails_before_any_call: add THREADS_ACCESS_TOKEN values 'FAKE OLD' and 'FAKE-OLD\r', each exiting 2 with no records and 'THREADS_ACCESS_TOKEN' and 'Nothing was changed' in stderr.
**Out of scope:** Any change to scripts/refresh-token.sh, which already behaves correctly; the workflows; docs; threadsdelete/, main.py and every other test file. Do not add a readability check for .env (advisory note only).
**Verification:** Run kukulu_verify (full set, including bash -n scripts/refresh-token.sh). Then re-run each of these four mutants with kukulu_mutate (file scripts/refresh-token.sh, targeted 'unit', filter 'tests.test_refresh_token') and expect killed: (a) delete the line `    if [ "$n" -gt 1 ]; then die_before ".env has more than one $key line."; fi`; (b) delete the line `  [ -w . ] || die_before "the repository root is not writable."`; (c) replace ` Check the stored token with a cleanup preview (DRY_RUN=true ./scripts/run.sh locally, or the Threads cleanup workflow with dry_run true); if it fails authentication, replace it by hand (docs/META_SETUP.md sections 5 and 8).` with ` Run again.`; (d) replace `    *[[:space:]]*) die_before "THREADS_ACCESS_TOKEN must not contain whitespace." ;;` with `    '#never#') die_before "THREADS_ACCESS_TOKEN must not contain whitespace." ;;`.
**Depends on:** none
