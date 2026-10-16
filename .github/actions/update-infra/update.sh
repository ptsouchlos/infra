#!/usr/bin/env bash
# Move every infra embed in the working tree to an infra release, and bump infra action refs when
# the major version changes. Writes the PR title/body to GITHUB_OUTPUT; never forces embd.
# Env: TAG (empty = latest non-prerelease), INFRA_REPO (default ptsouchlos/infra),
#      INFRA_URL (git URL for tag lookup), DRY_RUN (print embd commands instead of running them).
set -euo pipefail

repo="${INFRA_REPO:-ptsouchlos/infra}"
url="${INFRA_URL:-https://github.com/$repo}"
out="${GITHUB_OUTPUT:-/dev/null}"

tag="${TAG:-}"
if [ -z "$tag" ]; then
  tag="$(gh release list -R "$repo" --exclude-pre-releases --exclude-drafts --limit 1 \
    --json tagName --jq '.[0].tagName')"
fi
if [[ ! "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "::error::Not a release tag: '$tag'"
  exit 1
fi
major="${tag%%.*}"

# Annotated tags list the tag object; the peeled ^{} line is the commit.
refs="$(git ls-remote "$url" "refs/tags/$tag" "refs/tags/$tag^{}")"
target="$(awk '/\^\{\}$/ {print $1; found=1} END {}' <<<"$refs")"
[ -n "$target" ] || target="$(awk 'NR==1 {print $1}' <<<"$refs")"
if [ -z "$target" ]; then
  echo "::error::Tag $tag not found in $url"
  exit 1
fi

# `remote = "git@github.com:o/r.git"` or "https://github.com/o/r" -> o/r
embeds=()
while IFS= read -r f; do
  remote="$(sed -n 's/^remote *= *"\(.*\)"/\1/p' "$f" | head -n 1)"
  slug="${remote#git@github.com:}"
  slug="${slug#https://github.com/}"
  slug="${slug%.git}"
  [ "$slug" = "$repo" ] && embeds+=("$f")
done < <(find . -name .embd -not -path './.git/*' -not -path '*/node_modules/*' | sort)

changed=()
body=""
for f in "${embeds[@]}"; do
  dir="$(dirname "$f")"
  old="$(sed -n 's/^commit_hash *= *"\(.*\)"/\1/p' "$f" | head -n 1)"
  if [ "$old" = "$target" ]; then
    echo "$dir already at $tag"
    continue
  fi
  if [ -n "${DRY_RUN:-}" ]; then
    echo "+ embd update $dir --rev $tag"
  else
    embd update "$dir" --rev "$tag"
  fi
  changed+=("$dir")
  body+="- \`$dir\`: \`${old:0:7}\` → \`$tag\` (\`${target:0:7}\`)"$'\n'
done

# Rewrite `<repo>/.github/actions/<name>@vN` refs whose major differs from the release.
bumped=""
if [ -d .github/workflows ]; then
  while IFS= read -r wf; do
    if grep -Eq "$repo/\.github/actions/[A-Za-z0-9_-]+@v[0-9]+" "$wf" \
       && grep -E "$repo/\.github/actions/[A-Za-z0-9_-]+@v[0-9]+" "$wf" | grep -vq "@$major\b"; then
      sed -E -i "s#($repo/\.github/actions/[A-Za-z0-9_-]+)@v[0-9]+#\1@$major#g" "$wf"
      bumped+="- \`$wf\`: action refs → \`@$major\`"$'\n'
    fi
  done < <(find .github/workflows -name '*.yml' -o -name '*.yaml' | sort)
fi

if [ ${#changed[@]} -eq 0 ] && [ -z "$bumped" ]; then
  echo "Nothing to update for $tag."
  echo "changed=false" >>"$out"
  exit 0
fi

{
  echo "changed=true"
  echo "tag=$tag"
  echo "title=chore(infra): update infra to $tag"
  echo "body<<EOF_BODY"
  echo "Moves this repo to [$repo $tag](https://github.com/$repo/releases/tag/$tag)."
  echo
  [ -z "$body" ] || printf '%s\n' "$body"
  [ -z "$bumped" ] || printf '%s\n' "$bumped"
  [ -z "$bumped" ] || echo "Major version change: read the release notes for breaking input changes."
  echo "EOF_BODY"
} >>"$out"
