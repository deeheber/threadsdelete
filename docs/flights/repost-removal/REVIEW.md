# Review: build/2026-10-25 (repost removal)
Round: 2

**Verdict: APPROVED**

Base `99d3c9e`, head `079c168` (plus `09b8d85`, a review feedback-log commit). Last review commit `7c48260`. Tasks: P1-01 to P1-04 (reviewed in round 1) and R1-01 (this round). All 5 done, none blocked or skipped.

## What was checked

- **PR checks:** `prChecks.state` was `pending` with no failing checks at review time. That is not a finding. CI still has to go green on the PR before merge (see Manual checks).
- **Constraints (category 1):** `kukulu_verify` ran all 21 rules. Every rule self-tested clean (`fixture: null`) with no hits. I re-read the whole branch diff to `threadsdelete/` (`api.py`, `core.py`). `cleanup.py`, `main.py`, the workflows and `scripts/run.sh` are unchanged, so the read-only dry-run client, discovery-before-mutation, the single `remove` per candidate and the `exec`/`pipefail` checks all still hold. `reposted_post` is never requested or used. Fixtures are synthetic.
- **Boundaries (category 2):** clean. R1-01 touched only `tests/test_discovery.py`, as PLAN requires. There were no `.gitignore`, editor-config or CI edits.
- **Tests (category 3):** with a clean bytecode cache, every verify command passes: lock check, mypy, ruff check, ruff format, 107 offline tests and `--help`. R1-01 added `ThreadsEdgeTests::test_repost_facade_wins_over_quote_flag`, which matches the PLAN acceptance test: a `REPOST_FACADE` record with `is_quote_post: True` comes back as one `Category.REPOST` candidate `"5"` with scanned 1, and `discover(Category.QUOTE, ...)` returns `([], 0)`.
- **Mutation (round 2, scoped to the files the last fix round changed):** that round changed only `tests/test_discovery.py`, so I mutated the mechanic it covers. The mutant swaps the `if media_type == _REPOST_TYPE` / `elif is_quote_post` branches in `threadsdelete/api.py` `_discover_threads`, run with `targeted: unit`, `filter: tests.test_discovery` and `confirmKill: true`. Result: **killed**. The new test fails on the mutant and passes on the clean tree in the confirm run. Round 1's F1 is closed.
- **Spec drift (category 5):** none. Classification, owner check, timestamp-based cutoff, separate `repost` counting, `Category.REPOST -> Operation.DELETE`, removal of `Operation.UNREPOST`, and `UNSUPPORTED_CATEGORIES == {LIKE}` all match SPEC section 4. SPEC section 7 policies (`archive: true`, `finalize: "ready"`) are set.
- **Interpretation choices (category 6):** P1-01 checks the exact operation values `{delete, unlike}` because the `no-unrepost-operation` rule scans `tests/`. Accepted in round 1 and still accepted. R1-01 lists none.
- **Blocked/skipped (category 7):** none.

## Findings

None.

## Spec issues

Carried from round 1. These are for the owner and block nothing:

- RESEARCH § Contracts (posts, quotes, media/carousel) still lists `reposted_post` under `Fields:`. The code never requests it, and SPEC section 4 forbids using it. This belongs to tidy-up issue #6.
- RESEARCH § Category: posts says a missing `owner` "on a non-repost record" aborts, which suggests reposts may lack `owner`. SPEC section 4 requires the owner check for reposts too, and the code follows SPEC.
- It is still unconfirmed whether repost deletions count against the 100-per-24-hours delete quota. The code takes the safe choice that SPEC prescribes: reposts are budgeted as `DELETE`.

## Manual checks still owed

- Owner, after merge: run a preview with real credentials and confirm old reposts are listed with the right dates. Then run one real removal and check in Threads that the reposts are gone and the originals remain. NOT VERIFIED (human).
- Confirm CI is green on the pull request. `prChecks` was `pending` at review time.

## Notes

- **The first run of the PLAN-specified mutant was inconclusive because of the tool, not the code.** I ran it as an exact same-length if/elif swap. `kukulu_mutate` restored `api.py` in the same mtime second it compiled the mutant, so `threadsdelete/__pycache__/api.cpython-314.pyc` kept the mutant's bytecode. CPython checks a `.pyc` against the source's mtime and size, and both matched, so the confirm run, and a `kukulu_verify` I had started at the same time, failed on the clean tree. A fresh `PYTHONPYCACHEPREFIX` run passed. I deleted the ignored `__pycache__` directories, re-ran verify (green), then re-ran the mutant with a trailing `# swapped` comment so the size differs. That run was killed and confirmed. This is the same root cause as round 1's friction entry, and I logged it again (`09b8d85`). R1-01's log says the implementer "manually swapped the if/elif". The implementer could have hit the same stale-cache trap, so this tool-run kill, not the log, is the evidence that the test works.
- Removing an assertion from `tests/test_discovery.py` would trivially leave the test passing, so test-file mutants say nothing here. The mutant above, against the source mechanic, is the meaningful check for R1-01.
- The R1-01 commit body follows the commit template (Goal, Tests, Interpretation, Manual check). The round 1 note about P1-02 to P1-04 commit bodies still stands as history hygiene only.
