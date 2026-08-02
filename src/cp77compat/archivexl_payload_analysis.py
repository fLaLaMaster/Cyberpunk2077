from __future__ import annotations

import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterable

from .archive_payloads import (
    ArchivePayloadProvider,
    SerializedPayloadResult,
    payload_failure_finding,
)
from .models import ArchiveManifest, Artifact, Finding, Reference, normalize_game_path


def _localization_entries(value: Any) -> list[dict[str, Any]]:
    """Find serialized localization entry objects without assuming wrapper depth."""
    found: list[dict[str, Any]] = []

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            if "secondaryKey" in item and "primaryKey" in item:
                found.append(item)
                return
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return found


def _scalar(value: Any) -> Any:
    if isinstance(value, dict):
        for key in ("$value", "Value", "value"):
            if key in value:
                return _scalar(value[key])
    return value


def parse_localization_payload(
    declaration: Reference, serialized: Any, archive_path: str
) -> list[Reference]:
    locale = str(declaration.details.get("locale") or "unknown").casefold()
    payload_source = f"{archive_path}::{declaration.identity}"
    references: list[Reference] = []
    for index, entry in enumerate(_localization_entries(serialized)):
        secondary = str(_scalar(entry.get("secondaryKey")) or "").strip()
        primary = str(_scalar(entry.get("primaryKey")) or "").strip()
        details = {
            "locale": locale,
            "resource_path": declaration.identity,
            "entry_index": index,
            "payload_source": payload_source,
            "female_variant": _scalar(entry.get("femaleVariant")),
            "male_variant": _scalar(entry.get("maleVariant")),
            "declaration_source_path": declaration.source_path,
            "declaration_line": declaration.line,
        }
        if secondary:
            references.append(
                Reference(
                    ecosystem="archivexl",
                    kind="localization.entry.secondary",
                    identity=f"{locale}#{secondary}",
                    mod_name=declaration.mod_name,
                    source_path=declaration.source_path,
                    line=declaration.line,
                    details={**details, "secondary_key": secondary},
                )
            )
        if primary and primary != "0":
            references.append(
                Reference(
                    ecosystem="archivexl",
                    kind="localization.entry.primary",
                    identity=f"{locale}#{primary}",
                    mod_name=declaration.mod_name,
                    source_path=declaration.source_path,
                    line=declaration.line,
                    details={**details, "primary_key": primary},
                )
            )
    return references


def _find_c2d_array(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if value.get("$type") == "C2dArray" or (
            "compiledHeaders" in value and "compiledData" in value
        ):
            return value
        for child in value.values():
            found = _find_c2d_array(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_c2d_array(child)
            if found is not None:
                return found
    return None


def parse_factory_payload(
    declaration: Reference, serialized: Any, archive_path: str
) -> tuple[list[Reference], list[Finding]]:
    array = _find_c2d_array(serialized)
    if array is None:
        return [], [
            Finding(
                rule_id="AXL-FACTORY-SHAPE",
                severity="error",
                confidence="high",
                summary=f"Factory payload is not a C2dArray: {declaration.identity}",
                explanation="The serialized factory has no C2dArray data.",
                participants=[declaration.mod_name],
                evidence=[declaration.to_dict()],
            )
        ]
    headers = array.get("compiledHeaders") or array.get("headers")
    rows = array.get("compiledData") or array.get("data")
    if not isinstance(headers, list) or not isinstance(rows, list):
        return [], [
            Finding(
                rule_id="AXL-FACTORY-SHAPE",
                severity="error",
                confidence="high",
                summary=f"Factory table is malformed: {declaration.identity}",
                explanation="Factory headers and rows must be arrays.",
                participants=[declaration.mod_name],
                evidence=[declaration.to_dict()],
            )
        ]
    header_index = {
        str(header).strip().casefold(): index for index, header in enumerate(headers)
    }
    if "name" not in header_index or "path" not in header_index:
        return [], [
            Finding(
                rule_id="AXL-FACTORY-SHAPE",
                severity="error",
                confidence="high",
                summary=f"Factory table lacks name/path columns: {declaration.identity}",
                explanation=f"Observed headers: {headers}",
                participants=[declaration.mod_name],
                evidence=[declaration.to_dict()],
            )
        ]

    references: list[Reference] = []
    findings: list[Finding] = []
    payload_source = f"{archive_path}::{declaration.identity}"
    for row_index, row in enumerate(rows):
        if not isinstance(row, list) or len(row) <= max(
            header_index["name"], header_index["path"]
        ):
            findings.append(
                Finding(
                    rule_id="AXL-FACTORY-SHAPE",
                    severity="error",
                    confidence="high",
                    summary=f"Malformed factory row {row_index}: {declaration.identity}",
                    explanation="The row does not contain the declared name/path columns.",
                    participants=[declaration.mod_name],
                    evidence=[{**declaration.to_dict(), "row_index": row_index}],
                )
            )
            continue
        name = str(_scalar(row[header_index["name"]]) or "").strip()
        target = str(_scalar(row[header_index["path"]]) or "").strip()
        preload_index = header_index.get("preload")
        preload = (
            str(_scalar(row[preload_index]) or "").strip()
            if preload_index is not None and preload_index < len(row)
            else None
        )
        if not name or not target:
            findings.append(
                Finding(
                    rule_id="AXL-FACTORY-SHAPE",
                    severity="error",
                    confidence="high",
                    summary=f"Empty factory name/path at row {row_index}",
                    explanation=f"Factory resource: {declaration.identity}",
                    participants=[declaration.mod_name],
                    evidence=[{**declaration.to_dict(), "row_index": row_index}],
                )
            )
            continue
        references.append(
            Reference(
                ecosystem="archivexl",
                kind="factory.entry",
                identity=name,
                mod_name=declaration.mod_name,
                source_path=declaration.source_path,
                line=declaration.line,
                details={
                    "target_path": target,
                    "preload": preload,
                    "factory_resource": declaration.identity,
                    "row_index": row_index,
                    "payload_source": payload_source,
                },
            )
        )
    return references, findings


def _entry_value(reference: Reference) -> str:
    return json.dumps(
        {
            "female_variant": reference.details.get("female_variant"),
            "male_variant": reference.details.get("male_variant"),
        },
        sort_keys=True,
        ensure_ascii=False,
    )


def compare_localization_entries(references: Iterable[Reference]) -> list[Finding]:
    grouped: dict[tuple[str, str], list[Reference]] = defaultdict(list)
    for reference in references:
        if reference.kind.startswith("localization.entry."):
            grouped[(reference.kind, reference.identity.casefold())].append(reference)

    raw: list[Finding] = []
    for (kind, _identity), refs in grouped.items():
        mods = sorted({item.mod_name for item in refs}, key=str.casefold)
        if len(mods) < 2:
            continue
        values = {_entry_value(item) for item in refs}
        key_name = "secondaryKey" if kind.endswith("secondary") else "primaryKey"
        key_value = (
            refs[0].details.get("secondary_key")
            if kind.endswith("secondary")
            else refs[0].details.get("primary_key")
        )
        if kind.endswith("secondary"):
            rule = (
                "AXL-LOC-SECONDARY-DUPLICATE"
                if len(values) == 1
                else "AXL-LOC-SECONDARY-CONFLICT"
            )
        else:
            rule = (
                "AXL-LOC-PRIMARY-DUPLICATE"
                if len(values) == 1
                else "AXL-LOC-PRIMARY-CONFLICT"
            )
        conflict = rule.endswith("CONFLICT")
        raw.append(
            Finding(
                rule_id=rule,
                severity="conflict" if conflict else "info",
                confidence="high",
                summary=(
                    f"Competing localization {key_name}: {key_value}"
                    if conflict
                    else f"Duplicate localization {key_name}: {key_value}"
                ),
                explanation=(
                    f"Multiple mods define the same locale and {key_name} with "
                    + (
                        "different text. Archive load order determines the active entry."
                        if conflict
                        else "identical text. The duplicate is harmless but load-order dependent."
                    )
                ),
                participants=mods,
                evidence=[item.to_dict() for item in refs],
            )
        )

    # Consolidate keys shared by the same mod group so large language packs stay readable.
    consolidated: dict[tuple[str, tuple[str, ...]], list[Finding]] = defaultdict(list)
    for finding in raw:
        consolidated[(finding.rule_id, tuple(finding.participants))].append(finding)
    findings: list[Finding] = []
    for (rule, participants), items in consolidated.items():
        count = len(items)
        key_type = "secondaryKey" if "SECONDARY" in rule else "primaryKey"
        conflict = rule.endswith("CONFLICT")
        findings.append(
            Finding(
                rule_id=rule,
                severity="conflict" if conflict else "info",
                confidence="high",
                summary=(
                    f"{count} competing localization {key_type} definitions"
                    if conflict
                    else f"{count} duplicate localization {key_type} definitions"
                ),
                explanation=items[0].explanation,
                participants=list(participants),
                evidence=[
                    {
                        "identity": item.evidence[0]["identity"],
                        "references": item.evidence,
                    }
                    for item in items
                ],
            )
        )
    return sorted(findings, key=lambda item: item.sort_key())


def inspect_localization_payloads(
    declarations: Iterable[Reference],
    manifests: Iterable[ArchiveManifest],
    provider: ArchivePayloadProvider,
    workers: int = 4,
) -> tuple[list[Reference], list[Finding], dict[str, int]]:
    by_mod_member: dict[tuple[str, str], ArchiveManifest] = {}
    for manifest in manifests:
        for member in manifest.members:
            if member.resolved:
                by_mod_member.setdefault(
                    (manifest.mod_name, member.normalized_path), manifest
                )

    unique: dict[tuple[str, str, str], tuple[Reference, ArchiveManifest]] = {}
    skipped = 0
    requested = 0
    for declaration in declarations:
        if declaration.kind != "localization.onscreens":
            continue
        requested += 1
        manifest = by_mod_member.get(
            (declaration.mod_name, declaration.normalized_identity)
        )
        if manifest is None:
            skipped += 1
            continue
        key = (
            declaration.mod_name,
            declaration.normalized_identity,
            str(declaration.details.get("locale") or "unknown").casefold(),
        )
        unique.setdefault(key, (declaration, manifest))

    payload_references: list[Reference] = []
    findings: list[Finding] = []
    results: list[tuple[Reference, SerializedPayloadResult]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(provider.serialize_json, manifest, declaration.identity): declaration
            for declaration, manifest in unique.values()
        }
        for future in as_completed(futures):
            declaration = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # provider boundary
                findings.append(
                    Finding(
                        rule_id="AXL-PAYLOAD-FAILED",
                        severity="error",
                        confidence="high",
                        summary=f"Could not inspect ArchiveXL payload: {declaration.identity}",
                        explanation=str(exc),
                        participants=[declaration.mod_name],
                        evidence=[declaration.to_dict()],
                    )
                )
                continue
            results.append((declaration, result))

    serialized = 0
    extraction_cache_hits = 0
    serialization_cache_hits = 0
    for declaration, result in results:
        if not result.ok:
            findings.append(payload_failure_finding(result))
            continue
        serialized += 1
        extraction_cache_hits += int(result.payload.from_cache)
        serialization_cache_hits += int(result.from_cache)
        payload_references.extend(
            parse_localization_payload(
                declaration, result.data, result.payload.archive_path
            )
        )
    findings.extend(compare_localization_entries(payload_references))
    stats = {
        "declarations": requested,
        "unique_archive_payloads": len(unique),
        "skipped_without_own_archive": skipped,
        "serialized": serialized,
        "failed": len(unique) - serialized,
        "entry_references": len(payload_references),
        "extraction_cache_hits": extraction_cache_hits,
        "serialization_cache_hits": serialization_cache_hits,
    }
    return payload_references, findings, stats


def compare_factory_entries(references: Iterable[Reference]) -> list[Finding]:
    grouped: dict[str, list[Reference]] = defaultdict(list)
    for reference in references:
        if reference.kind == "factory.entry":
            grouped[reference.identity.casefold()].append(reference)

    findings: list[Finding] = []
    for refs in grouped.values():
        if len(refs) < 2:
            continue
        mods = sorted({item.mod_name for item in refs}, key=str.casefold)
        targets = {
            normalize_game_path(str(item.details.get("target_path") or ""))
            for item in refs
        }
        conflict = len(targets) > 1
        findings.append(
            Finding(
                rule_id=(
                    "AXL-FACTORY-NAME-CONFLICT"
                    if conflict
                    else "AXL-FACTORY-NAME-DUPLICATE"
                ),
                severity="conflict" if conflict else "info",
                confidence="high",
                summary=(
                    f"Factory name maps to competing targets: {refs[0].identity}"
                    if conflict
                    else f"Duplicate factory name: {refs[0].identity}"
                ),
                explanation=(
                    "Multiple factory rows register the same entity name with "
                    + (
                        "different resource paths. Archive load order determines the target."
                        if conflict
                        else "the same resource path. The duplicate is load-order dependent."
                    )
                ),
                participants=mods,
                evidence=[item.to_dict() for item in refs],
            )
        )
    return sorted(findings, key=lambda item: item.sort_key())


def validate_factory_targets(
    references: Iterable[Reference],
    manifests: Iterable[ArchiveManifest],
    artifacts: Iterable[Artifact] = (),
) -> tuple[list[Finding], dict[str, int]]:
    own_members: set[tuple[str, str]] = set()
    global_members: dict[str, set[str]] = defaultdict(set)
    for manifest in manifests:
        for member in manifest.members:
            if not member.resolved:
                continue
            own_members.add((manifest.mod_name, member.normalized_path))
            global_members[member.normalized_path].add(manifest.mod_name)

    archive_prefix = "archive\\pc\\mod\\"
    loose_own: set[tuple[str, str]] = set()
    loose_global: dict[str, set[str]] = defaultdict(set)
    for artifact in artifacts:
        candidates = {artifact.normalized_path}
        if artifact.normalized_path.startswith(archive_prefix):
            candidates.add(artifact.normalized_path[len(archive_prefix) :])
        for candidate in candidates:
            loose_own.add((artifact.mod_name, candidate))
            loose_global[candidate].add(artifact.mod_name)

    findings: list[Finding] = []
    verified = 0
    cross_mod = 0
    missing = 0
    for reference in references:
        if reference.kind != "factory.entry":
            continue
        target = normalize_game_path(str(reference.details.get("target_path") or ""))
        own_key = (reference.mod_name, target)
        if own_key in own_members or own_key in loose_own:
            verified += 1
            continue
        providers = sorted(
            (global_members.get(target, set()) | loose_global.get(target, set()))
            - {reference.mod_name},
            key=str.casefold,
        )
        if providers:
            cross_mod += 1
            findings.append(
                Finding(
                    rule_id="AXL-FACTORY-CROSS-MOD-TARGET",
                    severity="warning",
                    confidence="high",
                    summary=f"Factory target comes from another mod: {reference.identity}",
                    explanation=(
                        "The mod registering this factory entity does not contain its "
                        "target resource, but another installed mod does. This creates "
                        "an implicit dependency."
                    ),
                    participants=[reference.mod_name, *providers],
                    evidence=[reference.to_dict(), {"providers": providers}],
                )
            )
        else:
            missing += 1
            findings.append(
                Finding(
                    rule_id="AXL-FACTORY-TARGET-NOT-FOUND",
                    severity="warning",
                    confidence="high",
                    summary=f"Factory target was not found: {reference.identity}",
                    explanation=(
                        "The factory row points to a resource that is absent from the "
                        "declaring mod, loose files, and every indexed archive."
                    ),
                    participants=[reference.mod_name],
                    evidence=[reference.to_dict()],
                )
            )
    return findings, {
        "verified_targets": verified,
        "cross_mod_targets": cross_mod,
        "missing_targets": missing,
    }


def inspect_factory_payloads(
    declarations: Iterable[Reference],
    manifests: Iterable[ArchiveManifest],
    artifacts: Iterable[Artifact],
    provider: ArchivePayloadProvider,
    workers: int = 4,
) -> tuple[list[Reference], list[Finding], dict[str, int]]:
    manifest_list = list(manifests)
    artifact_list = list(artifacts)
    by_mod_member: dict[tuple[str, str], ArchiveManifest] = {}
    for manifest in manifest_list:
        for member in manifest.members:
            if member.resolved:
                by_mod_member.setdefault(
                    (manifest.mod_name, member.normalized_path), manifest
                )

    unique: dict[tuple[str, str], tuple[Reference, ArchiveManifest]] = {}
    skipped = 0
    requested = 0
    for declaration in declarations:
        if declaration.kind != "factory":
            continue
        requested += 1
        manifest = by_mod_member.get(
            (declaration.mod_name, declaration.normalized_identity)
        )
        if manifest is None:
            skipped += 1
            continue
        unique.setdefault(
            (declaration.mod_name, declaration.normalized_identity),
            (declaration, manifest),
        )

    payload_references: list[Reference] = []
    findings: list[Finding] = []
    results: list[tuple[Reference, SerializedPayloadResult]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(provider.serialize_json, manifest, declaration.identity): declaration
            for declaration, manifest in unique.values()
        }
        for future in as_completed(futures):
            declaration = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # provider boundary
                findings.append(
                    Finding(
                        rule_id="AXL-PAYLOAD-FAILED",
                        severity="error",
                        confidence="high",
                        summary=f"Could not inspect ArchiveXL payload: {declaration.identity}",
                        explanation=str(exc),
                        participants=[declaration.mod_name],
                        evidence=[declaration.to_dict()],
                    )
                )
                continue
            results.append((declaration, result))

    serialized = 0
    extraction_cache_hits = 0
    serialization_cache_hits = 0
    for declaration, result in results:
        if not result.ok:
            findings.append(payload_failure_finding(result))
            continue
        serialized += 1
        extraction_cache_hits += int(result.payload.from_cache)
        serialization_cache_hits += int(result.from_cache)
        parsed, parse_findings = parse_factory_payload(
            declaration, result.data, result.payload.archive_path
        )
        payload_references.extend(parsed)
        findings.extend(parse_findings)

    findings.extend(compare_factory_entries(payload_references))
    target_findings, target_stats = validate_factory_targets(
        payload_references, manifest_list, artifact_list
    )
    findings.extend(target_findings)
    stats = {
        "declarations": requested,
        "unique_archive_payloads": len(unique),
        "skipped_without_own_archive": skipped,
        "serialized": serialized,
        "failed": len(unique) - serialized,
        "entry_references": len(payload_references),
        "extraction_cache_hits": extraction_cache_hits,
        "serialization_cache_hits": serialization_cache_hits,
        **target_stats,
    }
    return payload_references, findings, stats
