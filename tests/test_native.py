from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from cp77compat.models import Artifact
from cp77compat.native import (
    analyze_native_binaries,
    parse_native_binaries,
    parse_pe_imports,
)


def write_pe(path: Path, imports: list[str]) -> None:
    """Write a minimal PE32+ image with a valid import-name table."""
    data = bytearray(0x800)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 0x84, 0x8664, 1, 0, 0, 0, 0xF0, 0x2022)
    optional = 0x98
    struct.pack_into("<H", data, optional, 0x20B)
    struct.pack_into("<I", data, optional + 108, 16)
    struct.pack_into("<II", data, optional + 112 + 8, 0x1000, (len(imports) + 1) * 20)
    section = optional + 0xF0
    data[section:section + 8] = b".rdata\0\0"
    struct.pack_into("<IIII", data, section + 8, 0x600, 0x1000, 0x600, 0x200)
    name_offset = 0x200 + (len(imports) + 1) * 20
    for index, name in enumerate(imports):
        struct.pack_into(
            "<IIIII", data, 0x200 + index * 20, 0, 0, 0,
            0x1000 + name_offset - 0x200, 0,
        )
        encoded = name.encode("ascii") + b"\0"
        data[name_offset:name_offset + len(encoded)] = encoded
        name_offset += len(encoded)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def add_delay_import(path: Path, name: str) -> None:
    data = bytearray(path.read_bytes())
    optional = 0x98
    struct.pack_into("<II", data, optional + 112 + 13 * 8, 0x1300, 64)
    struct.pack_into("<IIIIIIII", data, 0x500, 1, 0x1340, 0, 0, 0, 0, 0, 0)
    encoded = name.encode("ascii") + b"\0"
    data[0x540:0x540 + len(encoded)] = encoded
    path.write_bytes(data)


def artifact(path: Path, mod: str, relative_path: str) -> Artifact:
    stat = path.stat()
    return Artifact(
        mod_name=mod,
        absolute_path=path,
        relative_path=relative_path,
        extension=path.suffix.casefold(),
        size=stat.st_size,
        modified_ns=stat.st_mtime_ns,
        deployed_state="deployed",
        deployed_source=mod,
    )


class NativeAnalyzerTests(unittest.TestCase):
    def test_parses_pe_import_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "plugin.dll"
            write_pe(path, ["KERNEL32.dll", "helper.dll"])
            add_delay_import(path, "delayed.dll")
            self.assertEqual(
                ["delayed.dll", "helper.dll", "KERNEL32.dll"],
                parse_pe_imports(path),
            )

    def test_correlates_plugin_loads_companions_and_missing_imports(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            staging = root / "staging"
            game = root / "game"
            inputs: list[Artifact] = []
            definitions = [
                (
                    "Test Mod",
                    r"red4ext\plugins\Test\Test.dll",
                    ["KERNEL32.dll", "MMDevAPI.dll", "missing.dll"],
                ),
                ("Radio Mod", r"red4ext\plugins\Radio\Radio.dll", ["fmod.dll"]),
                ("Radio Mod", r"red4ext\plugins\Radio\fmod.dll", ["KERNEL32.dll"]),
            ]
            for mod, relative, imports in definitions:
                source = staging / mod / Path(relative.replace("\\", "/"))
                deployed = game / Path(relative.replace("\\", "/"))
                write_pe(source, imports)
                deployed.parent.mkdir(parents=True, exist_ok=True)
                deployed.write_bytes(source.read_bytes())
                inputs.append(artifact(source, mod, relative))

            log = game / "red4ext" / "logs" / "red4ext-2026-01-01-00-00-00.log"
            log.parent.mkdir(parents=True)
            test_path = game / "red4ext" / "plugins" / "Test" / "Test.dll"
            fmod_path = game / "red4ext" / "plugins" / "Radio" / "fmod.dll"
            radio_path = game / "red4ext" / "plugins" / "Radio" / "Radio.dll"
            log.write_text(
                "[info] RED4ext (v1.30.0) is initializing\n"
                "[info] Product version: 2.31\n"
                "[info] File version: 3.0.80.51928\n"
                f"[info] Loading plugin from '{test_path}'\n"
                "[info] Test (version: 1.0.0, author(s): Tester) has been loaded\n"
                f"[info] Loading plugin from '{fmod_path}'\n"
                f"[info] Loading plugin from '{radio_path}'\n"
                "[info] Radio (version: 2.0.0, author(s): Tester) has been loaded\n",
                encoding="utf-8",
            )
            cet_log = game / "bin" / "x64" / "plugins" / "cyber_engine_tweaks" / "cyber_engine_tweaks.log"
            cet_log.parent.mkdir(parents=True)
            cet_log.write_text(
                "CET version 1.37.1\nGame version 3.0.80.51928\n",
                encoding="utf-8",
            )

            binaries, references = parse_native_binaries(inputs, game)
            findings, coverage = analyze_native_binaries(binaries, references, game)
            self.assertTrue(all(reference.line == 1 for reference in references))
            self.assertIn("NATIVE-DEPENDENCY-MISSING", {item.rule_id for item in findings})
            self.assertNotIn("NATIVE-PLUGIN-NOT-OBSERVED", {item.rule_id for item in findings})
            states = {item.artifact.absolute_path.name: item.runtime_state for item in binaries}
            self.assertEqual("loaded", states["Test.dll"])
            self.assertEqual("loaded", states["Radio.dll"])
            self.assertEqual("companion", states["fmod.dll"])
            operation = coverage["native_operations"][0]
            self.assertEqual(2, operation["loaded_plugins"])
            self.assertEqual(1, operation["companion_libraries"])
            self.assertEqual(1, operation["missing_imports"])

    def test_reports_different_providers_for_same_binary_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game = root / "game"
            relative = r"red4ext\plugins\Shared\Shared.dll"
            inputs = []
            for mod, imports in (("First", ["KERNEL32.dll"]), ("Second", ["USER32.dll"])):
                source = root / mod / "Shared.dll"
                write_pe(source, imports)
                inputs.append(artifact(source, mod, relative))
            deployed = game / Path(relative.replace("\\", "/"))
            deployed.parent.mkdir(parents=True)
            deployed.write_bytes(inputs[-1].absolute_path.read_bytes())
            inputs[0].deployed_state = "overridden"

            binaries, references = parse_native_binaries(inputs, game)
            findings, _ = analyze_native_binaries(binaries, references, game)
            override = next(item for item in findings if item.rule_id == "NATIVE-BINARY-OVERRIDE")
            self.assertEqual({"First", "Second"}, {item["mod_name"] for item in override.evidence})


if __name__ == "__main__":
    unittest.main()
