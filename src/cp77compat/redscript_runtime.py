from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .models import Artifact, Finding, Reference, normalize_game_path


DIAGNOSTIC_HEADER = re.compile(
    r"^\[(?P<level>WARN|ERROR)\s+-\s+(?P<timestamp>.+?)]\s+At\s+"
    r"(?P<path>.+):(?P<line>\d+):(?P<column>\d+):$"
)
LOG_HEADER = re.compile(r"^\[(?P<level>INFO|WARN|ERROR)\s+-\s+(?P<timestamp>.+?)]\s*(?P<message>.*)$")


@dataclass(slots=True)
class RedscriptRuntimeEvent:
    level: str
    timestamp: str
    source_path: str
    source_line: int
    source_column: int
    log_line: int
    source_text: str
    message: str
    rule_id: str
    identity: str | None = None
    sources: list[dict[str, Any]] | None = None
    static_rules: list[str] | None = None

    def to_dict(self, log_path: Path) -> dict[str, Any]:
        return {
            "log_path": str(log_path),
            "log_line": self.log_line,
            "timestamp": self.timestamp,
            "level": self.level,
            "source_path": self.source_path,
            "line": self.source_line,
            "column": self.source_column,
            "source_text": self.source_text,
            "message": self.message,
            "identity": self.identity,
            "sources": self.sources or [],
            "static_rules": self.static_rules or [],
        }


def _rule_for_message(message: str) -> str:
    lowered = message.casefold()
    if "method replacement overwrites a previous annotation" in lowered:
        return "RS-RUNTIME-METHOD-REPLACEMENT-OVERWRITE"
    if "@addfield" in lowered and "conflicts with an existing field" in lowered:
        return "RS-RUNTIME-ADDED-FIELD-CONFLICT"
    if "could not find a method with a matching signature" in lowered:
        return "RS-RUNTIME-ANNOTATED-METHOD-NOT-FOUND"
    if "duplicates an existing method with the same signature" in lowered:
        return "RS-RUNTIME-ADDED-METHOD-CONFLICT"
    return "RS-RUNTIME-COMPILER-DIAGNOSTIC"


def parse_redscript_runtime_log(
    path: Path,
) -> tuple[list[RedscriptRuntimeEvent], dict[str, Any]]:
    events: list[RedscriptRuntimeEvent] = []
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    compiled_files: list[str] = []
    compilation_complete = False
    output_saved = False
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.strip().casefold().endswith(".reds") and not line.startswith("["):
            compiled_files.append(line.strip())
        if "Compilation complete" in line:
            compilation_complete = True
        if "Output successfully saved" in line:
            output_saved = True
        match = DIAGNOSTIC_HEADER.match(line)
        if not match:
            index += 1
            continue
        source_text = lines[index + 1].strip() if index + 1 < len(lines) else ""
        message_index = index + 3
        message_lines: list[str] = []
        while message_index < len(lines):
            candidate = lines[message_index]
            if not candidate.strip():
                break
            if LOG_HEADER.match(candidate):
                break
            message_lines.append(candidate.strip())
            message_index += 1
        message = " ".join(message_lines)
        events.append(
            RedscriptRuntimeEvent(
                level=("warning" if match.group("level") == "WARN" else "error"),
                timestamp=match.group("timestamp"),
                source_path=match.group("path"),
                source_line=int(match.group("line")),
                source_column=int(match.group("column")),
                log_line=index + 1,
                source_text=source_text,
                message=message,
                rule_id=_rule_for_message(message),
            )
        )
        index = max(index + 1, message_index)
    return events, {
        "lines": len(lines),
        "compiled_files": len(set(compiled_files)),
        "compilation_complete": compilation_complete,
        "output_saved": output_saved,
    }


def _artifact_index(artifacts: Iterable[Artifact]) -> dict[str, list[Artifact]]:
    result: dict[str, list[Artifact]] = defaultdict(list)
    for artifact in artifacts:
        if artifact.extension.casefold() == ".reds":
            if artifact.deployed_state == "overridden":
                continue
            result[artifact.normalized_path].append(artifact)
    return result


def _source_relative_path(source_path: str, game_root: Path) -> str | None:
    try:
        return str(Path(source_path).resolve(strict=False).relative_to(game_root.resolve(strict=False)))
    except ValueError:
        return None


def analyze_redscript_runtime_log(
    game_root: Path,
    artifacts: Iterable[Artifact],
    references: Iterable[Reference],
    static_findings: Iterable[Finding],
) -> tuple[list[Finding], dict[str, Any]]:
    log_path = game_root / "r6" / "logs" / "redscript_rCURRENT.log"
    empty_coverage = {
        "name": "redscript_rCURRENT.log",
        "status": "unsupported",
        "log_path": str(log_path),
        "lines": 0,
        "compiled_files": 0,
        "errors": 0,
        "warnings": 0,
        "events": 0,
        "correlated_events": 0,
        "static_confirmations": 0,
        "findings": 0,
        "compilation_complete": False,
        "output_saved": False,
        "note": "The current REDscript compiler log was not found.",
    }
    if not log_path.is_file():
        return [], empty_coverage
    try:
        events, stats = parse_redscript_runtime_log(log_path)
    except OSError as exc:
        empty_coverage["status"] = "partial"
        empty_coverage["note"] = f"The current REDscript compiler log could not be read: {exc}"
        return [], empty_coverage

    artifact_by_path = _artifact_index(artifacts)
    refs_by_source_line: dict[tuple[str, int], list[Reference]] = defaultdict(list)
    for reference in references:
        refs_by_source_line[(str(Path(reference.source_path).resolve(strict=False)).casefold(), reference.line or 0)].append(reference)
    static_by_identity: dict[str, list[Finding]] = defaultdict(list)
    for finding in static_findings:
        if not finding.rule_id.startswith("RS-"):
            continue
        for evidence in finding.evidence:
            identity = evidence.get("identity")
            if isinstance(identity, str):
                static_by_identity[identity].append(finding)

    correlated = 0
    static_confirmations = 0
    for event in events:
        relative = _source_relative_path(event.source_path, game_root)
        source_artifacts = artifact_by_path.get(normalize_game_path(relative), []) if relative else []
        source_refs: list[Reference] = []
        for artifact in source_artifacts:
            source_refs.extend(
                refs_by_source_line.get(
                    (str(artifact.absolute_path.resolve(strict=False)).casefold(), event.source_line),
                    [],
                )
            )
        if source_refs:
            event.identity = source_refs[0].identity
            event.sources = [reference.to_dict() for reference in source_refs]
        elif source_artifacts:
            event.sources = [
                {
                    "mod_name": artifact.mod_name,
                    "source_path": str(artifact.absolute_path),
                    "line": event.source_line,
                    "match": "deployed path and line",
                }
                for artifact in source_artifacts
            ]
        if event.sources:
            correlated += 1
        static = static_by_identity.get(event.identity or "", [])
        if static:
            event.static_rules = sorted({finding.rule_id for finding in static})
            static_confirmations += 1

    grouped: dict[tuple[str, tuple[str, ...]], list[RedscriptRuntimeEvent]] = defaultdict(list)
    for event in events:
        participants = {
            str(source.get("mod_name"))
            for source in event.sources or []
            if source.get("mod_name")
        }
        for finding in static_by_identity.get(event.identity or "", []):
            participants.update(finding.participants)
        grouped[(event.rule_id, tuple(sorted(participants, key=str.casefold)))].append(event)

    descriptions = {
        "RS-RUNTIME-METHOD-REPLACEMENT-OVERWRITE": (
            "warning",
            "method replacements overwritten by later annotations",
            "The REDscript compiler confirms that only the last replacement for each exact method remains active. Earlier replacement behavior is unavailable unless the bodies are equivalent.",
        ),
        "RS-RUNTIME-ADDED-FIELD-CONFLICT": (
            "warning",
            "field additions ignored because the field already exists",
            "The compiler kept the first field and ignored a later @addField annotation targeting the same class and field name.",
        ),
        "RS-RUNTIME-ANNOTATED-METHOD-NOT-FOUND": (
            "error",
            "annotated methods with no matching target",
            "The compiler could not resolve the annotated class, method name, parameter types, and return type to an existing method.",
        ),
        "RS-RUNTIME-ADDED-METHOD-CONFLICT": (
            "error",
            "duplicate added method signatures",
            "The compiler found an @addMethod annotation that duplicates an existing method signature.",
        ),
        "RS-RUNTIME-COMPILER-DIAGNOSTIC": (
            "error",
            "other REDscript compiler diagnostics",
            "The current REDscript log contains compiler diagnostics not covered by a more specific compatibility rule. Inspect the attached source and message.",
        ),
    }
    findings: list[Finding] = []
    for (rule_id, participants), group in sorted(
        grouped.items(), key=lambda item: (item[0][0], tuple(name.casefold() for name in item[0][1]))
    ):
        severity, label, explanation = descriptions[rule_id]
        if rule_id == "RS-RUNTIME-COMPILER-DIAGNOSTIC" and all(event.level == "warning" for event in group):
            severity = "warning"
        findings.append(
            Finding(
                rule_id=rule_id,
                severity=severity,
                confidence="high",
                summary=f"{len(group)} {label}",
                explanation=explanation,
                participants=list(participants),
                evidence=[event.to_dict(log_path) for event in group],
            )
        )

    errors = sum(event.level == "error" for event in events)
    warnings = sum(event.level == "warning" for event in events)
    coverage = {
        "name": "redscript_rCURRENT.log",
        "status": "analyzed",
        "log_path": str(log_path),
        "lines": stats["lines"],
        "compiled_files": stats["compiled_files"],
        "errors": errors,
        "warnings": warnings,
        "events": len(events),
        "correlated_events": correlated,
        "static_confirmations": static_confirmations,
        "findings": len(findings),
        "compilation_complete": stats["compilation_complete"],
        "output_saved": stats["output_saved"],
        "note": "The current compiler log is parsed and diagnostics are attributed to staging sources and exact annotated signatures where possible.",
    }
    return findings, coverage
