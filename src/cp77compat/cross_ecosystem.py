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
