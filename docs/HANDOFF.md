# Handoff

- Branch: `build/2026-10-24`
- Base commit: `c29457c`
- Head commit: `cf38bf6` (before this file)
- Tasks: 24 done, 0 blocked, 0 skipped. 95 offline tests; mypy strict, ruff check and format, compileall and `--help` all green.
- Nothing was run against a live account or GitHub. All API contracts are documentation findings (`docs/RESEARCH.md`, Decision: GO).

## Blocked and skipped tasks

None.

## Interpretation choices

- P1-01: host is `graph.threads.com` (docs; CLAUDE.md text said `.net`), version `v1.0`. Token sent as the `access_token` query parameter because it is the only documented transport (plan preferred a Bearer header). Consequence: URLs carry the token, so errors never include URLs or bodies and `httpx`/`httpcore` loggers are pinned to WARNING.
- P1-02: Supported = posts, media/carousel parents, quotes, replies. Reposts unsupported (enumerable as `REPOST_FACADE` but no documented removal call). Likes unsupported (no API). Reply and quote deletion via `DELETE /{id}` is inferred from the generic delete page. Throttling = codes 4, 17, 341 or HTTP 429; the code the 100-deletes-per-day limit actually raises is Unknown.
- P1-03: GO on documentation evidence alone (Postman page unreadable, carried as not revalidated).
- P2-01: kept the existing `.gitignore` lock line and appended the required entries.
- P2-02: config errors never echo any value; `THREADS_USER_ID` validated as digits.
- P2-03: conflicting duplicate action times raise before eligibility filtering.
- P2-04: backoff `2**attempt` from attempt 0 (1 s, 2 s, ...); 429 is retried on reads; 4/17/341 on reads raise `QuotaExceededError`.
- P2-05: `SUPPORTED_CATEGORIES = (POST, QUOTE, REPLY)`. Reposts are counted under POST's `scanned` but never returned or ownership-checked. `/me/threads` is fetched once per client and shared by POST and QUOTE. A record without `media_type` aborts discovery. Replies need `is_reply_owned_by_me` true and a matching username. The plan's repost-action-time test was replaced.
- P2-07: summary lines exist only for supported categories; a `SelectionError` is reported as incomplete discovery.
- P2-08/P3-03: handler on the root logger for the duration of `main()` only.
- P3-01: 4xx with a well-formed Graph error body that is not auth/throttle is `ItemError`; a `deleted_id` that differs from the request is an unknown outcome; only `Operation.DELETE` is supported.
- P3-02: quota is read only when something is eligible; the failing item is deferred on quota or auth errors and counted `unknown_outcome` on an unknown outcome; the auth error is re-raised after the summary prints.
- P4-01/P4-02: actions pinned to lightweight-tag commits found on 2026-10-23 (checkout v7.0.1, setup-uv v10.3.2); `PYTHONUNBUFFERED=1` so the tee'd log keeps order.

## ⚠️ ASSUMPTION keys

| Key | Default | Tuned? |
| --- | --- | --- |
| `MAX_DELETIONS_PER_RUN` | 100 | Measured, kept (matches the documented 100/24 h) |
| `HTTP_TIMEOUT_SECONDS` | 30 | Measured, kept (127 s worst case per read chain with the other two) |
| `MAX_READ_RETRIES` | 3 | Measured, kept |
| `MAX_RETRY_WAIT_SECONDS` | 60 | Measured, kept |
| `jobs.cleanup.timeout-minutes` | 15 | Measured, kept (7 full-chain requests fit; realistic backlogs rely on normal latency) |

All live measurements are pending (human). Run `uv run python -c "from tests.test_budgets import report; report()"` for the tables.

## What a human must check by hand

- Phase 1: read `docs/RESEARCH.md`; confirm it states fees (none documented), what works, what is unsupported, what is untested.
- Phase 2: `uv run main.py --help` without credentials; the fixture tests; with credentials in `.env`, `DRY_RUN=true ./scripts/run.sh` prints a live preview and changes nothing.
- Phase 3: after authorizing specific disposable posts, preview, remove, confirm in Threads. Also confirm reply and quote deletion, the error raised at the deletion limit, and whether Threads-app-created content is enumerated.
- Phase 4: follow the README from a fresh checkout; set Secrets/Variables; run an owner-authorized `workflow_dispatch` preview and read the job summary; then set `DRY_RUN=false` for real scheduled cleanup. Record the first real run duration (timeout tuning).
- Unverified Meta steps (in `docs/META_SETUP.md`): whether `threads_delete` can be requested in the authorization `scope`, redirect URI behavior, the repost-removal call (would promote reposts to supported).

## Codebase notes

- `unittest discover -s tests` imports test modules top-level, so `tests/__init__.py`'s socket guard only loads through `from tests.fakes import ...`; every test that uses fakes does so.
- The `no-environ-in-package` constraint matches the text `os.environ` even inside a docstring; the `no-token-in-logs` pattern flags any `print`/logger line that names `access_token`, so errors are printed via a local `secrets` tuple.
- The Meta docs example for delete returns `{"success": true, "deleted_id": "...",}` (trailing comma, invalid JSON). The client treats an unparsable 2xx as an unknown outcome, never success.
- Meta's authorization docs omit `threads_delete` from the scope list while the delete page requires it.
- Retry warning logs print to stderr during tests (harmless).
- zsh does not word-split unquoted variables; run command loops through `bash -c`.

## For the reviewer

- Safety invariants live in `cleanup.run`: complete discovery and selection precede quota and removal; `remove` is called once per candidate and never retried; dry run builds a `read_only=True` client whose `_send` blocks any non-GET before the transport.
- The cap counts removal attempts. Quota is the single `DELETE` operation shared by all categories.
- Likes and reposts are listed under `Excluded:` in every report with their reason.
