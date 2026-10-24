# threadsdelete

Personal Threads cleanup tool (official Meta Threads API only) that removes the owner's own content by age, locally and from a weekly GitHub Actions cron. Source of truth: `docs/SPEC.md`.

## Principles

- [ ] Ruff lint + format and mypy (`strict`, untyped defs rejected) pass; every function in `threadsdelete/` and `main.py` is annotated.
- [ ] Documented Meta endpoints only, at an explicit API version; no scraping or unofficial APIs. API facts come from `docs/RESEARCH.md` § Contracts.
- [ ] Validate all configuration before any network activity. Booleans: case-insensitive `true`/`false` only; missing `DRY_RUN` → true.
- [ ] One UTC run-start time; eligible iff `action_at <= run_started_at - timedelta(days=DAYS_AGO)`. Posts/replies use creation time; likes/reposts use the owner's action time.
- [ ] Complete discovery and validation before any mutation; never mutate while paginating; dedupe by (operation, ID); sort by action time, category, ID.
- [ ] Abort mutation on incomplete discovery or ambiguous ownership; never touch another person's content.
- [ ] Dry run makes no mutation (any non-GET) and no token refresh.
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
| Budget measurements | `uv run python -c "from tests.test_budgets import report; report()"` |

Live commands (`./scripts/run.sh`, `uv run --env-file .env main.py`) need the owner's credentials: never run them during the build.

## Module map

| Location | Responsibility | May import |
| --- | --- | --- |
| `main.py` | argparse/`--help`, read `os.environ`, logging + `RedactingFilter`, capture `datetime.now(UTC)` once, build client, map exceptions → `ExitCode` | `threadsdelete.*` |
| `threadsdelete/config.py` | `load_config(env: Mapping) -> Config`, `ConfigError(problems)`, all `DEFAULT_*` constants, `ENV_KEYS` | stdlib |
| `threadsdelete/core.py` | `Category`, `Operation`, `OPERATION_FOR`, `Candidate`, `parse_timestamp`, `compute_cutoff`, `is_eligible`, `select_eligible`, `CategoryCounts`, `QuotaStatus`, `RunSummary`, `ExitCode` (OK 0, FAILURE 1, CONFIG 2, AUTH 3) | stdlib only, pure |
| `threadsdelete/api.py` | `API_HOST`, `Transport`, `ThreadsClient` (read retries, pagination `get_all`, `get_identity`, `discover`, `get_quota`, `remove`, `read_only` guard), `Identity`, `Quota`, `ApiError` family, `SUPPORTED_CATEGORIES`, `UNSUPPORTED_CATEGORIES`, `redact`, `RedactingFilter` | core, httpx |
| `threadsdelete/cleanup.py` | `verify_identity`, `discover_all`, `split_by_budget`, `run`, `exit_status`, report output | config, core, api |
| `scripts/run.sh` | `exec uv run [--env-file .env] main.py "$@"`; no logic | — |
| `tests/` | `__init__.py` (blocks sockets), `fakes.py` (`FakeThreadsApi`, `make_client`, `load_fixture`), `fixtures/*.json` (synthetic), `test_*.py` | app, unittest, httpx.MockTransport |
| `.github/workflows/` | `ci.yml` (offline checks), `cleanup-feed.yml` (schedule + dispatch) | — |

`ApiError` subclasses: `AuthError`, `ResponseError`, `ReadFailedError`, `QuotaExceededError`, `ItemError`, `UnknownOutcomeError`, `MutationBlockedError`, `OwnershipError`. The report's summary block starts with the exact line `=== Summary ===`.

## Constraints

Checked by `kukulu_verify` (ids in `docs/kukulu.json` `constraints`):

- `no-hardcoded-assumption-defaults`: the ⚠️ ASSUMPTION defaults (`MAX_DELETIONS_PER_RUN`, `HTTP_TIMEOUT_SECONDS`, `MAX_READ_RETRIES`, `MAX_RETRY_WAIT_SECONDS`) are literals only in `threadsdelete/config.py`.
- `core-is-pure`: `threadsdelete/core.py` imports no os/sys/time/socket/httpx/pathlib/io/logging, calls no `open(`, `sleep(`, `datetime.now(`.
- `no-wall-clock-in-package`: no `datetime.now(`/`time.time(` under `threadsdelete/`; `no-naive-now`: no `datetime.now()` or `utcnow(` anywhere.
- `httpx-only-in-api`, `single-http-client`: only `threadsdelete/api.py` imports httpx; no requests/urllib.request/http.client anywhere.
- `sleep-only-in-api`: only the read-retry loop sleeps, via its injected `sleep`.
- `no-token-in-logs`: no `print`/logger call takes the access token.
- `no-token-renewal-or-app-secret`: no refresh/exchange-token or app-secret code.
- `no-post-body-field`: never request the `text` field.
- `no-url-outside-api`, `no-redirects-or-insecure-tls`: URL literals only in api.py; no `follow_redirects=True`, no `verify=False`.
- `no-environ-in-package`: only `main.py` reads `os.environ`.
- `tests-no-real-transport`: tests never build a real transport or call `urlopen`.
- `actions-pinned-sha`, `cleanup-no-cancel-in-progress`, `no-expression-in-run`, `no-secrets-in-ci`, `no-pull-request-target`: workflow rules (SPEC section 6).

Reviewer checks by reading (structural, not a line pattern):

- Dry run constructs `ThreadsClient(read_only=True)`; no code path mutates in dry run.
- All discovery for all supported categories finishes before the first `remove` call.
- `remove` is called at most once per candidate per run; no retry wrapper around it.
- `scripts/run.sh` contains no cleanup logic; exit status is preserved (`exec`, `pipefail`).
- No `${{ }}` expression inside a multi-line `run: |` block (the `no-expression-in-run` pattern cannot see block context).
- Test fixtures are synthetic; `.env`, tokens and real account data are never committed.
- If any Bluesky source is adapted, its MIT notice is retained.

## Task protocols

**Research protocol (P1 tasks).** Fetch public documentation only (WebFetch/WebSearch or `curl -sL`); never use credentials or call the API with a token. Record each source with URL and retrieval date. Label findings `[doc]` or `[live]`. If a page cannot be retrieved, record the URL, date and failure, and carry SPEC section 9's starting evidence as "documentation finding, not revalidated". Never invent an endpoint, field or code; write `Unknown` instead. Time box: about 45 minutes of research per task.

**Research-contract protocol (code tasks).** Read `docs/RESEARCH.md` § Contracts before writing API code. Task text gives expected values (e.g. host `graph.threads.net`, `DELETE /{id}` returning `{"success": true}`); where RESEARCH differs, RESEARCH wins on API facts and SPEC wins on behavior. Implement only categories RESEARCH marks `Supported: yes`. Record any difference in the commit body under `Interpretation:`.

**Test protocol.** Tests are offline: use `tests.fakes.FakeThreadsApi` (an `httpx.MockTransport`) and import it as `from tests.fakes import ...` so `tests/__init__.py`'s socket guard loads. Fixtures in `tests/fixtures/` use fake IDs and usernames like `example_owner`. Assert behavior (requests made, counts, exit codes, key output lines), not whole-output snapshots.

**Tuning protocol (⚠️ ASSUMPTION keys).** 1) Run the task's measurement command with the current default; record the numbers. 2) Decide using the measurement plus `docs/RESEARCH.md`'s verified limits; change only the default constant in `threadsdelete/config.py` (or `timeout-minutes` in the workflow) and the matching `.env.sample`/README text. 3) Re-run and record. 4) Put `Measurement: <key> before=<…> after=<…> decision=<kept|changed> because <…>` in the commit body and the PROGRESS log entry, plus `Live measurement: pending (human)`.

**Pinned-action protocol.** Pin every `uses:` to a full 40-character commit SHA with the version in a trailing comment (`# v5.0.0`). Find it with `git ls-remote --tags https://github.com/<owner>/<repo>`, taking the peeled `^{}` SHA of the latest stable release tag. Never guess a SHA.

**Phase-end protocol.** Run the full verify set, `git push -u origin HEAD` (log a push failure; do not block on it), then append a log entry listing the task's manual checks verbatim, ending with `Manual check: NOT VERIFIED (human)`. Never perform live account actions.

## Commit template

```
<ID>: <title>

Goal: <one sentence>
Tests: <test files/names added or changed>
Interpretation: <choices made where SPEC/PLAN/RESEARCH allowed two readings, or "none">
Measurement: <tuning tasks only>
Manual check: <phase-end tasks: NOT VERIFIED (human); otherwise "none">
```

SPEC.md wins over PLAN.md, which wins over code comments.
