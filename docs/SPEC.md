# threadsdelete - repost removal specification

Version: 1.0 | Status: ready for implementation | Updated: 2026-10-24 | Tracks: issue #4

## 1. Context

threadsdelete already works: it removes the owner's own posts, quotes and replies by age, locally and from a weekly GitHub Actions run. See `README.md`, `CLAUDE.md` and `docs/RESEARCH.md`. The original build specification is archived in `docs/flights/threadsdelete/SPEC.md`; everything in it still applies unless this document changes it.

This flight adds one thing: removing the owner's **reposts**. Reposts are excluded today because no documented call removed them. A live test on 2026-10-24 (issue #4) showed removal works.

Keep every rule in `CLAUDE.md`. No live account actions during the build.

## 2. Live findings (2026-10-24)

These are `[live]` observations from the owner's account; record them in `docs/RESEARCH.md`.

- `GET /me/threads` returns reposts as records with `media_type=REPOST_FACADE`.
- `timestamp` on a `REPOST_FACADE` record is the time of the repost (the owner's action time), not the original post's time.
- `owner.id` on a `REPOST_FACADE` record equals the authenticated user's ID. All 51 reposts on the account had `owner` and `timestamp`.
- `reposted_post` comes back `null`, so the original post's ID is not available.
- `DELETE /{repost-record-id}` returns `{"success": true, "deleted_id": "<repost-record-id>"}`, the same shape as post deletion. Afterwards the record no longer exists (error code 100, subcode 33) and the original post is untouched.
- `delete_quota_usage` did not change after one repost deletion. Whether repost deletions count against the 100-per-24-hours quota is not confirmed.

## 3. Goals and non-goals

- Discover, preview and remove the owner's reposts older than `DAYS_AGO`, using the same flow, cap, quota handling, output and exit statuses as other categories.
- Non-goals: likes (still no API), undoing a repost by the original post's ID, new configuration keys, token refresh (issue #5), and the general tidy-up (issue #6).

## 4. Behavior

- **Category:** `repost` becomes a supported category. It is no longer printed as an `Excluded:` line; `like` still is.
- **Discovery:** classify `REPOST_FACADE` records from the existing `me/threads` fetch (which already requests `owner`) as `Category.REPOST` candidates. A repost whose `owner.id` is missing or differs from the authenticated user aborts discovery as ambiguous ownership, like posts. A malformed `timestamp` aborts discovery.
- **Action time:** a repost's `timestamp` is its action time for the cutoff.
- **Counting:** repost records count under `repost` `scanned`, not `post`. The summary gets a `repost:` line with the same fields as the other categories.
- **Removal:** `DELETE /{id}` on the repost record's own `id`, with the same success-body validation, error classification and no-retry rule as posts. Never use `reposted_post` or any other ID.
- **Quota:** reposts share the delete quota and `MAX_DELETIONS_PER_RUN` with posts (map `Category.REPOST` to `Operation.DELETE`). This is the safe choice while the quota question is open. Remove `Operation.UNREPOST` if nothing else uses it.

## 5. Changes

- `threadsdelete/api.py`: supported/unsupported categories, `_discover_threads`, `remove`.
- `threadsdelete/core.py`: `OPERATION_FOR` mapping for reposts.
- `docs/RESEARCH.md`: change "Category: reposts" to `Supported: yes` with the section 2 findings labeled `[live]` and dated, and update the summary and coverage table.
- `README.md`: "What is covered" table and any text saying reposts are excluded.
- Tests and fixtures:
  - in `tests/fixtures/threads_page2.json`, give repost `9000005` an `owner` and set `reposted_post` to `null` to match the live data. It is newer than the 90-day cutoff, so it stays ineligible in existing tests; add an eligible repost where a test needs one;
  - update the tests that expect reposts to be skipped and counted under `post`;
  - add tests for repost discovery, ownership failure, cutoff by repost time, removal success, and dry run sending no DELETE;
  - check that the expected counts in preview and removal tests include the `repost` line.

## 6. Done when

- All commands in `CLAUDE.md` → Commands pass, and CI is green.
- A preview against the fixtures lists eligible reposts as `would remove`, and the summary shows a `repost:` line.

Manual check (owner, after merge): run a preview with real credentials, confirm old reposts are listed with the right dates, then run one real removal and check in Threads that the reposts are gone and the originals remain.
