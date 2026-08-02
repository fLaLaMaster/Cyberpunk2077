from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .models import Artifact, Finding, Reference, normalize_game_path
from .tweakxl import is_tweak_artifact


LOG_LINE_PATTERN = re.compile(
    r"^\[(?P<timestamp>[^]]+)] \[(?P<thread>[^]]+)] "
    r"\[(?P<level>error|warning|warn)] (?P<message>.*)$",
    re.IGNORECASE,
)
READING_PATTERN = re.compile(r'\[info] Reading "(?P<path>.+)"\.\.\.$', re.IGNORECASE)
CLONE_PATTERN = re.compile(
    r"^(?P<identity>[^:]+): Cannot clone (?P<target>.+), "
    r"the record doesn't exist\.$"
)
UNKNOWN_PROPERTY_PATTERN = re.compile(
    r"^(?P<identity>[^:]+): Unknown property (?P<property>[^.]+)\.$"
)
AMBIGUOUS_PATTERN = re.compile(
    r"^(?P<identity>[^:]+): Ambiguous definition\. "
    r"The value type cannot be determined\.$"
)
DANGLING_PATTERN = re.compile(
    r"^(?P<identity>.+?) refers to a non-existent record or flat "
    r"(?P<target><TDBID:[^>]+>)\.$"
)


@dataclass(slots=True)
class TweakXLRuntimeEvent:
    log_line: int
    timestamp: str
    level: str
    message: str
    tweak_path: str | None
    rule_id: str
    identity: str | None = None
    target: str | None = None
    property_name: str | None = None


def find_latest_tweakxl_log(game_root: Path) -> Path | None:
    log_root = game_root / "red4ext" / "plugins" / "TweakXL"
    if not log_root.is_dir():
        return None
    logs = [path for path in log_root.glob("TweakXL-*.log") if path.is_file()]
    return max(logs, key=lambda path: (path.stat().st_mtime_ns, path.name)) if logs else None


def _classify(level: str, message: str) -> tuple[str, str | None, str | None, str | None]:
    if match := CLONE_PATTERN.match(message):
        return (
            "TXL-RUNTIME-CLONE-FAILED",
            match.group("identity"),
            match.group("target"),
            None,
        )
    if match := UNKNOWN_PROPERTY_PATTERN.match(message):
        return (
            "TXL-RUNTIME-UNKNOWN-PROPERTY",
            match.group("identity"),
            None,
            match.group("property"),
        )
    if match := AMBIGUOUS_PATTERN.match(message):
        return (
            "TXL-RUNTIME-AMBIGUOUS-DEFINITION",
            match.group("identity"),
            None,
            None,
        )
    if match := DANGLING_PATTERN.match(message):
        return (
            "TXL-RUNTIME-DANGLING-REFERENCE",
            match.group("identity"),
            match.group("target"),
            None,
        )
    identity = message.split(":", 1)[0] if ":" in message else None
    rule = "TXL-RUNTIME-ERROR" if level == "error" else "TXL-RUNTIME-WARNING"
    return rule, identity, None, None


def parse_tweakxl_runtime_log(path: Path) -> tuple[list[TweakXLRuntimeEvent], int]:
    events: list[TweakXLRuntimeEvent] = []
    current_tweak: str | None = None
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    for line_number, line in enumerate(lines, start=1):
        if match := READING_PATTERN.search(line):
            current_tweak = match.group("path")
            continue
        if "[info] Importing tweaks..." in line:
            current_tweak = None
            continue
        match = LOG_LINE_PATTERN.match(line)
        if not match:
            continue
        level = match.group("level").casefold()
        if level == "warn":
            level = "warning"
        message = match.group("message")
        rule, identity, target, property_name = _classify(level, message)
        events.append(
            TweakXLRuntimeEvent(
                log_line=line_number,
                timestamp=match.group("timestamp"),
                level=level,
                message=message,
                tweak_path=current_tweak,
                rule_id=rule,
                identity=identity,
                target=target,
                property_name=property_name,
            )
        )
    return events, len(lines)


def _source_candidates(
    event: TweakXLRuntimeEvent,
    artifact_by_relative: dict[str, Artifact],
    references: list[Reference],
) -> list[dict[str, Any]]:
    artifact = None
    if event.tweak_path:
        relative = normalize_game_path(rf"r6\tweaks\{event.tweak_path}")
        artifact = artifact_by_relative.get(relative)

    candidates = references
    if artifact:
        source_key = str(artifact.absolute_path).casefold()
        candidates = [item for item in references if item.source_path.casefold() == source_key]

    wanted = event.identity
    if event.rule_id == "TXL-RUNTIME-UNKNOWN-PROPERTY" and wanted:
        wanted = f"{wanted}.{event.property_name}"

    if wanted:
        exact = [item for item in candidates if item.identity == wanted]
        if exact:
            candidates = exact
        elif event.rule_id == "TXL-RUNTIME-AMBIGUOUS-DEFINITION":
            prefix = f"{wanted}."
            candidates = [item for item in candidates if item.identity.startswith(prefix)]
        else:
            candidates = []
    else:
        candidates = []

    sources: dict[tuple[str, str], dict[str, Any]] = {}
    for reference in candidates:
        key = (reference.mod_name, reference.source_path.casefold())
        source = sources.setdefault(
            key,
            {
                "mod_name": reference.mod_name,
                "source_path": reference.source_path,
                "line": reference.line,
                "reference_kinds": set(),
            },
        )
        if reference.line is not None and (
            source["line"] is None or reference.line < source["line"]
        ):
            source["line"] = reference.line
        source["reference_kinds"].add(reference.kind)

    if artifact and not sources:
        fallback_line = None
        if event.property_name:
            property_pattern = re.compile(
                rf"^\s*{re.escape(event.property_name)}\s*:", re.IGNORECASE
            )
            for line_number, text in enumerate(
                artifact.absolute_path.read_text(
                    encoding="utf-8-sig", errors="replace"
                ).splitlines(),
                start=1,
            ):
                if property_pattern.search(text):
                    fallback_line = line_number
                    break
        sources[(artifact.mod_name, str(artifact.absolute_path).casefold())] = {
            "mod_name": artifact.mod_name,
            "source_path": str(artifact.absolute_path),
            "line": fallback_line,
            "reference_kinds": set(),
        }

    result = []
    for source in sorted(
        sources.values(),
        key=lambda item: (item["mod_name"].casefold(), item["source_path"].casefold()),
    ):
        source["reference_kinds"] = sorted(source["reference_kinds"])
        result.append(source)
    return result


def _static_correlations(event: TweakXLRuntimeEvent, findings: Iterable[Finding]) -> list[str]:
    if event.rule_id != "TXL-RUNTIME-CLONE-FAILED":
        return []
    correlated: set[str] = set()
    for finding in findings:
        if finding.rule_id not in {"TXL-MISSING-BASE", "TXL-BASE-CASE-MISMATCH"}:
            continue
        for evidence in finding.evidence:
            if event.target and evidence.get("target") == event.target:
                correlated.add(finding.rule_id)
    return sorted(correlated)


def analyze_tweakxl_runtime_logs(
    game_root: Path,
    artifacts: Iterable[Artifact],
    references: Iterable[Reference],
    static_findings: Iterable[Finding],
) -> tuple[list[Finding], dict[str, Any]]:
    log_path = find_latest_tweakxl_log(game_root)
    if log_path is None:
        return [], {
            "name": "latest TweakXL log",
            "status": "unavailable",
            "log_path": "",
            "lines": 0,
            "errors": 0,
            "warnings": 0,
            "events": 0,
            "correlated_events": 0,
            "static_confirmations": 0,
            "findings": 0,
            "note": "No timestamped TweakXL runtime log was found.",
        }

    events, line_count = parse_tweakxl_runtime_log(log_path)
    reference_list = list(references)
    static_finding_list = list(static_findings)
    artifact_by_relative = {
        artifact.normalized_path: artifact
        for artifact in artifacts
        if is_tweak_artifact(artifact)
    }

    grouped: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
    correlated_events = 0
    static_confirmation_events = 0
    for event in events:
        sources = _source_candidates(event, artifact_by_relative, reference_list)
        participants = tuple(
            sorted({source["mod_name"] for source in sources}, key=str.casefold)
        )
        static_rules = _static_correlations(event, static_finding_list)
        if sources:
            correlated_events += 1
        if static_rules:
            static_confirmation_events += 1
        evidence: dict[str, Any] = {
            "log_path": str(log_path),
            "log_line": event.log_line,
            "timestamp": event.timestamp,
            "level": event.level,
            "message": event.message,
            "identity": event.identity,
            "target": event.target,
            "tweak_path": event.tweak_path,
            "sources": sources,
            "static_rules": static_rules,
        }
        if len(sources) == 1:
            evidence["mod_name"] = sources[0]["mod_name"]
            evidence["source_path"] = sources[0]["source_path"]
            evidence["line"] = sources[0]["line"]
        grouped[(event.rule_id, participants)].append(evidence)

    descriptions = {
        "TXL-RUNTIME-CLONE-FAILED": (
            "error",
            "high",
            "failed record clone",
            "TweakXL could not create a record because its clone source does not exist. "
            "This is direct runtime confirmation, not a heuristic static overlap.",
        ),
        "TXL-RUNTIME-UNKNOWN-PROPERTY": (
            "error",
            "high",
            "unknown record properties",
            "TweakXL rejected properties that are not present on the target record type. "
            "The affected assignments were not applied.",
        ),
        "TXL-RUNTIME-AMBIGUOUS-DEFINITION": (
            "error",
            "high",
            "ambiguous record definitions",
            "TweakXL could not determine a value type while importing these record "
            "definitions or mutations. Each log occurrence is attributed to the tweak "
            "file being read at that moment.",
        ),
        "TXL-RUNTIME-DANGLING-REFERENCE": (
            "warning",
            "high",
            "non-existent record references",
            "TweakXL's post-import validation found references to records or flats that "
            "do not exist. Hash-only targets cannot be named from the log, but the "
            "owning flat and all installed source candidates are retained.",
        ),
        "TXL-RUNTIME-ERROR": (
            "error",
            "high",
            "other TweakXL runtime errors",
            "TweakXL emitted runtime errors that do not match a more specific scanner rule.",
        ),
        "TXL-RUNTIME-WARNING": (
            "warning",
            "high",
            "other TweakXL runtime warnings",
            "TweakXL emitted runtime warnings that do not match a more specific scanner rule.",
        ),
    }
    findings: list[Finding] = []
    for (rule_id, participants), evidence in sorted(
        grouped.items(), key=lambda item: (item[0][0], item[0][1])
    ):
        severity, confidence, noun, explanation = descriptions[rule_id]
        unique_identities = len(
            {item["identity"] for item in evidence if item.get("identity")}
        )
        identity_text = (
            f" across {unique_identities} identities" if unique_identities > 1 else ""
        )
        findings.append(
            Finding(
                rule_id=rule_id,
                severity=severity,
                confidence=confidence,
                summary=f"{len(evidence)} {noun}{identity_text}",
                explanation=explanation,
                participants=list(participants),
                evidence=evidence,
            )
        )

    coverage = {
        "name": "latest TweakXL log",
        "status": "analyzed",
        "log_path": str(log_path),
        "lines": line_count,
        "errors": sum(event.level == "error" for event in events),
        "warnings": sum(event.level == "warning" for event in events),
        "events": len(events),
        "correlated_events": correlated_events,
        "static_confirmations": static_confirmation_events,
        "findings": len(findings),
        "note": "The newest timestamped log is parsed; repeated events are consolidated by rule and attributed mod set.",
    }
    return findings, coverage
