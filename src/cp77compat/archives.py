from __future__ import annotations

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

from .inventory import sha256_file
from .models import ArchiveManifest, ArchiveMember, Artifact, Finding


_LOG_LINE = re.compile(r"^\s*(?:\[|info:|warn:|error:|debug:)", re.IGNORECASE)
_HASH_ONLY = re.compile(r"^(?:0x)?[0-9a-f]{16}$", re.IGNORECASE)


def parse_archive_list_output(output: str) -> list[ArchiveMember]:
    members: list[ArchiveMember] = []
    seen: set[str] = set()
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or _LOG_LINE.match(line):
            continue
        normalized = line.replace("/", "\\").casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        members.append(ArchiveMember(path=line, resolved=not bool(_HASH_ONLY.match(line))))
    return sorted(members, key=lambda item: item.path.casefold())


class WolvenKitArchiveIndexer:
    def __init__(
        self,
        executable: Path,
        cache_root: Path,
        workers: int = 4,
        refresh_cache: bool = False,
        timeout_seconds: int = 120,
    ) -> None:
        self.executable = executable
        self.cache_root = cache_root
        self.workers = max(1, workers)
        self.refresh_cache = refresh_cache
        self.timeout_seconds = timeout_seconds
        self.version = self._get_version()

    def _get_version(self) -> str | None:
        try:
            result = subprocess.run(
                [str(self.executable), "--version"],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        value = result.stdout.strip()
        return value or None

    def _cache_path(self, digest: str) -> Path:
        return self.cache_root / digest / "manifest.json"

    def _load_cached(self, artifact: Artifact, digest: str) -> ArchiveManifest | None:
        path = self._cache_path(digest)
        if self.refresh_cache or not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return ArchiveManifest(
            mod_name=artifact.mod_name,
            archive_path=str(artifact.absolute_path),
            sha256=digest,
            size=artifact.size,
            wolvenkit_version=data.get("wolvenkit_version"),
            members=[ArchiveMember(**item) for item in data.get("members", [])],
            from_cache=True,
        )

    def _index_one(self, artifact: Artifact) -> ArchiveManifest:
        digest = artifact.sha256 or sha256_file(artifact.absolute_path)
        cached = self._load_cached(artifact, digest)
        if cached is not None:
            return cached
        result = subprocess.run(
            [
                str(self.executable),
                "archiveinfo",
                str(artifact.absolute_path),
                "--list",
                "--verbosity",
                "Minimal",
            ],
            check=True,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=self.timeout_seconds,
        )
        manifest = ArchiveManifest(
            mod_name=artifact.mod_name,
            archive_path=str(artifact.absolute_path),
            sha256=digest,
            size=artifact.size,
            wolvenkit_version=self.version,
            members=parse_archive_list_output(result.stdout),
        )
        cache_path = self._cache_path(digest)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return manifest

    def index(
        self, artifacts: Iterable[Artifact]
    ) -> tuple[list[ArchiveManifest], list[Finding]]:
        manifests: list[ArchiveManifest] = []
        findings: list[Finding] = []
        archive_artifacts = sorted(
            artifacts, key=lambda item: str(item.absolute_path).casefold()
        )
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(self._index_one, item): item for item in archive_artifacts}
            for future in as_completed(futures):
                artifact = futures[future]
                try:
                    manifests.append(future.result())
                except Exception as exc:  # external tool boundary
                    findings.append(
                        Finding(
                            rule_id="ARCHIVE-INDEX-FAILED",
                            severity="error",
                            confidence="high",
                            summary=f"Could not index {artifact.relative_path}",
                            explanation=str(exc),
                            participants=[artifact.mod_name],
                            evidence=[{"path": str(artifact.absolute_path)}],
                        )
                    )
        manifests.sort(key=lambda item: (item.mod_name.casefold(), item.archive_path.casefold()))
        return manifests, findings

