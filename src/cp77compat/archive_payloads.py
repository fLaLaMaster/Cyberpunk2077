from __future__ import annotations

import json
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any, Callable, Protocol

from .inventory import sha256_file
from .models import ArchiveManifest, Finding, normalize_game_path


Runner = Callable[..., subprocess.CompletedProcess[str]]


def resource_path_hash(value: str) -> int:
    """Return Cyberpunk's unsigned 64-bit FNV-1a resource-path hash."""
    result = 14695981039346656037
    for byte in normalize_game_path(value).encode("utf-8"):
        result ^= byte
        result = (result * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return result


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def safe_member_path(root: Path, member_path: str) -> Path:
    """Map a REDengine path below root, rejecting absolute and traversal paths."""
    windows_path = PureWindowsPath(member_path.replace("/", "\\"))
    if windows_path.is_absolute() or windows_path.drive:
        raise ValueError(f"archive member path is absolute: {member_path}")
    parts = windows_path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"archive member path is unsafe: {member_path}")
    candidate = root.joinpath(*parts)
    if not _inside(root, candidate):
        raise ValueError(f"archive member escapes payload cache: {member_path}")
    return candidate


@dataclass(slots=True)
class PayloadResult:
    mod_name: str
    archive_path: str
    archive_sha256: str
    resource_path: str
    status: str
    path: Path | None = None
    from_cache: bool = False
    error: str | None = None
    metadata_path: Path | None = None

    @property
    def ok(self) -> bool:
        return self.status == "success" and self.path is not None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["path"] = str(self.path) if self.path else None
        data["metadata_path"] = (
            str(self.metadata_path) if self.metadata_path else None
        )
        return data


@dataclass(slots=True)
class SerializedPayloadResult:
    payload: PayloadResult
    status: str
    data: Any = None
    from_cache: bool = False
    error: str | None = None
    cache_path: Path | None = None

    @property
    def ok(self) -> bool:
        return self.status == "success" and self.data is not None


class ArchivePayloadProvider(Protocol):
    def materialize(
        self, manifest: ArchiveManifest, resource_path: str
    ) -> PayloadResult: ...

    def serialize_json(
        self, manifest: ArchiveManifest, resource_path: str
    ) -> SerializedPayloadResult: ...


class WolvenKitArchivePayloadProvider:
    """Exact, cache-backed extraction and CR2W serialization via WolvenKit."""

    def __init__(
        self,
        executable: Path,
        cache_root: Path,
        wolvenkit_version: str | None,
        refresh_cache: bool = False,
        timeout_seconds: int = 120,
        runner: Runner = subprocess.run,
    ) -> None:
        self.executable = executable
        self.cache_root = cache_root
        self.wolvenkit_version = wolvenkit_version
        self.refresh_cache = refresh_cache
        self.timeout_seconds = timeout_seconds
        self._runner = runner

    def _archive_root(self, manifest: ArchiveManifest) -> Path:
        digest = manifest.sha256.casefold()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError(f"invalid archive SHA-256: {manifest.sha256}")
        root = self.cache_root / digest
        if not _inside(self.cache_root, root):
            raise ValueError("archive hash resolved outside payload cache")
        return root

    def _canonical_member(
        self, manifest: ArchiveManifest, resource_path: str
    ) -> str | None:
        requested = normalize_game_path(resource_path)
        for member in manifest.members:
            if member.resolved and member.normalized_path == requested:
                return member.path.replace("/", "\\").lstrip("\\")
        return None

    def _metadata_path(self, root: Path, resource_path: str) -> Path:
        name = f"{resource_path_hash(resource_path):016x}.json"
        return root / "payload-metadata" / name

    @staticmethod
    def _read_json(path: Path) -> Any | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        temporary.replace(path)

    def _cached_payload(
        self,
        manifest: ArchiveManifest,
        resource_path: str,
        output_path: Path,
        metadata_path: Path,
    ) -> PayloadResult | None:
        if self.refresh_cache or not output_path.is_file():
            return None
        metadata = self._read_json(metadata_path)
        if not isinstance(metadata, dict):
            return None
        extraction = metadata.get("extraction")
        if not isinstance(extraction, dict):
            return None
        if (
            metadata.get("source_archive_sha256") != manifest.sha256
            or metadata.get("resource_path_normalized")
            != normalize_game_path(resource_path)
            or extraction.get("status") != "success"
            or extraction.get("wolvenkit_version") != self.wolvenkit_version
        ):
            return None
        try:
            size_matches = output_path.stat().st_size == extraction.get("size")
            hash_matches = sha256_file(output_path) == extraction.get("sha256")
        except OSError:
            return None
        if not size_matches or not hash_matches:
            return None
        if extraction.get("timeout_seconds") != self.timeout_seconds:
            extraction["timeout_seconds"] = self.timeout_seconds
            self._write_json(metadata_path, metadata)
        return PayloadResult(
            mod_name=manifest.mod_name,
            archive_path=manifest.archive_path,
            archive_sha256=manifest.sha256,
            resource_path=resource_path,
            status="success",
            path=output_path,
            from_cache=True,
            metadata_path=metadata_path,
        )

    def materialize(
        self, manifest: ArchiveManifest, resource_path: str
    ) -> PayloadResult:
        base = {
            "mod_name": manifest.mod_name,
            "archive_path": manifest.archive_path,
            "archive_sha256": manifest.sha256,
            "resource_path": resource_path,
        }
        try:
            root = self._archive_root(manifest)
            canonical = self._canonical_member(manifest, resource_path)
            if canonical is None:
                raise ValueError("resource is not a resolved member of this archive")
            extracted_root = root / "extracted"
            output_path = safe_member_path(extracted_root, canonical)
            metadata_path = self._metadata_path(root, canonical)
        except ValueError as exc:
            return PayloadResult(**base, status="error", error=str(exc))

        cached = self._cached_payload(
            manifest, canonical, output_path, metadata_path
        )
        if cached is not None:
            return cached

        source_archive = Path(manifest.archive_path)
        if not source_archive.is_file():
            return PayloadResult(
                **base,
                status="error",
                error="source archive no longer exists",
                metadata_path=metadata_path,
            )
        try:
            if source_archive.stat().st_size != manifest.size:
                raise ValueError("source archive size changed after indexing")
        except OSError as exc:
            return PayloadResult(
                **base, status="error", error=str(exc), metadata_path=metadata_path
            )

        extracted_root.mkdir(parents=True, exist_ok=True)
        command = [
            str(self.executable),
            "unbundle",
            str(source_archive),
            "--outpath",
            str(extracted_root),
            "--hash",
            str(resource_path_hash(canonical)),
            "--verbosity",
            "Minimal",
        ]
        started = time.monotonic()
        extraction: dict[str, Any] = {
            "status": "error",
            "command": command,
            "wolvenkit_version": self.wolvenkit_version,
            "timeout_seconds": self.timeout_seconds,
            "started_at": _utc_now(),
        }
        try:
            completed = self._runner(
                command,
                check=False,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=self.timeout_seconds,
            )
            extraction.update(
                {
                    "returncode": completed.returncode,
                    "stdout": completed.stdout[-4000:],
                    "stderr": completed.stderr[-4000:],
                }
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    completed.stderr.strip()
                    or completed.stdout.strip()
                    or f"WolvenKit exited with code {completed.returncode}"
                )
            if not output_path.is_file() or not _inside(extracted_root, output_path):
                raise RuntimeError("WolvenKit did not create the requested cache file")
            extraction.update(
                {
                    "status": "success",
                    "size": output_path.stat().st_size,
                    "sha256": sha256_file(output_path),
                }
            )
            error = None
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            error = str(exc)
            extraction["error"] = error
        extraction["duration_seconds"] = round(time.monotonic() - started, 6)
        extraction["finished_at"] = _utc_now()
        metadata = {
            "schema_version": 1,
            "source_archive": str(source_archive),
            "source_archive_sha256": manifest.sha256,
            "source_archive_size": manifest.size,
            "resource_path": canonical,
            "resource_path_normalized": normalize_game_path(canonical),
            "resource_hash": resource_path_hash(canonical),
            "extraction": extraction,
        }
        self._write_json(metadata_path, metadata)
        if error is not None:
            return PayloadResult(
                **base,
                status="error",
                error=error,
                metadata_path=metadata_path,
            )
        return PayloadResult(
            **base,
            status="success",
            path=output_path,
            metadata_path=metadata_path,
        )

    def serialize_json(
        self, manifest: ArchiveManifest, resource_path: str
    ) -> SerializedPayloadResult:
        payload = self.materialize(manifest, resource_path)
        if not payload.ok or payload.path is None or payload.metadata_path is None:
            return SerializedPayloadResult(
                payload=payload,
                status="error",
                error=payload.error or "payload extraction failed",
            )

        payload_sha256 = sha256_file(payload.path)
        root = self._archive_root(manifest)
        serialized_path = (
            root
            / "serialized"
            / f"{resource_path_hash(resource_path):016x}-{payload_sha256[:16]}.json"
        )
        metadata = self._read_json(payload.metadata_path)
        conversion = metadata.get("conversion") if isinstance(metadata, dict) else None
        if (
            not self.refresh_cache
            and isinstance(conversion, dict)
            and conversion.get("status") == "success"
            and conversion.get("payload_sha256") == payload_sha256
            and conversion.get("wolvenkit_version") == self.wolvenkit_version
            and serialized_path.is_file()
        ):
            cached_data = self._read_json(serialized_path)
            if cached_data is not None:
                if conversion.get("timeout_seconds") != self.timeout_seconds:
                    conversion["timeout_seconds"] = self.timeout_seconds
                    if not isinstance(metadata, dict):
                        metadata = {}
                    metadata["conversion"] = conversion
                    self._write_json(payload.metadata_path, metadata)
                return SerializedPayloadResult(
                    payload=payload,
                    status="success",
                    data=cached_data,
                    from_cache=True,
                    cache_path=serialized_path,
                )

        command = [
            str(self.executable),
            "convert",
            "serialize",
            str(payload.path),
            "--print",
            "--verbosity",
            "Quiet",
        ]
        started = time.monotonic()
        conversion = {
            "status": "error",
            "command": command,
            "wolvenkit_version": self.wolvenkit_version,
            "timeout_seconds": self.timeout_seconds,
            "payload_sha256": payload_sha256,
            "started_at": _utc_now(),
        }
        try:
            completed = self._runner(
                command,
                check=False,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=self.timeout_seconds,
            )
            conversion.update(
                {
                    "returncode": completed.returncode,
                    "stderr": completed.stderr[-4000:],
                }
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    completed.stderr.strip()
                    or completed.stdout.strip()
                    or f"WolvenKit exited with code {completed.returncode}"
                )
            data = json.loads(completed.stdout.lstrip("\ufeff").strip())
            self._write_json(serialized_path, data)
            conversion.update(
                {
                    "status": "success",
                    "serialized_cache": str(serialized_path),
                }
            )
            error = None
        except (OSError, subprocess.SubprocessError, RuntimeError, json.JSONDecodeError) as exc:
            data = None
            error = str(exc)
            conversion["error"] = error
        conversion["duration_seconds"] = round(time.monotonic() - started, 6)
        conversion["finished_at"] = _utc_now()
        if not isinstance(metadata, dict):
            metadata = {}
        metadata["conversion"] = conversion
        self._write_json(payload.metadata_path, metadata)
        if error is not None:
            return SerializedPayloadResult(
                payload=payload,
                status="error",
                error=error,
                cache_path=serialized_path,
            )
        return SerializedPayloadResult(
            payload=payload,
            status="success",
            data=data,
            cache_path=serialized_path,
        )


def payload_failure_finding(
    result: PayloadResult | SerializedPayloadResult,
) -> Finding:
    payload = result.payload if isinstance(result, SerializedPayloadResult) else result
    error = result.error or payload.error or "unknown payload inspection failure"
    operation = "serialize" if isinstance(result, SerializedPayloadResult) else "extract"
    return Finding(
        rule_id="AXL-PAYLOAD-FAILED",
        severity="error",
        confidence="high",
        summary=f"Could not {operation} ArchiveXL payload: {payload.resource_path}",
        explanation=error,
        participants=[payload.mod_name],
        evidence=[payload.to_dict()],
    )
