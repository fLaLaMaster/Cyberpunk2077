from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

from cp77compat.cli import resolve_scan_args
from cp77compat.config import ConfigError, load_config


class ConfigTests(unittest.TestCase):
    def test_relative_paths_resolve_from_config_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "scanner.yaml"
            path.write_text(
                """version: 1
paths:
  output: reports/current
  cache: .cache/archives
scan:
  archive_scope: none
  payload_scope: none
  hash_mode: none
  workers: 2
  refresh_cache: true
  wolvenkit_timeout_seconds: 45
""",
                encoding="utf-8",
            )
            config = load_config(path)
            self.assertEqual(root / "reports" / "current", config.output)
            self.assertEqual(root / ".cache" / "archives", config.cache)
            self.assertEqual("none", config.archive_scope)
            self.assertEqual("none", config.payload_scope)
            self.assertTrue(config.refresh_cache)
            self.assertEqual(45, config.wolvenkit_timeout_seconds)

    def test_duplicate_and_unknown_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            duplicate = root / "duplicate.yaml"
            duplicate.write_text("version: 1\nversion: 1\n", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(duplicate)

            unknown = root / "unknown.yaml"
            unknown.write_text("version: 1\nscan:\n  mystery: true\n", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(unknown)

    def test_cli_values_override_yaml_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "scanner.yaml"
            path.write_text(
                "version: 1\nscan:\n  workers: 2\n  refresh_cache: true\n",
                encoding="utf-8",
            )
            config = load_config(path)
            args = argparse.Namespace(
                staging=None,
                game=None,
                wolvenkit=None,
                output=root / "override",
                cache=None,
                archive_scope="all",
                payload_scope="none",
                hash_mode=None,
                workers=7,
                refresh_cache=False,
                wolvenkit_timeout=None,
                config=path,
            )
            resolved = resolve_scan_args(args, config)
            self.assertEqual(7, resolved.workers)
            self.assertEqual("all", resolved.archive_scope)
            self.assertEqual("none", resolved.payload_scope)
            self.assertFalse(resolved.refresh_cache)
            self.assertEqual((root / "override").resolve(), resolved.output)


if __name__ == "__main__":
    unittest.main()
