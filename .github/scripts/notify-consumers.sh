#!/usr/bin/env bash
# Dispatch `infra-release` to every repo the App is installed on that has the `uses-infra` topic.
# infra is public, so this log must never name a consumer repo: print counts only.
# Env: TAG, TOPIC (default uses-infra), GH_TOKEN (App installation token).
set -uo pipefail

topic="${TOPIC:-uses-infra}"

# Repo objects normally carry `topics`; if the field is absent, fetch it per repo.
repos="$(gh api --paginate /installation/repositories \
  --jq '.repositories[] | select(.archived | not) | [.full_name, (.topics // null | tojson)] | @tsv' 2>/dev/null)" || {
  echo "::error::Could not list the App's installed repositories"
  exit 1
}

sent=0
failed=0
while IFS=$'\t' read -r name topics; do
  [ -n "$name" ] || continue
  if [ "$topics" = "null" ]; then
    topics="$(gh api "/repos/$name/topics" --jq '.names' 2>/dev/null || echo '[]')"
  fi
  jq -e --arg t "$topic" 'index($t) != null' <<<"$topics" >/dev/null || continue
  if gh api -X POST "/repos/$name/dispatches" -f event_type=infra-release \
       -f "client_payload[tag]=$TAG" >/dev/null 2>&1; then
    sent=$((sent + 1))
  else
    failed=$((failed + 1))
  fi
done <<<"$repos"

echo "dispatched to $sent repos, $failed failed"
[ "$failed" -eq 0 ]
