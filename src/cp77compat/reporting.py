from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .html_report import write_html_report
from .models import ArchiveManifest, Artifact, Finding, ModSource, Reference


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def write_reports(
    output_dir: Path,
    mods: list[ModSource],
    artifacts: list[Artifact],
    deployment: dict[str, Any] | None,
    manifests: list[ArchiveManifest],
    archivexl_references: list[Reference],
    tweakxl_references: list[Reference],
    redscript_references: list[Reference],
    cet_references: list[Reference],
    findings: list[Finding],
    metadata: dict[str, Any],
    coverage: dict[str, Any] | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    ordered_findings = sorted(findings, key=lambda item: item.sort_key())
    summary = {
        "mods": len(mods),
        "artifacts": len(artifacts),
        "archive_manifests": len(manifests),
        "archive_members": sum(len(item.members) for item in manifests),
        "archivexl_references": len(archivexl_references),
        "tweakxl_references": len(tweakxl_references),
        "redscript_references": len(redscript_references),
        "cet_references": len(cet_references),
        "findings": dict(sorted(Counter(item.severity for item in ordered_findings).items())),
        "coverage": coverage or {},
    }
    _write_json(
        output_dir / "inventory.json",
        {
            "metadata": metadata,
            "summary": summary,
            "deployment": deployment,
            "mods": [mod.to_dict() for mod in mods],
            "artifacts": [artifact.to_dict() for artifact in artifacts],
        },
    )
    _write_json(
        output_dir / "archive-manifests.json",
        {
            "metadata": metadata,
            "archives": [manifest.to_dict() for manifest in manifests],
        },
    )
    _write_json(
        output_dir / "archivexl-findings.json",
        {
            "metadata": metadata,
            "summary": summary,
            "references": [reference.to_dict() for reference in archivexl_references],
            "findings": [
                finding.to_dict()
                for finding in ordered_findings
                if finding.rule_id.startswith("AXL-")
            ],
        },
    )
    _write_json(
        output_dir / "tweakxl-findings.json",
        {
            "metadata": metadata,
            "summary": summary,
            "references": [reference.to_dict() for reference in tweakxl_references],
            "findings": [
                finding.to_dict()
                for finding in ordered_findings
                if finding.rule_id.startswith("TXL-")
            ],
        },
    )
    _write_json(
        output_dir / "redscript-findings.json",
        {
            "metadata": metadata,
            "summary": summary,
            "references": [reference.to_dict() for reference in redscript_references],
            "findings": [
                finding.to_dict()
                for finding in ordered_findings
                if finding.rule_id.startswith("RS-")
            ],
        },
    )
    _write_json(
        output_dir / "cet-findings.json",
        {
            "metadata": metadata,
            "summary": summary,
            "references": [reference.to_dict() for reference in cet_references],
            "findings": [
                finding.to_dict()
                for finding in ordered_findings
                if finding.rule_id.startswith("CET-")
            ],
        },
    )
    _write_json(
        output_dir / "compatibility-findings.json",
        {
            "metadata": metadata,
            "summary": summary,
            "findings": [finding.to_dict() for finding in ordered_findings],
        },
    )

    lines = [
        "# Cyberpunk 2077 Compatibility Report",
        "",
        "## Summary",
        "",
        f"- Mods: {summary['mods']}",
        f"- Files: {summary['artifacts']}",
        f"- Indexed archives: {summary['archive_manifests']}",
        f"- Indexed archive members: {summary['archive_members']}",
        f"- ArchiveXL references: {summary['archivexl_references']}",
        f"- TweakXL references: {summary['tweakxl_references']}",
        f"- REDscript references: {summary['redscript_references']}",
        f"- CET references: {summary['cet_references']}",
        "- Findings: " + ", ".join(f"{key}={value}" for key, value in summary["findings"].items()),
        "",
    ]
    if summary["coverage"]:
        lines.extend(["## Analyzer coverage", ""])
        for ecosystem, analyzer in summary["coverage"].items():
            lines.extend([f"### {ecosystem}", "", "#### Sections", ""])
            for section in analyzer.get("sections", []):
                lines.append(
                    f"- `{section['name']}`: {section['status']}; "
                    f"documents={section['documents']} — {section['note']}"
                )
            operations = analyzer.get("resource_operations", [])
            if operations:
                lines.extend(["", "#### Resource operations", ""])
                for operation in operations:
                    lines.append(
                        f"- `{operation['name']}`: {operation['status']}; "
                        f"documents={operation['documents']}; "
                        f"references={operation['references']} — {operation['note']}"
                    )
            override_operations = analyzer.get("override_operations", [])
            if override_operations:
                lines.extend(["", "#### Visual-tag overrides", ""])
                for operation in override_operations:
                    lines.append(
                        f"- `{operation['name']}`: {operation['status']}; "
                        f"documents={operation['documents']}; "
                        f"definitions={operation['definitions']}; "
                        f"components={operation['components']}; "
                        f"chunk references={operation['chunk_references']}; "
                        f"shared/duplicate/conflicting tags="
                        f"{operation['shared_tags']}/{operation['duplicate_tags']}/"
                        f"{operation['conflicting_tags']}; "
                        f"built-in redefinitions={operation['builtin_redefinitions']} - "
                        f"{operation['note']}"
                    )
            player_operations = analyzer.get("player_operations", [])
            if player_operations:
                lines.extend(["", "#### Player body types", ""])
                for operation in player_operations:
                    lines.append(
                        f"- `{operation['name']}`: {operation['status']}; "
                        f"documents={operation['documents']}; "
                        f"registrations={operation['registrations']}; "
                        f"unique/shared body types="
                        f"{operation['unique_body_types']}/"
                        f"{operation['shared_body_types']} - {operation['note']}"
                    )
            streaming_operations = analyzer.get("streaming_operations", [])
            if streaming_operations:
                lines.extend(["", "#### World streaming operations", ""])
                for operation in streaming_operations:
                    lines.append(
                        f"- `{operation['name']}`: {operation['status']}; "
                        f"documents={operation['documents']}; sectors={operation['sectors']}; "
                        f"node mutations={operation['node_mutations']}; "
                        f"element mutations={operation['element_mutations']}; "
                        f"node deletions={operation['node_deletions']}; "
                        f"node/element property writes="
                        f"{operation['node_property_writes']}/"
                        f"{operation['element_property_writes']}; "
                        f"shared mutation nodes={operation['shared_mutation_nodes']} - "
                        f"{operation['note']}"
                    )
            annotation_operations = analyzer.get("annotation_operations", [])
            if annotation_operations:
                lines.extend(["", "#### REDscript annotation operations", ""])
                for operation in annotation_operations:
                    lines.append(
                        f"- `{operation['name']}`: {operation['status']}; "
                        f"documents={operation['documents']}; "
                        f"wrap/replace/add-method/add-field="
                        f"{operation['wrap_methods']}/{operation['replace_methods']}/"
                        f"{operation['add_methods']}/{operation['add_fields']}; "
                        f"inactive conditions={operation['inactive_annotations']}; "
                        f"shared wrapper/replacement signatures="
                        f"{operation['shared_wrapper_signatures']}/"
                        f"{operation['shared_replacement_signatures']} - "
                        f"compatible/terminated wrapper chains="
                        f"{operation['compatible_wrapper_chains']}/"
                        f"{operation['terminated_wrapper_chains']} - "
                        f"{operation['note']}"
                    )
            registration_operations = analyzer.get("registration_operations", [])
            if registration_operations:
                lines.extend(["", "#### CET Lua registrations", ""])
                for operation in registration_operations:
                    lines.append(
                        f"- `{operation['name']}`: {operation['status']}; "
                        f"documents/roots={operation['documents']}/{operation['mod_roots']}; "
                        f"entrypoints/events={operation['entrypoints']}/{operation['events']}; "
                        f"hotkeys/inputs={operation['hotkeys']}/{operation['inputs']}; "
                        f"requires/GetMod={operation['requires']}/{operation['getmod_dependencies']}; "
                        f"observers/overrides={operation['observers']}/{operation['overrides']}; "
                        f"settings={operation['settings']}; dynamic={operation['dynamic_calls']}; "
                        f"missing modules={operation['unresolved_modules']}; "
                        f"shared hooks={operation['shared_hook_targets']} - {operation['note']}"
                    )
            quest_operations = analyzer.get("quest_operations", [])
            if quest_operations:
                lines.extend(["", "#### Quest operations", ""])
                for operation in quest_operations:
                    lines.append(
                        f"- `{operation['name']}`: {operation['status']}; "
                        f"documents={operation['documents']}; "
                        f"declarations={operation['declarations']}; "
                        f"phase own/cross/missing={operation['phase_own']}/"
                        f"{operation['phase_cross_mod']}/{operation['phase_missing']}; "
                        f"parent official/own/cross/missing={operation['parent_official']}/"
                        f"{operation['parent_own']}/{operation['parent_cross_mod']}/"
                        f"{operation['parent_missing']}; "
                        f"unique missing targets={operation['missing_targets']} - "
                        f"{operation['note']}"
                    )
            dependencies = analyzer.get("dependencies", [])
            if dependencies:
                lines.extend(["", "#### Dependency analysis", ""])
                for dependency in dependencies:
                    lines.append(
                        f"- `{dependency['name']}`: {dependency['status']}; "
                        f"references={dependency['references']}; "
                        f"vanilla={dependency['vanilla']}; "
                        f"same-mod={dependency['same_mod']}; "
                        f"cross-mod={dependency['cross_mod']}; "
                        f"case-mismatch={dependency['case_mismatch']}; "
                        f"missing={dependency['missing']}; "
                        f"cycles={dependency['cycles']} — {dependency['note']}"
                    )
            runtime_logs = analyzer.get("runtime_logs", [])
            if runtime_logs:
                lines.extend(["", "#### Runtime log correlation", ""])
                for runtime in runtime_logs:
                    lines.append(
                        f"- `{runtime['name']}`: {runtime['status']}; "
                        f"errors={runtime['errors']}; warnings={runtime['warnings']}; "
                        f"events={runtime['events']}; "
                        f"source-attributed={runtime['correlated_events']}; "
                        f"static-confirmations={runtime['static_confirmations']}; "
                        f"findings={runtime['findings']} — {runtime['note']}"
                    )
                    if runtime.get("log_path"):
                        lines.append(f"  - Log: `{runtime['log_path']}`")
            payloads = analyzer.get("payloads")
            if payloads:
                lines.extend(["", "#### Payload inspection", ""])
                for payload_name, payload_stats in payloads.items():
                    lines.append(f"- **{payload_name}**")
                    for key, value in payload_stats.items():
                        lines.append(f"  - `{key}`: {value}")
            lines.append("")
    lines.extend(["## Findings", ""])
    if not ordered_findings:
        lines.append("No findings.")
    for finding in ordered_findings:
        lines.extend(
            [
                f"### [{finding.severity.upper()}] {finding.rule_id}: {finding.summary}",
                "",
                finding.explanation,
                "",
                "Mods: " + (", ".join(finding.participants) or "n/a"),
                "",
            ]
        )
        displayed_evidence = finding.evidence[:10]
        for evidence in displayed_evidence:
            source = evidence.get("source_path") or evidence.get("path") or evidence.get("archive")
            line = evidence.get("line")
            if source:
                lines.append(f"- Evidence: `{source}`" + (f" (line {line})" if line else ""))
            identity = evidence.get("identity")
            if identity:
                lines.append(f"- Target: `{identity}`")
                nested = evidence.get("references") or []
                for reference in nested[:2]:
                    nested_source = reference.get("source_path")
                    nested_line = reference.get("line")
                    if nested_source:
                        lines.append(
                            f"  - `{nested_source}`"
                            + (f" (line {nested_line})" if nested_line else "")
                        )
        if len(finding.evidence) > len(displayed_evidence):
            remaining = len(finding.evidence) - len(displayed_evidence)
            lines.append(f"- ...and {remaining} more targets in the JSON report.")
        if finding.evidence:
            lines.append("")
    (output_dir / "compatibility-report.md").write_text("\n".join(lines), encoding="utf-8")
    write_html_report(
        output_dir / "compatibility-report.html",
        summary,
        ordered_findings,
        metadata,
    )
