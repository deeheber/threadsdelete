# threadsdelete build progress

Branch: build/2026-10-24
Started: 2026-10-24T02:37:10.812Z

## Tasks

- [x] P1-01 Research access, fees, permissions and token lifecycle
- [x] P1-02 Research content categories, removal, quota and payload contracts
- [x] P1-03 Decide go or no-go
- [x] P1-04 Phase 1 close — push and manual checks
- [x] P2-01 Project scaffold
- [x] P2-02 Configuration parsing and .env.sample
- [x] P2-03 Core candidate types, timestamps and eligibility
- [x] P2-04 API client transport, pagination, retries and redaction
- [x] P2-05 Category discovery and record validation
- [x] P2-06 Tune HTTP_TIMEOUT_SECONDS, MAX_READ_RETRIES and MAX_RETRY_WAIT_SECONDS
- [x] P2-07 Cleanup preview: identity, complete discovery, selection and report
- [x] P2-08 Entry point, logging and local wrapper
- [x] P2-09 Phase 2 close — push and manual checks
- [x] P3-01 API removal and quota inspection
- [x] P3-02 Sequential removal with quota budget
- [x] P3-03 Exit statuses and removal mode in the entry point
- [ ] P3-04 Tune MAX_DELETIONS_PER_RUN
- [ ] P3-05 Phase 3 close — push and manual checks
- [ ] P4-01 Offline CI workflow
- [ ] P4-02 Scheduled cleanup workflow
- [ ] P4-03 Tune the cleanup job timeout-minutes
- [ ] P4-04 README
- [ ] P4-05 Meta setup and token maintenance guide
- [ ] P4-06 Final offline checks, push and handoff checks

## Log

(one entry per task, appended by implement)

### P1-01 — fb5733f

docs/RESEARCH.md created (25 headings). Findings [doc]: no documented API fee; tester role allows own-account use without App Review; perms threads_basic, threads_delete, threads_read_replies; host graph.threads.com, version v1.0; token via access_token query param (only documented transport); identity GET /me?fields=id,username; tokens 1h short / 60d long, refresh after 24h. Postman page unreadable (JS shell) - carried as not revalidated. Interpretation: query-param token (not Bearer) since Bearer is undocumented; later tasks must redact access_token in URLs. threads_delete missing from authorize-window scope list: flagged Unknown.

### P1-02 — 8484378

RESEARCH contracts filled. Supported: posts, replies, quotes, media/carousel (all Operation.DELETE via DELETE /{id}, success {"success":true,"deleted_id":..}). Unsupported: reposts (no documented removal; REPOST_FACADE records scanned and skipped), likes (no API). Ownership: posts/quotes owner.id==identity id; replies is_reply_owned_by_me true AND username==identity username. Pagination: limit<=100, continue while paging.next, re-request with after cursor. Errors: auth 190/401/403/10/200-299/3; throttling 4,17,341/429 -> QuotaExceeded; 5xx unknown on removal; other 4xx with well-formed body = ItemError on removal. Quota: GET /{uid}/threads_publishing_limit?fields=delete_quota_usage,delete_config, data[0], remaining=quota_total-usage, 86400s window; only DELETE operation. Token as access_token query param.

### P1-03 — 9659c04

Decision: GO (criteria a-d all yes, doc-only). Unsupported categories reposts and likes omitted.

### P1-04 — 42cac76

Push: ok (origin build/2026-10-24). Owner reads docs/RESEARCH.md and confirms it explains whether personal cleanup is free of API fees, what works, what is unsupported, and what remains untested.
Manual check: NOT VERIFIED (human)

### P2-01 — 33c9852

Scaffold done; tests: HelpTests.test_help_needs_no_credentials. Note: `unittest discover -s tests` imports modules top-level (tests/__init__ not loaded unless a test imports tests.fakes), as the plan anticipates. ruff/mypy strict green. .gitignore preserved existing .kukulu/implement.lock line.

### P2-02 — c688aa6

config.py + .env.sample + 8 tests. Interpretation: error messages never echo any value; DEFAULT_API_VERSION="v1.0"; THREADS_USER_ID validated with the digits pattern. Config keys: all ten ENV_KEYS (SPEC's nine listed + THREADS_API_VERSION counted; tuple has 10 names incl. all SPEC rows). Note: constraint no-environ-in-package matches the literal text "os.environ" even in docstrings.

### P2-03 — 51d34cf

core.py done, 8 tests. Interpretation: conflicting duplicate action times raise SelectionError before eligibility filtering. parse_timestamp uses datetime.fromisoformat (py3.14 accepts +0000 and Z); date-only/naive rejected. Types per CLAUDE.md map, RunSummary.notes is default_factory list.

### P2-04 — a968d76

api.py read side + fakes + 14 tests. Interpretation: token as access_token query param (RESEARCH); API_HOST graph.threads.com; ThreadsClient._send(method, path, params) is the single request primitive (read-only guard lives there) and _get(path, params) does bounded retry; _classify(response) maps status/codes (reuse for removal in P3-01: 401/403/auth codes->AuthError, 429/codes 4,17,341->QuotaExceededError, else ResponseError); _fail(kind,msg) redacts. Backoff min(2**attempt,max) from attempt 0. FakeThreadsApi: add(method,path,*replies,repeat=), .requests, .sleeps, .calls(), .paths(), json_response, error_response(code,status) helpers; make_client(fake, **overrides) read_only=True default, sleep=fake.sleeps.append. Paths keyed without version prefix (e.g. "me/threads"). Warning logs on retries print to stderr during tests (harmless).

### P2-05 — bc8522e

discover(category, identity)->(candidates, scanned) added to ThreadsClient. SUPPORTED_CATEGORIES=(POST,QUOTE,REPLY); UNSUPPORTED={REPOST,LIKE} with reasons. Interpretation: reposts unsupported per RESEARCH so no repost-action-time test; REPOST_FACADE counted in POST's scanned, not returned, no ownership check; /me/threads fetched once and cached per client (POST+QUOTE share it); missing media_type aborts (ResponseError); replies: is_reply_owned_by_me True + username==identity.username else OwnershipError; TimestampError propagates. Fixtures: threads_page1.json, threads_page2.json (A1 cursor, 6 records), replies.json (2 replies); identity example_owner/1000001. Dedicated limit=100 params.

### P2-06 — f26e271

tests/test_budgets.py: measure_read_chain, report(), 2 tests (JOB_TIMEOUT_MINUTES_ASSUMED=15 in module; P3-04 extends this file, P4-03 should read the YAML value).
Measurement: HTTP_TIMEOUT_SECONDS/MAX_READ_RETRIES/MAX_RETRY_WAIT_SECONDS before=30/3/60 (4 attempts, 7s sleep, 127s worst case/chain) after=same decision=kept because 127s << 900s job timeout (retries 5: 211s; timeout 60: 247s; Retry-After at 60s cap: 300s).
Live measurement: pending (human)

### P2-07 — 605c515

cleanup.py: IdentityMismatchError, verify_identity, Discovery, discover_all, split_by_budget, run (dry only), SUMMARY_HEADER. 6 tests. Interpretation: summary has lines only for SUPPORTED_CATEGORIES; SelectionError -> incomplete discovery; run() raises ValueError for dry_run False (P3-02 replaces). Helpers _candidate_line/_summary_lines/_stamp are reusable for P3-02. Test helpers in test_cleanup: full_fake(), preview(fake, cap). Fixture scenario at RUN_START 2026-10-23, 90 days: 5 eligible (9000001, 7000001, 9000002, 9000003, 9000004).

### P2-08 — f7aac80

main.py wired (main(argv,*,env,transport,now,out,err)); scripts/run.sh executable; 7 CLI tests. Wrapper smoke: `env -i ... ./scripts/run.sh --help` exits 0; without env exits 2. Interpretation: root-logger handler added/removed within main(); errors printed via redact(str(exc), secrets) where `secrets` is a local tuple (the no-token-in-logs pattern flags any print line naming access_token). Removal branch (DRY_RUN=false) still returns CONFIG - P3-03 must replace and construct ThreadsClient(read_only=config.dry_run).

### P2-09 — b3b99fd

Push: ok. 1. `uv run main.py --help` works with no credentials. 2. `uv run python -m unittest tests.test_cleanup tests.test_cli -v` shows the expected fixture candidates. 3. With owner-supplied credentials in `.env`: `DRY_RUN=true ./scripts/run.sh` prints a live preview, and nothing changes in Threads.
Manual check: NOT VERIFIED (human)

### P3-01 — 092d3d9

remove(candidate) and get_quota(identity)->Quota added; 11 tests. Interpretation: get_quota raises ResponseError on malformed data (never None since RESEARCH documents inspection); callers (P3-02) must treat any non-Auth ApiError from get_quota as unavailable. remove: ItemError for success:false and for 4xx with well-formed Graph error body not auth/throttle; UnknownOutcomeError for timeouts/transport/5xx/unparsable or mismatched body and non-error 4xx; AuthError/QuotaExceededError propagate from _classify (429 or codes 4,17,341). Only Operation.DELETE supported (ValueError otherwise). Quota remaining key is Operation.DELETE. Fixtures quota.json (usage 37/100 => remaining 63), delete_success.json (deleted_id 9000001).

### P3-02 — 1e4b5cb

cleanup.run now handles dry and real runs (_check_quota, _remove_all). 9 new tests. Interpretation: quota requested only if eligible non-empty; failing item deferred on QuotaExceeded/Auth, counted unknown_outcome on UnknownOutcome (rest deferred); AuthError re-raised after summary; real run with a read-only client would raise MutationBlockedError (programming error). tests/fakes.py gained fixture_api(quota=True) (me, 2 thread pages, replies, quota 63 remaining) now used by test_cleanup/test_cli. Removal order for scenario: 9000001, 7000001, 9000002, 9000003, 9000004. Output line labels: removed/failed/unknown/would remove/deferred.

### P3-03 — f07e7a5

cleanup.exit_status added; main.py builds ThreadsClient(read_only=cfg.dry_run) and returns exit_status(summary); removal-not-available branch removed. Tests: exit status matrix + 5 CLI removal tests (82 total passing). No interpretation changes.
