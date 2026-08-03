from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError


CONFIG_VERSION = 1
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "cp77compat.yaml"

DEFAULT_STAGING = Path(r"C:\Games\Programs\Vortex Mods\cyberpunk2077")
DEFAULT_GAME = Path(r"C:\Games\Steam\steamapps\common\Cyberpunk 2077")
DEFAULT_WOLVENKIT = Path(r"C:\Games\Programs\WolvenKit-Console\WolvenKit.CLI.exe")


class ConfigError(ValueError):
    pass


class StrictConfigLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_mapping(
    loader: StrictConfigLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConstructorError(
                "while constructing scanner configuration",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


StrictConfigLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


@dataclass(frozen=True, slots=True)
class ScannerConfig:
    source_path: Path
    version: int
    staging: Path
    game: Path
    wolvenkit: Path
    output: Path
    cache: Path
    archive_scope: str
    payload_scope: str
    hash_mode: str
    workers: int
    refresh_cache: bool
    wolvenkit_timeout_seconds: int


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{label} must be a YAML mapping")
    return value


def _reject_unknown(mapping: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(str(key) for key in mapping if key not in allowed)
    if unknown:
        raise ConfigError(f"unknown {label} key(s): {', '.join(unknown)}")


def _path_value(value: Any, default: Path, base: Path, label: str) -> Path:
    if value is None:
        path = default
    elif isinstance(value, str) and value.strip():
        path = Path(os.path.expandvars(os.path.expanduser(value.strip())))
    else:
        raise ConfigError(f"{label} must be a non-empty path string")
    if not path.is_absolute():
        path = base / path
    return path.resolve(strict=False)


def _choice(value: Any, default: str, choices: set[str], label: str) -> str:
    selected = default if value is None else value
    if not isinstance(selected, str) or selected not in choices:
        raise ConfigError(f"{label} must be one of: {', '.join(sorted(choices))}")
    return selected


def _positive_int(value: Any, default: int, label: str) -> int:
    selected = default if value is None else value
    if isinstance(selected, bool) or not isinstance(selected, int) or selected < 1:
        raise ConfigError(f"{label} must be a positive integer")
    return selected


def load_config(path: Path) -> ScannerConfig:
    source_path = path.expanduser().resolve(strict=False)
    if not source_path.is_file():
        raise ConfigError(f"configuration file does not exist: {source_path}")
    try:
        loaded = yaml.load(
            source_path.read_text(encoding="utf-8-sig"),
            Loader=StrictConfigLoader,
        )
    except yaml.YAMLError as exc:
        raise ConfigError(f"cannot parse configuration {source_path}: {exc}") from exc

    root = _mapping(loaded, "configuration root")
    _reject_unknown(root, {"version", "paths", "scan"}, "top-level")
    version = root.get("version", CONFIG_VERSION)
    if isinstance(version, bool) or not isinstance(version, int):
        raise ConfigError("version must be an integer")
    if version != CONFIG_VERSION:
        raise ConfigError(
            f"unsupported configuration version {version}; expected {CONFIG_VERSION}"
        )

    paths = _mapping(root.get("paths"), "paths")
    scan = _mapping(root.get("scan"), "scan")
    _reject_unknown(
        paths,
        {"staging", "game", "wolvenkit", "output", "cache"},
        "paths",
    )
    _reject_unknown(
        scan,
        {
            "archive_scope",
            "payload_scope",
            "hash_mode",
            "workers",
            "refresh_cache",
            "wolvenkit_timeout_seconds",
        },
        "scan",
    )

    refresh_cache = scan.get("refresh_cache", False)
    if not isinstance(refresh_cache, bool):
        raise ConfigError("scan.refresh_cache must be true or false")

    base = source_path.parent
    return ScannerConfig(
        source_path=source_path,
        version=version,
        staging=_path_value(paths.get("staging"), DEFAULT_STAGING, base, "paths.staging"),
        game=_path_value(paths.get("game"), DEFAULT_GAME, base, "paths.game"),
        wolvenkit=_path_value(paths.get("wolvenkit"), DEFAULT_WOLVENKIT, base, "paths.wolvenkit"),
        output=_path_value(paths.get("output"), PROJECT_ROOT / "reports" / "current", base, "paths.output"),
        cache=_path_value(paths.get("cache"), PROJECT_ROOT / ".cache" / "archives", base, "paths.cache"),
        archive_scope=_choice(scan.get("archive_scope"), "xl", {"none", "xl", "all"}, "scan.archive_scope"),
        payload_scope=_choice(
            scan.get("payload_scope"),
            "all",
            {"all", "factories", "journals", "localization", "none", "patches"},
            "scan.payload_scope",
        ),
        hash_mode=_choice(scan.get("hash_mode"), "archives", {"none", "archives", "all"}, "scan.hash_mode"),
        workers=_positive_int(scan.get("workers"), 4, "scan.workers"),
        refresh_cache=refresh_cache,
        wolvenkit_timeout_seconds=_positive_int(
            scan.get("wolvenkit_timeout_seconds"),
            120,
            "scan.wolvenkit_timeout_seconds",
        ),
    )
