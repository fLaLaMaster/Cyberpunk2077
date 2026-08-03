from __future__ import annotations

import unittest

from cp77compat.cross_ecosystem import (
    analyze_cross_ecosystem_methods,
    analyze_cross_ecosystem_tweakdb,
)
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


def cet_flat(mod: str, value: object, *, known: bool = True) -> Reference:
    return Reference(
        "cet", "tweakdb.flat.set", "Items.Example.value", mod, f"{mod}.lua", 30,
        {
            "target": "Items.Example.value",
            "value": value,
            "value_known": known,
            "value_key": str(value) if known else None,
            "reachable": True,
            "deployed_state": "deployed",
        },
    )


def tweak_flat(mod: str, value: object, *, array: bool = False) -> Reference:
    return Reference(
        "tweakxl", "array.append-once" if array else "assignment",
        "Items.Example.value", mod, f"{mod}.yaml", 40,
        {
            "operation": "append-once" if array else "assign",
            "value": value,
            "value_key": str(value),
        },
    )


def cet_record(kind: str, mod: str, value: str | None = None) -> Reference:
    details = {
        "target": "Items.NewRecord",
        "reachable": True,
        "deployed_state": "deployed",
    }
    if kind == "tweakdb.record.clone":
        details.update({"source_record": value, "source_known": value is not None})
    elif kind == "tweakdb.record.create":
        details.update({"record_type": value, "record_type_known": value is not None})
    return Reference(
        "cet", kind, "Items.NewRecord", mod, f"{mod}.lua", 50, details
    )


def tweak_record(kind: str, mod: str, value: str) -> Reference:
    return Reference(
        "tweakxl", kind, "Items.NewRecord", mod, f"{mod}.yaml", 60,
        {"operation": kind.rsplit(".", 1)[-1], "value": value, "value_key": f'"{value}"'},
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

    def test_compares_cet_runtime_flat_writes_with_tweakxl(self) -> None:
        different, operation = analyze_cross_ecosystem_tweakdb(
            [cet_flat("CET", -0.01)], [tweak_flat("TweakXL", 1)]
        )
        self.assertEqual("XEC-CET-TWEAKDB-FLAT-RUNTIME-OVERRIDE", different[0].rule_id)
        self.assertEqual("warning", different[0].severity)
        self.assertEqual(1, operation["cross_package_targets"])
        self.assertEqual(1, operation["runtime_override_targets"])

        equivalent, operation = analyze_cross_ecosystem_tweakdb(
            [cet_flat("CET", 1)], [tweak_flat("TweakXL", 1)]
        )
        self.assertEqual("XEC-CET-TWEAKDB-FLAT-EQUIVALENT", equivalent[0].rule_id)
        self.assertEqual("info", equivalent[0].severity)
        self.assertEqual(1, operation["equivalent_targets"])

    def test_classifies_array_dynamic_and_same_package_tweakdb_targets(self) -> None:
        array_findings, _operation = analyze_cross_ecosystem_tweakdb(
            [cet_flat("CET", ["A"])], [tweak_flat("TweakXL", "A", array=True)]
        )
        self.assertEqual("XEC-CET-TWEAKDB-ARRAY-RUNTIME-OVERRIDE", array_findings[0].rule_id)

        dynamic, operation = analyze_cross_ecosystem_tweakdb(
            [cet_flat("CET", None, known=False)], [tweak_flat("TweakXL", 1)]
        )
        self.assertEqual("XEC-CET-TWEAKDB-FLAT-DYNAMIC-VALUE", dynamic[0].rule_id)
        self.assertEqual("partial", operation["status"])

        same_package, operation = analyze_cross_ecosystem_tweakdb(
            [cet_flat("Combined", 2)], [tweak_flat("Combined", 1)]
        )
        self.assertEqual([], same_package)
        self.assertEqual(1, operation["same_package_targets"])

    def test_compares_record_operations_with_matching_tweakxl_directives(self) -> None:
        findings, operation = analyze_cross_ecosystem_tweakdb(
            [
                cet_record("tweakdb.record.clone", "CET", "Items.Base"),
                cet_record("tweakdb.record.create", "CET", "gamedataItem_Record"),
            ],
            [
                tweak_record("record.base", "TweakXL", "Items.Base"),
                tweak_record("record.type", "TweakXL", "gamedataOther_Record"),
            ],
        )
        by_rule = {item.rule_id: item for item in findings}
        self.assertIn("XEC-CET-TWEAKDB-RECORD-EQUIVALENT", by_rule)
        self.assertIn("XEC-CET-TWEAKDB-RECORD-RUNTIME-OVERRIDE", by_rule)
        self.assertEqual(1, operation["record_candidates"])

        deleted, _operation = analyze_cross_ecosystem_tweakdb(
            [cet_record("tweakdb.record.delete", "CET")],
            [Reference(
                "tweakxl", "assignment", "Items.NewRecord.value", "TweakXL",
                "TweakXL.yaml", 70, {"operation": "assign", "value": 1, "value_key": "1"},
            )],
        )
        self.assertEqual("XEC-CET-TWEAKDB-RECORD-DELETE", deleted[0].rule_id)


if __name__ == "__main__":
    unittest.main()
