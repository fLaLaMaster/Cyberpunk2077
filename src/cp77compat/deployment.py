from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import normalize_game_path


@dataclass(slots=True)
class Deployment:
    manifest_path: Path
    game_id: str | None
    method: str | None
    staging_path: str | None
    target_path: str | None
    winners: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_path": str(self.manifest_path),
            "game_id": self.game_id,
            "method": self.method,
            "staging_path": self.staging_path,
            "target_path": self.target_path,
            "winner_count": len(self.winners),
        }


def load_deployment(game_root: Path) -> Deployment | None:
    path = game_root / "vortex.deployment.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    winners: dict[str, str] = {}
    for entry in data.get("files", []):
        relative = entry.get("relPath")
        source = entry.get("source")
        if isinstance(relative, str) and isinstance(source, str):
            winners[normalize_game_path(relative)] = source
    return Deployment(
        manifest_path=path,
        game_id=data.get("gameId"),
        method=data.get("deploymentMethod"),
        staging_path=data.get("stagingPath"),
        target_path=data.get("targetPath"),
        winners=winners,
    )

