from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cp77compat.archivexl_runtime import (
    analyze_archivexl_runtime_logs,
    find_latest_archivexl_log_session,
    parse_archivexl_runtime_logs,
)
from cp77compat.models import Artifact, Finding, Reference


def artifact(path: Path, mod: str, relative_path: str) -> Artifact:
    stat = path.stat()
    return Artifact(
        mod_name=mod,
        absolute_path=path,
        relative_path=relative_path,
        extension=".xl",
        size=stat.st_size,
        modified_ns=stat.st_mtime_ns,
        deployed_state="deployed",
    )


class ArchiveXLRuntimeTests(unittest.TestCase):
    def test_parser_extracts_customization_type_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ArchiveXL-2026-01-01-00-00-00.log"
            path.write_text(
                '[2026-01-01 00:00:00.000] [1] [warning] '
                '[CharacterCustomization] Option "eyebrows" can\'t be merged: '
                'expected gameuiSwitcherInfo, got gameuiMorphInfo.\n',
                encoding="utf-8",
            )
            events, lines = parse_archivexl_runtime_logs([path])
            self.assertEqual(1, lines)
            self.assertEqual(1, len(events))
            self.assertEqual(
                "AXL-RUNTIME-CUSTOMIZATION-TYPE-MISMATCH",
                events[0].rule_id,
            )
            self.assertEqual("eyebrows", events[0].identity)
            self.assertEqual("gameuiSwitcherInfo", events[0].details["expected_type"])
            self.assertEqual("gameuiMorphInfo", events[0].details["actual_type"])

    def test_parser_pairs_journal_issue_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ArchiveXL-2026-01-01-00-00-00.log"
            path.write_text(
                """[2026-01-01 00:00:00.000] [1] [warning] [Journal] contacts/judy: Cannot modify entry, type mismatch.
[2026-01-01 00:00:00.001] [1] [warning] [Journal] Journal entries merged with issues.
""",
                encoding="utf-8",
            )
            events, lines = parse_archivexl_runtime_logs([path])
            self.assertEqual(2, lines)
            self.assertEqual(2, len(events))
            self.assertTrue(
                all(event.rule_id == "AXL-RUNTIME-JOURNAL-MERGE-ISSUE" for event in events)
            )
            self.assertEqual("contacts/judy", events[0].identity)
            self.assertTrue(events[1].details["consequence"])

    def test_latest_session_includes_rotated_chunks_in_chronological_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            game = Path(temp)
            logs = game / "red4ext" / "plugins" / "ArchiveXL"
            logs.mkdir(parents=True)
            (logs / "ArchiveXL-2025-12-31-23-59-59.log").write_text("old\n")
            base = logs / "ArchiveXL-2026-01-01-00-00-00.log"
            rotated = logs / "ArchiveXL-2026-01-01-00-00-00.1.log"
            base.write_text("new\n")
            rotated.write_text("older chunk\n")

            session, paths = find_latest_archivexl_log_session(game)

            self.assertEqual("2026-01-01-00-00-00", session)
            self.assertEqual([rotated, base], paths)

    def test_parser_pairs_summary_and_streaming_consequence_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rotated = root / "ArchiveXL-2026-01-01-00-00-00.1.log"
            base = root / "ArchiveXL-2026-01-01-00-00-00.log"
            rotated.write_text(
                """[2026-01-01 00:00:00.000] [1] [warning] [QuestPhase] Phase "mod\\quest\\missing.quest" doesn't exist. Skipped.
[2026-01-01 00:00:00.001] [1] [error] [Localization] Resource "mod\\localization\\en-us.json" failed to load.
""",
                encoding="utf-8",
            )
            base.write_text(
                """[2026-01-01 00:00:00.002] [1] [warning] [Localization] Translations merged with issues.
[2026-01-01 00:00:00.003] [2] [info] [WorldStreaming] Applying changes from "World.xl"...
[2026-01-01 00:00:00.004] [2] [error] [WorldStreaming] World.xl: The target sector has 6 node(s), but the mod expects 4.
[2026-01-01 00:00:00.005] [2] [warning] [WorldStreaming] No patches have been applied to "base\\world.streamingsector".
""",
                encoding="utf-8",
            )

            events, lines = parse_archivexl_runtime_logs([rotated, base])

            self.assertEqual(6, lines)
            self.assertEqual(5, len(events))
            self.assertEqual(events[1].identity, events[2].identity)
            self.assertTrue(events[2].details["consequence"])
            self.assertEqual("base\\world.streamingsector", events[3].identity)
            self.assertEqual(events[3].identity, events[4].identity)
            self.assertEqual(6, events[3].details["actual_nodes"])
            self.assertTrue(events[4].details["consequence"])

    def test_analyzer_attributes_semantic_and_source_text_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game = root / "game"
            logs = game / "red4ext" / "plugins" / "ArchiveXL"
            logs.mkdir(parents=True)
            log = logs / "ArchiveXL-2026-01-01-00-00-00.log"
            log.write_text(
                """[2026-01-01 00:00:00.000] [1] [warning] [QuestPhase] Phase "mod\\quest\\missing.quest" doesn't exist. Skipped.
[2026-01-01 00:00:00.001] [1] [error] [Localization] Resource "mod\\localization\\en-us.json" failed to load.
[2026-01-01 00:00:00.002] [2] [info] [WorldStreaming] Applying changes from "World.xl"...
[2026-01-01 00:00:00.003] [2] [error] [WorldStreaming] World.xl: The target sector has 6 node(s), but the mod expects 4.
[2026-01-01 00:00:00.004] [2] [warning] [WorldStreaming] No patches have been applied to "base\\world.streamingsector".
""",
                encoding="utf-8",
            )
            quest = root / "Quest.xl"
            localization = root / "Localization.xl"
            world = root / "World.xl"
            quest.write_text(
                "quest:\n  phases:\n    - parent: mod\\quest\\missing.quest\n",
                encoding="utf-8",
            )
            localization.write_text(
                "localization:\n  onscreens:\n    en-us: mod\\localization\\en-us.json\n",
                encoding="utf-8",
            )
            world.write_text(
                "streaming:\n  sectors:\n    - path: base\\world.streamingsector\n      expectedNodes: 4\n",
                encoding="utf-8",
            )
            artifacts = [
                artifact(quest, "Quest Mod", r"archive\pc\mod\Quest.xl"),
                artifact(localization, "Localization Mod", r"archive\pc\mod\Localization.xl"),
                artifact(world, "World Mod", r"archive\pc\mod\World.xl"),
            ]
            references = [
                Reference(
                    "archivexl", "quest.parent",
                    r"mod\quest\missing.quest", "Quest Mod", str(quest), 3,
                    {"phase": r"mod\quest\child.questphase"},
                ),
                Reference(
                    "archivexl", "localization.onscreens",
                    r"mod\localization\en-us.json", "Localization Mod",
                    str(localization), 3,
                ),
                Reference(
                    "archivexl", "streaming.sector",
                    r"base\world.streamingsector", "World Mod", str(world), 3,
                    {"expected_nodes": 4},
                ),
            ]
            static = [
                Finding(
                    "AXL-QUEST-PARENT-NOT-FOUND", "warning", "high", "quest", "quest",
                    ["Quest Mod"], [{"identity": r"mod\quest\missing.quest"}],
                ),
                Finding(
                    "AXL-SECTOR-EXPECTED-NODES", "conflict", "high", "sector", "sector",
                    ["World Mod"], [{"identity": r"base\world.streamingsector"}],
                )
            ]

            findings, coverage = analyze_archivexl_runtime_logs(
                game, artifacts, references, static
            )

            self.assertEqual(3, len(findings))
            self.assertEqual(2, coverage["errors"])
            self.assertEqual(2, coverage["warnings"])
            self.assertEqual(4, coverage["correlated_events"])
            self.assertEqual(3, coverage["static_confirmations"])
            quest_finding = next(
                item for item in findings if item.rule_id == "AXL-RUNTIME-QUEST-PHASE-MISSING"
            )
            self.assertEqual(["Quest Mod"], quest_finding.participants)
            self.assertEqual(3, quest_finding.evidence[0]["line"])
            streaming = next(
                item
                for item in findings
                if item.rule_id == "AXL-RUNTIME-STREAMING-EXPECTED-NODES"
            )
            self.assertEqual(["World Mod"], streaming.participants)
            self.assertEqual(3, streaming.evidence[0]["line"])


if __name__ == "__main__":
    unittest.main()
