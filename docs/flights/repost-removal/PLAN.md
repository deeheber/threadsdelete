# threadsdelete repost removal build plan

Derived from docs/SPEC.md v1.0 on 2026-10-25. SPEC.md wins over this file.

## Decisions

- Phases → SPEC defines none, so the plan derives one phase, "Phase 1 — Repost removal": core mapping, then discovery (the switch-on), then README, then the phase-end push. Rationale: the change is a few dozen lines of non-test code; a scaffold or polish phase would be empty.
- Task boundaries → the task that adds `Category.REPOST` to `SUPPORTED_CATEGORIES` (P1-02) also carries the fixture change and every dependent test edit in `tests/test_discovery.py`, `tests/test_cleanup.py` and `tests/test_cli.py`. Rationale: the full suite runs after every task, and the switch changes the `Excluded:` lines, POST `scanned` (5 → 4) and the summary lines at once; splitting it leaves a red intermediate commit.
- `SUPPORTED_CATEGORIES` order → `(Category.POST, Category.QUOTE, Category.REPOST, Category.REPLY)`. Rationale: the three `/me/threads` categories stay together; this order also fixes the order of the summary lines and of discovery.
- Repost scanned count → `repost` `scanned` counts the `REPOST_FACADE` records from `/me/threads`; POST `scanned` no longer includes them (SPEC section 4, Counting).
- Classification precedence → `media_type == "REPOST_FACADE"` makes a record a repost before `is_quote_post` is looked at. Rationale: RESEARCH § Category: quotes requires `media_type` not `REPOST_FACADE` for a quote.
- Repost ownership → the same rule as posts: `owner` must be a dict whose `id` equals the identity `user_id`. A missing, `null`, non-dict, empty or foreign `owner` raises `OwnershipError` (SPEC section 4, Discovery). SPEC wins over RESEARCH's posts wording ("a missing `owner` on a non-repost record").
- `_THREADS_FIELDS` → unchanged (`id,timestamp,permalink,owner,media_type,is_quote_post`). `reposted_post` is never requested or read. A new constraint, `no-reposted-post-id`, enforces this. Rationale: SPEC section 4, Removal says "Never use `reposted_post` or any other ID", and the live data returns it as `null` anyway.
- Already-deleted repost (error code 100, subcode 33) → `ItemError` through the existing "4xx with a well-formed Graph error body" rule, with no special case. Rationale: SPEC section 4 requires the same error classification as posts.
- Quota and cap → `OPERATION_FOR[Category.REPOST] = Operation.DELETE`, and `Operation.UNREPOST` is deleted (nothing else uses it). `Operation.UNLIKE` stays because `Category.LIKE` maps to it and the mapping must cover every category. A new constraint, `no-unrepost-operation` (`from: P1-01`), enforces the removal.
- Eligible repost fixture → added on request through `tests.fakes.fixture_api(eligible_repost=True)` rather than in the default fixture. Rationale: SPEC section 5 says repost `9000005` "stays ineligible in existing tests; add an eligible repost where a test needs one". The default fixture keeps its 5 eligible items, so the existing cap, deferral and DELETE-queue numbers do not change.
- `threadsdelete/cleanup.py` and `main.py` → unchanged. They iterate `SUPPORTED_CATEGORIES` and `UNSUPPORTED_CATEGORIES`, so the `Excluded: repost` line goes away and the `repost:` summary line appears automatically. If a task seems to need a change there, the implementer blocks the task rather than editing them.
- ⚠️ ASSUMPTION keys → SPEC adds none and changes none ("no new configuration keys"), so there are no tuning tasks. `tests/test_budgets.py` is unchanged: reposts reuse the cached `/me/threads` fetch and add no request, so its `categories = 3` bound is still an upper bound on read chains.
- Documentation → only `README.md` changes (P1-03). `docs/RESEARCH.md` and `docs/META_SETUP.md` already record the live findings (SPEC section 2), and their tidy-up is issue #6, which is a non-goal.
- P1-03 depends on P1-02 → so the README never claims that reposts are removed if the implementation task is blocked.
- Constraints → copied from the first flight's 19 rules (`docs/flights/threadsdelete/kukulu.json`), plus the two new rules above. `no-expression-in-run` is relaxed to allow any non-`run` YAML key mapping whose value contains `${{ }}`. Rationale: since the first flight, `main` gained `group: ci-${{ github.ref }}` in `.github/workflows/ci.yml`, which the old pattern flags but which is not shell code. `run:` lines and bare shell lines are still caught. The relaxed pattern's fixtures include the `group:` line.
- `docs/kukulu.json` policies → `archive: true` and `finalize: "ready"`, per SPEC section 7; every other policy keeps its default.
- Parallel streams → none. Four small serial tasks touch overlapping test files.
- Live commands → none in any task. A real `.env` with the owner's credentials exists in the checkout, so no task runs `./scripts/run.sh`, `uv run --env-file .env main.py` or any call to Meta (SPEC section 1: "No live account actions during the build").

## Conventions

- Commit title `<ID>: <title>`; body per `CLAUDE.md` § Flight repost-removal notes → Commit template.
- "RESEARCH" means `docs/RESEARCH.md`. Its § Contracts → Category: reposts wins on API facts; SPEC wins on behavior.
- Fixture IDs used throughout: account `1000001` / `example_owner`; posts `9000001`–`9000004`, `9000006`; fixture repost `9000005` (ineligible, 2026-09-30); added eligible repost `9000007` (2026-05-15); replies `7000001`, `7000002`. Test run start `2026-10-23T05:00:00Z`, `DAYS_AGO` 90, cutoff `2026-07-25T05:00:00Z`.

## Phase 1 — Repost removal

### P1-01: Map reposts to the delete operation

**Goal:** Make repost candidates use `Operation.DELETE`, so they share the delete quota and `MAX_DELETIONS_PER_RUN` and `ThreadsClient.remove` accepts them, and delete `Operation.UNREPOST`.
**Files touched:** `threadsdelete/core.py`, `tests/test_core.py`, `tests/test_removal_api.py`, `tests/test_cleanup.py`
**Design constraints:** SPEC section 4, Quota ("map `Category.REPOST` to `Operation.DELETE` ... Remove `Operation.UNREPOST` if nothing else uses it") and Removal ("`DELETE /{id}` on the repost record's own `id`, with the same success-body validation, error classification and no-retry rule as posts"). Constraints `core-is-pure`, `no-wall-clock-in-package` and `no-unrepost-operation` apply to `threadsdelete/core.py`: standard library only, no clock, and no `UNREPOST` or `"unrepost"` anywhere in `threadsdelete/`, `main.py` or `tests/` after this task. In `threadsdelete/core.py`, delete the `UNREPOST = "unrepost"` member from `Operation` and set `OPERATION_FOR[Category.REPOST] = Operation.DELETE`. Keep `Operation.UNLIKE` and `Category.LIKE: Operation.UNLIKE` unchanged. `threadsdelete/api.py` needs no change: `ThreadsClient.remove` already accepts any candidate whose `operation` is `Operation.DELETE` and sends exactly one `DELETE /{candidate.target_id}`. Do not change `SUPPORTED_CATEGORIES` here: reposts still are not discovered after this task, so every existing fixture count stays the same. Test protocol: follow `CLAUDE.md` § Conventions → Tests (`from tests.fakes import ...`, synthetic IDs).
**Acceptance tests:**
- `tests/test_core.py::SelectionTests::test_reposts_use_the_delete_operation`: `Candidate(Category.REPOST, "5", <aware datetime>, None).operation is Operation.DELETE`; `"unrepost"` is not among `{o.value for o in Operation}`. A repost and a post with the same ID and different action times raise `SelectionError` in `select_eligible`, because they share the `(DELETE, id)` dedupe key.
- `tests/test_removal_api.py::RemoveTests::test_only_delete_operations_are_supported`: changed to loop over `(Category.LIKE,)` only. It still asserts `ValueError` and that no request is recorded.
- `tests/test_removal_api.py::RemoveTests::test_repost_removed_by_own_record_id`: build `REPOST = Candidate(Category.REPOST, "9000005", parse_timestamp("2026-01-05T10:00:00+0000"), None)` and a `read_only=False` client, with `DELETE 9000005` → `{"success": true, "deleted_id": "9000005"}`. `remove(REPOST)` returns `None`. Exactly one request is recorded: method `DELETE`, path ending `/9000005`.
- `tests/test_removal_api.py::RemoveTests::test_repost_removal_failures_classified_like_posts`: for the same candidate, each case records exactly one request and no sleep:
  - `{"success": true, "deleted_id": "8000001"}` → `UnknownOutcomeError`
  - HTTP 400 with `{"error": {"message": "x", "type": "OAuthException", "code": 100, "error_subcode": 33}}` → `ItemError`
  - `httpx.ReadTimeout` → `UnknownOutcomeError`
  - HTTP 401 → `AuthError`
  - `error_response(4, 400)` → `QuotaExceededError`
- `tests/test_cleanup.py::SplitByBudgetTests::test_reposts_share_delete_quota_and_cap`: alternate four `Category.POST` and four `Category.REPOST` candidates in time order. `split_by_budget(items, 10, {Operation.DELETE: 3})` allows the first 3 of both categories together and defers 5. `split_by_budget(items, 4, {})` allows the first 4 (two of each category) and defers 4.
**Out of scope:** `threadsdelete/api.py` (no change needed); discovery, `SUPPORTED_CATEGORIES`, fixtures, `tests/fakes.py`; `threadsdelete/cleanup.py`, `main.py`; README; any other test file.
**Verification:** the full verify set (`kukulu_verify`); `uv run python -m unittest tests.test_core tests.test_removal_api tests.test_cleanup -v`; `grep -rn "UNREPOST\|unrepost" threadsdelete main.py tests` prints nothing.
**Depends on:** none

### P1-02: Discover reposts as removable candidates

**Goal:** Make `repost` a supported category: classify `REPOST_FACADE` records from the existing `/me/threads` fetch as `Category.REPOST` candidates with ownership and timestamp checks, count them under `repost`, and update the fixtures and every affected test in the same commit.
**Files touched:** `threadsdelete/api.py`, `tests/fixtures/threads_page2.json`, `tests/fakes.py`, `tests/test_discovery.py`, `tests/test_cleanup.py`, `tests/test_cli.py`
**Design constraints:** SPEC section 4: Category, Discovery, Action time, Counting and Removal. SPEC section 5: the fixture and test bullets. RESEARCH § Contracts → Category: reposts. Constraints on `threadsdelete/api.py`:
- `no-reposted-post-id`: do not add `reposted_post` to `_THREADS_FIELDS`, and do not read it or name it, not even in a comment or docstring.
- `no-post-body-field`, `no-token-in-logs`, `no-wall-clock-in-package`, `no-url-outside-api`, `no-hardcoded-assumption-defaults`.

Required code shape in `threadsdelete/api.py`:
1. `SUPPORTED_CATEGORIES = (Category.POST, Category.QUOTE, Category.REPOST, Category.REPLY)`. `UNSUPPORTED_CATEGORIES` keeps only `Category.LIKE` with its existing reason text.
2. In `_discover_threads`, for each record: keep the existing `media_type` check (missing or empty → `ResponseError`). Set `category = Category.REPOST` when `media_type == "REPOST_FACADE"`; otherwise `Category.QUOTE` if `is_quote_post is True`, else `Category.POST`. If `category is not wanted`, `continue`. Otherwise `scanned += 1`, run the existing owner check (`owner` must be a dict whose `id` equals `identity.user_id`; anything else raises `OwnershipError`), then append `self._candidate(category, record)`. That method parses `timestamp` with `parse_timestamp`, so a malformed value raises `TimestampError`, and the candidate's `target_id` is the record's own `id`.
3. Delete the old "repost: scanned under POST, never a candidate" branch.
4. Update the `discover` docstring: reposts are their own category.
5. `discover(Category.REPOST, ...)` reuses the cached `/me/threads` edge (`_edge`), so it adds no HTTP request.

Do not change `remove`, `get_quota`, `_classify`, `threadsdelete/cleanup.py` or `main.py`: the `Excluded:` lines and the summary lines follow `SUPPORTED_CATEGORIES` and `UNSUPPORTED_CATEGORIES`. If a test seems to need a change in those files, block the task with the reason instead.

Fixtures (synthetic only):
- In `tests/fixtures/threads_page2.json`, give record `9000005` `"owner": {"id": "1000001"}` and `"reposted_post": null`, keeping its `2026-09-30T09:00:00+0000` timestamp (ineligible at the 90-day cutoff).
- In `tests/fakes.py`, add the module constant `ELIGIBLE_REPOST = {"id": "9000007", "media_type": "REPOST_FACADE", "timestamp": "2026-05-15T09:00:00+0000", "permalink": "https://www.threads.com/@example_owner/post/AAA7", "owner": {"id": "1000001"}, "reposted_post": None}`.
- Change the signature to `fixture_api(quota: bool = True, eligible_repost: bool = False)`. When `eligible_repost` is true, the second `/me/threads` page is `load_fixture("threads_page2.json")` with `ELIGIBLE_REPOST` appended to its `data`. Update the docstring: 5 eligible items by default, 6 with `eligible_repost=True`, and `9000007` sorts last.

Expected numbers with the default fixture at the test run start (`2026-10-23T05:00:00Z`, `DAYS_AGO` 90):
- `scanned/eligible/would_remove`: POST `(4, 3, 3)`, QUOTE `(1, 1, 1)`, REPOST `(1, 0, 0)`, REPLY `(2, 1, 1)`.
- The eligible order is still `9000001, 7000001, 9000002, 9000003, 9000004`.

With `eligible_repost=True`:
- REPOST is `(2, 1, 1)`.
- The eligible order gains `9000007` as its last item.

Test protocol: follow `CLAUDE.md` § Conventions → Tests. Assert behavior: IDs, counts, recorded requests and key report lines. Do not snapshot whole outputs.
**Acceptance tests:**

`tests/test_discovery.py`:
- `test_posts_quotes_media_and_reposts_classified` (updated): on the two-page fixture, `discover` POST, QUOTE and REPOST in turn. Posts are `["9000001", "9000002", "9000003", "9000006"]`, quotes `["9000004"]`, reposts `["9000005"]` with category `Category.REPOST`. Scanned `(post, quote, repost) == (4, 1, 1)`. `9000031` is absent. `me/threads` is requested exactly twice in total (two pages, fetched once for all three categories).
- `test_repost_uses_repost_timestamp_and_own_id` (new): a single record `{"id": "5", "media_type": "REPOST_FACADE", "timestamp": "2026-01-01T00:00:00+0000", "owner": {"id": "1000001"}, "reposted_post": {"id": "8000001"}}` gives exactly one candidate with `target_id == "5"`, `category is Category.REPOST`, `action_at == datetime(2026, 1, 1, tzinfo=UTC)` and `permalink is None`.
- `test_repost_foreign_or_missing_owner_aborts` (replaces `test_repost_records_need_no_ownership_and_are_not_returned`): for repost records with `owner` `{"id": "42"}`, `None`, `{}`, `"1000001"`, and with no `owner` key, `discover(Category.REPOST, OWNER)` raises `OwnershipError`.
- `test_malformed_repost_timestamp_aborts` (new): repost records with timestamp `"2026-01-01T00:00:00"`, `"yesterday"` or `None` → `TimestampError`.
- `test_discovery_requests_never_ask_for_text` (updated): also call `discover(Category.REPOST, OWNER)`, and assert that neither `"text"` nor `"reposted_post"` is in any request's `fields`.
- `test_unsupported_categories_excluded_with_reason` (updated): also assert `set(UNSUPPORTED_CATEGORIES) == {Category.LIKE}` and `Category.REPOST in SUPPORTED_CATEGORIES`.

`tests/test_cleanup.py`:
- `test_preview_lists_eligible_candidates_from_fixtures` (updated):
  - `"Excluded: repost"` is not in the text; `"Excluded: like"` still is.
  - The counts dict equals `{POST: (4, 3, 3), QUOTE: (1, 1, 1), REPOST: (1, 0, 0), REPLY: (2, 1, 1)}`.
  - The text contains `"post: scanned=4 eligible=3 would_remove=3"` and `"repost: scanned=1 eligible=0 would_remove=0"`.
  - The listed IDs are unchanged and do not include `9000005`.
- `test_preview_lists_eligible_repost` (new): `preview(fixture_api(eligible_repost=True))` lists IDs `ELIGIBLE_ORDER + ["9000007"]`. The text contains the line `would remove  repost  9000007  https://www.threads.com/@example_owner/post/AAA7` and `"repost: scanned=2 eligible=1 would_remove=1"`. `9000005` is not listed. Only GET requests are recorded.
- `test_repost_eligibility_uses_repost_timestamp` (new): a fake with `me`, one `/me/threads` page holding two owned reposts (`9100001` at `2026-07-25T05:00:00+0000`, exactly the cutoff; `9100002` at `2026-07-25T05:00:01+0000`), `me/replies` → `{"data": []}`, and the quota fixture. The preview lists only `9100001` as `would remove`, and REPOST counts are `scanned=2 eligible=1`.
- `test_dry_run_sends_no_mutation_for_any_category` (updated): use `fixture_api(eligible_repost=True)`. Keep every existing assertion, which now requires all four categories to have eligible items, and assert `summary.counts[Category.REPOST].would_remove == 1`. No DELETE is recorded.
- `test_real_run_removes_eligible_repost_by_record_id` (new): `fixture_api(eligible_repost=True)`, with DELETE OK for every ID in `ELIGIBLE_ORDER` and `{"success": true, "deleted_id": "9000007"}` for `9000007`.
  - `deletes(fake) == ELIGIBLE_ORDER + ["9000007"]`.
  - `counts[Category.REPOST].removed == 1`, and the text contains `removed  repost  9000007`.
  - `cleanup.exit_status(summary) == ExitCode.OK`.
- `test_repost_counts_against_cap` (new): `real_run(fixture_api(eligible_repost=True), cap=5)` with DELETE OK for `ELIGIBLE_ORDER`. `9000007` is never deleted and appears as `deferred  repost  9000007`, `counts[Category.REPOST].deferred == 1`, and the exit status is OK.
- `test_foreign_repost_marks_discovery_incomplete` (new): a removal-mode run where the `/me/threads` single page holds an owned eligible post plus a repost with `owner: {"id": "42"}`. `summary.discovery_complete` is False, `"Discovery: INCOMPLETE"` is in the text, no DELETE is recorded, and `cleanup.exit_status(summary) == ExitCode.FAILURE`.

`tests/test_cli.py`:
- `CliPreviewTests::test_preview_lists_eligible_repost` (new): `run_main(fixture_api(eligible_repost=True))` with `DRY_RUN` unset. Expect exit 0, `"would remove  repost  9000007"` and `"repost: scanned=2 eligible=1 would_remove=1"` in stdout, `"Excluded: repost"` not in stdout, `"Excluded: like"` in stdout, and request methods `== {"GET"}`. This is SPEC section 6's "done when" preview.

Every other existing test in these three files keeps passing unchanged, or with only the count edits listed above.
**Out of scope:** `threadsdelete/cleanup.py`, `main.py`, `threadsdelete/core.py`, `threadsdelete/config.py`, `.env.sample`, `tests/test_budgets.py`, `tests/test_removal_api.py`, workflows, README; requesting any new field; adding an `eligible_repost` record to the default fixture; any live call.
**Verification:** the full verify set (`kukulu_verify`, including `no-reposted-post-id`); `uv run python -m unittest tests.test_discovery tests.test_cleanup tests.test_cli -v`; `grep -n reposted_post threadsdelete/*.py main.py` prints nothing.
**Depends on:** P1-01

### P1-03: README coverage for reposts

**Goal:** Update `README.md` so it describes reposts as removed: the coverage table, ownership, cutoff and quota text.
**Files touched:** `README.md`
**Design constraints:** SPEC section 5 (`README.md`: "What is covered" table and any text saying reposts are excluded), section 4 (Action time, Quota), section 2 (the quota question is open). Edits:
1. The "What is covered" intro line reads that posts, replies and reposts are live-verified and quotes are not yet.
2. The Reposts row reads `Removed (your repost only; the original post is untouched)`.
3. The ownership paragraph adds that reposts must carry an `owner` equal to your user ID.
4. The Cutoff paragraph says reposts use the time you reposted, not the original post's age.
5. The "Quota and backlog" section says that repost removals count against `MAX_DELETIONS_PER_RUN` and are budgeted against the same deletion quota, and that whether Meta counts them toward the 100-per-24-hours limit is not confirmed (one live repost deletion left the usage unchanged).
6. Where the report's per-category counts are described, name the categories `post`, `quote`, `repost`, `reply`.

The Likes row stays "Excluded". Use no real IDs or tokens. Keep every other section as it is.
**Acceptance tests:** none (documentation task).
**Out of scope:** `docs/RESEARCH.md`, `docs/META_SETUP.md`, `docs/flights/`, code, tests, workflows, `.env.sample`; the token-refresh (#5) and tidy-up (#6) issues.
**Verification:** the full verify set; `grep -n "Excluded for now\|implementation planned" README.md` prints nothing; `grep -n "Reposts" README.md` shows the "Removed" row; `grep -n "Likes" README.md` still shows "Excluded".
**Depends on:** P1-02

### P1-04: Phase 1 close — push and manual checks

**Goal:** Run the build check, push the branch and record the owner's manual check from SPEC section 6.
**Files touched:** `docs/PROGRESS.md` (log entry only)
**Design constraints:** SPEC section 6 (Done when; Manual check). Follow the phase-end protocol in `CLAUDE.md` § Flight repost-removal notes. Never run a live command: a real `.env` exists in the checkout.
**Acceptance tests:** none.
**Out of scope:** code or doc changes; fixing a failing check (block the task with the failing command instead); running `./scripts/run.sh` or `uv run --env-file .env main.py`.
**Verification:**
1. Run the full verify set and `uv run python -m compileall -q threadsdelete main.py`.
2. Run `git push -u origin HEAD`, recording a failure in the log if it fails.
3. Write a log entry that lists, verbatim: "Owner, after merge: run a preview with real credentials, confirm old reposts are listed with the right dates, then run one real removal and check in Threads that the reposts are gone and the originals remain. Also confirm CI is green on the pull request." followed by `Manual check: NOT VERIFIED (human)`.
**Depends on:** none

## Spec issues

- RESEARCH § Contracts → Category: posts, quotes, and media and carousel posts list `reposted_post` under `Fields:`, but the code has never requested it, and SPEC section 4 forbids using it. Resolution: `_THREADS_FIELDS` stays unchanged, and the `no-reposted-post-id` constraint keeps the field name out of the package. The RESEARCH wording belongs to the tidy-up issue #6.
- RESEARCH § Category: posts says a missing `owner` "on a non-repost record" aborts, which suggests reposts may lack `owner`. SPEC section 4 says a repost with a missing `owner.id` aborts too. Resolution: SPEC wins on behavior, so reposts get the same owner check as posts.
- RESEARCH § Conclusion ends with "All findings are documentation findings; none is live-verified.", which contradicts its own § Live observations. Resolution: not touched in this flight (issue #6 is a non-goal); noted for the owner.
- SPEC section 5 says the fixture repost "stays ineligible in existing tests; add an eligible repost where a test needs one". Read as: the default fixture's eligibility is unchanged, and an eligible repost (`9000007`) is added on request through `fixture_api(eligible_repost=True)`.
- SPEC section 4 says "Remove `Operation.UNREPOST` if nothing else uses it" and is silent on `Operation.UNLIKE`. Resolution: `UNLIKE` stays, because `Category.LIKE` maps to it and the mapping must cover every category.
- SPEC section 4, Counting does not fix the order of the summary lines. Resolution: they follow `SUPPORTED_CATEGORIES` order: post, quote, repost, reply.
- SPEC section 6 "CI is green" cannot be observed by the implementer. Resolution: the reviewer checks the pull request's CI; P1-04 lists it as a manual check.
- Since the first flight, `main` gained `group: ci-${{ github.ref }}` in `.github/workflows/ci.yml`, which the first flight's `no-expression-in-run` rule (and its description, "do not put expressions in ... concurrency group: values") flags. Resolution: the rule is relaxed to allow any non-`run` key mapping (see Decisions). The line interpolates into a concurrency key, not shell code, so the rule's intent still holds.

## Review fixes (round 1)

### R1-01: Test that REPOST_FACADE wins over the quote flag in classification

**Goal:** Cover SPEC section 4 Discovery (REPOST_FACADE records are Category.REPOST candidates) and the PLAN decision 'Classification precedence': a REPOST_FACADE record is classified as a repost before is_quote_post is looked at. Today, swapping the if/elif branches in threadsdelete/api.py _discover_threads (line ~325) survives the whole offline suite.
**Files touched:** tests/test_discovery.py
**Design constraints:** Test-only change; threadsdelete/api.py is correct and must not change. Follow CLAUDE.md Conventions → Tests: import from tests.fakes, synthetic IDs (owner 1000001 / example_owner). Constraint no-unrepost-operation scans tests/, so never write the UNREPOST name or the 'unrepost' string literal. No 'reposted_post' needed in the record.
**Acceptance tests:** New tests/test_discovery.py::ThreadsEdgeTests::test_repost_facade_wins_over_quote_flag: using threads_fake with one record {"id": "5", "media_type": "REPOST_FACADE", "is_quote_post": True, "timestamp": "2026-01-01T00:00:00+0000", "owner": {"id": "1000001"}}, discover(Category.REPOST, OWNER) returns exactly one candidate with category is Category.REPOST and target_id "5" and scanned == 1; discover(Category.QUOTE, OWNER) on the same client returns ([], 0). Both assertions are required: the QUOTE one is what fails when the branches are swapped.
**Out of scope:** threadsdelete/api.py and every other source file; fixtures and tests/fakes.py; README; any other test file.
**Verification:** Full verify set (kukulu_verify). Then the reviewer's mutant must be killed: kukulu_mutate on threadsdelete/api.py swapping the `if media_type == _REPOST_TYPE:\n                category = Category.REPOST\n            elif record.get("is_quote_post") is True:\n                category = Category.QUOTE` block so the is_quote_post check comes first, with targeted: unit, filter: tests.test_discovery → killed: true.
**Depends on:** none
