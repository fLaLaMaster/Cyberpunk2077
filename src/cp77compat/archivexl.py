from __future__ import annotations

import json
from collections import Counter, defaultdict
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

RESOURCE_OPERATIONS = {"copy", "fix", "link", "patch", "scope"}

SECTION_COVERAGE = {
    "customizations": (
        "unsupported",
        "Declarations are inventoried but customization identities are not compared yet.",
    ),
    "factories": (
        "partial",
        "Factory resources are resolved; CSV entity definitions are not inspected yet.",
    ),
    "journal": (
        "partial",
        "Journal resources are resolved; entry-tree identities require selective payload inspection.",
    ),
    "localization": (
        "partial",
        "On-screen resources are resolved; localization entries are not inspected yet.",
    ),
    "overrides": (
        "analyzed",
        "Visual-tag component overrides are parsed and same-name definitions are compared.",
    ),
    "player": (
        "unsupported",
        "Player declarations are not interpreted yet.",
    ),
    "quest": (
        "partial",
        "Quest phase merges and attachment points are compared; archive-backed phase and parent resolution requires archive indexing.",
    ),
    "resource": (
        "partial",
        "Resource declarations and overlaps are analyzed; patch payload contents are pending.",
    ),
    "streaming": (
        "partial",
        "Blocks, sectors, and node deletions are analyzed.",
    ),
}


@dataclass(frozen=True, slots=True)
class ArchiveXLTagged:
    tag: str
    value: Any
    line: int | None = None


class ArchiveXLLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


class ArchiveXLMapping(dict[Any, Any]):
    """ArchiveXL mapping with one-based source lines for keys and values."""

    def __init__(self) -> None:
        super().__init__()
        self.key_lines: dict[Any, int] = {}
        self.value_lines: dict[Any, int] = {}


class ArchiveXLSequence(list[Any]):
    """ArchiveXL sequence with one-based source lines for each item."""

    def __init__(self) -> None:
        super().__init__()
        self.item_lines: list[int] = []


def _construct_mapping(
    loader: ArchiveXLLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> ArchiveXLMapping:
    mapping = ArchiveXLMapping()
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in mapping:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=True)
        mapping.key_lines[key] = key_node.start_mark.line + 1
        mapping.value_lines[key] = value_node.start_mark.line + 1
    return mapping


def _construct_sequence(
    loader: ArchiveXLLoader,
    node: yaml.SequenceNode,
    deep: bool = False,
) -> ArchiveXLSequence:
    sequence = ArchiveXLSequence()
    for item_node in node.value:
        sequence.append(loader.construct_object(item_node, deep=True))
        sequence.item_lines.append(item_node.start_mark.line + 1)
    return sequence


def _construct_unknown_tag(
    loader: ArchiveXLLoader,
    suffix: str,
    node: yaml.Node,
) -> ArchiveXLTagged:
    if isinstance(node, yaml.ScalarNode):
        value: Any = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = _construct_sequence(loader, node, deep=True)
    else:
        value = _construct_mapping(loader, node, deep=True)
    return ArchiveXLTagged(
        tag=suffix.lstrip("!").casefold(),
        value=value,
        line=node.start_mark.line + 1,
    )


ArchiveXLLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)
ArchiveXLLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_SEQUENCE_TAG, _construct_sequence
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


def _mapping_line(
    mapping: Any,
    key: Any,
    fallback: int | None = None,
) -> int | None:
    if isinstance(mapping, ArchiveXLMapping):
        return mapping.key_lines.get(key) or mapping.value_lines.get(key) or fallback
    return fallback


def _sequence_entries(value: Any) -> list[tuple[Any, int | None]]:
    if isinstance(value, ArchiveXLSequence):
        return list(zip(value, value.item_lines, strict=True))
    if isinstance(value, list):
        return [(item, None) for item in value]
    return []


def _as_paths(value: Any, fallback_line: int | None = None) -> list[tuple[str, int | None]]:
    if isinstance(value, ArchiveXLTagged):
        if isinstance(value.value, str):
            return [(value.value, value.line or fallback_line)]
        return _as_paths(value.value, value.line or fallback_line)
    if isinstance(value, str):
        return [(value, fallback_line)]
    if isinstance(value, list):
        paths: list[tuple[str, int | None]] = []
        for item, line in _sequence_entries(value):
            paths.extend(_as_paths(item, line or fallback_line))
        return paths
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
        json_shaped = text.lstrip().startswith(("{", "["))
        try:
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
        if used_tab_fallback and not json_shaped:
            findings.append(
                Finding(
                    rule_id="AXL-NONSTANDARD-TABS",
                    severity="info",
                    confidence="high",
                    summary=f"ArchiveXL config contains tab characters: {artifact.relative_path}",
                    explanation=(
                        "The scanner normalized tab whitespace for parsing; the "
                        "original file was not modified."
                    ),
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
                    explanation=(
                        "The scanner does not yet understand these sections; they "
                        "are not necessarily invalid."
                    ),
                    participants=[artifact.mod_name],
                    evidence=[{"path": str(artifact.absolute_path), "sections": unknown}],
                )
            )
        references.extend(_extract_references(document, findings))

    return documents, references, findings


def _reference(
    document: ArchiveXLDocument,
    kind: str,
    identity: str,
    line: int | None = None,
    **details: Any,
) -> Reference:
    return Reference(
        ecosystem="archivexl",
        kind=kind,
        identity=identity,
        mod_name=document.artifact.mod_name,
        source_path=str(document.artifact.absolute_path),
        line=line or _line_for(document.text, identity),
        details=details,
    )


def _tagged_paths(
    value: Any,
    fallback_line: int | None = None,
) -> list[tuple[str, int | None, str | None]]:
    if isinstance(value, ArchiveXLTagged):
        if isinstance(value.value, str):
            return [(value.value, value.line or fallback_line, value.tag)]
        return [
            (path, line, tag or value.tag)
            for path, line, tag in _tagged_paths(
                value.value, value.line or fallback_line
            )
        ]
    if isinstance(value, str):
        return [(value, fallback_line, None)]
    if isinstance(value, list):
        paths: list[tuple[str, int | None, str | None]] = []
        for item, line in _sequence_entries(value):
            paths.extend(_tagged_paths(item, line or fallback_line))
        return paths
    return []


def _resource_shape_finding(
    document: ArchiveXLDocument,
    operation: str,
    explanation: str,
    line: int | None,
) -> Finding:
    return Finding(
        rule_id="AXL-RESOURCE-SHAPE",
        severity="error",
        confidence="high",
        summary=f"Invalid ArchiveXL resource.{operation} declaration",
        explanation=explanation,
        participants=[document.artifact.mod_name],
        evidence=[{"path": str(document.artifact.absolute_path), "line": line}],
    )


def _resource_reference(
    document: ArchiveXLDocument,
    operation: str,
    identity: str,
    line: int | None,
    **details: Any,
) -> Reference:
    return _reference(
        document,
        f"resource.{operation}",
        identity,
        line,
        resource_operation=operation,
        **details,
    )


def _extract_resource_references(
    document: ArchiveXLDocument,
    resource: dict[Any, Any],
    findings: list[Finding],
) -> list[Reference]:
    refs: list[Reference] = []
    for raw_operation, declarations in resource.items():
        operation = str(raw_operation).casefold()
        operation_line = _mapping_line(resource, raw_operation)
        if operation not in RESOURCE_OPERATIONS:
            findings.append(
                Finding(
                    rule_id="AXL-RESOURCE-UNKNOWN-OPERATION",
                    severity="review",
                    confidence="high",
                    summary=f"Unknown ArchiveXL resource operation: {raw_operation}",
                    explanation=(
                        "The operation is inventoried by coverage reporting but its "
                        "semantics are not compared."
                    ),
                    participants=[document.artifact.mod_name],
                    evidence=[
                        {
                            "path": str(document.artifact.absolute_path),
                            "line": operation_line,
                        }
                    ],
                )
            )
            continue
        if not isinstance(declarations, dict):
            findings.append(
                _resource_shape_finding(
                    document,
                    operation,
                    f"resource.{operation} must be a mapping.",
                    operation_line,
                )
            )
            continue

        for raw_source, raw_value in declarations.items():
            if not isinstance(raw_source, str):
                findings.append(
                    _resource_shape_finding(
                        document,
                        operation,
                        "Resource source, target, or scope identifiers must be strings.",
                        _mapping_line(declarations, raw_source, operation_line),
                    )
                )
                continue
            source_line = _mapping_line(declarations, raw_source, operation_line)

            if operation in {"copy", "link"}:
                targets = _tagged_paths(raw_value, source_line)
                if not targets:
                    findings.append(
                        _resource_shape_finding(
                            document,
                            operation,
                            f"resource.{operation}.{raw_source} must list target paths.",
                            source_line,
                        )
                    )
                for target, line, tag in targets:
                    refs.append(
                        _resource_reference(
                            document,
                            operation,
                            target,
                            line,
                            source=raw_source,
                            target=target,
                            target_tag=tag,
                        )
                    )
                continue

            if operation == "scope":
                members = _tagged_paths(raw_value, source_line)
                if not members:
                    findings.append(
                        _resource_shape_finding(
                            document,
                            operation,
                            f"resource.scope.{raw_source} must list scope members.",
                            source_line,
                        )
                    )
                for member, line, tag in members:
                    refs.append(
                        _resource_reference(
                            document,
                            operation,
                            f"{raw_source}#{member}",
                            line,
                            scope=raw_source,
                            member=member,
                            member_tag=tag,
                        )
                    )
                continue

            if operation == "patch":
                properties: list[str] = []
                target_value = raw_value
                if isinstance(raw_value, dict):
                    properties = [
                        path
                        for path, _line in _as_paths(
                            raw_value.get("props"),
                            _mapping_line(raw_value, "props", source_line),
                        )
                    ]
                    target_value = raw_value.get("targets")
                targets = _tagged_paths(target_value, source_line)
                if not targets:
                    findings.append(
                        _resource_shape_finding(
                            document,
                            operation,
                            f"resource.patch.{raw_source} must list patch targets.",
                            source_line,
                        )
                    )
                for target, line, tag in targets:
                    refs.append(
                        _resource_reference(
                            document,
                            operation,
                            target,
                            line,
                            source=raw_source,
                            target=target,
                            properties=properties,
                            target_tag=tag,
                        )
                    )
                continue

            # resource.fix: target -> category -> original value -> replacement
            if not isinstance(raw_value, dict):
                findings.append(
                    _resource_shape_finding(
                        document,
                        operation,
                        f"resource.fix.{raw_source} must be a mapping.",
                        source_line,
                    )
                )
                continue
            for raw_category, replacements in raw_value.items():
                category = str(raw_category)
                category_line = _mapping_line(raw_value, raw_category, source_line)
                if not isinstance(replacements, dict):
                    findings.append(
                        _resource_shape_finding(
                            document,
                            operation,
                            f"resource.fix.{raw_source}.{category} must be a mapping.",
                            category_line,
                        )
                    )
                    continue
                for original, replacement in replacements.items():
                    if not isinstance(original, str) or not isinstance(replacement, str):
                        findings.append(
                            _resource_shape_finding(
                                document,
                                operation,
                                "Resource fix keys and replacements must be strings.",
                                _mapping_line(
                                    replacements, original, category_line
                                ),
                            )
                        )
                        continue
                    refs.append(
                        _resource_reference(
                            document,
                            operation,
                            f"{raw_source}#{category}#{original}",
                            _mapping_line(replacements, original, category_line),
                            target=raw_source,
                            category=category,
                            original=original,
                            replacement=replacement,
                        )
                    )
    return refs


def _quest_shape_finding(
    document: ArchiveXLDocument,
    explanation: str,
    line: int | None,
) -> Finding:
    return Finding(
        rule_id="AXL-QUEST-SHAPE",
        severity="error",
        confidence="high",
        summary="Invalid ArchiveXL quest.phases declaration",
        explanation=explanation,
        participants=[document.artifact.mod_name],
        evidence=[{"path": str(document.artifact.absolute_path), "line": line}],
    )


def _plain_value(value: Any) -> Any:
    """Return a stable JSON-compatible representation of a YAML value."""
    if isinstance(value, ArchiveXLTagged):
        return {"tag": value.tag, "value": _plain_value(value.value)}
    if isinstance(value, dict):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain_value(item) for item in value]
    return value


OVERRIDE_BUILTIN_TAGS = {
    "FlatShoes",
    "HighHeels",
    "hide_Ankles",
    "hide_Arms",
    "hide_Calves",
    "hide_Chest",
    "hide_CollarBone",
    "hide_Feet",
    "hide_Head",
    "hide_Legs",
    "hide_LowerAbdomen",
    "hide_Thighs",
    "hide_Torso",
    "hide_UpperAbdomen",
}
_MASK_64 = (1 << 64) - 1


def _override_shape_finding(
    document: ArchiveXLDocument,
    explanation: str,
    line: int | None,
) -> Finding:
    return Finding(
        rule_id="AXL-OVERRIDE-SHAPE",
        severity="error",
        confidence="high",
        summary="Invalid ArchiveXL overrides.tags declaration",
        explanation=explanation,
        participants=[document.artifact.mod_name],
        evidence=[{"path": str(document.artifact.absolute_path), "line": line}],
    )


def _override_chunks(
    document: ArchiveXLDocument,
    value: Any,
    line: int | None,
) -> tuple[list[int] | None, Finding | None]:
    if not isinstance(value, list):
        return None, _override_shape_finding(
            document,
            "Override hide/show values must be sequences of chunk indices.",
            line,
        )
    chunks: list[int] = []
    for raw_chunk, chunk_line in _sequence_entries(value):
        if isinstance(raw_chunk, bool) or not isinstance(raw_chunk, int):
            return None, _override_shape_finding(
                document,
                "Override chunk indices must be integers from 0 through 63.",
                chunk_line or line,
            )
        if not 0 <= raw_chunk <= 63:
            return None, _override_shape_finding(
                document,
                "Override chunk indices must fit the 64-bit component mask (0 through 63).",
                chunk_line or line,
            )
        chunks.append(raw_chunk)
    return chunks, None


def _override_effective_mask(show: bool, chunks: list[int]) -> int:
    selected = 0
    for chunk in chunks:
        selected |= 1 << chunk
    if show:
        return selected
    return (_MASK_64 ^ selected) if selected else 0


def _extract_override_references(
    document: ArchiveXLDocument,
    overrides: dict[Any, Any],
    findings: list[Finding],
) -> list[Reference]:
    refs: list[Reference] = []
    overrides_line = _mapping_line(document.data, "overrides")
    for raw_operation in overrides:
        if str(raw_operation) != "tags":
            findings.append(
                Finding(
                    rule_id="AXL-OVERRIDE-UNKNOWN-OPERATION",
                    severity="review",
                    confidence="high",
                    summary=f"Unknown ArchiveXL override operation: {raw_operation}",
                    explanation=(
                        "Only overrides.tags is implemented by the installed ArchiveXL "
                        "garment override configuration parser."
                    ),
                    participants=[document.artifact.mod_name],
                    evidence=[{
                        "path": str(document.artifact.absolute_path),
                        "line": _mapping_line(overrides, raw_operation, overrides_line),
                    }],
                )
            )

    tags = overrides.get("tags")
    if tags is None:
        return refs
    tags_line = _mapping_line(overrides, "tags", overrides_line)
    if not isinstance(tags, dict):
        findings.append(
            _override_shape_finding(
                document,
                "overrides.tags must be a mapping of tag names to component definitions.",
                tags_line,
            )
        )
        return refs

    for raw_tag, raw_components in tags.items():
        tag = str(raw_tag)
        tag_line = _mapping_line(tags, raw_tag, tags_line)
        if not tag:
            findings.append(
                _override_shape_finding(document, "Override tag names cannot be empty.", tag_line)
            )
            continue
        if not isinstance(raw_components, dict):
            findings.append(
                _override_shape_finding(
                    document,
                    f"Override tag {tag!r} must map component names to masks.",
                    tag_line,
                )
            )
            continue

        components: list[dict[str, Any]] = []
        for raw_component, raw_mask in raw_components.items():
            component = str(raw_component)
            component_line = _mapping_line(raw_components, raw_component, tag_line)
            if not component:
                findings.append(
                    _override_shape_finding(
                        document, "Override component names cannot be empty.", component_line
                    )
                )
                continue

            operation = "mask"
            show = False
            chunks: list[int] | None = None
            mask: int | None = None
            value_line = component_line
            if isinstance(raw_mask, dict):
                present = [name for name in ("hide", "show") if name in raw_mask]
                unknown_keys = [key for key in raw_mask if str(key) not in {"hide", "show"}]
                if unknown_keys:
                    unknown = [str(key) for key in unknown_keys]
                    findings.append(
                        Finding(
                            rule_id="AXL-OVERRIDE-UNKNOWN-MASK-OPERATION",
                            severity="review",
                            confidence="high",
                            summary=f"Unknown component override operation for {tag}: {component}",
                            explanation=(
                                "ArchiveXL only reads hide or show from a component override mapping."
                            ),
                            participants=[document.artifact.mod_name],
                            evidence=[{
                                "path": str(document.artifact.absolute_path),
                                "line": _mapping_line(raw_mask, unknown_keys[0], component_line),
                                "operations": unknown,
                            }],
                        )
                    )
                if not present:
                    findings.append(
                        _override_shape_finding(
                            document,
                            f"Override component {component!r} requires hide or show.",
                            component_line,
                        )
                    )
                    continue
                if len(present) > 1:
                    findings.append(
                        _override_shape_finding(
                            document,
                            (
                                f"Override component {component!r} declares both hide and show; "
                                "ArchiveXL only applies hide because it checks that operation first."
                            ),
                            _mapping_line(raw_mask, "show", component_line),
                        )
                    )
                operation = present[0]
                show = operation == "show"
                value_line = _mapping_line(raw_mask, operation, component_line)
                chunks, chunk_finding = _override_chunks(
                    document, raw_mask[operation], value_line
                )
                if chunk_finding:
                    findings.append(chunk_finding)
                    continue
                mask = _override_effective_mask(show, chunks or [])
            elif isinstance(raw_mask, list):
                operation = "hide"
                chunks, chunk_finding = _override_chunks(
                    document, raw_mask, component_line
                )
                if chunk_finding:
                    findings.append(chunk_finding)
                    continue
                mask = _override_effective_mask(False, chunks or [])
            else:
                if isinstance(raw_mask, bool):
                    parsed_mask = None
                elif isinstance(raw_mask, int):
                    parsed_mask = raw_mask
                elif isinstance(raw_mask, str) and raw_mask.isdecimal():
                    parsed_mask = int(raw_mask, 10)
                else:
                    parsed_mask = None
                if parsed_mask is None or not 0 <= parsed_mask <= _MASK_64:
                    findings.append(
                        _override_shape_finding(
                            document,
                            (
                                "A scalar component override must be an unsigned decimal "
                                "64-bit mask."
                            ),
                            component_line,
                        )
                    )
                    continue
                mask = parsed_mask

            components.append(
                {
                    "component": component,
                    "operation": operation,
                    "show": show,
                    "mask": mask,
                    "chunks": chunks,
                    "line": value_line,
                }
            )

        if not components:
            continue
        canonical = [
            {
                "component": component["component"],
                "show": component["show"],
                "mask": component["mask"],
            }
            for component in sorted(components, key=lambda item: item["component"])
        ]
        fingerprint = json.dumps(
            canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        refs.append(
            _reference(
                document,
                "override.tag",
                tag,
                tag_line,
                components=components,
                component_count=len(components),
                chunk_references=sum(
                    len(component["chunks"] or []) for component in components
                ),
                fingerprint=fingerprint,
                redefines_builtin=tag in OVERRIDE_BUILTIN_TAGS,
            )
        )
    return refs


def _extract_quest_references(
    document: ArchiveXLDocument,
    quest: dict[Any, Any],
    findings: list[Finding],
) -> list[Reference]:
    phases_line = _mapping_line(quest, "phases", _mapping_line(document.data, "quest"))
    phases = quest.get("phases")
    if not isinstance(phases, list):
        findings.append(
            _quest_shape_finding(
                document,
                "quest.phases must be a sequence of phase merge mappings.",
                phases_line,
            )
        )
        return []

    refs: list[Reference] = []
    for declaration, declaration_line in _sequence_entries(phases):
        if not isinstance(declaration, dict):
            findings.append(
                _quest_shape_finding(
                    document,
                    "Every quest.phases item must be a mapping.",
                    declaration_line or phases_line,
                )
            )
            continue
        path = declaration.get("path")
        parent = declaration.get("parent")
        if not isinstance(path, str) or not isinstance(parent, str):
            findings.append(
                _quest_shape_finding(
                    document,
                    "Every quest phase merge requires string path and parent fields.",
                    declaration_line or phases_line,
                )
            )
            continue

        attachment_keys = [key for key in ("connection", "input") if key in declaration]
        if len(attachment_keys) > 1:
            findings.append(
                _quest_shape_finding(
                    document,
                    "A quest phase merge cannot declare both connection and input.",
                    _mapping_line(declaration, attachment_keys[1], declaration_line),
                )
            )
            continue
        attachment_kind = attachment_keys[0] if attachment_keys else "root"
        attachment = (
            _plain_value(declaration.get(attachment_kind))
            if attachment_keys
            else None
        )
        attachment_key = json.dumps(
            attachment,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        path_line = _mapping_line(declaration, "path", declaration_line)
        parent_line = _mapping_line(declaration, "parent", declaration_line)
        common = {
            "phase": path,
            "phase_line": path_line,
            "parent": parent,
            "parent_line": parent_line,
            "attachment_kind": attachment_kind,
            "attachment": attachment,
            "attachment_key": attachment_key,
        }
        refs.append(_reference(document, "quest.phase", path, path_line, **common))
        refs.append(_reference(document, "quest.parent", parent, parent_line, **common))
    return refs


def _extract_references(document: ArchiveXLDocument, findings: list[Finding]) -> list[Reference]:
    data = document.data
    refs: list[Reference] = []

    resource = data.get("resource")
    if isinstance(resource, dict):
        refs.extend(_extract_resource_references(document, resource, findings))

    quest = data.get("quest")
    if quest is not None:
        if isinstance(quest, dict):
            refs.extend(_extract_quest_references(document, quest, findings))
        else:
            findings.append(
                _quest_shape_finding(
                    document,
                    "quest must be a mapping containing a phases sequence.",
                    _mapping_line(data, "quest"),
                )
            )

    overrides = data.get("overrides")
    if overrides is not None:
        if isinstance(overrides, dict):
            refs.extend(_extract_override_references(document, overrides, findings))
        else:
            findings.append(
                _override_shape_finding(
                    document,
                    "overrides must be a mapping containing a tags mapping.",
                    _mapping_line(data, "overrides"),
                )
            )

    localization = data.get("localization")
    if isinstance(localization, dict):
        onscreens = localization.get("onscreens")
        if isinstance(onscreens, dict):
            for locale, path in onscreens.items():
                locale_line = _mapping_line(onscreens, locale)
                if isinstance(locale, str) and locale.casefold() not in KNOWN_LOCALES:
                    findings.append(
                        Finding(
                            rule_id="AXL-LOCALE",
                            severity="warning",
                            confidence="high",
                            summary=f"Unknown localization code {locale}",
                            explanation=(
                                "The localization key is not one of the documented "
                                "Cyberpunk 2077 language codes."
                            ),
                            participants=[document.artifact.mod_name],
                            evidence=[
                                {
                                    "path": str(document.artifact.absolute_path),
                                    "line": locale_line,
                                }
                            ],
                        )
                    )
                for item, line in _as_paths(path, locale_line):
                    refs.append(
                        _reference(
                            document,
                            "localization.onscreens",
                            item,
                            line,
                            locale=str(locale),
                        )
                    )

    journal = data.get("journal")
    if journal is not None:
        journal_paths = _as_paths(journal, _mapping_line(data, "journal"))
        if not journal_paths:
            findings.append(
                Finding(
                    rule_id="AXL-JOURNAL-SHAPE",
                    severity="error",
                    confidence="high",
                    summary="Invalid ArchiveXL journal declaration",
                    explanation="journal must be a resource path or a sequence of resource paths.",
                    participants=[document.artifact.mod_name],
                    evidence=[
                        {
                            "path": str(document.artifact.absolute_path),
                            "line": _mapping_line(data, "journal"),
                        }
                    ],
                )
            )
        for item, line in journal_paths:
            refs.append(_reference(document, "journal", item, line))

    for item, line in _as_paths(
        data.get("factories"), _mapping_line(data, "factories")
    ):
        refs.append(_reference(document, "factory", item, line))

    streaming = data.get("streaming")
    if isinstance(streaming, dict):
        for item, line in _as_paths(
            streaming.get("blocks"), _mapping_line(streaming, "blocks")
        ):
            refs.append(_reference(document, "streaming.block", item, line))
        sectors = streaming.get("sectors")
        if isinstance(sectors, list):
            for sector, sector_line in _sequence_entries(sectors):
                if not isinstance(sector, dict) or not isinstance(sector.get("path"), str):
                    continue
                path = sector["path"]
                path_line = _mapping_line(sector, "path", sector_line)
                refs.append(
                    _reference(
                        document,
                        "streaming.sector",
                        path,
                        path_line,
                        expected_nodes=sector.get("expectedNodes"),
                    )
                )
                deletions = sector.get("nodeDeletions")
                if isinstance(deletions, list):
                    for deletion, deletion_line in _sequence_entries(deletions):
                        if isinstance(deletion, dict) and deletion.get("index") is not None:
                            index_line = _mapping_line(
                                deletion, "index", deletion_line or path_line
                            )
                            refs.append(
                                _reference(
                                    document,
                                    "streaming.node_deletion",
                                    f"{path}#{deletion['index']}",
                                    index_line,
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
            expected = {
                ref.details.get("expected_nodes")
                for ref in group
                if ref.details.get("expected_nodes") is not None
            }
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
            explanation = (
                "These mods patch the same sectors. Different node operations may "
                "be compatible, so manual review is required."
            )
        else:
            severity = "conflict"
            noun = "streaming node deletion" if count == 1 else "streaming node deletions"
            explanation = (
                "These mods delete the same node indices from the same sectors, "
                "indicating duplicated or overlapping world patches."
            )
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


def compare_quest_references(references: Iterable[Reference]) -> list[Finding]:
    """Compare only identical child/parent quest merges across different mods."""
    by_phase_parent: dict[tuple[str, str], list[Reference]] = defaultdict(list)
    for reference in references:
        if reference.kind != "quest.phase":
            continue
        parent = reference.details.get("parent")
        if isinstance(parent, str):
            by_phase_parent[
                (reference.normalized_identity, normalize_game_path(parent))
            ].append(reference)

    findings: list[Finding] = []
    for (_phase, _parent), group in by_phase_parent.items():
        mods = sorted({reference.mod_name for reference in group}, key=str.casefold)
        if len(mods) < 2:
            continue
        signatures: dict[tuple[str, str], list[Reference]] = defaultdict(list)
        for reference in group:
            signatures[
                (
                    str(reference.details.get("attachment_kind", "root")),
                    str(reference.details.get("attachment_key", "null")),
                )
            ].append(reference)

        duplicate_refs = [
            refs
            for refs in signatures.values()
            if len({reference.mod_name for reference in refs}) > 1
        ]
        for refs in duplicate_refs:
            participants = sorted(
                {reference.mod_name for reference in refs}, key=str.casefold
            )
            findings.append(
                Finding(
                    rule_id="AXL-QUEST-MERGE-DUPLICATE",
                    severity="warning",
                    confidence="high",
                    summary=f"Duplicate quest phase merge: {refs[0].identity}",
                    explanation=(
                        "Multiple mods attach the same child phase to the same parent "
                        "at the same connection or input. The merge may be applied more "
                        "than once and should be reviewed as a duplicated integration."
                    ),
                    participants=participants,
                    evidence=[reference.to_dict() for reference in refs],
                )
            )

        if len(signatures) > 1:
            findings.append(
                Finding(
                    rule_id="AXL-QUEST-ATTACHMENT-OVERLAP",
                    severity="review",
                    confidence="medium",
                    summary=f"Quest phase has competing attachment points: {group[0].identity}",
                    explanation=(
                        "Multiple mods attach the same child phase to the same parent "
                        "using different connection or input descriptors. This may be "
                        "intentional, but it can also insert the same phase more than once."
                    ),
                    participants=mods,
                    evidence=[reference.to_dict() for reference in group],
                )
            )
    return findings


def compare_override_references(references: Iterable[Reference]) -> list[Finding]:
    """Compare global visual-tag definitions using ArchiveXL's last-wins behavior."""
    by_tag: dict[str, list[Reference]] = defaultdict(list)
    findings: list[Finding] = []
    for reference in references:
        if reference.kind == "override.tag":
            # Tag names become REDengine CNames and are case-sensitive.
            by_tag[reference.identity].append(reference)

    for tag, group in by_tag.items():
        builtin_refs = [
            reference
            for reference in group
            if reference.details.get("redefines_builtin")
        ]
        if builtin_refs:
            findings.append(
                Finding(
                    rule_id="AXL-OVERRIDE-BUILTIN-REDEFINED",
                    severity="review",
                    confidence="high",
                    summary=f"Built-in ArchiveXL visual tag is redefined: {tag}",
                    explanation=(
                        "A mod replaces ArchiveXL's built-in definition for this tag. "
                        "Every installed item using the tag can inherit the replacement, "
                        "so the change should be intentional."
                    ),
                    participants=sorted(
                        {reference.mod_name for reference in builtin_refs},
                        key=str.casefold,
                    ),
                    evidence=[reference.to_dict() for reference in builtin_refs],
                )
            )

    overlaps: list[tuple[str, str, str, str, tuple[str, ...], dict[str, Any]]] = []
    for group in by_tag.values():
        participants = tuple(
            sorted({reference.mod_name for reference in group}, key=str.casefold)
        )
        if len(participants) < 2:
            continue
        fingerprints = {
            str(reference.details.get("fingerprint", "")) for reference in group
        }
        if len(fingerprints) == 1:
            rule = "AXL-OVERRIDE-TAG-DUPLICATE"
            severity = "info"
            confidence = "high"
            explanation = (
                "Multiple mods define the same visual tag with the same effective "
                "component masks. ArchiveXL keeps the last definition, but its "
                "behavior is equivalent."
            )
        else:
            rule = "AXL-OVERRIDE-TAG-CONFLICT"
            severity = "conflict"
            confidence = "high"
            explanation = (
                "Multiple mods define the same visual tag differently. ArchiveXL "
                "replaces the entire earlier tag definition with the last loaded "
                "definition, so components from earlier definitions do not compose."
            )
        overlaps.append(
            (
                rule,
                severity,
                confidence,
                explanation,
                participants,
                {
                    "identity": group[0].identity,
                    "references": [reference.to_dict() for reference in group],
                },
            )
        )

    aggregate: dict[
        tuple[str, str, str, str, tuple[str, ...]], list[dict[str, Any]]
    ] = defaultdict(list)
    for rule, severity, confidence, explanation, participants, evidence in overlaps:
        aggregate[(rule, severity, confidence, explanation, participants)].append(
            evidence
        )

    nouns = {
        "AXL-OVERRIDE-TAG-CONFLICT": "conflicting visual-tag definitions",
        "AXL-OVERRIDE-TAG-DUPLICATE": "duplicate visual-tag definitions",
    }
    for (rule, severity, confidence, explanation, participants), evidence in sorted(
        aggregate.items(),
        key=lambda item: (
            item[0][0],
            tuple(participant.casefold() for participant in item[0][4]),
        ),
    ):
        findings.append(
            Finding(
                rule_id=rule,
                severity=severity,
                confidence=confidence,
                summary=f"{len(evidence)} {nouns[rule]}",
                explanation=explanation,
                participants=list(participants),
                evidence=evidence,
            )
        )
    return findings


def compare_resource_references(references: Iterable[Reference]) -> list[Finding]:
    resource_refs = [
        reference
        for reference in references
        if reference.kind.startswith("resource.")
    ]
    by_kind_identity: dict[tuple[str, str], list[Reference]] = defaultdict(list)
    redirects_by_target: dict[str, list[Reference]] = defaultdict(list)
    patches_by_target: dict[str, list[Reference]] = defaultdict(list)
    for reference in resource_refs:
        by_kind_identity[(reference.kind, reference.normalized_identity)].append(
            reference
        )
        if reference.kind in {"resource.copy", "resource.link"}:
            redirects_by_target[reference.normalized_identity].append(reference)
        elif reference.kind == "resource.patch":
            patches_by_target[reference.normalized_identity].append(reference)

    overlaps: list[
        tuple[str, str, str, str, list[str], dict[str, Any]]
    ] = []

    def add_overlap(
        rule: str,
        severity: str,
        confidence: str,
        explanation: str,
        group: list[Reference],
    ) -> None:
        participants = sorted({ref.mod_name for ref in group}, key=str.casefold)
        if len(participants) < 2:
            return
        overlaps.append(
            (
                rule,
                severity,
                confidence,
                explanation,
                participants,
                {
                    "identity": group[0].identity,
                    "references": [reference.to_dict() for reference in group],
                },
            )
        )

    for group in patches_by_target.values():
        add_overlap(
            "AXL-RESOURCE-PATCH-COMPOSABLE",
            "info",
            "medium",
            (
                "ArchiveXL is designed to compose multiple patch sources on one "
                "target. Payload-level identities are not inspected yet, so this "
                "is a confirmed declaration overlap rather than a full payload "
                "compatibility guarantee."
            ),
            group,
        )

    for group in redirects_by_target.values():
        participants = {reference.mod_name for reference in group}
        if len(participants) < 2:
            continue
        mappings = {
            (
                reference.kind,
                normalize_game_path(str(reference.details.get("source", ""))),
            )
            for reference in group
        }
        if len(mappings) > 1:
            add_overlap(
                "AXL-RESOURCE-TARGET-CONFLICT",
                "conflict",
                "high",
                (
                    "Different mods create the same copy/link target from different "
                    "sources or through different redirect operations."
                ),
                group,
            )
        else:
            add_overlap(
                "AXL-RESOURCE-TARGET-DUPLICATE",
                "info",
                "high",
                "Multiple mods declare the same resource redirect.",
                group,
            )

    for (kind, _identity), group in by_kind_identity.items():
        if kind == "resource.fix":
            replacements = {
                str(reference.details.get("replacement")) for reference in group
            }
            if len(replacements) > 1:
                add_overlap(
                    "AXL-RESOURCE-FIX-CONFLICT",
                    "conflict",
                    "high",
                    (
                        "Different mods rewrite the same name or path in the same "
                        "resource to different replacement values."
                    ),
                    group,
                )
        elif kind == "resource.scope":
            add_overlap(
                "AXL-RESOURCE-SCOPE-DUPLICATE",
                "info",
                "high",
                "Multiple mods append the same member to the same resource scope.",
                group,
            )

    for target, patches in patches_by_target.items():
        redirects = redirects_by_target.get(target, [])
        if redirects:
            add_overlap(
                "AXL-RESOURCE-PATCH-REDIRECT",
                "review",
                "medium",
                (
                    "One mod patches a resource path while another creates that path "
                    "through copy/link. Runtime ordering and the resulting payload "
                    "should be reviewed."
                ),
                [*patches, *redirects],
            )

    aggregate: dict[
        tuple[str, str, str, str, tuple[str, ...]], list[dict[str, Any]]
    ] = defaultdict(list)
    for rule, severity, confidence, explanation, participants, evidence in overlaps:
        aggregate[
            (rule, severity, confidence, explanation, tuple(participants))
        ].append(evidence)

    nouns = {
        "AXL-RESOURCE-FIX-CONFLICT": "conflicting resource fixes",
        "AXL-RESOURCE-PATCH-COMPOSABLE": "composable resource patch overlaps",
        "AXL-RESOURCE-PATCH-REDIRECT": "resource patch/redirect overlaps",
        "AXL-RESOURCE-SCOPE-DUPLICATE": "duplicate resource scope members",
        "AXL-RESOURCE-TARGET-CONFLICT": "conflicting resource redirect targets",
        "AXL-RESOURCE-TARGET-DUPLICATE": "duplicate resource redirects",
    }
    findings: list[Finding] = []
    for (rule, severity, confidence, explanation, participants), evidence in sorted(
        aggregate.items(),
        key=lambda item: (
            item[0][0],
            tuple(participant.casefold() for participant in item[0][4]),
        ),
    ):
        findings.append(
            Finding(
                rule_id=rule,
                severity=severity,
                confidence=confidence,
                summary=f"{len(evidence)} {nouns[rule]}",
                explanation=explanation,
                participants=list(participants),
                evidence=evidence,
            )
        )
    return findings


def build_archivexl_coverage(
    documents: Iterable[ArchiveXLDocument],
    references: Iterable[Reference],
) -> dict[str, Any]:
    document_list = list(documents)
    reference_list = list(references)
    section_documents: dict[str, set[str]] = defaultdict(set)
    operation_documents: dict[str, set[str]] = defaultdict(set)
    operation_blocks: Counter[str] = Counter()
    for document in document_list:
        document_id = str(document.artifact.absolute_path)
        for raw_section, value in document.data.items():
            section = str(raw_section).casefold()
            section_documents[section].add(document_id)
            if section == "resource" and isinstance(value, dict):
                for raw_operation in value:
                    operation = str(raw_operation).casefold()
                    operation_documents[operation].add(document_id)
                    operation_blocks[operation] += 1

    reference_counts = Counter(
        str(reference.details.get("resource_operation"))
        for reference in reference_list
        if reference.kind.startswith("resource.")
    )
    sections = []
    for section in sorted(section_documents, key=str.casefold):
        status, note = SECTION_COVERAGE.get(
            section,
            ("unsupported", "Unknown top-level section."),
        )
        sections.append(
            {
                "name": section,
                "documents": len(section_documents[section]),
                "status": status,
                "note": note,
            }
        )
    resource_operations = []
    for operation in sorted(operation_documents, key=str.casefold):
        known = operation in RESOURCE_OPERATIONS
        resource_operations.append(
            {
                "name": operation,
                "documents": len(operation_documents[operation]),
                "blocks": operation_blocks[operation],
                "references": reference_counts[operation],
                "status": "analyzed" if known else "unsupported",
                "note": (
                    "Declaration identities and cross-mod overlaps are analyzed."
                    if known
                    else "Operation semantics are not implemented."
                ),
            }
        )
    quest_phase_refs = [
        reference for reference in reference_list if reference.kind == "quest.phase"
    ]
    quest_operations = []
    if quest_phase_refs:
        quest_operations.append(
            {
                "name": "quest.phases",
                "documents": len({reference.source_path for reference in quest_phase_refs}),
                "declarations": len(quest_phase_refs),
                "phase_own": "pending",
                "phase_cross_mod": "pending",
                "phase_missing": "pending",
                "parent_official": "pending",
                "parent_own": "pending",
                "parent_cross_mod": "pending",
                "parent_missing": "pending",
                "missing_targets": "pending",
                "status": "partial",
                "note": (
                    "Child/parent identities and attachment points are parsed and "
                    "compared; resource resolution requires archive indexing."
                ),
            }
        )
    override_refs = [
        reference for reference in reference_list if reference.kind == "override.tag"
    ]
    override_operations = []
    if "overrides" in section_documents:
        by_tag: dict[str, list[Reference]] = defaultdict(list)
        for reference in override_refs:
            by_tag[reference.identity].append(reference)
        shared = [
            group
            for group in by_tag.values()
            if len({reference.mod_name for reference in group}) > 1
        ]
        duplicate_tags = sum(
            1
            for group in shared
            if len({reference.details.get("fingerprint") for reference in group}) == 1
        )
        conflicting_tags = len(shared) - duplicate_tags
        override_operations.append(
            {
                "name": "overrides.tags",
                "documents": len(section_documents["overrides"]),
                "definitions": len(override_refs),
                "components": sum(
                    int(reference.details.get("component_count", 0))
                    for reference in override_refs
                ),
                "chunk_references": sum(
                    int(reference.details.get("chunk_references", 0))
                    for reference in override_refs
                ),
                "shared_tags": len(shared),
                "duplicate_tags": duplicate_tags,
                "conflicting_tags": conflicting_tags,
                "builtin_redefinitions": sum(
                    bool(reference.details.get("redefines_builtin"))
                    for reference in override_refs
                ),
                "status": "analyzed",
                "note": (
                    "Tag names are case-sensitive. Effective component masks are "
                    "compared using ArchiveXL's whole-definition last-wins behavior."
                ),
            }
        )
    return {
        "documents": len(document_list),
        "sections": sections,
        "resource_operations": resource_operations,
        "quest_operations": quest_operations,
        "override_operations": override_operations,
    }


def resolve_quest_references(
    references: Iterable[Reference],
    manifests: Iterable[ArchiveManifest],
    artifacts: Iterable[Artifact] = (),
) -> tuple[list[Finding], dict[str, Any]]:
    """Resolve quest child phases and custom parent targets against mod resources."""
    by_mod: dict[str, set[str]] = defaultdict(set)
    global_members: dict[str, set[str]] = defaultdict(set)
    for manifest in manifests:
        for member in manifest.members:
            by_mod[manifest.mod_name].add(member.normalized_path)
            global_members[member.normalized_path].add(manifest.mod_name)

    archive_prefix = "archive\\pc\\mod\\"
    for artifact in artifacts:
        normalized = artifact.normalized_path
        candidates = {normalized}
        if normalized.startswith(archive_prefix):
            candidates.add(normalized[len(archive_prefix):])
        for candidate in candidates:
            by_mod[artifact.mod_name].add(candidate)
            global_members[candidate].add(artifact.mod_name)

    phase_refs = [reference for reference in references if reference.kind == "quest.phase"]
    parent_refs = [reference for reference in references if reference.kind == "quest.parent"]
    stats: dict[str, Any] = {
        "name": "quest.phases",
        "documents": len({reference.source_path for reference in phase_refs}),
        "declarations": len(phase_refs),
        "phase_own": 0,
        "phase_cross_mod": 0,
        "phase_missing": 0,
        "parent_official": 0,
        "parent_own": 0,
        "parent_cross_mod": 0,
        "parent_missing": 0,
        "missing_targets": 0,
        "status": "analyzed",
        "note": (
            "Child phase resources and custom parent targets are resolved; official "
            "base, expansion, and DLC parents are recognized without indexing game archives."
        ),
    }
    grouped: dict[
        tuple[str, str, tuple[str, ...]], list[Reference]
    ] = defaultdict(list)

    for reference in [*phase_refs, *parent_refs]:
        identity = reference.normalized_identity
        role = "phase" if reference.kind == "quest.phase" else "parent"
        if role == "parent" and identity.startswith(("base\\", "ep1\\", "dlc\\")):
            stats["parent_official"] += 1
            continue
        if identity in by_mod.get(reference.mod_name, set()):
            stats[f"{role}_own"] += 1
            continue
        providers = tuple(
            sorted(global_members.get(identity, set()), key=str.casefold)
        )
        if providers:
            stats[f"{role}_cross_mod"] += 1
            grouped[(f"cross-{role}", identity, providers)].append(reference)
        else:
            stats[f"{role}_missing"] += 1
            grouped[(f"missing-{role}", identity, ())].append(reference)

    stats["missing_targets"] = len(
        {
            identity
            for (state, identity, _providers) in grouped
            if state.startswith("missing-")
        }
    )
    findings: list[Finding] = []
    for (state, _identity, providers), group in sorted(
        grouped.items(),
        key=lambda item: (item[0][0], item[0][1]),
    ):
        reference = group[0]
        role = "child phase" if state.endswith("phase") else "parent target"
        if state.startswith("cross-"):
            rule_id = (
                "AXL-QUEST-CROSS-MOD-PHASE"
                if state.endswith("phase")
                else "AXL-QUEST-CROSS-MOD-PARENT"
            )
            participants = sorted(
                {item.mod_name for item in group} | set(providers), key=str.casefold
            )
            explanation = (
                f"The declaring mod does not provide this quest {role}, but another "
                "installed mod does. The quest merge therefore has an implicit dependency."
            )
            evidence = [
                {**item.to_dict(), "providers": list(providers)} for item in group
            ]
            summary = f"Quest {role} comes from another mod: {reference.identity}"
        else:
            rule_id = (
                "AXL-QUEST-PHASE-NOT-FOUND"
                if state.endswith("phase")
                else "AXL-QUEST-PARENT-NOT-FOUND"
            )
            participants = sorted({item.mod_name for item in group}, key=str.casefold)
            explanation = (
                f"The quest {role} was not present as a loose mod file or in any "
                "indexed mod archive. ArchiveXL cannot apply declarations that depend on it."
            )
            evidence = [item.to_dict() for item in group]
            summary = f"Quest {role} was not found: {reference.identity}"
        findings.append(
            Finding(
                rule_id=rule_id,
                severity="warning",
                confidence="high",
                summary=summary,
                explanation=explanation,
                participants=participants,
                evidence=evidence,
            )
        )
    return findings, stats


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

    resolvable_kinds = {
        "factory",
        "journal",
        "localization.onscreens",
        "streaming.block",
    }
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
                    explanation=(
                        "The declaring mod does not contain this resource, but "
                        "another installed mod does. This creates an implicit "
                        "dependency."
                    ),
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
                    explanation=(
                        "The referenced resource was not present as a loose mod file "
                        "or in any indexed archive. This can also mean that the "
                        "relevant archive was outside the selected archive scope."
                    ),
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
                explanation=(
                    "Archive load order determines the winning resource. This "
                    "scanner records the overlap but does not override the existing "
                    "archive conflict rules."
                ),
                participants=mods,
                evidence=[{"mod": mod, "archive": archive} for mod, archive in sorted(providers)],
            )
        )
    return findings
