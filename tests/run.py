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
    --timeout SECONDS  kill a step that runs longer than this (default 1800)
    --verbose          stream step output as it is produced

Exit codes: 0 pass or skipped, 1 a step failed, 2 usage error, 3 tool missing.
"""
from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate  # noqa: E402


def run_step(
    project: generate.Project,
    step: generate.Step,
    extra_args: Sequence[str] = (),
    verbose: bool = False,
    timeout: Optional[float] = None,
) -> bool:
    argv = [project.expand(part) for part in step.cmd]
    if step.extra_args:
        argv.extend(extra_args)
    cwd = project.expand(step.cwd)
    try:
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except OSError as error:
        print("[FAIL] %s: cannot run %s: %s" % (step.name, argv[0], error))
        return False
    timed_out = False

    def kill() -> None:
        nonlocal timed_out
        timed_out = True
        process.kill()

    timer = threading.Timer(timeout, kill) if timeout else None
    if timer:
        timer.start()
    chunks: List[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        chunks.append(line)
        if verbose:
            print(line, end="", flush=True)
    returncode = process.wait()
    if timer:
        timer.cancel()
    output = "".join(chunks)
    if timed_out:
        print("[FAIL] %s: timed out after %s seconds" % (step.name, timeout))
        print(output)
        return False
    reason = None
    if (returncode == 0) != (step.expect == "pass"):
        reason = "exit code %d, expected %s" % (returncode, step.expect)
    elif step.expect_output is not None and project.expand(step.expect_output) not in output:
        reason = "output did not contain %r" % project.expand(step.expect_output)
    if reason is None:
        print("[ ok ] %s" % step.name)
        return True
    print("[FAIL] %s: %s" % (step.name, reason))
    if not verbose:
        print(output)
    return False


def run_project(
    project: generate.Project,
    extra_args: Sequence[str] = (),
    verbose: bool = False,
    timeout: Optional[float] = None,
) -> bool:
    for step in project.steps():
        if not run_step(project, step, extra_args, verbose, timeout):
            return False
    return True


def _make_writable_and_retry(function, path, _error) -> None:
    for entry in (os.path.dirname(path), path):
        try:
            os.chmod(entry, stat.S_IRWXU)
        except OSError:
            pass
    function(path)


def force_rmtree(path) -> None:
    """Remove a tree even when it holds read-only entries (git objects on Windows)."""
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_make_writable_and_retry)
    else:
        shutil.rmtree(path, onerror=_make_writable_and_retry)


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
    except (generate.GenerateError, ValueError) as error:
        print("error: %s" % error, file=sys.stderr)
        return 2
    system = generate.current_os()
    if system in kind.skip_on:
        print("SKIP %s: not supported on %s" % (kind.name, system))
        return 0
    explicit = args.work_dir is not None
    work = Path(args.work_dir) if explicit else Path(tempfile.mkdtemp(prefix="infra-%s-" % kind.name))
    inspect = explicit or args.keep  # keep the project for a person to look at
    try:
        try:
            project = generate.generate(kind.name, work, overrides=overrides)
            missing = missing_tools(project)
        except generate.GenerateError as error:
            print("error: %s" % error, file=sys.stderr)
            return 2
        if missing:
            print("error: required tool(s) not found: %s" % ", ".join(missing), file=sys.stderr)
            return 3
        passed = run_project(project, args.cmake_arg, args.verbose, args.timeout)
        print("%s %s (%s)" % ("PASS" if passed else "FAIL", kind.name, work))
        inspect = inspect or not passed
        return 0 if passed else 1
    finally:
        if not inspect:
            try:
                force_rmtree(work)
            except OSError as error:
                print("warning: could not remove %s: %s" % (work, error), file=sys.stderr)


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
    parser.add_argument("--timeout", type=float, default=1800.0, metavar="SECONDS",
                        help="per-step time limit (default 1800)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    if bool(args.kind) == args.all:
        parser.error("give exactly one of <kind> or --all")
    if args.all and args.work_dir:
        parser.error("--work-dir cannot be combined with --all")
    if args.all and args.overrides:
        parser.error("--set cannot be combined with --all (it would apply to no kind)")
    try:
        overrides = generate.parse_overrides(args.overrides)
    except generate.GenerateError as error:
        parser.error(str(error))
    kinds = generate.list_kinds() if args.all else [args.kind]
    worst = 0
    for name in kinds:
        worst = max(worst, _run_kind(name, args, overrides))
    return worst


if __name__ == "__main__":
    sys.exit(main())
