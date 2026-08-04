from __future__ import annotations

import json
import hashlib
from copy import deepcopy
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


_CUSTOMIZATION_PARTS = ("arms", "body", "head")
_CUSTOMIZATION_CHOICE_FIELDS = {
    "gameuiAppearanceInfo": ("definitions", "name"),
    "gameuiMorphInfo": ("morphNames", "localizedName"),
    "gameuiSwitcherInfo": ("options", "localizedName"),
}


def _customization_shape_finding(
    declaration: Reference, explanation: str, archive_path: str
) -> Finding:
    return Finding(
        rule_id="AXL-CUSTOMIZATION-PAYLOAD-SHAPE",
        severity="error",
        confidence="high",
        summary=f"Invalid customization payload: {declaration.identity}",
        explanation=explanation,
        participants=[declaration.mod_name],
        evidence=[{**declaration.to_dict(), "archive_path": archive_path}],
    )


def _customization_option_identity(
    gender: str, part: str, option: dict[str, Any]
) -> tuple[str | None, dict[str, Any]]:
    def cname(key: str) -> str:
        value = str(_scalar(option.get(key)) or "").strip()
        return "" if value == "None" else value

    name = cname("name")
    ui_slot = cname("uiSlot")
    link = cname("link")
    if name:
        return f"{gender}/{part}/name/{name}", {
            "named": True,
            "name": name,
            "ui_slot": ui_slot,
            "link": link,
        }
    selectors = []
    if ui_slot:
        selectors.append(f"slot={ui_slot}")
    if link:
        selectors.append(f"link={link}")
    if not selectors:
        return None, {"named": False, "ui_slot": ui_slot, "link": link}
    return f"{gender}/{part}/selector/{'|'.join(selectors)}", {
        "named": False,
        "ui_slot": ui_slot,
        "link": link,
    }


def _expanded_customization_options(values: Any) -> list[dict[str, Any]]:
    """Apply ArchiveXL's inheritance for consecutive anonymous appearance options."""
    if not isinstance(values, list):
        return []
    expanded: list[dict[str, Any]] = []
    previous_appearance: dict[str, Any] | None = None
    for wrapped in values:
        value = _journal_handle_data(wrapped)
        if not isinstance(value, dict):
            continue
        option = deepcopy(value)
        option_type = str(option.get("$type") or "")
        name = str(_scalar(option.get("name")) or "").strip()
        if option_type == "gameuiAppearanceInfo" and (not name or name == "None"):
            if previous_appearance is not None:
                if not option.get("definitions"):
                    option["definitions"] = deepcopy(
                        previous_appearance.get("definitions") or []
                    )
                if not option.get("resource"):
                    option["resource"] = deepcopy(previous_appearance.get("resource"))
            previous_appearance = option
        expanded.append(option)
    return expanded


def parse_customization_payload(
    declaration: Reference, serialized: Any, archive_path: str
) -> tuple[list[Reference], list[Finding]]:
    try:
        resource = serialized["Data"]["RootChunk"]
    except (KeyError, TypeError):
        resource = None
    if (
        not isinstance(resource, dict)
        or resource.get("$type") != "gameuiCharacterCustomizationInfoResource"
    ):
        return [], [
            _customization_shape_finding(
                declaration,
                "WolvenKit JSON has no gameuiCharacterCustomizationInfoResource RootChunk.",
                archive_path,
            )
        ]

    gender = str(declaration.details.get("gender") or "unknown")
    payload_source = f"{archive_path}::{declaration.identity}"
    common = {
        "gender": gender,
        "resource_path": declaration.identity,
        "payload_source": payload_source,
        "declaration_source_path": declaration.source_path,
        "declaration_line": declaration.line,
    }
    references: list[Reference] = []
    findings: list[Finding] = []
    for part in _CUSTOMIZATION_PARTS:
        groups = resource.get(f"{part}Groups") or []
        if not isinstance(groups, list):
            findings.append(
                _customization_shape_finding(
                    declaration, f"{part}Groups must be an array.", archive_path
                )
            )
            groups = []
        for group_index, group in enumerate(groups):
            if not isinstance(group, dict):
                continue
            group_name = str(_scalar(group.get("name")) or "").strip()
            entries = group.get("options") or []
            if not group_name or not isinstance(entries, list):
                continue
            for entry_index, entry in enumerate(entries):
                entry_name = str(_scalar(entry) or "").strip()
                if not entry_name:
                    continue
                references.append(
                    Reference(
                        ecosystem="archivexl",
                        kind="customization.group.entry",
                        identity=f"{gender}/{part}/group/{group_name}/{entry_name}",
                        mod_name=declaration.mod_name,
                        source_path=declaration.source_path,
                        line=declaration.line,
                        details={
                            **common,
                            "part": part,
                            "group_name": group_name,
                            "entry_name": entry_name,
                            "group_index": group_index,
                            "entry_index": entry_index,
                            "fingerprint": _patch_fingerprint(entry),
                        },
                    )
                )

        raw_options = resource.get(f"{part}CustomizationOptions") or []
        if not isinstance(raw_options, list):
            findings.append(
                _customization_shape_finding(
                    declaration,
                    f"{part}CustomizationOptions must be an array.",
                    archive_path,
                )
            )
            continue
        expanded_options = _expanded_customization_options(raw_options)
        named_options = {
            str(_scalar(item.get("name")) or "").strip(): item
            for item in expanded_options
            if str(_scalar(item.get("name")) or "").strip() not in {"", "None"}
        }
        for option_index, option in enumerate(expanded_options):
            declared_option_type = str(option.get("$type") or "")
            identity, selectors = _customization_option_identity(
                gender, part, option
            )
            if identity is None:
                findings.append(
                    _customization_shape_finding(
                        declaration,
                        f"{part} option {option_index} has no name, uiSlot, or link selector.",
                        archive_path,
                    )
                )
                continue
            content_option = option
            if selectors.get("named") and selectors.get("link"):
                content_option = named_options.get(
                    str(selectors["link"]), option
                )
            option_type = str(content_option.get("$type") or "")
            choice_field, choice_key = _CUSTOMIZATION_CHOICE_FIELDS.get(
                option_type, (None, None)
            )
            metadata = {
                key: value
                for key, value in option.items()
                if key not in {choice_field, "index", "defaultIndex"}
            }
            option_details = {
                **common,
                **selectors,
                "part": part,
                "option_type": option_type,
                "declared_option_type": declared_option_type,
                "option_index": option_index,
                "choice_field": choice_field,
                "metadata_fingerprint": _patch_fingerprint(metadata),
            }
            references.append(
                Reference(
                    ecosystem="archivexl",
                    kind="customization.option",
                    identity=identity,
                    mod_name=declaration.mod_name,
                    source_path=declaration.source_path,
                    line=declaration.line,
                    details=option_details,
                )
            )
            choices = content_option.get(choice_field) if choice_field else None
            if not isinstance(choices, list) or choice_key is None:
                continue
            for choice_index, choice in enumerate(choices):
                choice_data = _journal_handle_data(choice)
                if not isinstance(choice_data, dict):
                    continue
                choice_identity = str(
                    _scalar(choice_data.get(choice_key)) or ""
                ).strip()
                if not choice_identity:
                    continue
                references.append(
                    Reference(
                        ecosystem="archivexl",
                        kind="customization.choice",
                        identity=f"{identity}/choice/{choice_identity}",
                        mod_name=declaration.mod_name,
                        source_path=declaration.source_path,
                        line=declaration.line,
                        details={
                            **option_details,
                            "option_identity": identity,
                            "choice_identity": choice_identity,
                            "choice_key": choice_key,
                            "choice_index": choice_index,
                            "fingerprint": _patch_fingerprint(choice_data),
                        },
                    )
                )
    return references, findings


def _selector_overlaps(left: Reference, right: Reference) -> bool:
    if left.details.get("named") or right.details.get("named"):
        return False
    if left.details.get("gender") != right.details.get("gender"):
        return False
    if left.details.get("part") != right.details.get("part"):
        return False
    def matches(source: Reference, target: Reference) -> bool:
        source_slot = str(source.details.get("ui_slot") or "")
        target_slot = str(target.details.get("ui_slot") or "")
        source_link = str(source.details.get("link") or "")
        target_link = str(target.details.get("link") or "")
        if not source_slot and not source_link:
            return False
        if source_slot:
            if source_slot.endswith("*"):
                if not target_slot.startswith(source_slot[:-1]):
                    return False
            elif source_slot != target_slot:
                return False
        # ArchiveXL 1.26.0 checks link values exactly. Its current source computes
        # the link-wildcard flag from the already-trimmed slot string.
        if source_link and source_link != target_link:
            return False
        return True

    return matches(left, right) or matches(right, left)


def _consolidate_customization_findings(
    raw: Iterable[Finding], stats: dict[str, int]
) -> list[Finding]:
    grouped: dict[tuple[str, tuple[str, ...]], list[Finding]] = defaultdict(list)
    for finding in raw:
        grouped[(finding.rule_id, tuple(finding.participants))].append(finding)
        if finding.rule_id.endswith("COMPOSABLE"):
            stats["composable_entries"] += 1
        elif finding.rule_id.endswith("DUPLICATE"):
            stats["duplicate_entries"] += 1
        elif finding.rule_id.endswith("CONFLICT"):
            stats["conflicting_entries"] += 1
        elif finding.severity == "review":
            stats["review_entries"] += 1
    result: list[Finding] = []
    for (_rule, participants), items in grouped.items():
        first = items[0]
        result.append(
            Finding(
                rule_id=first.rule_id,
                severity=first.severity,
                confidence=first.confidence,
                summary=(first.summary if len(items) == 1 else f"{len(items)} {first.summary}"),
                explanation=first.explanation,
                participants=list(participants),
                evidence=[evidence for item in items for evidence in item.evidence],
            )
        )
    return sorted(result, key=lambda item: item.sort_key())


def compare_customization_entries(
    references: Iterable[Reference],
) -> tuple[list[Finding], dict[str, int]]:
    refs = list(references)
    raw: list[Finding] = []
    by_kind_identity: dict[tuple[str, str], list[Reference]] = defaultdict(list)
    for reference in refs:
        if reference.kind.startswith("customization."):
            # ArchiveXL compares CName and localized-name identities case-sensitively.
            by_kind_identity[(reference.kind, reference.identity)].append(reference)

    for (kind, _identity), group in by_kind_identity.items():
        mods = sorted({item.mod_name for item in group}, key=str.casefold)
        if len(mods) < 2:
            continue
        first = group[0]
        if kind == "customization.group.entry":
            raw.append(
                Finding(
                    rule_id="AXL-CUSTOMIZATION-GROUP-ENTRY-DUPLICATE",
                    severity="info",
                    confidence="high",
                    summary="duplicate customization group entries",
                    explanation=(
                        "ArchiveXL appends group entries without deduplicating them; "
                        "the same entry is therefore registered more than once."
                    ),
                    participants=mods,
                    evidence=[item.to_dict() for item in group],
                )
            )
        elif kind == "customization.option":
            types = {str(item.details.get("option_type") or "") for item in group}
            metadata = {
                str(item.details.get("metadata_fingerprint") or "") for item in group
            }
            if len(types) > 1:
                raw.append(
                    Finding(
                        rule_id="AXL-CUSTOMIZATION-OPTION-TYPE-CONFLICT",
                        severity="conflict",
                        confidence="high",
                        summary="customization options with incompatible native types",
                        explanation=(
                            "ArchiveXL refuses to merge a matching option when its "
                            "native option type differs."
                        ),
                        participants=mods,
                        evidence=[item.to_dict() for item in group],
                    )
                )
            elif len(metadata) > 1:
                raw.append(
                    Finding(
                        rule_id="AXL-CUSTOMIZATION-OPTION-METADATA-REVIEW",
                        severity="review",
                        confidence="medium",
                        summary="customization options with differing non-choice metadata",
                        explanation=(
                            "The options share a merge identity but differ outside their "
                            "choice arrays. The first-created option supplies that metadata, "
                            "so the result can depend on archive load order."
                        ),
                        participants=mods,
                        evidence=[item.to_dict() for item in group],
                    )
                )
            else:
                raw.append(
                    Finding(
                        rule_id="AXL-CUSTOMIZATION-OPTION-COMPOSABLE",
                        severity="info",
                        confidence="high",
                        summary="composable customization option overlaps",
                        explanation=(
                            "The mods extend the same compatible option. ArchiveXL merges "
                            "their choice arrays by the type-specific choice identity."
                        ),
                        participants=mods,
                        evidence=[item.to_dict() for item in group],
                    )
                )
        elif kind == "customization.choice":
            fingerprints = {str(item.details.get("fingerprint") or "") for item in group}
            conflict = len(fingerprints) > 1
            raw.append(
                Finding(
                    rule_id=(
                        "AXL-CUSTOMIZATION-CHOICE-CONFLICT"
                        if conflict
                        else "AXL-CUSTOMIZATION-CHOICE-DUPLICATE"
                    ),
                    severity="conflict" if conflict else "info",
                    confidence="high",
                    summary=(
                        "competing customization choice definitions"
                        if conflict
                        else "duplicate customization choice definitions"
                    ),
                    explanation=(
                        "ArchiveXL replaces an existing matching choice; the later archive "
                        + (
                            "wins because these definitions differ."
                            if conflict
                            else "wins, although these definitions are identical."
                        )
                    ),
                    participants=mods,
                    evidence=[item.to_dict() for item in group],
                )
            )

    options = [item for item in refs if item.kind == "customization.option"]
    seen_selector_pairs: set[tuple[str, str, str, str]] = set()
    for index, left in enumerate(options):
        for right in options[index + 1 :]:
            if left.mod_name == right.mod_name or left.identity == right.identity:
                continue
            if not _selector_overlaps(left, right):
                continue
            participants = tuple(sorted({left.mod_name, right.mod_name}, key=str.casefold))
            key = (participants[0], participants[1], left.identity, right.identity)
            if key in seen_selector_pairs:
                continue
            seen_selector_pairs.add(key)
            raw.append(
                Finding(
                    rule_id="AXL-CUSTOMIZATION-SELECTOR-OVERLAP",
                    severity="review",
                    confidence="medium",
                    summary="prefix-overlapping anonymous customization selectors",
                    explanation=(
                        "ArchiveXL matches anonymous options by exact or prefix-overlapping "
                        "uiSlot/link selectors. Direction and archive order can affect which "
                        "option receives the merge."
                    ),
                    participants=list(participants),
                    evidence=[left.to_dict(), right.to_dict()],
                )
            )

    stats = {
        "composable_entries": 0,
        "duplicate_entries": 0,
        "conflicting_entries": 0,
        "review_entries": 0,
    }
    return _consolidate_customization_findings(raw, stats), stats


def inspect_customization_payloads(
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

    contexts: dict[tuple[str, str], list[Reference]] = defaultdict(list)
    selected: dict[tuple[str, str], tuple[Reference, ArchiveManifest]] = {}
    skipped = 0
    requested = 0
    for declaration in declarations:
        if declaration.kind != "customization":
            continue
        requested += 1
        key = (declaration.mod_name, declaration.normalized_identity)
        manifest = by_mod_member.get(key)
        if manifest is None:
            skipped += 1
            continue
        contexts[key].append(declaration)
        selected.setdefault(key, (declaration, manifest))

    results: dict[tuple[str, str], SerializedPayloadResult] = {}
    findings: list[Finding] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(provider.serialize_json, manifest, declaration.identity): key
            for key, (declaration, manifest) in selected.items()
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as exc:  # provider boundary
                declaration = selected[key][0]
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

    payload_references: list[Reference] = []
    serialized = 0
    extraction_cache_hits = 0
    serialization_cache_hits = 0
    for key, result in results.items():
        if not result.ok:
            findings.append(payload_failure_finding(result))
            continue
        serialized += 1
        extraction_cache_hits += int(result.payload.from_cache)
        serialization_cache_hits += int(result.from_cache)
        for declaration in contexts[key]:
            parsed, parse_findings = parse_customization_payload(
                declaration, result.data, result.payload.archive_path
            )
            payload_references.extend(parsed)
            findings.extend(parse_findings)

    comparison_findings, comparison_stats = compare_customization_entries(
        payload_references
    )
    findings.extend(comparison_findings)
    stats = {
        "declarations": requested,
        "unique_archive_payloads": len(selected),
        "skipped_without_own_archive": skipped,
        "serialized": serialized,
        "failed": len(selected) - serialized,
        "entry_references": len(payload_references),
        "group_entries": sum(
            item.kind == "customization.group.entry" for item in payload_references
        ),
        "option_references": sum(
            item.kind == "customization.option" for item in payload_references
        ),
        "choice_references": sum(
            item.kind == "customization.choice" for item in payload_references
        ),
        "extraction_cache_hits": extraction_cache_hits,
        "serialization_cache_hits": serialization_cache_hits,
        **comparison_stats,
    }
    return payload_references, findings, stats


_PATCH_ID_KEYS = (
    "name",
    "appearanceName",
    "componentName",
    "partName",
    "slotName",
    "id",
    "key",
    "hash",
)
_PATCH_METADATA_KEYS = {
    "$type",
    "$storage",
    "HandleId",
    "cookingPlatform",
    "resourceVersion",
    "saveDateTime",
    "version",
}
_PATCH_VOLATILE_KEYS = {"HandleId"}
_PATCHABLE_ROOT_PROPERTIES = {
    "CMesh": {
        "appearances",
        "externalMaterials",
        "localMaterialBuffer",
        "localMaterialInstances",
        "materialEntries",
        "parameters",
    },
    "entEntityTemplate": {
        "appearances",
        "components",
        "entity",
        "visualTagsSchema",
    },
    "appearanceResource": {"appearances"},
    "gameDeviceResource": {"data"},
}


def _canonical_patch_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _canonical_patch_value(child)
            for key, child in sorted(value.items(), key=lambda item: str(item[0]))
            if str(key) not in _PATCH_VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [_canonical_patch_value(child) for child in value]
    return value


def _patch_fingerprint(value: Any) -> str:
    encoded = json.dumps(
        _canonical_patch_value(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _journal_handle_data(value: Any) -> Any:
    if isinstance(value, dict) and isinstance(value.get("Data"), dict):
        return value["Data"]
    return value


def _journal_handle_key(value: Any) -> str | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    return str(value)


def _journal_handle_index(value: Any) -> dict[str, dict[str, Any]]:
    """Index WolvenKit handle wrappers before following graph references."""
    handles: dict[str, dict[str, Any]] = {}

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            handle_id = _journal_handle_key(item.get("HandleId"))
            if handle_id is not None and isinstance(item.get("Data"), dict):
                handles.setdefault(handle_id, item)
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return handles


def _resolve_journal_handle(
    value: Any, handles: dict[str, dict[str, Any]]
) -> tuple[Any, str | None, str | None, str | None]:
    """Return node data, effective handle ID, reference ID, and any error."""
    reference_id = (
        _journal_handle_key(value.get("HandleRefId"))
        if isinstance(value, dict)
        else None
    )
    resolved = value
    if reference_id is not None:
        resolved = handles.get(reference_id)
        if resolved is None:
            return (
                None,
                None,
                reference_id,
                f"Journal HandleRefId {reference_id} has no matching HandleId.",
            )
    handle_id = (
        _journal_handle_key(resolved.get("HandleId"))
        if isinstance(resolved, dict)
        else None
    )
    return _journal_handle_data(resolved), handle_id, reference_id, None


def _journal_shape_finding(
    declaration: Reference, explanation: str, archive_path: str
) -> Finding:
    return Finding(
        rule_id="AXL-JOURNAL-PAYLOAD-SHAPE",
        severity="error",
        confidence="high",
        summary=f"Invalid journal payload: {declaration.identity}",
        explanation=explanation,
        participants=[declaration.mod_name],
        evidence=[
            {
                **declaration.to_dict(),
                "archive_path": archive_path,
            }
        ],
    )


def parse_journal_payload(
    declaration: Reference, serialized: Any, archive_path: str
) -> tuple[list[Reference], list[Finding]]:
    """Extract ArchiveXL's effective slash-delimited journal entry paths."""
    try:
        resource = serialized["Data"]["RootChunk"]
    except (KeyError, TypeError):
        resource = None
    if not isinstance(resource, dict) or resource.get("$type") != "gameJournalResource":
        return [], [
            _journal_shape_finding(
                declaration,
                "WolvenKit JSON has no gameJournalResource RootChunk.",
                archive_path,
            )
        ]
    handles = _journal_handle_index(resource)
    root, root_handle_id, _root_reference_id, root_error = _resolve_journal_handle(
        resource.get("entry"), handles
    )
    if root_error is not None:
        return [], [
            _journal_shape_finding(declaration, root_error, archive_path)
        ]
    if (
        not isinstance(root, dict)
        or root.get("$type") != "gameJournalRootFolderEntry"
    ):
        return [], [
            _journal_shape_finding(
                declaration,
                "The journal resource entry must be gameJournalRootFolderEntry.",
                archive_path,
            )
        ]
    root_id = str(_scalar(root.get("id")) or "")
    if root_id:
        return [], [
            _journal_shape_finding(
                declaration,
                "The journal root ID is non-empty and will not merge with the game's root.",
                archive_path,
            )
        ]
    root_entries = root.get("entries")
    if not isinstance(root_entries, list):
        return [], [
            _journal_shape_finding(
                declaration,
                "The journal root has no entries sequence.",
                archive_path,
            )
        ]

    payload_source = f"{archive_path}::{declaration.identity}"
    references: list[Reference] = []
    issues: list[dict[str, Any]] = []
    entry_index = 0

    def issue(
        explanation: str,
        journal_path: str,
        handle_id: str | None = None,
        handle_ref_id: str | None = None,
    ) -> None:
        issues.append({
            "explanation": explanation,
            "journal_path": journal_path,
            "handle_id": handle_id,
            "handle_ref_id": handle_ref_id,
        })

    def visit(
        handle: Any, parent_path: str, active_handles: frozenset[str]
    ) -> None:
        nonlocal entry_index
        node, handle_id, handle_ref_id, resolve_error = _resolve_journal_handle(
            handle, handles
        )
        if resolve_error is not None:
            issue(resolve_error, parent_path, handle_id, handle_ref_id)
            return
        if handle_id is not None and handle_id in active_handles:
            issue(
                f"Journal handle graph contains an ancestor cycle at HandleId {handle_id}.",
                parent_path,
                handle_id,
                handle_ref_id,
            )
            return
        if not isinstance(node, dict):
            issue(
                "A journal entry handle has no object data.",
                parent_path,
                handle_id,
                handle_ref_id,
            )
            return
        raw_id_value = _scalar(node.get("id"))
        if not isinstance(raw_id_value, str) or not raw_id_value:
            issue(
                "Every journal entry requires a non-empty string ID.",
                parent_path,
                handle_id,
                handle_ref_id,
            )
            return
        raw_id = raw_id_value
        segments = raw_id.split("/")
        marked_for_edit = segments[-1].endswith("*")
        if marked_for_edit:
            segments[-1] = segments[-1][:-1]
        if any(not segment for segment in segments):
            issue(
                f"Journal entry ID contains an empty path segment: {raw_id}",
                parent_path,
                handle_id,
                handle_ref_id,
            )
            return
        identity = "/".join([part for part in (parent_path, *segments) if part])
        children = node.get("entries")
        is_container = isinstance(children, list)
        if "entries" in node and not is_container:
            issue(
                f"Journal container entries must be a sequence: {identity}",
                identity,
                handle_id,
                handle_ref_id,
            )
        references.append(
            Reference(
                ecosystem="archivexl",
                kind="journal.entry",
                identity=identity,
                mod_name=declaration.mod_name,
                source_path=declaration.source_path,
                line=declaration.line,
                details={
                    "resource_path": declaration.identity,
                    "payload_source": payload_source,
                    "entry_index": entry_index,
                    "raw_id": raw_id,
                    "entry_type": str(node.get("$type") or "unknown"),
                    "is_container": is_container,
                    "marked_for_edit": marked_for_edit,
                    "handle_id": handle_id,
                    "handle_ref_id": handle_ref_id,
                    "fingerprint": _patch_fingerprint(node),
                },
            )
        )
        entry_index += 1
        if is_container:
            next_active = (
                active_handles | {handle_id}
                if handle_id is not None
                else active_handles
            )
            for child in children:
                visit(child, identity, next_active)

    root_active = frozenset({root_handle_id}) if root_handle_id is not None else frozenset()
    for entry in root_entries:
        visit(entry, "", root_active)
    findings = []
    if issues:
        findings.append(Finding(
            rule_id="AXL-JOURNAL-PAYLOAD-SHAPE",
            severity="error",
            confidence="high",
            summary=f"Invalid journal payload: {declaration.identity}",
            explanation=(
                f"The serialized journal contains {len(issues)} structural issue"
                f"{'s' if len(issues) != 1 else ''}; see evidence for each graph location."
            ),
            participants=[declaration.mod_name],
            evidence=[{
                **declaration.to_dict(),
                "archive_path": archive_path,
                "issues": issues,
            }],
        ))
    return references, findings


def compare_journal_entries(
    references: Iterable[Reference],
) -> tuple[list[Finding], dict[str, int]]:
    grouped: dict[str, list[Reference]] = defaultdict(list)
    for reference in references:
        if reference.kind == "journal.entry":
            # ArchiveXL compares journal IDs with strcmp, so case is significant.
            grouped[reference.identity].append(reference)

    raw: list[tuple[str, str, str, list[Reference]]] = []
    shared_identities = 0
    for identity, refs in grouped.items():
        participants = {reference.mod_name for reference in refs}
        if len(participants) < 2:
            continue
        shared_identities += 1
        edits = [bool(reference.details.get("marked_for_edit")) for reference in refs]
        containers = [bool(reference.details.get("is_container")) for reference in refs]
        types = {str(reference.details.get("entry_type")) for reference in refs}
        fingerprints = {str(reference.details.get("fingerprint")) for reference in refs}
        if any(edits) and not all(edits):
            raw.append(
                (
                    "AXL-JOURNAL-EDIT-OVERLAP",
                    "review",
                    "One mod edits an existing journal entry while another merges or adds the same identity. Load order can change which properties and children survive.",
                    refs,
                )
            )
        elif all(edits):
            conflict = len(types) > 1 or len(fingerprints) > 1
            raw.append(
                (
                    "AXL-JOURNAL-EDIT-CONFLICT" if conflict else "AXL-JOURNAL-EDIT-DUPLICATE",
                    "conflict" if conflict else "info",
                    (
                        "Multiple mods edit the same journal path with different types or serialized content. ArchiveXL applies these property replacements in load order."
                        if conflict
                        else "Multiple mods apply the same serialized edit to the same journal path."
                    ),
                    refs,
                )
            )
        elif all(containers):
            raw.append(
                (
                    "AXL-JOURNAL-CONTAINER-COMPOSABLE",
                    "info",
                    "These mods share a journal container path but add or merge child entries below it. ArchiveXL recursively composes container children.",
                    refs,
                )
            )
        else:
            duplicate = len(types) == 1 and len(fingerprints) == 1
            raw.append(
                (
                    "AXL-JOURNAL-ENTRY-DUPLICATE" if duplicate else "AXL-JOURNAL-ENTRY-CONFLICT",
                    "info" if duplicate else "conflict",
                    (
                        "Multiple mods define identical non-container journal entries; only the already-present identity is retained."
                        if duplicate
                        else "Multiple mods define the same journal path with incompatible entry types or content. The first loaded non-container entry wins."
                    ),
                    refs,
                )
            )

    consolidated: dict[tuple[str, str, str, tuple[str, ...]], list[tuple[str, list[Reference]]]] = defaultdict(list)
    for rule, severity, explanation, refs in raw:
        participants = tuple(
            sorted({reference.mod_name for reference in refs}, key=str.casefold)
        )
        consolidated[(rule, severity, explanation, participants)].append(
            (refs[0].identity, refs)
        )
    labels = {
        "AXL-JOURNAL-CONTAINER-COMPOSABLE": "composable journal container overlaps",
        "AXL-JOURNAL-EDIT-CONFLICT": "conflicting journal edits",
        "AXL-JOURNAL-EDIT-DUPLICATE": "duplicate journal edits",
        "AXL-JOURNAL-EDIT-OVERLAP": "journal edit/merge overlaps",
        "AXL-JOURNAL-ENTRY-CONFLICT": "conflicting journal entries",
        "AXL-JOURNAL-ENTRY-DUPLICATE": "duplicate journal entries",
    }
    findings = [
        Finding(
            rule_id=rule,
            severity=severity,
            confidence="high" if severity in {"conflict", "info"} else "medium",
            summary=f"{len(items)} {labels[rule]}",
            explanation=explanation,
            participants=list(participants),
            evidence=[
                {
                    "identity": identity,
                    "references": [reference.to_dict() for reference in refs],
                }
                for identity, refs in items
            ],
        )
        for (rule, severity, explanation, participants), items in consolidated.items()
    ]
    rules = [item[0] for item in raw]
    return sorted(findings, key=lambda item: item.sort_key()), {
        "shared_identities": shared_identities,
        "composable_entries": rules.count("AXL-JOURNAL-CONTAINER-COMPOSABLE"),
        "duplicate_entries": sum("DUPLICATE" in rule for rule in rules),
        "conflicting_entries": sum("CONFLICT" in rule for rule in rules),
        "review_entries": rules.count("AXL-JOURNAL-EDIT-OVERLAP"),
    }


def inspect_journal_payloads(
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

    unique: dict[tuple[str, str], tuple[Reference, ArchiveManifest]] = {}
    skipped = 0
    requested = 0
    for declaration in declarations:
        if declaration.kind != "journal":
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
                results.append((declaration, future.result()))
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
        parsed, parse_findings = parse_journal_payload(
            declaration, result.data, result.payload.archive_path
        )
        payload_references.extend(parsed)
        findings.extend(parse_findings)

    comparison_findings, comparison_stats = compare_journal_entries(
        payload_references
    )
    findings.extend(comparison_findings)
    return payload_references, findings, {
        "declarations": requested,
        "unique_archive_payloads": len(unique),
        "skipped_without_own_archive": skipped,
        "serialized": serialized,
        "failed": len(unique) - serialized,
        "entry_references": len(payload_references),
        "extraction_cache_hits": extraction_cache_hits,
        "serialization_cache_hits": serialization_cache_hits,
        **comparison_stats,
    }


def _object_identity(value: dict[str, Any]) -> tuple[str, str] | None:
    for key in _PATCH_ID_KEYS:
        if key not in value:
            continue
        scalar = _scalar(value[key])
        if isinstance(scalar, (str, int)) and str(scalar).strip():
            return key, str(scalar).strip()
    return None


def _patch_records_for_value(
    path: str, value: Any, records: list[tuple[str, str, str]], depth: int = 0
) -> None:
    if depth > 6:
        digest = _patch_fingerprint(value)
        records.append((f"{path}[blob={digest[:16]}]", digest, "opaque"))
        return
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                identity = _object_identity(item)
                digest = _patch_fingerprint(item)
                if identity is not None:
                    key, name = identity
                    records.append((f"{path}[{key}={name}]", digest, "named-object"))
                else:
                    records.append(
                        (f"{path}[object={digest[:16]}]", digest, "opaque-object")
                    )
            else:
                digest = _patch_fingerprint(item)
                display = str(_scalar(item))
                records.append((f"{path}[value={display}]", digest, "scalar-item"))
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key) in _PATCH_METADATA_KEYS:
                continue
            _patch_records_for_value(f"{path}.{key}" if path else str(key), child, records, depth + 1)
        return
    records.append((path, _patch_fingerprint(value), "scalar"))


def _c2d_patch_records(root: dict[str, Any]) -> list[tuple[str, str, str]]:
    headers = root.get("compiledHeaders") or root.get("headers")
    rows = root.get("compiledData") or root.get("data")
    if not isinstance(headers, list) or not isinstance(rows, list):
        return []
    header_names = [str(item).strip() for item in headers]
    folded = [item.casefold() for item in header_names]
    identity_index = 0
    for candidate in ("name", "id", "key"):
        if candidate in folded:
            identity_index = folded.index(candidate)
            break
    records: list[tuple[str, str, str]] = []
    for row in rows:
        if not isinstance(row, list) or identity_index >= len(row):
            continue
        identity = str(_scalar(row[identity_index]) or "").strip()
        if not identity:
            continue
        digest = _patch_fingerprint(row)
        records.append((f"rows[{header_names[identity_index]}={identity}]", digest, "table-row"))
    return records


def parse_resource_patch_payload(
    declaration: Reference, serialized: Any, archive_path: str
) -> tuple[list[Reference], list[Finding]]:
    root = serialized
    try:
        root = serialized["Data"]["RootChunk"]
    except (KeyError, TypeError):
        pass
    if not isinstance(root, dict):
        return [], [
            Finding(
                rule_id="AXL-RESOURCE-PATCH-PAYLOAD-SHAPE",
                severity="error",
                confidence="high",
                summary=f"Patch payload has no serialized root: {declaration.details.get('source')}",
                explanation="WolvenKit JSON did not contain a usable RootChunk object.",
                participants=[declaration.mod_name],
                evidence=[declaration.to_dict()],
            )
        ]

    root_type = str(root.get("$type") or "unknown")
    if root_type == "C2dArray":
        records = _c2d_patch_records(root)
    else:
        records: list[tuple[str, str, str]] = []
        requested_properties = {
            str(item).casefold()
            for item in (declaration.details.get("properties") or [])
        }
        allowed_properties = _PATCHABLE_ROOT_PROPERTIES.get(root_type)
        root_items = root.items() if requested_properties or allowed_properties is not None else ()
        for key, value in root_items:
            if str(key) in _PATCH_METADATA_KEYS:
                continue
            if requested_properties and str(key).casefold() not in requested_properties:
                continue
            if (
                not requested_properties
                and allowed_properties is not None
                and str(key) not in allowed_properties
            ):
                continue
            if value is None or value == [] or value == {}:
                continue
            _patch_records_for_value(str(key), value, records)

    source = str(declaration.details.get("source") or "")
    payload_source = f"{archive_path}::{source}"
    references = [
        Reference(
            ecosystem="archivexl",
            kind="resource.patch.entry",
            identity=f"{declaration.identity}#{identity}",
            mod_name=declaration.mod_name,
            source_path=declaration.source_path,
            line=declaration.line,
            details={
                "target_path": declaration.identity,
                "patch_source": source,
                "inner_identity": identity,
                "fingerprint": fingerprint,
                "identity_kind": identity_kind,
                "root_type": root_type,
                "payload_source": payload_source,
            },
        )
        for identity, fingerprint, identity_kind in records
    ]
    return references, []


def compare_patch_target_entries(
    declarations: list[Reference], entries: list[Reference], inspected: bool
) -> Finding:
    participants = sorted({item.mod_name for item in declarations}, key=str.casefold)
    target = declarations[0].identity
    if not inspected or not entries:
        return Finding(
            rule_id="AXL-RESOURCE-PATCH-UNINSPECTED",
            severity="review",
            confidence="medium",
            summary=f"Patch payload overlap needs review: {target}",
            explanation=(
                "At least one patch source could not be serialized or did not expose a "
                "stable inner identity, so declaration-level compatibility is retained."
            ),
            participants=participants,
            evidence=[{"identity": target, "references": [item.to_dict() for item in declarations]}],
        )

    by_inner: dict[str, list[Reference]] = defaultdict(list)
    for entry in entries:
        by_inner[str(entry.details.get("inner_identity") or "").casefold()].append(entry)
    shared: list[tuple[str, list[Reference]]] = []
    conflicts: list[tuple[str, list[Reference]]] = []
    duplicates: list[tuple[str, list[Reference]]] = []
    for identity, refs in by_inner.items():
        if len({item.mod_name for item in refs}) < 2:
            continue
        shared.append((identity, refs))
        fingerprints = {str(item.details.get("fingerprint")) for item in refs}
        if len(fingerprints) > 1:
            conflicts.append((identity, refs))
        else:
            duplicates.append((identity, refs))

    if conflicts:
        return Finding(
            rule_id="AXL-RESOURCE-PATCH-INNER-CONFLICT",
            severity="conflict",
            confidence="medium",
            summary=f"Patch payloads change the same inner identities: {target}",
            explanation=(
                "Multiple mods patch the same target and address the same stable inner "
                "identities with different serialized content. Runtime merge order may "
                "determine the result."
            ),
            participants=participants,
            evidence=[
                {
                    "identity": target,
                    "inner_identity": identity,
                    "references": [item.to_dict() for item in refs],
                }
                for identity, refs in conflicts
            ],
        )
    if duplicates:
        return Finding(
            rule_id="AXL-RESOURCE-PATCH-INNER-DUPLICATE",
            severity="info",
            confidence="medium",
            summary=f"Patch payloads repeat inner identities: {target}",
            explanation=(
                "Multiple mods patch the same target with identical serialized content "
                "for the same stable inner identities."
            ),
            participants=participants,
            evidence=[
                {
                    "identity": target,
                    "inner_identity": identity,
                    "references": [item.to_dict() for item in refs],
                }
                for identity, refs in duplicates
            ],
        )
    return Finding(
        rule_id="AXL-RESOURCE-PATCH-DISJOINT",
        severity="info",
        confidence="medium",
        summary=f"Patch payloads use disjoint inner identities: {target}",
        explanation=(
            "The serialized patch sources address different stable inner identities, "
            "so this shared target appears composable."
        ),
        participants=participants,
        evidence=[
            {
                "identity": target,
                "references": [item.to_dict() for item in declarations],
                "inner_identity_count": len(by_inner),
            }
        ],
    )


def _consolidate_patch_findings(findings: Iterable[Finding]) -> list[Finding]:
    grouped: dict[tuple[str, tuple[str, ...]], list[Finding]] = defaultdict(list)
    for finding in findings:
        grouped[(finding.rule_id, tuple(finding.participants))].append(finding)
    labels = {
        "AXL-RESOURCE-PATCH-DISJOINT": "disjoint patch payload targets",
        "AXL-RESOURCE-PATCH-INNER-CONFLICT": "patch targets with inner conflicts",
        "AXL-RESOURCE-PATCH-INNER-DUPLICATE": "patch targets with duplicate inner data",
        "AXL-RESOURCE-PATCH-UNINSPECTED": "patch targets needing payload review",
    }
    consolidated: list[Finding] = []
    for (rule, participants), items in grouped.items():
        consolidated.append(
            Finding(
                rule_id=rule,
                severity=items[0].severity,
                confidence=items[0].confidence,
                summary=f"{len(items)} {labels[rule]}",
                explanation=items[0].explanation,
                participants=list(participants),
                evidence=[evidence for item in items for evidence in item.evidence],
            )
        )
    return sorted(consolidated, key=lambda item: item.sort_key())


def inspect_resource_patch_payloads(
    declarations: Iterable[Reference],
    manifests: Iterable[ArchiveManifest],
    provider: ArchivePayloadProvider,
    workers: int = 4,
) -> tuple[list[Reference], list[Finding], dict[str, int]]:
    declaration_list = [
        item for item in declarations if item.kind == "resource.patch"
    ]
    by_target: dict[str, list[Reference]] = defaultdict(list)
    for declaration in declaration_list:
        by_target[declaration.normalized_identity].append(declaration)
    shared_targets = {
        target: refs
        for target, refs in by_target.items()
        if len({item.mod_name for item in refs}) > 1
    }

    by_mod_member: dict[tuple[str, str], ArchiveManifest] = {}
    for manifest in manifests:
        for member in manifest.members:
            if member.resolved:
                by_mod_member.setdefault(
                    (manifest.mod_name, member.normalized_path), manifest
                )

    source_declarations: dict[
        tuple[str, str], tuple[Reference, ArchiveManifest | None]
    ] = {}
    for refs in shared_targets.values():
        for declaration in refs:
            source = str(declaration.details.get("source") or "")
            normalized_source = normalize_game_path(source)
            key = (declaration.mod_name, normalized_source)
            source_declarations.setdefault(
                key,
                (
                    declaration,
                    by_mod_member.get((declaration.mod_name, normalized_source)),
                ),
            )

    results: dict[tuple[str, str], SerializedPayloadResult] = {}
    findings: list[Finding] = []
    extractable = {
        key: value
        for key, value in source_declarations.items()
        if value[1] is not None
    }
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(
                provider.serialize_json,
                manifest,
                str(declaration.details.get("source") or ""),
            ): key
            for key, (declaration, manifest) in extractable.items()
            if manifest is not None
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as exc:  # provider boundary
                declaration = source_declarations[key][0]
                findings.append(
                    Finding(
                        rule_id="AXL-PAYLOAD-FAILED",
                        severity="error",
                        confidence="high",
                        summary=f"Could not inspect ArchiveXL patch payload: {declaration.details.get('source')}",
                        explanation=str(exc),
                        participants=[declaration.mod_name],
                        evidence=[declaration.to_dict()],
                    )
                )

    payload_references: list[Reference] = []
    entries_by_target: dict[str, list[Reference]] = defaultdict(list)
    source_has_entries: dict[tuple[str, str], bool] = {}
    extraction_cache_hits = 0
    serialization_cache_hits = 0
    serialized = 0
    reported_failures: set[tuple[str, str]] = set()
    for target, target_declarations in shared_targets.items():
        for declaration in target_declarations:
            source = str(declaration.details.get("source") or "")
            key = (declaration.mod_name, normalize_game_path(source))
            result = results.get(key)
            if result is None or not result.ok:
                source_has_entries[key] = False
                if result is not None and key not in reported_failures:
                    findings.append(payload_failure_finding(result))
                    reported_failures.add(key)
                continue
            if key not in source_has_entries:
                serialized += 1
                extraction_cache_hits += int(result.payload.from_cache)
                serialization_cache_hits += int(result.from_cache)
            parsed, parse_findings = parse_resource_patch_payload(
                declaration, result.data, result.payload.archive_path
            )
            source_has_entries[key] = bool(parsed)
            payload_references.extend(parsed)
            entries_by_target[target].extend(parsed)
            findings.extend(parse_findings)

    target_findings: list[Finding] = []
    outcomes = defaultdict(int)
    for target, target_declarations in shared_targets.items():
        inspected = all(
            source_has_entries.get(
                (
                    declaration.mod_name,
                    normalize_game_path(str(declaration.details.get("source") or "")),
                ),
                False,
            )
            for declaration in target_declarations
        )
        finding = compare_patch_target_entries(
            target_declarations, entries_by_target.get(target, []), inspected
        )
        target_findings.append(finding)
        outcomes[finding.rule_id] += 1
    findings.extend(_consolidate_patch_findings(target_findings))
    stats = {
        "declarations": sum(len(items) for items in shared_targets.values()),
        "shared_targets": len(shared_targets),
        "unique_archive_payloads": len(source_declarations),
        "skipped_without_own_archive": len(source_declarations) - len(extractable),
        "serialized": serialized,
        "failed": sum(
            1
            for key in extractable
            if key not in results or not results[key].ok
        ),
        "entry_references": len(payload_references),
        "extraction_cache_hits": extraction_cache_hits,
        "serialization_cache_hits": serialization_cache_hits,
        "disjoint_targets": outcomes["AXL-RESOURCE-PATCH-DISJOINT"],
        "duplicate_targets": outcomes["AXL-RESOURCE-PATCH-INNER-DUPLICATE"],
        "conflicting_targets": outcomes["AXL-RESOURCE-PATCH-INNER-CONFLICT"],
        "uninspected_targets": outcomes["AXL-RESOURCE-PATCH-UNINSPECTED"],
    }
    return payload_references, findings, stats
