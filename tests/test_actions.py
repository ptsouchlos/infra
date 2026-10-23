"""Tests for the composite actions in .github/actions/."""

import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACTIONS = ROOT / ".github" / "actions"


def action_files():
    return sorted(ACTIONS.glob("*/action.yml"))


def find_bash():
    # On Windows, PATH finds WSL's System32\bash.exe first; the actions run under Git Bash.
    if sys.platform == "win32":
        git = shutil.which("git")
        if git:
            candidate = Path(git).resolve().parent.parent / "bin" / "bash.exe"
            if candidate.is_file():
                return str(candidate)
    return shutil.which("bash") or "bash"


def run_script(path, env):
    full = {**os.environ, **env}
    return subprocess.run(
        [find_bash(), str(path)], env=full, capture_output=True, text=True
    )


class ActionStructure(unittest.TestCase):
    def test_expected_actions_exist(self):
        found = {f.parent.name for f in action_files()}
        self.assertEqual(
            found,
            {"setup-cpp", "cmake-build", "setup-rust", "cargo-check", "build-docs",
             "update-infra", "cargo-release"},
        )

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

    def test_windows_clang_exports_the_preinstalled_llvm(self):
        result, gh_env = self.run_install(RUNNER_OS="Windows", COMPILER="clang")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("apt-get", result.stdout)
        self.assertIn("CC=clang\n", gh_env)
        self.assertIn("CXX=clang++\n", gh_env)

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


class SetupRustScript(unittest.TestCase):
    script = ACTIONS / "setup-rust" / "install.sh"

    def run_install(self, **env):
        base = {"DRY_RUN": "1", "TOOLCHAIN": "stable", "COMPONENTS": "",
                "TARGETS": "", "RUNNER_OS": "Linux"}
        return run_script(self.script, {**base, **env})

    def test_no_targets_matches_the_previous_commands(self):
        r = self.run_install(COMPONENTS="rustfmt clippy")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("rustup toolchain install stable --profile minimal --no-self-update "
                      "--component rustfmt --component clippy", r.stdout)
        self.assertIn("rustup default stable", r.stdout)
        self.assertNotIn("--target", r.stdout)
        self.assertNotIn("apt-get", r.stdout)

    def test_targets_are_added_to_the_toolchain(self):
        r = self.run_install(TARGETS="x86_64-unknown-linux-musl wasm32-unknown-unknown")
        self.assertIn("--target x86_64-unknown-linux-musl --target wasm32-unknown-unknown",
                      r.stdout)

    def test_musl_target_on_linux_installs_musl_tools(self):
        r = self.run_install(TARGETS="aarch64-unknown-linux-musl")
        self.assertIn("apt-get install -y musl-tools", r.stdout)

    def test_musl_tools_are_linux_only(self):
        r = self.run_install(RUNNER_OS="macOS", TARGETS="x86_64-unknown-linux-musl")
        self.assertNotIn("apt-get", r.stdout)


@unittest.skipIf(sys.platform == "win32", "uses a fake gh on PATH")
@unittest.skipUnless(shutil.which("jq"), "jq is required")
class NotifyConsumersScript(unittest.TestCase):
    script = ROOT / ".github" / "scripts" / "notify-consumers.sh"

    def run_notify(self, listing, fail=""):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            calls = d / "calls"
            (d / "listing").write_text(listing)
            gh = d / "gh"
            gh.write_text(
                "#!/usr/bin/env bash\n"
                'case "$*" in\n'
                f'  *installation/repositories*) cat "{d}/listing" ;;\n'
                '  */topics*) echo \'["uses-infra"]\' ;;\n'
                f'  *dispatches*) echo "$*" >> "{calls}"\n'
                f'    if [ -n "{fail}" ]; then case "$*" in *"{fail}"*) exit 1 ;; esac; fi ;;\n'
                "esac\n")
            gh.chmod(0o755)
            env = {**os.environ, "PATH": f"{d}{os.pathsep}{os.environ['PATH']}",
                   "TAG": "v1.2.0"}
            result = subprocess.run([find_bash(), str(self.script)], env=env,
                                    capture_output=True, text=True)
            return result, calls.read_text() if calls.exists() else ""

    def test_only_topic_repos_are_dispatched_and_names_stay_out_of_the_log(self):
        result, calls = self.run_notify(
            'me/a\t["uses-infra","x"]\nme/b\t["other"]\nme/c\tnull\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("repos/me/a/dispatches", calls)
        self.assertIn("repos/me/c/dispatches", calls)  # topics fetched per repo
        self.assertNotIn("me/b", calls)
        self.assertIn("client_payload[tag]=v1.2.0", calls)
        self.assertIn("dispatched to 2 repos, 0 failed", result.stdout)
        self.assertNotIn("me/", result.stdout + result.stderr)

    def test_a_failed_dispatch_fails_the_job_without_naming_the_repo(self):
        result, _ = self.run_notify('me/a\t["uses-infra"]\nme/b\t["uses-infra"]\n',
                                    fail="me/b")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dispatched to 1 repos, 1 failed", result.stdout)
        self.assertNotIn("me/", result.stdout + result.stderr)


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def embd_file(remote, commit):
    return (f'[metadata]\nremote = "{remote}"\ncommit_hash = "{commit}"\n'
            'allow_untracked = false\n\n[files]\n')


@unittest.skipIf(sys.platform == "win32", "uses a fake embd/gh on PATH")
class UpdateInfraScript(unittest.TestCase):
    script = ACTIONS / "update-infra" / "update.sh"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        # A local "infra" remote with tags v1.0.0 and v2.0.0.
        self.remote = tmp / "infra.git"
        work = tmp / "infra-work"
        work.mkdir()
        git(work, "init", "-q", "-b", "main")
        self.commits = {}
        for tag in ("v1.0.0", "v2.0.0"):
            (work / "f").write_text(tag)
            git(work, "add", "f")
            git(work, "commit", "-q", "-m", tag)
            git(work, "tag", tag)
            self.commits[tag] = subprocess.run(
                ["git", "rev-parse", tag], cwd=work, capture_output=True, text=True,
                check=True).stdout.strip()
        git(tmp, "clone", "-q", "--bare", str(work), str(self.remote))
        # Fake tools: embd records its calls (or fails on demand); gh reports a latest release.
        self.bin = tmp / "bin"
        self.bin.mkdir()
        self.calls = tmp / "embd-calls"
        (self.bin / "embd").write_text(
            f'#!/usr/bin/env bash\necho "$@" >> "{self.calls}"\n'
            '[ -z "${FAKE_EMBD_FAIL:-}" ] || { echo "local modifications" >&2; exit 1; }\n')
        (self.bin / "gh").write_text('#!/usr/bin/env bash\necho "${FAKE_LATEST:-v1.0.0}"\n')
        for f in self.bin.iterdir():
            f.chmod(0o755)
        # The consumer repo.
        self.repo = tmp / "consumer"
        (self.repo / "infra").mkdir(parents=True)
        (self.repo / "other").mkdir()
        (self.repo / ".github" / "workflows").mkdir(parents=True)
        self.old = self.commits["v1.0.0"]
        (self.repo / "infra" / ".embd").write_text(
            embd_file("git@github.com:ptsouchlos/infra.git", self.old))
        (self.repo / "other" / ".embd").write_text(
            embd_file("git@github.com:someone/else.git", "a" * 40))
        (self.repo / ".github" / "workflows" / "ci.yml").write_text(
            "steps:\n  - uses: ptsouchlos/infra/.github/actions/setup-rust@v1\n"
            "  - uses: actions/checkout@v1\n")
        self.out = tmp / "output"
        self.out.touch()

    def run_update(self, **env):
        base = {"PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
                "INFRA_URL": str(self.remote), "GITHUB_OUTPUT": str(self.out)}
        full = {**os.environ, **base, **env}
        return subprocess.run([find_bash(), str(self.script)], cwd=self.repo, env=full,
                              capture_output=True, text=True)

    def embd_calls(self):
        return self.calls.read_text() if self.calls.exists() else ""

    def workflow_path(self):
        return self.repo / ".github" / "workflows" / "ci.yml"

    def workflow(self):
        return self.workflow_path().read_text()

    def test_only_infra_embeds_are_updated(self):
        result = self.run_update(TAG="v1.0.0", FAKE_LATEST="v1.0.0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.embd_calls(), "")  # already at v1.0.0
        result = self.run_update(TAG="v2.0.0")
        self.assertEqual(self.embd_calls().strip(), "update ./infra --rev v2.0.0")

    def test_https_remote_without_git_suffix_matches(self):
        (self.repo / "infra" / ".embd").write_text(
            embd_file("https://github.com/ptsouchlos/infra", self.old))
        self.run_update(TAG="v2.0.0")
        self.assertIn("./infra", self.embd_calls())

    def test_current_embed_changes_nothing(self):
        (self.repo / "infra" / ".embd").write_text(
            embd_file("git@github.com:ptsouchlos/infra.git", self.commits["v2.0.0"]))
        self.workflow_path().write_text(self.workflow().replace("@v1", "@v2"))
        result = self.run_update(TAG="v2.0.0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.embd_calls(), "")
        self.assertIn("changed=false", self.out.read_text())

    def test_minor_release_keeps_workflow_refs(self):
        (self.repo / "infra" / ".embd").write_text(
            embd_file("git@github.com:ptsouchlos/infra.git", "b" * 40))
        self.run_update(TAG="v1.0.0")
        self.assertIn("setup-rust@v1\n", self.workflow())
        self.assertIn("changed=true", self.out.read_text())

    def test_major_release_rewrites_only_infra_action_refs(self):
        self.run_update(TAG="v2.0.0")
        text = self.workflow()
        self.assertIn("ptsouchlos/infra/.github/actions/setup-rust@v2", text)
        self.assertIn("actions/checkout@v1", text)

    def test_drift_fails_loudly_and_is_not_forced(self):
        result = self.run_update(TAG="v2.0.0", FAKE_EMBD_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("--force", self.embd_calls())

    def test_empty_tag_uses_the_latest_release(self):
        self.run_update(TAG="", FAKE_LATEST="v2.0.0")
        self.assertIn("--rev v2.0.0", self.embd_calls())

    def test_non_release_tag_is_rejected(self):
        result = self.run_update(TAG="main")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("::error::", result.stdout + result.stderr)

    def test_dry_run_prints_instead_of_running_embd(self):
        result = self.run_update(TAG="v2.0.0", DRY_RUN="1")
        self.assertEqual(self.embd_calls(), "")
        self.assertIn("+ embd update ./infra --rev v2.0.0", result.stdout)


class UpdateInfraWorkflow(unittest.TestCase):
    path = ROOT / ".github" / "workflows" / "update-infra.yml"

    def test_is_a_reusable_workflow_that_wraps_the_action(self):
        text = self.path.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^  workflow_call:")
        self.assertRegex(text, r"(?m)^      tag:")
        self.assertRegex(text, r"(?m)^      INFRA_BOT_PRIVATE_KEY:")
        self.assertIn("ptsouchlos/infra/.github/actions/update-infra@v", text)
        self.assertIn("tag: ${{ inputs.tag }}", text)

    def test_third_party_actions_are_version_pinned(self):
        text = self.path.read_text(encoding="utf-8")
        for ref in re.findall(r"(?m)^\s*-?\s*uses:\s*(\S+)", text):
            with self.subTest(uses=ref):
                self.assertRegex(ref, r"@v\d")


def can_reach(host, port=443):
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


HAVE_TOOLS = bool(shutil.which("cmake") and shutil.which("ninja")
                  and (shutil.which("clang++") or shutil.which("g++")))


@unittest.skipIf(sys.platform == "win32",
                 "needs the MSVC environment; the cpp CI jobs cover Windows")
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

    def test_demo_projects_build_through_the_script(self):
        # The same kinds ci.yml feeds through the cmake-build action.
        env = {}
        if shutil.which("clang++"):  # gcc hosts may lack the sanitizer runtimes
            env = {"CC": "clang", "CXX": "clang++"}
        for kind in ("cpp-basic", "cpp-hardening", "cpp-sanitizers", "cpp-cpm"):
            with self.subTest(kind=kind):
                if kind == "cpp-cpm" and not can_reach("github.com"):
                    self.skipTest("no network")
                src = self.generate(kind, name=kind)
                result = self.run_build(src, **env)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_install_then_consumer_build(self):
        src = self.generate("cpp-install")
        prefix = self.tmp / "prefix"
        result = self.run_build(src, INSTALL_PREFIX=str(prefix))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = run_script(self.script, {
            "SOURCE_DIR": str(src / "consumer"),
            "BUILD_DIR": str(src / "build" / "consumer"),
            "CONFIGURE_ARGS": f"-DCMAKE_PREFIX_PATH={prefix}",
        })
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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

    def test_preset_ignores_build_dir_and_installs_from_its_binary_dir(self):
        src = self.generate("cpp-install")
        (src / "CMakePresets.json").write_text(
            '{"version": 6, "configurePresets": [{"name": "dev", "generator": '
            '"Ninja", "binaryDir": "${sourceDir}/preset-out"}]}', encoding="utf-8")
        prefix = self.tmp / "prefix"
        result = self.run_build(src, PRESET="dev", BUILD_DIR=str(src / "elsewhere"),
                                INSTALL_PREFIX=str(prefix))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((src / "elsewhere").exists())
        self.assertTrue(any(prefix.rglob("*-config.cmake")))

    def test_build_and_test_presets_run_when_present(self):
        src = self.generate("cpp-basic")
        (src / "CMakePresets.json").write_text(
            '{"version": 6, "configurePresets": [{"name": "dev", "generator": "Ninja", '
            '"binaryDir": "${sourceDir}/preset-out"}], '
            '"buildPresets": [{"name": "dev", "configurePreset": "dev", "targets": ["core"]}], '
            '"testPresets": [{"name": "dev", "configurePreset": "dev", '
            '"filter": {"include": {"name": "no-such-test"}}}]}', encoding="utf-8")
        result = self.run_build(src, PRESET="dev")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # The build preset builds only `core`, and the test preset's filter matches no test.
        self.assertFalse(any((src / "preset-out").glob("app*")))
        self.assertIn("No tests were found", result.stdout + result.stderr)


@unittest.skipIf(sys.platform == "win32", "uses a fake cargo on PATH")
class CargoCheckScript(unittest.TestCase):
    script = ACTIONS / "cargo-check" / "run.sh"

    def run_check(self, fail="", **env):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            calls = d / "calls"
            cargo = d / "cargo"
            cargo.write_text(
                "#!/usr/bin/env bash\n"
                f'echo "$*" >> "{calls}"\n'
                f'if [ "$1" = "{fail}" ]; then exit 1; fi\n')
            cargo.chmod(0o755)
            env = {"PATH": f"{d}{os.pathsep}{os.environ['PATH']}", **env}
            result = run_script(self.script, env)
            lines = calls.read_text().splitlines() if calls.exists() else []
            return result, lines

    def test_defaults_match_the_previous_commands(self):
        result, calls = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ["fmt --all --check",
                                 "clippy --all-targets -- -D warnings",
                                 "test"])

    def test_args_are_forwarded_to_clippy_and_test(self):
        result, calls = self.run_check(ARGS="--workspace --all-features")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ["fmt --all --check",
                                 "clippy --all-targets --workspace --all-features -- -D warnings",
                                 "test --workspace --all-features"])

    def test_steps_can_be_switched_off(self):
        _, calls = self.run_check(RUN_FMT="false", RUN_CLIPPY="false")
        self.assertEqual(calls, ["test"])

    def test_custom_clippy_args_follow_the_separator(self):
        _, calls = self.run_check(RUN_FMT="false", RUN_TESTS="false",
                                  CLIPPY_ARGS="-D warnings -W clippy::pedantic")
        self.assertEqual(calls, ["clippy --all-targets -- -D warnings -W clippy::pedantic"])

    def test_empty_clippy_args_stay_empty(self):
        # The action always sets CLIPPY_ARGS; clippy-args: "" must not fall back to -D warnings.
        _, calls = self.run_check(RUN_FMT="false", RUN_TESTS="false", CLIPPY_ARGS="")
        self.assertEqual(calls, ["clippy --all-targets --"])

    def test_failing_clippy_stops_before_test(self):
        result, calls = self.run_check(fail="clippy")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("::group::clippy", result.stdout)
        self.assertNotIn("test", calls)


@unittest.skipUnless(shutil.which("cargo"), "cargo is required")
class CargoCheckRealScript(unittest.TestCase):
    script = ACTIONS / "cargo-check" / "run.sh"

    def test_rust_basic_passes_through_the_script(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "my project"
            subprocess.run(
                [sys.executable, str(ROOT / "tests" / "generate.py"), "rust-basic", str(out),
                 "--infra", str(ROOT)],
                check=True, capture_output=True, text=True)
            result = run_script(self.script, {"WORKING_DIRECTORY": str(out),
                                              "ARGS": "--workspace"})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for group in ("fmt", "clippy", "test"):
                self.assertIn(f"::group::{group}", result.stdout)


@unittest.skipIf(sys.platform == "win32", "uses a fake cargo on PATH")
class CargoReleaseScript(unittest.TestCase):
    script = ACTIONS / "cargo-release" / "package.sh"
    linux = "x86_64-unknown-linux-musl"
    windows = "x86_64-pc-windows-msvc"

    def run_release(self, binary=True, crate="crate", target_dir=None, **env):
        """Run package.sh against a fake cargo; returns (result, cargo calls, out dir)."""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            calls = d / "calls"
            bindir = d / "bin"
            bindir.mkdir()
            cargo = bindir / "cargo"
            cargo.write_text(f'#!/usr/bin/env bash\necho "$*" >> "{calls}"\n')
            cargo.chmod(0o755)
            target = env["TARGET"]
            crate_dir = d / crate
            release = Path(target_dir or crate_dir / "target") / target / "release"
            if binary:
                release.mkdir(parents=True)
                exe = ".exe" if "windows" in target else ""
                (release / (env["BIN"] + exe)).write_text("binary")
            out = d / "dist"
            gh_output = d / "gh_output"
            gh_output.touch()
            full = {"PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
                    "WORKING_DIRECTORY": str(crate_dir), "OUT_DIR": str(out),
                    "GITHUB_OUTPUT": str(gh_output), "ARCHIVE": "auto", "NAME": "",
                    "CARGO_ARGS": "", **env}
            if target_dir:
                full["CARGO_TARGET_DIR"] = str(target_dir)
            crate_dir.mkdir(exist_ok=True)
            result = run_script(self.script, full)
            lines = calls.read_text().splitlines() if calls.exists() else []
            # Read everything the tests need before the temp dir goes away.
            self.out_files = sorted(p.name for p in out.glob("*")) if out.exists() else []
            self.gh_output = gh_output.read_text()
            self.tar_names = None
            self.zip_names = None
            tar = out / f"tool-{target}.tar.gz"
            if tar.exists():
                with tarfile.open(tar) as t:
                    self.tar_names = t.getnames()
            self.checksum = None
            self.checksum_ok = None
            for sha in out.glob("*.sha256") if out.exists() else []:
                self.checksum = sha.read_text()
                tool = shutil.which("sha256sum")
                if tool:
                    self.checksum_ok = subprocess.run(
                        [tool, "-c", sha.name], cwd=out, capture_output=True).returncode == 0
            zipped = out / f"tool-{target}.zip"
            if zipped.exists():
                with zipfile.ZipFile(zipped) as z:
                    self.zip_names = z.namelist()
            return result, lines, out

    def test_build_command_and_default_tar_asset(self):
        r, calls, _ = self.run_release(TARGET=self.linux, BIN="tool")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(calls, [f"build --release --target {self.linux}"])
        self.assertIn(f"tool-{self.linux}.tar.gz", self.out_files)

    def test_tar_archive_holds_only_the_binary_at_the_root(self):
        self.run_release(TARGET=self.linux, BIN="tool")
        self.assertEqual(self.tar_names, ["tool"])

    def test_checksum_names_the_bare_file(self):
        self.run_release(TARGET=self.linux, BIN="tool")
        self.assertRegex(self.checksum, rf"^[0-9a-f]{{64}}  tool-{self.linux}\.tar\.gz\n$")
        if self.checksum_ok is not None:
            self.assertTrue(self.checksum_ok)

    def test_windows_target_packages_the_exe(self):
        name = f"tool-1.2.3-{self.windows}"
        r, _, _ = self.run_release(TARGET=self.windows, BIN="tool", ARCHIVE="none", NAME=name)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"{name}.exe", self.out_files)
        self.assertIn(f"{name}.exe.sha256", self.out_files)

    @unittest.skipUnless(shutil.which("7z"), "7z is required")
    def test_zip_archive_holds_only_the_exe(self):
        r, _, _ = self.run_release(TARGET=self.windows, BIN="tool")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.zip_names, ["tool.exe"])

    def test_cargo_args_are_forwarded(self):
        _, calls, _ = self.run_release(TARGET=self.linux, BIN="tool",
                                       CARGO_ARGS="--locked --features=a,b")
        self.assertEqual(calls, [f"build --release --target {self.linux} --locked --features=a,b"])

    def test_cargo_target_dir_is_respected(self):
        with tempfile.TemporaryDirectory() as shared:
            r, _, _ = self.run_release(TARGET=self.linux, BIN="tool",
                                       target_dir=Path(shared) / "shared-target")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_working_directory_with_spaces(self):
        r, _, _ = self.run_release(TARGET=self.linux, BIN="tool", crate="my crate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_missing_binary_fails_with_the_expected_path(self):
        r, _, _ = self.run_release(binary=False, TARGET=self.linux, BIN="tool")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("::error::", out)
        self.assertIn(f"target/{self.linux}/release/tool", out)

    def test_outputs_are_written(self):
        self.run_release(TARGET=self.linux, BIN="tool")
        self.assertRegex(self.gh_output, r"(?m)^asset=.*\.tar\.gz$")
        self.assertRegex(self.gh_output, r"(?m)^checksum=.*\.tar\.gz\.sha256$")


@unittest.skipUnless(shutil.which("cargo") and shutil.which("rustc"), "cargo is required")
class CargoReleaseRealScript(unittest.TestCase):
    script = ACTIONS / "cargo-release" / "package.sh"

    def test_builds_and_packages_rust_basic(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            src = d / "my project"
            subprocess.run(
                [sys.executable, str(ROOT / "tests" / "generate.py"), "rust-basic", str(src),
                 "--infra", str(ROOT)],
                check=True, capture_output=True, text=True)
            name = re.search(r'(?m)^name\s*=\s*"([^"]+)"',
                             (src / "Cargo.toml").read_text()).group(1)
            host = re.search(r"(?m)^host:\s*(\S+)",
                             subprocess.run(["rustc", "-vV"], check=True, capture_output=True,
                                            text=True).stdout).group(1)
            out = d / "dist"
            gh_output = d / "gh_output"
            gh_output.touch()
            env = {"TARGET": host, "BIN": name, "WORKING_DIRECTORY": str(src),
                   "OUT_DIR": str(out), "GITHUB_OUTPUT": str(gh_output),
                   "CARGO_TARGET_DIR": str(d / "target")}
            result = run_script(self.script, env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            assets = [p.name for p in out.iterdir()]
            self.assertEqual(len(assets), 2, assets)
            self.assertTrue(any(a.endswith(".sha256") for a in assets), assets)


if __name__ == "__main__":
    unittest.main()
