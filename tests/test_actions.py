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
            {"setup-cpp", "cmake-build", "setup-rust", "cargo-check", "cargo-build",
             "cargo-deps", "build-docs", "update-infra", "cargo-release", "package-nfpm",
             "package-appimage", "package-flatpak", "package-macos"},
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

    def test_vcpkg_off_by_default(self):
        result, gh_env = self.run_install(RUNNER_OS="Linux", COMPILER="gcc", VCPKG_ROOT="")
        self.assertNotIn("vcpkg", result.stdout)
        self.assertNotIn("VCPKG_ROOT", gh_env)

    def test_vcpkg_clones_and_bootstraps_into_runner_temp(self):
        result, gh_env = self.run_install(RUNNER_OS="Linux", COMPILER="gcc", VCPKG="true",
                                          VCPKG_ROOT="", RUNNER_TEMP="/runner/temp")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("git clone https://github.com/microsoft/vcpkg.git /runner/temp/vcpkg",
                      result.stdout)
        self.assertIn("/runner/temp/vcpkg/bootstrap-vcpkg.sh -disableMetrics", result.stdout)
        # On Windows, cygpath turns the path into C:/.../runner/temp/vcpkg.
        self.assertRegex(gh_env, r"VCPKG_ROOT=.*/runner/temp/vcpkg\n")

    def test_vcpkg_on_windows_bootstraps_with_the_batch_file(self):
        result, gh_env = self.run_install(RUNNER_OS="Windows", COMPILER="msvc", VCPKG="true",
                                          VCPKG_ROOT="", RUNNER_TEMP="/runner/temp")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("cmd.exe //c", result.stdout)
        self.assertIn("bootstrap-vcpkg.bat -disableMetrics", result.stdout)
        self.assertNotIn("bootstrap-vcpkg.sh", result.stdout)
        self.assertIn("VCPKG_ROOT=", gh_env)

    def test_vcpkg_keeps_an_existing_vcpkg_root(self):
        result, gh_env = self.run_install(RUNNER_OS="Linux", COMPILER="gcc", VCPKG="true",
                                          VCPKG_ROOT="/opt/vcpkg")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("git clone", result.stdout)
        self.assertRegex(gh_env, r"VCPKG_ROOT=.*/opt/vcpkg\n")


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


@unittest.skipIf(sys.platform == "win32", "uses a fake just on PATH")
class CargoBuildScript(unittest.TestCase):
    script = ACTIONS / "cargo-build" / "run.sh"

    def run_build(self, missing="", **env):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            calls = d / "calls"
            just = d / "just"
            just.write_text(
                "#!/usr/bin/env bash\n"
                'if [ "$1" = "--show" ]; then\n'
                f'  [ "$2" = "{missing}" ] && exit 1\n'
                "  exit 0\n"
                "fi\n"
                f'echo "$*${{CARGO_BIN:+ [CARGO_BIN=$CARGO_BIN]}}" >> "{calls}"\n')
            just.chmod(0o755)
            env = {"PATH": f"{d}{os.pathsep}{os.environ['PATH']}", **env}
            result = run_script(self.script, env)
            lines = calls.read_text().splitlines() if calls.exists() else []
            return result, lines

    def test_debug_builds_and_tests_by_default(self):
        result, calls = self.run_build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ["build", "test"])

    def test_release_uses_the_release_recipe_and_tests_with_release(self):
        result, calls = self.run_build(BUILD_TYPE="release")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ["build-release", "test --release"])

    def test_args_go_to_the_build_and_the_test(self):
        _, calls = self.run_build(ARGS="--workspace --all-features")
        self.assertEqual(calls, ["build --workspace --all-features",
                                 "test --workspace --all-features"])

    def test_release_puts_its_flag_before_the_args(self):
        _, calls = self.run_build(BUILD_TYPE="release", ARGS="--workspace")
        self.assertEqual(calls, ["build-release --workspace", "test --release --workspace"])

    def test_tests_can_be_switched_off(self):
        _, calls = self.run_build(RUN_TESTS="false")
        self.assertEqual(calls, ["build"])

    def test_bin_reaches_the_recipes_as_cargo_bin(self):
        _, calls = self.run_build(BIN="my-tool")
        self.assertEqual(calls[0], "build [CARGO_BIN=my-tool]")

    def test_unknown_build_type_fails_before_running_anything(self):
        result, calls = self.run_build(BUILD_TYPE="profile")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("debug or release", result.stderr)
        self.assertEqual(calls, [])

    def test_missing_recipe_says_to_import_cargo_just(self):
        result, calls = self.run_build(missing="build-release", BUILD_TYPE="release")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cargo.just", result.stderr)
        self.assertEqual(calls, [])


@unittest.skipUnless(shutil.which("cargo") and shutil.which("just"), "cargo and just are required")
class CargoBuildRealScript(unittest.TestCase):
    script = ACTIONS / "cargo-build" / "run.sh"

    def test_rust_basic_builds_and_tests_in_both_build_types(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "my project"
            subprocess.run(
                [sys.executable, str(ROOT / "tests" / "generate.py"), "rust-basic", str(out),
                 "--infra", str(ROOT)],
                check=True, capture_output=True, text=True)
            for build_type in ("debug", "release"):
                with self.subTest(build_type=build_type):
                    result = run_script(self.script, {"WORKING_DIRECTORY": str(out),
                                                      "BUILD_TYPE": build_type})
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn(f"::group::build ({build_type})", result.stdout)
                    self.assertIn(f"::group::test ({build_type})", result.stdout)
            self.assertTrue((out / "target" / "release").is_dir())


class CargoDepsAction(unittest.TestCase):
    path = ACTIONS / "cargo-deps" / "action.yml"

    def setUp(self):
        self.text = self.path.read_text(encoding="utf-8")

    def test_each_check_has_its_own_switch(self):
        self.assertIn("if: inputs.deny == 'true'", self.text)
        self.assertIn("if: inputs.machete == 'true'", self.text)

    def test_advisories_are_off_by_default(self):
        self.assertRegex(self.text, r"(?ms)^  deny-checks:.*?default: licenses bans sources\n")
        self.assertNotRegex(self.text, r"default: .*advisories")

    def test_the_directory_reaches_both_tools(self):
        self.assertIn("manifest-path: ${{ inputs.working-directory }}/Cargo.toml", self.text)
        self.assertIn("args: ${{ inputs.machete-args }} ${{ inputs.working-directory }}", self.text)

    def test_says_it_needs_linux(self):
        self.assertIn("Linux runners only", self.text)


@unittest.skipUnless(shutil.which("just"), "just is required")
class DepsRecipes(unittest.TestCase):
    def dry_run(self, recipe, **env):
        with tempfile.TemporaryDirectory() as d:
            justfile = Path(d) / "justfile"
            justfile.write_text(f"import '{(ROOT / 'rust' / 'just' / 'deps.just').as_posix()}'\n")
            result = subprocess.run(
                ["just", "--justfile", str(justfile), "--dry-run", recipe],
                env={**os.environ, **env}, capture_output=True, text=True)
            return result

    def test_deny_checks_licenses_bans_and_sources_by_default(self):
        result = self.dry_run("deny")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("cargo deny check licenses bans sources", result.stderr)

    def test_deny_checks_can_be_overridden(self):
        result = self.dry_run("deny", DENY_CHECKS="advisories")
        self.assertIn("cargo deny check advisories", result.stderr)

    def test_machete(self):
        self.assertIn("cargo machete", self.dry_run("machete").stderr)


class RustBuildWorkflow(unittest.TestCase):
    path = ROOT / ".github" / "workflows" / "rust-build.yml"

    def setUp(self):
        self.text = self.path.read_text(encoding="utf-8")

    def test_is_a_reusable_workflow_with_the_three_matrix_inputs(self):
        self.assertRegex(self.text, r"(?m)^  workflow_call:")
        for name in ("os", "toolchain", "build-type"):
            with self.subTest(input=name):
                self.assertRegex(self.text, rf"(?m)^      {name}:")
                self.assertIn(f"{name}: ${{{{ fromJSON(inputs.{name}) }}}}", self.text)

    def test_matrix_defaults_are_single_leg_json_arrays(self):
        self.assertIn("""default: '["ubuntu-latest"]'""", self.text)
        self.assertIn("""default: '["stable"]'""", self.text)
        self.assertIn("""default: '["debug"]'""", self.text)

    def test_one_failing_leg_does_not_cancel_the_rest(self):
        self.assertRegex(self.text, r"(?m)^      fail-fast: false")

    def test_only_prerelease_toolchains_may_fail(self):
        self.assertIn("inputs.allow-prerelease-failures", self.text)
        self.assertIn("matrix.toolchain == 'beta'", self.text)
        self.assertIn("startsWith(matrix.toolchain, 'nightly')", self.text)

    def test_lfs_input_defaults_off_and_reaches_the_checkout(self):
        self.assertRegex(self.text, r"(?ms)^      lfs:\n.*?default: false")
        checkout = self.text.index("actions/checkout@v")
        self.assertIn("lfs: ${{ inputs.lfs }}", self.text[checkout:self.text.index("setup-rust@v")])

    def test_runs_setup_rust_with_just_then_cargo_build(self):
        setup = self.text.index("actions/setup-rust@v")
        build = self.text.index("actions/cargo-build@v")
        self.assertLess(setup, build)
        self.assertIn('just: "true"', self.text)
        self.assertIn("build-type: ${{ matrix.build-type }}", self.text)

    def test_third_party_actions_are_version_pinned(self):
        for ref in re.findall(r"(?m)^\s*-?\s*uses:\s*(\S+)", self.text):
            with self.subTest(uses=ref):
                self.assertRegex(ref, r"@v\d")


@unittest.skipIf(sys.platform == "win32", "uses a fake cargo on PATH")
class CargoReleaseScript(unittest.TestCase):
    script = ACTIONS / "cargo-release" / "package.sh"
    linux = "x86_64-unknown-linux-musl"
    windows = "x86_64-pc-windows-msvc"

    def run_release(self, binary=True, crate="crate", target_dir=None, missing=(), **env):
        """Run package.sh against a fake cargo; returns (result, cargo calls, out dir).

        Fake binaries are created for every name in BINS (else BIN), except those in `missing`.
        """
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
                for name in env.get("BINS", env.get("BIN", "")).split():
                    if name not in missing:
                        (release / (name + exe)).write_text("binary")
            out = d / "dist"
            gh_output = d / "gh_output"
            gh_output.touch()
            full = {"PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
                    "WORKING_DIRECTORY": str(crate_dir), "OUT_DIR": str(out),
                    "GITHUB_OUTPUT": str(gh_output), "ARCHIVE": "auto", "NAME": "",
                    "CARGO_ARGS": "", "BIN": "", "BINS": "", **env}
            if target_dir:
                full["CARGO_TARGET_DIR"] = str(target_dir)
            crate_dir.mkdir(exist_ok=True)
            result = run_script(self.script, full)
            lines = calls.read_text().splitlines() if calls.exists() else []
            # Read everything the tests need before the temp dir goes away.
            self.out_files = sorted(p.name for p in out.glob("*")) if out.exists() else []
            self.gh_output = gh_output.read_text()
            self.stage_names = None
            for line in self.gh_output.splitlines():
                if line.startswith("bin-dir="):
                    self.stage_names = sorted(p.name for p in Path(line[8:]).iterdir())
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

    def test_bins_are_all_in_the_tar_archive(self):
        r, _, _ = self.run_release(TARGET=self.linux, BINS="tool toold toolctl")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sorted(self.tar_names), ["tool", "toolctl", "toold"])

    def test_bins_default_name_uses_the_first_binary(self):
        self.run_release(TARGET=self.linux, BINS="tool toold")
        self.assertIn(f"tool-{self.linux}.tar.gz", self.out_files)

    @unittest.skipUnless(shutil.which("7z"), "7z is required")
    def test_bins_are_all_in_the_zip_archive(self):
        r, _, _ = self.run_release(TARGET=self.windows, BINS="tool toold")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sorted(self.zip_names), ["tool.exe", "toold.exe"])

    def test_bins_take_precedence_over_bin(self):
        self.run_release(TARGET=self.linux, BIN="other", BINS="tool toold")
        self.assertEqual(sorted(self.tar_names), ["tool", "toold"])

    def test_bin_alone_still_works(self):
        r, _, _ = self.run_release(TARGET=self.linux, BIN="tool")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.tar_names, ["tool"])

    def test_neither_bin_nor_bins_fails(self):
        r, _, _ = self.run_release(TARGET=self.linux)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("::error::", r.stdout + r.stderr)

    def test_a_missing_binary_among_several_is_named(self):
        r, _, _ = self.run_release(TARGET=self.linux, BINS="tool toold", missing=("toold",))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(f"target/{self.linux}/release/toold", r.stdout + r.stderr)

    def test_archive_none_rejects_several_binaries(self):
        r, _, _ = self.run_release(TARGET=self.linux, BINS="tool toold", ARCHIVE="none")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("::error::", r.stdout + r.stderr)

    def test_staged_directory_holds_every_binary(self):
        self.run_release(TARGET=self.linux, BINS="tool toold toolctl")
        self.assertEqual(self.stage_names, ["tool", "toolctl", "toold"])

    def test_staged_directory_is_output_for_a_single_bin_too(self):
        self.run_release(TARGET=self.linux, BIN="tool")
        self.assertEqual(self.stage_names, ["tool"])

    def test_staged_directory_with_archive_none(self):
        self.run_release(TARGET=self.linux, BIN="tool", ARCHIVE="none")
        self.assertEqual(self.stage_names, ["tool"])


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


@unittest.skipIf(sys.platform == "win32", "uses a fake nfpm on PATH")
class PackageNfpmInstallScript(unittest.TestCase):
    script = ACTIONS / "package-nfpm" / "install.sh"

    def run_install(self, **env):
        return run_script(self.script, {"DRY_RUN": "1", "NFPM_VERSION": "2.48.0", **env})

    def test_x64_runner_fetches_the_x86_64_build_and_checksums(self):
        r = self.run_install(RUNNER_ARCH="X64")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("v2.48.0/nfpm_2.48.0_Linux_x86_64.tar.gz", r.stdout)
        self.assertIn("v2.48.0/checksums.txt", r.stdout)

    def test_arm64_runner_fetches_the_arm64_build(self):
        r = self.run_install(RUNNER_ARCH="ARM64")
        self.assertIn("nfpm_2.48.0_Linux_arm64.tar.gz", r.stdout)

    def test_unknown_runner_architecture_fails(self):
        r = self.run_install(RUNNER_ARCH="PPC")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("::error::", r.stdout + r.stderr)


@unittest.skipIf(sys.platform == "win32", "uses a fake nfpm on PATH")
class PackageNfpmScript(unittest.TestCase):
    script = ACTIONS / "package-nfpm" / "package.sh"

    def run_package(self, config=True, **env):
        """Run package.sh against a fake nfpm; returns (result, nfpm calls)."""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            calls = d / "calls"
            bindir = d / "fakebin"
            bindir.mkdir()
            nfpm = bindir / "nfpm"
            # Record the call and the exported variables, then write the --target file.
            nfpm.write_text(
                '#!/usr/bin/env bash\n'
                f'echo "$*" >> "{calls}"\n'
                f'echo "env $PKG_BIN_DIR $PKG_VERSION $PKG_ARCH" >> "{calls}"\n'
                'while [ $# -gt 0 ]; do\n'
                '  [ "$1" = --target ] && echo package > "$2"\n'
                '  shift\n'
                'done\n')
            nfpm.chmod(0o755)
            staged = d / "staged"
            staged.mkdir()
            cfg = d / "nfpm.yaml"
            if config:
                cfg.write_text("name: tool\n")
            gh_output = d / "gh_output"
            gh_output.touch()
            out = d / "dist"
            full = {"PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
                    "CONFIG": str(cfg), "BIN_DIR": str(staged), "VERSION": "1.2.3",
                    "ARCH": "x86_64", "NAME": "tool-1.2.3-linux-x86_64",
                    "OUT_DIR": str(out), "GITHUB_OUTPUT": str(gh_output), **env}
            result = run_script(self.script, full)
            # Not resolve(): on macOS the temp dir sits behind a /var -> /private/var symlink.
            self.staged = str(staged)
            self.out_files = sorted(p.name for p in out.glob("*")) if out.exists() else []
            self.gh_output = gh_output.read_text()
            self.checksum = None
            for sha in out.glob("*.deb.sha256") if out.exists() else []:
                self.checksum = sha.read_text()
            lines = calls.read_text().splitlines() if calls.exists() else []
            return result, lines

    def test_default_builds_deb_and_rpm_with_checksums(self):
        r, calls = self.run_package()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.out_files, [
            "tool-1.2.3-linux-x86_64.deb", "tool-1.2.3-linux-x86_64.deb.sha256",
            "tool-1.2.3-linux-x86_64.rpm", "tool-1.2.3-linux-x86_64.rpm.sha256"])
        self.assertEqual(sum(c.startswith("package ") for c in calls), 2)
        self.assertRegex(self.checksum, r"^[0-9a-f]{64}  tool-1\.2\.3-linux-x86_64\.deb\n$")

    def test_packager_flag_matches_each_format(self):
        _, calls = self.run_package(FORMATS="rpm")
        self.assertEqual(len([c for c in calls if c.startswith("package ")]), 1)
        self.assertIn("--packager rpm", calls[0])

    def test_config_variables_are_exported_with_go_arch_names(self):
        # calls holds one "package ..." line then one "env ..." line per format.
        _, calls = self.run_package(ARCH="aarch64", FORMATS="deb")
        self.assertEqual(calls[1], f"env {self.staged} 1.2.3 arm64")

    def test_x86_64_maps_to_amd64(self):
        _, calls = self.run_package()
        self.assertEqual(calls[1], f"env {self.staged} 1.2.3 amd64")

    def test_outputs_list_assets_and_checksums(self):
        self.run_package(FORMATS="deb")
        self.assertIn("tool-1.2.3-linux-x86_64.deb\n", self.gh_output)
        self.assertIn("tool-1.2.3-linux-x86_64.deb.sha256\n", self.gh_output)

    def test_unsupported_arch_fails(self):
        r, calls = self.run_package(ARCH="riscv64")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(calls, [])

    def test_unsupported_format_fails_before_building(self):
        r, calls = self.run_package(FORMATS="deb apk")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("::error::", r.stdout + r.stderr)
        self.assertEqual(calls, [])

    def test_missing_config_fails(self):
        r, calls = self.run_package(config=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("::error::", r.stdout + r.stderr)
        self.assertEqual(calls, [])


PNG_64 = (  # a valid 64x64 PNG header is all package.sh reads
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x40\x00\x00\x00\x40\x08\x02\x00\x00\x00")


@unittest.skipIf(sys.platform == "win32", "uses bash scripts")
class PackageAppimageInstallScript(unittest.TestCase):
    script = ACTIONS / "package-appimage" / "install.sh"

    def run_install(self, **env):
        return run_script(self.script, {"DRY_RUN": "1", "TOOL_VERSION": "1.9.1", **env})

    def test_x64_runner_fetches_the_x86_64_tool_with_its_checksum(self):
        r = self.run_install(RUNNER_ARCH="X64")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("1.9.1/appimagetool-x86_64.AppImage", r.stdout)
        self.assertIn("sha256 ed4ce84f", r.stdout)

    def test_arm64_runner_fetches_the_aarch64_tool(self):
        r = self.run_install(RUNNER_ARCH="ARM64")
        self.assertIn("1.9.1/appimagetool-aarch64.AppImage", r.stdout)
        self.assertIn("sha256 f0837e74", r.stdout)

    def test_other_version_needs_a_checksum(self):
        r = self.run_install(RUNNER_ARCH="X64", TOOL_VERSION="1.9.0")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("appimagetool-sha256", r.stdout + r.stderr)

    def test_other_version_with_a_checksum_is_accepted(self):
        r = self.run_install(RUNNER_ARCH="X64", TOOL_VERSION="1.9.0", TOOL_SHA256="ab" * 32)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("1.9.0/appimagetool-x86_64.AppImage", r.stdout)

    def test_unknown_runner_architecture_fails(self):
        r = self.run_install(RUNNER_ARCH="PPC")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("::error::", r.stdout + r.stderr)


@unittest.skipIf(sys.platform == "win32", "uses bash scripts")
class PackageAppimageScript(unittest.TestCase):
    script = ACTIONS / "package-appimage" / "package.sh"

    def run_package(self, desktop="[Desktop Entry]\nName=Tool\nExec=tool\nIcon=tool\n",
                    icon=PNG_64, **env):
        """Run package.sh against a fake appimagetool that snapshots the AppDir it is given.

        Sets self.tree (sorted relative file paths), self.files (path -> text), self.args
        (the appimagetool command line) and self.out_files.
        """
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            fake = d / "fakebin"
            fake.mkdir()
            tool = fake / "appimagetool"
            tool.write_text(
                '#!/usr/bin/env bash\n'
                f'echo "$ARCH $*" > "{d}/args"\n'
                'args=("$@"); n=${#args[@]}\n'
                f'cp -a "${{args[$((n-2))]}}" "{d}/snapshot"\n'
                'echo image > "${args[$((n-1))]}"\n')
            tool.chmod(0o755)
            binaries = d / "bins"
            binaries.mkdir()
            (binaries / "tool").write_text("#!/bin/sh\n")
            (binaries / "toolctl").write_text("#!/bin/sh\n")
            (d / "tool.desktop").write_text(desktop)
            if icon is not None:
                (d / "icon.png").write_bytes(icon)
            gh_output = d / "gh_output"
            gh_output.touch()
            out = d / "dist"
            full = {"PATH": f"{fake}{os.pathsep}{os.environ['PATH']}",
                    "BIN_DIR": str(binaries), "EXE": "tool", "DESKTOP_FILE": str(d / "tool.desktop"),
                    "ICON": str(d / "icon.png"), "NAME": "tool-1.2.3-linux-x86_64",
                    "ARCH": "x86_64", "OUT_DIR": str(out), "GITHUB_OUTPUT": str(gh_output), **env}
            result = run_script(self.script, full)
            snap = d / "snapshot"
            self.tree = sorted(str(p.relative_to(snap)) for p in snap.rglob("*")
                               if p.is_file()) if snap.exists() else []
            self.files = {str(p.relative_to(snap)): p.read_text(errors="replace")
                          for p in snap.rglob("*") if p.is_file()} if snap.exists() else {}
            self.args = (d / "args").read_text().strip() if (d / "args").exists() else ""
            self.out_files = sorted(p.name for p in out.glob("*")) if out.exists() else []
            self.gh_output = gh_output.read_text()
            return result

    def test_builds_the_image_and_checksum(self):
        r = self.run_package()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.out_files, ["tool-1.2.3-linux-x86_64.AppImage",
                                          "tool-1.2.3-linux-x86_64.AppImage.sha256"])
        self.assertIn("asset=", self.gh_output)
        self.assertIn("checksum=", self.gh_output)

    def test_appdir_layout(self):
        self.run_package()
        for path in ("AppRun", ".DirIcon", "tool.png", "tool.desktop", "usr/bin/tool",
                     "usr/bin/toolctl", "usr/share/applications/tool.desktop",
                     "usr/share/icons/hicolor/64x64/apps/tool.png"):
            self.assertIn(path, self.tree)

    def test_default_apprun_starts_the_named_exe(self):
        self.run_package()
        self.assertIn('usr/bin/tool"', self.files["AppRun"])
        self.assertNotIn("@EXE@", self.files["AppRun"])

    def test_custom_apprun_is_copied_as_is(self):
        with tempfile.TemporaryDirectory() as d:
            custom = Path(d) / "AppRun"
            custom.write_text("#!/bin/sh\necho custom\n")
            self.run_package(APPRUN=str(custom))
        self.assertEqual(self.files["AppRun"], "#!/bin/sh\necho custom\n")

    def test_without_metainfo_skips_appstream_validation(self):
        self.run_package()
        self.assertIn("--no-appstream", self.args)

    def test_with_metainfo_it_is_packaged_and_validated(self):
        with tempfile.TemporaryDirectory() as d:
            meta = Path(d) / "io.example.Tool.metainfo.xml"
            meta.write_text("<component/>")
            self.run_package(METAINFO=str(meta))
        self.assertIn("usr/share/metainfo/io.example.Tool.metainfo.xml", self.tree)
        self.assertNotIn("--no-appstream", self.args)

    def test_arch_is_passed_to_appimagetool(self):
        self.run_package(ARCH="aarch64")
        self.assertTrue(self.args.startswith("aarch64 "), self.args)

    def test_pinned_runtime_is_passed_when_installed(self):
        self.run_package(APPIMAGE_RUNTIME_DIR="/pinned")
        self.assertIn("--runtime-file /pinned/runtime-x86_64", self.args)

    def test_exe_must_be_in_bin_dir(self):
        r = self.run_package(EXE="missing")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("::error::", r.stdout + r.stderr)
        self.assertEqual(self.args, "")

    def test_desktop_file_needs_an_icon_line(self):
        r = self.run_package(desktop="[Desktop Entry]\nName=Tool\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Icon=", r.stdout + r.stderr)

    def test_icon_must_be_a_png(self):
        r = self.run_package(icon=b"not a png at all, but long enough to read")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.args, "")

    def test_unsupported_arch_fails(self):
        r = self.run_package(ARCH="riscv64")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.args, "")


@unittest.skipIf(sys.platform == "win32", "uses a POSIX shell")
class PackageAppimageAppRun(unittest.TestCase):
    template = ACTIONS / "package-appimage" / "AppRun"

    def run_apprun(self, args=(), argv0=None):
        with tempfile.TemporaryDirectory() as d:
            appdir = Path(d) / "app"
            (appdir / "usr" / "bin").mkdir(parents=True)
            for name in ("tool", "toolctl"):
                exe = appdir / "usr" / "bin" / name
                exe.write_text(f'#!/bin/sh\necho "{name} $*"\n')
                exe.chmod(0o755)
            apprun = appdir / "AppRun"
            apprun.write_text(self.template.read_text().replace("@EXE@", "tool"))
            apprun.chmod(0o755)
            env = {**os.environ}
            env.pop("ARGV0", None)
            if argv0:
                env["ARGV0"] = argv0
            return subprocess.run(["sh", str(apprun), *args], env=env,
                                  capture_output=True, text=True).stdout.strip()

    def test_starts_the_main_exe_by_default(self):
        self.assertEqual(self.run_apprun(["a", "b"]), "tool a b")

    def test_first_argument_naming_a_binary_starts_it(self):
        self.assertEqual(self.run_apprun(["toolctl", "x"]), "toolctl x")

    def test_invoked_name_selects_the_binary(self):
        self.assertEqual(self.run_apprun(["x"], argv0="/usr/local/bin/toolctl"), "toolctl x")

    def test_unrelated_invoked_name_falls_back_to_the_main_exe(self):
        self.assertEqual(self.run_apprun(["x"], argv0="tool-1.2.3-linux-x86_64.AppImage"),
                         "tool x")


@unittest.skipIf(sys.platform == "win32", "uses bash scripts")
class PackageFlatpakInstallScript(unittest.TestCase):
    script = ACTIONS / "package-flatpak" / "install.sh"

    def run_install(self, **env):
        return run_script(self.script, {"DRY_RUN": "1", **env})

    def test_installs_the_tools_and_adds_the_remote(self):
        r = self.run_install()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("apt-get install -y flatpak flatpak-builder", r.stdout)
        self.assertIn("flatpak remote-add --user --if-not-exists flathub "
                      "https://dl.flathub.org/repo/flathub.flatpakrepo", r.stdout)

    def test_runtime_repo_override_is_used_for_the_remote(self):
        r = self.run_install(RUNTIME_REPO="https://example.org/r.flatpakrepo")
        self.assertIn("flathub https://example.org/r.flatpakrepo", r.stdout)

    def test_lifts_the_apparmor_userns_restriction(self):
        r = self.run_install()
        self.assertIn("sysctl -w kernel.apparmor_restrict_unprivileged_userns=0", r.stdout)


@unittest.skipIf(sys.platform == "win32", "uses fake tools on PATH")
class PackageFlatpakScript(unittest.TestCase):
    script = ACTIONS / "package-flatpak" / "package.sh"

    def run_package(self, manifest=True, **env):
        """Run package.sh against fake flatpak-builder and flatpak.

        Sets self.builder_args / self.bundle_args (the command lines), self.src_tree (sorted
        files in the directory flatpak-builder was given the manifest from) and self.out_files.
        """
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            fake = d / "fakebin"
            fake.mkdir()
            builder = fake / "flatpak-builder"
            builder.write_text(
                '#!/usr/bin/env bash\n'
                f'echo "$*" > "{d}/builder_args"\n'
                'manifest="${!#}"\n'
                'src="$(dirname "$manifest")"\n'
                f'(cd "$src" && find . -type f | sort) > "{d}/src_tree"\n'
                f'cat "$manifest" > "{d}/manifest_seen"\n')
            builder.chmod(0o755)
            flatpak = fake / "flatpak"
            flatpak.write_text(
                '#!/usr/bin/env bash\n'
                f'echo "$*" > "{d}/bundle_args"\n'
                '# build-bundle ... <repo> <bundle> <app-id> <branch>\n'
                'args=("$@"); n=${#args[@]}\n'
                'echo bundle > "${args[$((n-3))]}"\n')
            flatpak.chmod(0o755)
            binaries = d / "bins"
            binaries.mkdir()
            (binaries / "tool").write_text("#!/bin/sh\n")
            pack = d / "packaging"
            pack.mkdir()
            (pack / "io.example.Tool.desktop").write_text("[Desktop Entry]\n")
            if manifest:
                (pack / "io.example.Tool.yml").write_text("app-id: io.example.Tool\n")
            gh_output = d / "gh_output"
            gh_output.touch()
            out = d / "dist"
            full = {"PATH": f"{fake}{os.pathsep}{os.environ['PATH']}",
                    "MANIFEST": str(pack / "io.example.Tool.yml"), "BIN_DIR": str(binaries),
                    "APP_ID": "io.example.Tool", "ARCH": "x86_64",
                    "NAME": "tool-1.2.3-linux-x86_64", "OUT_DIR": str(out),
                    "GITHUB_OUTPUT": str(gh_output), **env}
            result = run_script(self.script, full)

            def read(name):
                path = d / name
                return path.read_text().strip() if path.exists() else ""
            self.builder_args = read("builder_args")
            self.bundle_args = read("bundle_args")
            self.src_tree = read("src_tree").splitlines()
            self.manifest_seen = read("manifest_seen")
            self.out_files = sorted(p.name for p in out.glob("*")) if out.exists() else []
            self.gh_output = gh_output.read_text()
            return result

    def test_builds_the_bundle_and_checksum(self):
        r = self.run_package()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.out_files, ["tool-1.2.3-linux-x86_64.flatpak",
                                          "tool-1.2.3-linux-x86_64.flatpak.sha256"])
        self.assertIn("asset=", self.gh_output)
        self.assertIn("checksum=", self.gh_output)

    def test_manifest_dir_is_copied_with_the_binaries_at_bin(self):
        self.run_package()
        self.assertEqual(self.src_tree, ["./bin/tool", "./io.example.Tool.desktop",
                                         "./io.example.Tool.yml"])
        self.assertEqual(self.manifest_seen, "app-id: io.example.Tool")

    def test_builder_arguments(self):
        self.run_package(ARCH="aarch64", BRANCH="beta")
        for flag in ("--user", "--force-clean", "--disable-rofiles-fuse",
                     "--install-deps-from=flathub", "--arch=aarch64", "--default-branch=beta"):
            self.assertIn(flag, self.builder_args)
        # State stays out of the caller's checkout.
        self.assertRegex(self.builder_args, r"--state-dir=\S*/state")

    def test_bundle_arguments(self):
        self.run_package()
        self.assertIn("build-bundle", self.bundle_args)
        self.assertIn("--arch=x86_64", self.bundle_args)
        self.assertIn("--runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo",
                      self.bundle_args)
        self.assertTrue(self.bundle_args.endswith("io.example.Tool stable"), self.bundle_args)

    def test_a_stale_bin_next_to_the_manifest_does_not_leak_in(self):
        with tempfile.TemporaryDirectory() as d:
            # Same layout as the default run, but the manifest dir already has a bin/ of its own.
            pack = Path(d) / "packaging"
            (pack / "bin").mkdir(parents=True)
            (pack / "bin" / "stale").write_text("x")
            (pack / "m.yml").write_text("app-id: io.example.Tool\n")
            self.run_package(MANIFEST=str(pack / "m.yml"))
        self.assertIn("./bin/tool", self.src_tree)
        self.assertNotIn("./bin/stale", self.src_tree)

    def test_missing_manifest_fails_before_building(self):
        r = self.run_package(MANIFEST="/nonexistent/m.yml")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("::error::", r.stdout + r.stderr)
        self.assertEqual(self.builder_args, "")

    def test_missing_bin_dir_fails_before_building(self):
        r = self.run_package(BIN_DIR="/nonexistent/bins")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.builder_args, "")

    def test_unsupported_arch_fails(self):
        r = self.run_package(ARCH="riscv64")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.builder_args, "")


PNG_1024 = (  # only the IHDR is read: a 1024x1024 PNG header
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x04\x00\x00\x00\x04\x00\x08\x02\x00\x00\x00")

PLIST_TEMPLATE = """<plist><dict>
<key>CFBundleName</key><string>@APP_NAME@</string>
<key>CFBundleExecutable</key><string>@EXECUTABLE@</string>
<key>CFBundleIdentifier</key><string>@BUNDLE_ID@</string>
<key>CFBundleVersion</key><string>@VERSION@</string>
<key>CFBundleShortVersionString</key><string>@SHORT_VERSION@</string>
<key>CFBundleIconFile</key><string>@ICON_FILE@</string>
</dict></plist>
"""


@unittest.skipIf(sys.platform == "win32", "uses fake macOS tools on PATH")
class PackageMacosScript(unittest.TestCase):
    """package.sh against fake sips, iconutil, codesign and hdiutil.

    The real tools only exist on macOS; the package-macos CI job exercises them.
    """
    script = ACTIONS / "package-macos" / "package.sh"

    def run_package(self, plist=PLIST_TEMPLATE, icon=PNG_1024, **env):
        """Sets self.stage (relative paths in the dmg's source folder, symlinks marked with
        '@'), self.files (path -> text), self.codesign (one line per call), self.sips (pixel
        sizes) and self.out_files."""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            fake = d / "fakebin"
            fake.mkdir()

            def tool(name, body):
                path = fake / name
                path.write_text("#!/usr/bin/env bash\n" + body)
                path.chmod(0o755)
            tool("sips", f'echo "$2" >> "{d}/sips"\n'
                         'while [ $# -gt 0 ]; do [ "$1" = --out ] && echo icon > "$2"; shift; done\n')
            tool("iconutil", f'(cd "$3" && ls | sort) > "{d}/iconset"\necho icns > "$5"\n')
            tool("codesign", f'echo "$*" >> "{d}/codesign"\n')
            tool("hdiutil",
                 f'echo "$*" > "{d}/hdiutil"\n'
                 'args=("$@"); n=${#args[@]}\n'
                 'while [ $# -gt 0 ]; do [ "$1" = -srcfolder ] && src="$2"; shift; done\n'
                 f'cp -R "$src" "{d}/snapshot"\n'
                 'echo dmg > "${args[$((n-1))]}"\n')
            binaries = d / "bins"
            binaries.mkdir()
            (binaries / "tool").write_text("#!/bin/sh\n")
            (binaries / "toolctl").write_text("#!/bin/sh\n")
            (d / "Info.plist").write_text(plist)
            (d / "icon.png").write_bytes(icon)
            gh_output = d / "gh_output"
            gh_output.touch()
            out = d / "dist"
            full = {"PATH": f"{fake}{os.pathsep}{os.environ['PATH']}",
                    "BIN_DIR": str(binaries), "EXE": "tool", "APP_NAME": "Tool",
                    "BUNDLE_ID": "io.example.Tool", "VERSION": "1.2.3",
                    "INFO_PLIST": str(d / "Info.plist"), "ICON": str(d / "icon.png"),
                    "NAME": "tool-1.2.3-macos-aarch64", "OUT_DIR": str(out),
                    "GITHUB_OUTPUT": str(gh_output), **env}
            result = run_script(self.script, full)

            def read(name):
                path = d / name
                return path.read_text().strip().splitlines() if path.exists() else []
            snap = d / "snapshot"
            self.stage, self.files = [], {}
            if snap.exists():
                for p in sorted(snap.rglob("*")):
                    rel = str(p.relative_to(snap))
                    if p.is_symlink():
                        self.stage.append(rel + "@")
                    elif p.is_file():
                        self.stage.append(rel)
                        self.files[rel] = p.read_text(errors="replace")
            self.codesign = read("codesign")
            self.sips = read("sips")
            self.iconset = read("iconset")
            self.hdiutil = " ".join(read("hdiutil"))
            self.out_files = sorted(p.name for p in out.glob("*")) if out.exists() else []
            self.gh_output = gh_output.read_text()
            return result

    def test_builds_the_dmg_and_checksum(self):
        r = self.run_package()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.out_files, ["tool-1.2.3-macos-aarch64.dmg",
                                          "tool-1.2.3-macos-aarch64.dmg.sha256"])
        self.assertIn("asset=", self.gh_output)

    def test_bundle_layout_with_all_binaries_in_macos(self):
        self.run_package()
        for path in ("Tool.app/Contents/MacOS/tool", "Tool.app/Contents/MacOS/toolctl",
                     "Tool.app/Contents/Info.plist", "Tool.app/Contents/Resources/Tool.icns"):
            self.assertIn(path, self.stage)

    def test_dmg_holds_an_applications_shortcut(self):
        self.run_package()
        self.assertIn("Applications@", self.stage)
        self.assertIn("-volname Tool", self.hdiutil)
        self.assertIn("-format UDZO", self.hdiutil)

    def test_info_plist_placeholders_are_replaced(self):
        self.run_package()
        plist = self.files["Tool.app/Contents/Info.plist"]
        self.assertNotIn("@", plist)
        for fragment in ("<string>Tool</string>", "<string>tool</string>",
                         "<string>io.example.Tool</string>", "<string>1.2.3</string>"):
            self.assertIn(fragment, plist)

    def test_prerelease_is_dropped_from_the_short_version_only(self):
        self.run_package(VERSION="1.2.3-rc.1")
        plist = self.files["Tool.app/Contents/Info.plist"]
        self.assertIn("<key>CFBundleVersion</key><string>1.2.3-rc.1</string>", plist)
        self.assertIn("<key>CFBundleShortVersionString</key><string>1.2.3</string>", plist)

    def test_iconset_has_all_ten_sizes(self):
        self.run_package()
        self.assertEqual(len(self.iconset), 10)
        self.assertIn("icon_512x512@2x.png", self.iconset)
        self.assertEqual(sorted(set(self.sips), key=int), ["16", "32", "64", "128", "256", "512", "1024"])

    def test_signs_ad_hoc_by_default_binaries_first_then_the_bundle(self):
        self.run_package()
        self.assertEqual(len(self.codesign), 4)  # two binaries, the bundle, and the verify
        for line in self.codesign[:3]:
            self.assertTrue(line.startswith("--force --sign - "), line)
        self.assertTrue(self.codesign[2].endswith("Tool.app"), self.codesign[2])
        self.assertNotIn("--options runtime", " ".join(self.codesign))
        self.assertTrue(self.codesign[3].startswith("--verify"), self.codesign[3])

    def test_developer_id_turns_on_hardened_runtime_and_keeps_spaces_intact(self):
        self.run_package(SIGN_IDENTITY="Developer ID Application: Example (ABCDE12345)")
        for line in self.codesign[:3]:
            self.assertIn("--sign Developer ID Application: Example (ABCDE12345) "
                          "--options runtime --timestamp", line)

    def test_icon_must_be_at_least_1024(self):
        small = PNG_1024.replace(b"\x00\x00\x04\x00\x00\x00\x04\x00", b"\x00\x00\x02\x00\x00\x00\x02\x00")
        r = self.run_package(icon=small)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("1024", r.stdout + r.stderr)
        self.assertEqual(self.out_files, [])

    def test_icon_must_be_a_png(self):
        r = self.run_package(icon=b"not a png at all, but long enough to read")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("::error::", r.stdout + r.stderr)

    def test_exe_must_be_in_bin_dir(self):
        r = self.run_package(EXE="missing")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.codesign, [])

    def test_missing_plist_fails(self):
        r = self.run_package(INFO_PLIST="/nonexistent/Info.plist")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("info-plist", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
