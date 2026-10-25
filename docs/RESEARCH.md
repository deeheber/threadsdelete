# Threads API feasibility research

## Summary

Personal cleanup appears free of API fees: no fee, subscription or paid tier is documented for the Threads API, and an app with the owner as Threads Tester can act on the owner's own account without App Review. Supported (documentation findings): posts, media and carousel posts, quotes and replies, enumerated with cursor pagination and creation timestamps and removed with `DELETE /{id}` under a documented 100-per-24-hours deletion quota that can be inspected through `threads_publishing_limit`. Reposts: removal is undocumented, but a live check on 2026-10-24 showed `DELETE /{id}` removes them (see Live observations). Unsupported: likes (no API at all). Untested: most behavior live, because the original research used no credentials; notably quote deletion and the error code of the deletion limit (see Untested and pending).

## Sources

Retrieved 2026-10-23 with `curl` (no credentials, no token). "OK" means HTTP 200 and readable text.

| Source | Result |
| --- | --- |
| https://developers.facebook.com/documentation/threads/overview | OK. Hosts, rate limits, deletion quota. |
| https://developers.facebook.com/documentation/threads/get-started | OK. Permissions, testers, token types. |
| https://developers.facebook.com/documentation/threads/get-started/get-access-tokens-and-permissions | OK. Authorization window, code exchange. |
| https://developers.facebook.com/documentation/threads/get-started/long-lived-tokens | OK. Exchange and refresh. |
| https://developers.facebook.com/documentation/threads/posts/delete-posts | OK. `DELETE /{threads-media-id}`, `threads_delete`, 100/day. |
| https://developers.facebook.com/documentation/threads/retrieve-and-discover-posts/retrieve-posts | OK. `GET /{user-id}/threads`, fields, paging. |
| https://developers.facebook.com/documentation/threads/retrieve-and-manage-replies/retrieve-replies | OK. `GET /{user-id}/replies`. |
| https://developers.facebook.com/documentation/threads/posts/reposts | OK. `REPOST_FACADE`, `reposted_post`. |
| https://developers.facebook.com/documentation/threads/posts/quote-posts | OK. `is_quote_post`, `quoted_post`. |
| https://developers.facebook.com/documentation/threads/reference/user | OK. User edges, `threads_publishing_limit` fields, `limit`/`since`/`until`. |
| https://developers.facebook.com/documentation/threads/reference/media-retrieval | OK. Media fields. |
| https://developers.facebook.com/documentation/threads/troubleshooting | OK. Quota inspection example. |
| https://developers.facebook.com/documentation/threads/changelog | OK. Changelog current to 2026-08-18. |
| https://developers.facebook.com/docs/graph-api/guides/error-handling | OK. Graph error body and codes. |
| https://developers.facebook.com/docs/graph-api/results | OK. Cursor pagination. |
| https://developers.facebook.com/docs/threads | OK (redirects to the documentation tree above). |
| https://github.com/fbsamples/threads_api (Meta sample app) | OK. README only; no endpoint contract beyond the docs. |
| https://www.postman.com/meta/threads/... (SPEC section 9 links) | HTTP 200 but a JavaScript shell with no readable content. Not revalidated; SPEC's starting evidence (`DELETE /{thread_id}`, token exchange and refresh) is carried as "documentation finding, not revalidated" and is independently confirmed by the Meta pages above. |
| https://github.com/deeheber/blueskydelete (README, main.py) | OK. Reference categories: posts, reposts, likes. |

## Access, fees and eligibility

- [doc] No API fee, subscription or per-request charge appears anywhere in the Threads documentation tree read above (overview, get-started, delete-posts, rate limiting). The only limits are rate limits (see Quota inspection). Absence of a documented fee is not a legal guarantee; Meta's platform terms were not reviewed. Source: https://developers.facebook.com/documentation/threads/overview (2026-10-23).
- [doc] An app created with the Threads use case can act on its owner's account when the owner holds a role on the app (Threads Tester). "Threads testers can grant your app these permissions at any time. In order for app users without a role on your app to be able to grant your app these permissions, each permission must first be approved through the App Review process, and your app must be published." So own-account use needs no App Review. Source: https://developers.facebook.com/documentation/threads/get-started (2026-10-23).
- [doc] Testers are invited in App Dashboard > App roles > Roles > Add People > Threads Tester, and accepted in the Threads account's Website permissions settings. Source: same page.
- [doc] Private profiles: long-lived tokens for private profiles can be refreshed; permission grants by private-profile users are valid for 90 days (public: also 90 days, extended by refreshing the token). Public/private status does not otherwise restrict reading or deleting one's own content in the documentation read. Sources: get-started and long-lived-tokens pages (2026-10-23).
- [doc] The reference says the app may be used to "display those posts within your app solely to the person who created it": this tool only reads and deletes the owner's own data, so it is personal developer use, not serving unrelated users. Source: overview page.

## Permissions and app review

- [doc] `threads_basic`: required for every Threads endpoint. Source: get-started.
- [doc] `threads_delete`: required for any delete call, and (per the overview) for the `delete_quota_usage` and `delete_config` fields of `threads_publishing_limit`. Source: https://developers.facebook.com/documentation/threads/posts/delete-posts and overview.
- [doc] `threads_read_replies`: required for GET calls to reply endpoints (`/{user-id}/replies`). Source: get-started.
- [doc] `threads_manage_replies` (POST to reply endpoints), `threads_content_publish` (publishing), `threads_manage_insights`: not needed by this tool.
- [doc] The authorization-window documentation lists `scope` values `threads_basic, threads_content_publish, threads_read_replies, threads_manage_replies, threads_manage_insights` and does not list `threads_delete`, while the delete page requires it. Whether `threads_delete` must be requested in `scope` or is granted differently is Unknown; META_SETUP must tell the owner to request `threads_basic,threads_read_replies,threads_delete` and verify the granted scopes live (pending). Source: get-started-access-tokens-and-permissions vs delete-posts (2026-10-23).
- [doc] App Review is not needed for own-account use through a tester role (see above).
- [doc] Reading `owner` is "only available on top-level posts that you own".

## Authentication and token lifecycle

- [doc] Authorization window: `https://threads.com/oauth/authorize?client_id=<THREADS_APP_ID>&redirect_uri=<REDIRECT_URI>&scope=<SCOPES>&response_type=code`. Threads apps do not support `localhost` redirect URIs (sample app README). Authorization code: valid 1 hour, single use.
- [doc] Code to short-lived token: `POST https://graph.threads.com/oauth/access_token` with `client_id`, `client_secret`, `grant_type=authorization_code`, `redirect_uri`, `code`; response `{"access_token", "token_type", "user_id"}`. The `user_id` is the value for `THREADS_USER_ID`. Short-lived tokens last 1 hour.
- [doc] Short-lived to long-lived: `GET https://graph.threads.com/access_token?grant_type=th_exchange_token&client_secret=<APP_SECRET>&access_token=<SHORT_LIVED>`; response `{"access_token", "token_type": "bearer", "expires_in": <seconds>}` (about 5183944, 60 days). Server-side only because it carries the app secret. An expired short-lived token cannot be exchanged.
- [doc] Refresh: `GET https://graph.threads.com/refresh_access_token?grant_type=th_refresh_token&access_token=<LONG_LIVED>`; allowed when the token is at least 24 hours old and not expired, and `threads_basic` is granted; the refreshed token is valid 60 days from refresh. Tokens not refreshed within 60 days expire and cannot be refreshed.
- [doc] Revocation: no revocation endpoint was found in the documentation read. The owner removes the app under Threads Account Settings > Website permissions, or removes the tester role in the App Dashboard. Specific revocation endpoint: Unknown.
- This tool never exchanges or refreshes tokens (SPEC non-goal); these calls are for the manual steps in `docs/META_SETUP.md` only.
- Sources: https://developers.facebook.com/documentation/threads/get-started/get-access-tokens-and-permissions and .../long-lived-tokens (2026-10-23).

## Content categories

| Category | Supported | Basis |
| --- | --- | --- |
| posts (text, GIF, poll) | yes | `GET /me/threads`, `timestamp`, `DELETE /{id}` |
| media and carousel posts | yes | same endpoint; parent post only |
| quotes | yes | `is_quote_post` on `/me/threads`; `DELETE /{id}` |
| replies | yes | `GET /me/replies`, `is_reply_owned_by_me`; `DELETE /{id}` (live-verified 2026-10-25) |
| reposts | yes | `REPOST_FACADE` on `/me/threads`; `DELETE /{id}` (live-verified 2026-10-24) |
| likes | no | no documented list, timestamp or unlike endpoint |

Unsupported categories are documented here and omitted from the implementation (SPEC section 1).

## Comparison with blueskydelete

blueskydelete (README and main.py read 2026-10-23, https://github.com/deeheber/blueskydelete) cleans three collections: posts, reposts and likes, filtered by age, with `DRY_RUN`, `DAYS_AGO` and `LOG_LEVEL`. Threads parity: posts yes (plus quotes, media and carousels, and replies as SPEC extras); reposts yes (live-verified 2026-10-24); likes no (no documented API). Bluesky's age filter uses each record's own creation time, which maps to `timestamp` for Threads posts and replies. Bluesky authenticates with username and app password; Threads needs a manually replaced long-lived user token (60 days).

## Contracts

### API host and version

- [doc] Host `graph.threads.com`; the overview states the API "can be accessed by either graph.threads.com or graph.threads.net". Every current example uses `https://graph.threads.com/v1.0/...`. Use `graph.threads.com` as `API_HOST`. (CLAUDE.md's task text mentions `graph.threads.net`; per the research-contract protocol RESEARCH wins.)
- [doc] Version `v1.0`: default for `THREADS_API_VERSION`. The path form is `https://graph.threads.com/{version}/{path}`. Source: all example requests, e.g. https://developers.facebook.com/documentation/threads/posts/delete-posts (2026-10-23). No newer version string is documented in the pages read.

### Authentication transport

- [doc] Every documented request passes the token as the `access_token` query parameter ("Make sure to include the access_token parameter with your API request"). No page documents an `Authorization` header for Threads. Contract: send `access_token` as a query parameter. Consequence: the token is part of the URL, so the client must never log URLs and must redact `access_token=<value>`; httpx/httpcore loggers are pinned to WARNING. Source: delete-posts, retrieve-posts (2026-10-23).

### Identity

- [doc] `GET /me?fields=id,username` (equivalently `GET /{threads-user-id}?fields=id,username`); requires `threads_basic`. Response `{"id": "<user id>", "username": "<name>"}`. `me` is used as a path alias throughout the documentation examples (`/me/threads`). Source: https://developers.facebook.com/documentation/threads/reference/user (2026-10-23).

### Pagination

[doc] Graph cursor pagination. Page shape: `{"data": [...], "paging": {"cursors": {"before": "...", "after": "..."}, "next": "<url>", "previous": "<url>"}}`. `paging.next` is present only while more pages exist; the last page may omit `paging.next`, and the Threads examples show `paging.cursors` without `next`. A page with an empty `data` list can still carry `next`, so continue while `paging.next` exists. Page size: `limit` (default 25, maximum 100). `before` and `after` cannot be sent together. Cursors are opaque and may be invalidated if the item is deleted, which is why the tool finishes all discovery before any deletion. Continuation request: same path and params plus `after=<paging.cursors.after>`; never request the `next` URL itself (it may carry another host or the token).
Sources: https://developers.facebook.com/docs/graph-api/results ; https://developers.facebook.com/documentation/threads/reference/user (2026-10-23).

### Errors

[doc] Body shape (Graph API): `{"error": {"message": "...", "type": "OAuthException", "code": 190, "error_subcode": 460, "error_user_title": "...", "error_user_msg": "...", "fbtrace_id": "..."}}`. The Threads OAuth token endpoints use a different shape, `{"error_type", "code", "error_message"}`, but this tool never calls them.
Classification used by the client (code from `error.code`):

| Condition | Codes / status | Class |
| --- | --- | --- |
| Invalid, expired or revoked token | 190 (subcodes 458, 459, 460, 463, 464, 467, 492); HTTP 401 | `AuthError` |
| Missing permission | 10; 200-299; 3 (capability/permission); HTTP 403 | `AuthError` |
| Throttling / quota exhaustion | 4, 17, 341; HTTP 429 | `QuotaExceededError` |
| Transient server error | 1, 2; HTTP 500, 502, 503, 504 | read: retried; removal: unknown outcome |
| Item not found, already deleted or otherwise rejected | HTTP 400/404 with a well-formed error body and none of the codes above | `ItemError` on removal; `ResponseError` on reads |
| Anything else | other codes, other statuses, malformed bodies | `ResponseError` (read) / `UnknownOutcomeError` (removal) |

Notes: codes 4, 17, 341 are the documented generic Graph throttling codes; which code (if any) the Threads 100-deletions-per-day limit raises is Unknown (pending live observation), so only these documented throttling signals map to `QuotaExceededError`. The Graph error table lists code 368 (temporarily blocked) as wait-and-retry: it is not mapped to quota and stays `ResponseError` / unknown. The not-found code for Threads (Graph usually uses code 100) is Unknown; the 4xx-with-well-formed-body rule relies on HTTP semantics, not on a documented code: a 4xx means the request was rejected, not applied.
Sources: https://developers.facebook.com/docs/graph-api/guides/error-handling (2026-10-23); Threads overview (rate limits).

### Category: posts

Supported: yes
Reason: n/a
Enumerate: `GET /me/threads` with `fields=...&limit=100`, then `after=<cursor>`; no `since`/`until` (filtering happens locally).
Fields: `id,timestamp,permalink,owner,media_type,is_quote_post,reposted_post` (never `text`)
Action timestamp field: `timestamp` (creation time, ISO 8601 `2023-10-17T05:42:03+0000`); this is the owner's own creation time.
Ownership check: `owner.id` must equal the authenticated identity `id` from `GET /me`; a missing `owner` on a non-repost record or a different value is ambiguous ownership and aborts discovery. ([doc] `owner` "is only available on top-level posts that you own".)
Classification: Top-level record from `/me/threads` where `media_type` is not `REPOST_FACADE` and `is_quote_post` is not true. Text posts, images, videos, audio, GIF and poll posts all appear as top-level records (`TEXT_POST`, `IMAGE`, `VIDEO`, `CAROUSEL_ALBUM`, `AUDIO`).
Remove: `DELETE /{threads-media-id}`; success body `{"success": true, "deleted_id": "<id>"}`.
Permission: `threads_basic` (read), `threads_delete` (remove).
Quota: Shared deletion quota: 100 deletes per rolling 24 hours per profile (see Quota inspection).
Historical coverage: [doc] Not stated beyond the `since` lower bound `1688540400` (2023-07-05, Threads launch), so everything since launch is nominally reachable. Whether content created in the Threads app (not through the API) is returned is Unknown (pending live check); the documentation describes the endpoint as returning "all threads created by a user".
Evidence: https://developers.facebook.com/documentation/threads/retrieve-and-discover-posts/retrieve-posts ; https://developers.facebook.com/documentation/threads/posts/delete-posts (2026-10-23)

### Category: replies

Supported: yes
Reason: n/a
Enumerate: `GET /me/replies` with `fields=...&limit=100`, then `after=<cursor>`.
Fields: `id,timestamp,permalink,username,is_reply,is_reply_owned_by_me` (never `text`)
Action timestamp field: `timestamp` (creation time of the reply; owner's own creation time).
Ownership check: `is_reply_owned_by_me` must be `true` AND `username` must equal the identity `username`; a missing or false value aborts discovery as ambiguous ownership. (The replies list has no `owner` field.)
Classification: Every record from `/me/replies` is a reply (`is_reply` true).
Remove: `DELETE /{threads-media-id}` on the reply's own ID; same success body. [doc, inferred] The delete page says "a Threads post that was created by the authenticated user"; a reply is a Threads media object created through the same publishing flow. Not explicitly shown for replies. [live] Verified 2026-10-25: a removal run deleted three replies.
Permission: `threads_basic`, `threads_read_replies` (read), `threads_delete` (remove).
Quota: Shared deletion quota: 100 deletes per rolling 24 hours per profile (see Quota inspection).
Historical coverage: [doc] Not stated. App-created vs API-created replies: Unknown (pending).
Evidence: https://developers.facebook.com/documentation/threads/retrieve-and-manage-replies/retrieve-replies ; https://developers.facebook.com/documentation/threads/posts/delete-posts (2026-10-23)

### Category: quotes

Supported: yes
Reason: n/a
Enumerate: `GET /me/threads` with `fields=...&limit=100`, then `after=<cursor>`; no `since`/`until` (filtering happens locally).
Fields: `id,timestamp,permalink,owner,media_type,is_quote_post,reposted_post` (never `text`) plus `quoted_post`
Action timestamp field: `timestamp` (creation time; owner's own).
Ownership check: `owner.id` must equal the identity `id` (as for posts).
Classification: Record from `/me/threads` with `is_quote_post` true and `media_type` not `REPOST_FACADE`.
Remove: `DELETE /{threads-media-id}`; success body `{"success": true, "deleted_id": "<id>"}`. [doc, inferred] a quote post is created by the owner through the normal publishing flow (`quote_post_id` on the container), so it is the owner's post.
Permission: `threads_basic`, `threads_delete`.
Quota: Shared deletion quota: 100 deletes per rolling 24 hours per profile (see Quota inspection).
Historical coverage: [doc] Not stated beyond the `since` lower bound `1688540400` (2023-07-05, Threads launch), so everything since launch is nominally reachable. Whether content created in the Threads app (not through the API) is returned is Unknown (pending live check); the documentation describes the endpoint as returning "all threads created by a user".
Evidence: https://developers.facebook.com/documentation/threads/posts/quote-posts ; https://developers.facebook.com/documentation/threads/retrieve-and-discover-posts/retrieve-posts ; https://developers.facebook.com/documentation/threads/posts/delete-posts (2026-10-23)

### Category: media and carousel posts

Supported: yes
Reason: n/a
Enumerate: `GET /me/threads` with `fields=...&limit=100`, then `after=<cursor>`; no `since`/`until` (filtering happens locally).
Fields: `id,timestamp,permalink,owner,media_type,is_quote_post,reposted_post` (never `text`); `children` is not requested
Action timestamp field: `timestamp` of the parent post (creation time; owner's own).
Ownership check: `owner.id` must equal the identity `id`.
Classification: Top-level record whose `media_type` is `IMAGE`, `VIDEO`, `AUDIO` or `CAROUSEL_ALBUM` (and not a quote/repost). The parent ID is the only candidate; carousel children are never enumerated or deleted separately.
Remove: `DELETE /{threads-media-id}`; success body `{"success": true, "deleted_id": "<id>"}`. Deleting the parent removes the carousel.
Permission: `threads_basic`, `threads_delete`.
Quota: Shared deletion quota: 100 deletes per rolling 24 hours per profile (see Quota inspection).
Historical coverage: [doc] Not stated beyond the `since` lower bound `1688540400` (2023-07-05, Threads launch), so everything since launch is nominally reachable. Whether content created in the Threads app (not through the API) is returned is Unknown (pending live check); the documentation describes the endpoint as returning "all threads created by a user".
Evidence: https://developers.facebook.com/documentation/threads/retrieve-and-discover-posts/retrieve-posts ; https://developers.facebook.com/documentation/threads/posts/delete-posts (2026-10-23) ; https://developers.facebook.com/documentation/threads/reference/media-retrieval

### Category: reposts

Supported: yes [live, 2026-10-24]
Reason: [doc] The reposts page shows only `POST /{id}/repost` and the delete page never mentions reposts, so removal is undocumented. [live] Deleting a repost record with `DELETE /{id}` worked on the owner's account (see Live observations).
Enumerate: [doc] `GET /me/threads` returns reposts as `media_type=REPOST_FACADE`.
Fields: `id,timestamp,permalink,owner,media_type` (the same request as posts; never `text`)
Action timestamp field: [live] `timestamp` is the time of the repost (the owner's action time), not the original post's time.
Ownership check: [live] `owner.id` equals the authenticated identity `id`; a missing or different `owner` aborts discovery, as for posts.
Classification: `media_type == "REPOST_FACADE"`. [live] `reposted_post` is `null`, so the original post's ID is unavailable; remove by the repost record's own `id` only.
Remove: [live] `DELETE /{repost-record-id}` returns `{"success": true, "deleted_id": "<id>"}`; the record then no longer exists (error 100, subcode 33) and the original post is untouched.
Permission: `threads_basic`, `threads_delete`.
Quota: Unknown. [live] One repost deletion left `delete_quota_usage` unchanged.
Historical coverage: [live] reposts back to 2023-07 were returned.
Evidence: https://developers.facebook.com/documentation/threads/posts/reposts ; https://developers.facebook.com/documentation/threads/posts/delete-posts (2026-10-23)

### Category: likes

Supported: no
Reason: No documented endpoint lists the owner's likes, returns the time they were liked, or removes a like. The Threads reference pages (user, media-retrieval, reply-management, posts, changelog as of 2026-08-18) contain no likes edge or unlike call. Scraping or unofficial APIs are forbidden by SPEC section 1.
Enumerate: Unknown (none documented).
Fields: n/a
Action timestamp field: Unknown (the owner's like time is not exposed).
Ownership check: n/a
Classification: n/a
Remove: Unknown (none documented).
Permission: Unknown.
Quota: Unknown.
Historical coverage: Unknown.
Evidence: https://developers.facebook.com/documentation/threads/reference/user ; https://developers.facebook.com/documentation/threads/reference/media-retrieval ; https://developers.facebook.com/documentation/threads/changelog (2026-10-23)

### Removal

[doc] `DELETE https://graph.threads.com/v1.0/{threads-media-id}?access_token=<token>`; permissions `threads_basic` and `threads_delete`; limit 100 deletes per day per account. Success body to validate: JSON object with `"success": true`, and `"deleted_id"` (string) equal to the requested ID when present. The documentation example shows `{"success": true, "deleted_id": "1234567",}`; the trailing comma is a documentation typo, and the client treats an unparsable body on a 2xx as an unknown outcome, not success. Validation: status 2xx and body `success is True`; `success: false` is an item failure; any other 2xx body is unknown. There is no documented unrepost or unlike call.
Source: https://developers.facebook.com/documentation/threads/posts/delete-posts (2026-10-23).

### Quota inspection

[doc] `GET https://graph.threads.com/v1.0/{threads-user-id}/threads_publishing_limit?fields=delete_quota_usage,delete_config&access_token=<token>` (requires `threads_basic` and `threads_delete`). Response: `{"data": [{"delete_quota_usage": <int>, "delete_config": {"quota_total": 100, "quota_duration": 86400}}]}`. Remaining deletions = `quota_total - delete_quota_usage` (never below 0); the window is a rolling 24 hours (`quota_duration` seconds). Applies to the single `DELETE` operation; there are no other removal operations. A malformed or missing `data[0]` is treated as quota unavailable. Fallback when the call fails: proceed within `MAX_DELETIONS_PER_RUN` and stop at the first throttling error (codes 4, 17, 341 or HTTP 429).
Sources: https://developers.facebook.com/documentation/threads/overview ; https://developers.facebook.com/documentation/threads/troubleshooting (2026-10-23).

### Token lifetime and renewal

- [doc] Short-lived 1 hour; long-lived 60 days; refresh extends to 60 days when the token is at least 24 hours old and unexpired; a token not refreshed within 60 days is dead and the owner repeats the authorization flow.
- [doc] Permission grants last 90 days; for public profiles refreshing the token extends the grant by another 90 days, for private profiles the grant cannot be extended and must be granted again.
- Consequence for v1: the owner replaces `THREADS_ACCESS_TOKEN` (local `.env` and the GitHub secret) manually at least every 60 days (refresh by hand with the `curl` above, no more often than daily). A weekly run after expiry fails with an authentication error and exit 3.
- Source: long-lived-tokens and get-started pages (2026-10-23).

## Live observations

The original research (2026-10-23) used no credentials. Live checks on the owner's account on 2026-10-24:

- `GET /me/threads` returned 51 `REPOST_FACADE` records, all with `owner.id` equal to the user's ID and a `timestamp`; `reposted_post` was `null` on all of them.
- A new repost of a post about 15 hours old had `timestamp` set to the moment of the repost.
- `DELETE /{id}` on one old repost (of another person's post) returned `{"success": true, "deleted_id": "<id>"}`. A follow-up GET returned error 100, subcode 33. The owner confirmed in the app that the repost was gone and the original post remained.
- `delete_quota_usage` was 15 before and after that deletion. `threads_publishing_limit` returned `delete_quota_usage` and `delete_config` (`quota_total` 100, `quota_duration` 86400) as documented.
- GitHub Actions runs on 2026-10-25: a `workflow_dispatch` preview (90 days) listed 30 posts, 4 quotes and 55 replies with discovery complete. A removal run (`DAYS_AGO=365`, cap 5) removed 2 posts and 3 replies with no failed or unknown outcomes and deferred the rest. `delete_quota_usage` went from 10 to 15, and stayed at 15 after the later repost deletion.
- The owner completed `docs/META_SETUP.md` steps 1 to 7. The resulting token could delete, so `threads_delete` was granted, and it worked through the `access_token` query parameter.
- `GET /me?fields=id,username` returned exactly `id` and `username`.
- `GET /me/threads` paginated with `paging.next` and returned content created in the Threads app back to 2023-07 (text posts and reposts). `GET /me/replies` returned 68 replies back to 2024-02, all with `is_reply_owned_by_me: true`.

## Untested and pending

- Whether `DELETE /{id}` removes a quote post.
- Whether repost deletions count against the 100-per-24-hours deletion quota (one deletion left `delete_quota_usage` unchanged; re-check for a delayed update).
- Which error code and HTTP status the 100-per-day deletion limit raises.
- Ghost posts: whether `/me/threads` returns them (they have a separate `ghost_posts` edge not used here).
- Any Meta platform-terms constraint on automated personal cleanup.
- Existence of likes endpoints newer than the 2026-08-18 changelog.

## Conclusion

Decision: GO

- (a) Documented endpoint removes the owner's own posts: yes. `DELETE /{threads-media-id}` with `threads_basic` and `threads_delete` (https://developers.facebook.com/documentation/threads/posts/delete-posts, 2026-10-23).
- (b) No documented API fee or paid tier for personal developer use: yes. None found in the overview, get-started or delete pages; Meta platform terms not reviewed (listed as pending).
- (c) Owner can use their own account via an app role/tester without serving other users: yes. Testers can grant permissions without App Review (https://developers.facebook.com/documentation/threads/get-started).
- (d) SPEC section 4's architecture still fits: yes. Identity, paginated GET discovery, a quota GET and a single DELETE per item fit `api.py`/`core.py`/`cleanup.py`; no helper, database or callback service is needed. Token comes from manual steps in `docs/META_SETUP.md`.

All findings are documentation findings; none is live-verified.
