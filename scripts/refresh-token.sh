#!/usr/bin/env bash
# Refresh the Threads long-lived token, verify it, and save it.
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."

REFRESH_URL='https://graph.threads.com/refresh_access_token?grant_type=th_refresh_token'
ME_URL='https://graph.threads.com/v1.0/me?fields=id'

if [ "${GITHUB_ACTIONS:-}" = "true" ]; then mode=actions; else mode=local; fi

work=""
env_tmp=""
cleanup() {
  if [ -n "$env_tmp" ]; then rm -f "$env_tmp"; fi
  if [ -n "$work" ]; then rm -rf "$work"; fi
  return 0
}
trap cleanup EXIT

die_before() {
  printf 'refresh-token: %s Nothing was changed. Fix the cause and run again.\n' "$1" >&2
  exit 2
}
die_after() {
  printf 'refresh-token: %s\n' "$1" >&2
  printf '%s\n' "The token's state may have changed, and any new token was not saved. Running again may not fix it: a refresh needs a token at least 24 hours old, and the old token may no longer work. Check the stored token with a cleanup preview (DRY_RUN=true ./scripts/run.sh locally, or the Threads cleanup workflow with dry_run true); if it fails authentication, replace it by hand (docs/META_SETUP.md sections 5 and 8)." >&2
  exit 1
}

# Step 1: validate inputs.
if [ "$mode" = actions ]; then
  for key in THREADS_ACCESS_TOKEN THREADS_USER_ID GH_TOKEN GH_REPO; do
    eval "val=\${$key:-}"
    if [ -z "$val" ]; then die_before "$key is not set."; fi
  done
  old_token=$THREADS_ACCESS_TOKEN
  user_id=$THREADS_USER_ID
  case $old_token in
    *[[:space:]]*) die_before "THREADS_ACCESS_TOKEN must not contain whitespace." ;;
  esac
else
  [ -f .env ] || die_before ".env not found in the repository root."
  for key in THREADS_ACCESS_TOKEN THREADS_USER_ID; do
    n=$(grep -c "^${key}=" .env || true)
    if [ "$n" -eq 0 ]; then die_before "$key is missing from .env."; fi
    if [ "$n" -gt 1 ]; then die_before ".env has more than one $key line."; fi
    val=$(sed -n "s/^${key}=//p" .env)
    if [ -z "$val" ]; then die_before "$key is empty in .env."; fi
    if [ "$key" = THREADS_ACCESS_TOKEN ]; then
      old_token=$val
    else
      user_id=$val
    fi
  done
  case $old_token in
    *[[:space:]\"\']*) die_before "THREADS_ACCESS_TOKEN must be one unquoted value with no spaces." ;;
  esac
fi
case $user_id in
  '' | *[!0-9]*) die_before "THREADS_USER_ID must be digits only." ;;
esac
command -v curl >/dev/null 2>&1 || die_before "curl is not on PATH."
command -v jq >/dev/null 2>&1 || die_before "jq is not on PATH."
if [ "$mode" = actions ]; then
  command -v gh >/dev/null 2>&1 || die_before "gh is not on PATH."
fi

work=$(mktemp -d)

# Step 2: destination writable.
if [ "$mode" = actions ]; then
  rc=0
  gh secret list >"$work/gh-list.out" 2>&1 || rc=$?
  if [ "$rc" -ne 0 ]; then
    die_before "gh secret list failed (exit $rc). Check that the SECRETS_WRITE_TOKEN secret holds an unexpired fine-grained PAT for this repository with Secrets: read and write."
  fi
else
  [ -w .env ] || die_before ".env is not writable."
  [ -w . ] || die_before "the repository root is not writable."
fi

# error_code FILE KEY: print a digits-only error code, or nothing.
error_code() {
  local v
  v=$(jq -r "(if (.error|type)==\"object\" then .error.$2 else .$2 end) | if type==\"number\" and .==floor and .>=0 then tostring else empty end" "$1" 2>/dev/null || true)
  case $v in
    '' | *[!0-9]*) ;;
    *) printf '%s' "$v" ;;
  esac
}

# Step 3: refresh, once, never retried.
rc=0
status=$(printf '%s' "$old_token" | curl -q --silent --show-error --max-time 30 --get --data-urlencode 'access_token@-' --output "$work/refresh.json" --write-out '%{http_code}' "$REFRESH_URL" 2>"$work/refresh.err") || rc=$?
if [ "$rc" -ne 0 ]; then die_after "Refresh request failed, curl exit $rc."; fi
if [ "$status" != "200" ]; then
  msg="Refresh failed: HTTP $status"
  code=$(error_code "$work/refresh.json" code)
  sub=$(error_code "$work/refresh.json" error_subcode)
  if [ -n "$code" ]; then msg="$msg, error code $code"; fi
  if [ -n "$sub" ]; then msg="$msg subcode $sub"; fi
  die_after "$msg."
fi
jq -e 'type=="object"' "$work/refresh.json" >/dev/null 2>&1 || die_after "Refresh failed: the response was not a JSON object."
jq -e '(.access_token|type)=="string" and (.access_token|length)>0 and (.access_token|test("\\s")|not)' "$work/refresh.json" >/dev/null 2>&1 || die_after "Refresh failed: the response had no usable access token."
new_token=$(jq -r '.access_token' "$work/refresh.json")

# Step 4: mask.
if [ "$mode" = actions ]; then printf '::add-mask::%s\n' "$new_token"; fi

# Step 5: verify the new token belongs to the same account.
rc=0
status=$(printf '%s' "$new_token" | curl -q --silent --show-error --max-time 30 --get --data-urlencode 'access_token@-' --output "$work/me.json" --write-out '%{http_code}' "$ME_URL" 2>"$work/me.err") || rc=$?
if [ "$rc" -ne 0 ]; then die_after "Verify request failed, curl exit $rc."; fi
if [ "$status" != "200" ]; then die_after "Verify failed: HTTP $status."; fi
jq -e 'type=="object"' "$work/me.json" >/dev/null 2>&1 || die_after "Verify failed: the response was not a JSON object."
jq -e --arg id "$user_id" '(.id|type)=="string" and .id == $id' "$work/me.json" >/dev/null 2>&1 || die_after "Verify failed: the new token's account ID differs from THREADS_USER_ID."

# Step 6: save.
if [ "$mode" = actions ]; then
  rc=0
  printf '%s' "$new_token" | gh secret set THREADS_ACCESS_TOKEN >"$work/gh-set.out" 2>&1 || rc=$?
  if [ "$rc" -ne 0 ]; then die_after "gh secret set failed (exit $rc); the PAT may lack Secrets: read and write."; fi
  printf 'Token refreshed and saved to the repository secret\n'
else
  env_tmp=$(mktemp .env.XXXXXX) || die_after "Saving to .env failed."
  NEW_TOKEN="$new_token" awk '/^THREADS_ACCESS_TOKEN=/ { print "THREADS_ACCESS_TOKEN=" ENVIRON["NEW_TOKEN"]; next } { print }' .env >"$env_tmp" || die_after "Saving to .env failed."
  chmod 600 "$env_tmp" || die_after "Saving to .env failed."
  mv -f "$env_tmp" .env || die_after "Saving to .env failed."
  env_tmp=""
  printf 'Token refreshed and saved to .env\n'
fi
