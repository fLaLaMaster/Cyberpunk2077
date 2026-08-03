from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cp77compat.input_mapping import analyze_input_documents, parse_input_documents
from cp77compat.models import Artifact


def artifact(path: Path, mod: str) -> Artifact:
    stat = path.stat()
    return Artifact(
        mod_name=mod,
        absolute_path=path,
        relative_path=rf"r6\input\{path.name}",
        extension=".xml",
        size=stat.st_size,
        modified_ns=stat.st_mtime_ns,
        deployed_state="deployed",
        deployed_source=mod,
    )


def write_game_inputs(root: Path, contexts: str, mappings: str) -> None:
    (root / "r6" / "config").mkdir(parents=True)
    (root / "r6" / "cache").mkdir(parents=True)
    (root / "r6" / "config" / "inputContexts.xml").write_text(
        contexts, encoding="utf-8"
    )
    (root / "r6" / "config" / "inputUserMappings.xml").write_text(
        mappings, encoding="utf-8"
    )


class InputMappingTests(unittest.TestCase):
    def test_models_append_conflicts_baseline_overwrite_and_missing_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game = root / "game"
            write_game_inputs(
                game,
                '<bindings><context name="Base"><action name="Vanilla" map="VanillaMap" /></context></bindings>',
                '<bindings><mapping name="VanillaMap" type="Button"><button id="IK_V" /></mapping></bindings>',
            )
            first = root / "First.xml"
            first.write_text(
                """<bindings>
  <context name="Base" append="true">
    <action name="Shared" map="FirstMap" />
  </context>
  <mapping name="FirstMap" type="Button"><button id="IK_F1" /></mapping>
  <mapping name="VanillaMap" type="Button"><button id="IK_F2" /></mapping>
</bindings>""",
                encoding="utf-8",
            )
            second = root / "Second.xml"
            second.write_text(
                """<bindings>
  <context name="Base" append="true">
    <action name="Shared" map="SecondMap" />
    <action name="Broken" map="MissingMap" />
  </context>
  <mapping name="SecondMap" type="Button"><button id="IK_F3" /></mapping>
</bindings>""",
                encoding="utf-8",
            )
            (game / "r6" / "cache" / "inputContexts.xml").write_text(
                '<bindings><context name="Base"><action name="Vanilla" map="VanillaMap" /><action name="Shared" map="FirstMap" /><action name="Shared" map="SecondMap" /><action name="Broken" map="MissingMap" /></context></bindings>',
                encoding="utf-8",
            )
            (game / "r6" / "cache" / "inputUserMappings.xml").write_text(
                '<bindings><mapping name="VanillaMap" type="Button"><button id="IK_F2" /></mapping><mapping name="FirstMap" type="Button"><button id="IK_F1" /></mapping><mapping name="SecondMap" type="Button"><button id="IK_F3" /></mapping></bindings>',
                encoding="utf-8",
            )
            log = game / "red4ext" / "logs" / "input_loader.log"
            log.parent.mkdir(parents=True)
            log.write_text(
                "[info] Loading document: C:\\Game\\r6/input/First.xml\n"
                "[info] Loading document: C:\\Game\\r6/input/Second.xml\n",
                encoding="utf-8",
            )

            documents, references = parse_input_documents(
                [artifact(first, "First Mod"), artifact(second, "Second Mod")]
            )
            self.assertEqual(2, len(documents))
            self.assertTrue(all(reference.line is not None for reference in references))
            findings, coverage = analyze_input_documents(
                documents, references, game
            )
            rules = {finding.rule_id for finding in findings}
            self.assertIn("INPUT-NODE-APPEND-COMPOSABLE", rules)
            self.assertIn("INPUT-APPEND-CHILD-CONFLICT", rules)
            self.assertIn("INPUT-BASELINE-OVERWRITE", rules)
            self.assertIn("INPUT-TARGET-MISSING", rules)
            self.assertNotIn("INPUT-CACHE-MISMATCH", rules)
            operation = coverage["input_operations"][0]
            self.assertEqual(1, operation["baseline_overwrites"])
            self.assertEqual(1, operation["shared_append_nodes"])
            self.assertEqual(1, operation["missing_targets"])
            self.assertEqual("analyzed", coverage["runtime_logs"][0]["status"])

    def test_detects_competing_whole_nodes_and_cache_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game = root / "game"
            write_game_inputs(game, "<bindings />", "<bindings />")
            (game / "r6" / "cache" / "inputContexts.xml").write_text(
                "<bindings />", encoding="utf-8"
            )
            (game / "r6" / "cache" / "inputUserMappings.xml").write_text(
                "<bindings />", encoding="utf-8"
            )
            paths = []
            for number, key in enumerate(("IK_A", "IK_B"), 1):
                path = root / f"Mod{number}.xml"
                extra = (
                    '<mapping name="Unique" type="Button"><button id="IK_U" /></mapping>'
                    if number == 1 else ""
                )
                path.write_text(
                    f'<bindings><mapping name="Shared" type="Button"><button id="{key}" /></mapping>{extra}</bindings>',
                    encoding="utf-8",
                )
                paths.append(path)
            documents, references = parse_input_documents([
                artifact(paths[0], "Mod A"), artifact(paths[1], "Mod B")
            ])
            findings, coverage = analyze_input_documents(documents, references, game)
            rules = {finding.rule_id for finding in findings}
            self.assertIn("INPUT-NODE-OVERWRITE", rules)
            self.assertIn("INPUT-CACHE-MISMATCH", rules)
            self.assertEqual(1, coverage["input_operations"][0]["competing_nodes"])
            self.assertEqual(1, coverage["input_operations"][0]["cache_mismatches"])

    def test_rejects_non_bindings_root_without_losing_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "Bad.xml"
            path.write_text("<wrong />", encoding="utf-8")
            documents, references = parse_input_documents([artifact(path, "Broken")])
            self.assertEqual(1, len(documents))
            self.assertFalse(documents[0].parsed)
            self.assertEqual([], references)
            self.assertEqual(1, documents[0].error_line)


if __name__ == "__main__":
    unittest.main()
