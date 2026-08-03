from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from xml.parsers import expat

from .models import Artifact, Finding, Reference


INPUT_PREFIX = "r6\\input\\"
USER_MAPPING_TAGS = {"mapping", "buttonGroup", "pairedAxes", "preset"}
CONTEXT_TAGS = {
    "blend", "context", "hold", "multitap", "repeat", "toggle", "acceptedEvents"
}
SUPPORTED_TAGS = USER_MAPPING_TAGS | CONTEXT_TAGS


@dataclass(slots=True)
class InputNode:
    tag: str
    attributes: dict[str, str]
    line: int
    children: list["InputNode"] = field(default_factory=list)

    @property
    def name(self) -> str | None:
        return self.attributes.get("name")

    @property
    def append(self) -> bool:
        return self.attributes.get("append", "").casefold() in {"1", "true", "yes"}

    def canonical(self, *, ignore_append: bool = False) -> tuple[Any, ...]:
        attributes = self.attributes.items()
        if ignore_append:
            attributes = ((key, value) for key, value in attributes if key != "append")
        return (
            self.tag,
            tuple(sorted(attributes)),
            tuple(child.canonical(ignore_append=ignore_append) for child in self.children),
        )


@dataclass(slots=True)
class InputDocument:
    artifact: Artifact
    nodes: list[InputNode]
    parsed: bool
    encoding: str
    error: str | None = None
    error_line: int | None = None


def _decode(data: bytes) -> tuple[str, str]:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "utf-16"
    try:
        return data.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("cp1252"), "cp1252"


def _parse_xml(text: str) -> tuple[str | None, list[InputNode]]:
    parser = expat.ParserCreate()
    stack: list[InputNode] = []
    roots: list[InputNode] = []

    def start(name: str, attributes: dict[str, str]) -> None:
        node = InputNode(
            tag=name,
            attributes=dict(attributes),
            line=max(1, parser.CurrentLineNumber),
        )
        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)

    def end(_: str) -> None:
        stack.pop()

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.Parse(text, True)
    if len(roots) != 1:
        return None, []
    return roots[0].tag, roots[0].children


def _is_input_artifact(artifact: Artifact) -> bool:
    normalized = artifact.relative_path.replace("/", "\\").casefold()
    return artifact.extension.casefold() == ".xml" and normalized.startswith(
        INPUT_PREFIX.casefold()
    )


def _node_key(node: InputNode) -> str:
    value = node.name or node.attributes.get("action") or node.attributes.get("id")
    return value or f"line-{node.line}"


def _node_reference(document: InputDocument, node: InputNode) -> Reference:
    artifact = document.artifact
    return Reference(
        ecosystem="input",
        kind=f"input.{node.tag}",
        identity=f"{node.tag}:{_node_key(node)}",
        mod_name=artifact.mod_name,
        source_path=str(artifact.absolute_path),
        line=node.line,
        details={
            "tag": node.tag,
            "name": node.name,
            "action": node.attributes.get("action"),
            "append": node.append,
            "attributes": node.attributes,
            "child_count": len(node.children),
            "semantic_hash": _node_hash(node),
            "relative_path": artifact.relative_path,
            "deployed_state": artifact.deployed_state,
            "deployed_source": artifact.deployed_source,
        },
    )


def _child_identity(parent: InputNode, child: InputNode) -> str:
    qualifier = (
        child.attributes.get("name")
        or child.attributes.get("action")
        or child.attributes.get("id")
        or f"line-{child.line}"
    )
    if child.tag == "button" and child.attributes.get("overridableUI"):
        qualifier += f"@{child.attributes['overridableUI']}"
    return f"{parent.tag}:{_node_key(parent)}/{child.tag}:{qualifier}"


def _child_reference(
    document: InputDocument, parent: InputNode, child: InputNode
) -> Reference:
    artifact = document.artifact
    return Reference(
        ecosystem="input",
        kind=f"input.{parent.tag}.{child.tag}",
        identity=_child_identity(parent, child),
        mod_name=artifact.mod_name,
        source_path=str(artifact.absolute_path),
        line=child.line,
        details={
            "parent_tag": parent.tag,
            "parent_name": parent.name,
            "parent_action": parent.attributes.get("action"),
            "parent_append": parent.append,
            "tag": child.tag,
            "attributes": child.attributes,
            "semantic_hash": _node_hash(child),
            "relative_path": artifact.relative_path,
            "deployed_state": artifact.deployed_state,
            "deployed_source": artifact.deployed_source,
        },
    )


def _node_hash(node: InputNode) -> str:
    payload = json.dumps(node.canonical(ignore_append=True), separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_input_documents(
    artifacts: Iterable[Artifact],
) -> tuple[list[InputDocument], list[Reference]]:
    documents: list[InputDocument] = []
    references: list[Reference] = []
    for artifact in artifacts:
        if not _is_input_artifact(artifact):
            continue
        encoding = "unknown"
        try:
            text, encoding = _decode(artifact.absolute_path.read_bytes())
            root_tag, nodes = _parse_xml(text)
            if root_tag != "bindings":
                raise ValueError("input fragment root must be <bindings>")
            document = InputDocument(artifact, nodes, True, encoding)
        except (OSError, UnicodeError, ValueError, expat.ExpatError) as exc:
            line = getattr(exc, "lineno", None)
            document = InputDocument(
                artifact, [], False, encoding, str(exc), line if isinstance(line, int) else 1
            )
        documents.append(document)
        for node in document.nodes:
            references.append(_node_reference(document, node))
            references.extend(_child_reference(document, node, child) for child in node.children)
    return documents, references


def _parse_path(path: Path) -> tuple[list[InputNode], str | None]:
    try:
        text, _ = _decode(path.read_bytes())
        root, nodes = _parse_xml(text)
        if root != "bindings":
            return [], "root is not <bindings>"
        return nodes, None
    except (OSError, UnicodeError, expat.ExpatError) as exc:
        return [], str(exc)


def _source_evidence(document: InputDocument, node: InputNode) -> dict[str, Any]:
    return _node_reference(document, node).to_dict()


def _active_documents(documents: Iterable[InputDocument]) -> list[InputDocument]:
    return [
        document for document in documents
        if document.parsed and document.artifact.deployed_state != "overridden"
    ]


def _top_groups(
    documents: Iterable[InputDocument],
) -> dict[tuple[str, str], list[tuple[InputDocument, InputNode]]]:
    grouped: dict[tuple[str, str], list[tuple[InputDocument, InputNode]]] = defaultdict(list)
    for document in documents:
        for node in document.nodes:
            if node.name:
                grouped[(node.tag, node.name)].append((document, node))
    return grouped


def _baseline_nodes(game_root: Path) -> tuple[list[InputNode], list[str], list[str]]:
    nodes: list[InputNode] = []
    paths: list[str] = []
    errors: list[str] = []
    candidates = (
        game_root / "r6" / "config" / "inputContexts.xml",
        game_root / "r6" / "config" / "inputUserMappings.xml",
    )
    for path in candidates:
        parsed, error = _parse_path(path)
        if error:
            errors.append(f"{path}: {error}")
        else:
            nodes.extend(parsed)
            paths.append(str(path))
    return nodes, paths, errors


def _cache_nodes(game_root: Path) -> tuple[list[InputNode], list[str], list[str]]:
    nodes: list[InputNode] = []
    paths: list[str] = []
    errors: list[str] = []
    for name in ("inputContexts.xml", "inputUserMappings.xml"):
        path = game_root / "r6" / "cache" / name
        parsed, error = _parse_path(path)
        if error:
            errors.append(f"{path}: {error}")
        else:
            nodes.extend(parsed)
            paths.append(str(path))
    return nodes, paths, errors


def _cache_target(cache_nodes: list[InputNode], node: InputNode) -> InputNode | None:
    if not node.name:
        return None
    return next(
        (candidate for candidate in cache_nodes if candidate.tag == node.tag and candidate.name == node.name),
        None,
    )


def _cache_matches(node: InputNode, cache_nodes: list[InputNode]) -> bool:
    target = _cache_target(cache_nodes, node)
    if node.name:
        if target is None:
            return False
        if node.append:
            available = Counter(child.canonical(ignore_append=True) for child in target.children)
            required = Counter(child.canonical(ignore_append=True) for child in node.children)
            return all(available[value] >= count for value, count in required.items())
        return target.canonical(ignore_append=True) == node.canonical(ignore_append=True)
    signature = node.canonical(ignore_append=True)
    return any(candidate.canonical(ignore_append=True) == signature for candidate in cache_nodes)


def _runtime_coverage(game_root: Path, active: list[InputDocument]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    path = game_root / "red4ext" / "logs" / "input_loader.log"
    result: dict[str, Any] = {
        "name": "Input Loader startup log",
        "status": "unsupported",
        "files": 0,
        "lines": 0,
        "errors": 0,
        "warnings": 0,
        "events": 0,
        "correlated_events": 0,
        "static_confirmations": 0,
        "findings": 0,
        "loaded_documents": 0,
        "missing_documents": 0,
        "log_path": str(path),
        "note": "Input Loader log was not found.",
    }
    evidence: list[dict[str, Any]] = []
    if not path.is_file():
        return result, evidence
    try:
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError as exc:
        result["status"] = "partial"
        result["note"] = f"Input Loader log could not be read: {exc}"
        return result, evidence
    loaded: set[str] = set()
    errors = warnings = 0
    for number, line in enumerate(lines, 1):
        lowered = line.casefold()
        if "] [error]" in lowered:
            errors += 1
            evidence.append({"path": str(path), "line": number, "message": line})
        elif "] [warning]" in lowered or "] [warn]" in lowered:
            warnings += 1
            evidence.append({"path": str(path), "line": number, "message": line})
        match = re.search(r"Loading document:\s+(.+?\.xml)\s*$", line, re.IGNORECASE)
        if match:
            loaded.add(Path(match.group(1).strip()).name.casefold())
    expected = {
        Path(document.artifact.relative_path.replace("\\", "/")).name.casefold()
        for document in active
    }
    missing = sorted(expected - loaded)
    result.update({
        "status": "analyzed",
        "files": 1,
        "lines": len(lines),
        "errors": errors,
        "warnings": warnings,
        "events": errors + warnings,
        "correlated_events": len(evidence),
        "static_confirmations": 0,
        "findings": int(bool(errors or warnings or missing)),
        "loaded_documents": len(loaded),
        "missing_documents": len(missing),
        "note": (
            f"The current log loaded {len(loaded)} input fragments; "
            f"{len(missing)} active staged fragment(s) were not named in that session."
        ),
    })
    if missing:
        evidence.append({"path": str(path), "missing_documents": missing})
    return result, evidence


def analyze_input_documents(
    documents: Iterable[InputDocument],
    references: Iterable[Reference],
    game_root: Path,
) -> tuple[list[Finding], dict[str, Any]]:
    document_list = list(documents)
    reference_list = list(references)
    active = _active_documents(document_list)
    findings: list[Finding] = []

    invalid = [document for document in document_list if not document.parsed]
    unsupported: list[tuple[InputDocument, InputNode]] = []
    for document in active:
        unsupported.extend(
            (document, node) for node in document.nodes if node.tag not in SUPPORTED_TAGS
        )
    if unsupported:
        findings.append(Finding(
            rule_id="INPUT-NODE-UNSUPPORTED",
            severity="warning",
            confidence="high",
            summary=f"{len(unsupported)} unsupported Input Loader top-level node(s)",
            explanation="Input Loader ignores children of <bindings> whose tag is not one of its supported input-context or user-mapping node types.",
            participants=sorted({document.artifact.mod_name for document, _ in unsupported}, key=str.casefold),
            evidence=[_source_evidence(document, node) for document, node in unsupported],
        ))

    active_groups = _top_groups(active)
    append_groups: list[tuple[tuple[str, str], list[tuple[InputDocument, InputNode]]]] = []
    overwrite_groups: list[tuple[tuple[str, str], list[tuple[InputDocument, InputNode]]]] = []
    duplicate_groups: list[tuple[tuple[str, str], list[tuple[InputDocument, InputNode]]]] = []
    for key, group in active_groups.items():
        if len({document.artifact.mod_name for document, _ in group}) < 2:
            continue
        hashes = {_node_hash(node) for _, node in group}
        if all(node.append for _, node in group):
            append_groups.append((key, group))
        elif len(hashes) == 1 and all(not node.append for _, node in group):
            duplicate_groups.append((key, group))
        else:
            overwrite_groups.append((key, group))
    if overwrite_groups:
        findings.append(Finding(
            rule_id="INPUT-NODE-OVERWRITE",
            severity="conflict",
            confidence="high",
            summary=f"{len(overwrite_groups)} Input Loader node(s) have competing whole-node providers",
            explanation="Input Loader removes the earlier top-level node when a same-tag, same-name node lacks append=\"true\". The effective definition therefore depends on filesystem traversal order.",
            participants=sorted({document.artifact.mod_name for _, group in overwrite_groups for document, _ in group}, key=str.casefold),
            evidence=[{"identity": f"{key[0]}:{key[1]}", "references": [_source_evidence(document, node) for document, node in group]} for key, group in overwrite_groups],
        ))
    if duplicate_groups:
        findings.append(Finding(
            rule_id="INPUT-NODE-DUPLICATE",
            severity="info",
            confidence="high",
            summary=f"{len(duplicate_groups)} identical Input Loader node(s) are repeated",
            explanation="The repeated whole-node definitions are semantically identical. Input Loader still selects the later copy, but behavior does not change.",
            participants=sorted({document.artifact.mod_name for _, group in duplicate_groups for document, _ in group}, key=str.casefold),
            evidence=[{"identity": f"{key[0]}:{key[1]}", "references": [_source_evidence(document, node) for document, node in group]} for key, group in duplicate_groups],
        ))
    if append_groups:
        findings.append(Finding(
            rule_id="INPUT-NODE-APPEND-COMPOSABLE",
            severity="info",
            confidence="high",
            summary=f"{len(append_groups)} shared Input Loader node(s) use append semantics",
            explanation="Every provider uses append=\"true\", so Input Loader retains the existing node and adds each provider's children. Child identities are checked separately for incompatible repetitions.",
            participants=sorted({document.artifact.mod_name for _, group in append_groups for document, _ in group}, key=str.casefold),
            evidence=[{"identity": f"{key[0]}:{key[1]}", "references": [_source_evidence(document, node) for document, node in group]} for key, group in append_groups],
        ))

    child_groups: dict[str, list[tuple[InputDocument, InputNode, InputNode]]] = defaultdict(list)
    for document in active:
        for node in document.nodes:
            if node.name:
                for child in node.children:
                    child_groups[_child_identity(node, child)].append((document, node, child))
    child_conflicts = []
    for identity, group in child_groups.items():
        if len({document.artifact.mod_name for document, _, _ in group}) < 2:
            continue
        if len({child.canonical(ignore_append=True) for _, _, child in group}) > 1:
            child_conflicts.append((identity, group))
    if child_conflicts:
        findings.append(Finding(
            rule_id="INPUT-APPEND-CHILD-CONFLICT",
            severity="warning",
            confidence="high",
            summary=f"{len(child_conflicts)} appended input child identities have different definitions",
            explanation="Input Loader blindly appends these children. The generated XML therefore contains repeated semantic identities with different attributes instead of resolving them as one definition.",
            participants=sorted({document.artifact.mod_name for _, group in child_conflicts for document, _, _ in group}, key=str.casefold),
            evidence=[{"identity": identity, "references": [_child_reference(document, parent, child).to_dict() for document, parent, child in group]} for identity, group in child_conflicts],
        ))

    policies: dict[tuple[str, str], list[tuple[InputDocument, InputNode]]] = defaultdict(list)
    for document in active:
        for node in document.nodes:
            action = node.attributes.get("action")
            if action and node.tag in {"hold", "multitap", "repeat", "toggle", "acceptedEvents"}:
                policies[(node.tag, action)].append((document, node))
    policy_conflicts = [
        (key, group) for key, group in policies.items()
        if len({document.artifact.mod_name for document, _ in group}) > 1
        and len({node.canonical(ignore_append=True) for _, node in group}) > 1
    ]
    if policy_conflicts:
        findings.append(Finding(
            rule_id="INPUT-ACTION-POLICY-CONFLICT",
            severity="warning",
            confidence="high",
            summary=f"{len(policy_conflicts)} input action policies have competing values",
            explanation="These action-level timing/event policies coexist in the generated context XML because Input Loader matches only a top-level name attribute, which these nodes do not use.",
            participants=sorted({document.artifact.mod_name for _, group in policy_conflicts for document, _ in group}, key=str.casefold),
            evidence=[{"identity": f"{key[0]}:{key[1]}", "references": [_source_evidence(document, node) for document, node in group]} for key, group in policy_conflicts],
        ))

    baseline, baseline_paths, baseline_errors = _baseline_nodes(game_root)
    baseline_index = {(node.tag, node.name): node for node in baseline if node.name}
    baseline_overwrites: list[tuple[InputDocument, InputNode, InputNode]] = []
    baseline_appends = 0
    for document in active:
        for node in document.nodes:
            original = baseline_index.get((node.tag, node.name)) if node.name else None
            if original is None:
                continue
            if node.append:
                baseline_appends += 1
            elif node.canonical(ignore_append=True) != original.canonical(ignore_append=True):
                baseline_overwrites.append((document, node, original))
    if baseline_overwrites:
        findings.append(Finding(
            rule_id="INPUT-BASELINE-OVERWRITE",
            severity="info",
            confidence="high",
            summary=f"{len(baseline_overwrites)} base-game input node(s) are intentionally replaced",
            explanation="These fragments omit append=\"true\" for an existing same-tag, same-name node. Input Loader replaces the complete base-game definition; this is often the purpose of a rebinding mod and is reported as load-order context rather than a cross-mod conflict.",
            participants=sorted({document.artifact.mod_name for document, _, _ in baseline_overwrites}, key=str.casefold),
            evidence=[{
                **_source_evidence(document, node),
                "baseline_path": baseline_paths[1] if node.tag in USER_MAPPING_TAGS and len(baseline_paths) > 1 else (baseline_paths[0] if baseline_paths else None),
                "baseline_line": original.line,
            } for document, node, original in baseline_overwrites],
        ))

    cache, cache_paths, cache_errors = _cache_nodes(game_root)
    cache_mismatches: list[tuple[InputDocument, InputNode]] = []
    if not cache_errors:
        for document in active:
            for node in document.nodes:
                group = active_groups.get((node.tag, node.name), []) if node.name else []
                if node.name and len(group) > 1 and not all(item.append for _, item in group):
                    continue
                if not _cache_matches(node, cache):
                    cache_mismatches.append((document, node))
    if cache_mismatches:
        findings.append(Finding(
            rule_id="INPUT-CACHE-MISMATCH",
            severity="warning",
            confidence="high",
            summary=f"{len(cache_mismatches)} active input node(s) are missing or different in Input Loader's cache",
            explanation="The current generated cache does not contain the effective node or appended children expected from these active fragments. Start the game once after deployment and inspect input_loader.log if the cache is stale.",
            participants=sorted({document.artifact.mod_name for document, _ in cache_mismatches}, key=str.casefold),
            evidence=[_source_evidence(document, node) for document, node in cache_mismatches],
        ))

    final_nodes = cache if not cache_errors else baseline + [node for document in active for node in document.nodes]
    mapping_names = {node.name for node in final_nodes if node.tag == "mapping" and node.name}
    context_names = {node.name for node in final_nodes if node.tag == "context" and node.name}
    action_names = {
        child.attributes.get("name")
        for node in final_nodes if node.tag == "context"
        for child in node.children if child.tag == "action" and child.attributes.get("name")
    }
    missing_links: list[Reference] = []
    for document in active:
        for node in document.nodes:
            for child in node.children:
                if node.tag == "context" and child.tag == "action":
                    target = child.attributes.get("map")
                    if target and target not in mapping_names:
                        missing_links.append(_child_reference(document, node, child))
                elif node.tag == "context" and child.tag == "include":
                    target = child.attributes.get("name")
                    if target and target not in context_names:
                        missing_links.append(_child_reference(document, node, child))
            action = node.attributes.get("action")
            if node.tag in {"hold", "multitap", "repeat", "toggle", "acceptedEvents"} and action and action not in action_names:
                missing_links.append(_node_reference(document, node))
    if missing_links:
        findings.append(Finding(
            rule_id="INPUT-TARGET-MISSING",
            severity="warning",
            confidence="high",
            summary=f"{len(missing_links)} input reference(s) target missing mappings, contexts, or actions",
            explanation="The target is absent from the current generated Input Loader cache (or from the scanner's baseline/source fallback). The affected action, include, or timing policy cannot resolve as declared.",
            participants=sorted({reference.mod_name for reference in missing_links}, key=str.casefold),
            evidence=[reference.to_dict() for reference in missing_links],
        ))

    runtime, runtime_evidence = _runtime_coverage(game_root, active)
    if runtime["errors"] or runtime["warnings"]:
        findings.append(Finding(
            rule_id="INPUT-RUNTIME-DIAGNOSTIC",
            severity="error" if runtime["errors"] else "warning",
            confidence="high",
            summary=f"Input Loader logged {runtime['errors']} error(s) and {runtime['warnings']} warning(s)",
            explanation="The current Input Loader startup log reported merge diagnostics. Individual log lines are retained as evidence.",
            participants=sorted({document.artifact.mod_name for document in active}, key=str.casefold),
            evidence=runtime_evidence,
        ))
    elif runtime["missing_documents"]:
        findings.append(Finding(
            rule_id="INPUT-RUNTIME-SOURCE-MISSING",
            severity="warning",
            confidence="medium",
            summary=f"{runtime['missing_documents']} active input fragment(s) were absent from the current startup log",
            explanation="The latest Input Loader session did not name every active staged input filename. The log or deployed input directory may predate the frozen staging state.",
            participants=sorted({document.artifact.mod_name for document in active}, key=str.casefold),
            evidence=runtime_evidence,
        ))

    tag_counts = Counter(node.tag for document in active for node in document.nodes)
    coverage = {
        "documents": len(document_list),
        "sections": [
            {
                "name": "Input Loader XML semantics",
                "documents": len(active),
                "status": "partial" if invalid or unsupported else "analyzed",
                "note": "Top-level replacement/append behavior, nested identities, action links, and source lines are analyzed using Input Loader's merge model.",
            },
            {
                "name": "generated cache validation",
                "documents": len(cache_paths),
                "status": "partial" if cache_errors else "analyzed",
                "note": "Active source nodes and appended children are compared with r6/cache/inputContexts.xml and inputUserMappings.xml.",
            },
        ],
        "input_operations": [{
            "name": "Input Loader mappings and contexts",
            "status": "partial" if invalid or unsupported or baseline_errors else "analyzed",
            "documents": len(document_list),
            "active_documents": len(active),
            "references": len(reference_list),
            "top_level_nodes": sum(tag_counts.values()),
            "mappings": tag_counts["mapping"],
            "contexts": tag_counts["context"],
            "action_policies": sum(tag_counts[tag] for tag in ("hold", "multitap", "repeat", "toggle", "acceptedEvents")),
            "baseline_overwrites": len(baseline_overwrites),
            "baseline_appends": baseline_appends,
            "shared_append_nodes": len(append_groups),
            "competing_nodes": len(overwrite_groups),
            "missing_targets": len(missing_links),
            "cache_mismatches": len(cache_mismatches),
            "note": "Input Loader's exact tag/name whole-node replacement and child-append semantics are modeled; current generated caches provide effective-state validation.",
        }],
        "runtime_logs": [runtime],
        "baseline_paths": baseline_paths,
        "baseline_errors": baseline_errors,
        "cache_paths": cache_paths,
        "cache_errors": cache_errors,
    }
    return findings, coverage
