# Handoff

Branch: build/2026-10-25 (base: main, 99d3c9e). Tasks: 4 done, 0 blocked, 0 skipped.

## Changes
- P1-01: `Category.REPOST` maps to `Operation.DELETE`; `Operation.UNREPOST` removed.
- P1-02: reposts (`REPOST_FACADE`) discovered as candidates with owner and timestamp checks; `SUPPORTED_CATEGORIES` includes REPOST, `UNSUPPORTED_CATEGORIES` only LIKE; fixtures and tests updated.
- P1-03: README coverage updated.
- P1-04: push and manual-check record.

## Interpretation choices
- P1-01: the operation-set test asserts exact values {delete, unlike}, because the `no-unrepost-operation` constraint forbids the literal.

## Blocked/skipped
None.

## ASSUMPTION config keys
Unchanged and untuned: MAX_DELETIONS_PER_RUN=100, HTTP_TIMEOUT_SECONDS=30, MAX_READ_RETRIES=3, MAX_RETRY_WAIT_SECONDS=60.

## Manual check (human)
Owner, after merge: run a preview with real credentials, confirm old reposts are listed with the right dates, then run one real removal and check in Threads that the reposts are gone and the originals remain. Also confirm CI is green on the pull request. NOT VERIFIED (human).

## Codebase notes
- `kukulu_task_done` requires HEAD's subject to be `<ID>:`; for a log-only task make an empty commit with that subject.
- Constraint `no-unrepost-operation` also scans tests; avoid the literal there.
