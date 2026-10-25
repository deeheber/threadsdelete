# threadsdelete

Personal Threads cleanup tool (official Meta Threads API only) that removes the owner's own content by age, locally and from a weekly GitHub Actions cron. Source of truth: `docs/flights/threadsdelete/SPEC.md` (the original build) plus `docs/SPEC.md` (the current change, which wins where they differ); both win over code comments. "SPEC section N" references in code and `docs/RESEARCH.md` mean the original spec.

## Principles

- [ ] Ruff lint + format and mypy (`strict`, untyped defs rejected) pass; every function in `threadsdelete/` and `main.py` is annotated.
- [ ] Documented Meta endpoints only, at an explicit API version; no scraping or unofficial APIs. API facts come from `docs/RESEARCH.md` § Contracts, which wins over SPEC on API facts; SPEC wins on behavior.
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

Live commands (`./scripts/run.sh`, `uv run --env-file .env main.py`) need the owner's credentials: never run them without the owner's say-so.

## Import boundaries

| Location | May import |
| --- | --- |
| `main.py` | `threadsdelete.*` |
| `threadsdelete/config.py` | stdlib |
| `threadsdelete/core.py` | stdlib only, pure |
| `threadsdelete/api.py` | core, httpx |
| `threadsdelete/cleanup.py` | config, core, api |
| `tests/` | app, unittest, httpx.MockTransport |

## Constraints

Checked by `kukulu_verify` during a flight (current rule definitions: `docs/flights/repost-removal/kukulu.json` `constraints`; the first build's: `docs/flights/threadsdelete/kukulu.json`):

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
- `no-reposted-post-id`: nothing in `threadsdelete/` or `main.py` requests, reads or names `reposted_post`; a repost is removed by its own record `id`.
- `no-unrepost-operation`: no `Operation.UNREPOST`/`"unrepost"`; reposts map to `Operation.DELETE`.

Checks by reading (no line pattern catches these):

- Dry run constructs `ThreadsClient(read_only=True)`; no code path mutates in dry run.
- All discovery for all supported categories finishes before the first `remove` call.
- `remove` is called at most once per candidate per run; no retry wrapper around it.
- `scripts/run.sh` contains no cleanup logic; exit status is preserved (`exec`, `pipefail`).
- No `${{ }}` expression inside a multi-line `run: |` block (the `no-expression-in-run` pattern cannot see block context; its one exception is `ci.yml`'s exact `group: ci-${{ github.ref }}` line).
- Test fixtures are synthetic; `.env`, tokens and real account data are never committed.
- If any Bluesky source is adapted, its MIT notice is retained.

## Conventions

- **Tests:** use `tests.fakes.FakeThreadsApi` (an `httpx.MockTransport`), imported as `from tests.fakes import ...` so `tests/__init__.py`'s socket guard loads. Fixtures use fake IDs and usernames like `example_owner`.
- **ASSUMPTION defaults:** change one only with a measurement (`report()` above) and the matching `.env.sample` and README text; live measurements are still pending.
- **Pinned actions:** pin every `uses:` to a full 40-character commit SHA with the version in a trailing comment (`# v5.0.0`). Get it from `git ls-remote --tags https://github.com/<owner>/<repo>` (the peeled `^{}` SHA of the latest stable tag). Never guess a SHA.

## Flight repost-removal notes

Scope: `docs/SPEC.md` v1.0 (issue #4) makes reposts a supported category. No new config keys, no ⚠️ ASSUMPTION changes. `docs/RESEARCH.md` and `docs/META_SETUP.md` are already up to date and are not edited.

- **No live commands.** A real `.env` with the owner's credentials is in the checkout. Never run `./scripts/run.sh`, `uv run --env-file .env main.py` or anything that reaches Meta.
- **Repost facts** (RESEARCH § Category: reposts):
  - Reposts are `/me/threads` records with `media_type == "REPOST_FACADE"`, and that check comes before `is_quote_post`.
  - The action time is the record's `timestamp`.
  - Ownership is checked as for posts: `owner` must be a dict whose `id` equals the identity `user_id`, otherwise `OwnershipError`.
  - A repost is removed by `DELETE /{record id}`; `reposted_post` is never used.
  - An already-deleted repost answers error 100 subcode 33, which is an `ItemError`.
- **Categories:** `SUPPORTED_CATEGORIES = (POST, QUOTE, REPOST, REPLY)` and `UNSUPPORTED_CATEGORIES = {LIKE: ...}`. `OPERATION_FOR[REPOST] = Operation.DELETE`, so reposts share the cap and the delete quota; `Operation.UNLIKE` stays.
- **Unchanged files:** `threadsdelete/cleanup.py` and `main.py` need no change; the `Excluded:` and summary lines follow the category tuples. If a task seems to need them, block it instead.
- **Fixtures:**
  - Account `1000001`/`example_owner`; test run start `2026-10-23T05:00:00Z`; `DAYS_AGO` 90; cutoff `2026-07-25T05:00:00Z`.
  - The default `fixture_api()` has 5 eligible items (`9000001, 7000001, 9000002, 9000003, 9000004`). Repost `9000005` (2026-09-30) is ineligible.
  - `fixture_api(eligible_repost=True)` adds `tests.fakes.ELIGIBLE_REPOST` (`9000007`, 2026-05-15), which sorts last.
  - Default counts are POST `(4,3,3)`, QUOTE `(1,1,1)`, REPOST `(1,0,0)`, REPLY `(2,1,1)` (scanned, eligible, would_remove).
- **Switch-on rule:** the full suite runs after every task. The commit that adds `REPOST` to `SUPPORTED_CATEGORIES` must also carry the fixture change and every test edit that it breaks.
- **Phase-end protocol:**
  1. Run the full verify set plus `uv run python -m compileall -q threadsdelete main.py`.
  2. Run `git push -u origin HEAD`; record `Push: ok` or the failure.
  3. Copy the task's manual-check text verbatim into the log, then the line `Manual check: NOT VERIFIED (human)`.
  4. Never block a later task on a manual check.

### Commit template

```
<ID>: <title>

Goal: <one sentence>
Tests: <test names added or changed>
Interpretation: <choices made where the task allowed two readings, or "none">
Manual check: <none | NOT VERIFIED (human): what the owner must check>
```

SPEC.md (`docs/SPEC.md`, then `docs/flights/threadsdelete/SPEC.md`) wins over `docs/PLAN.md`, which wins over code comments.
