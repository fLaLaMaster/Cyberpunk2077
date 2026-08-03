from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .archives import WolvenKitArchiveIndexer
from .archive_payloads import WolvenKitArchivePayloadProvider
from .archivexl_runtime import analyze_archivexl_runtime_logs
from .archivexl import (
    build_archivexl_coverage,
    compare_override_references,
    compare_player_references,
    compare_quest_references,
    compare_references,
    compare_resource_references,
    compare_streaming_mutations,
    internal_archive_collisions,
    parse_documents,
    resolve_archive_references,
    resolve_quest_references,
)
from .archivexl_payload_analysis import (
    inspect_customization_payloads,
    inspect_factory_payloads,
    inspect_journal_payloads,
    inspect_localization_payloads,
    inspect_resource_patch_payloads,
)
from .config import DEFAULT_CONFIG_PATH, ScannerConfig, load_config
from .deployment import load_deployment
from .inventory import build_inventory, discover_mods, exact_path_findings
from .models import Finding
from .reporting import write_reports
from .tweakxl import compare_tweak_references, parse_tweak_documents
from .tweakxl_dependencies import analyze_tweak_dependencies
from .tweakxl_runtime import analyze_tweakxl_runtime_logs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cp77compat")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan = subparsers.add_parser("scan", help="scan a frozen Vortex mod collection")
    scan.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    scan.add_argument("--staging", type=Path)
    scan.add_argument("--game", type=Path)
    scan.add_argument("--wolvenkit", type=Path)
    scan.add_argument("--output", type=Path)
    scan.add_argument("--cache", type=Path)
    scan.add_argument("--archive-scope", choices=("none", "xl", "all"))
    scan.add_argument(
        "--payload-scope",
        choices=(
            "none",
            "customizations",
            "localization",
            "factories",
            "journals",
            "patches",
            "all",
        ),
    )
    scan.add_argument("--hash-mode", choices=("none", "archives", "all"))
    scan.add_argument("--workers", type=int)
    scan.add_argument(
        "--refresh-cache",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    scan.add_argument("--wolvenkit-timeout", type=int)
    return parser


def resolve_scan_args(args: argparse.Namespace, config: ScannerConfig) -> argparse.Namespace:
    for name in ("staging", "game", "wolvenkit", "output", "cache"):
        if getattr(args, name) is None:
            setattr(args, name, getattr(config, name))
        else:
            setattr(args, name, getattr(args, name).expanduser().resolve(strict=False))
    if args.archive_scope is None:
        args.archive_scope = config.archive_scope
    if args.payload_scope is None:
        args.payload_scope = config.payload_scope
    if args.hash_mode is None:
        args.hash_mode = config.hash_mode
    if args.workers is None:
        args.workers = config.workers
    if args.refresh_cache is None:
        args.refresh_cache = config.refresh_cache
    if args.wolvenkit_timeout is None:
        args.wolvenkit_timeout = config.wolvenkit_timeout_seconds
    if args.workers < 1:
        raise ValueError("--workers must be a positive integer")
    if args.wolvenkit_timeout < 1:
        raise ValueError("--wolvenkit-timeout must be a positive integer")
    args.config = config.source_path
    args.config_version = config.version
    return args


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
    findings.extend(compare_streaming_mutations(references))
    findings.extend(compare_resource_references(references))
    findings.extend(compare_quest_references(references))
    findings.extend(compare_override_references(references))
    findings.extend(compare_player_references(references))
    coverage = {"archivexl": build_archivexl_coverage(documents, references)}
    tweak_documents, tweak_references, tweak_findings = parse_tweak_documents(artifacts)
    findings.extend(tweak_findings)
    findings.extend(compare_tweak_references(tweak_references))
    dependency_findings, tweak_coverage = analyze_tweak_dependencies(
        tweak_references,
        args.game,
    )
    findings.extend(dependency_findings)
    runtime_findings, runtime_coverage = analyze_tweakxl_runtime_logs(
        args.game,
        artifacts,
        tweak_references,
        findings,
    )
    findings.extend(runtime_findings)
    tweak_coverage["runtime_logs"] = [runtime_coverage]
    tweak_coverage["sections"].append(
        {
            "name": "runtime log correlation",
            "documents": 1 if runtime_coverage["status"] == "analyzed" else 0,
            "status": runtime_coverage["status"],
            "note": (
                f"Latest TweakXL log: {runtime_coverage['errors']} errors, "
                f"{runtime_coverage['warnings']} warnings, "
                f"{runtime_coverage['correlated_events']} source-attributed events."
                if runtime_coverage["status"] == "analyzed"
                else runtime_coverage["note"]
            ),
        }
    )
    coverage["tweakxl"] = tweak_coverage
    if runtime_coverage["status"] == "analyzed":
        print(
            f"Parsed latest TweakXL runtime log: {runtime_coverage['errors']} errors, "
            f"{runtime_coverage['warnings']} warnings, "
            f"{runtime_coverage['findings']} consolidated findings"
        )
    print(
        f"Found {len(mods)} mods, {len(artifacts)} files, "
        f"{len(documents)} non-empty ArchiveXL configs, and "
        f"{len(tweak_documents)} non-empty TweakXL configs"
    )

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
                timeout_seconds=args.wolvenkit_timeout,
            )
            wolvenkit_version = indexer.version
            manifests, index_findings = indexer.index(archive_artifacts)
            findings.extend(index_findings)
            findings.extend(resolve_archive_references(references, manifests, artifacts))
            quest_findings, quest_stats = resolve_quest_references(
                references, manifests, artifacts
            )
            findings.extend(quest_findings)
            coverage["archivexl"]["quest_operations"] = [quest_stats]
            for section in coverage["archivexl"]["sections"]:
                if section["name"] == "quest":
                    section["status"] = "analyzed"
                    section["note"] = quest_stats["note"]
                    break
            findings.extend(internal_archive_collisions(manifests))
            payload_coverage = {}
            if args.payload_scope != "none":
                provider = WolvenKitArchivePayloadProvider(
                    args.wolvenkit,
                    args.cache,
                    wolvenkit_version,
                    refresh_cache=args.refresh_cache,
                    timeout_seconds=args.wolvenkit_timeout,
                )
            if args.payload_scope in {"customizations", "all"}:
                print("Inspecting ArchiveXL customization payloads")
                payload_references, payload_findings, payload_stats = (
                    inspect_customization_payloads(
                        references,
                        manifests,
                        provider,
                        workers=args.workers,
                    )
                )
                references.extend(payload_references)
                findings.extend(payload_findings)
                payload_coverage["customizations"] = payload_stats
                for section in coverage["archivexl"]["sections"]:
                    if section["name"] == "customizations":
                        section["status"] = "analyzed"
                        section["note"] = (
                            "Male and female customization resources are resolved; "
                            "serialized group, option, selector, and choice identities "
                            "are compared using ArchiveXL merge semantics."
                        )
                        break
                print(
                    f"Serialized {payload_stats['serialized']} customization payloads; "
                    f"extracted {payload_stats['entry_references']} merge identities"
                )
            if args.payload_scope in {"localization", "all"}:
                print("Inspecting ArchiveXL localization payloads")
                payload_references, payload_findings, payload_stats = (
                    inspect_localization_payloads(
                        references,
                        manifests,
                        provider,
                        workers=args.workers,
                    )
                )
                references.extend(payload_references)
                findings.extend(payload_findings)
                payload_coverage["localization"] = payload_stats
                for section in coverage["archivexl"]["sections"]:
                    if section["name"] == "localization":
                        section["status"] = "analyzed"
                        section["note"] = (
                            "On-screen resources are resolved and archive-owned "
                            "payload entry identities are compared."
                        )
                        break
                print(
                    f"Serialized {payload_stats['serialized']} localization payloads; "
                    f"extracted {payload_stats['entry_references']} entry references"
                )
            if args.payload_scope in {"factories", "all"}:
                print("Inspecting ArchiveXL factory payloads")
                payload_references, payload_findings, payload_stats = (
                    inspect_factory_payloads(
                        references,
                        manifests,
                        artifacts,
                        provider,
                        workers=args.workers,
                    )
                )
                references.extend(payload_references)
                findings.extend(payload_findings)
                payload_coverage["factories"] = payload_stats
                for section in coverage["archivexl"]["sections"]:
                    if section["name"] == "factories":
                        section["status"] = "analyzed"
                        section["note"] = (
                            "Factory CSV entity names and target resource paths are "
                            "extracted, compared, and resolved."
                        )
                        break
                print(
                    f"Serialized {payload_stats['serialized']} factory payloads; "
                    f"extracted {payload_stats['entry_references']} entity rows"
                )
            if args.payload_scope in {"journals", "all"}:
                print("Inspecting ArchiveXL journal payloads")
                payload_references, payload_findings, payload_stats = (
                    inspect_journal_payloads(
                        references,
                        manifests,
                        provider,
                        workers=args.workers,
                    )
                )
                references.extend(payload_references)
                findings.extend(payload_findings)
                payload_coverage["journals"] = payload_stats
                for section in coverage["archivexl"]["sections"]:
                    if section["name"] == "journal":
                        section["status"] = "analyzed"
                        section["note"] = (
                            "Journal resources are resolved and serialized entry trees "
                            "are compared using ArchiveXL's effective slash-delimited paths."
                        )
                        break
                print(
                    f"Serialized {payload_stats['serialized']} journal payloads; "
                    f"extracted {payload_stats['entry_references']} entry identities"
                )
            if args.payload_scope in {"patches", "all"}:
                print("Inspecting shared ArchiveXL resource patch payloads")
                payload_references, payload_findings, payload_stats = (
                    inspect_resource_patch_payloads(
                        references,
                        manifests,
                        provider,
                        workers=args.workers,
                    )
                )
                references.extend(payload_references)
                findings = [
                    finding
                    for finding in findings
                    if finding.rule_id != "AXL-RESOURCE-PATCH-COMPOSABLE"
                ]
                findings.extend(payload_findings)
                payload_coverage["patches"] = payload_stats
                for section in coverage["archivexl"]["sections"]:
                    if section["name"] == "resource":
                        section["note"] = (
                            "Declarations are analyzed and shared-target patch "
                            "payloads are compared by stable inner identities; "
                            "unshared payload contents remain outside scan scope."
                        )
                        break
                print(
                    f"Serialized {payload_stats['serialized']} shared patch payloads; "
                    f"compared {payload_stats['shared_targets']} targets"
                )
            if payload_coverage:
                coverage["archivexl"]["payloads"] = payload_coverage

    archive_runtime_findings, archive_runtime_coverage = analyze_archivexl_runtime_logs(
        args.game,
        artifacts,
        references,
        findings,
    )
    findings.extend(archive_runtime_findings)
    coverage["archivexl"]["runtime_logs"] = [archive_runtime_coverage]
    coverage["archivexl"]["sections"].append(
        {
            "name": "runtime log correlation",
            "documents": archive_runtime_coverage["files"],
            "status": archive_runtime_coverage["status"],
            "note": (
                f"Latest ArchiveXL session: {archive_runtime_coverage['errors']} errors, "
                f"{archive_runtime_coverage['warnings']} warnings, "
                f"{archive_runtime_coverage['correlated_events']} source-attributed events."
                if archive_runtime_coverage["status"] == "analyzed"
                else archive_runtime_coverage["note"]
            ),
        }
    )
    if any(
        finding.rule_id == "AXL-RUNTIME-QUEST-PHASE-MISSING"
        for finding in archive_runtime_findings
    ):
        for section in coverage["archivexl"]["sections"]:
            if section["name"] == "quest":
                if section["status"] != "analyzed":
                    section["status"] = "partial"
                section["note"] += (
                    " Runtime missing-phase messages are correlated with exact "
                    "phase or parent declarations."
                )
                break
    if archive_runtime_coverage["status"] == "analyzed":
        print(
            f"Parsed latest ArchiveXL runtime session: "
            f"{archive_runtime_coverage['errors']} errors, "
            f"{archive_runtime_coverage['warnings']} warnings, "
            f"{archive_runtime_coverage['findings']} consolidated findings"
        )

    metadata = {
        "scanner_version": __version__,
        "config_file": str(args.config),
        "config_version": args.config_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "staging_root": str(args.staging),
        "game_root": str(args.game),
        "archive_scope": args.archive_scope,
        "payload_scope": args.payload_scope,
        "hash_mode": args.hash_mode,
        "workers": args.workers,
        "wolvenkit": str(args.wolvenkit),
        "wolvenkit_version": wolvenkit_version,
        "wolvenkit_timeout_seconds": args.wolvenkit_timeout,
    }
    write_reports(
        args.output,
        mods,
        artifacts,
        deployment.to_dict() if deployment else None,
        manifests,
        references,
        tweak_references,
        findings,
        metadata,
        coverage,
    )
    print(f"Wrote reports to {args.output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            config = load_config(args.config)
            args = resolve_scan_args(args, config)
            return run_scan(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 2
