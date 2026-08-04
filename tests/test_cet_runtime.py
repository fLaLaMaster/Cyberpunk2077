from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cp77compat.cet_runtime import analyze_cet_runtime_logs
from cp77compat.models import Artifact, Reference


class CETRuntimeTests(unittest.TestCase):
    def test_ignores_events_from_older_appended_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            game = workspace / "game"
            cet = game / "bin" / "x64" / "plugins" / "cyber_engine_tweaks"
            mod_dir = cet / "mods" / "ExampleRoot"
            mod_dir.mkdir(parents=True)
            source = workspace / "init.lua"
            source.write_text("registerForEvent('onInit', function() end)\n", encoding="utf-8")
            stat = source.stat()
            artifact = Artifact(
                "Example Package", source,
                r"bin\x64\plugins\cyber_engine_tweaks\mods\ExampleRoot\init.lua",
                ".lua", stat.st_size, stat.st_mtime_ns, deployed_state="deployed",
            )
            (cet / "cyber_engine_tweaks.log").write_text(
                "[2026-01-01 10:00:00 UTC+00:00] [error] old framework error\n"
                "[2026-01-01 11:00:00 UTC+00:00] [info] CET version v1.test\n",
                encoding="utf-8",
            )
            (cet / "scripting.log").write_text(
                "[2026-01-01 10:00:00 UTC+00:00] [1] Mod ExampleRoot loaded! ('C:\\Game\\mods\\ExampleRoot')\n"
                "[2026-01-01 10:00:01 UTC+00:00] [1] Function Old in class Target does not exist\n"
                "[2026-01-01 11:00:00 UTC+00:00] [2] Mod ExampleRoot loaded! ('C:\\Game\\mods\\ExampleRoot')\n",
                encoding="utf-8",
            )
            (mod_dir / "ExampleRoot.log").write_text(
                "[2026-01-01 10:00:02 UTC+00:00] [1] init.lua:1: old failure\n",
                encoding="utf-8",
            )

            findings, coverage = analyze_cet_runtime_logs(
                game, [artifact], [], []
            )

            self.assertEqual([], findings)
            self.assertEqual(0, coverage["errors"])
            self.assertEqual("2026-01-01 11:00:00 UTC+00:00", coverage["session_timestamp"])

    def test_correlates_loaded_mod_lua_error_and_missing_hook(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            game = workspace / "game"
            cet = game / "bin" / "x64" / "plugins" / "cyber_engine_tweaks"
            mod_dir = cet / "mods" / "ExampleRoot"
            mod_dir.mkdir(parents=True)
            source = workspace / "init.lua"
            source.write_text("\n\nregisterForEvent('onInit', function() end)\n", encoding="utf-8")
            stat = source.stat()
            artifact = Artifact(
                "Example Package", source,
                r"bin\x64\plugins\cyber_engine_tweaks\mods\ExampleRoot\init.lua",
                ".lua", stat.st_size, stat.st_mtime_ns, deployed_state="deployed",
            )
            reference = Reference(
                "cet", "event.registration", "ExampleRoot:onInit", "Example Package",
                str(source), 3,
                {"mod_root": "ExampleRoot", "deployed_state": "deployed"},
            )
            (cet / "cyber_engine_tweaks.log").write_text(
                "[Now] [info] [fn] [1] CET version v1.test\n[Now] [info] [fn] [1] Game version test-game\n",
                encoding="utf-8",
            )
            (cet / "scripting.log").write_text(
                "[Now] [1] Mod ExampleRoot loaded! ('C:\\Game\\mods\\ExampleRoot')\n"
                "[Now] [1] Function Missing in class Target does not exist\n",
                encoding="utf-8",
            )
            (mod_dir / "ExampleRoot.log").write_text(
                "[Now] [1] init.lua:3: attempt to index a nil value\nstack traceback:\n\tinit.lua:3: in function <init.lua:2>\n",
                encoding="utf-8",
            )
            findings, coverage = analyze_cet_runtime_logs(
                game, [artifact], [reference], []
            )
            rules = {item.rule_id for item in findings}
            self.assertIn("CET-RUNTIME-LUA-ERROR", rules)
            self.assertIn("CET-RUNTIME-HOOK-TARGET-MISSING", rules)
            self.assertEqual(1, coverage["loaded_mods"])
            self.assertEqual(1, coverage["correlated_events"])
            self.assertEqual("v1.test", coverage["cet_version"])


if __name__ == "__main__":
    unittest.main()
