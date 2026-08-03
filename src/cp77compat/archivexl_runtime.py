from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .models import Artifact, Finding, Reference, normalize_game_path


SESSION_PATTERN = re.compile(
    r"^ArchiveXL-(?P<session>\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})"
    r"(?:\.(?P<rotation>\d+))?\.log$",
    re.IGNORECASE,
)
LOG_LINE_PATTERN = re.compile(
    r"^\[(?P<timestamp>[^]]+)] \[(?P<thread>[^]]+)] "
    r"\[(?P<level>error|warning|warn)] "
    r"(?:\[(?P<component>[^]]+)])?\s*(?P<message>.*)$",
    re.IGNORECASE,
)
LOADING_PATTERN = re.compile(r'\[info] Loading "(?P<config>.+\.xl)"\.\.\.$', re.IGNORECASE)
APPLYING_PATTERN = re.compile(
    r'\[info] \[WorldStreaming] Applying changes from "(?P<config>.+\.xl)"\.\.\.$',
    re.IGNORECASE,
)
QUEST_PHASE_PATTERN = re.compile(
    r'^Phase "(?P<identity>.+)" doesn\'t exist\. Skipped\.$'
)
LOCALIZATION_FAILED_PATTERN = re.compile(
    r'^Resource "(?P<identity>.+)" failed to load\.$'
)
LOCALIZATION_SUMMARY_PATTERN = re.compile(r"^Translations merged with issues\.$")
WORLD_EXPECTATION_PATTERN = re.compile(
    r"^(?P<config>.+\.xl): The target sector has (?P<actual>\d+) node\(s\), "
    r"but the mod expects (?P<expected>\d+)\.$",
    re.IGNORECASE,
)
WORLD_SKIPPED_PATTERN = re.compile(
    r'^No patches have been applied to "(?P<identity>.+)"\.$'
)
JOURNAL_RESOURCE_FAILED_PATTERN = re.compile(
    r'^Resource "(?P<identity>.+)" failed to load\.$'
)
JOURNAL_ISSUE_PATTERN = re.compile(
    r"^(?P<identity>.+): (?P<reason>Cannot modify entry, (?:path not fould|type mismatch)|Path not fould)\.$"
)
JOURNAL_SUMMARY_PATTERN = re.compile(r"^Journal entries merged with issues\.$")
CUSTOMIZATION_OPTION_PATTERN = re.compile(
    r'^Option "(?P<identity>.*)" can\'t be merged: expected '
    r'(?P<expected>[^,]+), got (?P<actual>.+)\.$'
)


@dataclass(slots=True)
class ArchiveXLRuntimeEvent:
    log_path: str
    log_line: int
    timestamp: str
    thread: str
    level: str
    component: str | None
    message: str
    rule_id: str
    config_name: str | None = None
    identity: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


def find_latest_archivexl_log_session(game_root: Path) -> tuple[str | None, list[Path]]:
    log_root = game_root / "red4ext" / "plugins" / "ArchiveXL"
    if not log_root.is_dir():
        return None, []
    sessions: dict[str, list[tuple[int, Path]]] = defaultdict(list)
    for path in log_root.glob("ArchiveXL-*.log"):
        if not path.is_file() or not (match := SESSION_PATTERN.match(path.name)):
            continue
        rotation = int(match.group("rotation") or 0)
        sessions[match.group("session")].append((rotation, path))
    if not sessions:
        return None, []
    session = max(sessions)
    # ArchiveXL renames the older chunk to .1 (then .2, etc.) and continues in
    # the unnumbered file. Highest rotation is therefore chronologically first.
    paths = [path for _rotation, path in sorted(sessions[session], key=lambda item: -item[0])]
    return session, paths


def parse_archivexl_runtime_logs(
    paths: Iterable[Path],
) -> tuple[list[ArchiveXLRuntimeEvent], int]:
    events: list[ArchiveXLRuntimeEvent] = []
    current_config: dict[str, str] = {}
    pending_localization: dict[str, int] = {}
    pending_world: dict[str, int] = {}
    pending_journal: dict[str, int] = {}
    line_count = 0

    for path in paths:
        with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
            for line_number, raw_line in enumerate(stream, start=1):
                line_count += 1
                line = raw_line.rstrip("\r\n")
                if match := LOADING_PATTERN.search(line):
                    thread_match = re.match(r"^\[[^]]+] \[(?P<thread>[^]]+)]", line)
                    if thread_match:
                        current_config[thread_match.group("thread")] = match.group("config")
                    continue
                if match := APPLYING_PATTERN.search(line):
                    thread_match = re.match(r"^\[[^]]+] \[(?P<thread>[^]]+)]", line)
                    if thread_match:
                        current_config[thread_match.group("thread")] = match.group("config")
                    continue

                match = LOG_LINE_PATTERN.match(line)
                if not match:
                    continue
                thread = match.group("thread")
                level = match.group("level").casefold()
                if level == "warn":
                    level = "warning"
                component = match.group("component")
                message = match.group("message")
                config_name = current_config.get(thread)
                identity = None
                details: dict[str, Any] = {}

                if component == "QuestPhase" and (specific := QUEST_PHASE_PATTERN.match(message)):
                    rule_id = "AXL-RUNTIME-QUEST-PHASE-MISSING"
                    identity = specific.group("identity")
                elif component == "Localization" and (
                    specific := LOCALIZATION_FAILED_PATTERN.match(message)
                ):
                    rule_id = "AXL-RUNTIME-LOCALIZATION-FAILED"
                    identity = specific.group("identity")
                    pending_localization[thread] = len(events)
                elif component == "Localization" and LOCALIZATION_SUMMARY_PATTERN.match(message):
                    rule_id = "AXL-RUNTIME-LOCALIZATION-FAILED"
                    pending_index = pending_localization.get(thread)
                    if pending_index is not None:
                        identity = events[pending_index].identity
                        config_name = events[pending_index].config_name
                        details["related_log_path"] = events[pending_index].log_path
                        details["related_log_line"] = events[pending_index].log_line
                        details["consequence"] = True
                elif component == "WorldStreaming" and (
                    specific := WORLD_EXPECTATION_PATTERN.match(message)
                ):
                    rule_id = "AXL-RUNTIME-STREAMING-EXPECTED-NODES"
                    config_name = specific.group("config")
                    details["actual_nodes"] = int(specific.group("actual"))
                    details["expected_nodes"] = int(specific.group("expected"))
                    pending_world[thread] = len(events)
                elif component == "WorldStreaming" and (
                    specific := WORLD_SKIPPED_PATTERN.match(message)
                ):
                    rule_id = "AXL-RUNTIME-STREAMING-EXPECTED-NODES"
                    identity = specific.group("identity")
                    details["consequence"] = True
                    pending_index = pending_world.get(thread)
                    if pending_index is not None:
                        pending = events[pending_index]
                        pending.identity = identity
                        config_name = pending.config_name or config_name
                        details["related_log_path"] = pending.log_path
                        details["related_log_line"] = pending.log_line
                elif component == "Journal" and (
                    specific := JOURNAL_RESOURCE_FAILED_PATTERN.match(message)
                ):
                    rule_id = "AXL-RUNTIME-JOURNAL-RESOURCE-FAILED"
                    identity = specific.group("identity")
                    pending_journal[thread] = len(events)
                elif component == "Journal" and (
                    specific := JOURNAL_ISSUE_PATTERN.match(message)
                ):
                    rule_id = "AXL-RUNTIME-JOURNAL-MERGE-ISSUE"
                    identity = specific.group("identity")
                    details["reason"] = specific.group("reason")
                    pending_journal[thread] = len(events)
                elif component == "Journal" and JOURNAL_SUMMARY_PATTERN.match(message):
                    pending_index = pending_journal.get(thread)
                    if pending_index is not None:
                        pending = events[pending_index]
                        rule_id = pending.rule_id
                        identity = pending.identity
                        config_name = pending.config_name
                        details["related_log_path"] = pending.log_path
                        details["related_log_line"] = pending.log_line
                        details["consequence"] = True
                    else:
                        rule_id = "AXL-RUNTIME-WARNING"
                elif component == "CharacterCustomization" and (
                    specific := CUSTOMIZATION_OPTION_PATTERN.match(message)
                ):
                    rule_id = "AXL-RUNTIME-CUSTOMIZATION-TYPE-MISMATCH"
                    identity = specific.group("identity")
                    details["expected_type"] = specific.group("expected")
                    details["actual_type"] = specific.group("actual")
                else:
                    rule_id = (
                        "AXL-RUNTIME-ERROR" if level == "error" else "AXL-RUNTIME-WARNING"
                    )

                events.append(
                    ArchiveXLRuntimeEvent(
                        log_path=str(path),
                        log_line=line_number,
                        timestamp=match.group("timestamp"),
                        thread=thread,
                        level=level,
                        component=component,
                        message=message,
                        rule_id=rule_id,
                        config_name=config_name,
                        identity=identity,
                        details=details,
                    )
                )
    return events, line_count


def _active_xl_artifacts(artifacts: Iterable[Artifact]) -> list[Artifact]:
    return [
        artifact
        for artifact in artifacts
        if artifact.extension == ".xl" and artifact.deployed_state != "overridden"
    ]


def _text_source_index(
    artifacts: list[Artifact], identities: set[str]
) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, dict[tuple[str, str], dict[str, Any]]] = {
        identity: {} for identity in identities
    }
    folded_identities = {identity.casefold(): identity for identity in identities}
    for artifact in artifacts:
        with artifact.absolute_path.open("r", encoding="utf-8-sig", errors="replace") as stream:
            for line_number, line in enumerate(stream, start=1):
                folded_line = line.casefold()
                for folded_identity, identity in folded_identities.items():
                    if folded_identity not in folded_line:
                        continue
                    key = (artifact.mod_name, str(artifact.absolute_path).casefold())
                    source = index[identity].setdefault(
                        key,
                        {
                            "mod_name": artifact.mod_name,
                            "source_path": str(artifact.absolute_path),
                            "line": line_number,
                            "lines": [],
                            "reference_kinds": [],
                            "match": "source text",
                        },
                    )
                    source["lines"].append(line_number)
    return {
        identity: sorted(
            sources.values(),
            key=lambda item: (item["mod_name"].casefold(), item["source_path"].casefold()),
        )
        for identity, sources in index.items()
    }


def _reference_sources(
    identity: str,
    references: list[Reference],
    active_paths: set[str],
) -> list[dict[str, Any]]:
    normalized = normalize_game_path(identity)
    matched = [
        reference
        for reference in references
        if reference.normalized_identity == normalized
        and reference.source_path.casefold() in active_paths
    ]
    sources: dict[tuple[str, str], dict[str, Any]] = {}
    for reference in matched:
        key = (reference.mod_name, reference.source_path.casefold())
        source = sources.setdefault(
            key,
            {
                "mod_name": reference.mod_name,
                "source_path": reference.source_path,
                "line": reference.line,
                "lines": [],
                "reference_kinds": set(),
                "match": "semantic reference",
            },
        )
        if reference.line is not None:
            source["lines"].append(reference.line)
            if source["line"] is None or reference.line < source["line"]:
                source["line"] = reference.line
        source["reference_kinds"].add(reference.kind)
    result = []
    for source in sorted(
        sources.values(),
        key=lambda item: (item["mod_name"].casefold(), item["source_path"].casefold()),
    ):
        source["lines"] = sorted(set(source["lines"]))
        source["reference_kinds"] = sorted(source["reference_kinds"])
        result.append(source)
    return result


def _customization_option_sources(
    identity: str,
    references: list[Reference],
    active_paths: set[str],
) -> list[dict[str, Any]]:
    matched = [
        reference
        for reference in references
        if reference.kind == "customization.option"
        and str(reference.details.get("name") or "") == identity
        and reference.source_path.casefold() in active_paths
    ]
    sources: dict[tuple[str, str], dict[str, Any]] = {}
    for reference in matched:
        key = (reference.mod_name, reference.source_path.casefold())
        source = sources.setdefault(
            key,
            {
                "mod_name": reference.mod_name,
                "source_path": reference.source_path,
                "line": reference.line,
                "lines": [],
                "reference_kinds": [reference.kind],
                "match": "customization option name",
            },
        )
        if reference.line is not None:
            source["lines"].append(reference.line)
    return sorted(
        sources.values(),
        key=lambda item: (item["mod_name"].casefold(), item["source_path"].casefold()),
    )


def _config_sources(
    config_name: str | None,
    artifact_by_name: dict[str, list[Artifact]],
) -> list[dict[str, Any]]:
    if not config_name:
        return []
    return [
        {
            "mod_name": artifact.mod_name,
            "source_path": str(artifact.absolute_path),
            "line": None,
            "lines": [],
            "reference_kinds": [],
            "match": "runtime config name",
        }
        for artifact in artifact_by_name.get(config_name.casefold(), [])
    ]


def _contains_identity(value: Any, normalized_identity: str) -> bool:
    if isinstance(value, str):
        return normalize_game_path(value) == normalized_identity
    if isinstance(value, dict):
        return any(_contains_identity(item, normalized_identity) for item in value.values())
    if isinstance(value, list):
        return any(_contains_identity(item, normalized_identity) for item in value)
    return False


def _static_correlations(
    event: ArchiveXLRuntimeEvent, findings: Iterable[Finding]
) -> list[str]:
    if not event.identity:
        return []
    allowed: set[str]
    if event.rule_id == "AXL-RUNTIME-LOCALIZATION-FAILED":
        allowed = {"AXL-RESOURCE-NOT-INDEXED", "AXL-CROSS-MOD-RESOURCE", "AXL-PAYLOAD-FAILED"}
    elif event.rule_id == "AXL-RUNTIME-STREAMING-EXPECTED-NODES":
        allowed = {"AXL-SECTOR-EXPECTED-NODES", "AXL-SECTOR-MULTI-PATCH"}
    elif event.rule_id == "AXL-RUNTIME-QUEST-PHASE-MISSING":
        allowed = {
            "AXL-QUEST-PHASE-NOT-FOUND",
            "AXL-QUEST-PARENT-NOT-FOUND",
            "AXL-QUEST-CROSS-MOD-PHASE",
            "AXL-QUEST-CROSS-MOD-PARENT",
        }
    elif event.rule_id == "AXL-RUNTIME-JOURNAL-RESOURCE-FAILED":
        allowed = {
            "AXL-RESOURCE-NOT-INDEXED",
            "AXL-CROSS-MOD-RESOURCE",
            "AXL-PAYLOAD-FAILED",
            "AXL-JOURNAL-PAYLOAD-SHAPE",
        }
    elif event.rule_id == "AXL-RUNTIME-JOURNAL-MERGE-ISSUE":
        allowed = {
            "AXL-JOURNAL-EDIT-CONFLICT",
            "AXL-JOURNAL-EDIT-OVERLAP",
            "AXL-JOURNAL-ENTRY-CONFLICT",
            "AXL-JOURNAL-PAYLOAD-SHAPE",
        }
    elif event.rule_id == "AXL-RUNTIME-CUSTOMIZATION-TYPE-MISMATCH":
        allowed = {
            "AXL-CUSTOMIZATION-OPTION-TYPE-CONFLICT",
            "AXL-CUSTOMIZATION-PAYLOAD-SHAPE",
        }
    else:
        return []
    normalized = normalize_game_path(event.identity)
    return sorted(
        finding.rule_id
        for finding in findings
        if finding.rule_id in allowed and _contains_identity(finding.evidence, normalized)
    )


def analyze_archivexl_runtime_logs(
    game_root: Path,
    artifacts: Iterable[Artifact],
    references: Iterable[Reference],
    static_findings: Iterable[Finding],
) -> tuple[list[Finding], dict[str, Any]]:
    session, log_paths = find_latest_archivexl_log_session(game_root)
    if not log_paths:
        return [], {
            "name": "latest ArchiveXL log session",
            "status": "unavailable",
            "session": "",
            "log_path": "",
            "log_paths": [],
            "files": 0,
            "bytes": 0,
            "lines": 0,
            "errors": 0,
            "warnings": 0,
            "events": 0,
            "correlated_events": 0,
            "static_confirmations": 0,
            "findings": 0,
            "note": "No timestamped ArchiveXL runtime log session was found.",
        }

    events, line_count = parse_archivexl_runtime_logs(log_paths)
    active_artifacts = _active_xl_artifacts(artifacts)
    reference_list = list(references)
    active_paths = {str(artifact.absolute_path).casefold() for artifact in active_artifacts}
    artifact_by_name: dict[str, list[Artifact]] = defaultdict(list)
    for artifact in active_artifacts:
        artifact_by_name[artifact.absolute_path.name.casefold()].append(artifact)
    quest_identities = {
        event.identity
        for event in events
        if event.rule_id == "AXL-RUNTIME-QUEST-PHASE-MISSING" and event.identity
    }
    text_sources = _text_source_index(active_artifacts, quest_identities)

    grouped: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
    correlated_events = 0
    static_confirmation_events = 0
    for event in events:
        sources = (
            _reference_sources(event.identity, reference_list, active_paths)
            if event.identity
            else []
        )
        if (
            not sources
            and event.identity is not None
            and event.rule_id == "AXL-RUNTIME-CUSTOMIZATION-TYPE-MISMATCH"
        ):
            sources = _customization_option_sources(
                event.identity, reference_list, active_paths
            )
        if not sources and event.rule_id == "AXL-RUNTIME-QUEST-PHASE-MISSING":
            sources = text_sources.get(event.identity or "", [])
        if not sources and event.config_name:
            sources = _config_sources(event.config_name, artifact_by_name)
        if not sources and event.identity:
            sources = text_sources.get(event.identity, [])
        participants = tuple(
            sorted({source["mod_name"] for source in sources}, key=str.casefold)
        )
        static_rules = _static_correlations(event, static_findings)
        if sources:
            correlated_events += 1
        if static_rules:
            static_confirmation_events += 1
        evidence: dict[str, Any] = {
            "log_path": event.log_path,
            "log_line": event.log_line,
            "timestamp": event.timestamp,
            "level": event.level,
            "component": event.component,
            "message": event.message,
            "config_name": event.config_name,
            "identity": event.identity,
            "details": event.details,
            "sources": sources,
            "static_rules": static_rules,
        }
        if len(sources) == 1:
            evidence["mod_name"] = sources[0]["mod_name"]
            evidence["source_path"] = sources[0]["source_path"]
            evidence["line"] = sources[0]["line"]
        grouped[(event.rule_id, participants)].append(evidence)

    descriptions = {
        "AXL-RUNTIME-QUEST-PHASE-MISSING": (
            "warning",
            "high",
            "missing quest phases",
            "ArchiveXL skipped quest phase operations because the referenced parent or phase "
            "resource does not exist in the active loadout. Semantic quest references identify "
            "all installed declarations that depend on each missing phase.",
        ),
        "AXL-RUNTIME-LOCALIZATION-FAILED": (
            "error",
            "high",
            "localization resources failed to load",
            "ArchiveXL found the declared localization resource but failed to load it at "
            "runtime. The affected translations are not reliably available.",
        ),
        "AXL-RUNTIME-STREAMING-EXPECTED-NODES": (
            "error",
            "high",
            "streaming sector patches were rejected",
            "ArchiveXL rejected a world-streaming patch because the live sector node count "
            "did not equal the config's expectedNodes guard. The related patch was not applied.",
        ),
        "AXL-RUNTIME-JOURNAL-RESOURCE-FAILED": (
            "error",
            "high",
            "journal resources failed to load",
            "ArchiveXL could not load a declared journal resource, so its entry tree was not merged.",
        ),
        "AXL-RUNTIME-JOURNAL-MERGE-ISSUE": (
            "warning",
            "high",
            "journal entries failed to merge",
            "ArchiveXL could not resolve or safely edit a journal entry path. The affected entry operation was skipped.",
        ),
        "AXL-RUNTIME-CUSTOMIZATION-TYPE-MISMATCH": (
            "warning",
            "high",
            "customization options failed to merge",
            "ArchiveXL matched a character-customization option but refused to merge it because the source and target native option types differ.",
        ),
        "AXL-RUNTIME-ERROR": (
            "error",
            "high",
            "other ArchiveXL runtime errors",
            "ArchiveXL emitted runtime errors that do not match a more specific scanner rule.",
        ),
        "AXL-RUNTIME-WARNING": (
            "warning",
            "high",
            "other ArchiveXL runtime warnings",
            "ArchiveXL emitted runtime warnings that do not match a more specific scanner rule.",
        ),
    }
    findings: list[Finding] = []
    for (rule_id, participants), evidence in sorted(
        grouped.items(), key=lambda item: (item[0][0], item[0][1])
    ):
        severity, confidence, noun, explanation = descriptions[rule_id]
        identities = {item["identity"] for item in evidence if item.get("identity")}
        count = len(identities) if identities else len(evidence)
        event_text = f" ({len(evidence)} log events)" if count != len(evidence) else ""
        findings.append(
            Finding(
                rule_id=rule_id,
                severity=severity,
                confidence=confidence,
                summary=f"{count} {noun}{event_text}",
                explanation=explanation,
                participants=list(participants),
                evidence=evidence,
            )
        )

    coverage = {
        "name": "latest ArchiveXL log session",
        "status": "analyzed",
        "session": session,
        "log_path": "; ".join(str(path) for path in log_paths),
        "log_paths": [str(path) for path in log_paths],
        "files": len(log_paths),
        "bytes": sum(path.stat().st_size for path in log_paths),
        "lines": line_count,
        "errors": sum(event.level == "error" for event in events),
        "warnings": sum(event.level == "warning" for event in events),
        "events": len(events),
        "correlated_events": correlated_events,
        "static_confirmations": static_confirmation_events,
        "findings": len(findings),
        "note": "All rotated chunks sharing the newest session timestamp are parsed chronologically and consolidated by rule and attributed mod set.",
    }
    return findings, coverage
