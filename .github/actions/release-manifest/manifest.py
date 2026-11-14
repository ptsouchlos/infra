#!/usr/bin/env python3
"""Gather release assets into one manifest JSON.

Inputs arrive as environment variables so the action and the unit tests share one path:
  ASSETS_DIR  directory searched recursively for assets (download-artifact leaves one
              subdirectory per artifact)
  NAME        app name; every asset is named <NAME>-<VERSION>-<os>-<arch>[-<variant>].<ext>
  VERSION     release version without a leading v
  COMMIT      commit sha the release was built from (default $GITHUB_SHA)
  OUT_DIR     where <NAME>-<VERSION>-manifest.json is written (default dist)
  SIGNED      "true" marks every asset signed in the manifest (default "false")
  CREATED     ISO-8601 UTC timestamp override, for reproducible tests (default: now)

Every asset needs a sibling <asset>.sha256 in `<hash>  <file>` format, and the hash must match
the file. A file that does not follow the naming scheme is an error, not skipped, so a
packaging mistake surfaces here rather than as a confusing release.
Writes manifest= to $GITHUB_OUTPUT.
"""

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# extension -> (format, kind); the longest suffix wins, matched case-insensitively
FORMATS = {
    ".tar.gz": ("tar.gz", "archive"),
    ".zip": ("zip", "archive"),
    ".msi": ("msi", "installer"),
    ".dmg": ("dmg", "installer"),
    ".deb": ("deb", "installer"),
    ".rpm": ("rpm", "installer"),
    ".appimage": ("appimage", "installer"),
    ".flatpak": ("flatpak", "installer"),
}
OSES = {"linux", "macos", "windows"}
ARCHES = {"x86_64", "aarch64"}


def fail(message):
    print(f"::error::{message}")
    sys.exit(1)


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def describe(path, prefix):
    """Split an asset's file name into its manifest fields."""
    name = path.name
    lower = name.lower()
    ext = max((e for e in FORMATS if lower.endswith(e)), key=len, default=None)
    if ext is None:
        fail(f"'{name}' has no recognized extension ({', '.join(sorted(FORMATS))})")
    if not name.startswith(prefix):
        fail(f"'{name}' does not start with '{prefix}'")
    parts = name[len(prefix):-len(ext)].split("-", 2)
    if len(parts) < 2 or not parts[1] or parts[0] not in OSES or parts[1] not in ARCHES:
        fail(f"'{name}' should be {prefix}<os>-<arch>[-<variant>]{ext} "
             f"with os in {sorted(OSES)} and arch in {sorted(ARCHES)}")
    fmt, kind = FORMATS[ext]
    return {"os": parts[0], "arch": parts[1], "format": fmt, "kind": kind}


def main():
    env = os.environ
    for key in ("ASSETS_DIR", "NAME", "VERSION"):
        if not env.get(key):
            fail(f"{key} is required")
    assets_dir = Path(env["ASSETS_DIR"])
    name, version = env["NAME"], env["VERSION"]
    commit = env.get("COMMIT") or env.get("GITHUB_SHA", "")
    out_dir = Path(env.get("OUT_DIR") or "dist")
    signed = env.get("SIGNED", "false") == "true"
    signed_oses = {s.strip() for s in env.get("SIGNED_OSES", "").split(",") if s.strip()}
    created = env.get("CREATED") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not assets_dir.is_dir():
        fail(f"assets-dir '{assets_dir}' does not exist")
    if not commit:
        fail("COMMIT is required when GITHUB_SHA is not set")

    prefix = f"{name}-{version}-"
    manifest_name = f"{prefix}manifest.json"
    sidecars = (".sha256", ".asc", ".sig")
    files = sorted(p for p in assets_dir.rglob("*")
                   if p.is_file() and not p.name.endswith(sidecars) and p.name != manifest_name)
    if not files:
        fail(f"no assets found under '{assets_dir}'")

    seen = {}
    assets = []
    for path in files:
        if path.name in seen:
            fail(f"'{path.name}' appears twice: {seen[path.name]} and {path}")
        seen[path.name] = path
        fields = describe(path, prefix)
        checksum = path.with_name(path.name + ".sha256")
        if not checksum.is_file():
            fail(f"'{path.name}' has no {path.name}.sha256 beside it")
        recorded = checksum.read_text().split()
        actual = sha256_of(path)
        if not recorded or recorded[0].lower() != actual:
            fail(f"'{path.name}' does not match its .sha256 file")
        asset_signed = (
            signed
            or fields["os"] in signed_oses
            or path.with_name(path.name + ".asc").is_file()
            or path.with_name(path.name + ".sig").is_file()
        )
        assets.append({"file": path.name, **fields, "size": path.stat().st_size,
                       "sha256": actual, "signed": asset_signed})

    assets.sort(key=lambda a: a["file"])
    manifest = {
        "schema": 1,
        "name": name,
        "version": version,
        "prerelease": "-" in version,
        "commit": commit,
        "created": created,
        "assets": assets,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / manifest_name
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {target} with {len(assets)} assets")

    with open(env.get("GITHUB_OUTPUT") or os.devnull, "a", encoding="utf-8") as out:
        out.write(f"manifest={target}\n")


if __name__ == "__main__":
    main()
