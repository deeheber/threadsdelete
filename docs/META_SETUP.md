# Meta setup and token maintenance

Steps 1 to 7 were verified on the owner's account on 2026-10-24. Steps 8 and 9 come from Meta's documentation (2026-10-23).

Commands use placeholders. Never put real IDs, secrets or tokens in docs, issues or commits. Sources and unknowns: [RESEARCH.md](RESEARCH.md).

## Personal developer access versus serving other users

Use a development-mode app with yourself as its only Threads Tester; no App Review is needed. Serving other accounts requires App Review and publication and is out of scope. No API fee is documented; see [access findings](RESEARCH.md#access-fees-and-eligibility).

## 1. Developer registration

1. Sign in at https://developers.facebook.com with a Meta account and complete the "Get started" developer registration if prompted (verification steps vary by account).
2. Your Threads account must exist and be the one you want cleaned.

## 2. Create the app and choose the Threads use case

1. In the App Dashboard choose Create app and select the use case for accessing the Threads API.
2. Open App settings, Basic. Use the Threads app ID (`<APP_ID>`) and Threads app secret (`<APP_SECRET>`), not the regular app credentials.
3. Under the Threads use case, open **Permissions and features** and enable `threads_basic`, `threads_read_replies` and `threads_delete`.
4. Add a redirect callback URL in the Threads use case settings. Use an HTTPS URL such as `https://example.com/callback/`, not `localhost`. Call it `<REDIRECT_URI>` and match it exactly, including any trailing slash Meta adds. The page need not load: copy `code` from the browser address bar after approval.

## 3. Testers (own-account role)

1. App Dashboard, App roles, Roles, Add People, choose Threads Tester, and enter your Threads username.
2. Accept the invitation in Threads: Account settings, Website permissions (web or mobile app), signed in as that account.
3. Until you accept, the authorization in step 5a fails.

## 4. Permissions

| Permission | Why |
| --- | --- |
| `threads_basic` | Required for every endpoint (identity, listing posts). |
| `threads_read_replies` | Listing your own replies. |
| `threads_delete` | Removing content and reading the deletion quota. |

Despite its omission from the authorization-window docs, `threads_delete` is required. Verified 2026-10-24: enabling it in step 2.3 and requesting all three permissions in step 5a produced a token that could delete.

## 5. Token acquisition and exchange (manual)

Only manual token exchange uses the app secret; cleanup uses the long-lived user token.

**a. Authorization code.** Open this URL in a browser while signed in as the tester account (one line):

```
https://threads.com/oauth/authorize?client_id=<APP_ID>&redirect_uri=<REDIRECT_URI>&scope=threads_basic,threads_read_replies,threads_delete&response_type=code
```

Approve. You are redirected to `<REDIRECT_URI>?code=<CODE>#_`. Copy `<CODE>` without the trailing `#_`. It is valid for 1 hour and works once.

**b. Short-lived token** (valid 1 hour):

```
curl -X POST https://graph.threads.com/oauth/access_token \
  -F client_id=<APP_ID> -F client_secret=<APP_SECRET> \
  -F grant_type=authorization_code -F redirect_uri=<REDIRECT_URI> -F code=<CODE>
```

The response contains `access_token` (`<SHORT_LIVED_TOKEN>`) and `user_id`.

**c. Long-lived token** (valid 60 days):

```
curl "https://graph.threads.com/access_token?grant_type=th_exchange_token&client_secret=<APP_SECRET>&access_token=<SHORT_LIVED_TOKEN>"
```

The response has `access_token` (`<LONG_LIVED_TOKEN>`) and `expires_in` in seconds. Do this while the short-lived token is still valid; an expired one cannot be exchanged.

## 6. Account ID

The `user_id` from step 5b is your `THREADS_USER_ID`. You can also confirm it with the token:

```
curl "https://graph.threads.com/v1.0/me?fields=id,username&access_token=<LONG_LIVED_TOKEN>"
```

The tool compares this to `THREADS_USER_ID` on every run and refuses to continue (exit 3) if they differ.

## 7. Store the credentials

- Local: put `THREADS_ACCESS_TOKEN=<LONG_LIVED_TOKEN>` and `THREADS_USER_ID=<USER_ID>` in `.env` (git-ignored; see `.env.sample`).
- GitHub Actions: repository Secret `THREADS_ACCESS_TOKEN` and repository Variable `THREADS_USER_ID` (see the README).
- Do not store the app secret in either place.

## 8. Expiry and manual renewal

- Long-lived tokens last 60 days. A token can be refreshed once it is at least 24 hours old and not yet expired; a token that has not been refreshed within 60 days expires for good.
- Refresh by hand (calendar a reminder well before day 60):

```
curl "https://graph.threads.com/refresh_access_token?grant_type=th_refresh_token&access_token=<LONG_LIVED_TOKEN>"
```

- Replace the old value with the new `access_token` in the local `.env` **and** in the GitHub Secret (Settings, Secrets and variables, Actions, edit `THREADS_ACCESS_TOKEN`).
- If the token already expired, repeat steps 5a to 5c.
- Permission grants themselves last 90 days; refreshing a public-profile token extends the grant, but for a private profile the grant cannot be extended and you must authorize again (step 5a).
- When the token has expired, scheduled runs fail with exit status 3 until you replace it.

## 9. Revocation

Remove the app under Threads Account settings, Website permissions, or remove your Threads Tester role in the App Dashboard. No revocation endpoint was found in the documentation (RESEARCH: Unknown). Rotate or reset the app secret in the dashboard if it was ever exposed.

## 10. What is not verified yet

The deletion-limit error is still unverified; see [pending checks](RESEARCH.md#untested-and-pending).
