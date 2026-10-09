from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import generate
import run


_KEEP_ALIVE: list = []


def project_with(*steps: generate.Step) -> generate.Project:
    tmp = tempfile.TemporaryDirectory()
    kind = generate.Kind(
        name="t",
        description="t",
        includes=(),
        vars={},
        skip_on=(),
        steps=tuple(steps),
    )
    project = generate.Project(
        kind=kind,
        dir=Path(tmp.name),
        tokens={"PROJECT_DIR": Path(tmp.name).as_posix(), "MSG": "hello"},
    )
    _KEEP_ALIVE.append(tmp)  # the directory lives until the process exits
    return project


def py(code: str, **kwargs) -> generate.Step:
    return generate.Step(name=kwargs.pop("name", "step"), cmd=(sys.executable, "-c", code), **kwargs)


class RunStepTests(unittest.TestCase):
    def test_passing_step(self) -> None:
        project = project_with(py("pass"))
        self.assertTrue(run.run_step(project, project.kind.steps[0]))

    def test_failing_step_fails(self) -> None:
        project = project_with(py("raise SystemExit(3)"))
        self.assertFalse(run.run_step(project, project.kind.steps[0]))

    def test_expected_failure_passes(self) -> None:
        project = project_with(py("raise SystemExit(1)", expect="fail"))
        self.assertTrue(run.run_step(project, project.kind.steps[0]))

    def test_unexpected_success_of_expected_failure_is_a_failure(self) -> None:
        project = project_with(py("pass", expect="fail"))
        self.assertFalse(run.run_step(project, project.kind.steps[0]))

    def test_expect_output_is_required(self) -> None:
        good = project_with(py("print('needle here')", expect_output="needle"))
        bad = project_with(py("print('nothing')", expect_output="needle"))
        self.assertTrue(run.run_step(good, good.kind.steps[0]))
        self.assertFalse(run.run_step(bad, bad.kind.steps[0]))

    def test_expect_output_checks_stderr_too(self) -> None:
        project = project_with(
            py("import sys; sys.stderr.write('needle'); raise SystemExit(1)",
               expect="fail", expect_output="needle")
        )
        self.assertTrue(run.run_step(project, project.kind.steps[0]))

    def test_missing_executable_fails_even_when_failure_is_expected(self) -> None:
        step = generate.Step(
            name="missing", cmd=("definitely-not-a-real-binary-xyz",), expect="fail"
        )
        project = project_with(step)
        self.assertFalse(run.run_step(project, step))

    def test_extra_args_only_appended_when_flagged(self) -> None:
        code = "import sys; sys.exit(0 if sys.argv[1:] == ['--flag'] else 1)"
        with_flag = project_with(py(code, extra_args=True))
        without = project_with(py(code))
        self.assertTrue(run.run_step(with_flag, with_flag.kind.steps[0], extra_args=["--flag"]))
        self.assertFalse(run.run_step(without, without.kind.steps[0], extra_args=["--flag"]))

    def test_tokens_expand_in_cmd_and_cwd(self) -> None:
        code = "import os, sys; sys.exit(0 if sys.argv[1] == 'hello' else 1)"
        step = generate.Step(
            name="tok", cmd=(sys.executable, "-c", code, "@MSG@"), cwd="@PROJECT_DIR@"
        )
        project = project_with(step)
        self.assertTrue(run.run_step(project, step))


class RunProjectTests(unittest.TestCase):
    def test_stops_at_first_failure(self) -> None:
        marker = tempfile.NamedTemporaryFile(delete=False)
        marker.close()
        path = Path(marker.name)
        self.addCleanup(path.unlink)
        first = py("raise SystemExit(1)", name="first")
        second = py("open(%r, 'w').write('ran')" % path.as_posix(), name="second")
        project = project_with(first, second)
        self.assertFalse(run.run_project(project))
        self.assertEqual(path.read_text(), "")

    def test_all_pass(self) -> None:
        project = project_with(py("pass", name="a"), py("pass", name="b"))
        self.assertTrue(run.run_project(project))


class MissingToolsTests(unittest.TestCase):
    def test_reports_only_missing_commands(self) -> None:
        project = project_with(
            py("pass"),
            generate.Step(name="x", cmd=("definitely-not-a-real-binary-xyz",)),
        )
        self.assertEqual(run.missing_tools(project), ["definitely-not-a-real-binary-xyz"])


class MainTests(unittest.TestCase):
    def test_unknown_kind_exits_2(self) -> None:
        self.assertEqual(run.main(["nope"]), 2)

    def test_skipped_kind_exits_0(self) -> None:
        original = generate.current_os
        generate.current_os = lambda: "windows"  # type: ignore[assignment]
        try:
            skipped = [
                name for name in generate.list_kinds()
                if "windows" in generate.load_kind(name).skip_on
            ]
            for name in skipped:
                self.assertEqual(run.main([name]), 0)
        finally:
            generate.current_os = original  # type: ignore[assignment]


if __name__ == "__main__":
    unittest.main()
