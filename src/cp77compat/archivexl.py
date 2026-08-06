from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
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
        "partial",
        "Male and female customization resources are resolved; option, group, and choice identities require selective payload inspection.",
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
        "analyzed",
        "Body-type registrations and their case-sensitive Body:<name> tag identities are parsed and compared.",
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
        "analyzed",
        "Blocks, sectors, node mutations, element mutations, and full/partial node deletions are analyzed.",
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
    logical_mod_name: str | None = None

    @property
    def mod_name(self) -> str:
        return self.logical_mod_name or self.artifact.mod_name


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


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip(), 10)
        except ValueError:
            return None
    return None


def _yaml_scalar_text(value: Any) -> str | None:
    """Match yaml-cpp's acceptance of any non-null YAML scalar."""
    if isinstance(value, ArchiveXLTagged):
        return _yaml_scalar_text(value.value)
    if value is None or isinstance(value, (dict, list)):
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _float_vector(value: Any, lengths: set[int]) -> list[float] | None:
    if not isinstance(value, list) or len(value) not in lengths:
        return None
    result: list[float] = []
    for item in value:
        if isinstance(item, bool):
            return None
        try:
            result.append(float(item))
        except (TypeError, ValueError):
            return None
    return result


_NODE_MUTATION_FIELDS = {
    "index", "type", "position", "orientation", "scale",
    "nbNodesUnderProxyDiff", "resource", "mesh", "meshRef", "material",
    "effect", "entityTemplate", "appearance", "appearanceName",
    "meshAppearance", "recordID", "recordId", "objectRecordId",
    "actorMutations", "expectedActors", "instanceMutations",
    "expectedInstances",
}
_ELEMENT_MUTATION_FIELDS = {"index", "position", "orientation", "scale"}
_ELEMENT_MUTATION_TYPES = {
    "worldCollisionNode",
    "worldInstancedMeshNode",
    "worldInstancedDestructibleMeshNode",
}


def _extract_node_mutations(
    document: ArchiveXLDocument,
    sector: dict[str, Any],
    sector_line: int | None,
    findings: list[Finding],
) -> list[Reference]:
    mutations = sector.get("nodeMutations")
    if not isinstance(mutations, list):
        return []

    path = sector.get("path")
    if not isinstance(path, str):
        return []
    expected_nodes = _integer(sector.get("expectedNodes"))
    refs: list[Reference] = []
    shape_evidence: list[dict[str, Any]] = []
    unknown_evidence: list[dict[str, Any]] = []
    ignored_evidence: list[dict[str, Any]] = []

    for mutation, mutation_line in _sequence_entries(mutations):
        if not isinstance(mutation, dict):
            shape_evidence.append({
                "path": str(document.artifact.absolute_path),
                "line": mutation_line or sector_line,
                "reason": "node mutation is not a mapping",
            })
            continue

        index_line = _mapping_line(mutation, "index", mutation_line or sector_line)
        node_index = _integer(mutation.get("index"))
        node_type = _yaml_scalar_text(mutation.get("type"))
        if (
            node_index is None
            or node_type is None
            or node_index < 0
            or (expected_nodes is not None and expected_nodes > 0 and node_index >= expected_nodes)
        ):
            shape_evidence.append({
                "path": str(document.artifact.absolute_path),
                "line": index_line,
                "reason": "node mutation has an invalid type or index",
            })
            continue

        for raw_field in mutation:
            field = str(raw_field)
            if field not in _NODE_MUTATION_FIELDS:
                unknown_evidence.append({
                    "path": str(document.artifact.absolute_path),
                    "line": _mapping_line(mutation, raw_field, mutation_line),
                    "field": field,
                    "identity": f"{path}#{node_index}",
                })

        writes: dict[str, Any] = {}
        invalid_vector = False
        for field, lengths in (
            ("position", {3, 4}),
            ("orientation", {4}),
            ("scale", {3}),
        ):
            if field not in mutation:
                continue
            vector = _float_vector(mutation[field], lengths)
            if vector is None:
                shape_evidence.append({
                    "path": str(document.artifact.absolute_path),
                    "line": _mapping_line(mutation, field, mutation_line),
                    "reason": f"invalid {field} vector",
                    "identity": f"{path}#{node_index}",
                })
                invalid_vector = True
                break
            if field == "position":
                vector = [*vector[:3], 0.0]
            writes[field] = vector
        if invalid_vector:
            continue

        if "nbNodesUnderProxyDiff" in mutation:
            proxy_diff = _integer(mutation.get("nbNodesUnderProxyDiff"))
            if proxy_diff is None:
                shape_evidence.append({
                    "path": str(document.artifact.absolute_path),
                    "line": _mapping_line(mutation, "nbNodesUnderProxyDiff", mutation_line),
                    "reason": "invalid nbNodesUnderProxyDiff scalar",
                    "identity": f"{path}#{node_index}",
                })
                continue
            if proxy_diff > 0:
                writes["proxy_nodes_add"] = proxy_diff
            else:
                ignored_evidence.append({
                    "path": str(document.artifact.absolute_path),
                    "line": _mapping_line(mutation, "nbNodesUnderProxyDiff", mutation_line),
                    "identity": f"{path}#{node_index}",
                    "operation": f"nbNodesUnderProxyDiff: {proxy_diff}",
                    "reason": "ArchiveXL applies only positive proxy-node deltas",
                })

        for target, aliases in (
            ("resource", ("resource", "mesh", "meshRef", "material", "effect", "entityTemplate")),
            ("appearance", ("appearance", "appearanceName", "meshAppearance")),
            ("record_id", ("recordID", "recordId", "objectRecordId")),
        ):
            for alias in aliases:
                if alias not in mutation:
                    continue
                value = _yaml_scalar_text(mutation[alias])
                if value is not None:
                    writes[target] = value

        element_mutations: list[dict[str, Any]] = []
        effective_expected_elements: int | None = None
        for collection_field, count_field, element_kind in (
            ("actorMutations", "expectedActors", "actor"),
            ("instanceMutations", "expectedInstances", "instance"),
        ):
            if collection_field not in mutation:
                continue
            collection = mutation.get(collection_field)
            expected_elements = _integer(mutation.get(count_field))
            if not isinstance(collection, list) or expected_elements is None or expected_elements <= 0:
                ignored_evidence.append({
                    "path": str(document.artifact.absolute_path),
                    "line": _mapping_line(mutation, collection_field, mutation_line),
                    "identity": f"{path}#{node_index}",
                    "operation": collection_field,
                    "reason": f"ArchiveXL requires a sequence and positive {count_field}",
                })
                continue
            effective_expected_elements = expected_elements
            for element, element_line in _sequence_entries(collection):
                if not isinstance(element, dict):
                    ignored_evidence.append({
                        "path": str(document.artifact.absolute_path),
                        "line": element_line or _mapping_line(mutation, collection_field, mutation_line),
                        "identity": f"{path}#{node_index}",
                        "operation": collection_field,
                        "reason": "ArchiveXL requires each element mutation to be a mapping",
                    })
                    continue
                element_index = _integer(element.get("index"))
                if element_index is None or not 0 <= element_index < expected_elements:
                    ignored_evidence.append({
                        "path": str(document.artifact.absolute_path),
                        "line": _mapping_line(element, "index", element_line),
                        "identity": f"{path}#{node_index}",
                        "operation": collection_field,
                        "reason": "element mutation index is invalid or outside the expected count",
                    })
                    continue
                for raw_field in element:
                    field = str(raw_field)
                    if field not in _ELEMENT_MUTATION_FIELDS:
                        unknown_evidence.append({
                            "path": str(document.artifact.absolute_path),
                            "line": _mapping_line(element, raw_field, element_line),
                            "field": field,
                            "identity": f"{path}#{node_index}#{element_index}",
                        })
                element_writes: dict[str, Any] = {}
                element_invalid = False
                for field, lengths in (
                    ("position", {4}),
                    ("orientation", {4}),
                    ("scale", {3}),
                ):
                    if field not in element:
                        continue
                    vector = _float_vector(element[field], lengths)
                    if vector is None:
                        ignored_evidence.append({
                            "path": str(document.artifact.absolute_path),
                            "line": _mapping_line(element, field, element_line),
                            "identity": f"{path}#{node_index}#{element_index}",
                            "operation": field,
                            "reason": "invalid element mutation vector",
                        })
                        element_invalid = True
                        break
                    if field == "position":
                        vector = [*vector[:3], 0.0]
                    element_writes[field] = vector
                if element_invalid or not element_writes:
                    continue
                effective_writes = dict(element_writes)
                if node_type in {"worldCollisionNode", "worldInstancedDestructibleMeshNode"}:
                    effective_writes.pop("scale", None)
                if node_type not in _ELEMENT_MUTATION_TYPES:
                    effective_writes.clear()
                if not effective_writes:
                    ignored_evidence.append({
                        "path": str(document.artifact.absolute_path),
                        "line": element_line,
                        "identity": f"{path}#{node_index}#{element_index}",
                        "operation": collection_field,
                        "reason": f"ArchiveXL does not apply these element properties to {node_type}",
                    })
                    continue
                element_mutation = {
                    "element_index": element_index,
                    "element_kind": element_kind,
                    "writes": effective_writes,
                    "line": _mapping_line(element, "index", element_line),
                }
                element_mutations.append(element_mutation)
                refs.append(
                    _reference(
                        document,
                        "streaming.node_element_mutation",
                        f"{path}#{node_index}#{element_index}",
                        element_mutation["line"],
                        sector=path,
                        node_index=node_index,
                        node_type=node_type,
                        expected_elements=expected_elements,
                        element_index=element_index,
                        element_kind=element_kind,
                        writes=effective_writes,
                    )
                )

        refs.append(
            _reference(
                document,
                "streaming.node_mutation",
                f"{path}#{node_index}",
                index_line,
                sector=path,
                index=node_index,
                node_type=node_type,
                writes=writes,
                expected_elements=effective_expected_elements,
                element_mutations=element_mutations,
            )
        )

    for rule_id, severity, summary, explanation, evidence in (
        (
            "AXL-NODE-MUTATION-SHAPE", "error",
            "Invalid ArchiveXL streaming node mutations",
            "ArchiveXL skips a whole node mutation when its required index/type or transform vector has an invalid shape.",
            shape_evidence,
        ),
        (
            "AXL-NODE-MUTATION-UNKNOWN-FIELD", "warning",
            "ArchiveXL node mutation fields are ignored",
            "The installed ArchiveXL WorldStreaming parser does not read these fields, so the intended changes are not applied.",
            unknown_evidence,
        ),
        (
            "AXL-NODE-MUTATION-IGNORED", "warning",
            "ArchiveXL node mutation operations are ignored",
            "The installed ArchiveXL parser or application path accepts the surrounding declaration but does not apply these operations.",
            ignored_evidence,
        ),
    ):
        if evidence:
            findings.append(
                Finding(
                    rule_id=rule_id,
                    severity=severity,
                    confidence="high",
                    summary=f"{summary}: {len(evidence)} occurrence(s)",
                    explanation=explanation,
                    participants=[document.mod_name],
                    evidence=evidence,
                )
            )
    return refs


def _consolidate_node_mutation_parse_findings(
    items: Iterable[Finding],
) -> list[Finding]:
    grouped: dict[str, list[Finding]] = defaultdict(list)
    for item in items:
        grouped[item.rule_id].append(item)
    consolidated: list[Finding] = []
    for rule_id, group in grouped.items():
        first = group[0]
        evidence = [entry for item in group for entry in item.evidence]
        summary = first.summary.rsplit(": ", 1)[0]
        consolidated.append(
            Finding(
                rule_id=rule_id,
                severity=first.severity,
                confidence=first.confidence,
                summary=f"{summary}: {len(evidence)} occurrence(s)",
                explanation=first.explanation,
                participants=first.participants,
                evidence=evidence,
            )
        )
    return consolidated


def _small_override_origin(
    winner: Artifact,
    overridden: list[Artifact],
    text_by_path: dict[Path, str],
) -> str | None:
    """Return a unique logical owner for a small or deletion-only override."""
    if len(overridden) != 1:
        return None
    original = overridden[0]
    winner_lines = text_by_path[winner.absolute_path].splitlines()
    original_lines = text_by_path[original.absolute_path].splitlines()
    opcodes = SequenceMatcher(
        None, original_lines, winner_lines, autojunk=False
    ).get_opcodes()
    changed_lines = sum(
        (winner_end - winner_start) + (original_end - original_start)
        for opcode, original_start, original_end, winner_start, winner_end
        in opcodes
        if opcode != "equal"
    )
    deletion_only = any(opcode == "delete" for opcode, *_rest in opcodes) and all(
        opcode in {"equal", "delete"} for opcode, *_rest in opcodes
    )
    return original.mod_name if changed_lines <= 20 or deletion_only else None


def parse_documents(artifacts: Iterable[Artifact]) -> tuple[list[ArchiveXLDocument], list[Reference], list[Finding]]:
    documents: list[ArchiveXLDocument] = []
    references: list[Reference] = []
    findings: list[Finding] = []

    archive_xl_artifacts = sorted(
        (artifact for artifact in artifacts if artifact.extension == ".xl"),
        key=lambda item: str(item.absolute_path).casefold(),
    )
    by_deployed_path: dict[str, list[Artifact]] = defaultdict(list)
    text_by_path: dict[Path, str] = {}
    for artifact in archive_xl_artifacts:
        by_deployed_path[artifact.normalized_path].append(artifact)
        text_by_path[artifact.absolute_path] = artifact.absolute_path.read_text(
            encoding="utf-8-sig", errors="replace"
        )

    logical_owners: dict[Path, str] = {}
    for group in by_deployed_path.values():
        winners = [item for item in group if item.deployed_state != "overridden"]
        overridden = [item for item in group if item.deployed_state == "overridden"]
        if len(winners) == 1:
            origin = _small_override_origin(winners[0], overridden, text_by_path)
            if origin is not None:
                logical_owners[winners[0].absolute_path] = origin

    for artifact in archive_xl_artifacts:
        if artifact.deployed_state == "overridden":
            continue
        text = text_by_path[artifact.absolute_path]
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

        document = ArchiveXLDocument(
            artifact=artifact,
            data=loaded,
            text=text,
            logical_mod_name=logical_owners.get(artifact.absolute_path),
        )
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
                    participants=[document.mod_name],
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
                    participants=[document.mod_name],
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
        mod_name=document.mod_name,
        source_path=str(document.artifact.absolute_path),
        line=line or _line_for(document.text, identity),
        details={
            **details,
            "deployed_state": document.artifact.deployed_state,
            "deployed_mod_name": document.artifact.mod_name,
            **(
                {"override_origin": document.logical_mod_name}
                if document.logical_mod_name is not None
                else {}
            ),
        },
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
        participants=[document.mod_name],
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
                    participants=[document.mod_name],
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
        participants=[document.mod_name],
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
        participants=[document.mod_name],
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
                    participants=[document.mod_name],
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
                            participants=[document.mod_name],
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

    player = data.get("player")
    player_line = _mapping_line(data, "player")
    if "player" in data:
        invalid_lines: list[int | None] = []
        body_types: list[tuple[str, int | None]] = []
        if not isinstance(player, dict):
            invalid_lines.append(player_line)
        else:
            has_body_types = "bodyTypes" in player
            raw_body_types = player.get("bodyTypes")
            body_types_line = _mapping_line(player, "bodyTypes", player_line)
            if isinstance(raw_body_types, list):
                for value, line in _sequence_entries(raw_body_types):
                    body_type = _yaml_scalar_text(value)
                    if body_type is None:
                        invalid_lines.append(line or body_types_line)
                    else:
                        body_types.append((body_type, line or body_types_line))
            elif has_body_types:
                body_type = _yaml_scalar_text(raw_body_types)
                if body_type is None:
                    invalid_lines.append(body_types_line)
                else:
                    body_types.append((body_type, body_types_line))

        if invalid_lines:
            findings.append(
                Finding(
                    rule_id="AXL-PLAYER-SHAPE",
                    severity="error",
                    confidence="high",
                    summary="Invalid ArchiveXL player.bodyTypes declaration",
                    explanation=(
                        "ArchiveXL expects player.bodyTypes to be a scalar body-type "
                        "name or a sequence containing only scalar names. Valid scalar "
                        "items in a mixed sequence are still registered."
                    ),
                    participants=[document.mod_name],
                    evidence=[
                        {
                            "path": str(document.artifact.absolute_path),
                            "line": line,
                        }
                        for line in invalid_lines
                    ],
                )
            )
        for body_type, line in body_types:
            refs.append(
                _reference(
                    document,
                    "player.body_type",
                    body_type,
                    line,
                    body_tag=f"Body:{body_type}",
                )
            )

    customizations = data.get("customizations")
    customization_line = _mapping_line(data, "customizations")
    if customizations is not None:
        if not isinstance(customizations, dict):
            findings.append(
                Finding(
                    rule_id="AXL-CUSTOMIZATION-SHAPE",
                    severity="error",
                    confidence="high",
                    summary="Invalid ArchiveXL customizations declaration",
                    explanation=(
                        "customizations must be a mapping containing male and/or "
                        "female resource paths."
                    ),
                    participants=[document.mod_name],
                    evidence=[
                        {
                            "path": str(document.artifact.absolute_path),
                            "line": customization_line,
                        }
                    ],
                )
            )
        else:
            for raw_gender, value in customizations.items():
                gender_line = _mapping_line(customizations, raw_gender, customization_line)
                gender = str(raw_gender)
                if gender not in {"female", "male"}:
                    findings.append(
                        Finding(
                            rule_id="AXL-CUSTOMIZATION-UNKNOWN-GENDER",
                            severity="error",
                            confidence="high",
                            summary=f"Unknown ArchiveXL customization gender: {gender}",
                            explanation=(
                                "ArchiveXL accepts only the exact customizations keys "
                                "female and male."
                            ),
                            participants=[document.mod_name],
                            evidence=[
                                {
                                    "path": str(document.artifact.absolute_path),
                                    "line": gender_line,
                                }
                            ],
                        )
                    )
                    continue
                paths = _as_paths(value, gender_line)
                if not paths:
                    findings.append(
                        Finding(
                            rule_id="AXL-CUSTOMIZATION-SHAPE",
                            severity="error",
                            confidence="high",
                            summary=f"Invalid ArchiveXL {gender} customization declaration",
                            explanation=(
                                "A customization gender must contain a resource path "
                                "or a sequence of resource paths."
                            ),
                            participants=[document.mod_name],
                            evidence=[
                                {
                                    "path": str(document.artifact.absolute_path),
                                    "line": gender_line,
                                }
                            ],
                        )
                    )
                    continue
                for item, line in paths:
                    refs.append(
                        _reference(
                            document,
                            "customization",
                            item,
                            line,
                            gender=gender,
                        )
                    )

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
                            participants=[document.mod_name],
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
                    participants=[document.mod_name],
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
    mutation_parse_findings: list[Finding] = []
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
                expected_nodes = _integer(sector.get("expectedNodes"))
                sector_refs: list[Reference] = []
                deletions = sector.get("nodeDeletions")
                if isinstance(deletions, list):
                    for deletion, deletion_line in _sequence_entries(deletions):
                        if isinstance(deletion, dict) and deletion.get("index") is not None:
                            index_line = _mapping_line(
                                deletion, "index", deletion_line or path_line
                            )
                            node_index = _integer(deletion.get("index"))
                            node_type = _yaml_scalar_text(deletion.get("type"))
                            if (
                                node_index is None
                                or node_type is None
                                or node_index < 0
                                or (
                                    expected_nodes is not None
                                    and expected_nodes > 0
                                    and node_index >= expected_nodes
                                )
                            ):
                                mutation_parse_findings.append(
                                    Finding(
                                        rule_id="AXL-NODE-DELETION-SHAPE",
                                        severity="error",
                                        confidence="high",
                                        summary="Invalid ArchiveXL streaming node deletions: 1 occurrence(s)",
                                        explanation=(
                                            "ArchiveXL skips a whole node deletion when its required "
                                            "index/type is invalid or the index is outside expectedNodes."
                                        ),
                                        participants=[document.mod_name],
                                        evidence=[
                                            {
                                                "path": str(document.artifact.absolute_path),
                                                "line": index_line,
                                                "identity": f"{path}#{deletion.get('index')}",
                                                "index": deletion.get("index"),
                                                "expected_nodes": expected_nodes,
                                                "reason": (
                                                    "node deletion has an invalid type or index, "
                                                    "or its index is outside expectedNodes"
                                                ),
                                            }
                                        ],
                                    )
                                )
                                continue
                            element_deletions: list[dict[str, int]] = []
                            deletion_fields: list[str] = []
                            expected_elements: list[Any] = []
                            for deletion_field, expected_field in (
                                ("actorDeletions", "expectedActors"),
                                ("instanceDeletions", "expectedInstances"),
                            ):
                                values = deletion.get(deletion_field)
                                if not isinstance(values, list):
                                    continue
                                deletion_fields.append(deletion_field)
                                expected_elements.append(
                                    _integer(deletion.get(expected_field))
                                )
                                for value in values:
                                    element_index = _integer(value)
                                    if element_index is not None:
                                        element_deletions.append(
                                            {
                                                "element_index": element_index,
                                                "sub_element_index": -1,
                                            }
                                        )
                                    elif (
                                        isinstance(value, list)
                                        and len(value) == 2
                                        and _integer(value[0]) is not None
                                        and _integer(value[1]) is not None
                                    ):
                                        element_deletions.append(
                                            {
                                                "element_index": _integer(value[0]),
                                                "sub_element_index": _integer(value[1]),
                                            }
                                        )
                            sector_refs.append(
                                _reference(
                                    document,
                                    "streaming.node_deletion",
                                    f"{path}#{node_index}",
                                    index_line,
                                    sector=path,
                                    index=node_index,
                                    node_type=node_type,
                                    deletion_scope=(
                                        "partial" if element_deletions else "full"
                                    ),
                                    effective_deletion_scope=(
                                        "partial"
                                        if element_deletions
                                        and deletion.get("type")
                                        in {
                                            "worldCollisionNode",
                                            "worldInstancedMeshNode",
                                            "worldInstancedDestructibleMeshNode",
                                        }
                                        else "full"
                                    ),
                                    deletion_fields=deletion_fields,
                                    expected_elements=expected_elements,
                                    element_deletions=element_deletions,
                                )
                            )
                sector_refs.extend(
                    _extract_node_mutations(
                        document,
                        sector,
                        sector_line or path_line,
                        mutation_parse_findings,
                    )
                )
                # ArchiveXL drops sector declarations that contain no valid
                # node deletions or mutations. Keeping their sector reference
                # would create expectedNodes overlaps for operations that the
                # runtime never registers.
                if sector_refs:
                    refs.append(
                        _reference(
                            document,
                            "streaming.sector",
                            path,
                            path_line,
                            expected_nodes=sector.get("expectedNodes"),
                        )
                    )
                    refs.extend(sector_refs)
    findings.extend(
        _consolidate_node_mutation_parse_findings(mutation_parse_findings)
    )
    return refs


def _node_deletion_outcome(
    group: list[Reference],
) -> tuple[str, str, str, str]:
    node_types = {
        str(reference.details.get("node_type") or "") for reference in group
    }
    if len(node_types) > 1:
        return (
            "conflict",
            "high",
            "AXL-NODE-DELETION-TYPE-CONFLICT",
            "These mods target the same sector node index with different expected native types. ArchiveXL validates the type before applying a sector patch, so at least one declaration cannot match the loaded node.",
        )

    partial = [
        reference
        for reference in group
        if reference.details.get(
            "effective_deletion_scope", reference.details.get("deletion_scope")
        )
        == "partial"
    ]
    expected_counts = {
        value
        for reference in partial
        for value in reference.details.get("expected_elements", [])
        if value is not None
    }
    if len(expected_counts) > 1:
        return (
            "conflict",
            "high",
            "AXL-NODE-DELETION-COUNT-CONFLICT",
            "These partial deletions expect different actor/instance counts for the same node. ArchiveXL validates the live count before applying each whole sector patch, so the declarations cannot all describe the same loaded node state.",
        )

    collision_shape_patches = [
        reference
        for reference in partial
        if reference.details.get("node_type") == "worldCollisionNode"
        and any(
            int(element.get("sub_element_index", -1)) >= 0
            for element in reference.details.get("element_deletions", [])
        )
    ]
    if len(collision_shape_patches) > 1:
        return (
            "conflict",
            "high",
            "AXL-NODE-DELETION-COLLISION-SHAPE-CONFLICT",
            "Multiple mods delete individual collision shapes from the same node. ArchiveXL stores one shared preset override per sector/node; subsequent patches reuse that allocation while extending its logical size, so this overlap is not safely idempotent or composable.",
        )

    if not partial:
        return (
            "info",
            "high",
            "AXL-NODE-DELETION-IDEMPOTENT",
            "These mods repeat the same full-node deletion. ArchiveXL hides or moves nodes in place without removing or renumbering them, so applying the same deletion again is idempotent.",
        )
    if len(partial) != len(group):
        return (
            "info",
            "high",
            "AXL-NODE-DELETION-REDUNDANT",
            "A full-node deletion overlaps partial element deletions on the same node. ArchiveXL keeps node and element indices stable; the full deletion makes the partial operations redundant rather than incompatible.",
        )
    return (
        "info",
        "high",
        "AXL-NODE-DELETION-COMPOSABLE",
        "These mods hide elements within the same node. ArchiveXL does not remove or renumber the element buffers, so disjoint deletions compose and repeated element deletions are idempotent.",
    )


def compare_references(references: Iterable[Reference]) -> list[Finding]:
    reference_list = list(references)
    findings: list[Finding] = []
    aggregate: dict[tuple[str, tuple[str, ...]], list[tuple[str, list[Reference]]]] = defaultdict(list)
    grouped: dict[tuple[str, str], list[Reference]] = defaultdict(list)
    node_mods_by_sector: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for ref in reference_list:
        grouped[(ref.kind, ref.normalized_identity)].append(ref)
        if ref.kind in {"streaming.node_deletion", "streaming.node_mutation"}:
            sector = ref.details.get("sector")
            if isinstance(sector, str):
                node_mods_by_sector[normalize_game_path(sector)][
                    ref.normalized_identity
                ].add(ref.mod_name)

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
                has_shared_node = any(
                    len(node_mods.intersection(mods)) > 1
                    for node_mods in node_mods_by_sector.get(first.normalized_identity, {}).values()
                )
                if has_shared_node:
                    # Node-level mutation/deletion rules describe the actual overlap.
                    continue
                severity, rule, explanation = (
                    "info",
                    "AXL-SECTOR-NODE-DISJOINT",
                    "These mods patch different node indices in the same sector. ArchiveXL keeps node indices stable, so the operations compose.",
                )
        elif kind == "streaming.node_deletion":
            severity, confidence, rule, explanation = _node_deletion_outcome(group)
        else:
            continue
        if rule == "AXL-SECTOR-NODE-DISJOINT" or rule.startswith(
            "AXL-NODE-DELETION-"
        ):
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
        if rule == "AXL-SECTOR-NODE-DISJOINT":
            severity = "info"
            confidence = "high"
            noun = "streaming sector" if count == 1 else "streaming sectors"
            summary = f"{count} node-disjoint shared {noun}"
            explanation = (
                "These mods patch different node indices in the same sectors. "
                "ArchiveXL keeps node indices stable, so the operations compose."
            )
        else:
            severity, confidence, _classified_rule, explanation = (
                _node_deletion_outcome(overlaps[0][1])
            )
            labels = {
                "AXL-NODE-DELETION-IDEMPOTENT": "idempotent full-node deletion overlap",
                "AXL-NODE-DELETION-COMPOSABLE": "composable partial-node deletion overlap",
                "AXL-NODE-DELETION-REDUNDANT": "redundant full/partial node deletion overlap",
                "AXL-NODE-DELETION-TYPE-CONFLICT": "node deletion type conflict",
                "AXL-NODE-DELETION-COUNT-CONFLICT": "node deletion element-count conflict",
                "AXL-NODE-DELETION-COLLISION-SHAPE-CONFLICT": "collision-shape deletion conflict",
            }
            noun = labels[rule] + ("s" if count != 1 else "")
            summary = f"{count} {noun}"
        findings.append(
            Finding(
                rule_id=rule,
                severity=severity,
                confidence=confidence,
                summary=summary,
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


def _json_fingerprint(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _mutation_write_map(reference: Reference) -> dict[str, str]:
    writes = {
        f"node.{property_name}": _json_fingerprint(value)
        for property_name, value in reference.details.get("writes", {}).items()
    }
    for element in reference.details.get("element_mutations", []):
        element_index = element.get("element_index")
        for property_name, value in element.get("writes", {}).items():
            writes[f"element.{element_index}.{property_name}"] = _json_fingerprint(value)
    return writes


def _node_mutation_outcome(
    group: list[Reference],
) -> tuple[str, str, str]:
    node_types = {str(reference.details.get("node_type") or "") for reference in group}
    if len(node_types) > 1:
        return (
            "AXL-NODE-MUTATION-TYPE-CONFLICT",
            "conflict",
            "These mods expect different native types at the same sector node index. ArchiveXL validates every mutation before applying the sector patch, so they cannot all match the loaded node.",
        )
    expected_counts = {
        reference.details.get("expected_elements")
        for reference in group
        if reference.details.get("element_mutations")
        and reference.details.get("expected_elements") is not None
    }
    if len(expected_counts) > 1:
        return (
            "AXL-NODE-MUTATION-COUNT-CONFLICT",
            "conflict",
            "These mods expect different actor/instance counts for the same mutated node. ArchiveXL validates the live count before applying any changes from that sector declaration.",
        )

    per_mod: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for reference in group:
        for target, value in _mutation_write_map(reference).items():
            per_mod[reference.mod_name][target].add(value)

    participants = sorted(per_mod, key=str.casefold)
    targets: dict[str, dict[str, set[str]]] = defaultdict(dict)
    for mod_name, writes in per_mod.items():
        for target, values in writes.items():
            targets[target][mod_name] = values
    for target, mod_values in targets.items():
        if len(mod_values) < 2 or target == "node.proxy_nodes_add":
            continue
        if len({value for values in mod_values.values() for value in values}) > 1:
            return (
                "AXL-NODE-MUTATION-WRITE-CONFLICT",
                "conflict",
                "These mods write different values to the same node or element property. ArchiveXL applies the declarations sequentially, so the later value wins.",
            )

    if node_types == {"worldInstancedDestructibleMeshNode"}:
        element_signatures: dict[int, dict[str, str]] = defaultdict(dict)
        for reference in group:
            for element in reference.details.get("element_mutations", []):
                index = int(element["element_index"])
                element_signatures[index][reference.mod_name] = _json_fingerprint(
                    element.get("writes", {})
                )
        if any(
            len(signatures) > 1 and len(set(signatures.values())) > 1
            for signatures in element_signatures.values()
        ):
            return (
                "AXL-NODE-MUTATION-DESTRUCTIBLE-CONFLICT",
                "conflict",
                "Separate mutations of the same destructible-mesh instance do not preserve unspecified transform fields: ArchiveXL rebuilds each edit from the node transform. Different edits to one instance are therefore load-order dependent even when their declared properties are disjoint.",
            )

    signatures = {
        _json_fingerprint(
            {target: sorted(values) for target, values in sorted(writes.items())}
        )
        for writes in per_mod.values()
    }
    if len(participants) > 1 and len(signatures) == 1:
        return (
            "AXL-NODE-MUTATION-IDEMPOTENT",
            "info",
            "These mods repeat the same effective property writes on the same node. Applying the exact mutation again is idempotent.",
        )
    return (
        "AXL-NODE-MUTATION-COMPOSABLE",
        "info",
        "These mods mutate disjoint node/element properties, repeat equivalent values, or add positive proxy-node deltas. ArchiveXL can compose these effective operations.",
    )


def _mutation_deletion_outcome(
    mutations: list[Reference], deletions: list[Reference]
) -> tuple[str, str, str]:
    node_types = {
        str(reference.details.get("node_type") or "")
        for reference in [*mutations, *deletions]
    }
    if len(node_types) > 1:
        return (
            "AXL-NODE-MUTATION-DELETION-TYPE-CONFLICT",
            "conflict",
            "The mutation and deletion declarations expect different native types at the same node index, so ArchiveXL cannot validate all affected sector patches.",
        )
    node_type = next(iter(node_types), "")
    full_deletions = [
        reference
        for reference in deletions
        if reference.details.get(
            "effective_deletion_scope", reference.details.get("deletion_scope")
        ) == "full"
    ]
    if full_deletions:
        revives_static_mesh = node_type == "worldStaticMeshNode" and any(
            "scale" in reference.details.get("writes", {}) for reference in mutations
        )
        revives_instanced_mesh = node_type == "worldInstancedMeshNode" and any(
            "scale" in element.get("writes", {})
            for reference in mutations
            for element in reference.details.get("element_mutations", [])
        )
        if revives_static_mesh or revives_instanced_mesh:
            return (
                "AXL-NODE-MUTATION-DELETION-CONFLICT",
                "conflict",
                "A later scale mutation can make content visible again after ArchiveXL's specialized full deletion for this node type, while the reverse order leaves it hidden. The result is load-order dependent.",
            )
        return (
            "AXL-NODE-MUTATION-DELETION-REDUNDANT",
            "info",
            "A full-node deletion dominates these mutations in either order. The mutation is redundant for the final visible result rather than incompatible.",
        )

    deleted_elements = [
        element
        for reference in deletions
        for element in reference.details.get("element_deletions", [])
    ]
    mutated_elements = [
        element
        for reference in mutations
        for element in reference.details.get("element_mutations", [])
    ]
    conflict = False
    for deletion in deleted_elements:
        for mutation in mutated_elements:
            if deletion.get("element_index") != mutation.get("element_index"):
                continue
            writes = mutation.get("writes", {})
            sub_index = int(deletion.get("sub_element_index", -1))
            if (
                (node_type == "worldCollisionNode" and sub_index < 0 and "position" in writes)
                or (node_type == "worldInstancedMeshNode" and "scale" in writes)
                or (node_type == "worldInstancedDestructibleMeshNode" and "position" in writes)
            ):
                conflict = True
                break
        if conflict:
            break
    if conflict:
        return (
            "AXL-NODE-MUTATION-DELETION-CONFLICT",
            "conflict",
            "A mutation writes the same effective transform property that a partial deletion uses to hide this element. The final visibility depends on which mod ArchiveXL applies last.",
        )
    return (
        "AXL-NODE-MUTATION-DELETION-COMPOSABLE",
        "info",
        "The mutation and partial deletion affect different elements or effective properties, so ArchiveXL can apply both without one restoring the deleted content.",
    )


def compare_streaming_mutations(references: Iterable[Reference]) -> list[Finding]:
    """Compare effective node/property mutations and mutation/deletion interactions."""
    by_node: dict[str, dict[str, list[Reference]]] = defaultdict(
        lambda: {"mutations": [], "deletions": []}
    )
    for reference in references:
        if reference.kind == "streaming.node_mutation":
            by_node[reference.normalized_identity]["mutations"].append(reference)
        elif reference.kind == "streaming.node_deletion":
            by_node[reference.normalized_identity]["deletions"].append(reference)

    aggregate: dict[
        tuple[str, str, str, tuple[str, ...]], list[dict[str, Any]]
    ] = defaultdict(list)
    for operations in by_node.values():
        mutations = operations["mutations"]
        deletions = operations["deletions"]
        mutation_mods = {reference.mod_name for reference in mutations}
        if len(mutation_mods) > 1:
            rule, severity, explanation = _node_mutation_outcome(mutations)
            participants = tuple(sorted(mutation_mods, key=str.casefold))
            aggregate[(rule, severity, explanation, participants)].append(
                {
                    "identity": mutations[0].identity,
                    "references": [reference.to_dict() for reference in mutations],
                }
            )
        if mutations and deletions:
            participants_set = {
                reference.mod_name for reference in [*mutations, *deletions]
            }
            has_cross_mod_pair = any(
                mutation.mod_name != deletion.mod_name
                for mutation in mutations
                for deletion in deletions
            )
            if len(participants_set) > 1 and has_cross_mod_pair:
                rule, severity, explanation = _mutation_deletion_outcome(
                    mutations, deletions
                )
                participants = tuple(sorted(participants_set, key=str.casefold))
                aggregate[(rule, severity, explanation, participants)].append(
                    {
                        "identity": mutations[0].identity,
                        "references": [
                            reference.to_dict()
                            for reference in [*mutations, *deletions]
                        ],
                    }
                )

    labels = {
        "AXL-NODE-MUTATION-TYPE-CONFLICT": "node-mutation type conflicts",
        "AXL-NODE-MUTATION-COUNT-CONFLICT": "node-mutation element-count conflicts",
        "AXL-NODE-MUTATION-WRITE-CONFLICT": "competing node-mutation writes",
        "AXL-NODE-MUTATION-DESTRUCTIBLE-CONFLICT": "destructible-instance mutation conflicts",
        "AXL-NODE-MUTATION-IDEMPOTENT": "idempotent node-mutation overlaps",
        "AXL-NODE-MUTATION-COMPOSABLE": "composable node-mutation overlaps",
        "AXL-NODE-MUTATION-DELETION-TYPE-CONFLICT": "mutation/deletion type conflicts",
        "AXL-NODE-MUTATION-DELETION-CONFLICT": "mutation/deletion write conflicts",
        "AXL-NODE-MUTATION-DELETION-REDUNDANT": "redundant mutation/full-deletion overlaps",
        "AXL-NODE-MUTATION-DELETION-COMPOSABLE": "composable mutation/deletion overlaps",
    }
    return [
        Finding(
            rule_id=rule,
            severity=severity,
            confidence="high",
            summary=f"{len(evidence)} {labels[rule]}",
            explanation=explanation,
            participants=list(participants),
            evidence=evidence,
        )
        for (rule, severity, explanation, participants), evidence in sorted(
            aggregate.items(),
            key=lambda item: (
                item[0][0],
                tuple(participant.casefold() for participant in item[0][3]),
            ),
        )
    ]


def compare_player_references(references: Iterable[Reference]) -> list[Finding]:
    """Compare PuppetState registrations using ArchiveXL's exact CName strings."""
    by_body_type: dict[str, list[Reference]] = defaultdict(list)
    for reference in references:
        if reference.kind == "player.body_type":
            # REDengine CNames and Body:<name> tags are case-sensitive.
            by_body_type[reference.identity].append(reference)

    duplicates: dict[tuple[str, ...], list[tuple[str, list[Reference]]]] = defaultdict(list)
    for body_type, group in by_body_type.items():
        participants = tuple(
            sorted({reference.mod_name for reference in group}, key=str.casefold)
        )
        if len(participants) > 1:
            duplicates[participants].append((body_type, group))
    if not duplicates:
        return []

    findings: list[Finding] = []
    for participants, registrations in sorted(
        duplicates.items(),
        key=lambda item: tuple(participant.casefold() for participant in item[0]),
    ):
        count = len(registrations)
        noun = "body-type registration" if count == 1 else "body-type registrations"
        findings.append(
            Finding(
                rule_id="AXL-PLAYER-BODY-TYPE-DUPLICATE",
                severity="info",
                confidence="high",
                summary=f"{count} idempotent player {noun}",
                explanation=(
                    "These mods register the same case-sensitive player body type and "
                    "Body:<name> tag. ArchiveXL inserts both identities into global "
                    "set/map containers, so repeating the exact registration is idempotent."
                ),
                participants=list(participants),
                evidence=[
                    {
                        "identity": body_type,
                        "body_tag": f"Body:{body_type}",
                        "references": [reference.to_dict() for reference in group],
                    }
                    for body_type, group in sorted(
                        registrations, key=lambda item: item[0].casefold()
                    )
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
    player_refs = [
        reference
        for reference in reference_list
        if reference.kind == "player.body_type"
    ]
    player_operations = []
    if "player" in section_documents:
        by_body_type: dict[str, list[Reference]] = defaultdict(list)
        for reference in player_refs:
            by_body_type[reference.identity].append(reference)
        player_operations.append(
            {
                "name": "player.bodyTypes",
                "documents": len(section_documents["player"]),
                "registrations": len(player_refs),
                "unique_body_types": len(by_body_type),
                "shared_body_types": sum(
                    len({reference.mod_name for reference in group}) > 1
                    for group in by_body_type.values()
                ),
                "status": "analyzed",
                "note": (
                    "Body-type and Body:<name> tag identities are case-sensitive. "
                    "Distinct registrations compose and exact duplicates are idempotent."
                ),
            }
        )
    streaming_operations = []
    if "streaming" in section_documents:
        sector_refs = [
            reference
            for reference in reference_list
            if reference.kind == "streaming.sector"
        ]
        mutation_refs = [
            reference
            for reference in reference_list
            if reference.kind == "streaming.node_mutation"
        ]
        element_mutation_refs = [
            reference
            for reference in reference_list
            if reference.kind == "streaming.node_element_mutation"
        ]
        deletion_refs = [
            reference
            for reference in reference_list
            if reference.kind == "streaming.node_deletion"
        ]
        mutation_nodes: dict[str, set[str]] = defaultdict(set)
        for reference in mutation_refs:
            mutation_nodes[reference.normalized_identity].add(reference.mod_name)
        streaming_operations.append(
            {
                "name": "streaming.sectors",
                "documents": len(section_documents["streaming"]),
                "sectors": len(sector_refs),
                "node_mutations": len(mutation_refs),
                "element_mutations": len(element_mutation_refs),
                "node_deletions": len(deletion_refs),
                "node_property_writes": sum(
                    len(reference.details.get("writes", {}))
                    for reference in mutation_refs
                ),
                "element_property_writes": sum(
                    len(reference.details.get("writes", {}))
                    for reference in element_mutation_refs
                ),
                "shared_mutation_nodes": sum(
                    len(mods) > 1 for mods in mutation_nodes.values()
                ),
                "status": "analyzed",
                "note": (
                    "Node and element writes are compared by effective property; "
                    "mutation/deletion interactions and expected type/count guards "
                    "are also classified."
                ),
            }
        )
    return {
        "documents": len(document_list),
        "sections": sections,
        "resource_operations": resource_operations,
        "quest_operations": quest_operations,
        "override_operations": override_operations,
        "player_operations": player_operations,
        "streaming_operations": streaming_operations,
    }


def resolve_quest_references(
    references: Iterable[Reference],
    manifests: Iterable[ArchiveManifest],
    artifacts: Iterable[Artifact] = (),
) -> tuple[list[Finding], dict[str, Any]]:
    """Resolve quest child phases and custom parent targets against mod resources."""
    reference_list = list(references)
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

    phase_refs = [
        reference for reference in reference_list if reference.kind == "quest.phase"
    ]
    parent_refs = [
        reference for reference in reference_list if reference.kind == "quest.parent"
    ]
    scope_providers: dict[str, set[str]] = defaultdict(set)
    framework_scopes: set[str] = set()
    for reference in reference_list:
        if reference.kind != "resource.scope":
            continue
        scope = reference.details.get("scope")
        if not isinstance(scope, str):
            continue
        normalized_scope = normalize_game_path(scope)
        scope_providers[normalized_scope].add(reference.mod_name)
        if "red4ext\\plugins\\archivexl\\bundle\\" in normalize_game_path(
            reference.source_path
        ):
            framework_scopes.add(normalized_scope)
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
        if role == "parent" and (
            identity.startswith(("base\\", "ep1\\", "dlc\\"))
            or identity in framework_scopes
        ):
            stats["parent_official"] += 1
            continue
        if role == "parent" and identity in scope_providers:
            providers = tuple(sorted(scope_providers[identity], key=str.casefold))
            if reference.mod_name in providers:
                stats["parent_own"] += 1
            else:
                stats["parent_cross_mod"] += 1
                grouped[("cross-parent", identity, providers)].append(reference)
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
    source_providers: dict[str, str] = {}
    archive_prefix = "archive\\pc\\mod\\"
    for artifact in artifacts:
        source_providers[str(artifact.absolute_path).replace("/", "\\").casefold()] = (
            artifact.mod_name
        )
        normalized = artifact.normalized_path
        candidates = {normalized}
        if normalized.startswith(archive_prefix):
            candidates.add(normalized[len(archive_prefix):])
        for candidate in candidates:
            loose_by_mod[artifact.mod_name].add(candidate)
            loose_global[candidate].add(artifact.mod_name)

    resolvable_kinds = {
        "customization",
        "factory",
        "journal",
        "localization.onscreens",
        "streaming.block",
    }
    for ref in references:
        if ref.kind not in resolvable_kinds:
            continue
        identity = ref.normalized_identity
        declaring_mods = {ref.mod_name}
        source_provider = source_providers.get(
            ref.source_path.replace("/", "\\").casefold()
        )
        if source_provider is not None:
            declaring_mods.add(source_provider)
        if any(
            identity in by_mod.get(mod_name, {})
            or identity in loose_by_mod.get(mod_name, set())
            for mod_name in declaring_mods
        ):
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
