from __future__ import annotations

import ctypes
import hashlib
import os
import re
import struct
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .models import Artifact, Finding, Reference


NATIVE_EXTENSIONS = {".dll", ".asi"}
SYSTEM_DLLS = {
    "advapi32.dll", "bcrypt.dll", "bcryptprimitives.dll", "combase.dll",
    "crypt32.dll", "d3d11.dll", "d3d12.dll", "d3dcompiler_47.dll", "dbghelp.dll",
    "dinput8.dll", "dxgi.dll", "gdi32.dll", "imm32.dll", "kernel32.dll", "ntdll.dll",
    "ole32.dll", "oleaut32.dll", "rpcrt4.dll", "secur32.dll", "setupapi.dll",
    "shell32.dll", "shlwapi.dll", "user32.dll", "version.dll", "winhttp.dll",
    "winmm.dll", "wintrust.dll", "ws2_32.dll",
}
DELEGATED_LOGS = {
    "archivexl": "ArchiveXL analyzer",
    "tweakxl": "TweakXL analyzer",
    "input_loader": "Input mapping analyzer",
}


@dataclass(slots=True)
class NativeBinary:
    artifact: Artifact
    category: str
    plugin_root: str | None
    sha256: str
    imports: list[str]
    pe_error: str | None
    file_version: str | None
    deployed_path: Path
    deployed_exists: bool
    deployed_sha256: str | None
    deployed_matches: bool | None
    runtime_name: str | None = None
    runtime_version: str | None = None
    runtime_authors: str | None = None
    runtime_state: str = "not-applicable"


@dataclass(slots=True)
class RuntimePlugin:
    path: str
    name: str | None = None
    version: str | None = None
    authors: str | None = None
    state: str = "attempted"
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _category(relative_path: str) -> tuple[str, str | None]:
    normalized = relative_path.replace("/", "\\")
    lowered = normalized.casefold()
    prefix = "red4ext\\plugins\\"
    if lowered.startswith(prefix):
        rest = normalized[len(prefix):]
        root, separator, _ = rest.partition("\\")
        return "red4ext-plugin-binary", root if separator else None
    if lowered == "red4ext\\red4ext.dll":
        return "red4ext-core", None
    if lowered == "bin\\x64\\winmm.dll":
        return "red4ext-loader", None
    if lowered.startswith("bin\\x64\\plugins\\cyber_engine_tweaks") or lowered == "bin\\x64\\version.dll":
        return "cet-framework", None
    if lowered == "engine\\tools\\scc_lib.dll":
        return "redscript-compiler", None
    return "native-library", None


def _read_c_string(data: bytes, offset: int | None) -> str:
    if offset is None or offset < 0 or offset >= len(data):
        return ""
    end = data.find(b"\0", offset)
    if end < 0:
        end = len(data)
    return data[offset:end].decode("ascii", errors="replace")


def parse_pe_imports(path: Path) -> list[str]:
    """Return normal and delay-load DLL imports from a PE image."""
    data = path.read_bytes()
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise ValueError("missing DOS/PE header")
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_offset + 24 > len(data) or data[pe_offset:pe_offset + 4] != b"PE\0\0":
        raise ValueError("missing PE signature")
    coff = pe_offset + 4
    section_count = struct.unpack_from("<H", data, coff + 2)[0]
    optional_size = struct.unpack_from("<H", data, coff + 16)[0]
    optional = coff + 20
    if optional + optional_size > len(data):
        raise ValueError("truncated optional header")
    magic = struct.unpack_from("<H", data, optional)[0]
    if magic == 0x20B:
        directories = optional + 112
        image_base = struct.unpack_from("<Q", data, optional + 24)[0]
    elif magic == 0x10B:
        directories = optional + 96
        image_base = struct.unpack_from("<I", data, optional + 28)[0]
    else:
        raise ValueError(f"unsupported PE optional-header magic 0x{magic:04X}")
    section_table = optional + optional_size
    sections: list[tuple[int, int, int]] = []
    for index in range(section_count):
        offset = section_table + index * 40
        if offset + 40 > len(data):
            raise ValueError("truncated PE section table")
        virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from(
            "<IIII", data, offset + 8
        )
        sections.append((virtual_address, max(virtual_size, raw_size), raw_pointer))

    def rva_offset(rva: int) -> int | None:
        if rva == 0:
            return None
        for virtual_address, size, raw_pointer in sections:
            if virtual_address <= rva < virtual_address + size:
                result = raw_pointer + rva - virtual_address
                return result if result < len(data) else None
        return rva if rva < len(data) else None

    imports: set[str] = set()
    if directories + 16 <= optional + optional_size:
        import_rva = struct.unpack_from("<I", data, directories + 8)[0]
        descriptor = rva_offset(import_rva)
        while descriptor is not None and descriptor + 20 <= len(data):
            values = struct.unpack_from("<IIIII", data, descriptor)
            if not any(values):
                break
            name = _read_c_string(data, rva_offset(values[3]))
            if name:
                imports.add(name)
            descriptor += 20
    if directories + 14 * 8 <= optional + optional_size:
        delay_rva = struct.unpack_from("<I", data, directories + 13 * 8)[0]
        descriptor = rva_offset(delay_rva)
        while descriptor is not None and descriptor + 32 <= len(data):
            values = struct.unpack_from("<IIIIIIII", data, descriptor)
            if not any(values):
                break
            name_rva = values[1]
            if not values[0] & 1 and name_rva >= image_base:
                name_rva -= image_base
            name = _read_c_string(data, rva_offset(name_rva))
            if name:
                imports.add(name)
            descriptor += 32
    return sorted(imports, key=str.casefold)


def _windows_file_version(path: Path) -> str | None:
    if os.name != "nt":
        return None
    try:
        version = ctypes.WinDLL("version", use_last_error=True)
        version.GetFileVersionInfoSizeW.argtypes = [
            ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)
        ]
        version.GetFileVersionInfoSizeW.restype = ctypes.c_uint32
        version.GetFileVersionInfoW.argtypes = [
            ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p
        ]
        version.GetFileVersionInfoW.restype = ctypes.c_int
        version.VerQueryValueW.argtypes = [
            ctypes.c_void_p, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_uint),
        ]
        version.VerQueryValueW.restype = ctypes.c_int
        size = version.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return None
        buffer = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(str(path), 0, size, buffer):
            return None
        value = ctypes.c_void_p()
        value_size = ctypes.c_uint()
        if not version.VerQueryValueW(buffer, "\\", ctypes.byref(value), ctypes.byref(value_size)):
            return None
        fixed = ctypes.cast(value, ctypes.POINTER(ctypes.c_uint32 * 13)).contents
        if fixed[0] != 0xFEEF04BD:
            return None
        major, minor = fixed[2] >> 16, fixed[2] & 0xFFFF
        patch, build = fixed[3] >> 16, fixed[3] & 0xFFFF
        return f"{major}.{minor}.{patch}.{build}"
    except (AttributeError, OSError, ValueError):
        return None


def _binary_reference(binary: NativeBinary) -> Reference:
    artifact = binary.artifact
    return Reference(
        ecosystem="native",
        kind="native.binary",
        identity=artifact.relative_path.replace("/", "\\"),
        mod_name=artifact.mod_name,
        source_path=str(artifact.absolute_path),
        line=1,
        details={
            "category": binary.category,
            "plugin_root": binary.plugin_root,
            "sha256": binary.sha256,
            "file_version": binary.file_version,
            "imports": binary.imports,
            "pe_error": binary.pe_error,
            "relative_path": artifact.relative_path,
            "deployed_state": artifact.deployed_state,
            "deployed_source": artifact.deployed_source,
            "deployed_path": str(binary.deployed_path),
            "deployed_exists": binary.deployed_exists,
            "deployed_sha256": binary.deployed_sha256,
            "deployed_matches": binary.deployed_matches,
            "runtime_name": binary.runtime_name,
            "runtime_version": binary.runtime_version,
            "runtime_authors": binary.runtime_authors,
            "runtime_state": binary.runtime_state,
        },
    )


def _import_reference(binary: NativeBinary, dependency: str) -> Reference:
    artifact = binary.artifact
    return Reference(
        ecosystem="native",
        kind="native.import",
        identity=f"{artifact.relative_path.replace('/', '!')}!{dependency}",
        mod_name=artifact.mod_name,
        source_path=str(artifact.absolute_path),
        line=1,
        details={
            "binary": artifact.relative_path,
            "dependency": dependency,
            "system": _is_system_dependency(dependency),
            "deployed_state": artifact.deployed_state,
        },
    )


def parse_native_binaries(
    artifacts: Iterable[Artifact], game_root: Path
) -> tuple[list[NativeBinary], list[Reference]]:
    binaries: list[NativeBinary] = []
    references: list[Reference] = []
    for artifact in artifacts:
        if artifact.extension.casefold() not in NATIVE_EXTENSIONS:
            continue
        category, plugin_root = _category(artifact.relative_path)
        digest = _sha256(artifact.absolute_path)
        try:
            imports = parse_pe_imports(artifact.absolute_path)
            pe_error = None
        except (OSError, ValueError, struct.error) as exc:
            imports = []
            pe_error = str(exc)
        deployed_path = game_root / Path(artifact.relative_path.replace("\\", "/"))
        deployed_exists = deployed_path.is_file()
        deployed_sha = _sha256(deployed_path) if deployed_exists else None
        binary = NativeBinary(
            artifact=artifact,
            category=category,
            plugin_root=plugin_root,
            sha256=digest,
            imports=imports,
            pe_error=pe_error,
            file_version=_windows_file_version(artifact.absolute_path),
            deployed_path=deployed_path,
            deployed_exists=deployed_exists,
            deployed_sha256=deployed_sha,
            deployed_matches=(deployed_sha == digest) if deployed_sha else None,
        )
        binaries.append(binary)
        references.append(_binary_reference(binary))
        references.extend(_import_reference(binary, dependency) for dependency in imports)
    return binaries, references


def _latest(paths: Iterable[Path]) -> Path | None:
    files = [path for path in paths if path.is_file()]
    return max(files, key=lambda path: (path.stat().st_mtime_ns, path.name.casefold())) if files else None


def _level(line: str) -> str | None:
    match = re.search(r"\[(error|critical|warning|warn)\s*\]", line, re.IGNORECASE)
    if not match:
        return None
    level = match.group(1).casefold()
    return "error" if level in {"error", "critical"} else "warning"


def _parse_red4ext_runtime(game_root: Path) -> tuple[dict[str, Any], list[RuntimePlugin], list[dict[str, Any]]]:
    log_dir = game_root / "red4ext" / "logs"
    path = _latest(log_dir.glob("red4ext-*.log")) if log_dir.is_dir() else None
    coverage = {
        "name": "RED4ext loader log", "status": "unsupported", "files": 0,
        "lines": 0, "errors": 0, "warnings": 0, "events": 0,
        "correlated_events": 0, "static_confirmations": 0, "findings": 0,
        "loaded_plugins": 0, "attempted_binaries": 0,
        "red4ext_version": None, "game_product_version": None,
        "game_file_version": None, "log_path": str(path) if path else None,
        "note": "No RED4ext loader log was found.",
    }
    if path is None:
        return coverage, [], []
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    plugins: list[RuntimePlugin] = []
    pending: RuntimePlugin | None = None
    diagnostics: list[dict[str, Any]] = []
    red4ext_version = game_product = game_file = None
    for number, line in enumerate(lines, 1):
        match = re.search(r"RED4ext \(v([^\)]+)\) is initializing", line)
        if match:
            red4ext_version = match.group(1)
        match = re.search(r"Product version:\s*(\S+)", line)
        if match:
            game_product = match.group(1)
        match = re.search(r"File version:\s*(\S+)", line)
        if match:
            game_file = match.group(1)
        match = re.search(r"Loading plugin from '([^']+)'", line)
        if match:
            candidate = match.group(1)
            normalized_candidate = candidate.replace("/", "\\").casefold()
            if "\\red4ext\\plugins\\" in normalized_candidate:
                pending = RuntimePlugin(path=candidate)
                plugins.append(pending)
            else:
                pending = None
            continue
        match = re.search(
            r"(.+?) \(version:\s*([^,]+), author\(s\):\s*(.+?)\) has been loaded",
            line,
        )
        if match and pending:
            pending.name = match.group(1).split("]")[-1].strip()
            pending.version = match.group(2).strip()
            pending.authors = match.group(3).strip()
            pending.state = "loaded"
            pending = None
        level = _level(line)
        if level:
            item = {"path": str(path), "line": number, "severity": level, "message": line}
            diagnostics.append(item)
            if pending:
                pending.diagnostics.append(item)
                pending.state = "failed" if level == "error" else pending.state
    errors = sum(item["severity"] == "error" for item in diagnostics)
    warnings = len(diagnostics) - errors
    loaded = sum(plugin.state == "loaded" for plugin in plugins)
    coverage.update({
        "status": "analyzed", "files": 1, "lines": len(lines), "errors": errors,
        "warnings": warnings, "events": len(diagnostics),
        "correlated_events": sum(bool(plugin.diagnostics) for plugin in plugins),
        "findings": int(bool(diagnostics)), "loaded_plugins": loaded,
        "attempted_binaries": len(plugins), "red4ext_version": red4ext_version,
        "game_product_version": game_product, "game_file_version": game_file,
        "note": f"RED4ext {red4ext_version or 'unknown'} reported {loaded} loaded plugins for game {game_product or game_file or 'unknown'}.",
    })
    return coverage, plugins, diagnostics


def _relative_runtime_path(path: str, game_root: Path) -> str:
    try:
        return str(Path(path).resolve(strict=False).relative_to(game_root.resolve(strict=False))).replace("/", "\\").casefold()
    except ValueError:
        return path.replace("/", "\\").casefold()


def _is_system_dependency(name: str) -> bool:
    lowered = name.casefold()
    return (
        lowered in SYSTEM_DLLS
        or lowered.startswith(("api-ms-win-", "ext-ms-win-", "msvcp", "vcruntime", "concrt"))
        or lowered == "ucrtbase.dll"
    )


def _dependency_exists(binary: NativeBinary, dependency: str, game_root: Path) -> bool:
    if _is_system_dependency(dependency):
        return True
    candidates = (
        binary.deployed_path.parent / dependency,
        game_root / "bin" / "x64" / dependency,
        game_root / "bin" / "x64" / "plugins" / dependency,
        game_root / "red4ext" / dependency,
        game_root / dependency,
    )
    return any(path.is_file() for path in candidates)


def _version_prefix(value: str | None) -> tuple[int, ...] | None:
    if not value:
        return None
    match = re.search(r"\d+(?:\.\d+)+", value)
    if not match:
        return None
    parts = tuple(int(item) for item in match.group(0).split("."))
    while len(parts) > 3 and parts[-1] == 0:
        parts = parts[:-1]
    return parts[:3]


def _scan_framework_logs(game_root: Path) -> list[dict[str, Any]]:
    candidates: list[tuple[str, list[Path], str | None]] = []
    plugin_root = game_root / "red4ext" / "plugins"
    log_root = game_root / "red4ext" / "logs"
    candidates.append(("ArchiveXL", list((plugin_root / "ArchiveXL").glob("ArchiveXL-*.log")), "archivexl"))
    candidates.append(("TweakXL", list((plugin_root / "TweakXL").glob("TweakXL-*.log")), "tweakxl"))
    candidates.append(("Codeware", list((plugin_root / "Codeware").glob("Codeware-*.log")), None))
    if log_root.is_dir():
        grouped: dict[str, list[Path]] = defaultdict(list)
        for path in log_root.glob("*.log"):
            lowered = path.name.casefold()
            if lowered.startswith("red4ext-"):
                continue
            stem = re.sub(r"-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}$", "", path.stem, flags=re.IGNORECASE)
            grouped[stem.casefold()].append(path)
        for name, paths in grouped.items():
            candidates.append((name, paths, name if name in DELEGATED_LOGS else None))
    rows: list[dict[str, Any]] = []
    for name, paths, delegated in candidates:
        if name == "ArchiveXL":
            selected = sorted(paths, key=lambda path: path.name.casefold())
        else:
            latest = _latest(paths)
            selected = [latest] if latest else []
        lines: list[tuple[Path, int, str]] = []
        if delegated not in DELEGATED_LOGS:
            for path in selected:
                for number, line in enumerate(path.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1):
                    lines.append((path, number, line))
        errors = sum(_level(line) == "error" for _, _, line in lines)
        warnings = sum(_level(line) == "warning" for _, _, line in lines)
        rows.append({
            "name": name,
            "status": "analyzed" if selected else "unsupported",
            "files": len(selected),
            "lines": len(lines),
            "errors": None if delegated in DELEGATED_LOGS else errors,
            "warnings": None if delegated in DELEGATED_LOGS else warnings,
            "delegated_to": DELEGATED_LOGS.get(delegated or ""),
            "log_path": str(selected[-1]) if selected else None,
            "diagnostics": [
                {"path": str(path), "line": number, "severity": _level(line), "message": line}
                for path, number, line in lines if _level(line)
            ],
            "note": (
                f"Diagnostics are reported by {DELEGATED_LOGS[delegated]}."
                if delegated in DELEGATED_LOGS
                else "Structured warning/error levels are checked directly."
            ),
        })
    return rows


def _cet_versions(game_root: Path) -> tuple[str | None, str | None, str | None]:
    path = game_root / "bin" / "x64" / "plugins" / "cyber_engine_tweaks" / "cyber_engine_tweaks.log"
    if not path.is_file():
        return None, None, None
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    cet = re.search(r"CET version\s+v?([^\s]+)", text)
    game = re.search(r"Game version\s+([^\s]+)", text)
    return cet.group(1) if cet else None, game.group(1) if game else None, str(path)


def analyze_native_binaries(
    binaries: Iterable[NativeBinary],
    references: Iterable[Reference],
    game_root: Path,
) -> tuple[list[Finding], dict[str, Any]]:
    binary_list = list(binaries)
    reference_list = list(references)
    findings: list[Finding] = []
    runtime, runtime_plugins, runtime_diagnostics = _parse_red4ext_runtime(game_root)
    runtime_by_path = {
        _relative_runtime_path(plugin.path, game_root): plugin for plugin in runtime_plugins
    }
    imported_names = {
        dependency.casefold() for binary in binary_list
        if binary.artifact.deployed_state == "deployed" for dependency in binary.imports
    }
    for binary in binary_list:
        normalized = binary.artifact.relative_path.replace("/", "\\").casefold()
        plugin = runtime_by_path.get(normalized)
        if plugin:
            binary.runtime_name = plugin.name
            binary.runtime_version = plugin.version
            binary.runtime_authors = plugin.authors
            binary.runtime_state = (
                "companion"
                if plugin.state == "attempted"
                and binary.artifact.absolute_path.name.casefold() in imported_names
                else plugin.state
            )
        elif binary.category == "red4ext-plugin-binary" and binary.artifact.deployed_state == "deployed":
            binary.runtime_state = "companion" if binary.artifact.absolute_path.name.casefold() in imported_names else "not-observed"

    reference_by_path = {
        reference.details.get("relative_path", "").replace("/", "\\").casefold(): reference
        for reference in reference_list if reference.kind == "native.binary"
    }
    for binary in binary_list:
        reference = reference_by_path[binary.artifact.relative_path.replace("/", "\\").casefold()]
        reference.details.update({
            "runtime_name": binary.runtime_name,
            "runtime_version": binary.runtime_version,
            "runtime_authors": binary.runtime_authors,
            "runtime_state": binary.runtime_state,
        })

    grouped: dict[str, list[NativeBinary]] = defaultdict(list)
    for binary in binary_list:
        grouped[binary.artifact.relative_path.replace("/", "\\").casefold()].append(binary)
    for group in grouped.values():
        if len({binary.artifact.mod_name for binary in group}) < 2:
            continue
        identical = len({binary.sha256 for binary in group}) == 1
        findings.append(Finding(
            rule_id="NATIVE-BINARY-DUPLICATE" if identical else "NATIVE-BINARY-OVERRIDE",
            severity="info" if identical else "warning",
            confidence="high",
            summary=(
                f"Identical native binary is bundled by {len(group)} packages: {group[0].artifact.relative_path}"
                if identical else f"Different native binaries compete for {group[0].artifact.relative_path}"
            ),
            explanation=(
                "The providers are byte-identical, so Vortex's selected winner does not change runtime behavior."
                if identical else "Vortex can deploy only one provider at this exact binary path, and the package hashes differ. The selected winner determines the loaded native code."
            ),
            participants=sorted({binary.artifact.mod_name for binary in group}, key=str.casefold),
            evidence=[_binary_reference(binary).to_dict() for binary in group],
        ))

    active = [binary for binary in binary_list if binary.artifact.deployed_state == "deployed"]
    missing_deployed = [binary for binary in active if not binary.deployed_exists]
    mismatched_deployed = [binary for binary in active if binary.deployed_exists and not binary.deployed_matches]
    pe_failures = [binary for binary in active if binary.pe_error]
    if missing_deployed:
        findings.append(Finding(
            rule_id="NATIVE-DEPLOYMENT-MISSING", severity="error", confidence="high",
            summary=f"{len(missing_deployed)} Vortex-selected native binary file(s) are absent from the game",
            explanation="The deployment manifest selects these package files, but the corresponding game paths do not exist.",
            participants=sorted({binary.artifact.mod_name for binary in missing_deployed}, key=str.casefold),
            evidence=[reference_by_path[binary.artifact.relative_path.replace("/", "\\").casefold()].to_dict() for binary in missing_deployed],
        ))
    if mismatched_deployed:
        findings.append(Finding(
            rule_id="NATIVE-DEPLOYMENT-MISMATCH", severity="warning", confidence="high",
            summary=f"{len(mismatched_deployed)} deployed native binary file(s) differ from the selected Vortex source",
            explanation="The deployed file hash does not match its selected staging provider. The game may contain a stale or externally modified binary.",
            participants=sorted({binary.artifact.mod_name for binary in mismatched_deployed}, key=str.casefold),
            evidence=[reference_by_path[binary.artifact.relative_path.replace("/", "\\").casefold()].to_dict() for binary in mismatched_deployed],
        ))
    if pe_failures:
        findings.append(Finding(
            rule_id="NATIVE-PE-PARSE", severity="warning", confidence="high",
            summary=f"{len(pe_failures)} active native binary file(s) could not be parsed as PE images",
            explanation="Import dependencies could not be inventoried for these DLL/ASI files.",
            participants=sorted({binary.artifact.mod_name for binary in pe_failures}, key=str.casefold),
            evidence=[reference_by_path[binary.artifact.relative_path.replace("/", "\\").casefold()].to_dict() for binary in pe_failures],
        ))

    missing_imports: list[tuple[NativeBinary, str]] = []
    for binary in active:
        for dependency in binary.imports:
            if not _dependency_exists(binary, dependency, game_root):
                missing_imports.append((binary, dependency))
    if missing_imports:
        findings.append(Finding(
            rule_id="NATIVE-DEPENDENCY-MISSING", severity="error", confidence="high",
            summary=f"{len(missing_imports)} hard native DLL import(s) cannot be resolved locally",
            explanation="These non-system DLL names are present in PE import tables but absent from the binary directory and standard game-local search locations. Windows cannot load the importing binary unless another search path supplies them.",
            participants=sorted({binary.artifact.mod_name for binary, _ in missing_imports}, key=str.casefold),
            evidence=[{
                "identity": dependency,
                "source_path": str(binary.artifact.absolute_path),
                "line": 1,
                "details": {"binary": binary.artifact.relative_path, "deployed_path": str(binary.deployed_path)},
            } for binary, dependency in missing_imports],
        ))

    failed_plugins = [binary for binary in active if binary.category == "red4ext-plugin-binary" and binary.runtime_state == "failed"]
    unobserved_plugins = [binary for binary in active if binary.category == "red4ext-plugin-binary" and binary.runtime_state == "not-observed"]
    loader_errors = [item for item in runtime_diagnostics if item["severity"] == "error"]
    loader_warnings = [item for item in runtime_diagnostics if item["severity"] == "warning"]
    if failed_plugins or loader_errors:
        participants = {binary.artifact.mod_name for binary in failed_plugins}
        findings.append(Finding(
            rule_id="NATIVE-PLUGIN-LOAD-FAILED", severity="error", confidence="high",
            summary=f"RED4ext reported {runtime['errors']} loader error(s); {len(failed_plugins)} staged plugin binary file(s) are confirmed failed",
            explanation="The current RED4ext loader session contains native plugin load errors. Runtime log evidence is authoritative for this game/framework session.",
            participants=sorted(participants, key=str.casefold),
            evidence=loader_errors,
        ))
    if loader_warnings:
        findings.append(Finding(
            rule_id="NATIVE-LOADER-WARNING", severity="warning", confidence="high",
            summary=f"RED4ext reported {len(loader_warnings)} loader warning(s)",
            explanation="The current RED4ext loader session contains structured warnings that may affect native plugins even when loading completed.",
            evidence=loader_warnings,
        ))
    if unobserved_plugins:
        findings.append(Finding(
            rule_id="NATIVE-PLUGIN-NOT-OBSERVED", severity="warning", confidence="medium",
            summary=f"{len(unobserved_plugins)} deployed RED4ext plugin binary file(s) were not observed by the current loader log",
            explanation="The binary is deployed under red4ext/plugins but was neither loaded nor recognized as a hard dependency of another deployed native binary. The log may predate deployment or the plugin may be skipped.",
            participants=sorted({binary.artifact.mod_name for binary in unobserved_plugins}, key=str.casefold),
            evidence=[reference_by_path[binary.artifact.relative_path.replace("/", "\\").casefold()].to_dict() for binary in unobserved_plugins],
        ))

    version_mismatches = [
        binary for binary in active
        if binary.runtime_state == "loaded"
        and _version_prefix(binary.file_version)
        and _version_prefix(binary.runtime_version)
        and _version_prefix(binary.file_version) != _version_prefix(binary.runtime_version)
    ]
    if version_mismatches:
        findings.append(Finding(
            rule_id="NATIVE-VERSION-MISMATCH", severity="warning", confidence="high",
            summary=f"{len(version_mismatches)} plugin runtime version(s) disagree with Windows binary metadata",
            explanation="The RED4ext-reported semantic version and the PE fixed file version have different major/minor/patch values.",
            participants=sorted({binary.artifact.mod_name for binary in version_mismatches}, key=str.casefold),
            evidence=[reference_by_path[binary.artifact.relative_path.replace("/", "\\").casefold()].to_dict() for binary in version_mismatches],
        ))

    framework_logs = _scan_framework_logs(game_root)
    direct_log_diagnostics = [
        (row, item) for row in framework_logs if not row["delegated_to"]
        for item in row["diagnostics"]
    ]
    if direct_log_diagnostics:
        findings.append(Finding(
            rule_id="NATIVE-PLUGIN-LOG-DIAGNOSTIC",
            severity="error" if any(item["severity"] == "error" for _, item in direct_log_diagnostics) else "warning",
            confidence="high",
            summary=f"Non-delegated native plugin logs contain {len(direct_log_diagnostics)} warning/error event(s)",
            explanation="Structured diagnostics from Codeware and other native plugin logs are consolidated here. ArchiveXL, TweakXL, and Input Loader diagnostics remain in their dedicated analyzers.",
            participants=sorted({row["name"] for row, _ in direct_log_diagnostics}, key=str.casefold),
            evidence=[item for _, item in direct_log_diagnostics],
        ))

    cet_version, cet_game_version, cet_log = _cet_versions(game_root)
    version_disagreement = bool(
        runtime.get("game_file_version") and cet_game_version
        and runtime["game_file_version"] != cet_game_version
    )
    if version_disagreement:
        findings.append(Finding(
            rule_id="NATIVE-GAME-VERSION-DISAGREEMENT", severity="warning", confidence="high",
            summary="RED4ext and CET logs report different game executable versions",
            explanation="The framework logs appear to come from different game sessions or installations, so cross-framework runtime conclusions may be stale.",
            evidence=[{"path": runtime.get("log_path"), "version": runtime.get("game_file_version")}, {"path": cet_log, "version": cet_game_version}],
        ))

    plugin_rows = []
    for binary in sorted(
        (item for item in active if item.category == "red4ext-plugin-binary"),
        key=lambda item: (item.plugin_root or "").casefold(),
    ):
        plugin_rows.append({
            "name": binary.runtime_name or binary.plugin_root or binary.artifact.absolute_path.name,
            "status": "analyzed" if runtime["status"] == "analyzed" else "partial",
            "root": binary.plugin_root,
            "binary": binary.artifact.absolute_path.name,
            "runtime_state": binary.runtime_state,
            "runtime_version": binary.runtime_version,
            "file_version": binary.file_version,
            "authors": binary.runtime_authors,
            "imports": len(binary.imports),
            "non_system_imports": sum(not _is_system_dependency(item) for item in binary.imports),
            "deployment_match": binary.deployed_matches,
            "note": "Runtime compatibility is confirmed by the current RED4ext loader session." if binary.runtime_state == "loaded" else "This DLL is a companion dependency rather than a RED4ext plugin entrypoint." if binary.runtime_state == "companion" else "No successful plugin load was observed.",
        })

    coverage = {
        "documents": len(binary_list),
        "sections": [
            {
                "name": "native binary inventory", "documents": len(binary_list),
                "status": "partial" if pe_failures else "analyzed",
                "note": "DLL/ASI hashes, PE imports, fixed file versions, Vortex providers, and deployed copies are inventoried without loading code.",
            },
            {
                "name": "native runtime compatibility", "documents": runtime["loaded_plugins"],
                "status": runtime["status"],
                "note": "Current RED4ext and CET logs provide game/framework versions and authoritative successful-plugin load results.",
            },
        ],
        "native_operations": [{
            "name": "native binaries and hard dependencies",
            "status": "partial" if pe_failures else "analyzed",
            "documents": len(binary_list), "active_documents": len(active),
            "references": len(reference_list),
            "plugin_binaries": sum(binary.category == "red4ext-plugin-binary" for binary in active),
            "loaded_plugins": sum(binary.runtime_state == "loaded" for binary in active),
            "companion_libraries": sum(binary.runtime_state == "companion" for binary in active),
            "imports": sum(len(binary.imports) for binary in active),
            "non_system_imports": sum(not _is_system_dependency(dependency) for binary in active for dependency in binary.imports),
            "missing_imports": len(missing_imports),
            "shared_paths": sum(len({binary.artifact.mod_name for binary in group}) > 1 for group in grouped.values()),
            "deployment_mismatches": len(missing_deployed) + len(mismatched_deployed),
            "note": "PE normal/delay imports are resolved against system and game-local locations; exact-path providers and deployed hashes are compared.",
        }],
        "native_plugins": plugin_rows,
        "framework_versions": [{
            "name": "RED4ext", "status": runtime["status"],
            "version": runtime.get("red4ext_version"),
            "game_product_version": runtime.get("game_product_version"),
            "game_file_version": runtime.get("game_file_version"),
            "log_path": runtime.get("log_path"),
            "note": f"{runtime['loaded_plugins']} plugins loaded successfully in the selected session.",
        }, {
            "name": "Cyber Engine Tweaks", "status": "analyzed" if cet_version else "unsupported",
            "version": cet_version, "game_product_version": None,
            "game_file_version": cet_game_version, "log_path": cet_log,
            "note": "The CET and RED4ext game executable versions agree." if not version_disagreement and cet_version else "No current CET version metadata was found.",
        }],
        "framework_logs": [{key: value for key, value in row.items() if key != "diagnostics"} for row in framework_logs],
        "runtime_logs": [runtime],
    }
    return findings, coverage
