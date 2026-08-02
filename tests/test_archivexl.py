from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cp77compat.archives import parse_archive_list_output
from cp77compat.archivexl import (
    build_archivexl_coverage,
    compare_references,
    compare_resource_references,
    parse_documents,
    resolve_archive_references,
)
from cp77compat.archivexl_payload_analysis import (
    compare_localization_entries,
    parse_localization_payload,
)
from cp77compat.models import Artifact, Reference


def artifact(path: Path, mod: str) -> Artifact:
    stat = path.stat()
    return Artifact(
        mod_name=mod,
        absolute_path=path,
        relative_path=r"archive\pc\mod\test.archive.xl",
        extension=".xl",
        size=stat.st_size,
        modified_ns=stat.st_mtime_ns,
    )


class ArchiveXLTests(unittest.TestCase):
    def test_parses_serialized_localization_entries(self) -> None:
        declaration = Reference(
            "archivexl",
            "localization.onscreens",
            r"mod\localization.json",
            "Example",
            "example.xl",
            line=4,
            details={"locale": "en-us"},
        )
        serialized = {
            "Data": {
                "RootChunk": {
                    "root": {
                        "Data": {
                            "entries": [
                                {
                                    "secondaryKey": "Example-Key",
                                    "primaryKey": "42",
                                    "femaleVariant": "Example text",
                                    "maleVariant": "",
                                }
                            ]
                        }
                    }
                }
            }
        }
        references = parse_localization_payload(
            declaration, serialized, "example.archive"
        )
        self.assertEqual(2, len(references))
        self.assertEqual(
            {"localization.entry.primary", "localization.entry.secondary"},
            {item.kind for item in references},
        )
        self.assertEqual(4, references[0].details["declaration_line"])
        self.assertEqual(4, references[0].line)
        self.assertEqual(0, references[0].details["entry_index"])

    def test_competing_localization_secondary_key_is_a_conflict(self) -> None:
        references = [
            Reference(
                "archivexl",
                "localization.entry.secondary",
                "en-us#Shared-Key",
                "A",
                "a.archive::a.json",
                details={
                    "secondary_key": "Shared-Key",
                    "female_variant": "Text A",
                    "male_variant": "",
                },
            ),
            Reference(
                "archivexl",
                "localization.entry.secondary",
                "en-us#Shared-Key",
                "B",
                "b.archive::b.json",
                details={
                    "secondary_key": "Shared-Key",
                    "female_variant": "Text B",
                    "male_variant": "",
                },
            ),
        ]
        findings = compare_localization_entries(references)
        self.assertEqual(1, len(findings))
        self.assertEqual("AXL-LOC-SECONDARY-CONFLICT", findings[0].rule_id)
        self.assertEqual("conflict", findings[0].severity)

    def test_extracts_all_observed_resource_operations(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "resources.xl"
            path.write_text(
                """resource:
  patch:
    mod\\patch.mesh:
      props: [appearances]
      targets:
        - !include player.ent
  copy:
    base\\original.mesh: [mod\\copied.mesh]
  link:
    mod\\source.mesh: [mod\\alias.mesh]
  scope:
    player.ent: [base\\player.ent]
  fix:
    base\\target.mesh:
      paths:
        base\\old.mesh: mod\\new.mesh
""",
                encoding="utf-8",
            )
            documents, references, findings = parse_documents(
                [artifact(path, "Example")]
            )
            self.assertEqual(
                {
                    "resource.copy",
                    "resource.fix",
                    "resource.link",
                    "resource.patch",
                    "resource.scope",
                },
                {reference.kind for reference in references},
            )
            patch = next(
                reference
                for reference in references
                if reference.kind == "resource.patch"
            )
            self.assertEqual("include", patch.details["target_tag"])
            self.assertEqual(["appearances"], patch.details["properties"])
            self.assertEqual(6, patch.line)
            coverage = build_archivexl_coverage(documents, references)
            self.assertEqual(5, len(coverage["resource_operations"]))
            self.assertTrue(
                all(
                    operation["status"] == "analyzed"
                    for operation in coverage["resource_operations"]
                )
            )
            self.assertFalse([item for item in findings if item.severity == "error"])

    def test_competing_resource_redirect_targets_are_a_conflict(self) -> None:
        references = [
            Reference(
                "archivexl",
                "resource.copy",
                "mod\\target.mesh",
                "A",
                "a.xl",
                details={"source": "base\\a.mesh"},
            ),
            Reference(
                "archivexl",
                "resource.link",
                "mod\\target.mesh",
                "B",
                "b.xl",
                details={"source": "base\\b.mesh"},
            ),
        ]
        findings = compare_resource_references(references)
        self.assertEqual("AXL-RESOURCE-TARGET-CONFLICT", findings[0].rule_id)
        self.assertEqual("conflict", findings[0].severity)

    def test_resource_patches_on_same_target_are_composable(self) -> None:
        references = [
            Reference(
                "archivexl",
                "resource.patch",
                "base\\target.mesh",
                "A",
                "a.xl",
                details={"source": "mod\\a.mesh"},
            ),
            Reference(
                "archivexl",
                "resource.patch",
                "base\\target.mesh",
                "B",
                "b.xl",
                details={"source": "mod\\b.mesh"},
            ),
        ]
        findings = compare_resource_references(references)
        self.assertEqual("AXL-RESOURCE-PATCH-COMPOSABLE", findings[0].rule_id)
        self.assertEqual("info", findings[0].severity)

    def test_contradictory_resource_fixes_are_a_conflict(self) -> None:
        references = [
            Reference(
                "archivexl",
                "resource.fix",
                "base\\target.mesh#paths#old",
                "A",
                "a.xl",
                details={"replacement": "mod\\a.mesh"},
            ),
            Reference(
                "archivexl",
                "resource.fix",
                "base\\target.mesh#paths#old",
                "B",
                "b.xl",
                details={"replacement": "mod\\b.mesh"},
            ),
        ]
        findings = compare_resource_references(references)
        self.assertEqual("AXL-RESOURCE-FIX-CONFLICT", findings[0].rule_id)

    def test_parses_json_and_extracts_localization_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test.xl"
            path.write_text(
                '{"localization":{"onscreens":{"en-us":"mod\\\\loc\\\\en-us.json"}}}',
                encoding="utf-8",
            )
            documents, references, findings = parse_documents([artifact(path, "Example")])
            self.assertEqual(1, len(documents))
            self.assertEqual("localization.onscreens", references[0].kind)
            self.assertFalse([item for item in findings if item.severity == "error"])

    def test_duplicate_yaml_key_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test.xl"
            path.write_text("streaming:\n  blocks: [a]\n  blocks: [b]\n", encoding="utf-8")
            _documents, _references, findings = parse_documents([artifact(path, "Example")])
            self.assertEqual("AXL-PARSE", findings[0].rule_id)

    def test_json_with_tab_indentation_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test.xl"
            path.write_text('{\n\t"streaming": {"blocks": ["mod/all.streamingblock"]}\n}', encoding="utf-8")
            documents, references, findings = parse_documents([artifact(path, "Example")])
            self.assertEqual(1, len(documents))
            self.assertEqual("streaming.block", references[0].kind)
            self.assertFalse([item for item in findings if item.severity == "error"])

    def test_yaml_trailing_tab_uses_lenient_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test.xl"
            path.write_text("streaming:\n  blocks:\n  - mod/all.streamingblock\t\n", encoding="utf-8")
            documents, _references, findings = parse_documents([artifact(path, "Example")])
            self.assertEqual(1, len(documents))
            self.assertIn("AXL-NONSTANDARD-TABS", [item.rule_id for item in findings])

    def test_conflicting_expected_nodes(self) -> None:
        refs = [
            Reference("archivexl", "streaming.sector", "base\\sector", "A", "a.xl", details={"expected_nodes": 10}),
            Reference("archivexl", "streaming.sector", "base\\sector", "B", "b.xl", details={"expected_nodes": 11}),
        ]
        findings = compare_references(refs)
        self.assertEqual("AXL-SECTOR-EXPECTED-NODES", findings[0].rule_id)
        self.assertEqual("conflict", findings[0].severity)

    def test_sector_and_node_deletion_use_structural_source_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "deletions.xl"
            path.write_text(
                """streaming:
  sectors:
    - path: base\\worlds\\example.streamingsector
      nodeDeletions:
        - index: 179
          type: worldEntityNode
""",
                encoding="utf-8",
            )
            _documents, references, findings = parse_documents(
                [artifact(path, "Example")]
            )
            lines = {item.kind: item.line for item in references}
            self.assertEqual(3, lines["streaming.sector"])
            self.assertEqual(5, lines["streaming.node_deletion"])
            self.assertFalse([item for item in findings if item.severity == "error"])

    def test_sector_reviews_are_aggregated_by_mod_set(self) -> None:
        refs = [
            Reference("archivexl", "streaming.sector", "sector_a", "A", "a.xl"),
            Reference("archivexl", "streaming.sector", "sector_a", "B", "b.xl"),
            Reference("archivexl", "streaming.sector", "sector_b", "A", "a.xl"),
            Reference("archivexl", "streaming.sector", "sector_b", "B", "b.xl"),
        ]
        findings = compare_references(refs)
        self.assertEqual(1, len(findings))
        self.assertEqual("2 overlapping streaming sectors", findings[0].summary)

    def test_archive_list_output(self) -> None:
        members = parse_archive_list_output("foo\\bar.json\nfoo\\mesh.mesh\n")
        self.assertEqual(["foo\\bar.json", "foo\\mesh.mesh"], [item.path for item in members])

    def test_loose_archive_mod_resource_resolves(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "en-us.json"
            path.write_text("{}", encoding="utf-8")
            loose = artifact(path, "Example")
            loose.relative_path = r"archive\pc\mod\example\localization\en-us.json"
            loose.extension = ".json"
            reference = Reference(
                "archivexl",
                "localization.onscreens",
                r"example\localization\en-us.json",
                "Example",
                "example.xl",
            )
            self.assertEqual([], resolve_archive_references([reference], [], [loose]))


if __name__ == "__main__":
    unittest.main()
