# threadsdelete - implementation specification

Version: 0.2 | Status: ready for feasibility research and v1 implementation | Updated: 2026-10-23

## 1. Overview

Build a personal Threads cleanup tool modeled on [deeheber/blueskydelete](https://github.com/deeheber/blueskydelete), using Meta's official API to remove the owner's content by age. It must run locally and through a weekly GitHub Actions cron with compatible settings. Done means feasibility is documented, supported cleanup works through both execution paths, useful offline tests pass, and setup instructions cover Meta credentials and maintenance.

Research first, then proceed through implementation if the core use case works without an API subscription or per-request fee for personal/developer use. Stop and ask if core post deletion is unavailable, requires payment, or needs a materially different design. Document and omit unsupported optional categories while implementing the supported ones; never substitute scraping or unofficial APIs.

Missing credentials must not prevent offline implementation. Mark live checks pending and obtain separate authorization for account setup or deletion of specifically identified test content. Follow repository working agreements for commits and publishing.

## 2. Goals and non-goals

- Match cleanup of posts, reposts, and likes wherever the official API supports reliable enumeration, age filtering, and removal. Include own replies, quotes, and media/carousel posts where supported.
- Preserve `DAYS_AGO=90`, `DRY_RUN=true`, `LOG_LEVEL=INFO`, and the Python/`uv` workflow. Replace Bluesky username/password authentication with Threads OAuth.
- Run weekly at Friday 05:00 UTC (`0 5 * * 5`), matching blueskydelete, with manual Actions dispatch as well.
- Support manual replacement of the local token and GitHub secret in v1.
- Non-goals: web UI, hosted service, multi-account orchestration, direct messages, account deletion, backups, engagement filters, automatic token renewal/secret writeback, and paid third-party services.

## 3. Engineering principles

- Use Ruff for linting and formatting, and mypy for type checking. Annotate application function parameters and return values; configure mypy to reject untyped function definitions. Keep behavior tests alongside these checks.
- Use documented Meta endpoints and an explicit supported API version. Cite contracts and permissions in the research report.
- Validate configuration before network activity. Only case-insensitive `true` and `false` are valid booleans; missing `DRY_RUN` defaults to true.
- Capture one UTC run-start time. Eligibility is `action_timestamp <= run_started_at - timedelta(days=DAYS_AGO)`. Use creation time for posts/replies and the owner's action time for likes/reposts, never the original post's age.
- Selection code accepts time as an argument and performs no network, environment, filesystem, or sleep operations. Reject malformed or timezone-naive timestamps.
- Complete discovery and validation before mutation. Do not assume API ordering or mutate while paginating. Deduplicate by operation/type and ID; sort by action timestamp, type, then ID.
- Abort mutation on incomplete discovery or ambiguous ownership. For likes/reposts, verify the owner's action, not ownership of the original post. Never delete another person's content. Exclude known unsupported categories during phase 1.
- Dry run performs no mutations, regardless of HTTP method, and no token refresh. It may read candidates and quota information.
- Remove items sequentially within the local cap and verified API limits. A per-run cap is not a rolling-quota tracker. Report quota-deferred work for the next run.
- Bound read retries. Never blindly retry a destructive request after a timeout with an unknown outcome; report uncertainty and rediscover on a later run.
- Redact credentials from all logs and errors. Do not commit `.env`, token files, or real account fixtures; avoid logging post bodies.
- Keep tests offline and behavior-focused. No arbitrary coverage target, trivial getter tests, formatting snapshots, or duplicated assertions at every layer.
- Keep the design small: no database, queue, hosted callback service, plugin framework, or general social-network abstraction. Retain applicable MIT notices if adapting Bluesky source.

## 4. Architecture

Use Python 3.14 and `uv`, matching the inspected reference project; record any dependency-driven runtime change. Keep dependencies in `uv.lock` and the runtime in `.python-version`.

| Location | Responsibility | Allowed dependencies |
| --- | --- | --- |
| `main.py` | Entry point, help, exit status | Application/config modules |
| `threadsdelete/config.py` | Environment parsing | Standard library |
| `threadsdelete/core.py` | Candidate/result types, eligibility | Standard library only |
| `threadsdelete/api.py` | HTTP, pagination, response validation, sanitized errors | Core types, one maintained HTTP client |
| `threadsdelete/cleanup.py` | Identity, discovery, quota budget, execution, summary | Config, core, API |
| `scripts/run.sh` | Local wrapper; no cleanup logic | Python entry point |
| `tests/` | Offline tests and synthetic fixtures | Application, unittest/mock |
| `.github/workflows/` | Offline CI and separate cleanup workflow | Documented commands |

A small manually invoked token helper is optional if it simplifies the verified setup flow; it is not required for v1.

## 5. Data and configuration

Use environment variables and `uv --env-file .env` locally. Explicit process environment values take precedence over `.env`. Store credentials in GitHub Secrets and non-secret settings in Variables.

| Key | Default | Contract |
| --- | --- | --- |
| `DRY_RUN` | `true` | Explicit `false` opts into removal. |
| `DAYS_AGO` | `90` | Non-negative integer; zero includes content up to run start. |
| `LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR; case-insensitive. |
| `THREADS_ACCESS_TOKEN` | Required | User access token, secret. |
| `THREADS_USER_ID` | Required | Expected account ID; compare against authenticated identity. |
| `THREADS_API_VERSION` | Resolve in phase 1 | Document supported default in `.env.sample`. |
| `MAX_DELETIONS_PER_RUN` | `100` | ⚠️ ASSUMPTION: total removal-attempt cap across supported categories; zero allows no mutation. Also enforce each operation's verified quota. |
| `HTTP_TIMEOUT_SECONDS` | `30` | ⚠️ ASSUMPTION: positive per-request timeout. |
| `MAX_READ_RETRIES` | `3` | ⚠️ ASSUMPTION: non-negative retry count. |
| `MAX_RETRY_WAIT_SECONDS` | `60` | ⚠️ ASSUMPTION: maximum individual retry wait; stop if Retry-After exceeds it. |

Workflow configuration: `on.schedule[].cron: '0 5 * * 5'`; `jobs.cleanup.timeout-minutes: 15` (⚠️ ASSUMPTION, tunable in YAML). Cron is a YAML setting, not an interpolated environment variable. Missing Actions Variables must resolve to documented defaults rather than invalid empty strings.

Candidates contain operation/type, target ID, action timestamp, and permalink when available. Results distinguish scanned, eligible, would-remove, removed, failed, unknown-outcome, and deferred counts by category. Keep bootstrap-only app secrets out of routine cleanup when unnecessary.

## 6. Interfaces

### CLI and results

Support `uv run --env-file .env main.py`, `./scripts/run.sh`, and credential-free/network-free `--help`. `DRY_RUN=false` is the removal opt-in; cron must not prompt interactively.

Print account, UTC cutoff, mode, candidate IDs/permalinks, and final counts. Preview distinguishes eligible items from those currently allowed by quota/cap. Label incomplete discovery and unavailable quota information explicitly.

Exit 0 for completed cleanup, no eligible content, or deliberate quota/cap deferral clearly reported. Exit nonzero for invalid configuration, authentication/permission failure, incomplete discovery, failed/unknown removal outcomes, or unrecoverable API errors. Wrappers and workflows preserve exit status.

### API adapter

Implement the phase-1 contracts for identity, discovery, quota inspection, and removal for each supported category. Validate response bodies as well as status codes. Stop globally on authentication/permission loss; continue after known isolated item failures and exit nonzero afterward. Never reinterpret unknown errors as quota exhaustion or successful removal.

Follow all documented pagination cursors, including empty pages with continuation, and reject repeated cursors. Keep credential-bearing requests on the trusted API host. If quota inspection is unavailable, document the verified fallback; do not invent an endpoint or claim the local cap proves remaining quota.

### GitHub Actions

- Separate offline CI from `.github/workflows/cleanup-feed.yml`, which uses `schedule` and `workflow_dispatch` to call the same entry point as local execution.
- Serialize cleanup using a concurrency group and `cancel-in-progress: false`; document that local runs are not coordinated with Actions.
- Use `contents: read`, pinned action SHAs, locked dependencies, and a standard Linux runner. Pull-request CI must not receive cleanup credentials or run live cleanup.
- Pass settings through environment mappings, not interpolated shell code. Produce a sanitized summary even when cleanup fails.

### Documentation

Deliver a README covering quick start, compatible parameters, forced-preview and real-run examples, content coverage, cutoff semantics, quota/backlog behavior, commands, and troubleshooting.

`docs/META_SETUP.md` must cover developer registration, Threads app/use case, own-account role/tester acceptance, permissions, redirect settings if needed, user-token acquisition/exchange, expected account ID, expiry, manual renewal/replacement, and revocation. Distinguish personal developer access from serving unrelated users. Date the verified instructions and use placeholders for credentials.

Document Actions Secrets/Variables, cron editing, dispatch, run-history checks, failure notifications, default-branch requirements, scheduling delays, and public-repository inactivity disablement using [GitHub's schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule). Explain runner costs using [GitHub's billing documentation](https://docs.github.com/en/billing/concepts/product-billing/github-actions). State that this tool provides no undo and manual token maintenance is required for continued operation.

## 7. Commands

Implementation targets, to be configured in the new project and copied into Kūkulu's command configuration. Checks must exit nonzero on failure; CI must not auto-fix files. This script needs no wheel/sdist packaging; use the syntax check for the template's build step.

| Purpose | Command |
| --- | --- |
| Install | `uv sync --locked` |
| Typecheck | `uv run mypy threadsdelete main.py` |
| Lint | `uv run ruff check .` |
| Format check | `uv run ruff format --check .` |
| Offline tests | `uv run python -m unittest discover -s tests -v` |
| Targeted tests (dotted module/class) | `uv run python -m unittest {filter} -v` |
| Build/syntax check | `uv run python -m compileall -q threadsdelete main.py` |
| Offline smoke | `uv run main.py --help` |
| Forced local preview | `DRY_RUN=true uv run --env-file .env main.py` |
| Wrapper preview | `DRY_RUN=true ./scripts/run.sh` |
| Explicit removal | `DRY_RUN=false ./scripts/run.sh` |

Make `tests` importable, e.g. `tests.test_cleanup`. Live commands require owner-provided credentials and are not CI checks. Show platform-appropriate environment overrides in the README.

## 8. Phases

### Phase 1: Feasibility

Write `docs/RESEARCH.md` with dated primary-source evidence and a go/no-go conclusion. Resolve section 9's questions, compare supported categories against blueskydelete, and record section 6's API contracts. Distinguish documentation findings from live observations.

Manual check: the report explains whether personal cleanup is free of API fees, what works, what is unsupported, and what remains untested. If feasible, continue to phase 2 without requiring approval of the report itself.

### Phase 2: Local preview

Implement project setup, config, identity verification, discovery, selection, preview, `.env.sample`, `.gitignore`, and the local wrapper.

Manual check: help works without credentials and offline fixtures demonstrate expected candidates. With supplied credentials, the owner can inspect a live preview without mutation.

### Phase 3: Removal and useful tests

Implement sequential removal, quota handling, bounded retries, summaries, and exit statuses. Cover realistic failure boundaries, combining cases where appropriate:

- Cutoff before/at/after boundary, timezones, zero days, malformed timestamps, and distinct like/repost action ages.
- Safe defaults, invalid config, identity mismatch, and dry run preventing every mutation type.
- Multiple/empty pages, duplicates, unordered records, repeated cursors, and discovery failure before mutation.
- Ownership/type checks, quota/cap limits, partial failures, auth failure, and accurate counts/statuses.
- Unknown mutation outcomes are not retried or reported as success; secrets stay redacted.

Use a fake HTTP transport for a small CLI integration test of preview and a failure path. Test only implemented behavior, including exclusion of unsupported categories; add no tests for hypothetical token automation.

Manual check: after authorization for named disposable content, preview, remove, and verify it in Threads. Otherwise record this check as pending and continue offline work.

### Phase 4: Automation and handoff

Add CI and cleanup workflows, complete documentation, and run section 7's offline checks. Verify workflow defaults match the CLI.

Manual check: follow the README from a fresh checkout and inspect an owner-authorized Actions preview. The owner enables real scheduled cleanup. Report completed checks and pending live validation separately; do not claim an unexercised integration is verified.

## 9. Open questions

Product choices are settled: supported Bluesky parity, weekly schedule, manual token replacement. Resolve these technical questions in phase 1:

- Current API fees and personal-app eligibility, required permissions/review, and public/private profile restrictions.
- Enumeration/removal of posts, own replies, quotes, reposts, and likes, including reliable action timestamps and historical coverage. Verify content created in the Threads app as well as through the API.
- Supported API host/version, success/error payloads, rolling quotas and inspection, and token lifetime/manual renewal procedure.

Starting evidence, not a substitute for current verification:

- Meta's [official deletion request](https://www.postman.com/meta/threads/request/34203612-0a51cfc6-6407-4aec-974f-5bcbfbbf9da3) confirms `DELETE /{thread_id}`; its [authorization examples](https://www.postman.com/meta/threads/documentation/dht3nzz/threads-api) show user-token exchange and refresh. These were read on 2026-10-23.
- Prior official-doc research on 2026-10-20 found `threads_basic`/`threads_delete`, a 100-deletion rolling 24-hour quota, no documented API fee, and development access through app roles/testers. Meta's main docs blocked retrieval during drafting, so revalidate these findings against the [official guide](https://developers.facebook.com/documentation/threads/posts/delete-posts) and [Threads documentation](https://developers.facebook.com/documentation/threads). No authenticated account setup or deletion was tested for this spec.

## Appendix: mockups and fixtures

At drafting time only `docs/SPEC.md` exists. Planned artifacts: `docs/RESEARCH.md` for evidence/contracts, `docs/META_SETUP.md` for setup/maintenance, `README.md` for usage, and `tests/fixtures/` for synthetic API responses. No UI mockups are needed.

Reference inspected on 2026-10-23: blueskydelete [README](https://github.com/deeheber/blueskydelete/blob/main/README.md) and [main.py](https://github.com/deeheber/blueskydelete/blob/main/main.py). Preserve all supplied template section headings; mark guessed numeric defaults with `⚠️ ASSUMPTION` and a config key.
