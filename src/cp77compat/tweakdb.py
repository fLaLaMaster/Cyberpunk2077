from __future__ import annotations

import re
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


PACKAGE_PATTERN = re.compile(r"^\s*package\s+([A-Za-z_][A-Za-z0-9_.]*)\s*$")
RECORD_PATTERN = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_.]*)"
    r"(?:\s*:\s*[A-Za-z_][A-Za-z0-9_.]*)?\s*(\{)?\s*$"
)
INLINE_RECORD_PATTERN = re.compile(r"_inline\d+$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class TweakDBRecordIndex:
    named_records: frozenset[str]
    source_files: int
    binary_files: tuple[Path, ...]
    binary_data: tuple[bytes, ...]

    def contains_named(self, identity: str) -> bool:
        return identity in self.named_records

    def contains_generated_inline(self, identity: str) -> bool:
        if not INLINE_RECORD_PATTERN.search(identity):
            return False
        encoded = identity.encode("utf-8")
        if not encoded or len(encoded) > 0xFF:
            return False
        tweakdb_id = struct.pack("<IB3x", zlib.crc32(encoded), len(encoded))
        return any(tweakdb_id in data for data in self.binary_data)

    def contains(self, identity: str) -> bool:
        return self.contains_named(identity) or self.contains_generated_inline(identity)


def _strip_comments_and_strings(line: str, in_block_comment: bool) -> tuple[str, bool]:
    """Keep tweak syntax while removing braces hidden in comments and strings."""
    result: list[str] = []
    index = 0
    quote: str | None = None
    while index < len(line):
        current = line[index]
        following = line[index + 1] if index + 1 < len(line) else ""
        if in_block_comment:
            if current == "*" and following == "/":
                in_block_comment = False
                index += 2
            else:
                index += 1
            continue
        if quote is not None:
            if current == "\\":
                index += 2
                continue
            if current == quote:
                quote = None
            index += 1
            continue
        if current == "/" and following == "/":
            break
        if current == "/" and following == "*":
            in_block_comment = True
            index += 2
            continue
        if current in {'"', "'"}:
            quote = current
            index += 1
            continue
        result.append(current)
        index += 1
    return "".join(result), in_block_comment


def _record_names_from_source(path: Path) -> set[str]:
    try:
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        return set()

    cleaned: list[str] = []
    in_block_comment = False
    for line in lines:
        value, in_block_comment = _strip_comments_and_strings(line, in_block_comment)
        cleaned.append(value)

    records: set[str] = set()
    package = ""
    depth = 0
    for index, line in enumerate(cleaned):
        stripped = line.strip()
        if depth == 0 and stripped:
            package_match = PACKAGE_PATTERN.fullmatch(stripped)
            if package_match:
                package = package_match.group(1)
            else:
                record_match = RECORD_PATTERN.fullmatch(stripped)
                if record_match:
                    has_open_brace = bool(record_match.group(2))
                    lookahead = index + 1
                    while lookahead < len(cleaned) and not cleaned[lookahead].strip():
                        lookahead += 1
                    opens_next = (
                        lookahead < len(cleaned)
                        and cleaned[lookahead].lstrip().startswith("{")
                    )
                    if has_open_brace or opens_next:
                        name = record_match.group(1)
                        records.add(name if "." in name or not package else f"{package}.{name}")
        depth += line.count("{") - line.count("}")
        if depth < 0:
            depth = 0
    return records


def build_tweakdb_record_index(game_root: Path) -> TweakDBRecordIndex:
    source_root = game_root / "tools" / "redmod" / "tweaks"
    source_paths = (
        sorted(source_root.rglob("*.tweak"), key=lambda item: str(item).casefold())
        if source_root.is_dir()
        else []
    )
    records: set[str] = set()
    for path in source_paths:
        records.update(_record_names_from_source(path))

    cache_root = game_root / "r6" / "cache"
    binary_paths = tuple(
        path
        for name in ("tweakdb.bin", "tweakdb_ep1.bin")
        if (path := cache_root / name).is_file()
    )
    binary_data: list[bytes] = []
    loaded_paths: list[Path] = []
    for path in binary_paths:
        try:
            binary_data.append(path.read_bytes())
            loaded_paths.append(path)
        except OSError:
            continue

    return TweakDBRecordIndex(
        named_records=frozenset(records),
        source_files=len(source_paths),
        binary_files=tuple(loaded_paths),
        binary_data=tuple(binary_data),
    )


def validate_tweakdb_ids(
    index: TweakDBRecordIndex,
    identities: Iterable[str],
) -> dict[str, bool]:
    return {identity: index.contains(identity) for identity in set(identities)}
