#!/usr/bin/env bash
set -euo pipefail

manifest_path="${MANIFEST_PATH:-Cargo.toml}"
packages="${PACKAGES:-}"
tag="${TAG:-}"
require_tag="${REQUIRE_TAG:-false}"

if [ ! -f "$manifest_path" ]; then
    echo "::error::manifest-path '$manifest_path' does not exist"
    exit 1
fi

case "$require_tag" in
    true | false) ;;
    *)
        echo "::error::require-tag must be 'true' or 'false' (got '$require_tag')"
        exit 1
        ;;
esac

if [ "$require_tag" = "true" ] && [ -z "$tag" ]; then
    echo "::error::tag is required when require-tag is true"
    exit 1
fi

if command -v python3 >/dev/null 2>&1; then
    py=python3
elif command -v python >/dev/null 2>&1; then
    py=python
else
    echo "::error::python3 is required"
    exit 1
fi

metadata="$(cargo metadata --manifest-path "$manifest_path" --no-deps --format-version 1)"

version="$(
    printf '%s' "$metadata" | PACKAGES="$packages" "$py" -c '
import json, os, sys

data = json.load(sys.stdin)
pkgs = data.get("packages", [])
wanted = os.environ.get("PACKAGES", "").split()
if wanted:
    by_name = {p["name"]: p for p in pkgs}
    missing = [n for n in wanted if n not in by_name]
    if missing:
        print("::error::packages not found in workspace: " + ", ".join(missing), file=sys.stderr)
        sys.exit(1)
    pkgs = [by_name[n] for n in wanted]

if not pkgs:
    print("::error::no workspace packages found", file=sys.stderr)
    sys.exit(1)

versions = sorted({p["version"] for p in pkgs})
if len(versions) != 1:
    detail = " ".join(p["name"] + "=" + p["version"] for p in pkgs)
    print(f"::error::crate versions disagree: {detail}", file=sys.stderr)
    sys.exit(1)

print(versions[0])
'
)"

if [ -n "$tag" ] && [ "$tag" != "v$version" ]; then
    echo "::error::tag '$tag' does not match Cargo.toml version '$version' (expected 'v$version')"
    exit 1
fi

echo "Verified version $version${tag:+ (tag $tag)}"

if [ -n "${GITHUB_OUTPUT:-}" ]; then
    {
        echo "version=$version"
        echo "tag=$tag"
    } >>"$GITHUB_OUTPUT"
fi
