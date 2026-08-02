from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from .deployment import Deployment
from .models import Artifact, Finding, ModSource


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def discover_mods(staging_root: Path) -> list[ModSource]:
    return [
        ModSource(name=path.name, path=path)
        for path in sorted(staging_root.iterdir(), key=lambda item: item.name.casefold())
        if path.is_dir()
    ]


def build_inventory(
    mods: Iterable[ModSource],
    deployment: Deployment | None,
    hash_mode: str = "archives",
) -> list[Artifact]:
    artifacts: list[Artifact] = []
    winners = deployment.winners if deployment else {}
    for mod in mods:
        files = sorted(
            (path for path in mod.path.rglob("*") if path.is_file()),
            key=lambda item: str(item).casefold(),
        )
        for path in files:
            stat = path.stat()
            relative = str(path.relative_to(mod.path))
            extension = path.suffix.casefold()
            normalized = relative.replace("/", "\\").casefold()
            winner = winners.get(normalized)
            if winner == mod.name:
                state = "deployed"
            elif winner is not None:
                state = "overridden"
            else:
                state = "not_deployed"
            should_hash = hash_mode == "all" or (
                hash_mode == "archives" and extension == ".archive"
            )
            artifacts.append(
                Artifact(
                    mod_name=mod.name,
                    absolute_path=path,
                    relative_path=relative,
                    extension=extension,
                    size=stat.st_size,
                    modified_ns=stat.st_mtime_ns,
                    sha256=sha256_file(path) if should_hash else None,
                    deployed_state=state,
                    deployed_source=winner,
                )
            )
    return artifacts


def exact_path_findings(artifacts: Iterable[Artifact]) -> list[Finding]:
    grouped: dict[str, list[Artifact]] = defaultdict(list)
    for artifact in artifacts:
        grouped[artifact.normalized_path].append(artifact)

    findings: list[Finding] = []
    for normalized, group in grouped.items():
        mods = sorted({item.mod_name for item in group}, key=str.casefold)
        if len(mods) < 2:
            continue
        winners = sorted(
            {item.deployed_source for item in group if item.deployed_source},
            key=str.casefold,
        )
        winner_text = winners[0] if len(winners) == 1 else None
        findings.append(
            Finding(
                rule_id="CORE-EXACT-PATH",
                severity="info" if winner_text else "review",
                confidence="high",
                summary=f"Multiple mods provide {group[0].relative_path}",
                explanation=(
                    f"Vortex deploys the copy from {winner_text}."
                    if winner_text
                    else "No single deployed winner was found in the Vortex manifest."
                ),
                participants=mods,
                evidence=[
                    {
                        "mod": item.mod_name,
                        "path": str(item.absolute_path),
                        "state": item.deployed_state,
                    }
                    for item in sorted(group, key=lambda value: value.mod_name.casefold())
                ],
            )
        )
    return findings

