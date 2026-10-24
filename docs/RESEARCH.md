# Threads API feasibility research

## Summary

Pending (P1-03).

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

Pending (P1-02).

## Comparison with blueskydelete

Pending (P1-02).

## Contracts

### API host and version

- [doc] Host `graph.threads.com`; the overview states the API "can be accessed by either graph.threads.com or graph.threads.net". Every current example uses `https://graph.threads.com/v1.0/...`. Use `graph.threads.com` as `API_HOST`. (CLAUDE.md's task text mentions `graph.threads.net`; per the research-contract protocol RESEARCH wins.)
- [doc] Version `v1.0`: default for `THREADS_API_VERSION`. The path form is `https://graph.threads.com/{version}/{path}`. Source: all example requests, e.g. https://developers.facebook.com/documentation/threads/posts/delete-posts (2026-10-23). No newer version string is documented in the pages read.

### Authentication transport

- [doc] Every documented request passes the token as the `access_token` query parameter ("Make sure to include the access_token parameter with your API request"). No page documents an `Authorization` header for Threads. Contract: send `access_token` as a query parameter. Consequence: the token is part of the URL, so the client must never log URLs and must redact `access_token=<value>`; httpx/httpcore loggers are pinned to WARNING. Source: delete-posts, retrieve-posts (2026-10-23).

### Identity

- [doc] `GET /me?fields=id,username` (equivalently `GET /{threads-user-id}?fields=id,username`); requires `threads_basic`. Response `{"id": "<user id>", "username": "<name>"}`. `me` is used as a path alias throughout the documentation examples (`/me/threads`). Source: https://developers.facebook.com/documentation/threads/reference/user (2026-10-23).

### Pagination

Pending (P1-02).

### Errors

Pending (P1-02).

### Category: posts

Pending (P1-02).

### Category: replies

Pending (P1-02).

### Category: quotes

Pending (P1-02).

### Category: media and carousel posts

Pending (P1-02).

### Category: reposts

Pending (P1-02).

### Category: likes

Pending (P1-02).

### Removal

Pending (P1-02).

### Quota inspection

Pending (P1-02).

### Token lifetime and renewal

- [doc] Short-lived 1 hour; long-lived 60 days; refresh extends to 60 days when the token is at least 24 hours old and unexpired; a token not refreshed within 60 days is dead and the owner repeats the authorization flow.
- [doc] Permission grants last 90 days; for public profiles refreshing the token extends the grant by another 90 days, for private profiles the grant cannot be extended and must be granted again.
- Consequence for v1: the owner replaces `THREADS_ACCESS_TOKEN` (local `.env` and the GitHub secret) manually at least every 60 days (refresh by hand with the `curl` above, no more often than daily). A weekly run after expiry fails with an authentication error and exit 3.
- Source: long-lived-tokens and get-started pages (2026-10-23).

## Live observations

Pending (P1-02).

## Untested and pending

Pending (P1-02).

## Conclusion

Pending (P1-03).
