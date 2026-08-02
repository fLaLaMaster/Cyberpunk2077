from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cp77compat.models import Artifact, Finding, Reference
from cp77compat.tweakxl_runtime import (
    analyze_tweakxl_runtime_logs,
    parse_tweakxl_runtime_log,
)


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
    )


class TweakXLRuntimeTests(unittest.TestCase):
    def test_parser_tracks_reading_context_and_clears_it_before_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "TweakXL-2026-01-01-00-00-00.log"
            log.write_text(
                """[2026-01-01 00:00:00.000] [1] [info] Reading "Folder\\One.yaml"...
[2026-01-01 00:00:00.001] [1] [error] Items.New: Cannot clone Items.missing, the record doesn't exist.
[2026-01-01 00:00:00.002] [1] [info] Importing tweaks...
[2026-01-01 00:00:00.003] [1] [warning] Items.New.tags refers to a non-existent record or flat <TDBID:12345678:12>.
""",
                encoding="utf-8",
            )
            events, lines = parse_tweakxl_runtime_log(log)
            self.assertEqual(4, lines)
            self.assertEqual(2, len(events))
            self.assertEqual(r"Folder\One.yaml", events[0].tweak_path)
            self.assertIsNone(events[1].tweak_path)
            self.assertEqual("TXL-RUNTIME-CLONE-FAILED", events[0].rule_id)
            self.assertEqual("TXL-RUNTIME-DANGLING-REFERENCE", events[1].rule_id)

    def test_analyzer_attributes_sources_and_correlates_static_findings(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game = root / "game"
            logs = game / "red4ext" / "plugins" / "TweakXL"
            logs.mkdir(parents=True)
            log = logs / "TweakXL-2026-01-01-00-00-00.log"
            log.write_text(
                """[2026-01-01 00:00:00.000] [1] [info] Reading "One.yaml"...
[2026-01-01 00:00:00.001] [1] [error] Items.New: Cannot clone Items.missing, the record doesn't exist.
[2026-01-01 00:00:00.002] [1] [info] Reading "Two.yaml"...
[2026-01-01 00:00:00.003] [1] [error] Items.Other: Unknown property oldProperty.
[2026-01-01 00:00:00.004] [1] [error] Items.Other: Ambiguous definition. The value type cannot be determined.
[2026-01-01 00:00:00.005] [1] [info] Importing tweaks...
[2026-01-01 00:00:00.006] [1] [warning] Items.Shared.tags refers to a non-existent record or flat <TDBID:12345678:12>.
""",
                encoding="utf-8",
            )
            first = root / "One.yaml"
            second = root / "Two.yaml"
            first.write_text("Items.New:\n  $base: Items.missing\n", encoding="utf-8")
            second.write_text(
                "Items.Other:\n  oldProperty: true\n  tags: [Items.Shared]\n",
                encoding="utf-8",
            )
            artifacts = [
                artifact(first, "First Mod", r"r6\tweaks\One.yaml"),
                artifact(second, "Second Mod", r"r6\tweaks\Two.yaml"),
            ]
            references = [
                Reference(
                    "tweakxl", "record.base", "Items.New", "First Mod", str(first), 2,
                    {"operation": "base", "value_key": "Items.missing"},
                ),
                Reference(
                    "tweakxl", "assignment", "Items.Other.oldProperty", "Second Mod", str(second), 2,
                ),
                Reference(
                    "tweakxl", "assignment", "Items.Other.tags", "Second Mod", str(second), 3,
                ),
                Reference(
                    "tweakxl", "array.append-once", "Items.Shared.tags", "Third Mod", "third.yaml", 7,
                ),
            ]
            static = [
                Finding(
                    "TXL-BASE-CASE-MISMATCH", "error", "high", "case", "case",
                    ["First Mod"], [{"identity": "Items.New", "target": "Items.missing"}],
                )
            ]

            findings, coverage = analyze_tweakxl_runtime_logs(
                game, artifacts, references, static
            )

            self.assertEqual(4, len(findings))
            self.assertEqual(3, coverage["errors"])
            self.assertEqual(1, coverage["warnings"])
            self.assertEqual(4, coverage["correlated_events"])
            self.assertEqual(1, coverage["static_confirmations"])
            clone = next(
                item for item in findings if item.rule_id == "TXL-RUNTIME-CLONE-FAILED"
            )
            self.assertEqual(["First Mod"], clone.participants)
            self.assertEqual(2, clone.evidence[0]["line"])
            self.assertEqual(
                ["TXL-BASE-CASE-MISMATCH"], clone.evidence[0]["static_rules"]
            )
            warning = next(
                item
                for item in findings
                if item.rule_id == "TXL-RUNTIME-DANGLING-REFERENCE"
            )
            self.assertEqual(["Third Mod"], warning.participants)


if __name__ == "__main__":
    unittest.main()
