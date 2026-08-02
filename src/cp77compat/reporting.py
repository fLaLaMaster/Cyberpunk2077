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
    findings: list[Finding],
    metadata: dict[str, Any],
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
        "findings": dict(sorted(Counter(item.severity for item in ordered_findings).items())),
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
        "- Findings: " + ", ".join(f"{key}={value}" for key, value in summary["findings"].items()),
        "",
        "## Findings",
        "",
    ]
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
