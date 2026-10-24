# threadsdelete build progress

Branch: build/2026-10-24
Started: 2026-10-24T02:37:10.812Z

## Tasks

- [x] P1-01 Research access, fees, permissions and token lifecycle
- [x] P1-02 Research content categories, removal, quota and payload contracts
- [x] P1-03 Decide go or no-go
- [x] P1-04 Phase 1 close — push and manual checks
- [ ] P2-01 Project scaffold
- [ ] P2-02 Configuration parsing and .env.sample
- [ ] P2-03 Core candidate types, timestamps and eligibility
- [ ] P2-04 API client transport, pagination, retries and redaction
- [ ] P2-05 Category discovery and record validation
- [ ] P2-06 Tune HTTP_TIMEOUT_SECONDS, MAX_READ_RETRIES and MAX_RETRY_WAIT_SECONDS
- [ ] P2-07 Cleanup preview: identity, complete discovery, selection and report
- [ ] P2-08 Entry point, logging and local wrapper
- [ ] P2-09 Phase 2 close — push and manual checks
- [ ] P3-01 API removal and quota inspection
- [ ] P3-02 Sequential removal with quota budget
- [ ] P3-03 Exit statuses and removal mode in the entry point
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
