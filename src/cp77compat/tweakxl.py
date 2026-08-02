from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

import yaml

from .models import Artifact, Finding, Reference


TWEAK_EXTENSIONS = {".yaml", ".yml"}
ARRAY_OPERATIONS = {
    "append",
    "append-once",
    "append-from",
    "prepend",
    "prepend-once",
    "prepend-from",
    "remove",
}
ADD_OPERATIONS = ARRAY_OPERATIONS - {"remove"}
UNIQUE_ADD_OPERATIONS = {"append-once", "prepend-once"}
TEMPLATE_PATTERN = re.compile(r"\$\(([^)]+)\)")


@dataclass(frozen=True, slots=True)
class TaggedValue:
    tag: str
    value: Any
    line: int | None = None


class TweakXLMapping(dict[Any, Any]):
    """A mapping that also retains duplicate YAML entries in source order."""

    def __init__(self) -> None:
        super().__init__()
        self.pairs: list[tuple[Any, Any]] = []
        self.locations: list[tuple[int | None, int | None]] = []

    def add(
        self,
        key: Any,
        value: Any,
        key_line: int | None = None,
        value_line: int | None = None,
    ) -> None:
        self.pairs.append((key, value))
        self.locations.append((key_line, value_line))
        self[key] = value


class TweakXLLoader(yaml.SafeLoader):
    """Safe TweakXL loader that preserves custom tags and duplicate keys."""


def _construct_mapping(
    loader: TweakXLLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> TweakXLMapping:
    mapping = TweakXLMapping()
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        value = loader.construct_object(value_node, deep=True)
        mapping.add(
            key,
            value,
            key_node.start_mark.line + 1,
            value_node.start_mark.line + 1,
        )
    return mapping


def _construct_tagged(loader: TweakXLLoader, suffix: str, node: yaml.Node) -> TaggedValue:
    if isinstance(node, yaml.ScalarNode):
        value: Any = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        value = loader.construct_mapping(node, deep=True)
    return TaggedValue(
        tag=suffix.lstrip("!").casefold(),
        value=value,
        line=node.start_mark.line + 1,
    )


TweakXLLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)
TweakXLLoader.add_multi_constructor("!", _construct_tagged)


@dataclass(slots=True)
class TweakXLDocument:
    artifact: Artifact
    data: TweakXLMapping
    text: str


def is_tweak_artifact(artifact: Artifact) -> bool:
    return (
        artifact.extension in TWEAK_EXTENSIONS
        and artifact.normalized_path.startswith("r6\\tweaks\\")
        and artifact.deployed_state != "overridden"
    )


def _line_for(text: str, *needles: str) -> int | None:
    normalized = [needle.casefold() for needle in needles if needle]
    for number, line in enumerate(text.splitlines(), start=1):
        folded = line.casefold()
        if any(needle in folded for needle in normalized):
            return number
    return None


def _mapping_pairs(value: Any) -> list[tuple[Any, Any]]:
    if isinstance(value, TweakXLMapping):
        return value.pairs
    if isinstance(value, dict):
        return list(value.items())
    return []


def _mapping_entries(
    value: Any,
) -> list[tuple[Any, Any, int | None, int | None]]:
    if isinstance(value, TweakXLMapping):
        return [
            (key, item, key_line, value_line)
            for (key, item), (key_line, value_line) in zip(
                value.pairs, value.locations, strict=True
            )
        ]
    if isinstance(value, dict):
        return [(key, item, None, None) for key, item in value.items()]
    return []


def _json_value(value: Any) -> Any:
    if isinstance(value, TaggedValue):
        return {"$tag": value.tag, "value": _json_value(value.value)}
    if isinstance(value, TweakXLMapping):
        keys = [str(key) for key, _ in value.pairs]
        if len(keys) == len(set(keys)):
            return {str(key): _json_value(item) for key, item in value.pairs}
        # A list of pairs preserves the uncommon case of duplicate nested keys.
        return {"$pairs": [[str(key), _json_value(item)] for key, item in value.pairs]}
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _canonical(value: Any) -> str:
    return json.dumps(_json_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _substitute_string(value: str, variables: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        return str(variables.get(name, match.group(0)))

    return TEMPLATE_PATTERN.sub(replace, value)


def _substitute(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return _substitute_string(value, variables)
    if isinstance(value, TaggedValue):
        return TaggedValue(value.tag, _substitute(value.value, variables), value.line)
    if isinstance(value, TweakXLMapping):
        result = TweakXLMapping()
        for key, item, key_line, value_line in _mapping_entries(value):
            expanded_key = _substitute(key, variables) if isinstance(key, str) else key
            result.add(
                expanded_key,
                _substitute(item, variables),
                key_line,
                value_line,
            )
        return result
    if isinstance(value, dict):
        return {
            _substitute(key, variables) if isinstance(key, str) else key: _substitute(item, variables)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_substitute(item, variables) for item in value]
    return value


def _reference(
    document: TweakXLDocument,
    kind: str,
    identity: str,
    value: Any,
    operation: str,
    source_identity: str,
    source_line: int | None,
    scope: Any = None,
) -> Reference:
    rendered = _json_value(value)
    details = {
        "operation": operation,
        "value": rendered,
        "value_key": _canonical(value),
        "source_identity": source_identity,
    }
    if scope is not None:
        details["dlc"] = _json_value(scope)
    return Reference(
        ecosystem="tweakxl",
        kind=kind,
        identity=identity,
        mod_name=document.artifact.mod_name,
        source_path=str(document.artifact.absolute_path),
        line=source_line or _line_for(document.text, source_identity, identity),
        details=details,
    )


def _parse_property(
    document: TweakXLDocument,
    identity: str,
    source_identity: str,
    value: Any,
    scope: Any,
    source_line: int | None,
    findings: list[Finding],
) -> list[Reference]:
    references: list[Reference] = []

    def mutation(tagged: TaggedValue) -> None:
        operation = tagged.tag
        if operation not in ARRAY_OPERATIONS:
            findings.append(
                Finding(
                    rule_id="TXL-UNKNOWN-TAG",
                    severity="review",
                    confidence="medium",
                    summary=f"Unknown TweakXL tag !{operation}",
                    explanation="The value was preserved, but this scanner version does not compare its semantics.",
                    participants=[document.artifact.mod_name],
                    evidence=[
                        {
                            "path": str(document.artifact.absolute_path),
                            "line": tagged.line or source_line,
                            "identity": identity,
                        }
                    ],
                )
            )
        references.append(
            _reference(
                document,
                f"array.{operation}",
                identity,
                tagged.value,
                operation,
                source_identity,
                tagged.line or source_line,
                scope,
            )
        )

    if isinstance(value, TaggedValue):
        mutation(value)
        return references

    if isinstance(value, list):
        plain_values: list[Any] = []
        for item in value:
            if isinstance(item, TaggedValue):
                mutation(item)
            else:
                plain_values.append(item)
        if plain_values:
            references.append(
                _reference(
                    document,
                    "assignment",
                    identity,
                    plain_values,
                    "assign",
                    source_identity,
                    source_line,
                    scope,
                )
            )
        return references

    references.append(
        _reference(
            document,
            "assignment",
            identity,
            value,
            "assign",
            source_identity,
            source_line,
            scope,
        )
    )
    return references


def _instances(
    document: TweakXLDocument,
    root: str,
    body: TweakXLMapping,
    root_line: int | None,
    findings: list[Finding],
) -> list[dict[str, Any]]:
    value = body.get("$instances")
    if value is None:
        return [{}]
    if not isinstance(value, list) or not value:
        findings.append(
            Finding(
                rule_id="TXL-INSTANCES",
                severity="error",
                confidence="high",
                summary=f"Invalid $instances for {root}",
                explanation="$instances must be a non-empty sequence of variable mappings.",
                participants=[document.artifact.mod_name],
                evidence=[
                    {"path": str(document.artifact.absolute_path), "line": root_line}
                ],
            )
        )
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            findings.append(
                Finding(
                    rule_id="TXL-INSTANCES",
                    severity="error",
                    confidence="high",
                    summary=f"Invalid $instances entry for {root}",
                    explanation="Every $instances entry must be a variable mapping.",
                    participants=[document.artifact.mod_name],
                    evidence=[
                        {"path": str(document.artifact.absolute_path), "line": root_line}
                    ],
                )
            )
            continue
        result.append({str(key): value for key, value in item.items()})
    return result


def _extract_references(
    document: TweakXLDocument,
    findings: list[Finding],
) -> list[Reference]:
    references: list[Reference] = []
    for raw_root, raw_body, root_line, body_line in _mapping_entries(document.data):
        if not isinstance(raw_root, str):
            findings.append(
                Finding(
                    rule_id="TXL-ROOT-KEY",
                    severity="error",
                    confidence="high",
                    summary=f"Non-string TweakXL root key in {document.artifact.relative_path}",
                    explanation="TweakDB record and flat identifiers must be strings.",
                    participants=[document.artifact.mod_name],
                    evidence=[{"path": str(document.artifact.absolute_path)}],
                )
            )
            continue

        if not isinstance(raw_body, dict):
            references.extend(
                _parse_property(
                    document,
                    raw_root,
                    raw_root,
                    raw_body,
                    None,
                    root_line or body_line,
                    findings,
                )
            )
            continue

        body = raw_body if isinstance(raw_body, TweakXLMapping) else _substitute(raw_body, {})
        for variables in _instances(document, raw_root, body, root_line, findings):
            root = _substitute_string(raw_root, variables)
            expanded = _substitute(body, variables)
            if TEMPLATE_PATTERN.search(root):
                findings.append(
                    Finding(
                        rule_id="TXL-UNRESOLVED-TEMPLATE",
                        severity="error",
                        confidence="high",
                        summary=f"Unresolved TweakXL template: {raw_root}",
                        explanation="At least one placeholder has no matching $instances variable.",
                        participants=[document.artifact.mod_name],
                        evidence=[
                            {
                                "path": str(document.artifact.absolute_path),
                                "line": root_line,
                            }
                        ],
                    )
                )
                continue

            scope = expanded.get("$dlc") if isinstance(expanded, dict) else None
            for raw_property, value, property_line, value_line in _mapping_entries(
                expanded
            ):
                if not isinstance(raw_property, str):
                    findings.append(
                        Finding(
                            rule_id="TXL-PROPERTY-KEY",
                            severity="error",
                            confidence="high",
                            summary=f"Non-string property key under {root}",
                            explanation="TweakDB property names must be strings.",
                            participants=[document.artifact.mod_name],
                            evidence=[
                                {
                                    "path": str(document.artifact.absolute_path),
                                    "line": property_line or root_line,
                                }
                            ],
                        )
                    )
                    continue
                if raw_property in {"$instances", "$dlc"}:
                    continue
                if raw_property in {"$base", "$type"}:
                    directive = raw_property[1:]
                    references.append(
                        _reference(
                            document,
                            f"record.{directive}",
                            root,
                            value,
                            directive,
                            raw_root,
                            property_line or value_line or root_line,
                            scope,
                        )
                    )
                    continue
                if raw_property.startswith("$"):
                    findings.append(
                        Finding(
                            rule_id="TXL-UNKNOWN-DIRECTIVE",
                            severity="review",
                            confidence="medium",
                            summary=f"Unknown TweakXL directive {raw_property}",
                            explanation="The directive was preserved but is not interpreted by this scanner version.",
                            participants=[document.artifact.mod_name],
                            evidence=[
                                {
                                    "path": str(document.artifact.absolute_path),
                                    "line": property_line or root_line,
                                    "identity": root,
                                }
                            ],
                        )
                    )
                    continue
                identity = f"{root}.{raw_property}"
                references.extend(
                    _parse_property(
                        document,
                        identity,
                        f"{raw_root}.{raw_property}",
                        value,
                        scope,
                        property_line or value_line or root_line,
                        findings,
                    )
                )
    return references


def parse_tweak_documents(
    artifacts: Iterable[Artifact],
) -> tuple[list[TweakXLDocument], list[Reference], list[Finding]]:
    documents: list[TweakXLDocument] = []
    references: list[Reference] = []
    findings: list[Finding] = []
    for artifact in sorted(artifacts, key=lambda item: str(item.absolute_path).casefold()):
        if not is_tweak_artifact(artifact):
            continue
        text = artifact.absolute_path.read_text(encoding="utf-8-sig", errors="replace")
        if not text.strip():
            findings.append(
                Finding(
                    rule_id="TXL-EMPTY",
                    severity="info",
                    confidence="high",
                    summary=f"Empty TweakXL file: {artifact.relative_path}",
                    explanation="The tweak file contains no operations.",
                    participants=[artifact.mod_name],
                    evidence=[{"path": str(artifact.absolute_path)}],
                )
            )
            continue
        used_tab_fallback = False
        try:
            try:
                loaded = yaml.load(text, Loader=TweakXLLoader)
            except yaml.scanner.ScannerError as exc:
                if "character '\\t'" not in str(exc):
                    raise
                loaded = yaml.load(text.replace("\t", "  "), Loader=TweakXLLoader)
                used_tab_fallback = True
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            findings.append(
                Finding(
                    rule_id="TXL-PARSE",
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
        if loaded is None:
            continue
        if not isinstance(loaded, TweakXLMapping):
            findings.append(
                Finding(
                    rule_id="TXL-ROOT-TYPE",
                    severity="error",
                    confidence="high",
                    summary=f"TweakXL root is not a mapping: {artifact.relative_path}",
                    explanation="A TweakXL YAML file must contain named TweakDB records or flats.",
                    participants=[artifact.mod_name],
                    evidence=[{"path": str(artifact.absolute_path)}],
                )
            )
            continue
        document = TweakXLDocument(artifact=artifact, data=loaded, text=text)
        documents.append(document)
        if used_tab_fallback:
            findings.append(
                Finding(
                    rule_id="TXL-NONSTANDARD-TABS",
                    severity="info",
                    confidence="high",
                    summary=f"TweakXL YAML contains tab characters: {artifact.relative_path}",
                    explanation="The scanner normalized tabs for parsing; the source file was not modified.",
                    participants=[artifact.mod_name],
                    evidence=[{"path": str(artifact.absolute_path)}],
                )
            )
        references.extend(_extract_references(document, findings))
    return documents, references, findings


def _cross_mod(references: Iterable[Reference]) -> bool:
    return len({reference.mod_name for reference in references}) > 1


def _evidence(identity: str, references: Iterable[Reference]) -> dict[str, Any]:
    return {
        "identity": identity,
        "references": [reference.to_dict() for reference in references],
    }


def _compact_evidence(identity: str, references: Iterable[Reference]) -> dict[str, Any]:
    reference_list = list(references)
    counts: dict[tuple[str, str], int] = defaultdict(int)
    sources: dict[tuple[str, str], dict[str, Any]] = {}
    for reference in reference_list:
        operation = str(reference.details.get("operation", reference.kind))
        counts[(reference.mod_name, operation)] += 1
        sources.setdefault(
            (reference.mod_name, reference.source_path),
            {
                "mod_name": reference.mod_name,
                "source_path": reference.source_path,
                "line": reference.line,
            },
        )
    return {
        "identity": identity,
        "reference_count": len(reference_list),
        "operation_counts": [
            {"mod_name": mod, "operation": operation, "count": count}
            for (mod, operation), count in sorted(
                counts.items(), key=lambda item: (item[0][0].casefold(), item[0][1])
            )
        ],
        "sources": list(sources.values()),
    }


def compare_tweak_references(references: Iterable[Reference]) -> list[Finding]:
    grouped: dict[str, list[Reference]] = defaultdict(list)
    directives: dict[tuple[str, str], list[Reference]] = defaultdict(list)
    for reference in references:
        if reference.kind in {"record.base", "record.type"}:
            directives[(reference.kind, reference.normalized_identity)].append(reference)
        else:
            grouped[reference.normalized_identity].append(reference)

    overlaps: list[tuple[str, str, str, str, list[str], dict[str, Any]]] = []

    for (kind, _), group in directives.items():
        if not _cross_mod(group):
            continue
        values = {reference.details.get("value_key") for reference in group}
        if len(values) < 2:
            continue
        directive = kind.rsplit(".", 1)[-1]
        rule = f"TXL-RECORD-{directive.upper()}-CONFLICT"
        explanation = f"Multiple mods give the same TweakDB record different ${directive} values."
        mods = sorted({reference.mod_name for reference in group}, key=str.casefold)
        overlaps.append((rule, "conflict", "high", explanation, mods, _evidence(group[0].identity, group)))

    for group in grouped.values():
        assignments = [reference for reference in group if reference.details.get("operation") == "assign"]
        mutations = [reference for reference in group if reference.details.get("operation") in ARRAY_OPERATIONS]
        mutation_issue = False

        if _cross_mod(assignments):
            values = {reference.details.get("value_key") for reference in assignments}
            if len(values) > 1:
                mods = sorted({reference.mod_name for reference in assignments}, key=str.casefold)
                overlaps.append(
                    (
                        "TXL-ASSIGNMENT-CONFLICT",
                        "conflict",
                        "high",
                        "Multiple mods assign different complete values to the same TweakDB flat or record property.",
                        mods,
                        _evidence(assignments[0].identity, assignments),
                    )
                )

        if assignments and mutations and _cross_mod([*assignments, *mutations]):
            assignment_mods = {reference.mod_name for reference in assignments}
            mutation_mods = {reference.mod_name for reference in mutations}
            if assignment_mods != mutation_mods or len(assignment_mods) > 1:
                participants = sorted(assignment_mods | mutation_mods, key=str.casefold)
                overlaps.append(
                    (
                        "TXL-ASSIGNMENT-MUTATION",
                        "warning",
                        "medium",
                        "One mod replaces the complete value while another appends, "
                        "prepends, or removes array entries. The result can depend on "
                        "tweak load order.",
                        participants,
                        _evidence(group[0].identity, [*assignments, *mutations]),
                    )
                )

        by_value: dict[str, list[Reference]] = defaultdict(list)
        for reference in mutations:
            by_value[str(reference.details.get("value_key"))].append(reference)
        for same_value in by_value.values():
            if not _cross_mod(same_value):
                continue
            operations = {str(reference.details.get("operation")) for reference in same_value}
            participants = sorted({reference.mod_name for reference in same_value}, key=str.casefold)
            if "remove" in operations and operations & ADD_OPERATIONS:
                mutation_issue = True
                overlaps.append(
                    (
                        "TXL-ARRAY-ADD-REMOVE",
                        "conflict",
                        "high",
                        "Different mods add and remove the same value from the same TweakDB array.",
                        participants,
                        _evidence(same_value[0].identity, same_value),
                    )
                )
            elif operations & ADD_OPERATIONS and not operations <= UNIQUE_ADD_OPERATIONS:
                mutation_issue = True
                overlaps.append(
                    (
                        "TXL-ARRAY-DUPLICATE",
                        "warning",
                        "medium",
                        "Different mods add the same value to the same TweakDB array "
                        "without exclusively using uniqueness-preserving operations.",
                        participants,
                        _evidence(same_value[0].identity, same_value),
                    )
                )

        if mutations and not assignments and _cross_mod(mutations) and not mutation_issue:
            participants = sorted(
                {reference.mod_name for reference in mutations}, key=str.casefold
            )
            overlaps.append(
                (
                    "TXL-ARRAY-COMPOSABLE",
                    "info",
                    "high",
                    "These mods mutate the same TweakDB array, but their tagged "
                    "operations do not assign the whole array, add duplicate values, "
                    "or add and remove the same value.",
                    participants,
                    _compact_evidence(group[0].identity, mutations),
                )
            )

    aggregate: dict[
        tuple[str, str, str, str, tuple[str, ...]], list[dict[str, Any]]
    ] = defaultdict(list)
    for rule, severity, confidence, explanation, participants, evidence in overlaps:
        aggregate[(rule, severity, confidence, explanation, tuple(participants))].append(evidence)

    findings: list[Finding] = []
    nouns = {
        "TXL-ASSIGNMENT-CONFLICT": "incompatible TweakDB assignments",
        "TXL-ASSIGNMENT-MUTATION": "assignment/mutation overlaps",
        "TXL-ARRAY-ADD-REMOVE": "array add/remove conflicts",
        "TXL-ARRAY-DUPLICATE": "duplicate array additions",
        "TXL-ARRAY-COMPOSABLE": "composable array overlaps",
        "TXL-RECORD-BASE-CONFLICT": "incompatible TweakDB record bases",
        "TXL-RECORD-TYPE-CONFLICT": "incompatible TweakDB record types",
    }
    for (rule, severity, confidence, explanation, participants), evidence in sorted(
        aggregate.items(),
        key=lambda item: (item[0][0], tuple(value.casefold() for value in item[0][4])),
    ):
        count = len(evidence)
        noun = nouns.get(rule, "TweakXL overlaps")
        findings.append(
            Finding(
                rule_id=rule,
                severity=severity,
                confidence=confidence,
                summary=f"{count} {noun}",
                explanation=explanation,
                participants=list(participants),
                evidence=evidence,
            )
        )
    return findings
