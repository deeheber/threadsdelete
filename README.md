# threadsdelete

Cleans up your own old [Threads](https://www.threads.com) content with Meta's official Threads API. Runs locally or weekly through GitHub Actions, removing content older than `DAYS_AGO` (default 90).

**There is no undo.** A removed post is gone. The tool previews by default (`DRY_RUN=true`) and removes only when you set `DRY_RUN=false`.

Feasibility findings and API contracts: [docs/RESEARCH.md](docs/RESEARCH.md). Meta app and token setup: [docs/META_SETUP.md](docs/META_SETUP.md).

> Tested offline with synthetic fixtures and live through GitHub Actions on 2026-10-25. See [live observations](docs/RESEARCH.md#live-observations) and [pending checks](docs/RESEARCH.md#untested-and-pending).

## Quick start

> Requires [uv](https://docs.astral.sh/uv/).

1. Clone this repository (Python 3.14 is pinned in `.python-version`; uv installs it).
2. Install dependencies: `uv sync --locked`
3. Create a Meta app and a long-lived token by following [docs/META_SETUP.md](docs/META_SETUP.md).
4. Copy the sample settings: `cp .env.sample .env` (Windows: `copy .env.sample .env`), then edit `.env`. It is git-ignored; never commit it.
5. Preview: `DRY_RUN=true uv run --env-file .env main.py` (or `DRY_RUN=true ./scripts/run.sh`).

`uv run main.py --help` works without credentials or network.

## Settings

Set these in `.env`, in the shell, or (for Actions) as repository Secrets/Variables. A value set in the process environment overrides the same key in `.env`. Empty values, including unset Actions Variables, use the default.

| Key | Default | Meaning |
| --- | --- | --- |
| `DRY_RUN` | `true` | Only an explicit `false` (any case) removes content. Only `true`/`false` are accepted. |
| `DAYS_AGO` | `90` | Non-negative integer, at most 36500. `0` includes everything up to run start. |
| `THREADS_ACCESS_TOKEN` | required | Long-lived Threads user token. A secret. |
| `THREADS_USER_ID` | required | Your numeric Threads user ID; must match the token's account. |
| `MAX_DELETIONS_PER_RUN` | `100` | ⚠️ ASSUMPTION: removal attempts per run across all categories; `0` allows none. |

API version (`v1.0`), logging (`INFO`), timeout (30 seconds), read retries (3), and maximum retry wait (60 seconds) are internal constants in `threadsdelete/config.py`. The timeout and retry values remain assumptions pending live measurement. Older `.env` entries and repository Variables for these settings are ignored; they can be removed.

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

The report prints the account, the UTC cutoff, the mode, one line per candidate (ID and permalink; post text is never fetched), then a block starting with `=== Summary ===` with per-category counts (`post`, `quote`, `repost`, `reply`): scanned, eligible, would_remove, removed, failed, unknown_outcome, deferred.

### Exit statuses

| Code | Meaning |
| --- | --- |
| 0 | Completed, nothing eligible, or deferral by cap/quota that the report shows |
| 1 | Incomplete discovery, a failed or unknown-outcome removal, or an unrecoverable API error |
| 2 | Invalid configuration or usage (no network was used) |
| 3 | Authentication or permission failure, or the token's account is not `THREADS_USER_ID` |

## What is covered

From [docs/RESEARCH.md](docs/RESEARCH.md) (posts, quotes, replies and reposts are all live-verified):

| Content | Status |
| --- | --- |
| Posts, including image/video/audio, polls and carousels (the parent post only) | Removed |
| Quote posts | Removed |
| Your own replies | Removed |
| Reposts | Removed (your repost only; the original post is untouched) |
| Likes | Excluded: the API has no documented endpoint to list or remove likes |

Nothing from other people is ever touched: every record must prove it is yours (post and repost `owner` equals your user ID; replies must be flagged as yours and carry your username). If ownership or any timestamp is ambiguous, discovery is marked incomplete and nothing is removed.

## Cutoff

One UTC run-start time is captured per run. An item is eligible when `its time <= run start - DAYS_AGO days`. Posts, quotes and replies use their creation time; reposts use the time you reposted, not the original post's age. With `DAYS_AGO=90` and a run at `2026-10-23T05:00:00Z`, everything created at or before `2026-07-25T05:00:00Z` is eligible.

## Quota and backlog

Posts, quotes, replies and reposts share a quota of 100 deletions per rolling 24 hours. The tool reads the remaining quota and removes oldest first, up to that quota or `MAX_DELETIONS_PER_RUN`, whichever is lower. Remaining items are reported as `deferred` for a later run; at the default cap, 500 items take 5 weekly runs.

If quota inspection fails, the report says `Quota: unavailable`; removal stays within the cap and stops at the API's quota error. The cap does not track rolling usage, so closely spaced runs can still hit the limit.

Removals run one at a time and are never retried. If one ends with an unknown outcome (timeout, connection loss, server error), the run stops, reports it, and exits 1; the next run rediscovers what is left.

## Commands

See [contributor commands](CLAUDE.md#commands) for checks and targeted tests. Tests run offline with synthetic fixtures.

## Scheduled cleanup with GitHub Actions

Two workflows live in `.github/workflows/`: `ci.yml` (offline checks on push and pull request, no credentials) and `cleanup-feed.yml` (the cleanup).

1. In the repository go to Settings, Secrets and variables, Actions.
2. **Secret**: `THREADS_ACCESS_TOKEN`.
3. **Variables**: `THREADS_USER_ID`, and optionally `DRY_RUN`, `DAYS_AGO`, `MAX_DELETIONS_PER_RUN`. A missing Variable resolves to the default above. With `DRY_RUN` unset, scheduled runs are previews; set the Variable to `false` to enable real scheduled removal.
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

Tokens expire after 60 days; the tool does not renew them. Follow [Meta setup](docs/META_SETUP.md#8-expiry-and-refresh) to renew the token in both `.env` and the GitHub Secret, or [revoke access](docs/META_SETUP.md#9-revocation).

## Troubleshooting

| Symptom | Likely cause and fix |
| --- | --- |
| Exit 2, "Configuration error: ..." | A setting is missing or invalid; the message names the key. |
| Exit 3, "Authentication failure" | Token expired or revoked, missing permission (`threads_basic`, `threads_read_replies`, `threads_delete`), or `THREADS_USER_ID` is not the token's account. |
| Exit 1, "Discovery: INCOMPLETE" | A read failed, a timestamp was malformed, or ownership was ambiguous. Nothing was removed. Re-run after resolving the reported problem. |
| Exit 1, an `unknown` line | A removal timed out or got a server error. Check Threads, then re-run. |
| Items stay `deferred` | The per-run cap or the 24-hour deletion quota was reached; they are picked up next run. |
| `Quota: unavailable` | The quota endpoint failed; the run stays within `MAX_DELETIONS_PER_RUN`. |

## Credit

Reference project: [deeheber/blueskydelete](https://github.com/deeheber/blueskydelete).

Built with [Kūkulu](https://kukulu.tech) ([GitHub](https://github.com/DisplaceTech/kukulu)); [original spec and build history](docs/flights/threadsdelete/).

## License

[MIT](LICENSE)
