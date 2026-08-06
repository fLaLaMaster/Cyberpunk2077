from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from cp77compat.archive_payloads import (
    WolvenKitArchivePayloadProvider,
    resource_path_hash,
    safe_member_path,
)
from cp77compat.models import ArchiveManifest, ArchiveMember


RESOURCE = r"base\localization\en-us\onscreens\example.json"


def manifest(path: Path) -> ArchiveManifest:
    return ArchiveManifest(
        mod_name="Example",
        archive_path=str(path),
        sha256="a" * 64,
        size=path.stat().st_size,
        wolvenkit_version="8.19.0",
        members=[ArchiveMember(RESOURCE)],
    )


class ArchivePayloadTests(unittest.TestCase):
    def test_fnv_hash_matches_wolvenkit(self) -> None:
        self.assertEqual(
            2656514476776495490,
            resource_path_hash(
                r"base\localization\en-us\onscreens\first-equip.json"
            ),
        )

    def test_safe_member_path_rejects_traversal_and_absolute_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertEqual(
                root / "base" / "example.json",
                safe_member_path(root, r"base\example.json"),
            )
            for unsafe in (r"..\escape.json", r"C:\escape.json", r"\escape.json"):
                with self.subTest(unsafe=unsafe), self.assertRaises(ValueError):
                    safe_member_path(root, unsafe)

    def test_exact_extraction_and_serialization_are_cached(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "example.archive"
            archive.write_bytes(b"archive")
            calls: list[list[str]] = []

            def runner(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(command)
                if "unbundle" in command:
                    output_root = Path(command[command.index("--outpath") + 1])
                    output = output_root / "base" / "localization" / "en-us" / "onscreens" / "example.json"
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(b"CR2W")
                    return subprocess.CompletedProcess(command, 0, "extracted", "")
                return subprocess.CompletedProcess(
                    command,
                    0,
                    json.dumps({"Data": {"RootChunk": {"value": 1}}}),
                    "",
                )

            provider = WolvenKitArchivePayloadProvider(
                root / "WolvenKit.CLI.exe",
                root / "cache",
                "8.19.0",
                runner=runner,
            )
            first = provider.serialize_json(manifest(archive), RESOURCE)
            second = provider.serialize_json(manifest(archive), RESOURCE)
            self.assertTrue(first.ok)
            self.assertTrue(second.ok)
            self.assertTrue(second.from_cache)
            self.assertEqual(2, len(calls))
            self.assertEqual(
                str(resource_path_hash(RESOURCE)),
                calls[0][calls[0].index("--hash") + 1],
            )

            metadata = json.loads(
                first.payload.metadata_path.read_text(encoding="utf-8")
            )
            self.assertEqual("success", metadata["extraction"]["status"])
            self.assertEqual("success", metadata["conversion"]["status"])
            self.assertEqual("a" * 64, metadata["source_archive_sha256"])
            self.assertEqual(120, metadata["extraction"]["timeout_seconds"])
            self.assertEqual(120, metadata["conversion"]["timeout_seconds"])

    def test_corrupt_cached_payload_is_extracted_again(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "example.archive"
            archive.write_bytes(b"archive")
            calls = 0

            def runner(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal calls
                calls += 1
                output_root = Path(command[command.index("--outpath") + 1])
                output = output_root / "base" / "localization" / "en-us" / "onscreens" / "example.json"
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(f"payload-{calls}".encode())
                return subprocess.CompletedProcess(command, 0, "extracted", "")

            provider = WolvenKitArchivePayloadProvider(
                root / "WolvenKit.CLI.exe",
                root / "cache",
                "8.19.0",
                runner=runner,
            )
            first = provider.materialize(manifest(archive), RESOURCE)
            self.assertTrue(first.ok)
            first.path.write_bytes(b"corrupt")
            second = provider.materialize(manifest(archive), RESOURCE)
            self.assertTrue(second.ok)
            self.assertFalse(second.from_cache)
            self.assertEqual(2, calls)

    def test_valid_serialization_survives_wolvenkit_nonzero_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "example.archive"
            archive.write_bytes(b"archive")

            def runner(
                command: list[str], **_kwargs: object
            ) -> subprocess.CompletedProcess[str]:
                if "unbundle" in command:
                    output_root = Path(command[command.index("--outpath") + 1])
                    output = (
                        output_root
                        / "base"
                        / "localization"
                        / "en-us"
                        / "onscreens"
                        / "example.json"
                    )
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(b"CR2W")
                    return subprocess.CompletedProcess(command, 0, "extracted", "")
                return subprocess.CompletedProcess(
                    command,
                    160,
                    json.dumps({"Data": {"RootChunk": {"value": 1}}}),
                    "Input path does not exist.",
                )

            provider = WolvenKitArchivePayloadProvider(
                root / "WolvenKit.CLI.exe",
                root / "cache",
                "8.20.0",
                runner=runner,
            )
            result = provider.serialize_json(manifest(archive), RESOURCE)

            self.assertTrue(result.ok)
            self.assertEqual(1, result.data["Data"]["RootChunk"]["value"])
            metadata = json.loads(
                result.payload.metadata_path.read_text(encoding="utf-8")
            )
            self.assertEqual(160, metadata["conversion"]["returncode"])
            self.assertTrue(
                metadata["conversion"]["accepted_nonzero_returncode"]
            )

    def test_nonzero_exit_without_valid_json_is_still_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "example.archive"
            archive.write_bytes(b"archive")

            def runner(
                command: list[str], **_kwargs: object
            ) -> subprocess.CompletedProcess[str]:
                if "unbundle" in command:
                    output_root = Path(command[command.index("--outpath") + 1])
                    output = (
                        output_root
                        / "base"
                        / "localization"
                        / "en-us"
                        / "onscreens"
                        / "example.json"
                    )
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(b"CR2W")
                    return subprocess.CompletedProcess(command, 0, "extracted", "")
                return subprocess.CompletedProcess(
                    command, 160, "not json", "conversion failed"
                )

            provider = WolvenKitArchivePayloadProvider(
                root / "WolvenKit.CLI.exe",
                root / "cache",
                "8.20.0",
                runner=runner,
            )
            result = provider.serialize_json(manifest(archive), RESOURCE)

            self.assertFalse(result.ok)
            self.assertEqual("conversion failed", result.error)

    def test_unknown_or_unsafe_member_never_invokes_wolvenkit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "example.archive"
            archive.write_bytes(b"archive")

            def runner(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
                raise AssertionError("runner must not be called")

            provider = WolvenKitArchivePayloadProvider(
                root / "WolvenKit.CLI.exe",
                root / "cache",
                "8.19.0",
                runner=runner,
            )
            result = provider.materialize(manifest(archive), r"..\escape.json")
            self.assertFalse(result.ok)
            self.assertIn("not a resolved member", result.error)


if __name__ == "__main__":
    unittest.main()
