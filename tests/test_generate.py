from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import generate
import run


def write_template(root: Path, name: str, manifest: dict, files: dict) -> None:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for relative, content in files.items():
        target = folder / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8"))


class ManifestTests(unittest.TestCase):
    def test_every_kind_loads_with_steps(self) -> None:
        for name in generate.list_kinds():
            with self.subTest(kind=name):
                kind = generate.load_kind(name)
                self.assertTrue(kind.description)
                self.assertTrue(kind.steps)

    def test_private_directories_are_not_kinds(self) -> None:
        self.assertNotIn("_cpp_common", generate.list_kinds())
        with self.assertRaises(generate.UnknownKind):
            generate.load_kind("_cpp_common")

    def test_unknown_kind(self) -> None:
        with self.assertRaises(generate.UnknownKind):
            generate.load_kind("does-not-exist")


class GenerateTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.out = self.tmp / "project"

    def test_cpp_basic_files_and_no_manifest(self) -> None:
        generate.generate("cpp-basic", self.out)
        for relative in (
            "CMakeLists.txt",
            "src/lib.hpp",
            "src/lib.cpp",
            "src/main.cpp",
            "test/check.cpp",
        ):
            self.assertTrue((self.out / relative).is_file(), relative)
        self.assertFalse((self.out / "manifest.json").exists())

    def test_infra_path_is_posix_in_generated_files(self) -> None:
        generate.generate("cpp-basic", self.out)
        text = (self.out / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn(generate.INFRA_DIR.as_posix() + "/cpp/cmake", text)
        self.assertNotIn("\\", text)

    def test_every_kind_generates_fully_resolved(self) -> None:
        for name in generate.list_kinds():
            with self.subTest(kind=name):
                out = self.tmp / name
                project = generate.generate(name, out)
                project.steps()  # raises on unresolved step tokens
                for path in out.rglob("*"):
                    if path.is_file():
                        text = path.read_text(encoding="utf-8")
                        self.assertIsNone(generate.UNRESOLVED.search(text), path)

    def test_rejects_non_empty_directory(self) -> None:
        self.out.mkdir()
        (self.out / "keep.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(generate.GenerateError):
            generate.generate("cpp-basic", self.out)
        generate.generate("cpp-basic", self.out, force=True)

    def test_rejects_unknown_variable_override(self) -> None:
        with self.assertRaises(generate.GenerateError):
            generate.generate("cpp-basic", self.out, overrides={"NOPE": "1"})

    def test_parse_overrides_splits_on_first_equals(self) -> None:
        self.assertEqual(
            generate.parse_overrides(["A=1", "B=x=y", "C="]),
            {"A": "1", "B": "x=y", "C": ""},
        )

    def test_parse_overrides_rejects_missing_equals(self) -> None:
        with self.assertRaises(generate.GenerateError) as caught:
            generate.parse_overrides(["oops"])
        self.assertIn("KEY=VALUE", str(caught.exception))
        self.assertIn("oops", str(caught.exception))

    def test_cli_reports_bad_set_cleanly(self) -> None:
        self.assertEqual(generate.main(["cpp-basic", str(self.out), "--set", "oops"]), 2)

    def test_manifest_with_utf8_bom_loads(self) -> None:
        templates = self.tmp / "templates"
        (templates / "bom").mkdir(parents=True)
        (templates / "bom" / "manifest.json").write_bytes(
            b"\xef\xbb\xbf" + b'{"description": "d", "steps": [{"name": "s", "cmd": ["true"]}]}'
        )
        self.assertEqual(generate.load_kind("bom", templates).description, "d")

    def test_nested_manifest_json_is_copied_as_a_project_file(self) -> None:
        templates = self.tmp / "templates"
        write_template(
            templates,
            "nested",
            {"description": "d", "steps": [{"name": "s", "cmd": ["true"]}]},
            {"sub/manifest.json": '{"payload": 1}'},
        )
        generate.generate("nested", self.out, templates_dir=templates)
        self.assertTrue((self.out / "sub" / "manifest.json").is_file())
        self.assertFalse((self.out / "manifest.json").exists())

    def test_lowercase_token_typo_is_an_error(self) -> None:
        templates = self.tmp / "templates"
        write_template(
            templates,
            "typo",
            {"description": "d", "steps": [{"name": "s", "cmd": ["true"]}]},
            {"file.txt": "path: @project_dir@\n"},
        )
        with self.assertRaises(generate.GenerateError):
            generate.generate("typo", self.out, templates_dir=templates)

    def test_infra_path_with_single_quote_is_rejected(self) -> None:
        with self.assertRaises(generate.GenerateError) as caught:
            generate.generate("cpp-basic", self.out, infra_dir=self.tmp / "it's here")
        self.assertIn("single quote", str(caught.exception))

    def test_requires_selects_by_os(self) -> None:
        kind = generate.load_kind("cpp-cpm")
        self.assertIn("git", kind.required_tools("linux"))
        self.assertIn("git", kind.required_tools("windows"))

    def test_just_kinds_require_the_shell_their_justfile_selects(self) -> None:
        for name in ("cpp-just", "rust-basic"):
            kind = generate.load_kind(name)
            self.assertIn("bash", kind.required_tools("linux"), name)
            self.assertIn("pwsh", kind.required_tools("windows"), name)
            self.assertNotIn("pwsh", kind.required_tools("linux"), name)

    def test_unknown_requires_key_is_an_error(self) -> None:
        templates = self.tmp / "templates"
        write_template(
            templates,
            "bad",
            {"description": "d", "requires": {"plan9": ["x"]}, "steps": [{"name": "s", "cmd": ["true"]}]},
            {},
        )
        with self.assertRaises(generate.GenerateError):
            generate.load_kind("bad", templates)

    @unittest.skipUnless(shutil.which("cmake"), "cmake is required")
    def test_output_path_with_spaces_survives(self) -> None:
        spaced = self.tmp / "dir with spaces" / "project"
        project = generate.generate("cpp-basic", spaced)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(run.run_step(project, project.steps()[0]))  # a real configure in the spaced path

    def test_typo_in_step_token_is_an_error(self) -> None:
        templates = self.tmp / "templates"
        write_template(
            templates,
            "typo",
            {
                "description": "typo",
                "steps": [{"name": "bad", "cmd": ["echo", "@BULID_DIR@"]}],
            },
            {"a.txt": "hello"},
        )
        project = generate.generate("typo", self.out, templates_dir=templates)
        with self.assertRaises(generate.GenerateError):
            project.steps()

    def test_crlf_templates_generate_lf_with_tokens_resolved(self) -> None:
        templates = self.tmp / "templates"
        write_template(
            templates,
            "crlf",
            {"description": "crlf", "steps": [{"name": "s", "cmd": ["echo"]}]},
            {"a.txt": "name=@PROJECT_NAME@\r\nline2\r\n"},
        )
        generate.generate("crlf", self.out, templates_dir=templates)
        data = (self.out / "a.txt").read_bytes()
        self.assertNotIn(b"\r", data)
        self.assertIn(b"name=infra_crlf\n", data)

    def test_include_chain_later_template_overrides(self) -> None:
        templates = self.tmp / "templates"
        write_template(templates, "_base", {}, {"f.txt": "base"})
        (templates / "_base" / "manifest.json").unlink()
        write_template(
            templates,
            "mid",
            {"description": "m", "includes": ["_base"], "steps": [{"name": "s", "cmd": ["x"]}]},
            {"g.txt": "mid"},
        )
        write_template(
            templates,
            "top",
            {"description": "t", "includes": ["mid"], "steps": [{"name": "s", "cmd": ["x"]}]},
            {"f.txt": "top"},
        )
        generate.generate("top", self.out, templates_dir=templates)
        self.assertEqual((self.out / "f.txt").read_text(encoding="utf-8"), "top")
        self.assertEqual((self.out / "g.txt").read_text(encoding="utf-8"), "mid")

    def test_warnings_error_overrides_library_source(self) -> None:
        generate.generate("cpp-warnings-error", self.out)
        self.assertIn("unused", (self.out / "src" / "lib.cpp").read_text(encoding="utf-8"))
        # inherited files are still present
        self.assertTrue((self.out / "CMakeLists.txt").is_file())

    def test_negative_kinds_expect_failure(self) -> None:
        in_source = generate.load_kind("cpp-in-source")
        self.assertEqual([s.expect for s in in_source.steps], ["fail"])
        warnings = generate.load_kind("cpp-warnings-error")
        self.assertEqual([s.expect for s in warnings.steps], ["pass", "fail"])

    def test_toolchain_var_changes_configure_command(self) -> None:
        project = generate.generate("cpp-toolchain", self.out, overrides={"TOOLCHAIN": "llvm"})
        configure = project.steps()[0]
        expected = "-DCMAKE_TOOLCHAIN_FILE=%s/cpp/cmake/toolchains/llvm.cmake" % generate.INFRA_DIR.as_posix()
        self.assertIn(expected, configure.cmd)
        self.assertFalse(configure.extra_args)

    def test_toolchain_default_is_gnu(self) -> None:
        project = generate.generate("cpp-toolchain", self.out)
        self.assertTrue(any(part.endswith("toolchains/gnu.cmake") for part in project.steps()[0].cmd[-1:]))

    def test_just_kind_imports_cmake_recipes_and_runs_them(self) -> None:
        project = generate.generate("cpp-just", self.out)
        justfile = (self.out / "justfile").read_text(encoding="utf-8")
        self.assertIn("import '%s/cpp/just/cmake.just'" % generate.INFRA_DIR.as_posix(), justfile)
        self.assertEqual([list(s.cmd) for s in project.steps()], [["just", "configure"], ["just", "build"], ["just", "test"]])

    def test_every_toolchain_file_exists(self) -> None:
        toolchains = generate.INFRA_DIR / "cpp" / "cmake" / "toolchains"
        for name in ("gnu", "llvm", "llvm_libcxx", "appleclang", "msvc"):
            self.assertTrue((toolchains / (name + ".cmake")).is_file(), name)

    def test_install_kind_has_consumer_project(self) -> None:
        generate.generate("cpp-install", self.out)
        self.assertTrue((self.out / "consumer" / "CMakeLists.txt").is_file())
        step_names = [s.name for s in generate.load_kind("cpp-install").steps]
        self.assertEqual(
            step_names,
            ["configure", "build", "install", "consumer configure", "consumer build", "consumer test"],
        )

    def test_cpm_kind_uses_cpm_module(self) -> None:
        generate.generate("cpp-cpm", self.out)
        text = (self.out / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("include(cpm)", text)

    def test_rust_project_imports_infra_just_files(self) -> None:
        generate.generate("rust-basic", self.out)
        text = (self.out / "justfile").read_text(encoding="utf-8")
        self.assertIn(generate.INFRA_DIR.as_posix() + "/rust/just/format.just", text)
        self.assertIn(generate.INFRA_DIR.as_posix() + "/rust/just/clippy.just", text)
        self.assertIn('name = "infra_rust_basic"', (self.out / "Cargo.toml").read_text(encoding="utf-8"))

    def test_rust_step_order(self) -> None:
        names = [s.name for s in generate.load_kind("rust-basic").steps]
        self.assertEqual(names, ["format", "format check", "lint", "test"])

    def test_docs_kind_checks_generated_index(self) -> None:
        project = generate.generate("docs", self.out)
        self.assertEqual([s.name for s in project.steps()], ["doxygen", "index exists"])
        self.assertTrue((self.out / "Doxyfile").is_file())

    def _cmake_text(self, kind: str, **overrides: str) -> str:
        generate.generate(kind, self.out, overrides=overrides or None)
        return (self.out / "CMakeLists.txt").read_text(encoding="utf-8")

    def test_cache_kind_enables_ccache_before_any_target(self) -> None:
        kind = generate.load_kind("cpp-cache")
        self.assertEqual(kind.skip_on, ("windows",))
        self.assertEqual(kind.required_tools("linux"), ("ccache",))
        text = self._cmake_text("cpp-cache")
        self.assertLess(text.index("pt_enable_cache()"), text.index("add_library(core"))

    def test_linker_kind_passes_the_linker_option_to_configure(self) -> None:
        kind = generate.load_kind("cpp-linker")
        self.assertEqual(kind.vars, {"LINKER": "DEFAULT", "LINK_FLAG": ""})
        project = generate.generate("cpp-linker", self.out, overrides={"LINKER": "LLD"})
        self.assertIn("-DPT_USER_LINKER_OPTION=LLD", project.steps()[0].cmd)
        text = (self.out / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertLess(text.index("add_executable(check"), text.index("pt_configure_linker(check)"))

    def test_linker_kind_with_no_flag_expects_empty_output(self) -> None:
        project = generate.generate("cpp-linker", self.out)
        self.assertEqual(project.steps()[1].expect_output, "")

    def test_ipo_kind_enables_ipo_before_any_target(self) -> None:
        self.assertEqual(generate.load_kind("cpp-ipo").vars, {"IPO_FLAG": "-flto"})
        text = self._cmake_text("cpp-ipo")
        self.assertLess(text.index("pt_enable_ipo()"), text.index("add_library(core"))


    def _bad_templates(self, manifests: dict) -> Path:
        templates = self.tmp / "templates"
        for name, manifest in manifests.items():
            write_template(templates, name, manifest, {"a.txt": "x"})
        return templates

    def test_invalid_expect_value_is_rejected(self) -> None:
        templates = self._bad_templates(
            {"bad": {"description": "d", "steps": [{"name": "s", "cmd": ["x"], "expect": "fial"}]}}
        )
        with self.assertRaises(generate.GenerateError):
            generate.load_kind("bad", templates)

    def test_unknown_preset_is_rejected(self) -> None:
        templates = self._bad_templates({"bad": {"description": "d", "steps": ["no-such-preset"]}})
        with self.assertRaises(generate.GenerateError):
            generate.load_kind("bad", templates)

    def test_missing_required_manifest_keys_are_rejected(self) -> None:
        templates = self._bad_templates(
            {
                "no-description": {"steps": [{"name": "s", "cmd": ["x"]}]},
                "no-cmd": {"description": "d", "steps": [{"name": "s"}]},
                "no-steps": {"description": "d"},
            }
        )
        for name in ("no-description", "no-cmd", "no-steps"):
            with self.subTest(manifest=name):
                with self.assertRaises(generate.GenerateError):
                    generate.load_kind(name, templates)

    def test_missing_include_is_rejected(self) -> None:
        templates = self._bad_templates(
            {"bad": {"description": "d", "includes": ["nope"], "steps": [{"name": "s", "cmd": ["x"]}]}}
        )
        with self.assertRaises(generate.GenerateError):
            generate.generate("bad", self.out, templates_dir=templates)

    def test_include_cycle_is_rejected(self) -> None:
        step = [{"name": "s", "cmd": ["x"]}]
        templates = self._bad_templates(
            {
                "a": {"description": "d", "includes": ["b"], "steps": step},
                "b": {"description": "d", "includes": ["a"], "steps": step},
            }
        )
        with self.assertRaises(generate.GenerateError):
            generate.generate("a", self.out, templates_dir=templates)


if __name__ == "__main__":
    unittest.main()
