from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cp77compat.models import Artifact, Finding, Reference
from cp77compat.redscript_runtime import (
    analyze_redscript_runtime_log,
    parse_redscript_runtime_log,
)


class RedscriptRuntimeTests(unittest.TestCase):
    def test_parser_extracts_compiler_diagnostic_and_success_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "redscript_rCURRENT.log"
            path.write_text(
                """[INFO - Now] Compiling files in C:\\Game\\r6\\scripts:
Example\\one.reds
[WARN - Now] At C:\\Game\\r6\\scripts\\Example\\one.reds:4:1:
@replaceMethod(Target)
^^^
this method replacement overwrites a previous annotation targeting the same method, only one replacement per method can be active at a time

[INFO - Now] Compilation complete
[INFO - Now] Output successfully saved to C:\\Game\\r6\\cache\\final.redscripts.modded
""",
                encoding="utf-8",
            )
            events, stats = parse_redscript_runtime_log(path)
            self.assertEqual(1, len(events))
            self.assertEqual("RS-RUNTIME-METHOD-REPLACEMENT-OVERWRITE", events[0].rule_id)
            self.assertEqual(4, events[0].source_line)
            self.assertEqual(1, stats["compiled_files"])
            self.assertTrue(stats["output_saved"])

    def test_analyzer_correlates_deployed_line_and_static_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game = root / "game"
            logs = game / "r6" / "logs"
            logs.mkdir(parents=True)
            source = root / "one.reds"
            source.write_text("\n\n\n@replaceMethod(Target)\nfunc Go() -> Void {}\n", encoding="utf-8")
            deployed = game / "r6" / "scripts" / "Example" / "one.reds"
            deployed.parent.mkdir(parents=True)
            log = logs / "redscript_rCURRENT.log"
            log.write_text(
                f"""[WARN - Now] At {deployed}:4:1:
@replaceMethod(Target)
^^^
this method replacement overwrites a previous annotation targeting the same method, only one replacement per method can be active at a time

[INFO - Now] Compilation complete
""",
                encoding="utf-8",
            )
            stat = source.stat()
            artifact = Artifact(
                "Later Mod", source, r"r6\scripts\Example\one.reds", ".reds",
                stat.st_size, stat.st_mtime_ns, deployed_state="deployed",
            )
            reference = Reference(
                "redscript", "method.replace", "Target.Go()->Void", "Later Mod",
                str(source), 4, {"relative_path": artifact.relative_path},
            )
            static = Finding(
                "RS-METHOD-REPLACEMENT-CONFLICT", "conflict", "high", "conflict",
                "conflict", ["Earlier Mod", "Later Mod"],
                [{"identity": reference.identity}],
            )
            findings, coverage = analyze_redscript_runtime_log(
                game, [artifact], [reference], [static]
            )
            self.assertEqual(1, len(findings))
            self.assertEqual(["Earlier Mod", "Later Mod"], findings[0].participants)
            self.assertEqual(1, coverage["correlated_events"])
            self.assertEqual(1, coverage["static_confirmations"])
            self.assertEqual(reference.identity, findings[0].evidence[0]["identity"])


if __name__ == "__main__":
    unittest.main()

