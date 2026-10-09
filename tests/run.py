#!/usr/bin/env python3
"""Generate a throwaway project and run its steps.

Usage:
    uv run tests/run.py <kind> [options]
    uv run tests/run.py --all [options]

Options:
    --work-dir DIR     generate into DIR (must be empty); it is kept afterwards
    --keep             keep the temporary directory
    --set KEY=VALUE    override a kind variable (e.g. TOOLCHAIN=llvm)
    --cmake-arg=ARG    extra argument for configure steps (repeatable); use the
                       "=" form, e.g. --cmake-arg=-DCMAKE_CXX_COMPILER=clang++
    --verbose          print output of passing steps too

Exit codes: 0 pass or skipped, 1 a step failed, 2 usage error, 3 tool missing.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate  # noqa: E402


def run_step(
    project: generate.Project,
    step: generate.Step,
    extra_args: Sequence[str] = (),
    verbose: bool = False,
) -> bool:
    argv = [project.expand(part) for part in step.cmd]
    if step.extra_args:
        argv.extend(extra_args)
    cwd = project.expand(step.cwd)
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (FileNotFoundError, NotADirectoryError) as error:
        print("[FAIL] %s: cannot run %s: %s" % (step.name, argv[0], error))
        return False
    output = result.stdout + result.stderr
    reason = None
    if (result.returncode == 0) != (step.expect == "pass"):
        reason = "exit code %d, expected %s" % (result.returncode, step.expect)
    elif step.expect_output is not None and project.expand(step.expect_output) not in output:
        reason = "output did not contain %r" % project.expand(step.expect_output)
    if reason is None:
        print("[ ok ] %s" % step.name)
        if verbose:
            print(output)
        return True
    print("[FAIL] %s: %s" % (step.name, reason))
    print(output)
    return False


def run_project(
    project: generate.Project,
    extra_args: Sequence[str] = (),
    verbose: bool = False,
) -> bool:
    for step in project.steps():
        if not run_step(project, step, extra_args, verbose):
            return False
    return True


def missing_tools(project: generate.Project) -> List[str]:
    missing = set()
    for step in project.steps():
        tool = step.cmd[0]
        if shutil.which(tool) is None and not Path(tool).exists():
            missing.add(tool)
    return sorted(missing)


def _run_kind(kind_name: str, args: argparse.Namespace, overrides: Dict[str, str]) -> int:
    try:
        kind = generate.load_kind(kind_name)
    except generate.UnknownKind:
        print("error: unknown kind %r (try --all or generate.py --list)" % kind_name, file=sys.stderr)
        return 2
    system = generate.current_os()
    if system in kind.skip_on:
        print("SKIP %s: not supported on %s" % (kind.name, system))
        return 0
    explicit = args.work_dir is not None
    work = Path(args.work_dir) if explicit else Path(tempfile.mkdtemp(prefix="infra-%s-" % kind.name))
    try:
        project = generate.generate(kind.name, work, overrides=overrides)
    except generate.GenerateError as error:
        print("error: %s" % error, file=sys.stderr)
        return 2
    missing = missing_tools(project)
    if missing:
        print("error: required tool(s) not found: %s" % ", ".join(missing), file=sys.stderr)
        return 3
    passed = run_project(project, args.cmake_arg, args.verbose)
    print("%s %s (%s)" % ("PASS" if passed else "FAIL", kind.name, work))
    if passed and not args.keep and not explicit:
        shutil.rmtree(work, ignore_errors=True)
    return 0 if passed else 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("kind", nargs="?")
    parser.add_argument("--all", action="store_true", help="run every kind")
    parser.add_argument("--work-dir", help="generate into this empty directory and keep it")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--set", dest="overrides", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--cmake-arg", action="append", default=[], metavar="ARG")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    if bool(args.kind) == args.all:
        parser.error("give exactly one of <kind> or --all")
    if args.all and args.work_dir:
        parser.error("--work-dir cannot be combined with --all")
    try:
        overrides = dict(item.split("=", 1) for item in args.overrides)
    except ValueError:
        parser.error("--set expects KEY=VALUE")
    kinds = generate.list_kinds() if args.all else [args.kind]
    worst = 0
    for name in kinds:
        worst = max(worst, _run_kind(name, args, overrides if not args.all else {}))
    return worst


if __name__ == "__main__":
    sys.exit(main())
