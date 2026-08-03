from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .cet import cet_artifact_location
from .models import Artifact, Finding, Reference


_LOG_PREFIX = re.compile(r"^\[(?P<timestamp>[^]]+)]\s+\[(?P<thread>[^]]+)]\s*(?P<message>.*)$")
_LOADED = re.compile(r"^Mod (?P<root>.+?) loaded! \('(?P<path>.+)'\)$")
_FAILED = re.compile(r"^Mod (?P<root>.+?) failed to load! \('(?P<path>.+)'\)$")
_IGNORED = re.compile(r"^Ignoring mod which does not contain init\.lua! \('(?P<path>.+)'\)$")
_HOOK_MISSING = re.compile(r"^Function (?P<method>.+) in class (?P<class>.+) does not exist$")
_CLASS_MISSING = re.compile(r"^Class type (?P<class>.+) not found$")
_LUA_ERROR = re.compile(
    r"^(?P<path>(?:init\.lua|(?:[A-Za-z]:\\|\.\.\.|[^:]+\\)[^:]*?\.lua)):(?P<line>\d+):\s*(?P<message>.+)$",
    re.IGNORECASE,
)


@dataclass(slots=True)
class CETRuntimeEvent:
    rule_id: str
    severity: str
    message: str
    log_path: Path
    log_line: int
    timestamp: str | None = None
    mod_root: str | None = None
    identity: str | None = None
    source_path: str | None = None
    source_line: int | None = None
    sources: list[dict[str, Any]] | None = None
    static_rules: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "log_path": str(self.log_path),
            "log_line": self.log_line,
            "timestamp": self.timestamp,
            "mod_root": self.mod_root,
            "identity": self.identity,
            "source_path": self.source_path,
            "line": self.source_line,
            "message": self.message,
            "sources": self.sources or [],
            "static_rules": self.static_rules or [],
        }


def _message(line: str) -> tuple[str | None, str]:
    match = _LOG_PREFIX.match(line)
    if match:
        return match.group("timestamp"), match.group("message")
    return None, line.strip()


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8-sig", errors="replace").splitlines()


def _parse_scripting_log(path: Path) -> tuple[list[CETRuntimeEvent], dict[str, Any]]:
    lines = _read_lines(path)
    events: list[CETRuntimeEvent] = []
    loaded: list[str] = []
    ignored: list[str] = []
    failed: list[str] = []
    for number, line in enumerate(lines, 1):
        timestamp, message = _message(line)
        if match := _LOADED.match(message):
            loaded.append(match.group("root"))
            continue
        if match := _FAILED.match(message):
            root = match.group("root")
            failed.append(root)
            events.append(CETRuntimeEvent(
                "CET-RUNTIME-MOD-LOAD-FAILURE", "error", message, path, number,
                timestamp=timestamp, mod_root=root,
            ))
            continue
        if match := _IGNORED.match(message):
            ignored_path = Path(match.group("path"))
            root = ignored_path.name
            ignored.append(root)
            events.append(CETRuntimeEvent(
                "CET-RUNTIME-MOD-IGNORED", "info", message, path, number,
                timestamp=timestamp, mod_root=root,
            ))
            continue
        if match := _HOOK_MISSING.match(message):
            identity = f"{match.group('class')}.{match.group('method')}"
            events.append(CETRuntimeEvent(
                "CET-RUNTIME-HOOK-TARGET-MISSING", "warning", message, path, number,
                timestamp=timestamp, identity=identity,
            ))
            continue
        if match := _CLASS_MISSING.match(message):
            events.append(CETRuntimeEvent(
                "CET-RUNTIME-HOOK-CLASS-MISSING", "warning", message, path, number,
                timestamp=timestamp, identity=match.group("class"),
            ))
    return events, {
        "lines": len(lines),
        "loaded_mods": sorted(set(loaded), key=str.casefold),
        "ignored_mods": sorted(set(ignored), key=str.casefold),
        "failed_mods": sorted(set(failed), key=str.casefold),
    }


def _parse_mod_log(path: Path, root: str) -> tuple[list[CETRuntimeEvent], int]:
    lines = _read_lines(path)
    events: list[CETRuntimeEvent] = []
    seen: set[tuple[str, int, str]] = set()
    for number, line in enumerate(lines, 1):
        if line[:1].isspace() or line.strip().casefold() == "stack traceback:":
            continue
        timestamp, message = _message(line)
        match = _LUA_ERROR.match(message)
        if match:
            source_path = match.group("path")
            source_line = int(match.group("line"))
            error_message = match.group("message")
            key = (source_path.casefold(), source_line, error_message)
            if key in seen:
                continue
            seen.add(key)
            events.append(CETRuntimeEvent(
                "CET-RUNTIME-LUA-ERROR", "error", error_message, path, number,
                timestamp=timestamp, mod_root=root, source_path=source_path,
                source_line=source_line,
            ))
            continue
        lowered = message.casefold()
        if "tried to register" in lowered and any(
            marker in lowered for marker in ("unknown event", "same id", "incorrect id", "empty display")
        ):
            events.append(CETRuntimeEvent(
                "CET-RUNTIME-REGISTRATION-ERROR", "error", message, path, number,
                timestamp=timestamp, mod_root=root,
            ))
        elif message.startswith("Error: Cannot load module"):
            events.append(CETRuntimeEvent(
                "CET-RUNTIME-MODULE-ERROR", "error", message, path, number,
                timestamp=timestamp, mod_root=root,
            ))
    return events, len(lines)


def _parse_main_log(path: Path) -> dict[str, Any]:
    lines = _read_lines(path)
    version = None
    game_version = None
    errors = 0
    warnings = 0
    for line in lines:
        if "CET version " in line:
            version = line.split("CET version ", 1)[1].strip()
        elif "Game version " in line:
            game_version = line.split("Game version ", 1)[1].strip()
        lowered = line.casefold()
        errors += "[error]" in lowered
        warnings += "[warning]" in lowered or "[warn]" in lowered
    return {
        "lines": len(lines),
        "cet_version": version,
        "game_version": game_version,
        "framework_errors": errors,
        "framework_warnings": warnings,
    }


def _source_candidates(
    event: CETRuntimeEvent,
    artifacts_by_root: dict[str, list[tuple[Artifact, str]]],
) -> list[dict[str, Any]]:
    if not event.mod_root or not event.source_path:
        return []
    candidates = artifacts_by_root.get(event.mod_root.casefold(), [])
    normalized = event.source_path.replace("/", "\\").casefold()
    if "\\mods\\" in normalized:
        normalized = normalized.split("\\mods\\", 1)[1]
        _, _, normalized = normalized.partition("\\")
    elif normalized.startswith("init.lua"):
        normalized = "init.lua"
    else:
        normalized = normalized.removeprefix("...\\")
    matched = [
        (artifact, relative) for artifact, relative in candidates
        if relative.replace("/", "\\").casefold().endswith(normalized)
        or normalized.endswith(relative.replace("/", "\\").casefold())
    ]
    if not matched and normalized.endswith("init.lua"):
        matched = [item for item in candidates if item[1].casefold() == "init.lua"]
    return [
        {
            "mod_name": artifact.mod_name,
            "source_path": str(artifact.absolute_path),
            "line": event.source_line,
            "match": "CET mod root, Lua path suffix, and runtime line",
        }
        for artifact, _ in matched
    ]


def analyze_cet_runtime_logs(
    game_root: Path,
    artifacts: Iterable[Artifact],
    references: Iterable[Reference],
    static_findings: Iterable[Finding],
) -> tuple[list[Finding], dict[str, Any]]:
    cet_root = game_root / "bin" / "x64" / "plugins" / "cyber_engine_tweaks"
    main_log = cet_root / "cyber_engine_tweaks.log"
    scripting_log = cet_root / "scripting.log"
    empty = {
        "name": "CET current logs",
        "status": "unsupported",
        "log_path": str(scripting_log),
        "files": 0,
        "lines": 0,
        "errors": 0,
        "warnings": 0,
        "events": 0,
        "correlated_events": 0,
        "static_confirmations": 0,
        "findings": 0,
        "loaded_mods": 0,
        "ignored_mods": 0,
        "failed_mods": 0,
        "cet_version": None,
        "game_version": None,
        "note": "CET scripting.log was not found.",
    }
    if not scripting_log.is_file():
        return [], empty

    try:
        events, scripting_stats = _parse_scripting_log(scripting_log)
        main_stats = _parse_main_log(main_log) if main_log.is_file() else {
            "lines": 0, "cet_version": None, "game_version": None,
            "framework_errors": 0, "framework_warnings": 0,
        }
    except OSError as exc:
        empty["status"] = "partial"
        empty["note"] = f"CET logs could not be read: {exc}"
        return [], empty

    artifact_list = list(artifacts)
    artifacts_by_root: dict[str, list[tuple[Artifact, str]]] = defaultdict(list)
    active_roots: dict[str, str] = {}
    for artifact in artifact_list:
        location = cet_artifact_location(artifact)
        if location is None or artifact.extension.casefold() != ".lua" or artifact.deployed_state == "overridden":
            continue
        root, relative = location
        artifacts_by_root[root.casefold()].append((artifact, relative))
        if relative.casefold() == "init.lua":
            active_roots[root.casefold()] = root

    mod_log_lines = 0
    mod_log_files = 0
    for root in active_roots.values():
        mod_log = cet_root / "mods" / root / f"{root}.log"
        if not mod_log.is_file():
            continue
        try:
            mod_events, line_count = _parse_mod_log(mod_log, root)
        except OSError:
            continue
        events.extend(mod_events)
        mod_log_lines += line_count
        mod_log_files += 1

    reference_list = list(references)
    references_by_identity: dict[str, list[Reference]] = defaultdict(list)
    references_by_source_line: dict[tuple[str, int], list[Reference]] = defaultdict(list)
    for reference in reference_list:
        if reference.details.get("deployed_state") == "overridden":
            continue
        references_by_identity[reference.identity].append(reference)
        references_by_source_line[
            (str(Path(reference.source_path).resolve(strict=False)).casefold(), reference.line or 0)
        ].append(reference)

    static_by_rule_identity: dict[str, list[Finding]] = defaultdict(list)
    for finding in static_findings:
        if not finding.rule_id.startswith("CET-"):
            continue
        for evidence in finding.evidence:
            identity = evidence.get("identity")
            if isinstance(identity, str):
                static_by_rule_identity[identity].append(finding)

    correlated = 0
    static_confirmations = 0
    for event in events:
        if event.source_path:
            event.sources = _source_candidates(event, artifacts_by_root)
            source_refs: list[Reference] = []
            for source in event.sources:
                source_refs.extend(references_by_source_line.get(
                    (str(Path(source["source_path"]).resolve(strict=False)).casefold(), event.source_line or 0),
                    []
                ))
            if source_refs:
                event.identity = source_refs[0].identity
                event.sources = [reference.to_dict() for reference in source_refs]
        elif event.identity:
            identity_refs = references_by_identity.get(event.identity, [])
            if identity_refs:
                event.sources = [reference.to_dict() for reference in identity_refs]
        if event.sources:
            correlated += 1
        static = static_by_rule_identity.get(event.identity or "", [])
        if static:
            event.static_rules = sorted({finding.rule_id for finding in static})
            static_confirmations += 1

    grouped: dict[tuple[str, tuple[str, ...]], list[CETRuntimeEvent]] = defaultdict(list)
    for event in events:
        participants = {
            str(source.get("mod_name"))
            for source in event.sources or [] if source.get("mod_name")
        }
        if event.mod_root and not participants:
            for artifact, _ in artifacts_by_root.get(event.mod_root.casefold(), []):
                participants.add(artifact.mod_name)
        grouped[(event.rule_id, tuple(sorted(participants, key=str.casefold)))].append(event)

    descriptions = {
        "CET-RUNTIME-MOD-LOAD-FAILURE": (
            "error", "CET mod load failure",
            "CET found the mod entry but init.lua failed while the sandbox was being created, so this CET mod is inactive for the session.",
        ),
        "CET-RUNTIME-MOD-IGNORED": (
            "info", "ignored CET mod-root folder",
            "CET scans every directory directly below its mods folder and ignores directories without init.lua. Some framework data directories intentionally produce this message.",
        ),
        "CET-RUNTIME-HOOK-TARGET-MISSING": (
            "warning", "hook target missing from the current game RTTI",
            "CET could not find the requested method on the requested class. The observer or override was not registered, usually because the Lua helper targets an older game method.",
        ),
        "CET-RUNTIME-HOOK-CLASS-MISSING": (
            "warning", "hook class missing from the current game RTTI",
            "CET could not find the requested class, so the observer or override was not registered.",
        ),
        "CET-RUNTIME-LUA-ERROR": (
            "error", "Lua callback error",
            "A loaded CET mod raised a Lua error during the captured session. The first source line and stack traceback origin are attached where CET recorded them.",
        ),
        "CET-RUNTIME-REGISTRATION-ERROR": (
            "error", "CET registration rejected at runtime",
            "CET rejected an event or binding registration according to its current ID, label, duplicate, or event-name validation rules.",
        ),
        "CET-RUNTIME-MODULE-ERROR": (
            "error", "Lua module load error",
            "CET resolved the requested Lua module but failed to compile or execute it.",
        ),
    }
    findings: list[Finding] = []
    for (rule_id, participants), group in sorted(
        grouped.items(), key=lambda item: (item[0][0], tuple(value.casefold() for value in item[0][1]))
    ):
        severity, label, explanation = descriptions[rule_id]
        findings.append(Finding(
            rule_id=rule_id,
            severity=severity,
            confidence="high",
            summary=f"{len(group)} {label}" + ("s" if len(group) != 1 else ""),
            explanation=explanation,
            participants=list(participants),
            evidence=[event.to_dict() for event in group],
        ))

    error_events = sum(event.severity == "error" for event in events)
    warning_events = sum(event.severity == "warning" for event in events)
    coverage = {
        "name": "CET current logs",
        "status": "analyzed",
        "log_path": str(scripting_log),
        "files": 1 + int(main_log.is_file()) + mod_log_files,
        "lines": scripting_stats["lines"] + main_stats["lines"] + mod_log_lines,
        "errors": error_events + main_stats["framework_errors"],
        "warnings": warning_events + main_stats["framework_warnings"],
        "events": len(events),
        "correlated_events": correlated,
        "static_confirmations": static_confirmations,
        "findings": len(findings),
        "loaded_mods": len(scripting_stats["loaded_mods"]),
        "ignored_mods": len(scripting_stats["ignored_mods"]),
        "failed_mods": len(scripting_stats["failed_mods"]),
        "cet_version": main_stats["cet_version"],
        "game_version": main_stats["game_version"],
        "note": "The current CET framework/scripting logs and canonical per-mod logs are parsed; load state, missing hook targets, registration failures, module failures, and Lua stack origins are correlated.",
    }
    return findings, coverage
