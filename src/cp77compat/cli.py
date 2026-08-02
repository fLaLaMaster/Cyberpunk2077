from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .archives import WolvenKitArchiveIndexer
from .archivexl import (
    compare_references,
    internal_archive_collisions,
    parse_documents,
    resolve_archive_references,
)
from .deployment import load_deployment
from .inventory import build_inventory, discover_mods, exact_path_findings
from .models import Finding
from .reporting import write_reports


DEFAULT_STAGING = Path(r"C:\Games\Programs\Vortex Mods\cyberpunk2077")
DEFAULT_GAME = Path(r"C:\Games\Steam\steamapps\common\Cyberpunk 2077")
DEFAULT_WOLVENKIT = Path(r"C:\Games\Programs\WolvenKit-Console\WolvenKit.CLI.exe")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cp77compat")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan = subparsers.add_parser("scan", help="scan a frozen Vortex mod collection")
    scan.add_argument("--staging", type=Path, default=DEFAULT_STAGING)
    scan.add_argument("--game", type=Path, default=DEFAULT_GAME)
    scan.add_argument("--wolvenkit", type=Path, default=DEFAULT_WOLVENKIT)
    scan.add_argument("--output", type=Path, default=Path.cwd() / "reports" / "current")
    scan.add_argument("--cache", type=Path, default=Path.cwd() / ".cache" / "archives")
    scan.add_argument("--archive-scope", choices=("none", "xl", "all"), default="xl")
    scan.add_argument("--hash-mode", choices=("none", "archives", "all"), default="archives")
    scan.add_argument("--workers", type=int, default=4)
    scan.add_argument("--refresh-cache", action="store_true")
    return parser


def run_scan(args: argparse.Namespace) -> int:
    if not args.staging.is_dir():
        raise SystemExit(f"Staging directory does not exist: {args.staging}")
    if not args.game.is_dir():
        raise SystemExit(f"Game directory does not exist: {args.game}")

    print(f"Discovering mods in {args.staging}")
    deployment = load_deployment(args.game)
    mods = discover_mods(args.staging)
    artifacts = build_inventory(mods, deployment, hash_mode=args.hash_mode)
    findings = exact_path_findings(artifacts)

    documents, references, archive_xl_findings = parse_documents(artifacts)
    findings.extend(archive_xl_findings)
    findings.extend(compare_references(references))
    print(f"Found {len(mods)} mods, {len(artifacts)} files, and {len(documents)} non-empty ArchiveXL configs")

    manifests = []
    wolvenkit_version = None
    if args.archive_scope != "none":
        if not args.wolvenkit.is_file():
            findings.append(
                Finding(
                    rule_id="WOLVENKIT-NOT-FOUND",
                    severity="error",
                    confidence="high",
                    summary="WolvenKit CLI was not found",
                    explanation=str(args.wolvenkit),
                )
            )
        else:
            xl_mods = {artifact.mod_name for artifact in artifacts if artifact.extension == ".xl"}
            archive_artifacts = [
                artifact
                for artifact in artifacts
                if artifact.extension == ".archive"
                and (args.archive_scope == "all" or artifact.mod_name in xl_mods)
            ]
            print(f"Indexing {len(archive_artifacts)} archives with WolvenKit")
            indexer = WolvenKitArchiveIndexer(
                args.wolvenkit,
                args.cache,
                workers=args.workers,
                refresh_cache=args.refresh_cache,
            )
            wolvenkit_version = indexer.version
            manifests, index_findings = indexer.index(archive_artifacts)
            findings.extend(index_findings)
            findings.extend(resolve_archive_references(references, manifests, artifacts))
            findings.extend(internal_archive_collisions(manifests))

    metadata = {
        "scanner_version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "staging_root": str(args.staging),
        "game_root": str(args.game),
        "archive_scope": args.archive_scope,
        "hash_mode": args.hash_mode,
        "wolvenkit": str(args.wolvenkit),
        "wolvenkit_version": wolvenkit_version,
    }
    write_reports(
        args.output,
        mods,
        artifacts,
        deployment.to_dict() if deployment else None,
        manifests,
        references,
        findings,
        metadata,
    )
    print(f"Wrote reports to {args.output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            return run_scan(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 2
