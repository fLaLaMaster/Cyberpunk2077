from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cp77compat.models import Artifact
from cp77compat.shared_config import (
    analyze_config_documents,
    build_config_coverage,
    parse_config_documents,
)


def artifact(
    path: Path,
    mod: str,
    relative: str,
    state: str = "deployed",
) -> Artifact:
    stat = path.stat()
    return Artifact(
        mod_name=mod,
        absolute_path=path,
        relative_path=relative,
        extension=path.suffix.lower(),
        size=stat.st_size,
        modified_ns=stat.st_mtime_ns,
        deployed_state=state,
        deployed_source=mod if state == "deployed" else "Package A",
    )


class SharedConfigTests(unittest.TestCase):
    def test_parses_all_formats_and_reports_encoding_duplicates_and_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            json_path = root / "config.json"
            json_path.write_bytes(b'{"name":"caf\xe9","same":1,"same":2}')
            toml_path = root / "config.toml"
            toml_path.write_text("[section]\nvalue = 2\n", encoding="utf-8")
            ini_path = root / "config.ini"
            ini_path.write_text("[Section]\nValue=3\n", encoding="utf-8")
            xml_path = root / "config.xml"
            xml_path.write_text('<root value="4"><child /></root>', encoding="utf-8")
            invalid_path = root / "invalid.json"
            invalid_path.write_text("{}{}", encoding="utf-8")
            documents, references, findings = parse_config_documents([
                artifact(json_path, "JSON Mod", r"mods\config.json"),
                artifact(toml_path, "TOML Mod", r"mods\config.toml"),
                artifact(ini_path, "INI Mod", r"mods\config.ini"),
                artifact(xml_path, "XML Mod", r"mods\config.xml"),
                artifact(invalid_path, "Broken Mod", r"mods\invalid.json"),
            ])
            self.assertEqual(5, len(documents))
            self.assertTrue(all(reference.line is not None for reference in references))
            rules = {finding.rule_id for finding in findings}
            self.assertIn("CFG-NON-UTF8", rules)
            self.assertIn("CFG-DUPLICATE-KEY", rules)
            self.assertIn("CFG-PARSE-ERROR", rules)
            coverage = build_config_coverage(documents, references)
            by_format = {item["name"]: item for item in coverage["configuration_formats"]}
            self.assertEqual(2, by_format["JSON"]["documents"])
            self.assertEqual(1, by_format["JSON"]["failed"])
            self.assertEqual(1, by_format["TOML"]["parsed"])
            self.assertEqual(1, by_format["INI"]["parsed"])
            self.assertEqual(1, by_format["XML"]["parsed"])

    def test_compares_same_paths_and_inventories_shared_cet_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = []
            for name, content in (
                ("winner.json", '{"b":2,"a":1}'),
                ("same.json", '{"a":1,"b":2}'),
                ("different.json", '{"a":9}'),
                ("addon.json", '{"addon":true}'),
                ("competing.json", '{"a":9}'),
                ("loser.json", '{"a":10}'),
            ):
                path = root / name
                path.write_text(content, encoding="utf-8")
                paths.append(path)
            shared_path = r"bin\x64\plugins\cyber_engine_tweaks\mods\SharedRoot\config.json"
            addon_path = r"bin\x64\plugins\cyber_engine_tweaks\mods\SharedRoot\addon.json"
            artifacts = [
                artifact(paths[0], "Package A", shared_path),
                artifact(paths[1], "Package B", shared_path, "overridden"),
                artifact(paths[2], "Package C", r"mods\other.json"),
                artifact(paths[3], "Package D", addon_path),
                artifact(paths[4], "Package C", r"mods\competing.json"),
                artifact(paths[5], "Package E", r"mods\competing.json", "overridden"),
            ]
            documents, references, parse_findings = parse_config_documents(artifacts)
            self.assertEqual([], parse_findings)
            findings = analyze_config_documents(documents, references)
            rules = {finding.rule_id for finding in findings}
            self.assertIn("CFG-PATH-DUPLICATE", rules)
            self.assertIn("CFG-SCOPE-MULTI-PACKAGE", rules)
            self.assertIn("CFG-PATH-OVERRIDE", rules)
            coverage = build_config_coverage(documents, references)["ownership_operations"][0]
            self.assertEqual(2, coverage["shared_paths"])
            self.assertEqual(1, coverage["shared_scopes"])


if __name__ == "__main__":
    unittest.main()
