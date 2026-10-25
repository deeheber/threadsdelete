# Summary: build/2026-10-25 (repost removal)

**Merge line:** `build/2026-10-25`, base `99d3c9e` (main) → head `be893d7`, 20 commits, 2 reviews, final verdict **APPROVED** (review 2).

## What was built

**Phase 1: Repost removal (P1-01 to P1-04, plus review fix R1-01).** threadsdelete now finds and removes the owner's own reposts by age, alongside posts, quotes and replies. Reposts are the `REPOST_FACADE` records in the existing `/me/threads` fetch, so no new requests are made. Each repost goes through the same owner check as a post and is aged by its own `timestamp`, which is when the owner reposted. Each one is removed with a single `DELETE` on the repost record's own ID, and the original post is not touched. Reposts share the delete quota and `MAX_DELETIONS_PER_RUN` with posts, because `Category.REPOST` maps to `Operation.DELETE`, and `Operation.UNREPOST` is gone (P1-01). Reposts are now a supported category. The `Excluded: repost` line is gone, the summary has a new `repost:` line, and the `post` scanned count no longer includes reposts. Fixtures and tests were updated in the same commit (P1-02). The README coverage table, ownership, cutoff and quota text now describe reposts as removed (P1-03). P1-04 is the phase-end push and the record of manual checks. R1-01 added a test-only check that a `REPOST_FACADE` record is classified as a repost even when `is_quote_post` is true.

## Decisions that shaped it

- One phase: core mapping, then discovery, then README, then push. SPEC defines no phases, and the change is small (plan-level).
- P1-01: `OPERATION_FOR[Category.REPOST] = Operation.DELETE`, and `Operation.UNREPOST` is deleted. `Operation.UNLIKE` stays because `Category.LIKE` maps to it. A new constraint, `no-unrepost-operation`, enforces the removal.
- P1-01 (interpretation): the operation-set test asserts exact values `{delete, unlike}` rather than "`unrepost` not in values", because `no-unrepost-operation` also scans `tests/`. The reviewer accepted this in both rounds.
- P1-02: the task that turns reposts on also carries the fixture change and every dependent test edit, so no intermediate commit is red.
- P1-02: `SUPPORTED_CATEGORIES` order is `(POST, QUOTE, REPOST, REPLY)`. This also sets the order of discovery and of the summary lines.
- P1-02: `repost` scanned counts the `REPOST_FACADE` records, and POST scanned no longer includes them.
- P1-02: classification precedence. `media_type == "REPOST_FACADE"` makes a record a repost before `is_quote_post` is looked at. R1-01 now locks this in with a test.
- P1-02: repost ownership uses the post rule. A missing, null, non-dict, empty or foreign `owner` raises `OwnershipError`. SPEC wins over RESEARCH's "non-repost record" wording.
- P1-02: `_THREADS_FIELDS` is unchanged. `reposted_post` is never requested, read or named, and a new constraint, `no-reposted-post-id`, enforces this.
- P1-02: an already-deleted repost (code 100, subcode 33) is an `ItemError` through the existing 4xx Graph-error rule, with no special case.
- P1-02: the eligible repost fixture (`9000007`) is added only on request, via `fixture_api(eligible_repost=True)`. The default fixture keeps its 5 eligible items.
- P1-02: `threadsdelete/cleanup.py` and `main.py` are unchanged, because they iterate the category tuples.
- P1-02: `tests/test_budgets.py` is unchanged. Reposts reuse the cached `/me/threads` fetch, so the `categories = 3` bound still holds.
- P1-03: only `README.md` changes. P1-03 depends on P1-02 so the README never claims something the code does not do. RESEARCH and META_SETUP tidy-up is left to issue #6.
- Plan-level: constraints are the first flight's 19 rules plus the two new ones. `no-expression-in-run` is relaxed to allow non-`run` keys such as `group: ci-${{ github.ref }}`, which is now on `main`.
- Plan-level: `docs/kukulu.json` policies set `archive: true` and `finalize: "ready"` (SPEC section 7).
- Plan-level: no task runs a live command. A real `.env` exists in the checkout.

## Assumptions still in play

None of these defaults was tuned in this flight; all four are still guesses. Live measurements are still pending.

- `MAX_DELETIONS_PER_RUN` = 100 (untuned guess)
- `HTTP_TIMEOUT_SECONDS` = 30 (untuned guess)
- `MAX_READ_RETRIES` = 3 (untuned guess)
- `MAX_RETRY_WAIT_SECONDS` = 60 (untuned guess)

## Spec issues

From PLAN.md. Review rounds 1 and 2 repeated the first two and added the quota question. Deduplicated list:

- RESEARCH § Contracts (posts, quotes, media/carousel) still lists `reposted_post` under `Fields:`. The code never requests it, and SPEC section 4 forbids using it. This belongs to tidy-up issue #6.
- RESEARCH § Category: posts says a missing `owner` "on a non-repost record" aborts, which suggests reposts may lack `owner`. SPEC section 4 requires the owner check for reposts too, and the code follows SPEC.
- It is still unconfirmed whether repost deletions count against the 100-per-24-hours delete quota (RESEARCH line 238). The code takes the safe choice SPEC prescribes and budgets reposts as `DELETE`.
- RESEARCH § Conclusion ends "All findings are documentation findings; none is live-verified.", which contradicts its own § Live observations. Not touched (issue #6).
- SPEC section 5 "stays ineligible in existing tests; add an eligible repost where a test needs one" was read as an opt-in fixture (`fixture_api(eligible_repost=True)`). Consider wording SPEC that way.
- SPEC section 4 is silent on `Operation.UNLIKE`. It was kept because `Category.LIKE` maps to it.
- SPEC section 4 Counting does not fix the order of the summary lines. They follow `SUPPORTED_CATEGORIES`: post, quote, repost, reply.
- SPEC section 6 "CI is green" cannot be observed by the implementer, so it is a reviewer and owner check.
- The first flight's `no-expression-in-run` rule description ("do not put expressions in ... concurrency group: values") conflicts with `group: ci-${{ github.ref }}` on `main`. The rule was relaxed for non-`run` keys.

Known-gap candidates: the final REVIEW.md has no `Known-gap candidates` section, so nothing was copied.

## Manual checks owed

Phase 1:
- **Owner, after merge (NOT VERIFIED):** run a preview with real credentials and confirm old reposts are listed with the right dates. Then run one real removal and check in Threads that the reposts are gone and the originals remain.
- **CI green on the PR:** `prChecks` was `pass` at summarize time (it was `pending` during review 2). Re-confirm before merging.

## Review history

- Round 1: 1 finding (F1, test gap: repost-vs-quote precedence untested), 1 fix task (R1-01; sources: review 1, mutation 0, blocked 0). Verdict CHANGES REQUESTED, not non-converging.
- Round 2: 0 findings, 0 fix tasks. Verdict APPROVED. No finding recurred: R1-01 appears only in round 1's findings and was confirmed fixed by a killed mutant in round 2.
- **Notes-only approval (round 2):** these were flagged but not queued as work:
  - The first run of the PLAN-specified if/elif-swap mutant was inconclusive because `kukulu_mutate` left a stale `__pycache__` `.pyc`. A re-run with a length-changing replacement was killed and confirmed, and that tool run, not the implementer's log, is the evidence for R1-01.
  - Test-file mutants say nothing for R1-01. The source-mechanic mutant is the meaningful check.
  - From round 1: P1-02 and P1-03 commit bodies have no `Interpretation:` line, no commit has a `Manual check:` line, and P1-04 is a subject-only empty commit. This is history hygiene only.

## Pipeline friction

From `.kukulu/feedback.jsonl` (2 entries, in order):

- review / tool-bug: kukulu_mutate on a Python file with a same-length replacement (DELETE->UNLIKE) restored the source but left a stale __pycache__ .pyc (same size and mtime second), so the confirmKill rerun and every later test run still saw the mutant; the result was falsely 'inconclusive' and the suite stayed red until I deleted __pycache__ by hand. The tool should remove or invalidate .pyc files (e.g. PYTHONDONTWRITEBYTECODE=1 or bump mtime) when it restores.
- review / stale-bytecode: kukulu_mutate with a same-length find/replace (the PLAN-prescribed if/elif swap in api.py) restored the source within the same mtime second, leaving a stale __pycache__ .pyc of the mutant; confirmKill then reported 'inconclusive' and the next verify failed on the clean tree. Same root cause as round 1's friction entry: the tool should clear or invalidate __pycache__ (or bump mtime) on restore.

Observed in HANDOFF/REVIEW, not logged:
- The R1-01 implementer reported `kukulu_mutate` "was not available" and swapped the if/elif by hand.
- The feedback log labels the rounds 0 and 1, while REVIEW.md stamps them `Round: 1` and `Round: 2`. This off-by-one is confusing when reading both.
- The summarizer's zsh shell treated a `====` echo separator as `=cmd` expansion, which aborted a compound command. This was minor.

## Suggested CLAUDE.md additions

- `kukulu_task_done` requires HEAD's subject to be `<ID>:`; for a log-only task make an empty commit with that subject.
- Constraint `no-unrepost-operation` also scans tests; avoid the literal there.

## Advisory mutation survivors

None.

## Breaking call

Breaking: yes. The weekly cron with `DRY_RUN=false` will start irreversibly deleting reposts, a category it excluded before. The `Excluded: repost` output line is gone, a `repost:` summary line is added, and `Operation.UNREPOST` is removed. The owner should merge this by hand and then do the live check.
