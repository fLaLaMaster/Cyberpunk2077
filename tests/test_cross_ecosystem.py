from __future__ import annotations

import unittest

from cp77compat.cross_ecosystem import analyze_cross_ecosystem_methods
from cp77compat.models import Reference


def cet_hook(
    kind: str,
    mod: str,
    method: str = "DoThing",
    calls_wrapped: bool | None = None,
    *,
    reachable: bool = True,
    deployed_state: str = "deployed",
) -> Reference:
    details = {
        "class": "Target",
        "method": method,
        "reachable": reachable,
        "deployed_state": deployed_state,
    }
    if kind == "hook.override":
        details["calls_wrapped"] = calls_wrapped
    return Reference(
        "cet", kind, f"Target.{method}", mod, f"{mod}.lua", 10, details
    )


def redscript_method(
    kind: str,
    mod: str,
    parameter_types: list[str] | None = None,
    *,
    condition_state: bool | None = True,
    deployed_state: str = "deployed",
) -> Reference:
    parameters = parameter_types if parameter_types is not None else ["Int32"]
    return Reference(
        "redscript",
        kind,
        f"Target.DoThing({','.join(parameters)})->Void",
        mod,
        f"{mod}.reds",
        20,
        {
            "target_class": "Target",
            "method_name": "DoThing",
            "parameter_types": parameters,
            "condition_state": condition_state,
            "deployed_state": deployed_state,
        },
    )


class CrossEcosystemTests(unittest.TestCase):
    def test_classifies_observers_and_override_chains(self) -> None:
        findings, coverage = analyze_cross_ecosystem_methods(
            [
                cet_hook("hook.observe_before", "CET Observer"),
                cet_hook("hook.override", "CET Override", calls_wrapped=True),
            ],
            [redscript_method("method.wrap", "REDscript Wrapper")],
        )
        by_rule = {finding.rule_id: finding for finding in findings}
        self.assertEqual(
            "info", by_rule["XEC-CET-OBSERVER-REDSCRIPT-METHOD"].severity
        )
        self.assertEqual(
            "info", by_rule["XEC-CET-OVERRIDE-REDSCRIPT-CHAIN"].severity
        )
        operation = coverage["cross_ecosystem_operations"][0]
        self.assertEqual(1, operation["candidate_targets"])
        self.assertEqual(1, operation["matched_targets"])
        self.assertEqual(1, operation["ambiguous_targets"])
        self.assertEqual(1, operation["observer_targets"])
        self.assertEqual(1, operation["chained_override_targets"])

    def test_distinguishes_unknown_and_terminating_overrides(self) -> None:
        unknown, _coverage = analyze_cross_ecosystem_methods(
            [cet_hook("hook.override", "Unknown CET", calls_wrapped=None)],
            [redscript_method("method.replace", "REDscript")],
        )
        self.assertEqual("XEC-CET-OVERRIDE-REDSCRIPT-REVIEW", unknown[0].rule_id)
        self.assertEqual("review", unknown[0].severity)

        terminating, _coverage = analyze_cross_ecosystem_methods(
            [cet_hook("hook.override", "Terminating CET", calls_wrapped=False)],
            [redscript_method("method.replace", "REDscript")],
        )
        self.assertEqual(
            "XEC-CET-OVERRIDE-TERMINATES-REDSCRIPT", terminating[0].rule_id
        )
        self.assertEqual("warning", terminating[0].severity)

    def test_matches_native_full_signature_and_rejects_other_overloads(self) -> None:
        findings, coverage = analyze_cross_ecosystem_methods(
            [
                cet_hook(
                    "hook.override",
                    "CET",
                    "DoThing;TargetInt32",
                    calls_wrapped=False,
                )
            ],
            [
                redscript_method("method.wrap", "Matching REDscript", ["Int32"]),
                redscript_method("method.wrap", "Other REDscript", ["String"]),
            ],
        )
        self.assertEqual(1, len(findings))
        self.assertEqual(
            ["CET", "Matching REDscript"], findings[0].participants
        )
        self.assertEqual("high", findings[0].confidence)
        references = findings[0].evidence[0]["references"]
        self.assertEqual(2, len(references))
        operation = coverage["cross_ecosystem_operations"][0]
        self.assertEqual(1, operation["exact_signature_targets"])
        self.assertEqual(0, operation["signature_mismatches"])

        no_match, no_match_coverage = analyze_cross_ecosystem_methods(
            [cet_hook("hook.observe_after", "CET", "DoThing;TargetBool")],
            [redscript_method("method.wrap", "REDscript", ["Int32"])],
        )
        self.assertEqual([], no_match)
        operation = no_match_coverage["cross_ecosystem_operations"][0]
        self.assertEqual(0, operation["matched_targets"])
        self.assertEqual(1, operation["signature_mismatches"])

    def test_ignores_inactive_and_same_package_pairs(self) -> None:
        findings, coverage = analyze_cross_ecosystem_methods(
            [
                cet_hook("hook.observe_before", "Inactive CET", reachable=False),
                cet_hook("hook.observe_before", "Overridden CET", deployed_state="overridden"),
                cet_hook("hook.observe_before", "Combined Mod"),
            ],
            [
                redscript_method("method.wrap", "Inactive REDscript", condition_state=False),
                redscript_method("method.wrap", "Combined Mod"),
            ],
        )
        self.assertEqual([], findings)
        operation = coverage["cross_ecosystem_operations"][0]
        self.assertEqual(1, operation["matched_targets"])
        self.assertEqual(1, operation["same_package_targets"])
        self.assertEqual(0, operation["cross_package_targets"])


if __name__ == "__main__":
    unittest.main()
