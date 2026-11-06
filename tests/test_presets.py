"""Structure checks for cpp/presets/CMakePresets.json."""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRESETS = ROOT / "cpp" / "presets" / "CMakePresets.json"
TOOLCHAINS = ROOT / "cpp" / "cmake" / "toolchains"


def load():
    return json.loads(PRESETS.read_text(encoding="utf-8"))


def by_name(presets):
    return {p["name"]: p for p in presets}


def parents(preset):
    inherits = preset.get("inherits", [])
    return [inherits] if isinstance(inherits, str) else inherits


class PresetsFile(unittest.TestCase):
    def setUp(self):
        self.doc = load()
        self.configure = by_name(self.doc["configurePresets"])
        self.build = by_name(self.doc["buildPresets"])
        self.test = by_name(self.doc["testPresets"])

    def visible(self, presets):
        return {n: p for n, p in presets.items() if not p.get("hidden")}

    def test_names_are_unique_per_section(self):
        for section in ("configurePresets", "buildPresets", "testPresets"):
            names = [p["name"] for p in self.doc[section]]
            with self.subTest(section=section):
                self.assertEqual(len(names), len(set(names)))

    def test_inherited_presets_exist(self):
        for section, presets in (("configure", self.configure), ("build", self.build),
                                 ("test", self.test)):
            for name, preset in presets.items():
                for parent in parents(preset):
                    with self.subTest(section=section, preset=name):
                        self.assertIn(parent, presets)

    def test_every_toolchain_mixin_points_at_a_toolchain_file(self):
        mixins = {n: p for n, p in self.configure.items() if n.startswith("toolchain-")}
        self.assertTrue(mixins)
        for name, preset in mixins.items():
            path = preset["environment"]["PT_TOOLCHAIN_FILE"]
            prefix = "$env{PT_INFRA_DIR}/"
            with self.subTest(preset=name):
                self.assertTrue(path.startswith(prefix), path)
                self.assertTrue((ROOT / path[len(prefix):]).is_file(), path)

    def test_visible_configure_presets_get_the_infra_dir_and_a_host_condition(self):
        for name, preset in self.visible(self.configure).items():
            chain = parents(preset)
            with self.subTest(preset=name):
                self.assertIn("infra-dir", chain)
                self.assertEqual(sum(p.startswith("host-") for p in chain), 1)
                self.assertTrue(any(p.startswith("toolchain-") for p in chain))
                # vcpkg must come before the toolchain mixin so its CMAKE_TOOLCHAIN_FILE wins.
                if "vcpkg" in chain:
                    toolchain = next(p for p in chain if p.startswith("toolchain-"))
                    self.assertLess(chain.index("vcpkg"), chain.index(toolchain))

    def test_every_visible_configure_preset_has_matching_build_and_test_presets(self):
        configure = self.visible(self.configure)
        for section, presets in (("build", self.build), ("test", self.test)):
            visible = self.visible(presets)
            with self.subTest(section=section):
                self.assertEqual(set(visible), set(configure))
            for name, preset in visible.items():
                host = next(p for p in parents(configure[name]) if p.startswith("host-"))
                with self.subTest(section=section, preset=name):
                    self.assertEqual(preset["configurePreset"], name)
                    self.assertEqual(parents(preset), [host])


if __name__ == "__main__":
    unittest.main()
