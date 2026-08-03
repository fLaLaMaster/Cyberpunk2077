from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .models import Finding


FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_COUNT_PATTERN = re.compile(r"(?<![\w])\d[\d,]*(?![\w])")


@dataclass(frozen=True, slots=True)
class Acknowledgement:
    fingerprint: str
    note: str

    def to_dict(self) -> dict[str, str]:
        return {"fingerprint": self.fingerprint, "note": self.note}


def _mapping(finding: Finding | Mapping[str, Any]) -> dict[str, Any]:
    return finding.to_dict() if isinstance(finding, Finding) else dict(finding)


def _normalized_summary(value: str) -> str:
    collapsed = " ".join(value.casefold().split())
    return _COUNT_PATTERN.sub("#", collapsed)


def _identity_anchors(value: Any) -> set[str]:
    anchors: set[str] = set()

    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                if key in {"identity", "sector"} and child is not None and child != "":
                    anchors.add(str(child).strip().replace("/", "\\").casefold())
                else:
                    visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return anchors


def finding_fingerprint(finding: Finding | Mapping[str, Any]) -> str:
    """Return a stable key for one semantic finding group."""
    data = _mapping(finding)
    payload = {
        "rule_id": str(data.get("rule_id", "")).casefold(),
        "participants": sorted(
            {str(item).casefold() for item in data.get("participants", [])}
        ),
        "summary": _normalized_summary(str(data.get("summary", ""))),
        "identities": sorted(_identity_anchors(data.get("evidence", []))),
    }
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def finding_signature(finding: Finding | Mapping[str, Any]) -> str:
    """Hash compatibility-relevant content while ignoring report state fields."""
    data = _mapping(finding)
    payload = {
        key: data.get(key)
        for key in (
            "rule_id",
            "severity",
            "confidence",
            "summary",
            "explanation",
            "participants",
            "evidence",
        )
    }
    encoded = json.dumps(
        _canonical_content(payload),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_content(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_content(child)
            for key, child in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, list):
        children = [_canonical_content(child) for child in value]
        return sorted(
            children,
            key=lambda child: json.dumps(
                child, ensure_ascii=True, sort_keys=True, separators=(",", ":")
            ),
        )
    return value


def classify_findings(
    findings: Iterable[Finding],
    acknowledgements: Iterable[Acknowledgement],
    previous_findings: Iterable[Mapping[str, Any]] | None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]]]:
    current = list(findings)
    acknowledgement_by_fingerprint = {
        item.fingerprint: item for item in acknowledgements
    }
    current_by_fingerprint: dict[str, Finding] = {}
    for finding in current:
        fingerprint = finding_fingerprint(finding)
        if fingerprint in current_by_fingerprint:
            raise ValueError(
                "finding fingerprint collision between current findings: "
                f"{fingerprint}"
            )
        finding.fingerprint = fingerprint
        acknowledgement = acknowledgement_by_fingerprint.get(fingerprint)
        finding.status = "acknowledged" if acknowledgement else "active"
        finding.acknowledgement = acknowledgement.note if acknowledgement else None
        current_by_fingerprint[fingerprint] = finding

    previous = list(previous_findings) if previous_findings is not None else None
    previous_by_fingerprint: dict[str, Mapping[str, Any]] = {}
    if previous is not None:
        for item in previous:
            previous_by_fingerprint[finding_fingerprint(item)] = item

    changed: list[dict[str, Any]] = []
    new: list[dict[str, Any]] = []
    unchanged = 0
    for fingerprint, finding in current_by_fingerprint.items():
        prior = previous_by_fingerprint.get(fingerprint)
        if previous is None:
            finding.change = "baseline"
        elif prior is None:
            finding.change = "new"
            new.append(finding.to_dict())
        elif finding_signature(prior) != finding_signature(finding):
            finding.change = "changed"
            changed.append(
                {
                    "fingerprint": fingerprint,
                    "previous": dict(prior),
                    "current": finding.to_dict(),
                }
            )
        else:
            finding.change = "unchanged"
            unchanged += 1

    resolved = [] if previous is None else [
        dict(item)
        for fingerprint, item in previous_by_fingerprint.items()
        if fingerprint not in current_by_fingerprint
    ]
    stale = [
        acknowledgement.to_dict()
        for fingerprint, acknowledgement in acknowledgement_by_fingerprint.items()
        if fingerprint not in current_by_fingerprint
    ]
    state = {
        "active": sum(item.status == "active" for item in current),
        "acknowledged": sum(item.status == "acknowledged" for item in current),
        "stale_acknowledgements": len(stale),
        "configured_acknowledgements": len(acknowledgement_by_fingerprint),
    }
    diff = {
        "baseline_available": previous is not None,
        "new": new,
        "changed": changed,
        "resolved": resolved,
        "unchanged": unchanged,
        "summary": {
            "new": len(new),
            "changed": len(changed),
            "resolved": len(resolved),
            "unchanged": unchanged,
        },
    }
    return state, diff, stale
