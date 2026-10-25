# Meta setup and token maintenance

Steps 1 to 7 were verified on the owner's account on 2026-10-24. Steps 8 and 9 come from Meta's documentation (2026-10-23).

Every command uses placeholders: never paste real IDs, secrets or tokens into this file, the README, an issue or a commit. Facts and sources are in [RESEARCH.md](RESEARCH.md); items it marks Unknown are called out below.

## Personal developer access versus serving other users

This tool uses an app in development mode with **you** as the only Threads Tester. Testers can grant the app its permissions without Meta's App Review. Serving other people's accounts would require App Review and a published app; that is out of scope for this project. No API fee is documented for this use (RESEARCH, "Access, fees and eligibility").

## 1. Developer registration

1. Sign in at https://developers.facebook.com with a Meta account and complete the "Get started" developer registration if prompted (verification steps vary by account).
2. Your Threads account must exist and be the one you want cleaned.

## 2. Create the app and choose the Threads use case

1. In the App Dashboard choose Create app and select the use case for accessing the Threads API.
2. Open App settings, Basic. There are two sets of IDs and secrets; use the **Threads app ID** and **Threads app secret**, not the regular ones. Call them `<APP_ID>` and `<APP_SECRET>` below.
3. Under the Threads use case, enable the permissions `threads_basic`, `threads_read_replies` and `threads_delete`.
4. Add a redirect callback URL in the Threads use case settings. Threads does not accept `localhost`. Use any HTTPS URL you control or a placeholder such as `https://example.com/callback/`; you only need to read the `code` parameter from the browser's address bar after approval, so the page itself does not have to load. The value must match exactly (Meta may add a trailing slash). Call it `<REDIRECT_URI>`.

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

Unverified: Meta's authorization-window documentation lists `threads_basic, threads_content_publish, threads_read_replies, threads_manage_replies, threads_manage_insights` as `scope` values and does not list `threads_delete`, while the delete documentation requires it. Request all three in `scope` as shown below; if the consent screen does not offer `threads_delete`, enable it for the app in the dashboard first.

## 5. Token acquisition and exchange (manual)

The app secret is used only during these manual steps. `threadsdelete` never stores or sends it; routine cleanup uses only the long-lived user token.

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

Steps 8 (renewal) and 9 (revocation) are from documentation only. Still to confirm by hand (see RESEARCH, "Untested and pending"): deletion of replies and quote posts, and the error returned when the deletion quota is reached.
