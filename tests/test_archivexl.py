from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cp77compat.archives import parse_archive_list_output
from cp77compat.archivexl import compare_references, parse_documents, resolve_archive_references
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
