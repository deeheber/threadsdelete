# Review: build/2026-10-25 (repost removal)
Round: 1

**Verdict: CHANGES REQUESTED**

Base `99d3c9e`, head `00ecdb9` (+ `aa14f52`, a review feedback-log commit). Tasks reviewed: P1-01, P1-02, P1-03, P1-04 (all done, none blocked or skipped).

## What was checked

- **Constraints (category 1):** `kukulu_verify` ran all 21 rules; every rule self-tested clean (`fixture: null`) and reported no hits. All verify commands passed (lock check, mypy, ruff check, ruff format, 106 offline tests, `--help`). By-reading checks: `threadsdelete/cleanup.py` and `main.py` are untouched on this branch, so dry run still builds `ThreadsClient(read_only=True)`, all discovery still finishes before the first `remove`, and `remove` is still called at most once per candidate with no retry wrapper. `remove` rejects any non-`DELETE` operation and sends one `DELETE /{candidate.target_id}`. No workflow, `scripts/run.sh`, `.gitignore` or editor-config change on the branch, so the `run: |` and `exec`/`pipefail` checks have nothing new to look at. Fixtures are synthetic (`1000001`, `example_owner`, `9000007`, `9100001` and so on). `reposted_post` is never requested or read in the package; `no-reposted-post-id` agrees.
- **Boundaries (category 2):** clean. No config value hard-coded outside `config.py`; no module-boundary crossing; only the files PLAN lists were touched.
- **Tests (category 3):** every acceptance test PLAN names exists and asserts behavior (IDs, counts, recorded requests, report lines). Mutation sample: 6 mutants on `threadsdelete/core.py` and `threadsdelete/api.py`; 5 killed, 1 survived (see Findings). Sweep on `api.py` after the survivor: the repost branch mapped to POST (killed), repost `scanned` not counted (killed), `_edge` cache disabled (killed), and repost owner check bypassed (killed).
- **Spec drift (category 5):** none. `SUPPORTED_CATEGORIES` order, the `UNSUPPORTED_CATEGORIES` = `{LIKE}` result, counting, ownership and the cutoff by repost time all match SPEC section 4 and PLAN P1-02. The README edits match P1-03 items 1 to 6.
- **Interpretation choices (category 6):** P1-01 asserts `{o.value for o in Operation} == {"delete", "unlike"}` instead of "`unrepost` not in values". The `no-unrepost-operation` rule scans `tests/`, which forces this, and the check is at least as strict as PLAN's. Accepted.
- **Blocked/skipped (category 7):** none.
- **PR checks:** `prChecks.state` is `pass` (no failing checks).

## Findings

### F1 (category 3, test gap): repost-vs-quote classification precedence is untested (R1-01)

- **Where:** `threadsdelete/api.py:325`, the `if media_type == _REPOST_TYPE:` / `elif record.get("is_quote_post") is True:` chain in `_discover_threads`.
- **What is wrong:** swapping the two branches, so that `is_quote_post` is checked before `media_type == "REPOST_FACADE"`, survives both `tests.test_discovery` and the full offline suite. No fixture or test has a `REPOST_FACADE` record with `is_quote_post: true`.
- **What would break:** SPEC section 4, Discovery says to classify `REPOST_FACADE` records as `Category.REPOST`, with no condition. The PLAN decision "Classification precedence" says `media_type == "REPOST_FACADE"` makes a record a repost before `is_quote_post` is looked at, and RESEARCH says a quote's `media_type` is not `REPOST_FACADE`. A refactor that reorders the checks would silently relabel such a repost as a quote: the wrong category line, wrong `scanned` counts and a wrong report label. Nothing would catch it.
- **Minimal fix:** a test only; the code is correct. Add a discovery test where a `REPOST_FACADE` record carrying `is_quote_post: true` comes back from `discover(Category.REPOST, ...)` as one `Category.REPOST` candidate with scanned 1, and `discover(Category.QUOTE, ...)` on the same fake returns `([], 0)`.

## Spec issues

Carried from PLAN § Spec issues and confirmed against `docs/RESEARCH.md`. These are for the owner and do not block anything:

- RESEARCH § Contracts → posts, quotes, and media/carousel (lines 120, 150, 165) still list `reposted_post` under `Fields:`. The code never requests it, and SPEC section 4 forbids using it. This belongs to tidy-up issue #6.
- RESEARCH § Category: posts (line 122) says a missing `owner` "on a non-repost record" aborts, which suggests reposts may lack `owner`. SPEC section 4 requires the owner check for reposts too, and the code follows SPEC.
- Whether repost deletions count against the 100-per-24-hours quota is still open (RESEARCH line 238). The code takes the safe choice that SPEC prescribes: reposts are budgeted as `DELETE`.

## Manual checks still owed

- Owner, after merge: run a preview with real credentials, confirm old reposts are listed with the right dates, then run one real removal and check in Threads that the reposts are gone and the originals remain. NOT VERIFIED (human).
- Confirm CI is green on the pull request. The reviewer saw `prChecks: pass` at review time; re-confirm after the fix round.

## Notes

- The first `core.py` mutant (`Operation.DELETE` → `Operation.UNLIKE`, same length) came back "inconclusive". The cause was a stale `__pycache__` `.pyc` left after the tool restored the file (same size, same mtime second), not the code. I cleared `__pycache__` (ignored files) and re-ran the mutant with a length-changing replacement: killed. Logged as pipeline friction in `aa14f52`.
- Task commit bodies only partly follow the `CLAUDE.md` § Flight repost-removal notes → Commit template. P1-02 and P1-03 have no `Interpretation:` line, and no commit has a `Manual check:` line. P1-04 is an empty commit with only a subject. This is history hygiene only.
- The precedence rule in F1 is also written down in `CLAUDE.md` § Flight repost-removal notes ("that check comes before `is_quote_post`").
