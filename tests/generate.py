#!/usr/bin/env python3
"""Generate a throwaway project that exercises one part of infra.

Usage:
    uv run tests/generate.py --list
    uv run tests/generate.py <kind> <out_dir> [--infra PATH] [--set KEY=VALUE ...] [--force]
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional, Tuple

TESTS_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = TESTS_DIR / "templates"
INFRA_DIR = TESTS_DIR.parent
MANIFEST = "manifest.json"
UNRESOLVED = re.compile(r"@[A-Z][A-Z0-9_]*@")

PRESETS: Dict[str, dict] = {
    "cmake-configure": {
        "name": "configure",
        "cmd": ["cmake", "-S", "@PROJECT_DIR@", "-B", "@BUILD_DIR@", "-DCMAKE_BUILD_TYPE=Release"],
        "extra_args": True,
    },
    "cmake-build": {
        "name": "build",
        "cmd": ["cmake", "--build", "@BUILD_DIR@", "--config", "Release", "--verbose"],
    },
    "cmake-test": {
        "name": "test",
        "cmd": ["ctest", "--test-dir", "@BUILD_DIR@", "-C", "Release", "--output-on-failure"],
    },
}


class UnknownKind(ValueError):
    """Raised when a kind has no manifest."""


class GenerateError(RuntimeError):
    """Raised when a project cannot be generated or a step cannot be expanded."""


@dataclass(frozen=True)
class Step:
    name: str
    cmd: Tuple[str, ...]
    cwd: str = "@PROJECT_DIR@"
    expect: str = "pass"  # "pass" or "fail"
    expect_output: Optional[str] = None
    extra_args: bool = False


@dataclass(frozen=True)
class Kind:
    name: str
    description: str
    includes: Tuple[str, ...]
    vars: Dict[str, str]
    skip_on: Tuple[str, ...]
    steps: Tuple[Step, ...]


@dataclass(frozen=True)
class Project:
    kind: Kind
    dir: Path
    tokens: Dict[str, str]

    def expand(self, text: str) -> str:
        for key, value in self.tokens.items():
            text = text.replace("@" + key + "@", value)
        return text

    def _expand_checked(self, text: str) -> str:
        expanded = self.expand(text)
        leftover = UNRESOLVED.search(expanded)
        if leftover:
            raise GenerateError(
                "unresolved token %s in step text %r" % (leftover.group(0), text)
            )
        return expanded

    def steps(self) -> Tuple[Step, ...]:
        return tuple(
            replace(
                step,
                cmd=tuple(self._expand_checked(part) for part in step.cmd),
                cwd=self._expand_checked(step.cwd),
                expect_output=(
                    None
                    if step.expect_output is None
                    else self._expand_checked(step.expect_output)
                ),
            )
            for step in self.kind.steps
        )


def current_os() -> str:
    return platform.system().lower()


def _parse_step(spec) -> Step:
    if isinstance(spec, str):
        spec = {"preset": spec}
    merged: dict = dict(PRESETS[spec["preset"]]) if "preset" in spec else {}
    merged.update({key: value for key, value in spec.items() if key != "preset"})
    return Step(
        name=merged["name"],
        cmd=tuple(merged["cmd"]),
        cwd=merged.get("cwd", "@PROJECT_DIR@"),
        expect=merged.get("expect", "pass"),
        expect_output=merged.get("expect_output"),
        extra_args=bool(merged.get("extra_args", False)),
    )


def _read_manifest(templates_dir: Path, name: str) -> Optional[dict]:
    path = templates_dir / name / MANIFEST
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_kind(name: str, templates_dir: Path = TEMPLATES_DIR) -> Kind:
    raw = None if name.startswith("_") else _read_manifest(templates_dir, name)
    if raw is None:
        raise UnknownKind(name)
    return Kind(
        name=name,
        description=raw["description"],
        includes=tuple(raw.get("includes", ())),
        vars=dict(raw.get("vars", {})),
        skip_on=tuple(raw.get("skip_on", ())),
        steps=tuple(_parse_step(spec) for spec in raw["steps"]),
    )


def list_kinds(templates_dir: Path = TEMPLATES_DIR) -> List[str]:
    return sorted(
        path.name
        for path in templates_dir.iterdir()
        if path.is_dir()
        and not path.name.startswith("_")
        and (path / MANIFEST).is_file()
    )


def _chain(templates_dir: Path, name: str) -> List[str]:
    """Return template names in copy order: includes first, the kind last."""
    raw = _read_manifest(templates_dir, name) or {}
    ordered: List[str] = []
    for included in raw.get("includes", ()):
        for item in _chain(templates_dir, included):
            if item not in ordered:
                ordered.append(item)
    ordered.append(name)
    return ordered


def _copy_template(source: Path, destination: Path, project: Project) -> None:
    for path in sorted(source.rglob("*")):
        if path.is_dir() or path.name == MANIFEST:
            continue
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        text = project.expand(path.read_text(encoding="utf-8"))
        leftover = UNRESOLVED.search(text)
        if leftover:
            raise GenerateError("unresolved token %s in %s" % (leftover.group(0), path))
        target.write_bytes(text.encode("utf-8"))


def generate(
    kind_name: str,
    out_dir,
    infra_dir: Path = INFRA_DIR,
    overrides: Optional[Dict[str, str]] = None,
    force: bool = False,
    templates_dir: Path = TEMPLATES_DIR,
) -> Project:
    kind = load_kind(kind_name, templates_dir)
    overrides = overrides or {}
    unknown = sorted(set(overrides) - set(kind.vars))
    if unknown:
        raise GenerateError(
            "unknown variable(s) %s for kind %s (known: %s)"
            % (", ".join(unknown), kind_name, ", ".join(sorted(kind.vars)) or "none")
        )
    out = Path(out_dir).resolve()
    if out.exists() and any(out.iterdir()) and not force:
        raise GenerateError("%s is not empty (use --force)" % out)
    out.mkdir(parents=True, exist_ok=True)
    tokens = {
        "INFRA_DIR": Path(infra_dir).resolve().as_posix(),
        "PROJECT_DIR": out.as_posix(),
        "BUILD_DIR": (out / "build").as_posix(),
        "PREFIX": (out / "prefix").as_posix(),
        "PYTHON": Path(sys.executable).as_posix(),
        "PROJECT_NAME": "infra_" + kind_name.replace("-", "_"),
    }
    tokens.update(kind.vars)
    tokens.update(overrides)
    project = Project(kind=kind, dir=out, tokens=tokens)
    for name in _chain(templates_dir, kind_name):
        _copy_template(templates_dir / name, out, project)
    return project


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("kind", nargs="?")
    parser.add_argument("out_dir", nargs="?")
    parser.add_argument("--list", action="store_true", help="list available kinds")
    parser.add_argument("--infra", type=Path, default=INFRA_DIR, help="infra checkout to test")
    parser.add_argument("--set", dest="overrides", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--force", action="store_true", help="allow a non-empty out_dir")
    args = parser.parse_args(argv)
    if args.list:
        for name in list_kinds():
            print("%-20s %s" % (name, load_kind(name).description))
        return 0
    if not args.kind or not args.out_dir:
        parser.error("kind and out_dir are required")
    try:
        overrides = dict(item.split("=", 1) for item in args.overrides)
        project = generate(
            args.kind, args.out_dir, infra_dir=args.infra, overrides=overrides, force=args.force
        )
    except (UnknownKind, GenerateError, ValueError) as error:
        print("error: %s" % error, file=sys.stderr)
        return 2
    print(project.dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
