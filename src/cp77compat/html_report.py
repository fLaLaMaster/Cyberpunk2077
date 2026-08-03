from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .models import Finding


def _safe_json(value: Any) -> str:
    """Encode JSON so it cannot terminate its containing script element."""
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def write_html_report(
    path: Path,
    summary: dict[str, Any],
    findings: Iterable[Finding],
    metadata: dict[str, Any],
    stale_acknowledgements: Iterable[dict[str, str]] = (),
) -> None:
    payload = _safe_json(
        {
            "summary": summary,
            "metadata": metadata,
            "findings": [finding.to_dict() for finding in findings],
            "stale_acknowledgements": list(stale_acknowledgements),
        }
    )
    path.write_text(_HTML_TEMPLATE.replace("__REPORT_DATA__", payload), encoding="utf-8")


_HTML_TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Cyberpunk 2077 Compatibility Report</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0b0d10;
      --panel: #14171c;
      --panel-2: #1b1f25;
      --border: #303641;
      --text: #edf0f3;
      --muted: #9ba5b1;
      --accent: #f4e600;
      --error: #ff5252;
      --conflict: #ff7a45;
      --warning: #ffbf47;
      --review: #58a6ff;
      --info: #8b949e;
      --shadow: 0 12px 35px rgba(0, 0, 0, .28);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: radial-gradient(circle at 85% -10%, #262718 0, transparent 32rem), var(--bg);
      color: var(--text);
      font-family: Inter, "Segoe UI", system-ui, sans-serif;
      line-height: 1.45;
    }
    button, input, select, textarea { font: inherit; }
    .shell { width: min(1740px, calc(100% - 24px)); margin: 0 auto; }
    header { padding: 34px 0 22px; }
    .eyebrow { color: var(--accent); font: 700 12px/1.2 Consolas, monospace; letter-spacing: .14em; text-transform: uppercase; }
    h1 { margin: 7px 0 5px; font-size: clamp(27px, 4vw, 44px); letter-spacing: -.035em; }
    .generated { color: var(--muted); font-size: 13px; }
    .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(145px, 1fr)); gap: 10px; margin-top: 22px; }
    .stat { padding: 15px 17px; background: rgba(20, 23, 28, .92); border: 1px solid var(--border); border-radius: 8px; box-shadow: var(--shadow); }
    .stat-value { display: block; font-size: 24px; font-weight: 750; }
    .stat-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
    .coverage-shell { margin-bottom: 18px; }
    .coverage-panel { min-width: 0; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; box-shadow: var(--shadow); }
    .coverage-panel > summary { cursor: pointer; padding: 13px 16px; color: var(--accent); font-weight: 750; }
    .coverage-content, .coverage-group { min-width: 0; }
    .coverage-content { display: grid; gap: 18px; padding: 0 16px 16px; }
    .coverage-group h2 { margin: 4px 0 10px; font-size: 17px; }
    .coverage-group h3 { margin: 14px 0 7px; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
    .coverage-table-wrap { width: 100%; max-width: 100%; overflow-x: auto; border: 1px solid var(--border); border-radius: 6px; }
    .coverage-table { width: 100%; min-width: 720px; border-collapse: collapse; font-size: 12px; }
    .coverage-table th, .coverage-table td { padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--border); vertical-align: top; }
    .coverage-table tr:last-child td { border-bottom: 0; }
    .coverage-table th { color: var(--muted); background: var(--panel-2); text-transform: uppercase; letter-spacing: .06em; font-size: 10px; }
    .coverage-status { display: inline-block; padding: 2px 6px; border: 1px solid var(--border); border-radius: 999px; font: 700 10px/1.4 Consolas, monospace; text-transform: uppercase; }
    .coverage-status[data-status="analyzed"] { color: #59d185; border-color: #326b48; }
    .coverage-status[data-status="partial"] { color: var(--warning); border-color: #79612f; }
    .coverage-status[data-status="unsupported"] { color: var(--muted); }
    .coverage-card-list { display: grid; gap: 10px; }
    .coverage-card { min-width: 0; padding: 13px; background: #101318; border: 1px solid var(--border); border-radius: 6px; }
    .coverage-card h4 { margin: 0 0 11px; color: var(--text); font-size: 14px; }
    .coverage-metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 8px; }
    .coverage-metric { min-width: 0; padding: 8px 9px; background: var(--panel-2); border-radius: 4px; }
    .coverage-metric.wide { grid-column: 1 / -1; }
    .coverage-metric-label { display: block; margin-bottom: 3px; color: var(--muted); font-size: 9px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }
    .coverage-metric-value { display: block; overflow-wrap: anywhere; font-size: 12px; }
    .toolbar-wrap { position: sticky; top: 0; z-index: 10; padding: 10px 0; background: rgba(11, 13, 16, .93); backdrop-filter: blur(12px); border-bottom: 1px solid rgba(48, 54, 65, .75); }
    .toolbar { display: grid; grid-template-columns: repeat(auto-fit, minmax(145px, 1fr)); gap: 9px; align-items: end; }
    .search-field { grid-column: span 2; }
    label { display: block; color: var(--muted); font-size: 11px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; }
    input, select, button, textarea {
      width: 100%; min-height: 40px; margin-top: 5px; padding: 8px 10px;
      color: var(--text); background: var(--panel-2); border: 1px solid var(--border); border-radius: 6px;
    }
    input:focus, select:focus, button:focus, textarea:focus { outline: 2px solid var(--accent); outline-offset: 1px; }
    button { width: auto; cursor: pointer; font-weight: 650; }
    button:hover { border-color: #657080; }
    main { padding: 18px 0 50px; }
    .result-bar, .pager { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: var(--muted); font-size: 13px; }
    .result-bar { margin: 2px 0 12px; }
    .finding-list { display: grid; gap: 10px; }
    .finding {
      --severity-color: var(--info);
      background: var(--panel);
      background: linear-gradient(100deg, color-mix(in srgb, var(--severity-color) 7%, var(--panel)) 0, var(--panel) 28%);
      border: 1px solid var(--border); border-left: 4px solid var(--severity-color); border-radius: 7px; overflow: hidden;
    }
    .finding[data-severity="error"] { --severity-color: var(--error); }
    .finding[data-severity="conflict"] { --severity-color: var(--conflict); }
    .finding[data-severity="warning"] { --severity-color: var(--warning); }
    .finding[data-severity="review"] { --severity-color: var(--review); }
    .finding > summary { cursor: pointer; list-style: none; padding: 14px 16px; }
    .finding > summary::-webkit-details-marker { display: none; }
    .finding > summary::after { content: "+"; float: right; color: var(--muted); font: 22px/1 Consolas, monospace; }
    .finding[open] > summary::after { content: "-"; }
    .finding-title { display: flex; align-items: center; gap: 9px; padding-right: 24px; }
    .badge { color: var(--severity-color); border: 1px solid color-mix(in srgb, var(--severity-color) 65%, transparent); border-radius: 999px; padding: 2px 7px; font: 700 11px/1.4 Consolas, monospace; text-transform: uppercase; }
    .state-badge { color: var(--muted); border: 1px solid var(--border); border-radius: 999px; padding: 2px 7px; font: 700 10px/1.4 Consolas, monospace; text-transform: uppercase; }
    .state-badge[data-status="acknowledged"] { color: #59d185; border-color: #326b48; }
    .state-badge[data-status="stale"] { color: var(--warning); border-color: #79612f; }
    .fingerprint { color: var(--muted); font: 11px/1.45 Consolas, monospace; overflow-wrap: anywhere; }
    .ack-editor { margin-top: 14px; padding: 11px; background: #101318; border: 1px solid var(--border); border-radius: 5px; }
    .ack-editor-row { display: flex; align-items: center; gap: 9px; }
    .ack-editor-row label { display: flex; align-items: center; gap: 7px; color: var(--text); font-size: 12px; letter-spacing: 0; text-transform: none; }
    .ack-toggle { width: 17px; min-height: 17px; margin: 0; padding: 0; accent-color: var(--accent); }
    .ack-note { min-height: 58px; margin-top: 9px; resize: vertical; font-size: 12px; }
    .ack-help { margin-top: 7px; color: var(--muted); font-size: 11px; }
    .toast { position: fixed; right: 18px; bottom: 18px; z-index: 30; max-width: min(420px, calc(100% - 36px)); padding: 11px 14px; color: var(--text); background: #20252d; border: 1px solid var(--border); border-radius: 6px; box-shadow: var(--shadow); }
    .rule { color: var(--muted); font: 600 12px/1.4 Consolas, monospace; }
    .summary { font-weight: 720; }
    .finding-body { padding: 0 16px 16px; border-top: 1px solid var(--border); }
    .explanation { margin: 14px 0; }
    .section-label { margin: 14px 0 6px; color: var(--muted); font-size: 11px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; }
    .chip { padding: 4px 7px; background: #222730; border: 1px solid var(--border); border-radius: 4px; font-size: 12px; }
    .evidence { margin-top: 13px; background: #0e1115; border: 1px solid var(--border); border-radius: 5px; }
    .evidence summary { cursor: pointer; padding: 9px 11px; color: var(--muted); font-size: 12px; }
    pre { max-height: 520px; overflow: auto; margin: 0; padding: 12px; border-top: 1px solid var(--border); color: #c8d1dc; font: 12px/1.5 Consolas, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
    pre a.source-folder-link { color: #8ecbff; text-decoration: underline; text-decoration-style: dotted; text-underline-offset: 2px; }
    pre a.source-folder-link:hover { color: #c8e7ff; text-decoration-style: solid; }
    .pager { justify-content: center; margin-top: 18px; }
    .pager button { min-width: 92px; }
    .empty { padding: 50px 20px; text-align: center; color: var(--muted); border: 1px dashed var(--border); border-radius: 8px; }
    @media (max-width: 900px) {
      .toolbar { grid-template-columns: 1fr 1fr; }
      .search-field { grid-column: 1 / -1; }
    }
    @media (max-width: 560px) {
      .shell { width: min(100% - 18px, 1740px); }
      .toolbar { grid-template-columns: 1fr; }
      .search-field { grid-column: auto; }
      .finding-title { align-items: flex-start; flex-wrap: wrap; }
    }
  </style>
</head>
<body>
  <header class="shell">
    <div class="eyebrow">CP77 / Compatibility Scanner</div>
    <h1>Compatibility Report</h1>
    <div class="generated" id="generated"></div>
    <div class="stats" id="stats"></div>
  </header>

  <section class="shell coverage-shell" id="coverage-shell" hidden>
    <details class="coverage-panel">
      <summary>Analyzer coverage</summary>
      <div class="coverage-content" id="coverage"></div>
    </details>
  </section>

  <div class="toolbar-wrap">
    <div class="shell toolbar">
      <label class="search-field">Search
        <input id="search" type="search" placeholder="Rule, mod, path, sector, explanation..." autocomplete="off">
      </label>
      <label>Severity
        <select id="severity"><option value="">All severities</option></select>
      </label>
      <label>Ecosystem
        <select id="ecosystem"><option value="">All ecosystems</option></select>
      </label>
      <label>Status
        <select id="status"><option value="">All statuses</option></select>
      </label>
      <label>Change
        <select id="change"><option value="">All changes</option></select>
      </label>
      <label>Rule
        <select id="rule"><option value="">All rules</option></select>
      </label>
      <label>Mod
        <select id="mod"><option value="">All mods</option></select>
      </label>
      <button id="clear" type="button">Clear</button>
      <button id="save-acknowledgements" type="button">Save acknowledgements</button>
    </div>
  </div>

  <main class="shell">
    <div class="result-bar">
      <span id="result-count"></span>
      <label>Per page
        <select id="page-size">
          <option>25</option><option selected>50</option><option>100</option><option>250</option>
        </select>
      </label>
    </div>
    <div class="finding-list" id="findings"></div>
    <div class="pager" id="pager">
      <button type="button" id="previous">Previous</button>
      <span id="page-label"></span>
      <button type="button" id="next">Next</button>
    </div>
  </main>
  <div class="toast" id="toast" hidden></div>

  <script id="report-data" type="application/json">__REPORT_DATA__</script>
  <script>
    "use strict";
    const report = JSON.parse(document.getElementById("report-data").textContent);
    const acknowledgementsPath = report.metadata.acknowledgements_file || "acknowledgements.yaml";
    const findings = report.findings;
    const staleAcknowledgements = report.stale_acknowledgements || [];
    const staleItems = staleAcknowledgements.map(item => ({
      rule_id: "ACK-STALE", severity: "info", confidence: "high",
      summary: `Stale acknowledgement: ${String(item.fingerprint || "").slice(0, 16)}`,
      explanation: item.note || "This configured fingerprint no longer matches a current finding.",
      participants: [], evidence: [], fingerprint: item.fingerprint,
      status: "stale", acknowledgement: item.note, change: "stale", _stale: true
    }));
    const reportItems = findings.concat(staleItems);
    const acknowledgementNotes = new Map();
    for (const finding of findings) {
      if (finding.status === "acknowledged") acknowledgementNotes.set(finding.fingerprint, finding.acknowledgement || "Acknowledged from HTML report.");
    }
    for (const item of staleItems) acknowledgementNotes.set(item.fingerprint, item.acknowledgement || "Stale acknowledgement.");
    const severityOrder = ["error", "conflict", "warning", "review", "info"];
    const controls = {
      search: document.getElementById("search"), severity: document.getElementById("severity"),
      ecosystem: document.getElementById("ecosystem"),
      status: document.getElementById("status"), change: document.getElementById("change"),
      rule: document.getElementById("rule"), mod: document.getElementById("mod"),
      pageSize: document.getElementById("page-size")
    };
    let page = 1;

    function evidenceText(evidence) {
      const values = [];
      for (const item of evidence || []) {
        for (const key of ["identity", "source_path", "path", "archive", "mod"]) {
          if (item[key] != null) values.push(String(item[key]));
        }
        for (const ref of item.references || []) {
          values.push(String(ref.source_path || ""), String(ref.mod_name || ""));
        }
        for (const source of item.sources || []) {
          values.push(String(source.source_path || ""), String(source.mod_name || ""));
        }
        for (const operation of item.operation_counts || []) {
          values.push(String(operation.mod_name || ""), String(operation.operation || ""));
        }
        if (item.details) values.push(JSON.stringify(item.details));
      }
      return values.join(" ");
    }

    for (const finding of reportItems) {
      const prefix = String(finding.rule_id || "").split("-", 1)[0];
      finding._ecosystem = ({AXL: "ArchiveXL", TXL: "TweakXL", RS: "REDscript", CET: "CET", XEC: "Cross-ecosystem", CFG: "Configuration", INPUT: "Input mappings", NATIVE: "Native frameworks", ACK: "Acknowledgements", CORE: "Core", WOLVENKIT: "WolvenKit"})[prefix] || "Other";
      finding._search = [finding.rule_id, finding.severity, finding.confidence, finding.summary,
        finding.explanation, ...(finding.participants || []), evidenceText(finding.evidence)]
        .join(" ").toLocaleLowerCase();
    }

    function addOptions(select, values, counts) {
      for (const value of values) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = `${value} (${counts.get(value) || 0})`;
        select.append(option);
      }
    }

    const severityCounts = new Map(), ecosystemCounts = new Map(), statusCounts = new Map(), changeCounts = new Map(), ruleCounts = new Map(), modCounts = new Map();
    for (const finding of reportItems) {
      severityCounts.set(finding.severity, (severityCounts.get(finding.severity) || 0) + 1);
      ecosystemCounts.set(finding._ecosystem, (ecosystemCounts.get(finding._ecosystem) || 0) + 1);
      statusCounts.set(finding.status || "active", (statusCounts.get(finding.status || "active") || 0) + 1);
      changeCounts.set(finding.change || "baseline", (changeCounts.get(finding.change || "baseline") || 0) + 1);
      ruleCounts.set(finding.rule_id, (ruleCounts.get(finding.rule_id) || 0) + 1);
      for (const mod of finding.participants || []) modCounts.set(mod, (modCounts.get(mod) || 0) + 1);
    }
    addOptions(controls.severity, severityOrder.filter(value => severityCounts.has(value)), severityCounts);
    addOptions(controls.ecosystem, [...ecosystemCounts.keys()].sort(), ecosystemCounts);
    addOptions(controls.status, [...statusCounts.keys()].sort(), statusCounts);
    addOptions(controls.change, [...changeCounts.keys()].sort(), changeCounts);
    addOptions(controls.rule, [...ruleCounts.keys()].sort(), ruleCounts);
    addOptions(controls.mod, [...modCounts.keys()].sort((a, b) => a.localeCompare(b)), modCounts);

    const summary = report.summary;
    const coverage = summary.coverage || {};
    const coverageShell = document.getElementById("coverage-shell");
    const coverageElement = document.getElementById("coverage");
    const coveragePanel = document.querySelector(".coverage-panel");

    function coverageTable(rows, columns) {
      const wrap = document.createElement("div"); wrap.className = "coverage-table-wrap";
      const table = document.createElement("table"); table.className = "coverage-table";
      const head = document.createElement("thead"), headRow = document.createElement("tr");
      for (const column of columns) {
        const th = document.createElement("th"); th.textContent = column.label; headRow.append(th);
      }
      head.append(headRow); table.append(head);
      const body = document.createElement("tbody");
      for (const row of rows) {
        const tr = document.createElement("tr");
        for (const column of columns) {
          const td = document.createElement("td");
          if (column.key === "status") {
            const status = document.createElement("span"); status.className = "coverage-status";
            status.dataset.status = row.status; status.textContent = row.status; td.append(status);
          } else {
            td.textContent = row[column.key] == null ? "" : String(row[column.key]);
          }
          tr.append(td);
        }
        body.append(tr);
      }
      table.append(body); wrap.append(table); return wrap;
    }

    function coverageCards(rows, columns) {
      const list = document.createElement("div"); list.className = "coverage-card-list";
      for (const row of rows) {
        const card = document.createElement("article"); card.className = "coverage-card";
        const nameColumn = columns.find(column => column.key === "name");
        if (nameColumn && row.name != null) {
          const heading = document.createElement("h4"); heading.textContent = String(row.name); card.append(heading);
        }
        const metrics = document.createElement("div"); metrics.className = "coverage-metrics";
        for (const column of columns) {
          if (column.key === "name") continue;
          const value = row[column.key];
          if (value == null || value === "") continue;
          const metric = document.createElement("div"); metric.className = "coverage-metric";
          if (column.wide) metric.classList.add("wide");
          const label = document.createElement("span"); label.className = "coverage-metric-label"; label.textContent = column.label;
          const content = document.createElement("span"); content.className = "coverage-metric-value";
          if (column.key === "status") {
            const status = document.createElement("span"); status.className = "coverage-status";
            status.dataset.status = value; status.textContent = value; content.append(status);
          } else {
            content.textContent = String(value);
          }
          metric.append(label, content); metrics.append(metric);
        }
        card.append(metrics); list.append(card);
      }
      return list;
    }

    for (const [ecosystem, analyzer] of Object.entries(coverage)) {
      coverageShell.hidden = false;
      const group = document.createElement("section"); group.className = "coverage-group";
      const heading = document.createElement("h2");
      heading.textContent = `${ecosystem} · ${Number(analyzer.documents || 0).toLocaleString()} documents`;
      group.append(heading);
      if ((analyzer.sections || []).length) {
        const label = document.createElement("h3"); label.textContent = "Top-level sections"; group.append(label);
        group.append(coverageTable(analyzer.sections, [
          {key: "name", label: "Section"}, {key: "documents", label: "Documents"},
          {key: "status", label: "Status"}, {key: "note", label: "Coverage note"}
        ]));
      }
      if ((analyzer.resource_operations || []).length) {
        const label = document.createElement("h3"); label.textContent = "Resource operations"; group.append(label);
        group.append(coverageTable(analyzer.resource_operations, [
          {key: "name", label: "Operation"}, {key: "documents", label: "Documents"},
          {key: "references", label: "References"}, {key: "status", label: "Status"},
          {key: "note", label: "Coverage note"}
        ]));
      }
      if ((analyzer.override_operations || []).length) {
        const label = document.createElement("h3"); label.textContent = "Visual-tag overrides"; group.append(label);
        group.append(coverageTable(analyzer.override_operations, [
          {key: "name", label: "Operation"}, {key: "status", label: "Status"},
          {key: "documents", label: "Documents"}, {key: "definitions", label: "Tag definitions"},
          {key: "components", label: "Components"}, {key: "chunk_references", label: "Chunk references"},
          {key: "shared_tags", label: "Shared tags"}, {key: "duplicate_tags", label: "Duplicates"},
          {key: "conflicting_tags", label: "Conflicts"},
          {key: "builtin_redefinitions", label: "Built-in redefinitions"},
          {key: "note", label: "Coverage note"}
        ]));
      }
      if ((analyzer.player_operations || []).length) {
        const label = document.createElement("h3"); label.textContent = "Player body types"; group.append(label);
        group.append(coverageTable(analyzer.player_operations, [
          {key: "name", label: "Operation"}, {key: "status", label: "Status"},
          {key: "documents", label: "Documents"}, {key: "registrations", label: "Registrations"},
          {key: "unique_body_types", label: "Unique"}, {key: "shared_body_types", label: "Shared"},
          {key: "note", label: "Notes"}
        ]));
      }
      if ((analyzer.streaming_operations || []).length) {
        const label = document.createElement("h3"); label.textContent = "World streaming operations"; group.append(label);
        group.append(coverageTable(analyzer.streaming_operations, [
          {key: "name", label: "Operation"}, {key: "status", label: "Status"},
          {key: "documents", label: "Documents"}, {key: "sectors", label: "Sectors"},
          {key: "node_mutations", label: "Node mutations"},
          {key: "element_mutations", label: "Element mutations"},
          {key: "node_deletions", label: "Node deletions"},
          {key: "node_property_writes", label: "Node writes"},
          {key: "element_property_writes", label: "Element writes"},
          {key: "shared_mutation_nodes", label: "Shared mutation nodes"},
          {key: "note", label: "Notes"}
        ]));
      }
      if ((analyzer.annotation_operations || []).length) {
        const label = document.createElement("h3"); label.textContent = "REDscript annotation operations"; group.append(label);
        group.append(coverageTable(analyzer.annotation_operations, [
          {key: "name", label: "Analyzer"}, {key: "status", label: "Status"},
          {key: "documents", label: "Documents"}, {key: "wrap_methods", label: "Wrappers"},
          {key: "replace_methods", label: "Replacements"}, {key: "add_methods", label: "Added methods"},
          {key: "add_fields", label: "Added fields"},
          {key: "inactive_annotations", label: "Inactive conditions"},
          {key: "shared_wrapper_signatures", label: "Shared wrappers"},
          {key: "shared_replacement_signatures", label: "Shared replacements"},
          {key: "compatible_wrapper_chains", label: "Compatible chains"},
          {key: "terminated_wrapper_chains", label: "Terminated chains"},
          {key: "note", label: "Notes"}
        ]));
      }
      if ((analyzer.registration_operations || []).length) {
        const label = document.createElement("h3"); label.textContent = "CET Lua registrations"; group.append(label);
        group.append(coverageCards(analyzer.registration_operations, [
          {key: "name", label: "Analyzer"}, {key: "status", label: "Status"},
          {key: "documents", label: "Lua files"}, {key: "mod_roots", label: "Mod roots"},
          {key: "entrypoints", label: "Entrypoints"}, {key: "events", label: "Events"},
          {key: "hotkeys", label: "Hotkeys"}, {key: "inputs", label: "Inputs"},
          {key: "requires", label: "Requires"}, {key: "getmod_dependencies", label: "GetMod"},
          {key: "observers", label: "Observers"}, {key: "overrides", label: "Overrides"},
          {key: "settings", label: "Settings IDs"}, {key: "global_writes", label: "Global writes"},
          {key: "merged_roots", label: "Merged roots"}, {key: "shared_globals", label: "Shared globals"},
          {key: "dynamic_globals", label: "Dynamic globals"}, {key: "dynamic_calls", label: "Dynamic calls"},
          {key: "unresolved_modules", label: "Missing modules"},
          {key: "shared_hook_targets", label: "Shared hooks"},
          {key: "inactive_references", label: "Inactive refs"}, {key: "note", label: "Notes", wide: true}
        ]));
      }
      if ((analyzer.cross_ecosystem_operations || []).length) {
        const label = document.createElement("h3"); label.textContent = "Cross-ecosystem method hooks"; group.append(label);
        group.append(coverageCards(analyzer.cross_ecosystem_operations, [
          {key: "name", label: "Analyzer"}, {key: "status", label: "Status"},
          {key: "documents", label: "Documents"},
          {key: "cet_hook_targets", label: "CET targets"},
          {key: "redscript_method_targets", label: "REDscript targets"},
          {key: "candidate_targets", label: "Candidates"},
          {key: "matched_targets", label: "Matched"},
          {key: "cross_package_targets", label: "Cross-package"},
          {key: "same_package_targets", label: "Same package"},
          {key: "exact_signature_targets", label: "Full signature"},
          {key: "ambiguous_targets", label: "Short-name ambiguous"},
          {key: "signature_mismatches", label: "Signature mismatches"},
          {key: "observer_targets", label: "Observer targets"},
          {key: "chained_override_targets", label: "Chained overrides"},
          {key: "uncertain_override_targets", label: "Uncertain overrides"},
          {key: "terminating_override_targets", label: "Terminating overrides"},
          {key: "dynamic_hooks", label: "Dynamic hooks"},
          {key: "findings", label: "Findings"},
          {key: "note", label: "Coverage note", wide: true}
        ]));
      }
      if ((analyzer.configuration_formats || []).length) {
        const label = document.createElement("h3"); label.textContent = "Configuration formats"; group.append(label);
        group.append(coverageTable(analyzer.configuration_formats, [
          {key: "name", label: "Format"}, {key: "status", label: "Status"},
          {key: "documents", label: "Documents"}, {key: "parsed", label: "Parsed"},
          {key: "failed", label: "Failed"}, {key: "entries", label: "Entries"},
          {key: "non_utf8", label: "Non-UTF-8"}, {key: "duplicate_keys", label: "Duplicate keys"},
          {key: "note", label: "Notes"}
        ]));
      }
      if ((analyzer.ownership_operations || []).length) {
        const label = document.createElement("h3"); label.textContent = "Configuration ownership"; group.append(label);
        group.append(coverageTable(analyzer.ownership_operations, [
          {key: "name", label: "Analyzer"}, {key: "status", label: "Status"},
          {key: "documents", label: "Documents"}, {key: "active_documents", label: "Active"},
          {key: "scopes", label: "Scopes"}, {key: "shared_scopes", label: "Shared scopes"},
          {key: "shared_paths", label: "Shared paths"}, {key: "references", label: "References"},
          {key: "note", label: "Notes"}
        ]));
      }
      if ((analyzer.input_operations || []).length) {
        const label = document.createElement("h3"); label.textContent = "Input Loader mappings"; group.append(label);
        group.append(coverageTable(analyzer.input_operations, [
          {key: "name", label: "Analyzer"}, {key: "status", label: "Status"},
          {key: "documents", label: "Documents"}, {key: "active_documents", label: "Active"},
          {key: "references", label: "References"}, {key: "top_level_nodes", label: "Top-level nodes"},
          {key: "mappings", label: "Mappings"}, {key: "contexts", label: "Contexts"},
          {key: "action_policies", label: "Action policies"},
          {key: "baseline_overwrites", label: "Base overwrites"}, {key: "baseline_appends", label: "Base appends"},
          {key: "shared_append_nodes", label: "Shared appends"}, {key: "competing_nodes", label: "Competing nodes"},
          {key: "missing_targets", label: "Missing targets"}, {key: "cache_mismatches", label: "Cache mismatches"},
          {key: "note", label: "Notes"}
        ]));
      }
      if ((analyzer.native_operations || []).length) {
        const label = document.createElement("h3"); label.textContent = "Native binaries and dependencies"; group.append(label);
        group.append(coverageTable(analyzer.native_operations, [
          {key: "name", label: "Analyzer"}, {key: "status", label: "Status"},
          {key: "documents", label: "Binaries"}, {key: "active_documents", label: "Active"},
          {key: "references", label: "References"}, {key: "plugin_binaries", label: "Plugin DLLs"},
          {key: "loaded_plugins", label: "Loaded"}, {key: "companion_libraries", label: "Companions"},
          {key: "imports", label: "Imports"}, {key: "non_system_imports", label: "Game-local imports"},
          {key: "missing_imports", label: "Missing imports"}, {key: "shared_paths", label: "Shared paths"},
          {key: "deployment_mismatches", label: "Deployment mismatches"}, {key: "note", label: "Notes"}
        ]));
      }
      if ((analyzer.native_plugins || []).length) {
        const label = document.createElement("h3"); label.textContent = "RED4ext plugins"; group.append(label);
        group.append(coverageTable(analyzer.native_plugins, [
          {key: "name", label: "Plugin"}, {key: "runtime_state", label: "Runtime state"},
          {key: "runtime_version", label: "Runtime version"}, {key: "file_version", label: "File version"},
          {key: "binary", label: "Binary"}, {key: "imports", label: "Imports"},
          {key: "non_system_imports", label: "Game-local imports"},
          {key: "deployment_match", label: "Deployment match"}, {key: "note", label: "Notes"}
        ]));
      }
      if ((analyzer.framework_versions || []).length) {
        const label = document.createElement("h3"); label.textContent = "Native framework versions"; group.append(label);
        group.append(coverageTable(analyzer.framework_versions, [
          {key: "name", label: "Framework"}, {key: "status", label: "Status"},
          {key: "version", label: "Version"}, {key: "game_product_version", label: "Game product"},
          {key: "game_file_version", label: "Game executable"}, {key: "log_path", label: "Selected log"},
          {key: "note", label: "Notes"}
        ]));
      }
      if ((analyzer.framework_logs || []).length) {
        const label = document.createElement("h3"); label.textContent = "Native plugin logs"; group.append(label);
        group.append(coverageTable(analyzer.framework_logs, [
          {key: "name", label: "Plugin"}, {key: "status", label: "Status"},
          {key: "files", label: "Files"}, {key: "lines", label: "Lines"},
          {key: "errors", label: "Errors"}, {key: "warnings", label: "Warnings"},
          {key: "delegated_to", label: "Delegated analyzer"}, {key: "log_path", label: "Selected log"},
          {key: "note", label: "Notes"}
        ]));
      }
      if ((analyzer.quest_operations || []).length) {
        const label = document.createElement("h3"); label.textContent = "Quest operations"; group.append(label);
        group.append(coverageTable(analyzer.quest_operations, [
          {key: "name", label: "Operation"}, {key: "status", label: "Status"},
          {key: "documents", label: "Documents"}, {key: "declarations", label: "Merges"},
          {key: "phase_own", label: "Child: own"}, {key: "phase_cross_mod", label: "Child: cross-mod"},
          {key: "phase_missing", label: "Child: missing"}, {key: "parent_official", label: "Parent: official"},
          {key: "parent_own", label: "Parent: own"}, {key: "parent_cross_mod", label: "Parent: cross-mod"},
          {key: "parent_missing", label: "Parent: missing"}, {key: "missing_targets", label: "Missing targets"},
          {key: "note", label: "Coverage note"}
        ]));
      }
      if ((analyzer.dependencies || []).length) {
        const label = document.createElement("h3"); label.textContent = "Dependency analysis"; group.append(label);
        group.append(coverageTable(analyzer.dependencies, [
          {key: "name", label: "Analyzer"}, {key: "references", label: "References"},
          {key: "vanilla", label: "Vanilla"}, {key: "same_mod", label: "Same mod"},
          {key: "cross_mod", label: "Cross-mod"}, {key: "case_mismatch", label: "Case mismatch"},
          {key: "missing", label: "Missing"},
          {key: "cycles", label: "Cycles"}, {key: "status", label: "Status"},
          {key: "note", label: "Coverage note"}
        ]));
      }
      if ((analyzer.runtime_logs || []).length) {
        const label = document.createElement("h3"); label.textContent = "Runtime log correlation"; group.append(label);
        group.append(coverageCards(analyzer.runtime_logs, [
          {key: "name", label: "Log analyzer"}, {key: "status", label: "Status"},
          {key: "session", label: "Session"}, {key: "files", label: "Files"},
          {key: "compiled_files", label: "Compiled files"},
          {key: "bytes", label: "Bytes"},
          {key: "lines", label: "Lines"}, {key: "errors", label: "Errors"},
          {key: "warnings", label: "Warnings"}, {key: "events", label: "Events"},
          {key: "correlated_events", label: "Source-attributed"},
          {key: "static_confirmations", label: "Static confirmations"},
          {key: "findings", label: "Findings"}, {key: "log_path", label: "Selected log", wide: true},
          {key: "note", label: "Coverage note", wide: true}
        ]));
      }
      if (analyzer.payloads) {
        const label = document.createElement("h3"); label.textContent = "Payload inspection"; group.append(label);
        const payloadRows = [];
        for (const [name, payload] of Object.entries(analyzer.payloads)) {
          payloadRows.push({
            name, declarations: payload.declarations,
            unique: payload.unique_archive_payloads, serialized: payload.serialized,
            skipped: payload.skipped_without_own_archive, failed: payload.failed,
            references: payload.entry_references,
            groups: payload.group_entries,
            options: payload.option_references,
            choices: payload.choice_references,
            extractionHits: payload.extraction_cache_hits,
            serializationHits: payload.serialization_cache_hits,
            verified: payload.verified_targets,
            crossMod: payload.cross_mod_targets,
            missing: payload.missing_targets,
            disjoint: payload.composable_entries ?? payload.disjoint_targets,
            duplicate: payload.duplicate_entries ?? payload.duplicate_targets,
            conflicting: payload.conflicting_entries ?? payload.conflicting_targets,
            review: payload.review_entries,
            uninspected: payload.uninspected_targets
          });
        }
        group.append(coverageTable(payloadRows, [
          {key: "name", label: "Analyzer"}, {key: "declarations", label: "Declarations"},
          {key: "unique", label: "Unique payloads"}, {key: "serialized", label: "Serialized"},
          {key: "skipped", label: "Skipped"}, {key: "failed", label: "Failures"},
          {key: "references", label: "References"}, {key: "extractionHits", label: "Extraction hits"},
          {key: "groups", label: "Group entries"}, {key: "options", label: "Options"},
          {key: "choices", label: "Choices"},
          {key: "serializationHits", label: "Serialization hits"},
          {key: "verified", label: "Targets verified"}, {key: "crossMod", label: "Cross-mod targets"},
          {key: "missing", label: "Missing targets"}, {key: "disjoint", label: "Composable identities"},
          {key: "duplicate", label: "Duplicate identities"}, {key: "conflicting", label: "Conflicting identities"},
          {key: "review", label: "Review identities"}, {key: "uninspected", label: "Uninspected identities"}
        ]));
      }
      coverageElement.append(group);
    }
    const stats = [
      [summary.mods, "Mods"], [summary.artifacts, "Files"],
      [summary.archive_manifests, "Archives"], [summary.archive_members, "Archive members"],
      [summary.archivexl_references, "ArchiveXL references"],
      [summary.tweakxl_references, "TweakXL references"],
      [summary.redscript_references, "REDscript references"],
      [summary.cet_references, "CET references"],
      [summary.config_references, "Configuration files"],
      [summary.input_references, "Input references"],
      [summary.native_references, "Native references"],
      [summary.cross_ecosystem_findings, "Cross-ecosystem"],
      [summary.finding_states?.active, "Active findings", "active"],
      [summary.finding_states?.acknowledged, "Acknowledged", "acknowledged"],
      [findings.length, "Findings"]
    ];
    const statsElement = document.getElementById("stats");
    for (const [value, label, stateKey] of stats) {
      const card = document.createElement("div"); card.className = "stat";
      if (stateKey) card.dataset.stateCount = stateKey;
      const number = document.createElement("span"); number.className = "stat-value";
      number.textContent = Number(value || 0).toLocaleString();
      const caption = document.createElement("span"); caption.className = "stat-label"; caption.textContent = label;
      card.append(number, caption); statsElement.append(card);
    }
    const generated = report.metadata.generated_at ? new Date(report.metadata.generated_at).toLocaleString() : "unknown";
    document.getElementById("generated").textContent = `Generated ${generated} · Scanner ${report.metadata.scanner_version || "unknown"} · Archive scope ${report.metadata.archive_scope || "unknown"}`;

    function filteredFindings() {
      const query = controls.search.value.trim().toLocaleLowerCase();
      return reportItems.filter(finding => !finding._removed &&
        (!query || finding._search.includes(query)) &&
        (!controls.severity.value || finding.severity === controls.severity.value) &&
        (!controls.ecosystem.value || finding._ecosystem === controls.ecosystem.value) &&
        (!controls.status.value || (finding.status || "active") === controls.status.value) &&
        (!controls.change.value || (finding.change || "baseline") === controls.change.value) &&
        (!controls.rule.value || finding.rule_id === controls.rule.value) &&
        (!controls.mod.value || (finding.participants || []).includes(controls.mod.value))
      );
    }

    function sourceFolderUrl(sourcePath) {
      if (typeof sourcePath !== "string") return null;
      const normalized = sourcePath.replaceAll("\\", "/");
      const separator = normalized.lastIndexOf("/");
      if (separator < 0) return null;
      const folder = normalized.slice(0, separator);
      const drive = folder.match(/^([A-Za-z]:)(?:\/(.*))?$/);
      if (drive) {
        const rest = (drive[2] || "").split("/").filter(Boolean).map(encodeURIComponent).join("/");
        return `file:///${drive[1]}/${rest}${rest ? "/" : ""}`;
      }
      if (folder.startsWith("//")) {
        const parts = folder.slice(2).split("/").filter(Boolean);
        if (parts.length < 2) return null;
        const host = encodeURIComponent(parts.shift());
        const path = parts.map(encodeURIComponent).join("/");
        return `file://${host}/${path}${path ? "/" : ""}`;
      }
      return null;
    }

    function evidencePre(value) {
      const serialized = JSON.stringify(value, null, 2);
      const pre = document.createElement("pre");
      const sourcePattern = /("source_path"\s*:\s*)("(?:\\.|[^"\\])*")/g;
      let cursor = 0;
      for (const match of serialized.matchAll(sourcePattern)) {
        pre.append(document.createTextNode(serialized.slice(cursor, match.index) + match[1]));
        let sourcePath = null;
        try { sourcePath = JSON.parse(match[2]); } catch (_error) { /* keep malformed text unlinked */ }
        const folderUrl = sourceFolderUrl(sourcePath);
        if (folderUrl) {
          const link = document.createElement("a");
          link.className = "source-folder-link";
          link.href = folderUrl;
          link.target = "_blank";
          link.rel = "noopener";
          link.title = `Open parent folder: ${sourcePath.slice(0, Math.max(sourcePath.lastIndexOf("\\"), sourcePath.lastIndexOf("/")))}`;
          link.textContent = match[2];
          pre.append(link);
        } else {
          pre.append(document.createTextNode(match[2]));
        }
        cursor = match.index + match[0].length;
      }
      pre.append(document.createTextNode(serialized.slice(cursor)));
      return pre;
    }

    function findingElement(finding) {
      const details = document.createElement("details"); details.className = "finding";
      details.dataset.severity = finding.severity;
      details.dataset.status = finding.status || "active";
      const heading = document.createElement("summary");
      const title = document.createElement("div"); title.className = "finding-title";
      const badge = document.createElement("span"); badge.className = "badge"; badge.textContent = finding.severity;
      const rule = document.createElement("span"); rule.className = "rule"; rule.textContent = finding.rule_id;
      const state = document.createElement("span"); state.className = "state-badge";
      state.dataset.status = finding.status || "active";
      state.textContent = `${finding.status || "active"} · ${finding.change || "baseline"}`;
      const summary = document.createElement("span"); summary.className = "summary"; summary.textContent = finding.summary;
      title.append(badge, rule, state, summary); heading.append(title);
      const body = document.createElement("div"); body.className = "finding-body";
      const explanation = document.createElement("div"); explanation.className = "explanation"; explanation.textContent = finding.explanation;
      body.append(explanation);
      if (finding.acknowledgement) {
        const label = document.createElement("div"); label.className = "section-label"; label.textContent = "Acknowledgement";
        const note = document.createElement("div"); note.textContent = finding.acknowledgement;
        body.append(label, note);
      }
      if (finding.fingerprint) {
        const label = document.createElement("div"); label.className = "section-label"; label.textContent = "Fingerprint";
        const fingerprint = document.createElement("div"); fingerprint.className = "fingerprint"; fingerprint.textContent = finding.fingerprint;
        body.append(label, fingerprint);
      }
      if (finding.fingerprint) {
        const editor = document.createElement("div"); editor.className = "ack-editor";
        const row = document.createElement("div"); row.className = "ack-editor-row";
        const toggleLabel = document.createElement("label");
        const toggle = document.createElement("input"); toggle.type = "checkbox"; toggle.className = "ack-toggle";
        toggle.checked = acknowledgementNotes.has(finding.fingerprint);
        const toggleText = document.createElement("span");
        toggleText.textContent = finding._stale ? "Keep this stale acknowledgement" : "Acknowledge this finding";
        toggleLabel.append(toggle, toggleText); row.append(toggleLabel);
        const note = document.createElement("textarea"); note.className = "ack-note"; note.rows = 2;
        note.placeholder = "Why is this finding expected?";
        note.value = acknowledgementNotes.get(finding.fingerprint) || "";
        note.disabled = !toggle.checked;
        const help = document.createElement("div"); help.className = "ack-help";
        help.textContent = `Changes apply immediately. Save the YAML to the configured path: ${acknowledgementsPath}`;
        toggle.addEventListener("change", () => {
          if (toggle.checked) {
            const value = note.value.trim() || "Acknowledged from HTML report.";
            acknowledgementNotes.set(finding.fingerprint, value);
            finding.acknowledgement = value;
            finding.status = finding._stale ? "stale" : "acknowledged";
            note.value = value; note.disabled = false;
          } else {
            acknowledgementNotes.delete(finding.fingerprint);
            finding.acknowledgement = null;
            if (finding._stale) finding._removed = true;
            else finding.status = "active";
          }
          page = 1; updateStateCounts(); render();
        });
        note.addEventListener("input", () => {
          if (!toggle.checked) return;
          const value = note.value.trim();
          if (value) {
            acknowledgementNotes.set(finding.fingerprint, value);
            finding.acknowledgement = value;
          }
        });
        note.addEventListener("blur", () => {
          if (!toggle.checked || note.value.trim()) return;
          note.value = "Acknowledged from HTML report.";
          acknowledgementNotes.set(finding.fingerprint, note.value);
          finding.acknowledgement = note.value;
        });
        editor.append(row, note, help); body.append(editor);
      }
      if ((finding.participants || []).length) {
        const label = document.createElement("div"); label.className = "section-label"; label.textContent = "Mods";
        const chips = document.createElement("div"); chips.className = "chips";
        for (const mod of finding.participants) {
          const chip = document.createElement("span"); chip.className = "chip"; chip.textContent = mod; chips.append(chip);
        }
        body.append(label, chips);
      }
      if ((finding.evidence || []).length) {
        const evidence = document.createElement("details"); evidence.className = "evidence";
        const evidenceSummary = document.createElement("summary");
        evidenceSummary.textContent = `Evidence (${finding.evidence.length})`;
        evidence.append(evidenceSummary);
        evidence.addEventListener("toggle", () => {
          if (evidence.open && !evidence.dataset.loaded) {
            evidence.append(evidencePre(finding.evidence)); evidence.dataset.loaded = "true";
          }
        });
        body.append(evidence);
      }
      details.append(heading, body);
      return details;
    }

    function render() {
      const filtered = filteredFindings();
      const pageSize = Number(controls.pageSize.value);
      const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
      page = Math.min(Math.max(page, 1), pageCount);
      const start = (page - 1) * pageSize;
      const visible = filtered.slice(start, start + pageSize);
      const list = document.getElementById("findings"); list.replaceChildren();
      if (!visible.length) {
        const empty = document.createElement("div"); empty.className = "empty";
        empty.textContent = "No findings match the current filters."; list.append(empty);
      } else {
        const fragment = document.createDocumentFragment();
        for (const finding of visible) fragment.append(findingElement(finding));
        list.append(fragment);
      }
      document.getElementById("result-count").textContent = `${filtered.length.toLocaleString()} of ${reportItems.length.toLocaleString()} report items (${findings.length.toLocaleString()} current findings)`;
      document.getElementById("page-label").textContent = `Page ${page} of ${pageCount}`;
      document.getElementById("previous").disabled = page <= 1;
      document.getElementById("next").disabled = page >= pageCount;
      document.getElementById("pager").hidden = filtered.length <= pageSize;
    }

    function updateStateCounts() {
      const active = findings.filter(finding => finding.status === "active").length;
      const acknowledged = findings.filter(finding => finding.status === "acknowledged").length;
      const counts = {active, acknowledged, stale: staleItems.filter(item => !item._removed).length};
      for (const card of document.querySelectorAll("[data-state-count]")) {
        card.querySelector(".stat-value").textContent = Number(counts[card.dataset.stateCount] || 0).toLocaleString();
      }
      for (const option of controls.status.options) {
        if (!option.value || counts[option.value] == null) continue;
        option.textContent = `${option.value} (${counts[option.value]})`;
      }
    }

    function acknowledgementsYaml() {
      const entries = [...acknowledgementNotes.entries()].sort((a, b) => a[0].localeCompare(b[0]));
      if (!entries.length) return "version: 1\n\nacknowledgements: []\n";
      const lines = ["version: 1", "", "acknowledgements:"];
      for (const [fingerprint, note] of entries) {
        lines.push(`  - fingerprint: ${fingerprint}`, `    note: ${JSON.stringify(note)}`);
      }
      return lines.join("\n") + "\n";
    }

    function showToast(message) {
      const toast = document.getElementById("toast"); toast.textContent = message; toast.hidden = false;
      clearTimeout(showToast.timer); showToast.timer = setTimeout(() => { toast.hidden = true; }, 5000);
    }

    function downloadAcknowledgements(yaml) {
      const blob = new Blob([yaml], {type: "application/yaml;charset=utf-8"});
      const url = URL.createObjectURL(blob), anchor = document.createElement("a");
      anchor.href = url; anchor.download = "acknowledgements.yaml"; anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      showToast("Downloaded acknowledgements.yaml. Replace the configured file before the next scan.");
    }

    async function saveAcknowledgements() {
      const yaml = acknowledgementsYaml();
      if (window.showSaveFilePicker) {
        try {
          const handle = await window.showSaveFilePicker({
            suggestedName: "acknowledgements.yaml",
            types: [{description: "YAML acknowledgements", accept: {"application/yaml": [".yaml", ".yml"]}}]
          });
          const writable = await handle.createWritable(); await writable.write(yaml); await writable.close();
          showToast(`Acknowledgements saved. Configured scanner path: ${acknowledgementsPath}`);
          return;
        } catch (error) {
          if (error && error.name === "AbortError") return;
        }
      }
      downloadAcknowledgements(yaml);
    }

    const hashKeys = ["search", "severity", "ecosystem", "status", "change", "rule", "mod", "pageSize"];
    function readHash() {
      const values = new URLSearchParams(location.hash.slice(1));
      for (const key of hashKeys) {
        if (!values.has(key)) continue;
        const value = values.get(key);
        if (key === "search" || [...controls[key].options].some(option => option.value === value)) controls[key].value = value;
      }
      coveragePanel.open = values.get("coverage") === "open";
    }
    function writeHash() {
      const values = new URLSearchParams();
      for (const key of hashKeys) {
        const value = controls[key].value;
        if (value && !(key === "pageSize" && value === "50")) values.set(key, value);
      }
      if (coveragePanel.open) values.set("coverage", "open");
      const next = values.toString();
      const base = location.href.split("#", 1)[0];
      history.replaceState(null, "", base + (next ? `#${next}` : ""));
    }
    readHash();
    coveragePanel.addEventListener("toggle", writeHash);
    for (const control of Object.values(controls)) control.addEventListener("input", () => { page = 1; writeHash(); render(); });
    document.getElementById("clear").addEventListener("click", () => {
      controls.search.value = ""; controls.severity.value = ""; controls.ecosystem.value = "";
      controls.status.value = ""; controls.change.value = ""; controls.rule.value = "";
      controls.mod.value = ""; page = 1; writeHash(); render();
    });
    document.getElementById("save-acknowledgements").addEventListener("click", saveAcknowledgements);
    document.getElementById("previous").addEventListener("click", () => { page--; render(); scrollTo({top: 0, behavior: "smooth"}); });
    document.getElementById("next").addEventListener("click", () => { page++; render(); scrollTo({top: 0, behavior: "smooth"}); });
    document.addEventListener("keydown", event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase() === "k") {
        event.preventDefault(); controls.search.focus();
      }
    });
    render();
  </script>
</body>
</html>
'''
