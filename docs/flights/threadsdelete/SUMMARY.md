# Build summary: threadsdelete

**Merge:** `build/2026-10-24`, base `c29457c` → head `1de1416`, 60 commits, 2 reviews, final verdict **APPROVED** (review 2).

## What was built

**Phase 1 — Feasibility (P1-01..P1-04).** `docs/RESEARCH.md` records dated Meta documentation findings on access, fees, permissions, token lifecycle, per-category contracts (enumeration, timestamps, ownership, removal), pagination, errors and quota. The flight decided `Decision: GO` on documentation evidence alone: no API fee is documented, own-account use works via an app role/tester, and `DELETE /{id}` removes the owner's posts. Every finding is `[doc]`; nothing was observed live.

**Phase 2 — Local preview (P2-01..P2-09).** A uv/Python 3.14 project with strict mypy and Ruff, and an offline test harness with a socket guard. It has strict config validation (`threadsdelete/config.py`, `.env.sample`), pure candidate/eligibility logic (`threadsdelete/core.py`), and an httpx-based `ThreadsClient` (`threadsdelete/api.py`). The client provides trusted-host requests, cursor pagination, bounded read retries, a read-only guard and token redaction. It also handles per-category discovery with ownership checks: posts, media/carousel parents, quotes and replies are supported, while reposts and likes are excluded with reasons. On top of these sit a dry-run preview report (`threadsdelete/cleanup.py`), a `main.py` entry point with redacted logging and exit codes, and `scripts/run.sh`. The HTTP timeout and retry assumptions were tuned offline.

**Phase 3 — Removal and useful tests (P3-01..P3-05).** It adds single-attempt, strictly validated removal and quota inspection. A sequential removal loop handles the cap and quota split. Item failures continue the run. An unknown outcome stops it and defers the rest. An auth loss stops it globally, and a quota error mid-run defers the rest. Real removal mode is enabled in `main.py` with exit statuses 0/1/2/3, and `MAX_DELETIONS_PER_RUN` was tuned offline.

**Phase 4 — Automation and handoff (P4-01..P4-06).** It adds offline CI (`.github/workflows/ci.yml`) and the weekly (Friday 05:00 UTC) plus dispatchable cleanup workflow (`.github/workflows/cleanup-feed.yml`). That workflow uses SHA-pinned actions, a non-cancelling concurrency group, and an always-written sanitized job summary. Workflow tests parse the YAML as text, and the job's `timeout-minutes` was tuned. The flight also wrote `README.md` and `docs/META_SETUP.md`, a dated credential setup and maintenance guide that flags unverified steps.

**Review fixes, round 1 (R1-01..R1-02).** These are test-only. CLI tests now cover four pieces of `main.py` safety wiring: the dry-run read-only client, the redacting log filter, the httpx/httpcore WARNING pin, and the generic API error exiting 1. A cleanup test covers a conflicting duplicate that marks discovery incomplete. There are now 101 offline tests.

## Decisions that shaped it

- Phases follow SPEC §8's four phases; task IDs use SPEC phase numbers (PLAN).
- SPEC §9 open questions were resolved by research (P1-01, P1-02) and gated by P1-03, not decided in PLAN (PLAN).
- Go/no-go: P1-03 writes `Decision: GO|NO-GO`. NO-GO blocks every later task (PLAN, P1-03).
- Unretrievable Meta docs are not NO-GO. Only positive evidence yields NO-GO (PLAN, P1-03). P1-03 went GO on documentation alone, with the Postman page unreadable and carried as not revalidated.
- Project setup lives in Phase 2. The Python verify commands start from P2-01 (PLAN).
- HTTP client is `httpx`, and `httpx.MockTransport` is the test fake (PLAN, P2-04).
- Token transport: PLAN preferred a Bearer header. RESEARCH documents only the `access_token` query parameter, so that is used. As a consequence, errors never include URLs or bodies, and the `httpx`/`httpcore` loggers are pinned to WARNING (P1-01, P2-04).
- API host is `graph.threads.com` (docs; CLAUDE.md said `.net`), and the version is `v1.0` (P1-01).
- Empty or whitespace-only env values are unset and fall back to the default, so empty Actions Variables work (PLAN, P2-02).
- `DAYS_AGO` upper bound is 36500 (PLAN, P2-02).
- `THREADS_USER_ID` must be ASCII digits, and `THREADS_API_VERSION` must match `^v[0-9]+\.[0-9]+$` (PLAN, P2-02). Config errors never echo any value (P2-02).
- Exit statuses: 0 for success, deferral or nothing eligible; 1 for runtime failure; 2 for config or usage; 3 for auth, permission or identity mismatch (PLAN, P3-03).
- An unknown mutation outcome stops further removals. The rest are deferred and the run exits 1 (PLAN, P3-02).
- If quota inspection is unavailable or fails, the run proceeds within `MAX_DELETIONS_PER_RUN`, and the API's own quota error is the backstop (PLAN, P3-02).
- Duplicates are deduplicated by (operation, id). The same key with different timestamps aborts as ambiguous, and this check raises before eligibility filtering (PLAN, P2-03). The run reports it as incomplete discovery (P2-07).
- Pagination uses our own base URL plus the `after` cursor and never follows response URLs. A repeated cursor, or `next` without a cursor, is a failure (PLAN, P2-04).
- Discovery never requests the post `text` field (PLAN, P2-05).
- Dry run constructs a `read_only=True` client that refuses any non-GET request before the transport (PLAN, P2-08/P3-03). A blocked mutation surfaces as exit 1 through main's `ApiError` mapping (R1-01).
- There is no token helper, refresh or app secret in code. `docs/META_SETUP.md` gives manual `curl` steps (PLAN, P4-05).
- No Bluesky code was adapted, so no MIT notice is needed. The README credits blueskydelete (PLAN).
- The report goes to stdout and diagnostics go to stderr through redacted logging. The summary starts with `=== Summary ===` (PLAN, P2-07).
- `THREADS_USER_ID` is an Actions Variable; `THREADS_ACCESS_TOKEN` is the only Secret (PLAN, P4-02).
- `workflow_dispatch` has a `dry_run` input that defaults to `true` (PLAN, P4-02).
- ⚠️ ASSUMPTION tuning is offline (P2-06, P3-04, P4-03). Live numbers are pending (PLAN).
- No parallel streams (PLAN).
- `uv run --env-file`: the process environment wins over `.env`, as verified on uv 0.13.5 (PLAN, P2-08).
- Supported categories are posts, media/carousel parents, quotes and replies. Reposts are unsupported because there is no documented removal call. Likes are unsupported because there is no API. Reply and quote deletion via `DELETE /{id}` is inferred. Throttling means codes 4, 17 or 341, or HTTP 429. The code raised at the 100/day delete limit is unknown (P1-02).
- The existing `.gitignore` lock line was kept and the required entries appended (P2-01).
- Backoff is `2**attempt` from attempt 0. 429 is retried on reads, and codes 4/17/341 on reads raise `QuotaExceededError` (P2-04).
- `SUPPORTED_CATEGORIES = (POST, QUOTE, REPLY)`. Reposts are counted in POST `scanned` but are never returned or ownership-checked. `/me/threads` is fetched once and shared by POST and QUOTE. A record without `media_type` aborts discovery. Replies need `is_reply_owned_by_me` and a matching username. The plan's repost-action-time test was replaced (P2-05).
- Summary lines exist only for supported categories (P2-07).
- The log handler sits on the root logger only for the duration of `main()` (P2-08/P3-03).
- A 4xx with a well-formed non-auth/throttle Graph error is an `ItemError`. A `deleted_id` that differs from the request is an unknown outcome. Only `Operation.DELETE` is supported (P3-01).
- Quota is read only when something is eligible. The failing item is deferred on a quota or auth error and counted `unknown_outcome` on an unknown outcome. The auth error is re-raised after the summary prints (P3-02).
- Actions are pinned to the commits of the lightweight tags found on 2026-10-23 (checkout v7.0.1, setup-uv v10.3.2). `PYTHONUNBUFFERED=1` keeps the tee'd log in order (P4-01/P4-02).

## Assumptions still in play

| Key | Final default | Status |
| --- | --- | --- |
| `MAX_DELETIONS_PER_RUN` | 100 | Tuned offline, kept (matches the documented 100/24 h). Live measurement still a guess. |
| `HTTP_TIMEOUT_SECONDS` | 30 | Tuned offline, kept (127 s worst-case read chain). Live measurement still a guess. |
| `MAX_READ_RETRIES` | 3 | Tuned offline, kept. Live measurement still a guess. |
| `MAX_RETRY_WAIT_SECONDS` | 60 | Tuned offline, kept. Live measurement still a guess. |
| `jobs.cleanup.timeout-minutes` | 15 | Tuned offline, kept (7 full-chain requests fit). Record the first real run's duration. |

Run `uv run python -c "from tests.test_budgets import report; report()"` for the tables.

## Spec issues

Suggested edits to SPEC.md (from PLAN; both reviews added none new):

- §5 vs §3: missing Actions Variables "resolve to documented defaults" conflicts with booleans accepting only `true`/`false`. Resolved as: empty or whitespace means unset, which gives the default.
- §3 "Exclude known unsupported categories during phase 1" reads as if Phase 1 has code. Resolved as: Phase 1 research decides the set, and P2-05 encodes it.
- §8 Phase 1 asks for live observations, while §1 forbids account setup without authorization. Resolved as: all findings are `[doc]`, and live checks are pending.
- §5 does not say whether `THREADS_USER_ID` is a Secret or a Variable. Resolved as: Variable.
- §6 does not cover a quota error mid-run. Resolved as: a documented quota error counts as deferral (exit 0 if nothing failed).
- §6 is silent on continuing after an unknown outcome. Resolved as: stop and defer the rest.
- §7 "Build/syntax check" is listed in `build` and run in CI and P4-06, not after every task.
- Possible further edit: §4/CLAUDE.md name host `graph.threads.net`, while the docs use `graph.threads.com` (P1-01).

Known-gap candidates: none (the final REVIEW.md lists none).

## Manual checks owed

- **Phase 1:** read `docs/RESEARCH.md`. Confirm it states the fees (none documented), what works, what is unsupported and what is untested.
- **Phase 2:**
  - `uv run main.py --help` works with no credentials.
  - The fixture tests pass.
  - With credentials in `.env`, `DRY_RUN=true ./scripts/run.sh` prints a live preview, and nothing changes in Threads.
- **Phase 3:**
  - Authorize specific disposable posts, then preview, remove and confirm in Threads that they are gone with exit 0.
  - Also confirm that reply and quote deletion work.
  - Record the error raised at the deletion limit.
  - Check whether content created in the Threads app is enumerated.
- **Phase 4:**
  - Follow the README from a fresh checkout and set the Secrets and Variables.
  - Run an owner-authorized `workflow_dispatch` preview and read the job summary.
  - Set `DRY_RUN=false` for real scheduled cleanup.
  - Record the first real run's duration, for timeout tuning.
- **Unverified Meta steps** (`docs/META_SETUP.md`):
  - whether `threads_delete` can be requested in the authorization `scope`
  - how the redirect URI behaves
  - the repost-removal call, which would promote reposts to supported
- **⚠️ ASSUMPTION keys:** all live measurements are pending.
- **CI:** confirm the PR's checks are green. They were pending at review 2; `kukulu_status` now reports `pass`.

## Review history

- Review 1: 2 findings (F1 main.py safety wiring untested, F2 conflicting duplicate untested). 2 fix tasks (R1-01, R1-02), all from review, 0 from mutation, 0 blocked. CHANGES REQUESTED, converging.
- Review 2: 0 findings, 0 fix tasks, no recurrence. APPROVED. This was a notes-only approval: its `## Notes` flagged the following without queuing work:
  - a stray `issubclass(MutationBlockedError, ApiError)` assertion in `test_removal_mode_client_is_not_read_only`
  - no-op `# type: ignore` comments on the test stubs
  - the `read_only=False` mutant fails as an ERROR, not an assertion failure
  - the round-1 notes still apply: `OwnershipError` is redundant in `discover_all`'s exception tuple, POST `scanned` includes repost facades, `api.py` uses the Python 3.14 `except A, B:` form, and retry warnings print to stderr during tests

## Pipeline friction

None.

## Suggested CLAUDE.md additions

- `unittest discover -s tests` imports test modules at the top level, so `tests/__init__.py`'s socket guard loads only through `from tests.fakes import ...`. Every test that uses fakes must import them that way.
- The `no-environ-in-package` constraint matches the text `os.environ` even inside a docstring. The `no-token-in-logs` pattern flags any `print`/logger line that names `access_token`, so print errors via a local `secrets` tuple.
- The Meta docs example for delete returns `{"success": true, "deleted_id": "...",}` (trailing comma, invalid JSON). The client treats an unparsable 2xx as an unknown outcome, never as success.
- Meta's authorization docs omit `threads_delete` from the scope list, while the delete page requires it.
- Retry warning logs print to stderr during tests (harmless).
- zsh does not word-split unquoted variables, so run command loops through `bash -c`.

## Advisory mutation survivors

None. Every survivor from review 1 was killed in review 2, and review 2's Notes list no survivors outside the diff.

## Breaking call

Breaking: no — greenfield project. The base held only docs, so no existing public interface, config default or user behavior changes.
