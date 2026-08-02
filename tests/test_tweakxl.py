from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cp77compat.models import Artifact, Reference
from cp77compat.tweakxl import compare_tweak_references, parse_tweak_documents
from cp77compat.tweakxl_dependencies import analyze_tweak_dependencies


def artifact(path: Path, mod: str, relative_path: str | None = None) -> Artifact:
    stat = path.stat()
    relative = relative_path or rf"r6\tweaks\{path.name}"
    return Artifact(
        mod_name=mod,
        absolute_path=path,
        relative_path=relative,
        extension=path.suffix.casefold(),
        size=stat.st_size,
        modified_ns=stat.st_mtime_ns,
        deployed_state="deployed",
    )


def reference(
    mod: str,
    operation: str,
    value_key: str,
    identity: str = "Items.Example.tags",
) -> Reference:
    kind = "assignment" if operation == "assign" else f"array.{operation}"
    return Reference(
        ecosystem="tweakxl",
        kind=kind,
        identity=identity,
        mod_name=mod,
        source_path=f"{mod}.yaml",
        details={"operation": operation, "value_key": value_key, "value": value_key},
    )


class TweakXLTests(unittest.TestCase):
    def test_parses_assignments_directives_and_custom_array_tags(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "example.yaml"
            path.write_text(
                """Items.Example:
  $type: gamedataItem_Record
  quality: Quality.Legendary
  tags:
    - !append-once Items.TagA
    - !remove Items.TagB
""",
                encoding="utf-8",
            )
            documents, references, findings = parse_tweak_documents([artifact(path, "Example")])
            self.assertEqual(1, len(documents))
            self.assertEqual(
                {"record.type", "assignment", "array.append-once", "array.remove"},
                {item.kind for item in references},
            )
            self.assertIn("Items.Example.quality", {item.identity for item in references})
            lines = {item.kind: item.line for item in references}
            self.assertEqual(2, lines["record.type"])
            self.assertEqual(3, lines["assignment"])
            self.assertEqual(5, lines["array.append-once"])
            self.assertEqual(6, lines["array.remove"])
            self.assertFalse([item for item in findings if item.severity == "error"])

    def test_duplicate_template_roots_are_preserved_and_expanded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "templates.yaml"
            path.write_text(
                """Items.$(item):
  $instances:
    - { item: First }
  blueprint: Items.BlueprintA
Items.$(item):
  $instances:
    - { item: Second }
  blueprint: Items.BlueprintB
""",
                encoding="utf-8",
            )
            _documents, references, findings = parse_tweak_documents([artifact(path, "Templates")])
            self.assertEqual(
                {"Items.First.blueprint", "Items.Second.blueprint"},
                {item.identity for item in references},
            )
            self.assertEqual(
                {"Items.First.blueprint": 4, "Items.Second.blueprint": 8},
                {item.identity: item.line for item in references},
            )
            self.assertFalse([item for item in findings if item.severity == "error"])

    def test_alias_references_keep_the_anchored_operation_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "aliases.yaml"
            path.write_text(
                """Items.First: &shared
  tags:
    - !append-once Items.SharedTag
Items.Second: *shared
""",
                encoding="utf-8",
            )
            _documents, references, findings = parse_tweak_documents(
                [artifact(path, "Aliases")]
            )
            self.assertEqual(
                {"Items.First.tags": 3, "Items.Second.tags": 3},
                {item.identity: item.line for item in references},
            )
            self.assertFalse([item for item in findings if item.severity == "error"])

    def test_yaml_outside_r6_tweaks_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "settings.yaml"
            path.write_text("Items.Example.value: 1\n", encoding="utf-8")
            documents, references, findings = parse_tweak_documents(
                [artifact(path, "Example", r"red4ext\plugins\example\settings.yaml")]
            )
            self.assertEqual(([], [], []), (documents, references, findings))

    def test_conflicting_assignments_are_reported(self) -> None:
        findings = compare_tweak_references(
            [reference("A", "assign", "one"), reference("B", "assign", "two")]
        )
        self.assertEqual("TXL-ASSIGNMENT-CONFLICT", findings[0].rule_id)
        self.assertEqual("conflict", findings[0].severity)

    def test_assignment_and_mutation_are_load_order_warning(self) -> None:
        findings = compare_tweak_references(
            [reference("A", "assign", "array"), reference("B", "append-once", "item")]
        )
        self.assertEqual(["TXL-ASSIGNMENT-MUTATION"], [item.rule_id for item in findings])

    def test_add_and_remove_same_value_are_reported(self) -> None:
        findings = compare_tweak_references(
            [reference("A", "append-once", "item"), reference("B", "remove", "item")]
        )
        self.assertEqual("TXL-ARRAY-ADD-REMOVE", findings[0].rule_id)
        self.assertEqual("conflict", findings[0].severity)

    def test_non_unique_duplicate_addition_is_a_warning(self) -> None:
        findings = compare_tweak_references(
            [reference("A", "append", "item"), reference("B", "append", "item")]
        )
        self.assertEqual("TXL-ARRAY-DUPLICATE", findings[0].rule_id)
        self.assertEqual("warning", findings[0].severity)

    def test_different_record_bases_are_a_conflict(self) -> None:
        references = [
            Reference(
                "tweakxl",
                "record.base",
                "Items.Example",
                "A",
                "A.yaml",
                details={"operation": "base", "value_key": "Items.BaseA"},
            ),
            Reference(
                "tweakxl",
                "record.base",
                "Items.Example",
                "B",
                "B.yaml",
                details={"operation": "base", "value_key": "Items.BaseB"},
            ),
        ]
        findings = compare_tweak_references(references)
        self.assertEqual("TXL-RECORD-BASE-CONFLICT", findings[0].rule_id)

    def test_append_once_from_multiple_mods_is_compatible(self) -> None:
        findings = compare_tweak_references(
            [reference("A", "append-once", "item"), reference("B", "append-once", "item")]
        )
        self.assertEqual(["TXL-ARRAY-COMPOSABLE"], [item.rule_id for item in findings])
        self.assertEqual("info", findings[0].severity)
        self.assertEqual(2, findings[0].evidence[0]["reference_count"])
        self.assertNotIn("references", findings[0].evidence[0])

    def test_dependency_analysis_resolves_vanilla_and_reports_missing_base(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            game = Path(temp)
            tweak = game / "tools" / "redmod" / "tweaks" / "base" / "items.tweak"
            tweak.parent.mkdir(parents=True)
            tweak.write_text(
                "package Items\n\nVanillaBase : Item\n{\n}\n",
                encoding="utf-8",
            )
            references = [
                Reference(
                    "tweakxl",
                    "record.base",
                    "Items.ValidClone",
                    "Valid",
                    "valid.yaml",
                    line=2,
                    details={"value": "Items.VanillaBase"},
                ),
                Reference(
                    "tweakxl",
                    "record.base",
                    "Items.BrokenClone",
                    "Broken",
                    "broken.yaml",
                    line=3,
                    details={"value": "Items.DoesNotExist"},
                ),
            ]

            findings, coverage = analyze_tweak_dependencies(references, game)

            missing = [item for item in findings if item.rule_id == "TXL-MISSING-BASE"]
            self.assertEqual(1, len(missing))
            self.assertEqual("Items.DoesNotExist", missing[0].evidence[0]["target"])
            base_stats = coverage["dependencies"][0]
            self.assertEqual(1, base_stats["vanilla"])
            self.assertEqual(1, base_stats["missing"])

    def test_dependency_analysis_detects_cycles_and_cross_mod_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            game = Path(temp)
            references = [
                Reference(
                    "tweakxl",
                    "record.base",
                    "Custom.A",
                    "Provider",
                    "provider.yaml",
                    line=1,
                    details={"value": "Custom.B"},
                ),
                Reference(
                    "tweakxl",
                    "record.base",
                    "Custom.B",
                    "Provider",
                    "provider.yaml",
                    line=3,
                    details={"value": "Custom.A"},
                ),
                Reference(
                    "tweakxl",
                    "assignment",
                    "Consumer.Record.foreignKey",
                    "Consumer",
                    "consumer.yaml",
                    line=5,
                    details={"value": "Custom.A", "operation": "assign"},
                ),
            ]

            findings, _coverage = analyze_tweak_dependencies(references, game)
            rules = {item.rule_id for item in findings}

            self.assertIn("TXL-BASE-CYCLE", rules)
            self.assertIn("TXL-CROSS-MOD-DEPENDENCY", rules)
            dependency = next(
                item for item in findings if item.rule_id == "TXL-CROSS-MOD-DEPENDENCY"
            )
            self.assertEqual(1, dependency.evidence[0]["record_references"])

    def test_dependency_analysis_reports_base_case_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            game = Path(temp)
            tweak = game / "tools" / "redmod" / "tweaks" / "base" / "items.tweak"
            tweak.parent.mkdir(parents=True)
            tweak.write_text(
                "package Items\n\nLegendaryBase : Item\n{\n}\n",
                encoding="utf-8",
            )
            references = [
                Reference(
                    "tweakxl",
                    "record.base",
                    "Items.Clone",
                    "Example",
                    "example.yaml",
                    line=2,
                    details={"value": "Items.legendaryBase"},
                )
            ]

            findings, coverage = analyze_tweak_dependencies(references, game)

            self.assertEqual(
                ["TXL-BASE-CASE-MISMATCH"],
                [item.rule_id for item in findings],
            )
            self.assertEqual(
                ["Items.LegendaryBase"],
                findings[0].evidence[0]["case_matches"],
            )
            self.assertEqual(1, coverage["dependencies"][0]["case_mismatch"])

    def test_dependency_analysis_reports_missing_explicit_foreign_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            references = [
                Reference(
                    "tweakxl",
                    "assignment",
                    "Items.Example.link",
                    "Example",
                    "example.yaml",
                    line=8,
                    details={
                        "value": 'TweakDBID("Custom.Missing")',
                        "operation": "assign",
                    },
                )
            ]

            findings, coverage = analyze_tweak_dependencies(references, Path(temp))

            self.assertEqual(
                ["TXL-MISSING-RECORD-REFERENCE"],
                [item.rule_id for item in findings],
            )
            self.assertEqual(1, coverage["dependencies"][1]["missing"])


if __name__ == "__main__":
    unittest.main()
