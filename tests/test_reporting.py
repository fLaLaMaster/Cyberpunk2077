from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from cp77compat.html_report import write_html_report
from cp77compat.models import Finding


class HtmlReportTests(unittest.TestCase):
    def test_html_report_is_self_contained_and_escapes_script_content(self) -> None:
        finding = Finding(
            rule_id="TEST-RULE",
            severity="warning",
            confidence="high",
            summary="Example </script><script>alert(1)</script>",
            explanation="Searchable explanation",
            participants=["Example Mod"],
            evidence=[{"identity": r"base\example.streamingsector"}],
        )
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "report.html"
            write_html_report(
                path,
                {
                    "mods": 1,
                    "artifacts": 2,
                    "archive_manifests": 0,
                    "archive_members": 0,
                    "archivexl_references": 1,
                    "tweakxl_references": 2,
                    "coverage": {
                        "archivexl": {
                            "documents": 1,
                            "sections": [
                                {
                                    "name": "resource",
                                    "documents": 1,
                                    "status": "partial",
                                    "note": "Example coverage",
                                }
                            ],
                            "resource_operations": [],
                            "player_operations": [
                                {
                                    "name": "player.bodyTypes",
                                    "status": "analyzed",
                                    "documents": 1,
                                    "registrations": 1,
                                    "unique_body_types": 1,
                                    "shared_body_types": 0,
                                    "note": "Example player coverage",
                                }
                            ],
                            "runtime_logs": [
                                {
                                    "name": "latest TweakXL log",
                                    "status": "analyzed",
                                    "lines": 10,
                                    "errors": 1,
                                    "warnings": 0,
                                    "events": 1,
                                    "correlated_events": 1,
                                    "static_confirmations": 1,
                                    "findings": 1,
                                    "log_path": "TweakXL-test.log",
                                    "note": "Test runtime coverage",
                                }
                            ],
                            "payloads": {
                                "localization": {
                                    "declarations": 1,
                                    "unique_archive_payloads": 1,
                                    "serialized": 1,
                                    "skipped_without_own_archive": 0,
                                    "failed": 0,
                                    "entry_references": 2,
                                    "extraction_cache_hits": 1,
                                    "serialization_cache_hits": 1,
                                }
                            },
                        }
                    },
                },
                [finding],
                {
                    "scanner_version": "test",
                    "generated_at": "2026-01-01T00:00:00+00:00",
                    "archive_scope": "none",
                },
            )
            html = path.read_text(encoding="utf-8")
            self.assertIn('id="search"', html)
            self.assertIn('id="severity"', html)
            self.assertIn('id="ecosystem"', html)
            self.assertIn('id="coverage"', html)
            self.assertIn("Payload inspection", html)
            self.assertIn("Player body types", html)
            self.assertIn("Runtime log correlation", html)
            self.assertNotIn("</script><script>alert(1)</script>", html)
            match = re.search(
                r'<script id="report-data" type="application/json">(.*?)</script>',
                html,
                re.DOTALL,
            )
            self.assertIsNotNone(match)
            payload = json.loads(match.group(1))
            self.assertEqual(finding.summary, payload["findings"][0]["summary"])


if __name__ == "__main__":
    unittest.main()
