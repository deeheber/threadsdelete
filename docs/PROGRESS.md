# threadsdelete token refresh build progress

Branch: build/2026-10-27
Started: 2026-10-27T01:39:46.742Z

## Tasks

- [x] P1-01 Refresh script with the local .env destination
- [x] P1-02 Actions destination for the refresh script
- [x] P1-03 Monthly refresh workflow
- [x] P1-04 Setup guide and research notes for automatic refresh
- [x] P1-05 README and .env.sample for token refresh
- [x] P1-06 Phase 1 close — push and manual checks

## Log

(one entry per task, appended by implement)

### P1-01 — 2e32e19

Added scripts/refresh-token.sh (100755) and tests/test_refresh_token.py (10 tests, fake curl/gh harness with prepare(mode=...) helper, MODES=("local",)). Actions mode dies at step 1 with die_before (P1-02 replaces). Interpretation: curl failure messages are "failed, curl exit N." to avoid curl-q-first matching "(curl". Helper assert_unchanged only handles local mode; P1-02 must extend it for Actions. Harness: Harness.prepare returns Result(code,out,err,calls); fake gh reads responses/gh.json list_exit/set_exit. Manual check: NOT VERIFIED (human).

### P1-02 — b98d3ee

Actions mode implemented in scripts/refresh-token.sh (inputs validated via eval on four fixed key names; gh secret list pre-check exit 2; gh secret set on stdin exit 1 on failure). Tests: ActionsRefreshTests (4) added; MODES=("local","actions"); Harness.prepare now clears .env/.env.* between subtests, defaults env_text to None in actions mode, extra_env value None unsets a var; assert_unchanged takes the Result. Manual check: NOT VERIFIED (human).

### P1-03 — 9f5abfe

Added .github/workflows/refresh-token.yml (exact content from task) and tests: RefreshWorkflowTests (4), SharedWorkflowTests now loop over ALL workflows (pinning, no expressions in run, no pull_request_target, coverage). ci.yml/cleanup-feed.yml untouched. Manual check: NOT VERIFIED (human).

### P1-04 — 170eb2e

Rewrote META_SETUP section 8 ("Expiry and refresh"), intro line, README anchor, and RESEARCH edits (six items). Docs only. Note: the task's grep for the old anchor over docs/*.md still hits docs/PLAN.md (it quotes it); README and META_SETUP are clean. Manual check: NOT VERIFIED (human).

### P1-05 — 2e248cf

README: Token maintenance rewritten, three workflows, SECRETS_WRITE_TOKEN as numbered step 3 (steps renumbered), inactivity bullet extended. .env.sample: only the token comment changed. Docs only. Manual check: NOT VERIFIED (human).

### P1-06 — 472a80e

Verify set green at 2e248cf (126 tests), compileall and bash -n ok, git diff --stat main -- threadsdelete main.py empty. Push: git push -u origin HEAD succeeded (build/2026-10-27). Empty commit made so the task commit subject exists.
Owner, after merge, in order:
(1) create the PAT, add the SECRETS_WRITE_TOKEN secret, and check that Actions failure notifications are on (docs/META_SETUP.md §8);
(2) with the current token at least 24 hours old, run "Refresh token" by manual dispatch and check that the log shows the "saved to the repository secret" line and no token, and that gh secret list shows THREADS_ACCESS_TOKEN just updated;
(3) run "Threads cleanup" by manual dispatch with dry_run true and check that authentication succeeds.
Recommended:
(4) if the local .env held the same token, run DRY_RUN=true ./scripts/run.sh before refreshing it locally;
(5) if that worked, run ./scripts/refresh-token.sh locally and preview again; otherwise give local its own token (§5);
(6) record in docs/RESEARCH.md as [live] whether the token string changed and the old token stayed valid, and update the shared-vs-separate guidance in docs/META_SETUP.md §8.
Also confirm CI is green on the pull request.
Manual check: NOT VERIFIED (human)
