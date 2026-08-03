from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cp77compat.cet import (
    analyze_cet_references,
    build_cet_coverage,
    parse_cet_documents,
)
from cp77compat.models import Artifact


def artifact(path: Path, root: str, mod: str = "Example", relative: str | None = None) -> Artifact:
    stat = path.stat()
    return Artifact(
        mod_name=mod,
        absolute_path=path,
        relative_path=(
            rf"bin\x64\plugins\cyber_engine_tweaks\mods\{root}\{relative or path.name}"
        ),
        extension=".lua",
        size=stat.st_size,
        modified_ns=stat.st_mtime_ns,
        deployed_state="deployed",
    )


class CETTests(unittest.TestCase):
    def test_extracts_lines_bindings_hooks_dependencies_and_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            init = root / "init.lua"
            module = root / "helper.lua"
            init.write_text(
                """-- registerHotkey('ignored', 'ignored', fn)
local helper = require("helper")
local dependency = GetMod('nativeSettings')
registerForEvent("onInit", function() end)
registerHotkey("valid.id", "Example", function() end)
registerInput('held_input', 'Held input', function(down) end)
ObserveAfter("PlayerPuppet", "OnGameAttached", function(self) end)
Override("Target", "DoThing", function(self, value, wrapped)
  return wrapped(value)
end)
nativeSettings.addSwitch('/example/enabled', 'Enabled', '', true, true, nil)
""",
                encoding="utf-8",
            )
            module.write_text("return {}\n", encoding="utf-8")
            documents, references, parse_findings = parse_cet_documents([
                artifact(init, "ExampleRoot"),
                artifact(module, "ExampleRoot", relative="helper.lua"),
            ])
            self.assertEqual([], parse_findings)
            findings = analyze_cet_references(documents, references)
            self.assertFalse(any(item.rule_id == "CET-MODULE-MISSING" for item in findings))
            by_kind = {item.kind: item for item in references if item.kind != "mod.entry"}
            self.assertEqual(4, by_kind["event.registration"].line)
            self.assertEqual("valid.id", by_kind["binding.hotkey"].details["binding_id"])
            self.assertEqual("PlayerPuppet.OnGameAttached", by_kind["hook.observe_after"].identity)
            self.assertTrue(by_kind["hook.override"].details["calls_wrapped"])
            self.assertEqual("/example/enabled", by_kind["settings.addSwitch"].identity)
            self.assertTrue(by_kind["module.require"].details["resolved"])
            coverage = build_cet_coverage(documents, references)
            operation = coverage["registration_operations"][0]
            self.assertEqual(1, operation["hotkeys"])
            self.assertEqual(1, operation["inputs"])
            self.assertEqual(2, operation["observers"] + operation["overrides"])

    def test_flags_event_and_binding_replacements_and_missing_modules(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "init.lua"
            path.write_text(
                """registerForEvent('onInit', function() end)
registerForEvent('onInit', function() end)
registerHotkey('same', 'First', function() end)
registerInput('same', 'Second', function(down) end)
require('missing/module')
""",
                encoding="utf-8",
            )
            documents, references, parse_findings = parse_cet_documents([artifact(path, "Root")])
            self.assertEqual([], parse_findings)
            rules = {item.rule_id for item in analyze_cet_references(documents, references)}
            self.assertIn("CET-EVENT-CALLBACK-REPLACED", rules)
            self.assertIn("CET-BINDING-ID-DUPLICATE", rules)
            self.assertIn("CET-MODULE-MISSING", rules)

    def test_classifies_cross_mod_observers_and_override_chains(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            artifacts = []
            for root, mod, callback in (
                ("A", "Mod A", "function(self, wrapped) return wrapped() end"),
                ("B", "Mod B", "function(self, wrapped) return wrapped() end"),
            ):
                path = Path(temp) / f"{root}.lua"
                path.write_text(
                    f"Observe('Target', 'Method', function(self) end)\nOverride('Target', 'Method', {callback})\n",
                    encoding="utf-8",
                )
                artifacts.append(artifact(path, root, mod, "init.lua"))
            documents, references, _ = parse_cet_documents(artifacts)
            rules = {item.rule_id for item in analyze_cet_references(documents, references)}
            self.assertIn("CET-OBSERVER-SHARED", rules)
            self.assertIn("CET-OVERRIDE-CHAIN", rules)

    def test_identical_terminating_overrides_and_shared_tabs_are_informational(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            artifacts = []
            for root, mod in (("A", "Mod A"), ("B", "Mod B")):
                path = Path(temp) / f"{root}.lua"
                path.write_text(
                    "Override('Target', 'Method', function(self) return true end)\n"
                    "nativeSettings.addTab('/Shared', 'Shared')\n",
                    encoding="utf-8",
                )
                artifacts.append(artifact(path, root, mod, "init.lua"))
            documents, references, _ = parse_cet_documents(artifacts)
            findings = analyze_cet_references(documents, references)
            by_rule = {item.rule_id: item for item in findings}
            self.assertEqual("info", by_rule["CET-OVERRIDE-CHAIN-DUPLICATE"].severity)
            self.assertEqual("info", by_rule["CET-SETTINGS-CONTAINER-SHARED"].severity)

    def test_extracts_literal_and_dynamic_tweakdb_mutations(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "init.lua"
            path.write_text(
                """registerForEvent('onInit', function()
  TweakDB:SetFlat('Items.Example.value', -0.01)
  TweakDB:SetFlatNoUpdate('Items.Example.tags', {'A', 'B'})
  TweakDB:CloneRecord(TweakDBID.new('Items.Clone'), 'Items.Source')
  TweakDB:CreateRecord('Items.Created', 'gamedataItem_Record')
  TweakDB:DeleteRecord('Items.Removed')
  TweakDB:SetFlat(prefix .. '.value', calculated)
end)
""",
                encoding="utf-8",
            )
            documents, references, parse_findings = parse_cet_documents([
                artifact(path, "Root")
            ])
            self.assertEqual([], parse_findings)
            analyze_cet_references(documents, references)
            by_kind = {
                item.kind: item
                for item in references
                if item.kind.startswith("tweakdb.") and "dynamic" not in item.kind
            }
            flat = by_kind["tweakdb.flat.set"]
            self.assertEqual("Items.Example.value", flat.identity)
            self.assertEqual(-0.01, flat.details["value"])
            self.assertEqual("-0.01", flat.details["value_key"])
            self.assertEqual(
                ["A", "B"], by_kind["tweakdb.flat.set-no-update"].details["value"]
            )
            clone = by_kind["tweakdb.record.clone"]
            self.assertEqual("Items.Clone", clone.identity)
            self.assertEqual("Items.Source", clone.details["source_record"])
            self.assertEqual(
                "gamedataItem_Record",
                by_kind["tweakdb.record.create"].details["record_type"],
            )
            self.assertEqual("Items.Removed", by_kind["tweakdb.record.delete"].identity)
            dynamic = [item for item in references if item.kind == "tweakdb.flat.dynamic"]
            self.assertEqual(1, len(dynamic))
            self.assertTrue(all(item.details["reachable"] for item in [*by_kind.values(), *dynamic]))

    def test_explicit_globals_collide_only_inside_one_merged_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            init = root / "init.lua"
            addon = root / "addon.lua"
            other = root / "other.lua"
            init.write_text(
                """local hidden = {}
function hidden.method() end
local localTable = { fakeGlobal = true }
Shared = {}
GlobalTable = { fakeMember = true }
function Shared.Run() end
_G.explicit = 1
_G['indexed'] = true
_G[dynamicName] = false
rawset(_ENV, 'rawName', {})
require('addon')
""",
                encoding="utf-8",
            )
            addon.write_text(
                "function Shared.Run() return true end\n_G.explicit = 2\n",
                encoding="utf-8",
            )
            other.write_text(
                "function Shared.Run() return false end\n_G.explicit = 3\n",
                encoding="utf-8",
            )
            documents, references, parse_findings = parse_cet_documents([
                artifact(init, "Merged", "Package A"),
                artifact(addon, "Merged", "Package B", "addon.lua"),
                artifact(other, "Separate", "Package C", "init.lua"),
            ])
            self.assertEqual([], parse_findings)
            findings = analyze_cet_references(documents, references)
            global_symbols = {
                item.details.get("symbol")
                for item in references
                if item.kind in {"global.assignment", "global.function"}
            }
            self.assertNotIn("hidden.method", global_symbols)
            self.assertNotIn("fakeGlobal", global_symbols)
            self.assertNotIn("fakeMember", global_symbols)
            self.assertTrue({"Shared", "GlobalTable", "Shared.Run", "explicit", "indexed", "rawName"} <= global_symbols)
            dynamic = [item for item in references if item.kind == "global.dynamic"]
            self.assertEqual(1, len(dynamic))
            shared = [item for item in findings if item.rule_id == "CET-GLOBAL-SYMBOL-SHARED"]
            self.assertEqual(1, len(shared))
            self.assertEqual("review", shared[0].severity)
            self.assertEqual(2, len(shared[0].evidence))
            coverage = build_cet_coverage(documents, references)["registration_operations"][0]
            self.assertEqual(1, coverage["merged_roots"])
            self.assertEqual(2, coverage["shared_globals"])
            self.assertEqual(1, coverage["dynamic_globals"])


if __name__ == "__main__":
    unittest.main()
