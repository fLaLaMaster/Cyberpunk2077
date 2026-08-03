from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Iterable

from .models import Finding, Reference


_CET_HOOK_KINDS = {
    "hook.observe_before",
    "hook.observe_after",
    "hook.override",
}
_CET_OBSERVER_KINDS = {"hook.observe_before", "hook.observe_after"}
_REDSCRIPT_METHOD_KINDS = {"method.wrap", "method.replace"}
_CET_TWEAKDB_FLAT_KINDS = {
    "tweakdb.flat.set",
    "tweakdb.flat.set-no-update",
}
_CET_TWEAKDB_RECORD_KINDS = {
    "tweakdb.record.clone",
    "tweakdb.record.create",
    "tweakdb.record.delete",
}
_TWEAKXL_FLAT_KINDS = {"assignment"}
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_REFERENCE_WRAPPER = re.compile(r"\b(?:ref|wref|script_ref)<([^<>]+)>", re.IGNORECASE)


def _cet_active(reference: Reference) -> bool:
    return (
        reference.kind in _CET_HOOK_KINDS
        and reference.details.get("deployed_state") != "overridden"
        and bool(reference.details.get("reachable"))
    )


def _redscript_active(reference: Reference) -> bool:
    return (
        reference.kind in _REDSCRIPT_METHOD_KINDS
        and reference.details.get("deployed_state") != "overridden"
        and reference.details.get("condition_state") is not False
    )


def _name(value: Any) -> str:
    return str(value or "").strip().casefold()


def _method_parts(reference: Reference) -> tuple[str, str | None]:
    method = str(reference.details.get("method") or "").strip()
    short, separator, suffix = method.partition(";")
    return short.casefold(), suffix if separator and suffix else None


def _signature_token(value: str) -> str:
    previous = None
    unwrapped = value
    while previous != unwrapped:
        previous = unwrapped
        unwrapped = _REFERENCE_WRAPPER.sub(r"\1", unwrapped)
    return _NON_ALNUM.sub("", unwrapped.casefold())


def _redscript_signature_variants(reference: Reference) -> set[str]:
    target = _signature_token(str(reference.details.get("target_class") or ""))
    parameters = reference.details.get("parameter_types")
    if not isinstance(parameters, list):
        return set()
    suffix = "".join(_signature_token(str(parameter)) for parameter in parameters)
    # NativeDB full names include the instance type for instance methods but
    # omit it for static methods. Accept both encodings while retaining the
    # exact declared parameter sequence.
    return {suffix, target + suffix}


def _full_signature_matches(cet: Reference, redscript: Reference) -> bool:
    _short, suffix = _method_parts(cet)
    if suffix is None:
        return True
    return _signature_token(suffix) in _redscript_signature_variants(redscript)


def _reference_key(reference: Reference) -> tuple[str, str, int, str, str]:
    return (
        reference.mod_name.casefold(),
        reference.source_path.casefold(),
        reference.line or 0,
        reference.kind,
        reference.identity.casefold(),
    )


def _unique(references: Iterable[Reference]) -> list[Reference]:
    result: list[Reference] = []
    seen: set[tuple[str, str, int, str, str]] = set()
    for reference in references:
        key = _reference_key(reference)
        if key not in seen:
            seen.add(key)
            result.append(reference)
    return sorted(result, key=_reference_key)


def _cross_package(cet: Iterable[Reference], redscript: Iterable[Reference]) -> bool:
    return any(
        left.mod_name.casefold() != right.mod_name.casefold()
        for left in cet
        for right in redscript
    )


def _evidence(
    target: tuple[str, str],
    cet: list[Reference],
    redscript: list[Reference],
) -> dict[str, Any]:
    precise = all(_method_parts(reference)[1] is not None for reference in cet)
    display_class = str(
        (cet[0].details.get("class") if cet else None)
        or (redscript[0].details.get("target_class") if redscript else target[0])
    )
    display_method = str(
        (cet[0].details.get("method") if cet else None)
        or (redscript[0].details.get("method_name") if redscript else target[1])
    ).split(";", 1)[0]
    return {
        "identity": f"{display_class}.{display_method}",
        "match_precision": "full-signature" if precise else "class-and-method",
        "cet_operations": sorted({reference.kind for reference in cet}),
        "redscript_operations": sorted({reference.kind for reference in redscript}),
        "references": [
            reference.to_dict() for reference in [*_unique(cet), *_unique(redscript)]
        ],
    }


def _aggregate(
    buckets: dict[tuple[str, str, str, tuple[str, ...]], list[dict[str, Any]]]
) -> list[Finding]:
    explanations = {
        "XEC-CET-OBSERVER-REDSCRIPT-METHOD": (
            "CET guarantees that Observe, ObserveBefore, and ObserveAfter callbacks remain "
            "additive around the final scripted method. The REDscript wrapper or replacement "
            "therefore remains reachable; this records shared behavioral ownership for review "
            "of side effects rather than reporting a conflict."
        ),
        "XEC-CET-OVERRIDE-REDSCRIPT-CHAIN": (
            "Every matched CET override visibly invokes its final wrapped/next callback. The "
            "compiled REDscript wrapper or replacement remains in the execution chain, so the "
            "two ecosystems compose at the hook level."
        ),
        "XEC-CET-OVERRIDE-REDSCRIPT-REVIEW": (
            "A CET override and a REDscript wrapper or replacement target the same method, but "
            "the Lua callback is indirect or dynamic enough that the scanner cannot prove it "
            "invokes CET's wrapped/next callback. The REDscript behavior may be bypassed."
        ),
        "XEC-CET-OVERRIDE-TERMINATES-REDSCRIPT": (
            "A CET override visibly omits its wrapped/next callback while another package "
            "modifies the same method through REDscript. When the CET override runs, it replaces "
            "the compiled method and can prevent the REDscript behavior from executing."
        ),
    }
    labels = {
        "XEC-CET-OBSERVER-REDSCRIPT-METHOD": "additive CET/REDscript method overlap",
        "XEC-CET-OVERRIDE-REDSCRIPT-CHAIN": "compatible CET/REDscript override chain",
        "XEC-CET-OVERRIDE-REDSCRIPT-REVIEW": "uncertain CET/REDscript override chain",
        "XEC-CET-OVERRIDE-TERMINATES-REDSCRIPT": "terminating CET/REDscript override overlap",
    }
    findings: list[Finding] = []
    for (rule_id, severity, confidence, participants), evidence in sorted(
        buckets.items(), key=lambda item: item[0]
    ):
        count = len(evidence)
        label = labels[rule_id]
        findings.append(
            Finding(
                rule_id=rule_id,
                severity=severity,
                confidence=confidence,
                summary=f"{count} {label}" + ("s" if count != 1 else ""),
                explanation=explanations[rule_id],
                participants=list(participants),
                evidence=sorted(evidence, key=lambda item: item["identity"].casefold()),
            )
        )
    return findings


def analyze_cross_ecosystem_methods(
    cet_references: Iterable[Reference],
    redscript_references: Iterable[Reference],
) -> tuple[list[Finding], dict[str, Any]]:
    """Compare active CET hooks with active REDscript method annotations."""
    cet_reference_list = list(cet_references)
    redscript_reference_list = list(redscript_references)
    cet = [reference for reference in cet_reference_list if _cet_active(reference)]
    redscript = [
        reference for reference in redscript_reference_list
        if _redscript_active(reference)
    ]
    cet_by_target: dict[tuple[str, str], list[Reference]] = defaultdict(list)
    redscript_by_target: dict[tuple[str, str], list[Reference]] = defaultdict(list)
    for reference in cet:
        method, _signature = _method_parts(reference)
        target = (_name(reference.details.get("class")), method)
        if all(target):
            cet_by_target[target].append(reference)
    for reference in redscript:
        target = (
            _name(reference.details.get("target_class")),
            _name(reference.details.get("method_name")),
        )
        if all(target):
            redscript_by_target[target].append(reference)

    candidate_targets = sorted(set(cet_by_target) & set(redscript_by_target))
    buckets: dict[
        tuple[str, str, str, tuple[str, ...]], list[dict[str, Any]]
    ] = defaultdict(list)
    matched_targets = 0
    exact_targets = 0
    ambiguous_targets = 0
    signature_mismatches = 0
    same_package_targets = 0
    observer_targets = 0
    chained_override_targets = 0
    uncertain_override_targets = 0
    terminating_override_targets = 0

    for target in candidate_targets:
        red_group = redscript_by_target[target]
        matched_by_cet: dict[tuple[str, str, int, str, str], list[Reference]] = {}
        matched_red: list[Reference] = []
        for hook in cet_by_target[target]:
            compatible = [
                method for method in red_group if _full_signature_matches(hook, method)
            ]
            if compatible:
                matched_by_cet[_reference_key(hook)] = compatible
                matched_red.extend(compatible)
            elif _method_parts(hook)[1] is not None:
                signature_mismatches += 1
        matched_cet = [
            hook
            for hook in cet_by_target[target]
            if _reference_key(hook) in matched_by_cet
        ]
        matched_red = _unique(matched_red)
        if not matched_cet or not matched_red:
            continue
        matched_targets += 1
        if all(_method_parts(reference)[1] is not None for reference in matched_cet):
            exact_targets += 1
        else:
            ambiguous_targets += 1
        if not _cross_package(matched_cet, matched_red):
            same_package_targets += 1
            continue

        observers = [
            reference for reference in matched_cet
            if reference.kind in _CET_OBSERVER_KINDS
        ]
        overrides = [
            reference for reference in matched_cet if reference.kind == "hook.override"
        ]
        for rule_id, severity, confidence, hook_group in (
            (
                "XEC-CET-OBSERVER-REDSCRIPT-METHOD",
                "info",
                "high" if observers and all(_method_parts(item)[1] for item in observers) else "medium",
                observers,
            ),
        ):
            if not hook_group:
                continue
            observer_targets += 1
            participants = tuple(sorted(
                {item.mod_name for item in [*hook_group, *matched_red]},
                key=str.casefold,
            ))
            buckets[(rule_id, severity, confidence, participants)].append(
                _evidence(target, hook_group, matched_red)
            )

        if overrides:
            wrapped_states = {item.details.get("calls_wrapped") for item in overrides}
            precise = all(_method_parts(item)[1] is not None for item in overrides)
            if False in wrapped_states:
                rule_id = "XEC-CET-OVERRIDE-TERMINATES-REDSCRIPT"
                severity = "warning"
                confidence = "high" if precise else "medium"
                terminating_override_targets += 1
            elif None in wrapped_states:
                rule_id = "XEC-CET-OVERRIDE-REDSCRIPT-REVIEW"
                severity = "review"
                confidence = "medium"
                uncertain_override_targets += 1
            else:
                rule_id = "XEC-CET-OVERRIDE-REDSCRIPT-CHAIN"
                severity = "info"
                confidence = "high" if precise else "medium"
                chained_override_targets += 1
            participants = tuple(sorted(
                {item.mod_name for item in [*overrides, *matched_red]},
                key=str.casefold,
            ))
            buckets[(rule_id, severity, confidence, participants)].append(
                _evidence(target, overrides, matched_red)
            )

    findings = _aggregate(buckets)
    dynamic_hooks = sum(
        reference.kind == "hook.dynamic"
        and reference.details.get("deployed_state") != "overridden"
        and bool(reference.details.get("reachable"))
        for reference in cet_reference_list
    )
    documents = len({reference.source_path.casefold() for reference in [*cet, *redscript]})
    operation = {
        "name": "CET hooks vs REDscript methods",
        "status": "partial" if dynamic_hooks or ambiguous_targets else "analyzed",
        "documents": documents,
        "cet_hook_targets": len(cet_by_target),
        "redscript_method_targets": len(redscript_by_target),
        "candidate_targets": len(candidate_targets),
        "matched_targets": matched_targets,
        "exact_signature_targets": exact_targets,
        "ambiguous_targets": ambiguous_targets,
        "signature_mismatches": signature_mismatches,
        "same_package_targets": same_package_targets,
        "cross_package_targets": matched_targets - same_package_targets,
        "observer_targets": observer_targets,
        "chained_override_targets": chained_override_targets,
        "uncertain_override_targets": uncertain_override_targets,
        "terminating_override_targets": terminating_override_targets,
        "dynamic_hooks": dynamic_hooks,
        "findings": len(findings),
        "note": (
            "Literal active CET hooks are matched to active REDscript wrappers and "
            "replacements by class, method, and NativeDB full signature when supplied. "
            "Short CET names remain overload-ambiguous; dynamic hook targets are counted "
            "but intentionally not guessed."
        ),
    }
    coverage = {
        "documents": documents,
        "sections": [
            {
                "name": "CET to REDscript method hooks",
                "documents": documents,
                "status": operation["status"],
                "note": operation["note"],
            }
        ],
        "cross_ecosystem_operations": [operation],
    }
    return findings, coverage


def _cet_tweakdb_active(reference: Reference) -> bool:
    return (
        reference.kind in _CET_TWEAKDB_FLAT_KINDS | _CET_TWEAKDB_RECORD_KINDS
        and reference.details.get("deployed_state") != "overridden"
        and bool(reference.details.get("reachable"))
    )


def _tweakdb_evidence(
    identity: str, cet: Iterable[Reference], tweakxl: Iterable[Reference]
) -> dict[str, Any]:
    cet_list = _unique(cet)
    tweak_list = _unique(tweakxl)
    return {
        "identity": identity,
        "cet_operations": sorted({item.kind for item in cet_list}),
        "tweakxl_operations": sorted({str(item.details.get("operation", item.kind)) for item in tweak_list}),
        "references": [item.to_dict() for item in [*cet_list, *tweak_list]],
    }


def _tweakdb_findings(
    buckets: dict[tuple[str, str, str, tuple[str, ...]], list[dict[str, Any]]]
) -> list[Finding]:
    labels = {
        "XEC-CET-TWEAKDB-FLAT-EQUIVALENT": "equivalent CET/TweakXL flat write",
        "XEC-CET-TWEAKDB-FLAT-RUNTIME-OVERRIDE": "CET runtime flat override",
        "XEC-CET-TWEAKDB-FLAT-DYNAMIC-VALUE": "CET runtime flat write requiring review",
        "XEC-CET-TWEAKDB-ARRAY-RUNTIME-OVERRIDE": "CET runtime array override",
        "XEC-CET-TWEAKDB-RECORD-EQUIVALENT": "equivalent CET/TweakXL record definition",
        "XEC-CET-TWEAKDB-RECORD-RUNTIME-OVERRIDE": "CET/TweakXL record overlap",
        "XEC-CET-TWEAKDB-RECORD-DYNAMIC-VALUE": "CET/TweakXL record overlap requiring review",
        "XEC-CET-TWEAKDB-RECORD-DELETE": "CET record deletion overlapping TweakXL",
    }
    explanations = {
        "XEC-CET-TWEAKDB-FLAT-EQUIVALENT": "The literal CET runtime write and the TweakXL assignment serialize to the same value. This is redundant shared ownership, not a behavioral conflict.",
        "XEC-CET-TWEAKDB-FLAT-RUNTIME-OVERRIDE": "TweakXL initializes this flat, then active CET code writes a different literal value at runtime. The CET value can replace the TweakXL result after initialization.",
        "XEC-CET-TWEAKDB-FLAT-DYNAMIC-VALUE": "TweakXL initializes this flat and active CET code writes it at runtime, but the Lua value is computed dynamically. The final behavior needs manual inspection.",
        "XEC-CET-TWEAKDB-ARRAY-RUNTIME-OVERRIDE": "TweakXL composes tagged mutations for this array, while active CET code replaces the complete flat at runtime. The CET write can discard the composed TweakXL array.",
        "XEC-CET-TWEAKDB-RECORD-EQUIVALENT": "CET and TweakXL declare the same record target with the same statically visible base or type.",
        "XEC-CET-TWEAKDB-RECORD-RUNTIME-OVERRIDE": "CET creates or clones a record that TweakXL also defines with a different statically visible base or type. Record creation can fail or produce different data depending on initialization order.",
        "XEC-CET-TWEAKDB-RECORD-DYNAMIC-VALUE": "CET creates or clones a record also defined by TweakXL, but one side is not statically comparable. Initialization order and the computed source/type need review.",
        "XEC-CET-TWEAKDB-RECORD-DELETE": "Active CET code deletes a record that TweakXL defines or mutates. The TweakXL data can become unavailable after the CET callback runs.",
    }
    findings: list[Finding] = []
    for (rule, severity, confidence, participants), evidence in sorted(
        buckets.items(), key=lambda item: item[0]
    ):
        count = len(evidence)
        findings.append(Finding(
            rule_id=rule,
            severity=severity,
            confidence=confidence,
            summary=f"{count} {labels[rule]}" + ("s" if count != 1 else ""),
            explanation=explanations[rule],
            participants=list(participants),
            evidence=sorted(evidence, key=lambda item: item["identity"].casefold()),
        ))
    return findings


def analyze_cross_ecosystem_tweakdb(
    cet_references: Iterable[Reference],
    tweakxl_references: Iterable[Reference],
) -> tuple[list[Finding], dict[str, Any]]:
    """Compare active literal CET TweakDB mutations with TweakXL operations."""
    cet_reference_list = list(cet_references)
    tweak_reference_list = list(tweakxl_references)
    cet = [item for item in cet_reference_list if _cet_tweakdb_active(item)]
    tweak = [
        item for item in tweak_reference_list
        if item.kind in _TWEAKXL_FLAT_KINDS
        or item.kind.startswith("array.")
        or item.kind in {"record.base", "record.type"}
    ]
    cet_flats: dict[str, list[Reference]] = defaultdict(list)
    tweak_flats: dict[str, list[Reference]] = defaultdict(list)
    cet_records: dict[str, list[Reference]] = defaultdict(list)
    tweak_records: dict[str, list[Reference]] = defaultdict(list)
    for item in cet:
        target = str(item.details.get("target") or "")
        if item.kind in _CET_TWEAKDB_FLAT_KINDS and target:
            cet_flats[target].append(item)
        elif item.kind in _CET_TWEAKDB_RECORD_KINDS and target:
            cet_records[target].append(item)
    for item in tweak:
        if item.kind in {"record.base", "record.type"}:
            tweak_records[item.identity].append(item)
        else:
            tweak_flats[item.identity].append(item)

    buckets: dict[tuple[str, str, str, tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
    same_package_targets = 0
    flat_candidates = 0
    record_candidates = 0
    equivalent_targets = 0
    runtime_override_targets = 0
    dynamic_value_targets = 0

    for identity in sorted(set(cet_flats) & set(tweak_flats), key=str.casefold):
        cet_group = cet_flats[identity]
        tweak_group = tweak_flats[identity]
        flat_candidates += 1
        if not _cross_package(cet_group, tweak_group):
            same_package_targets += 1
            continue
        participants = tuple(sorted(
            {item.mod_name for item in [*cet_group, *tweak_group]}, key=str.casefold
        ))
        if any(item.kind.startswith("array.") for item in tweak_group):
            rule, severity, confidence = "XEC-CET-TWEAKDB-ARRAY-RUNTIME-OVERRIDE", "warning", "high"
            runtime_override_targets += 1
        elif any(not item.details.get("value_known") for item in cet_group):
            rule, severity, confidence = "XEC-CET-TWEAKDB-FLAT-DYNAMIC-VALUE", "review", "medium"
            dynamic_value_targets += 1
        else:
            cet_values = {item.details.get("value_key") for item in cet_group}
            tweak_values = {item.details.get("value_key") for item in tweak_group}
            if len(cet_values | tweak_values) == 1:
                rule, severity, confidence = "XEC-CET-TWEAKDB-FLAT-EQUIVALENT", "info", "high"
                equivalent_targets += 1
            else:
                rule, severity, confidence = "XEC-CET-TWEAKDB-FLAT-RUNTIME-OVERRIDE", "warning", "high"
                runtime_override_targets += 1
        buckets[(rule, severity, confidence, participants)].append(
            _tweakdb_evidence(identity, cet_group, tweak_group)
        )

    # Record deletions also overlap TweakXL property declarations beneath the
    # record, even when the YAML does not repeat a $base or $type directive.
    for identity, cet_group in sorted(cet_records.items(), key=lambda item: item[0].casefold()):
        direct = tweak_records.get(identity, [])
        descendants = [
            item for target, group in tweak_flats.items()
            if target.startswith(identity + ".")
            for item in group
        ]
        deletions = [item for item in cet_group if item.kind == "tweakdb.record.delete"]
        clones = [item for item in cet_group if item.kind == "tweakdb.record.clone"]
        creations = [item for item in cet_group if item.kind == "tweakdb.record.create"]
        bases = [item for item in direct if item.kind == "record.base"]
        types = [item for item in direct if item.kind == "record.type"]
        comparisons = [
            (deletions, [*direct, *descendants], "delete"),
            (clones, bases, "clone"),
            (creations, types, "create"),
        ]
        if not any(left and right for left, right, _operation in comparisons):
            continue
        record_candidates += 1
        cross_package = False
        for selected_cet, matched, operation_name in comparisons:
            if not selected_cet or not matched or not _cross_package(selected_cet, matched):
                continue
            cross_package = True
            participants = tuple(sorted(
                {item.mod_name for item in [*selected_cet, *matched]}, key=str.casefold
            ))
            if operation_name == "delete":
                rule, severity, confidence = "XEC-CET-TWEAKDB-RECORD-DELETE", "warning", "high"
                runtime_override_targets += 1
            else:
                if operation_name == "clone":
                    expected = {item.details.get("source_record") for item in selected_cet}
                    known = all(item.details.get("source_known") for item in selected_cet)
                else:
                    expected = {item.details.get("record_type") for item in selected_cet}
                    known = all(item.details.get("record_type_known") for item in selected_cet)
                actual = {item.details.get("value") for item in matched}
                if not known:
                    rule, severity, confidence = "XEC-CET-TWEAKDB-RECORD-DYNAMIC-VALUE", "review", "medium"
                    dynamic_value_targets += 1
                elif len({str(item) for item in expected | actual}) == 1:
                    rule, severity, confidence = "XEC-CET-TWEAKDB-RECORD-EQUIVALENT", "info", "high"
                    equivalent_targets += 1
                else:
                    rule, severity, confidence = "XEC-CET-TWEAKDB-RECORD-RUNTIME-OVERRIDE", "warning", "high"
                    runtime_override_targets += 1
            buckets[(rule, severity, confidence, participants)].append(
                _tweakdb_evidence(identity, selected_cet, matched)
            )
        if not cross_package:
            same_package_targets += 1

    findings = _tweakdb_findings(buckets)
    dynamic_calls = sum(
        item.kind in {"tweakdb.flat.dynamic", "tweakdb.record.dynamic"}
        and item.details.get("deployed_state") != "overridden"
        and bool(item.details.get("reachable"))
        for item in cet_reference_list
    )
    documents = len({item.source_path.casefold() for item in [*cet, *tweak]})
    cross_package_targets = flat_candidates + record_candidates - same_package_targets
    operation = {
        "name": "CET TweakDB writes vs TweakXL",
        "status": "partial" if dynamic_calls or dynamic_value_targets else "analyzed",
        "documents": documents,
        "cet_flat_writes": len([item for item in cet if item.kind in _CET_TWEAKDB_FLAT_KINDS]),
        "cet_record_writes": len([item for item in cet if item.kind in _CET_TWEAKDB_RECORD_KINDS]),
        "tweakxl_flat_operations": len([item for item in tweak if item.kind not in {"record.base", "record.type"}]),
        "tweakxl_record_operations": len([item for item in tweak if item.kind in {"record.base", "record.type"}]),
        "candidate_targets": flat_candidates + record_candidates,
        "flat_candidates": flat_candidates,
        "record_candidates": record_candidates,
        "same_package_targets": same_package_targets,
        "cross_package_targets": cross_package_targets,
        "equivalent_targets": equivalent_targets,
        "runtime_override_targets": runtime_override_targets,
        "dynamic_value_targets": dynamic_value_targets,
        "dynamic_calls": dynamic_calls,
        "findings": len(findings),
        "note": "Exact literal TweakDB flat and record targets are compared across active CET Lua and TweakXL. Static Lua scalars and array tables are value-compared; computed targets and values are counted but not guessed.",
    }
    return findings, operation


def analyze_cross_ecosystem(
    cet_references: Iterable[Reference],
    redscript_references: Iterable[Reference],
    tweakxl_references: Iterable[Reference],
) -> tuple[list[Finding], dict[str, Any]]:
    cet_list = list(cet_references)
    method_findings, coverage = analyze_cross_ecosystem_methods(
        cet_list, redscript_references
    )
    tweakdb_findings, tweakdb_operation = analyze_cross_ecosystem_tweakdb(
        cet_list, tweakxl_references
    )
    coverage["cross_ecosystem_operations"].append(tweakdb_operation)
    coverage["sections"].append({
        "name": "CET TweakDB writes to TweakXL operations",
        "documents": tweakdb_operation["documents"],
        "status": tweakdb_operation["status"],
        "note": tweakdb_operation["note"],
    })
    coverage["documents"] = max(coverage["documents"], tweakdb_operation["documents"])
    return [*method_findings, *tweakdb_findings], coverage
