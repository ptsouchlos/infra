#!/usr/bin/env bash
# Create a draft GitHub release, upload every file under ASSETS_DIR plus MANIFEST, and undraft
# the release only after all uploads finish so a partial release is never visible.
# Inputs arrive as environment variables so the action and the unit tests share one path:
#   ASSETS_DIR MANIFEST TAG TITLE NOTES GENERATE_NOTES PRERELEASE DRAFT GH_TOKEN
# Runs under bash 3.2+: no mapfile, no associative arrays, no empty-array expansion under set -u.
set -euo pipefail

: "${ASSETS_DIR:?ASSETS_DIR is required}"
: "${MANIFEST:?MANIFEST is required}"
: "${TAG:?TAG is required}"
: "${TITLE:=}"
: "${NOTES:=}"
: "${GENERATE_NOTES:=true}"
: "${PRERELEASE:=auto}"
: "${DRAFT:=false}"

case "$PRERELEASE" in
    auto)
        case "$TAG" in
            *-*) prerelease=true ;;
            *) prerelease=false ;;
        esac
        ;;
    true | false) prerelease="$PRERELEASE" ;;
    *)
        echo "::error::prerelease must be auto, true or false (got '$PRERELEASE')"
        exit 1
        ;;
esac

for pair in "generate-notes:$GENERATE_NOTES" "draft:$DRAFT"; do
    case "${pair#*:}" in
        true | false) ;;
        *)
            echo "::error::${pair%%:*} must be true or false (got '${pair#*:}')"
            exit 1
            ;;
    esac
done

if [ ! -d "$ASSETS_DIR" ]; then
    echo "::error::assets-dir '$ASSETS_DIR' does not exist"
    exit 1
fi
if [ ! -f "$MANIFEST" ]; then
    echo "::error::manifest '$MANIFEST' does not exist"
    exit 1
fi

assets_dir="$(cd "$ASSETS_DIR" && pwd)"
manifest="$(cd "$(dirname "$MANIFEST")" && pwd)/$(basename "$MANIFEST")"
manifest_name="$(basename "$manifest")"

files=()
seen_names=""
while IFS= read -r f; do
    [ "$f" = "$manifest" ] && continue
    base="$(basename "$f")"
    if [ "$base" = "$manifest_name" ]; then
        echo "::error::'$base' in assets-dir collides with manifest '$MANIFEST'"
        exit 1
    fi
    case $'\n'"$seen_names"$'\n' in
        *$'\n'"$base"$'\n'*)
            echo "::error::duplicate file name '$base' under '$ASSETS_DIR'"
            exit 1
            ;;
    esac
    seen_names="${seen_names:+$seen_names$'\n'}$base"
    files+=("$f")
done < <(find "$assets_dir" -type f | LC_ALL=C sort)

if [ "${#files[@]}" -eq 0 ]; then
    echo "::error::no assets found under '$ASSETS_DIR'"
    exit 1
fi
files+=("$manifest")

echo "::group::draft release"
if gh release view "$TAG" >/dev/null 2>&1; then
    echo "Release $TAG already exists; uploading to it."
else
    create_args=("$TAG" --draft --verify-tag --title "${TITLE:-$TAG}")
    if [ "$prerelease" = true ]; then
        create_args+=(--prerelease)
    fi
    if [ "$GENERATE_NOTES" = true ]; then
        create_args+=(--generate-notes)
    fi
    if [ -n "$NOTES" ]; then
        create_args+=(--notes "$NOTES")
    elif [ "$GENERATE_NOTES" = false ]; then
        create_args+=(--notes "")
    fi
    gh release create "${create_args[@]}"
fi
echo "::endgroup::"

echo "::group::upload assets"
gh release upload "$TAG" --clobber "${files[@]}"
echo "::endgroup::"

if [ "$DRAFT" = false ]; then
    echo "::group::publish release"
    gh release edit "$TAG" --draft=false
    echo "::endgroup::"
fi
