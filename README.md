# threadsdelete

Cleans up your own old [Threads](https://www.threads.com) content with Meta's official Threads API. Content older than a configurable number of days (default 90) is removed, locally or from a weekly GitHub Actions run. Modeled on [blueskydelete](https://github.com/deeheber/blueskydelete).

**There is no undo.** A removed post is gone. The tool previews by default (`DRY_RUN=true`) and removes only when you set `DRY_RUN=false`.

Feasibility findings and API contracts: [docs/RESEARCH.md](docs/RESEARCH.md). Meta app and token setup: [docs/META_SETUP.md](docs/META_SETUP.md).

> Status: built and tested offline against synthetic fixtures. Nothing here has been exercised against a live account yet; the live checks are listed in `docs/RESEARCH.md` under "Untested and pending".

## Quick start

> Requires [uv](https://docs.astral.sh/uv/).

1. Clone this repository (Python 3.14 is pinned in `.python-version`; uv installs it).
2. Install dependencies: `uv sync --locked`
3. Create a Meta app and a long-lived token by following [docs/META_SETUP.md](docs/META_SETUP.md).
4. Copy the sample settings: `cp .env.sample .env` (Windows: `copy .env.sample .env`), then edit `.env`. It is git-ignored; never commit it.
5. Preview: `uv run --env-file .env main.py` (or `./scripts/run.sh`).

`uv run main.py --help` works without credentials or network.

## Settings

Set these in `.env`, in the shell, or (for Actions) as repository Secrets/Variables. A value set in the process environment overrides the same key in `.env`. An empty value counts as unset and falls back to the default, which is how unset Actions Variables behave.

| Key | Default | Meaning |
| --- | --- | --- |
| `DRY_RUN` | `true` | Only an explicit `false` (any case) removes content. Only `true`/`false` are accepted. |
| `DAYS_AGO` | `90` | Non-negative integer, at most 36500. `0` includes everything up to run start. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`, case-insensitive. |
| `THREADS_ACCESS_TOKEN` | required | Long-lived Threads user token. A secret. |
| `THREADS_USER_ID` | required | Your numeric Threads user ID; must match the token's account. |
| `THREADS_API_VERSION` | `v1.0` | Threads API version. |
| `MAX_DELETIONS_PER_RUN` | `100` | ⚠️ ASSUMPTION: removal attempts per run across all categories; `0` allows none. |
| `HTTP_TIMEOUT_SECONDS` | `30` | ⚠️ ASSUMPTION: per-request timeout. |
| `MAX_READ_RETRIES` | `3` | ⚠️ ASSUMPTION: retries for read requests only. Removals are never retried. |
| `MAX_RETRY_WAIT_SECONDS` | `60` | ⚠️ ASSUMPTION: longest single retry wait; a longer `Retry-After` stops the read. |

## Usage

Forced preview (nothing is changed):

```
DRY_RUN=true ./scripts/run.sh
DRY_RUN=true uv run --env-file .env main.py
```

PowerShell:

```
$env:DRY_RUN='true'; uv run --env-file .env main.py
```

Real removal (explicit opt-in):

```
DRY_RUN=false ./scripts/run.sh
```

Any key can be overridden inline, e.g. `DRY_RUN=false DAYS_AGO=30 ./scripts/run.sh`. `scripts/run.sh` only picks `.env` when it exists and keeps the exit status.

The report prints the account, the UTC cutoff, the mode, one line per candidate (ID and permalink; post text is never fetched), then a block starting with `=== Summary ===` with per-category counts: scanned, eligible, would_remove, removed, failed, unknown_outcome, deferred.

### Exit statuses

| Code | Meaning |
| --- | --- |
| 0 | Completed, nothing eligible, or deferral by cap/quota that the report shows |
| 1 | Incomplete discovery, a failed or unknown-outcome removal, or an unrecoverable API error |
| 2 | Invalid configuration or usage (no network was used) |
| 3 | Authentication or permission failure, or the token's account is not `THREADS_USER_ID` |

## What is covered

From [docs/RESEARCH.md](docs/RESEARCH.md) (documentation findings, not yet live-verified):

| Content | Status |
| --- | --- |
| Posts, including image/video/audio, polls and carousels (the parent post only) | Removed |
| Quote posts | Removed |
| Your own replies | Removed |
| Reposts | Excluded: no documented call removes a repost |
| Likes | Excluded: the API has no documented endpoint to list or remove likes |

Nothing from other people is ever touched: every record must prove it is yours (post `owner` equals your user ID; replies must be flagged as yours and carry your username). If ownership or any timestamp is ambiguous, discovery is marked incomplete and nothing is removed.

## Cutoff

One UTC run-start time is captured per run. An item is eligible when `its time <= run start - DAYS_AGO days`. Posts, quotes and replies use their creation time. With `DAYS_AGO=90` and a run at `2026-10-23T05:00:00Z`, everything created at or before `2026-07-25T05:00:00Z` is eligible.

## Quota and backlog

Threads limits a profile to 100 deletions per rolling 24 hours. Before removing, the tool reads your remaining deletion quota and removes oldest first, up to the lower of `MAX_DELETIONS_PER_RUN` and the remaining quota. The rest is reported as `deferred` and picked up by a later run: at the default cap, a backlog of 500 takes 5 weekly runs. If the quota cannot be read, the report says `Quota: unavailable` and the run stays within the cap and stops at the API's own quota error. The cap is not a rolling-quota tracker; runs close together can still hit the API limit.

Removals run one at a time and are never retried. If one ends with an unknown outcome (timeout, connection loss, server error), the run stops, reports it, and exits 1; the next run rediscovers what is left.

## Commands

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
| Budget measurements | `uv run python -c "from tests.test_budgets import report; report()"` |

Tests are offline and use synthetic fixtures.

## Scheduled cleanup with GitHub Actions

Two workflows live in `.github/workflows/`: `ci.yml` (offline checks on push and pull request, no credentials) and `cleanup-feed.yml` (the cleanup).

1. In the repository go to Settings, Secrets and variables, Actions.
2. **Secret**: `THREADS_ACCESS_TOKEN`.
3. **Variables**: `THREADS_USER_ID`, and optionally `DRY_RUN`, `DAYS_AGO`, `LOG_LEVEL`, `THREADS_API_VERSION`, `MAX_DELETIONS_PER_RUN`, `HTTP_TIMEOUT_SECONDS`, `MAX_READ_RETRIES`, `MAX_RETRY_WAIT_SECONDS`. A missing Variable resolves to the default above. With `DRY_RUN` unset, scheduled runs are previews; set the Variable to `false` to enable real scheduled removal.
4. Schedule: `cron: '0 5 * * 5'` (Fridays 05:00 UTC), edited directly in `cleanup-feed.yml`. The job's `timeout-minutes: 15` is an assumption you can change there too.
5. Manual run: Actions tab, "Threads cleanup", Run workflow. The `dry_run` input defaults to `true` (forced preview); choose `variable` to follow the `DRY_RUN` Variable.
6. Check results under Actions run history; each run writes a sanitized summary on the run page (the `=== Summary ===` block, or the last log lines on failure). Enable failure notifications in your GitHub notification settings for Actions.

Per [GitHub's schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule):

- Scheduled workflows only run from the default branch, so merge the workflow there.
- Runs can be delayed at busy times.
- In public repositories, scheduled workflows are disabled after 60 days without repository activity. Re-enable them or push occasionally.

Runner minutes are billed under [GitHub's billing rules](https://docs.github.com/en/billing/concepts/product-billing/github-actions). A weekly run of a few minutes is normally within free allowances.

Runs are serialized (`concurrency: cleanup-feed`, `cancel-in-progress: false`). Local runs are not coordinated with Actions runs: avoid running both with `DRY_RUN=false` at the same time.

## Token maintenance

Long-lived tokens last 60 days and this tool does not renew them. Before expiry, replace `THREADS_ACCESS_TOKEN` in your local `.env` and in the GitHub secret by following [docs/META_SETUP.md](docs/META_SETUP.md). Once a token has expired the scheduled run fails with exit status 3 until you replace it. To revoke access, remove the app from your Threads account's website permissions.

## Troubleshooting

| Symptom | Likely cause and fix |
| --- | --- |
| Exit 2, "Configuration error: ..." | A setting is missing or invalid; the message names the key. |
| Exit 3, "Authentication failure" | Token expired or revoked, missing permission (`threads_basic`, `threads_read_replies`, `threads_delete`), or `THREADS_USER_ID` is not the token's account. |
| Exit 1, "Discovery: INCOMPLETE" | A read failed, a timestamp was malformed, or ownership was ambiguous. Nothing was removed. Re-run; use `LOG_LEVEL=DEBUG` for detail. |
| Exit 1, an `unknown` line | A removal timed out or got a server error. Check Threads, then re-run. |
| Items stay `deferred` | The per-run cap or the 24-hour deletion quota was reached; they are picked up next run. |
| `Quota: unavailable` | The quota endpoint failed; the run stays within `MAX_DELETIONS_PER_RUN`. |

## Credit

Reference project: [deeheber/blueskydelete](https://github.com/deeheber/blueskydelete).

Built with [Kūkulu](https://kukulu.tech), which planned, implemented and reviewed it from `docs/SPEC.md`. The build's plan, progress log and reviews are in [docs/flights/threadsdelete/](docs/flights/threadsdelete/).

## License

[MIT](LICENSE)
