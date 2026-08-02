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
