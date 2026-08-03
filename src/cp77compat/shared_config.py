from __future__ import annotations

import configparser
import hashlib
import json
import tomllib
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree

from .models import Artifact, Finding, Reference


CONFIG_EXTENSIONS = {".json", ".toml", ".ini", ".xml"}
CET_MODS_PREFIX = "bin\\x64\\plugins\\cyber_engine_tweaks\\mods\\"


@dataclass(slots=True)
class ConfigDocument:
    artifact: Artifact
    format: str
    scope: str
    encoding: str
    parsed: bool
    semantic_hash: str | None
    entry_count: int
    duplicate_keys: list[str]
    error: str | None = None
    error_line: int | None = None


def _scope(relative_path: str) -> str:
    normalized = relative_path.replace("/", "\\")
    lowered = normalized.casefold()
    if lowered.startswith(CET_MODS_PREFIX.casefold()):
        remainder = normalized[len(CET_MODS_PREFIX):]
        root, separator, _ = remainder.partition("\\")
        if separator and root:
            return f"cet:{root}"
    if lowered.startswith("r6\\input\\"):
        return "r6-input"
    if lowered.startswith("r6\\cache\\input"):
        return "r6-input-cache"
    if lowered.startswith("r6\\config\\redsuserhints\\"):
        return "redscript-user-hints"
    if lowered.startswith("r6\\storages\\redscriptconfigframework\\"):
        return "redscript-config-framework"
    if lowered.startswith("engine\\config\\"):
        return "engine-config"
    if lowered.startswith("red4ext\\plugins\\"):
        parts = normalized.split("\\")
        return f"red4ext:{parts[2]}" if len(parts) > 2 else "red4ext"
    if lowered.startswith("archive\\pc\\mod\\"):
        return "archive-mod-data"
    parent = str(Path(normalized).parent).replace("/", "\\")
    return f"directory:{parent}"


def _decode(data: bytes) -> tuple[str, str]:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "utf-16"
    try:
        return data.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("cp1252"), "cp1252"


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, (datetime, date, time)):
        return {"$type": type(value).__name__, "$value": value.isoformat()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _fingerprint(value: Any) -> str:
    serialized = json.dumps(
        _normalize(value), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _leaf_count(value: Any) -> int:
    if isinstance(value, dict):
        return sum(_leaf_count(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return sum(_leaf_count(item) for item in value)
    return 1


def _parse_json(text: str) -> tuple[Any, list[str]]:
    duplicate_keys: set[str] = set()

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                duplicate_keys.add(key)
            result[key] = value
        return result

    value = json.loads(text, object_pairs_hook=object_pairs)
    return value, sorted(duplicate_keys, key=str.casefold)


def _parse_ini(text: str) -> dict[str, Any]:
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    parser.read_string(text)
    result: dict[str, Any] = {}
    if parser.defaults():
        result["DEFAULT"] = dict(parser.defaults())
    for section in parser.sections():
        result[section] = {
            key: value for key, value in parser.items(section, raw=True)
            if key not in parser.defaults()
        }
    return result


def _xml_value(element: ElementTree.Element) -> dict[str, Any]:
    return {
        "tag": element.tag,
        "attributes": dict(sorted(element.attrib.items())),
        "text": (element.text or "").strip(),
        "children": [_xml_value(child) for child in list(element)],
    }


def _parse_value(format_name: str, text: str) -> tuple[Any, list[str]]:
    if format_name == "json":
        return _parse_json(text)
    if format_name == "toml":
        return tomllib.loads(text), []
    if format_name == "ini":
        return _parse_ini(text), []
    root = ElementTree.fromstring(text)
    return _xml_value(root), []


def _error_line(exc: Exception) -> int | None:
    line = getattr(exc, "lineno", None)
    if isinstance(line, int):
        return line
    position = getattr(exc, "position", None)
    if isinstance(position, tuple) and position and isinstance(position[0], int):
        return position[0] + 1
    return None


def _reference(document: ConfigDocument) -> Reference:
    artifact = document.artifact
    return Reference(
        ecosystem="config",
        kind="config.document",
        identity=artifact.relative_path.replace("/", "\\"),
        mod_name=artifact.mod_name,
        source_path=str(artifact.absolute_path),
        line=document.error_line or 1,
        details={
            "format": document.format,
            "scope": document.scope,
            "encoding": document.encoding,
            "parsed": document.parsed,
            "semantic_hash": document.semantic_hash,
            "entry_count": document.entry_count,
            "duplicate_keys": document.duplicate_keys,
            "relative_path": artifact.relative_path,
            "deployed_state": artifact.deployed_state,
            "deployed_source": artifact.deployed_source,
            "error": document.error,
        },
    )


def parse_config_documents(
    artifacts: Iterable[Artifact],
) -> tuple[list[ConfigDocument], list[Reference], list[Finding]]:
    documents: list[ConfigDocument] = []
    references: list[Reference] = []
    findings: list[Finding] = []
    for artifact in artifacts:
        extension = artifact.extension.casefold()
        if extension not in CONFIG_EXTENSIONS:
            continue
        format_name = extension[1:]
        encoding = "unknown"
        try:
            text, encoding = _decode(artifact.absolute_path.read_bytes())
            value, duplicate_keys = _parse_value(format_name, text)
            document = ConfigDocument(
                artifact=artifact,
                format=format_name,
                scope=_scope(artifact.relative_path),
                encoding=encoding,
                parsed=True,
                semantic_hash=_fingerprint(value),
                entry_count=_leaf_count(value),
                duplicate_keys=duplicate_keys,
            )
        except (OSError, UnicodeError, ValueError, configparser.Error, ElementTree.ParseError) as exc:
            document = ConfigDocument(
                artifact=artifact,
                format=format_name,
                scope=_scope(artifact.relative_path),
                encoding=str(encoding),
                parsed=False,
                semantic_hash=None,
                entry_count=0,
                duplicate_keys=[],
                error=str(exc),
                error_line=_error_line(exc),
            )
        documents.append(document)
        reference = _reference(document)
        references.append(reference)
        if not document.parsed:
            findings.append(Finding(
                rule_id="CFG-PARSE-ERROR",
                severity="error",
                confidence="high",
                summary=f"Configuration file could not be parsed: {artifact.relative_path}",
                explanation=f"The file is not valid {format_name.upper()} under the scanner's strict format parser: {document.error}",
                participants=[artifact.mod_name],
                evidence=[reference.to_dict()],
            ))
        if document.encoding == "cp1252":
            findings.append(Finding(
                rule_id="CFG-NON-UTF8",
                severity="warning",
                confidence="high",
                summary=f"Configuration file uses CP-1252 encoding: {artifact.relative_path}",
                explanation="The file is structurally valid after Windows-1252 decoding but is not valid UTF-8. Framework JSON/XML readers may reject it or corrupt non-ASCII text depending on their decoder.",
                participants=[artifact.mod_name],
                evidence=[reference.to_dict()],
            ))
        if document.duplicate_keys:
            findings.append(Finding(
                rule_id="CFG-DUPLICATE-KEY",
                severity="warning",
                confidence="high",
                summary=f"Configuration file repeats {len(document.duplicate_keys)} key" + ("s" if len(document.duplicate_keys) != 1 else ""),
                explanation="Duplicate JSON keys are ambiguous across readers; the scanner retained the final value for semantic comparison.",
                participants=[artifact.mod_name],
                evidence=[reference.to_dict()],
            ))
    return documents, references, findings


def analyze_config_documents(
    documents: Iterable[ConfigDocument], references: Iterable[Reference]
) -> list[Finding]:
    document_list = list(documents)
    reference_list = list(references)
    reference_by_source = {reference.source_path.casefold(): reference for reference in reference_list}
    findings: list[Finding] = []

    by_path: dict[str, list[ConfigDocument]] = defaultdict(list)
    for document in document_list:
        by_path[document.artifact.relative_path.replace("/", "\\").casefold()].append(document)
    for group in by_path.values():
        if len(group) < 2:
            continue
        refs = [reference_by_source[str(item.artifact.absolute_path).casefold()] for item in group]
        hashes = {item.semantic_hash for item in group if item.semantic_hash is not None}
        all_parsed = all(item.parsed for item in group)
        identical = all_parsed and len(hashes) == 1
        findings.append(Finding(
            rule_id="CFG-PATH-DUPLICATE" if identical else "CFG-PATH-OVERRIDE",
            severity="info" if identical else "warning",
            confidence="high" if all_parsed else "medium",
            summary=(
                f"Semantically identical configuration providers: {group[0].artifact.relative_path}"
                if identical
                else f"Competing configuration providers: {group[0].artifact.relative_path}"
            ),
            explanation=(
                "Multiple Vortex packages provide the same configuration path and parse to the same value. The selected deployment winner is behaviorally equivalent."
                if identical
                else "Multiple Vortex packages provide the same configuration path. Their parsed values differ or at least one provider is invalid, so only the selected deployment winner is effective."
            ),
            participants=sorted({item.artifact.mod_name for item in group}, key=str.casefold),
            evidence=[reference.to_dict() for reference in refs],
        ))

    active = [
        document for document in document_list
        if document.artifact.deployed_state != "overridden"
    ]
    by_scope: dict[str, list[ConfigDocument]] = defaultdict(list)
    for document in active:
        by_scope[document.scope.casefold()].append(document)
    for group in by_scope.values():
        packages = sorted({item.artifact.mod_name for item in group}, key=str.casefold)
        if len(packages) < 2:
            continue
        scope = group[0].scope
        refs = [reference_by_source[str(item.artifact.absolute_path).casefold()] for item in group]
        findings.append(Finding(
            rule_id="CFG-SCOPE-MULTI-PACKAGE",
            severity="info",
            confidence="high",
            summary=f"Configuration scope has {len(packages)} package owners: {scope}",
            explanation="These packages contribute different active files to one framework or mod configuration scope. This is ownership context, not a conflict; exact shared paths are compared separately.",
            participants=packages,
            evidence=[{"scope": scope, "documents": [reference.to_dict() for reference in refs]}],
        ))
    return findings


def build_config_coverage(
    documents: Iterable[ConfigDocument], references: Iterable[Reference]
) -> dict[str, Any]:
    document_list = list(documents)
    reference_list = list(references)
    formats = []
    for format_name in ("json", "toml", "ini", "xml"):
        group = [document for document in document_list if document.format == format_name]
        failed = sum(not item.parsed for item in group)
        formats.append({
            "name": format_name.upper(),
            "status": "partial" if failed else "analyzed",
            "documents": len(group),
            "parsed": sum(item.parsed for item in group),
            "failed": failed,
            "non_utf8": sum(item.encoding == "cp1252" for item in group),
            "duplicate_keys": sum(len(item.duplicate_keys) for item in group),
            "entries": sum(item.entry_count for item in group),
            "note": "Strict structural parsing and semantic fingerprinting are enabled.",
        })
    active = [item for item in document_list if item.artifact.deployed_state != "overridden"]
    scopes: dict[str, set[str]] = defaultdict(set)
    for document in active:
        scopes[document.scope.casefold()].add(document.artifact.mod_name)
    path_counts = Counter(
        item.artifact.relative_path.replace("/", "\\").casefold()
        for item in document_list
    )
    return {
        "documents": len(document_list),
        "sections": [
            {
                "name": "configuration ownership",
                "documents": len(active),
                "status": "analyzed",
                "note": "Exact deployment paths and broader CET/framework ownership scopes are attributed to Vortex packages.",
            },
            {
                "name": "configuration semantics",
                "documents": sum(item.parsed for item in document_list),
                "status": "analyzed" if all(item.parsed for item in document_list) else "partial",
                "note": "Parsed documents receive format-normalized semantic hashes; same-path providers are compared without relying on whitespace or key order.",
            },
        ],
        "configuration_formats": formats,
        "ownership_operations": [{
            "name": "configuration ownership",
            "status": "analyzed",
            "documents": len(document_list),
            "active_documents": len(active),
            "scopes": len(scopes),
            "shared_scopes": sum(len(packages) > 1 for packages in scopes.values()),
            "shared_paths": sum(count > 1 for count in path_counts.values()),
            "references": len(reference_list),
            "note": "A shared scope is informational; only an exact shared deployed path can overwrite another provider.",
        }],
    }
