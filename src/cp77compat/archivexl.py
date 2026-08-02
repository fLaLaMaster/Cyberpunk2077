from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml
from yaml.constructor import ConstructorError

from .models import ArchiveManifest, Artifact, Finding, Reference, normalize_game_path


KNOWN_TOP_LEVEL_KEYS = {
    "customizations",
    "factories",
    "journal",
    "localization",
    "overrides",
    "player",
    "quest",
    "resource",
    "streaming",
}

KNOWN_LOCALES = {
    "ar-ar", "cz-cz", "de-de", "en-us", "es-es", "es-mx", "fr-fr",
    "hu-hu", "it-it", "jp-jp", "kr-kr", "pl-pl", "pt-br", "ru-ru",
    "th-th", "tr-tr", "ua-ua", "zh-cn", "zh-tw",
}


class ArchiveXLLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_mapping(loader: ArchiveXLLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


def _construct_unknown_tag(loader: ArchiveXLLoader, _suffix: str, node: yaml.Node) -> Any:
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


ArchiveXLLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)
ArchiveXLLoader.add_multi_constructor("!", _construct_unknown_tag)


@dataclass(slots=True)
class ArchiveXLDocument:
    artifact: Artifact
    data: dict[str, Any]
    text: str


def _line_for(text: str, value: str) -> int | None:
    needle = value.casefold().replace("/", "\\")
    for number, line in enumerate(text.splitlines(), start=1):
        if needle in line.casefold().replace("/", "\\"):
            return number
    return None


def _as_paths(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def parse_documents(artifacts: Iterable[Artifact]) -> tuple[list[ArchiveXLDocument], list[Reference], list[Finding]]:
    documents: list[ArchiveXLDocument] = []
    references: list[Reference] = []
    findings: list[Finding] = []

    for artifact in sorted(artifacts, key=lambda item: str(item.absolute_path).casefold()):
        if artifact.extension != ".xl":
            continue
        text = artifact.absolute_path.read_text(encoding="utf-8-sig", errors="replace")
        if not text.strip():
            is_bundle = "red4ext\\plugins\\archivexl\\bundle" in artifact.normalized_path
            findings.append(
                Finding(
                    rule_id="AXL-EMPTY",
                    severity="info" if is_bundle else "warning",
                    confidence="high",
                    summary=f"Empty ArchiveXL file: {artifact.relative_path}",
                    explanation=(
                        "This is an ArchiveXL framework bundle placeholder."
                        if is_bundle
                        else "The loader configuration contains no operations."
                    ),
                    participants=[artifact.mod_name],
                    evidence=[{"path": str(artifact.absolute_path)}],
                )
            )
            continue
        used_tab_fallback = False
        try:
            if text.lstrip().startswith(("{", "[")):
                loaded = json.loads(text)
            else:
                try:
                    loaded = yaml.load(text, Loader=ArchiveXLLoader)
                except yaml.scanner.ScannerError as exc:
                    if "character '\\t'" not in str(exc):
                        raise
                    loaded = yaml.load(text.replace("\t", "  "), Loader=ArchiveXLLoader)
                    used_tab_fallback = True
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            findings.append(
                Finding(
                    rule_id="AXL-PARSE",
                    severity="error",
                    confidence="high",
                    summary=f"Cannot parse {artifact.relative_path}",
                    explanation=str(exc),
                    participants=[artifact.mod_name],
                    evidence=[
                        {
                            "path": str(artifact.absolute_path),
                            "line": mark.line + 1 if mark is not None else None,
                        }
                    ],
                )
            )
            continue
        except json.JSONDecodeError as exc:
            findings.append(
                Finding(
                    rule_id="AXL-PARSE",
                    severity="error",
                    confidence="high",
                    summary=f"Cannot parse {artifact.relative_path}",
                    explanation=str(exc),
                    participants=[artifact.mod_name],
                    evidence=[{"path": str(artifact.absolute_path), "line": exc.lineno}],
                )
            )
            continue
        if not isinstance(loaded, dict):
            findings.append(
                Finding(
                    rule_id="AXL-ROOT-TYPE",
                    severity="error",
                    confidence="high",
                    summary=f"ArchiveXL root is not a mapping: {artifact.relative_path}",
                    explanation="ArchiveXL loader configuration must have named top-level sections.",
                    participants=[artifact.mod_name],
                    evidence=[{"path": str(artifact.absolute_path)}],
                )
            )
            continue

        document = ArchiveXLDocument(artifact=artifact, data=loaded, text=text)
        documents.append(document)
        if used_tab_fallback:
            findings.append(
                Finding(
                    rule_id="AXL-NONSTANDARD-TABS",
                    severity="info",
                    confidence="high",
                    summary=f"ArchiveXL YAML contains tab characters: {artifact.relative_path}",
                    explanation="The scanner normalized tabs for parsing; the original file was not modified.",
                    participants=[artifact.mod_name],
                    evidence=[{"path": str(artifact.absolute_path)}],
                )
            )
        unknown = sorted(
            (str(key) for key in loaded if str(key).casefold() not in KNOWN_TOP_LEVEL_KEYS),
            key=str.casefold,
        )
        if unknown:
            findings.append(
                Finding(
                    rule_id="AXL-UNKNOWN-SECTION",
                    severity="review",
                    confidence="medium",
                    summary=f"Unknown ArchiveXL section(s) in {artifact.relative_path}",
                    explanation="The scanner does not yet understand these sections; they are not necessarily invalid.",
                    participants=[artifact.mod_name],
                    evidence=[{"path": str(artifact.absolute_path), "sections": unknown}],
                )
            )
        references.extend(_extract_references(document, findings))

    return documents, references, findings


def _reference(document: ArchiveXLDocument, kind: str, identity: str, **details: Any) -> Reference:
    return Reference(
        ecosystem="archivexl",
        kind=kind,
        identity=identity,
        mod_name=document.artifact.mod_name,
        source_path=str(document.artifact.absolute_path),
        line=_line_for(document.text, identity),
        details=details,
    )


def _extract_references(document: ArchiveXLDocument, findings: list[Finding]) -> list[Reference]:
    data = document.data
    refs: list[Reference] = []

    localization = data.get("localization")
    if isinstance(localization, dict):
        onscreens = localization.get("onscreens")
        if isinstance(onscreens, dict):
            for locale, path in onscreens.items():
                if isinstance(locale, str) and locale.casefold() not in KNOWN_LOCALES:
                    findings.append(
                        Finding(
                            rule_id="AXL-LOCALE",
                            severity="warning",
                            confidence="high",
                            summary=f"Unknown localization code {locale}",
                            explanation="The localization key is not one of the documented Cyberpunk 2077 language codes.",
                            participants=[document.artifact.mod_name],
                            evidence=[{"path": str(document.artifact.absolute_path), "line": _line_for(document.text, str(locale))}],
                        )
                    )
                for item in _as_paths(path):
                    refs.append(_reference(document, "localization.onscreens", item, locale=str(locale)))

    for item in _as_paths(data.get("factories")):
        refs.append(_reference(document, "factory", item))

    streaming = data.get("streaming")
    if isinstance(streaming, dict):
        for item in _as_paths(streaming.get("blocks")):
            refs.append(_reference(document, "streaming.block", item))
        sectors = streaming.get("sectors")
        if isinstance(sectors, list):
            for sector in sectors:
                if not isinstance(sector, dict) or not isinstance(sector.get("path"), str):
                    continue
                path = sector["path"]
                refs.append(
                    _reference(
                        document,
                        "streaming.sector",
                        path,
                        expected_nodes=sector.get("expectedNodes"),
                    )
                )
                deletions = sector.get("nodeDeletions")
                if isinstance(deletions, list):
                    for deletion in deletions:
                        if isinstance(deletion, dict) and deletion.get("index") is not None:
                            refs.append(
                                _reference(
                                    document,
                                    "streaming.node_deletion",
                                    f"{path}#{deletion['index']}",
                                    sector=path,
                                    index=deletion["index"],
                                    node_type=deletion.get("type"),
                                )
                            )
    return refs


def compare_references(references: Iterable[Reference]) -> list[Finding]:
    findings: list[Finding] = []
    aggregate: dict[tuple[str, tuple[str, ...]], list[tuple[str, list[Reference]]]] = defaultdict(list)
    grouped: dict[tuple[str, str], list[Reference]] = defaultdict(list)
    for ref in references:
        grouped[(ref.kind, ref.normalized_identity)].append(ref)

    for (kind, _identity), group in grouped.items():
        mods = sorted({ref.mod_name for ref in group}, key=str.casefold)
        if len(mods) < 2:
            continue
        first = group[0]
        if kind == "streaming.block":
            severity, rule, explanation = (
                "warning",
                "AXL-STREAMING-BLOCK-DUPLICATE",
                "Multiple mods register the same streaming block resource path.",
            )
        elif kind == "streaming.sector":
            expected = {ref.details.get("expected_nodes") for ref in group if ref.details.get("expected_nodes") is not None}
            if len(expected) > 1:
                severity, rule, explanation = (
                    "conflict",
                    "AXL-SECTOR-EXPECTED-NODES",
                    f"The same sector is patched with different expectedNodes values: {sorted(expected)}.",
                )
            else:
                severity, rule, explanation = (
                    "review",
                    "AXL-SECTOR-MULTI-PATCH",
                    "Multiple mods patch the same streaming sector; operations may still be additive.",
                )
        elif kind == "streaming.node_deletion":
            severity, rule, explanation = (
                "conflict",
                "AXL-NODE-DELETION-DUPLICATE",
                "Multiple mods delete the same node index from the same streaming sector.",
            )
        else:
            continue
        if rule in {"AXL-SECTOR-MULTI-PATCH", "AXL-NODE-DELETION-DUPLICATE"}:
            aggregate[(rule, tuple(mods))].append((first.identity, group))
            continue
        findings.append(
            Finding(
                rule_id=rule,
                severity=severity,
                confidence="high" if severity == "conflict" else "medium",
                summary=f"ArchiveXL overlap: {first.identity}",
                explanation=explanation,
                participants=mods,
                evidence=[ref.to_dict() for ref in group],
            )
        )

    for (rule, mods), overlaps in sorted(
        aggregate.items(), key=lambda item: (item[0][0], tuple(value.casefold() for value in item[0][1]))
    ):
        count = len(overlaps)
        if rule == "AXL-SECTOR-MULTI-PATCH":
            severity = "review"
            noun = "streaming sector" if count == 1 else "streaming sectors"
            explanation = "These mods patch the same sectors. Different node operations may be compatible, so manual review is required."
        else:
            severity = "conflict"
            noun = "streaming node deletion" if count == 1 else "streaming node deletions"
            explanation = "These mods delete the same node indices from the same sectors, indicating duplicated or overlapping world patches."
        findings.append(
            Finding(
                rule_id=rule,
                severity=severity,
                confidence="high" if severity == "conflict" else "medium",
                summary=f"{count} overlapping {noun}",
                explanation=explanation,
                participants=list(mods),
                evidence=[
                    {
                        "identity": identity,
                        "references": [
                            {
                                "mod_name": ref.mod_name,
                                "source_path": ref.source_path,
                                "line": ref.line,
                                "details": ref.details,
                            }
                            for ref in refs
                        ],
                    }
                    for identity, refs in overlaps
                ],
            )
        )
    return findings


def resolve_archive_references(
    references: Iterable[Reference],
    manifests: Iterable[ArchiveManifest],
    artifacts: Iterable[Artifact] = (),
) -> list[Finding]:
    findings: list[Finding] = []
    by_mod: dict[str, dict[str, list[ArchiveManifest]]] = defaultdict(lambda: defaultdict(list))
    global_members: dict[str, set[str]] = defaultdict(set)
    for manifest in manifests:
        for member in manifest.members:
            by_mod[manifest.mod_name][member.normalized_path].append(manifest)
            global_members[member.normalized_path].add(manifest.mod_name)

    loose_by_mod: dict[str, set[str]] = defaultdict(set)
    loose_global: dict[str, set[str]] = defaultdict(set)
    archive_prefix = "archive\\pc\\mod\\"
    for artifact in artifacts:
        normalized = artifact.normalized_path
        candidates = {normalized}
        if normalized.startswith(archive_prefix):
            candidates.add(normalized[len(archive_prefix):])
        for candidate in candidates:
            loose_by_mod[artifact.mod_name].add(candidate)
            loose_global[candidate].add(artifact.mod_name)

    resolvable_kinds = {"factory", "localization.onscreens", "streaming.block"}
    for ref in references:
        if ref.kind not in resolvable_kinds:
            continue
        identity = ref.normalized_identity
        if identity in by_mod.get(ref.mod_name, {}) or identity in loose_by_mod.get(ref.mod_name, set()):
            continue
        providers = sorted(
            global_members.get(identity, set()) | loose_global.get(identity, set()),
            key=str.casefold,
        )
        if providers:
            findings.append(
                Finding(
                    rule_id="AXL-CROSS-MOD-RESOURCE",
                    severity="warning",
                    confidence="high",
                    summary=f"ArchiveXL resource comes from another mod: {ref.identity}",
                    explanation="The declaring mod does not contain this resource, but another installed mod does. This creates an implicit dependency.",
                    participants=[ref.mod_name, *providers],
                    evidence=[ref.to_dict(), {"providers": providers}],
                )
            )
        else:
            findings.append(
                Finding(
                    rule_id="AXL-RESOURCE-NOT-INDEXED",
                    severity="warning",
                    confidence="medium",
                    summary=f"ArchiveXL resource was not found: {ref.identity}",
                    explanation="The referenced resource was not present as a loose mod file or in any indexed archive. This can also mean that the relevant archive was outside the selected archive scope.",
                    participants=[ref.mod_name],
                    evidence=[ref.to_dict()],
                )
            )
    return findings


def internal_archive_collisions(manifests: Iterable[ArchiveManifest]) -> list[Finding]:
    grouped: dict[str, list[tuple[str, str]]] = defaultdict(list)
    display_path: dict[str, str] = {}
    for manifest in manifests:
        for member in manifest.members:
            normalized = member.normalized_path
            display_path.setdefault(normalized, member.path)
            grouped[normalized].append((manifest.mod_name, manifest.archive_path))

    findings: list[Finding] = []
    for normalized, providers in grouped.items():
        mods = sorted({item[0] for item in providers}, key=str.casefold)
        if len(mods) < 2:
            continue
        findings.append(
            Finding(
                rule_id="ARCHIVE-INTERNAL-PATH",
                severity="info",
                confidence="high",
                summary=f"Multiple archives contain {display_path[normalized]}",
                explanation="Archive load order determines the winning resource. This scanner records the overlap but does not override the existing archive conflict rules.",
                participants=mods,
                evidence=[{"mod": mod, "archive": archive} for mod, archive in sorted(providers)],
            )
        )
    return findings
