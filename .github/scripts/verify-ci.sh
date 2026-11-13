#!/usr/bin/env bash
# Verify that the tagged commit is on main and passed all required workflows before releasing.
# Env: GH_TOKEN, GITHUB_REPOSITORY, GITHUB_SHA.
set -euo pipefail

# Ensure the tagged commit is reachable from main.
status="$(gh api "repos/${GITHUB_REPOSITORY}/compare/main...${GITHUB_SHA}" --jq '.status')" || {
  echo "::error::Could not compare ${GITHUB_SHA} against main"
  exit 1
}

if [ "$status" != "identical" ] && [ "$status" != "behind" ]; then
  echo "::error::Commit ${GITHUB_SHA} is not on main (compare status: ${status}). Merge to main before tagging."
  exit 1
fi

for workflow in ci.yml verify-lockfile.yml; do
  runs_json="$(gh api "repos/${GITHUB_REPOSITORY}/actions/workflows/${workflow}/runs?head_sha=${GITHUB_SHA}&per_page=20")" || {
    echo "::error::Could not query workflow runs for ${workflow}"
    exit 1
  }

  passed="$(jq '[.workflow_runs[] | select(.status == "completed" and .conclusion == "success")] | length' <<<"$runs_json")"
  if [ "$passed" -gt 0 ]; then
    echo "Verified ${workflow} passed on ${GITHUB_SHA}"
    continue
  fi

  in_progress="$(jq '[.workflow_runs[] | select(.status != "completed")] | length' <<<"$runs_json")"
  if [ "$in_progress" -gt 0 ]; then
    echo "::error::Workflow ${workflow} is still in progress for ${GITHUB_SHA}. Wait for it to finish before tagging."
  else
    echo "::error::No successful ${workflow} run found for ${GITHUB_SHA}. Ensure CI passed on main before tagging."
  fi
  exit 1
done
