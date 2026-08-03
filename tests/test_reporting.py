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
            evidence=[{
                "identity": r"base\example.streamingsector",
                "sources": [{
                    "source_path": r"C:\Example Mod\r6\scripts\example.reds",
                    "line": 7,
                }],
            }],
            fingerprint="a" * 64,
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
                    "redscript_references": 3,
                    "cet_references": 4,
                    "config_references": 5,
                    "input_references": 6,
                    "native_references": 0,
                    "cross_ecosystem_findings": 1,
                    "finding_states": {"active": 1, "acknowledged": 0},
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
                            "streaming_operations": [
                                {
                                    "name": "streaming.sectors",
                                    "status": "analyzed",
                                    "documents": 1,
                                    "sectors": 1,
                                    "node_mutations": 2,
                                    "element_mutations": 1,
                                    "node_deletions": 3,
                                    "node_property_writes": 2,
                                    "element_property_writes": 1,
                                    "shared_mutation_nodes": 0,
                                    "note": "Example streaming coverage",
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
                        },
                        "redscript": {
                            "documents": 2,
                            "sections": [],
                            "annotation_operations": [
                                {
                                    "name": "REDscript annotations",
                                    "status": "analyzed",
                                    "documents": 2,
                                    "wrap_methods": 2,
                                    "replace_methods": 1,
                                    "add_methods": 3,
                                    "add_fields": 4,
                                    "shared_wrapper_signatures": 1,
                                    "shared_replacement_signatures": 1,
                                    "compatible_wrapper_chains": 1,
                                    "terminated_wrapper_chains": 0,
                                    "inactive_annotations": 0,
                                    "note": "Example REDscript coverage",
                                }
                            ],
                        },
                        "cet": {
                            "documents": 1,
                            "sections": [],
                            "registration_operations": [
                                {
                                    "name": "CET Lua API registrations",
                                    "status": "analyzed",
                                    "documents": 1,
                                    "mod_roots": 1,
                                    "entrypoints": 1,
                                    "events": 1,
                                    "hotkeys": 1,
                                    "inputs": 1,
                                    "requires": 0,
                                    "getmod_dependencies": 0,
                                    "observers": 1,
                                    "overrides": 1,
                                    "settings": 1,
                                    "global_writes": 2,
                                    "merged_roots": 1,
                                    "shared_globals": 1,
                                    "dynamic_globals": 1,
                                    "dynamic_calls": 0,
                                    "unresolved_modules": 0,
                                    "shared_hook_targets": 0,
                                    "inactive_references": 0,
                                    "note": "Example CET coverage",
                                }
                            ],
                        },
                        "cross-ecosystem": {
                            "documents": 2,
                            "sections": [],
                            "cross_ecosystem_operations": [
                                {
                                    "name": "CET hooks vs REDscript methods",
                                    "status": "partial",
                                    "documents": 2,
                                    "cet_hook_targets": 1,
                                    "redscript_method_targets": 1,
                                    "candidate_targets": 1,
                                    "matched_targets": 1,
                                    "cross_package_targets": 1,
                                    "same_package_targets": 0,
                                    "exact_signature_targets": 0,
                                    "ambiguous_targets": 1,
                                    "signature_mismatches": 0,
                                    "observer_targets": 1,
                                    "chained_override_targets": 0,
                                    "uncertain_override_targets": 0,
                                    "terminating_override_targets": 0,
                                    "dynamic_hooks": 0,
                                    "findings": 1,
                                    "note": "Example cross-ecosystem coverage",
                                }
                            ],
                        },
                        "config": {
                            "documents": 1,
                            "sections": [],
                            "configuration_formats": [
                                {
                                    "name": "JSON", "status": "analyzed",
                                    "documents": 1, "parsed": 1, "failed": 0,
                                    "entries": 2, "non_utf8": 0,
                                    "duplicate_keys": 0, "note": "Example config coverage",
                                }
                            ],
                            "ownership_operations": [
                                {
                                    "name": "configuration ownership", "status": "analyzed",
                                    "documents": 1, "active_documents": 1,
                                    "scopes": 1, "shared_scopes": 0, "shared_paths": 0,
                                    "references": 1, "note": "Example ownership coverage",
                                }
                            ],
                        },
                        "input": {
                            "documents": 1,
                            "sections": [],
                            "input_operations": [
                                {
                                    "name": "Input Loader mappings", "status": "analyzed",
                                    "documents": 1, "active_documents": 1,
                                    "references": 3, "top_level_nodes": 2,
                                    "mappings": 1, "contexts": 1, "action_policies": 0,
                                    "baseline_overwrites": 0, "baseline_appends": 1,
                                    "shared_append_nodes": 0, "competing_nodes": 0,
                                    "missing_targets": 0, "cache_mismatches": 0,
                                    "note": "Example input coverage",
                                }
                            ],
                        },
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
            self.assertIn('id="status"', html)
            self.assertIn('id="change"', html)
            self.assertIn('id="save-acknowledgements"', html)
            self.assertIn('id="coverage"', html)
            self.assertIn("Payload inspection", html)
            self.assertIn("Player body types", html)
            self.assertIn("World streaming operations", html)
            self.assertIn("REDscript annotation operations", html)
            self.assertIn("CET Lua registrations", html)
            self.assertIn("Cross-ecosystem operations", html)
            self.assertIn('XEC: "Cross-ecosystem"', html)
            self.assertIn("Configuration formats", html)
            self.assertIn("Configuration ownership", html)
            self.assertIn("Input Loader mappings", html)
            self.assertIn("Runtime log correlation", html)
            self.assertIn(".coverage-content, .coverage-group { min-width: 0; }", html)
            self.assertIn('controls.ecosystem.value = ""', html)
            self.assertIn("function readHash()", html)
            self.assertIn("function coverageCards", html)
            self.assertIn("function sourceFolderUrl", html)
            self.assertIn("function evidencePre", html)
            self.assertIn('link.className = "source-folder-link"', html)
            self.assertIn('return `file:///${drive[1]}/', html)
            self.assertIn('return `file://${host}/', html)
            self.assertIn("function acknowledgementsYaml", html)
            self.assertIn("showSaveFilePicker", html)
            self.assertIn("min(1740px", html)
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
