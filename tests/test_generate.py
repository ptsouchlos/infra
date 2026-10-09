from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import generate


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

    def test_output_path_with_spaces_survives(self) -> None:
        spaced = self.tmp / "dir with spaces" / "project"
        project = generate.generate("cpp-basic", spaced)
        configure = project.steps()[0]
        self.assertIn(spaced.resolve().as_posix(), configure.cmd)
        self.assertIn(
            spaced.resolve().as_posix() + "/build",
            configure.cmd,
        )

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

    def test_sanitizers_skipped_on_windows(self) -> None:
        self.assertIn("windows", generate.load_kind("cpp-sanitizers").skip_on)

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
