from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


SEVERITY_ORDER = {
    "error": 0,
    "conflict": 1,
    "warning": 2,
    "review": 3,
    "info": 4,
}


def normalize_game_path(value: str) -> str:
    """Return a stable, case-insensitive REDengine/game relative path."""
    return value.strip().replace("/", "\\").lstrip("\\").casefold()


@dataclass(slots=True)
class ModSource:
    name: str
    path: Path

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "path": str(self.path)}


@dataclass(slots=True)
class Artifact:
    mod_name: str
    absolute_path: Path
    relative_path: str
    extension: str
    size: int
    modified_ns: int
    sha256: str | None = None
    deployed_state: str = "unknown"
    deployed_source: str | None = None

    @property
    def normalized_path(self) -> str:
        return normalize_game_path(self.relative_path)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["absolute_path"] = str(self.absolute_path)
        return data


@dataclass(slots=True)
class Reference:
    ecosystem: str
    kind: str
    identity: str
    mod_name: str
    source_path: str
    line: int | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def normalized_identity(self) -> str:
        return normalize_game_path(self.identity)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Finding:
    rule_id: str
    severity: str
    confidence: str
    summary: str
    explanation: str
    participants: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    fingerprint: str = ""
    status: str = "active"
    acknowledgement: str | None = None
    change: str = "baseline"

    def sort_key(self) -> tuple[Any, ...]:
        return (
            SEVERITY_ORDER.get(self.severity, 99),
            self.rule_id,
            self.summary.casefold(),
            tuple(item.casefold() for item in self.participants),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ArchiveMember:
    path: str
    resolved: bool = True

    @property
    def normalized_path(self) -> str:
        return normalize_game_path(self.path)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ArchiveManifest:
    mod_name: str
    archive_path: str
    sha256: str
    size: int
    wolvenkit_version: str | None
    members: list[ArchiveMember]
    from_cache: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "mod_name": self.mod_name,
            "archive_path": self.archive_path,
            "sha256": self.sha256,
            "size": self.size,
            "wolvenkit_version": self.wolvenkit_version,
            "from_cache": self.from_cache,
            "members": [member.to_dict() for member in self.members],
        }
