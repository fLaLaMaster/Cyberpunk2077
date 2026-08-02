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
from .models import ArchiveManifest, Finding, Reference


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
