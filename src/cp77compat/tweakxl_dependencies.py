from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .models import Finding, Reference
from .tweakdb import TweakDBRecordIndex, build_tweakdb_record_index


EXPLICIT_TWEAKDB_ID = re.compile(
    r'^\s*(?:t"([^"]+)"|TweakDBID\(\s*"([^"]+)"\s*\))\s*$'
)


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)


def _explicit_record_ids(value: Any) -> Iterable[str]:
    for candidate in _strings(value):
        match = EXPLICIT_TWEAKDB_ID.fullmatch(candidate)
        if match:
            yield match.group(1) or match.group(2)


def _source(reference: Reference, target: str | None = None) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "mod_name": reference.mod_name,
        "source_path": reference.source_path,
        "line": reference.line,
        "identity": reference.identity,
    }
    if target is not None:
        evidence["target"] = target
    return evidence


def _strongly_connected_components(graph: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in graph.get(node, set()):
            if target not in indices:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])
        if lowlinks[node] != indices[node]:
            return
        component: list[str] = []
        while stack:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == node:
                break
        components.append(component)

    for node in graph:
        if node not in indices:
            visit(node)
    return components


def _add_relationship(
    relationships: dict[tuple[str, tuple[str, ...]], dict[str, Any]],
    reference: Reference,
    target: str,
    providers: set[str],
    kind: str,
) -> None:
    provider_names = tuple(sorted(providers, key=str.casefold))
    key = (reference.mod_name, provider_names)
    item = relationships.setdefault(
        key,
        {
            "consumer_mod": reference.mod_name,
            "provider_mods": list(provider_names),
            "base_references": 0,
            "record_references": 0,
            "targets": set(),
            "sources": {},
        },
    )
    item[f"{kind}_references"] += 1
    item["targets"].add(target)
    source_key = (reference.source_path, reference.line, reference.identity, target)
    if len(item["sources"]) < 10:
        item["sources"].setdefault(source_key, _source(reference, target))


def _relationship_evidence(
    relationships: dict[tuple[str, tuple[str, ...]], dict[str, Any]],
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for item in sorted(
        relationships.values(),
        key=lambda value: (
            value["consumer_mod"].casefold(),
            tuple(name.casefold() for name in value["provider_mods"]),
        ),
    ):
        targets = sorted(item["targets"], key=str.casefold)
        base_count = item["base_references"]
        record_count = item["record_references"]
        evidence.append(
            {
                "consumer_mod": item["consumer_mod"],
                "provider_mods": item["provider_mods"],
                "reference_count": base_count + record_count,
                "base_references": base_count,
                "record_references": record_count,
                "target_count": len(targets),
                "targets": targets[:25],
                "sources": list(item["sources"].values()),
            }
        )
    return evidence


def analyze_tweak_dependencies(
    references: Iterable[Reference],
    game_root: Path,
    record_index: TweakDBRecordIndex | None = None,
) -> tuple[list[Finding], dict[str, Any]]:
    reference_list = list(references)
    index = record_index or build_tweakdb_record_index(game_root)
    base_references = [item for item in reference_list if item.kind == "record.base"]
    definition_references = [
        item for item in reference_list if item.kind in {"record.base", "record.type"}
    ]
    providers: dict[str, list[Reference]] = defaultdict(list)
    for reference in definition_references:
        providers[reference.identity].append(reference)
    providers_casefold: dict[str, set[str]] = defaultdict(set)
    for identity in providers:
        providers_casefold[identity.casefold()].add(identity)
    official_casefold: dict[str, set[str]] = defaultdict(set)
    for identity in index.named_records:
        official_casefold[identity.casefold()].add(identity)
    official_cache: dict[str, bool] = {}

    def is_official(identity: str) -> bool:
        if identity not in official_cache:
            official_cache[identity] = index.contains(identity)
        return official_cache[identity]

    findings: list[Finding] = []
    missing_bases: list[tuple[Reference, str]] = []
    case_mismatched_bases: list[tuple[Reference, str, list[str]]] = []
    relationships: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
    base_resolution = defaultdict(int)
    graph: dict[str, set[str]] = {identity: set() for identity in providers}

    for reference in base_references:
        target_value = reference.details.get("value")
        if not isinstance(target_value, str) or not target_value.strip():
            missing_bases.append((reference, str(target_value)))
            base_resolution["invalid"] += 1
            continue
        target = target_value.strip()
        target_providers = providers.get(target, [])
        provider_mods = {item.mod_name for item in target_providers}
        if is_official(target):
            base_resolution["vanilla"] += 1
        elif reference.mod_name in provider_mods:
            base_resolution["same_mod"] += 1
        elif provider_mods:
            base_resolution["cross_mod"] += 1
            _add_relationship(
                relationships,
                reference,
                target,
                provider_mods,
                "base",
            )
        elif (
            case_matches := sorted(
                official_casefold.get(target.casefold(), set())
                | providers_casefold.get(target.casefold(), set()),
                key=str.casefold,
            )
        ):
            base_resolution["case_mismatch"] += 1
            case_mismatched_bases.append((reference, target, case_matches))
        else:
            base_resolution["missing"] += 1
            missing_bases.append((reference, target))
        if target in providers:
            graph.setdefault(reference.identity, set()).add(target)

    if missing_bases:
        findings.append(
            Finding(
                rule_id="TXL-MISSING-BASE",
                severity="error",
                confidence="high",
                summary=f"{len(missing_bases)} unresolved TweakXL record bases",
                explanation=(
                    "A $base clone source was not found among installed TweakXL record "
                    "definitions, official REDmod record sources, or generated inline "
                    "record IDs in the local TweakDB binaries. TweakXL cannot clone a "
                    "record that does not exist when the tweak is applied."
                ),
                participants=sorted(
                    {reference.mod_name for reference, _ in missing_bases},
                    key=str.casefold,
                ),
                evidence=[
                    _source(reference, target)
                    for reference, target in missing_bases
                ],
            )
        )

    if case_mismatched_bases:
        findings.append(
            Finding(
                rule_id="TXL-BASE-CASE-MISMATCH",
                severity="error",
                confidence="high",
                summary=(
                    f"{len(case_mismatched_bases)} TweakXL base IDs differ only by case"
                ),
                explanation=(
                    "TweakDB IDs use the spelling and capitalization supplied to their "
                    "CRC32/length identity. Each $base target below is absent exactly, "
                    "while a differently capitalized record exists locally."
                ),
                participants=sorted(
                    {reference.mod_name for reference, _, _ in case_mismatched_bases},
                    key=str.casefold,
                ),
                evidence=[
                    {
                        **_source(reference, target),
                        "case_matches": matches,
                    }
                    for reference, target, matches in case_mismatched_bases
                ],
            )
        )

    cyclic_components: list[list[str]] = []
    for component in _strongly_connected_components(graph):
        if len(component) > 1:
            cyclic_components.append(component)
        elif component and component[0] in graph.get(component[0], set()):
            cyclic_components.append(component)
    if cyclic_components:
        cycle_evidence: list[dict[str, Any]] = []
        cycle_mods: set[str] = set()
        for component in cyclic_components:
            members = set(component)
            sources = [
                _source(reference, str(reference.details.get("value")))
                for reference in base_references
                if reference.identity in members
                and reference.details.get("value") in members
            ]
            cycle_mods.update(source["mod_name"] for source in sources)
            cycle_evidence.append(
                {
                    "records": sorted(component, key=str.casefold),
                    "sources": sources,
                }
            )
        findings.append(
            Finding(
                rule_id="TXL-BASE-CYCLE",
                severity="error",
                confidence="high",
                summary=f"{len(cyclic_components)} cyclic TweakXL base chains",
                explanation=(
                    "These installed record definitions eventually clone themselves. "
                    "No record in a cyclic $base chain can be constructed first."
                ),
                participants=sorted(cycle_mods, key=str.casefold),
                evidence=cycle_evidence,
            )
        )

    explicit_resolution = defaultdict(int)
    implicit_provider_matches = 0
    implicit_cross_mod = 0
    missing_explicit: list[tuple[Reference, str]] = []
    for reference in reference_list:
        if reference.kind in {"record.base", "record.type"}:
            continue
        value = reference.details.get("value")
        explicit_targets = list(_explicit_record_ids(value))
        explicit_set = set(explicit_targets)
        for target in explicit_targets:
            target_providers = providers.get(target, [])
            provider_mods = {item.mod_name for item in target_providers}
            if is_official(target):
                explicit_resolution["vanilla"] += 1
            elif reference.mod_name in provider_mods:
                explicit_resolution["same_mod"] += 1
            elif provider_mods:
                explicit_resolution["cross_mod"] += 1
                _add_relationship(
                    relationships,
                    reference,
                    target,
                    provider_mods,
                    "record",
                )
            else:
                explicit_resolution["missing"] += 1
                missing_explicit.append((reference, target))

        for target in _strings(value):
            if target in explicit_set:
                continue
            target_providers = providers.get(target, [])
            if not target_providers or is_official(target):
                continue
            implicit_provider_matches += 1
            provider_mods = {item.mod_name for item in target_providers}
            if reference.mod_name not in provider_mods:
                implicit_cross_mod += 1
                _add_relationship(
                    relationships,
                    reference,
                    target,
                    provider_mods,
                    "record",
                )

    if missing_explicit:
        findings.append(
            Finding(
                rule_id="TXL-MISSING-RECORD-REFERENCE",
                severity="review",
                confidence="medium",
                summary=f"{len(missing_explicit)} unresolved explicit record references",
                explanation=(
                    "An explicit t\"...\" or TweakDBID(\"...\") foreign key was not "
                    "found in the local vanilla TweakDB index or installed TweakXL "
                    "record definitions. A script may still create it at runtime, so "
                    "confirm these entries against framework logs."
                ),
                participants=sorted(
                    {reference.mod_name for reference, _ in missing_explicit},
                    key=str.casefold,
                ),
                evidence=[
                    _source(reference, target)
                    for reference, target in missing_explicit
                ],
            )
        )

    relationship_evidence = _relationship_evidence(relationships)
    if relationship_evidence:
        participants = {
            evidence["consumer_mod"] for evidence in relationship_evidence
        }
        for evidence in relationship_evidence:
            participants.update(evidence["provider_mods"])
        reference_count = sum(
            evidence["reference_count"] for evidence in relationship_evidence
        )
        findings.append(
            Finding(
                rule_id="TXL-CROSS-MOD-DEPENDENCY",
                severity="info",
                confidence="high",
                summary=(
                    f"{len(relationship_evidence)} cross-mod TweakXL dependency "
                    f"relationships ({reference_count} references)"
                ),
                explanation=(
                    "These consumers clone or reference custom TweakDB records created "
                    "by another installed mod. They are compatible while the provider "
                    "is present, but disabling or replacing that provider can break the "
                    "consumer. Evidence is compacted by consumer/provider pair."
                ),
                participants=sorted(participants, key=str.casefold),
                evidence=relationship_evidence,
            )
        )

    explicit_total = sum(explicit_resolution.values())
    base_documents = len({item.source_path for item in base_references})
    dependency_documents = len({item.source_path for item in reference_list})
    coverage = {
        "documents": dependency_documents,
        "official_tweak_files": index.source_files,
        "official_named_records": len(index.named_records),
        "tweakdb_binaries": len(index.binary_files),
        "sections": [
            {
                "name": "record definitions",
                "documents": len({item.source_path for item in definition_references}),
                "status": "analyzed",
                "note": (
                    f"{len(providers)} concrete records created with $type or $base "
                    "are indexed as dependency providers."
                ),
            },
            {
                "name": "$base clone sources",
                "documents": base_documents,
                "status": "analyzed",
                "note": (
                    "Targets are resolved against installed definitions, official "
                    "REDmod sources, and generated inline IDs in local TweakDB binaries."
                ),
            },
            {
                "name": "foreign-key values",
                "documents": dependency_documents,
                "status": "partial",
                "note": (
                    "Explicit TweakDBID syntax and implicit values matching installed "
                    "custom record providers are analyzed. Other implicit scalars need "
                    "property type metadata and are intentionally not guessed."
                ),
            },
        ],
        "dependencies": [
            {
                "name": "$base targets",
                "references": len(base_references),
                "vanilla": base_resolution["vanilla"],
                "same_mod": base_resolution["same_mod"],
                "cross_mod": base_resolution["cross_mod"],
                "case_mismatch": base_resolution["case_mismatch"],
                "missing": base_resolution["missing"] + base_resolution["invalid"],
                "cycles": len(cyclic_components),
                "status": "analyzed",
                "note": "Every clone source is checked before base-chain cycle analysis.",
            },
            {
                "name": "explicit foreign keys",
                "references": explicit_total,
                "vanilla": explicit_resolution["vanilla"],
                "same_mod": explicit_resolution["same_mod"],
                "cross_mod": explicit_resolution["cross_mod"],
                "case_mismatch": "",
                "missing": explicit_resolution["missing"],
                "cycles": "",
                "status": "analyzed",
                "note": 'Checks t"..." and TweakDBID("...") values.',
            },
            {
                "name": "implicit provider matches",
                "references": implicit_provider_matches,
                "vanilla": "",
                "same_mod": "",
                "cross_mod": implicit_cross_mod,
                "case_mismatch": "",
                "missing": "",
                "cycles": "",
                "status": "partial",
                "note": (
                    "Only values that exactly name an installed custom record "
                    "definition are classified without schema metadata."
                ),
            },
        ],
    }
    return findings, coverage
