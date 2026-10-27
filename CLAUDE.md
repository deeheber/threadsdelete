# threadsdelete

Personal Threads cleanup tool using Meta's official API, locally or weekly through GitHub Actions.

Behavior: `docs/SPEC.md` overrides the original `docs/flights/threadsdelete/SPEC.md`; both override `docs/PLAN.md` during a flight, then code comments. "SPEC section N" means the original spec. API facts: `docs/RESEARCH.md` § Contracts overrides SPEC; SPEC wins on behavior.

Configuration is the five settings in README § Settings. Log level, API version, timeout and retry values are internal constants in `threadsdelete/config.py`. This overrides SPEC section 5 and the `LOG_LEVEL` rule in section 2 (issue #6).

Other flight files are archived decision history, except the current constraint rules named below. Check current code before relying on them.

## Principles

- [ ] Ruff lint + format and mypy (`strict`, untyped defs rejected) pass; every function in `threadsdelete/` and `main.py` is annotated.
- [ ] Documented Meta endpoints at an explicit API version; no scraping or unofficial APIs.
- [ ] Validate all configuration before any network activity. Booleans: case-insensitive `true`/`false` only; missing `DRY_RUN` → true.
- [ ] One UTC run-start time; eligible iff `action_at <= run_started_at - timedelta(days=DAYS_AGO)`. Posts/replies use creation time; likes/reposts use the owner's action time.
- [ ] Complete discovery and validation before any mutation; never mutate while paginating; dedupe by (operation, ID); sort by action time, category, ID.
- [ ] Abort mutation on incomplete discovery or ambiguous ownership; never touch another person's content.
- [ ] Dry run makes no mutation (any non-GET) and no token refresh.
- [ ] The Python package never refreshes tokens; only `scripts/refresh-token.sh` does. It checks the new token before saving it, never retries the refresh, and prints no token except the Actions `::add-mask::` line.
- [ ] Remove sequentially within the per-run cap and verified quota; report deferred work. Never retry a destructive request; unknown outcome is never success.
- [ ] Redact credentials everywhere; never fetch or log post bodies; never commit `.env`, tokens or real account data.
- [ ] Offline, behavior-focused tests; no coverage targets, getter tests, or formatting snapshots.
- [ ] Small design: no database, queue, hosted service, plugin framework, or social-network abstraction.

## Commands

| Purpose | Command |
| --- | --- |
| Install | `uv sync --locked` |
| Lockfile check | `uv lock --check` |
| Typecheck | `uv run mypy threadsdelete main.py` |
| Lint | `uv run ruff check .` |
| Format check | `uv run ruff format --check .` |
| Tests (offline) | `uv run python -m unittest discover -s tests -v` |
| One test module/class | `uv run python -m unittest tests.test_core -v` |
| Syntax check (build) | `uv run python -m compileall -q threadsdelete main.py` |
| Help smoke | `uv run main.py --help` |
| Refresh script syntax | `bash -n scripts/refresh-token.sh` |
| Budget measurements | `uv run python -c "from tests.test_budgets import report; report()"` |

The offline tests need `jq` on `PATH` (`tests/test_refresh_token.py` fails without it); `ubuntu-latest` runners ship it.

Live commands (`./scripts/run.sh`, `uv run --env-file .env main.py`, `./scripts/refresh-token.sh`) require the owner's authorization. Treat the checkout's `.env` as real credentials; anything reaching Meta is live. `./scripts/refresh-token.sh` run locally reads and rewrites that `.env` and calls Meta; only `bash -n` and the tests (which run a temporary copy against fake `curl`/`gh`) may touch it.

## Import boundaries

| Location | May import |
| --- | --- |
| `main.py` | `threadsdelete.*` |
| `threadsdelete/config.py` | stdlib |
| `threadsdelete/core.py` | stdlib only, pure |
| `threadsdelete/api.py` | core, httpx |
| `threadsdelete/cleanup.py` | config, core, api |
| `tests/` | app, unittest, httpx.MockTransport; subprocess runs of a temporary script copy against fake `curl`/`gh` |
| `scripts/refresh-token.sh` | bash (3.2-compatible), `curl`, `jq`, `gh` (Actions only); no Python |

## Constraints

Current rules: `constraints` in `docs/kukulu.json` during the token-refresh flight, archived afterwards to `docs/flights/token-refresh/kukulu.json`. The next flight's planner copies them from the newest archive to `docs/kukulu.json` for `kukulu_verify`:

- `no-hardcoded-assumption-defaults`: the ⚠️ ASSUMPTION defaults (`MAX_DELETIONS_PER_RUN`, `HTTP_TIMEOUT_SECONDS`, `MAX_READ_RETRIES`, `MAX_RETRY_WAIT_SECONDS`) are literals only in `threadsdelete/config.py`.
- `core-is-pure`: `threadsdelete/core.py` imports no os/sys/time/socket/httpx/pathlib/io/logging, calls no `open(`, `sleep(`, `datetime.now(`.
- `no-wall-clock-in-package`: no `datetime.now(`/`time.time(` under `threadsdelete/`; `no-naive-now`: no `datetime.now()` or `utcnow(` anywhere.
- `httpx-only-in-api`, `single-http-client`: only `threadsdelete/api.py` imports httpx; no requests/urllib.request/http.client anywhere.
- `sleep-only-in-api`: only the read-retry loop sleeps, via its injected `sleep`.
- `no-token-in-logs`: no `print`/logger call takes the access token.
- `no-token-refresh-outside-script`: `refresh_access_token`/`th_refresh_token` appear in `threadsdelete/`, `main.py`, `scripts/`, `.github/workflows/` only inside `scripts/refresh-token.sh`.
- `no-app-secret-or-exchange`: no `th_exchange_token`, `client_secret` or `APP_SECRET` in those paths.
- `secret-write-only-in-refresh-script`: `gh secret set` only in `scripts/refresh-token.sh` (docs and tests are not scanned).
- `no-shell-trace`: no `set -x`, `set -o xtrace` or `bash -x` (including combined flags like `set -euxo`) in `scripts/` or `.github/workflows/`, not even in a comment.
- `curl-q-first`, `no-curl-redirects`: under `scripts/`, every `curl` has `-q` as its first argument on the same line; no `-L`/`--location`.
- `no-secret-body-flag`, `no-awk-v`, `no-token-in-url-args`: no `gh secret set --body`/`-b`, no `awk -v`, no `access_token=$...` in a URL or `--data` argument; tokens go through stdin or `ENVIRON`.
- `no-post-body-field`: never request the `text` field.
- `no-url-outside-api`, `no-redirects-or-insecure-tls`: in the Python package, URL literals appear only in `threadsdelete/api.py`; under `scripts/`, only `scripts/refresh-token.sh` may contain URLs (the two `graph.threads.com` URLs of the token-refresh SPEC §4.1); no `follow_redirects=True`, no `verify=False`.
- `no-environ-in-package`: only `main.py` reads `os.environ`.
- `tests-no-real-transport`: tests never build a real transport or call `urlopen`.
- `actions-pinned-sha`, `cleanup-no-cancel-in-progress`, `no-expression-in-run`, `no-secrets-in-ci`, `no-pull-request-target`: workflow rules (SPEC section 6).
- `no-reposted-post-id`: nothing in `threadsdelete/` or `main.py` requests, reads or names `reposted_post`; a repost is removed by its own record `id`.
- `no-unrepost-operation`: no `Operation.UNREPOST`/`"unrepost"`; reposts map to `Operation.DELETE`.

Checks by reading (no line pattern catches these):

- Dry run constructs `ThreadsClient(read_only=True)`; no code path mutates in dry run.
- All discovery for all supported categories finishes before the first `remove` call.
- `remove` is called at most once per candidate per run; no retry wrapper around it.
- `scripts/run.sh` contains no cleanup logic; exit status is preserved (`exec`, `pipefail`).
- No `${{ }}` expression inside a multi-line `run: |` block (the `no-expression-in-run` pattern flags `run:` lines and bare shell lines, allows any other `key: ...${{ }}` mapping such as `group: ci-${{ github.ref }}`, and cannot see block context).
- Test fixtures are synthetic; `.env`, tokens and real account data are never committed.
- If any Bluesky source is adapted, its MIT notice is retained.
- `scripts/refresh-token.sh`: no token in any process argument or output except the Actions `::add-mask::` line; the mask is printed before any other use of the new token; the new token is verified (`/me` id) before saving; the refresh request is sent once, never retried; only this script writes `.env`, and only its `THREADS_ACCESS_TOKEN` line; nothing is printed from a response body except the HTTP status and integer error codes.

## Conventions

- **Tests:** use `tests.fakes.FakeThreadsApi` (an `httpx.MockTransport`), imported as `from tests.fakes import ...` so `tests/__init__.py`'s socket guard loads. Fixtures use fake IDs and usernames like `example_owner`.
- **ASSUMPTION defaults:** change one only with a measurement (`report()` above) and matching README text; update `.env.sample` too when changing a user setting. Timeout and retry values are internal constants; live measurements are still pending.
- **Pinned actions:** pin every `uses:` to a full 40-character commit SHA with the version in a trailing comment (`# v5.0.0`). Get it from `git ls-remote --tags https://github.com/<owner>/<repo>` (the peeled `^{}` SHA of the latest stable tag). Never guess a SHA.
- **Kūkulu policies:** every flight sets `policies.archive` to `true` and `policies.finalize` to `"ready"` in `docs/kukulu.json`, unless that flight's spec says otherwise.

## Flight token-refresh notes

Builds `scripts/refresh-token.sh` and `.github/workflows/refresh-token.yml` (`docs/SPEC.md`, issue #5). In this flight's PLAN, `SPEC 4.1` (a bare number) means `docs/SPEC.md`; "original SPEC section N" means `docs/flights/threadsdelete/SPEC.md`. No change to `threadsdelete/` or `main.py`.

### Task protocols

**Live safety.** Never run `./scripts/refresh-token.sh`, `./scripts/run.sh`, `gh secret ...` or `gh workflow ...` from this checkout. Allowed: `bash -n scripts/refresh-token.sh` and the offline tests.

**Refresh script contract** (P1-01, P1-02):
- `mode` is set once: `if [ "${GITHUB_ACTIONS:-}" = "true" ]; then mode=actions; else mode=local; fi`.
- Exit 2 for a step 1 or 2 failure (stderr ends `Nothing was changed. Fix the cause and run again.`). Exit 1 for a step 3 to 6 failure (stderr text contains `may have changed` and `docs/META_SETUP.md`). Exit 0 on success. Every error line starts `refresh-token: `.
- curl, every call: `printf '%s' "$token" | curl -q --silent --show-error --max-time 30 --get --data-urlencode 'access_token@-' --output "$work/<name>.json" --write-out '%{http_code}' "$URL" 2>"$work/<name>.err"`. The URLs are `https://graph.threads.com/refresh_access_token?grant_type=th_refresh_token` and `https://graph.threads.com/v1.0/me?fields=id`. curl stderr and `gh` output are never printed.
- `gh` argv is exactly `secret list`, or `secret set THREADS_ACCESS_TOKEN` with the token on stdin.
- Exit codes: `rc=0; cmd || rc=$?`. The `trap cleanup EXIT` body uses only `if` blocks and ends `return 0` (a failing last trap command turns exit 0 into 1).
- bash 3.2: no `mapfile`, `declare -A`, `${v,,}`, or empty `"${a[@]}"` under `set -u`.

**Refresh test harness** (`tests/test_refresh_token.py`):
- Copy the script to `<tmp>/scripts/`.
- Fakes `curl`/`gh` live in `<tmp>/fakebin/`, with shebang `#!` + `sys.executable` and the record and response paths baked into their text. `jq` is symlinked there from `shutil.which("jq")`; if jq is missing, `self.fail(...)`, never skip.
- `PATH=<tmp>/fakebin:/usr/bin:/bin`. The environment is built from scratch (`PATH`, `HOME`, `TMPDIR`, `XDG_CONFIG_HOME` under `<tmp>`, plus the case's inputs), never copied from `os.environ`.
- Assert that `curl` and `gh` resolve to the fakes before each run, and never drop a fake from `PATH`.
- Synthetic values only: tokens `FAKE-OLD-TOKEN-aaaa1111`/`FAKE-NEW-TOKEN-bbbb2222`, PAT `FAKE-PAT-cccc3333`, user `1000001`.

**Executable bit.** `chmod +x scripts/refresh-token.sh` before `git add`; `git ls-files -s scripts/refresh-token.sh` must show `100755`.

**Phase end.** Run the full verify set and the build command, then `git push -u origin HEAD`. Copy the task's manual-check text verbatim into the log, then add `Manual check: NOT VERIFIED (human)`. Fix nothing in this task: if a check fails, block with the failing command. A log-only task gets an empty commit whose subject is `<ID>: <title>` (`kukulu_task_done` needs that subject).

### Commit template

```
<ID>: <title>

Goal: <one sentence>
Tests: <test names added or changed, or "none (docs)">
Interpretation: <choices where SPEC or PLAN allowed two readings, or "none">
Manual check: <what a human must check, or "none">
```

SPEC.md wins over PLAN.md, which wins over code comments.
