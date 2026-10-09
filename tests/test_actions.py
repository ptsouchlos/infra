"""Tests for the composite actions in .github/actions/."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACTIONS = ROOT / ".github" / "actions"


def action_files():
    return sorted(ACTIONS.glob("*/action.yml"))


def run_script(path, env):
    full = {**os.environ, **env}
    return subprocess.run(
        ["bash", str(path)], env=full, capture_output=True, text=True
    )


class ActionStructure(unittest.TestCase):
    def test_every_action_is_composite_and_documented(self):
        for f in action_files():
            text = f.read_text(encoding="utf-8")
            with self.subTest(action=f.parent.name):
                self.assertRegex(text, r"(?m)^name:\s*\S")
                self.assertRegex(text, r"(?m)^description:\s*\S")
                self.assertRegex(text, r"(?m)^\s+using:\s*composite\s*$")

    def test_every_run_step_names_a_shell(self):
        for f in action_files():
            text = f.read_text(encoding="utf-8")
            runs = len(re.findall(r"(?m)^\s*(?:- )?run:", text))
            shells = len(re.findall(r"(?m)^\s*(?:- )?shell:", text))
            with self.subTest(action=f.parent.name):
                self.assertEqual(runs, shells)

    def test_no_windows_only_shells(self):
        for f in action_files():
            text = f.read_text(encoding="utf-8")
            with self.subTest(action=f.parent.name):
                self.assertNotRegex(text, r"shell:\s*(pwsh|powershell|cmd)\b")

    def test_third_party_actions_are_version_pinned(self):
        for f in action_files():
            text = f.read_text(encoding="utf-8")
            for ref in re.findall(r"(?m)^\s*-?\s*uses:\s*(\S+)", text):
                with self.subTest(action=f.parent.name, uses=ref):
                    self.assertRegex(ref, r"@v\d")


class SetupCppScript(unittest.TestCase):
    script = ACTIONS / "setup-cpp" / "install.sh"

    def run_install(self, **env):
        with tempfile.TemporaryDirectory() as d:
            gh_env = Path(d) / "env"
            gh_env.touch()
            base = {"DRY_RUN": "1", "GITHUB_ENV": str(gh_env), "VERSION": "",
                    "CMAKE_VERSION": ""}
            result = run_script(self.script, {**base, **env})
            return result, gh_env.read_text(encoding="utf-8")

    def test_linux_gcc_with_version_installs_and_exports(self):
        result, gh_env = self.run_install(RUNNER_OS="Linux", COMPILER="gcc",
                                          VERSION="13")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("apt-get install -y gcc-13 g++-13", result.stdout)
        self.assertIn("CC=gcc-13", gh_env)
        self.assertIn("CXX=g++-13", gh_env)

    def test_linux_clang_without_version_uses_unversioned_names(self):
        result, gh_env = self.run_install(RUNNER_OS="Linux", COMPILER="clang")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("apt-get install -y clang", result.stdout)
        self.assertIn("CC=clang\n", gh_env)
        self.assertIn("CXX=clang++\n", gh_env)

    def test_macos_appleclang_exports_clang(self):
        result, gh_env = self.run_install(RUNNER_OS="macOS",
                                          COMPILER="appleclang")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("apt-get", result.stdout)
        self.assertIn("CC=clang\n", gh_env)

    def test_windows_msvc_installs_nothing(self):
        result, gh_env = self.run_install(RUNNER_OS="Windows", COMPILER="msvc")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("apt-get", result.stdout)
        self.assertEqual(gh_env, "")

    def test_unsupported_pair_fails_before_installing(self):
        result, gh_env = self.run_install(RUNNER_OS="macOS", COMPILER="gcc")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("::error::", result.stdout + result.stderr)
        self.assertNotIn("apt-get", result.stdout)
        self.assertEqual(gh_env, "")

    def test_cmake_version_pins_pip_install(self):
        result, _ = self.run_install(RUNNER_OS="Linux", COMPILER="gcc",
                                     CMAKE_VERSION="3.31.6")
        self.assertIn("cmake==3.31.6", result.stdout)

    def test_no_cmake_version_leaves_cmake_alone(self):
        result, _ = self.run_install(RUNNER_OS="Linux", COMPILER="gcc")
        self.assertNotIn("cmake==", result.stdout)


HAVE_TOOLS = bool(shutil.which("cmake") and shutil.which("ninja")
                  and (shutil.which("clang++") or shutil.which("g++")))


@unittest.skipUnless(HAVE_TOOLS, "cmake, ninja and a C++ compiler are required")
class CmakeBuildScript(unittest.TestCase):
    script = ACTIONS / "cmake-build" / "run.sh"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def generate(self, kind, name="my project"):
        out = self.tmp / name
        subprocess.run(
            [sys.executable, str(ROOT / "tests" / "generate.py"), kind, str(out),
             "--infra", str(ROOT)],
            check=True, capture_output=True, text=True)
        return out

    def run_build(self, src, **env):
        base = {"SOURCE_DIR": str(src), "BUILD_DIR": str(src / "build dir")}
        return run_script(self.script, {**base, **env})

    def test_builds_a_project_in_a_directory_with_spaces(self):
        src = self.generate("cpp-basic")
        result = self.run_build(src)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for group in ("configure", "build", "test"):
            self.assertIn(f"::group::{group}", result.stdout)
        self.assertNotIn("::group::install", result.stdout)

    def test_configure_args_are_forwarded(self):
        src = self.generate("cpp-basic")
        result = self.run_build(src, CONFIGURE_ARGS="-DPT_PROBE=hello -DPT_OTHER=1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        cache = (src / "build dir" / "CMakeCache.txt").read_text(encoding="utf-8")
        self.assertIn("PT_PROBE:UNINITIALIZED=hello", cache)
        self.assertIn("PT_OTHER:UNINITIALIZED=1", cache)

    def test_run_tests_false_skips_ctest(self):
        src = self.generate("cpp-basic")
        result = self.run_build(src, RUN_TESTS="false")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("::group::test", result.stdout)

    def test_install_prefix_installs(self):
        src = self.generate("cpp-install")
        prefix = self.tmp / "prefix dir"
        result = self.run_build(src, INSTALL_PREFIX=str(prefix))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("::group::install", result.stdout)
        self.assertTrue(any(prefix.rglob("*-config.cmake")))

    def test_failing_configure_fails_the_script(self):
        result = self.run_build(self.tmp / "does-not-exist")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("::group::configure", result.stdout)

    def test_failing_build_fails_the_script(self):
        src = self.generate("cpp-warnings-error")
        result = self.run_build(src)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("::group::build", result.stdout)

    def test_preset_configures_through_the_preset(self):
        src = self.generate("cpp-basic")
        (src / "CMakePresets.json").write_text(
            '{"version": 6, "configurePresets": [{"name": "dev", "generator": '
            '"Ninja", "binaryDir": "${sourceDir}/preset-out", "cacheVariables": '
            '{"PT_FROM_PRESET": "yes"}}]}', encoding="utf-8")
        result = self.run_build(src, PRESET="dev", BUILD_DIR=str(src / "preset-out"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        cache = (src / "preset-out" / "CMakeCache.txt").read_text(encoding="utf-8")
        self.assertIn("PT_FROM_PRESET", cache)

    def test_preset_with_mismatched_build_dir_fails(self):
        src = self.generate("cpp-basic")
        (src / "CMakePresets.json").write_text(
            '{"version": 6, "configurePresets": [{"name": "dev", "generator": '
            '"Ninja", "binaryDir": "${sourceDir}/preset-out"}]}', encoding="utf-8")
        result = self.run_build(src, PRESET="dev", BUILD_DIR=str(src / "elsewhere"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("::error::", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
