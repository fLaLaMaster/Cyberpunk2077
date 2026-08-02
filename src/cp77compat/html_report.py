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
) -> None:
    payload = _safe_json(
        {
            "summary": summary,
            "metadata": metadata,
            "findings": [finding.to_dict() for finding in findings],
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
    button, input, select { font: inherit; }
    .shell { width: min(1500px, calc(100% - 32px)); margin: 0 auto; }
    header { padding: 34px 0 22px; }
    .eyebrow { color: var(--accent); font: 700 12px/1.2 Consolas, monospace; letter-spacing: .14em; text-transform: uppercase; }
    h1 { margin: 7px 0 5px; font-size: clamp(27px, 4vw, 44px); letter-spacing: -.035em; }
    .generated { color: var(--muted); font-size: 13px; }
    .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(145px, 1fr)); gap: 10px; margin-top: 22px; }
    .stat { padding: 15px 17px; background: rgba(20, 23, 28, .92); border: 1px solid var(--border); border-radius: 8px; box-shadow: var(--shadow); }
    .stat-value { display: block; font-size: 24px; font-weight: 750; }
    .stat-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
    .toolbar-wrap { position: sticky; top: 0; z-index: 10; padding: 10px 0; background: rgba(11, 13, 16, .93); backdrop-filter: blur(12px); border-bottom: 1px solid rgba(48, 54, 65, .75); }
    .toolbar { display: grid; grid-template-columns: minmax(260px, 2fr) repeat(3, minmax(145px, 1fr)) auto; gap: 9px; align-items: end; }
    label { display: block; color: var(--muted); font-size: 11px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; }
    input, select, button {
      width: 100%; min-height: 40px; margin-top: 5px; padding: 8px 10px;
      color: var(--text); background: var(--panel-2); border: 1px solid var(--border); border-radius: 6px;
    }
    input:focus, select:focus, button:focus { outline: 2px solid var(--accent); outline-offset: 1px; }
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
    .pager { justify-content: center; margin-top: 18px; }
    .pager button { min-width: 92px; }
    .empty { padding: 50px 20px; text-align: center; color: var(--muted); border: 1px dashed var(--border); border-radius: 8px; }
    @media (max-width: 900px) {
      .toolbar { grid-template-columns: 1fr 1fr; }
      .search-field { grid-column: 1 / -1; }
    }
    @media (max-width: 560px) {
      .shell { width: min(100% - 18px, 1500px); }
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

  <div class="toolbar-wrap">
    <div class="shell toolbar">
      <label class="search-field">Search
        <input id="search" type="search" placeholder="Rule, mod, path, sector, explanation..." autocomplete="off">
      </label>
      <label>Severity
        <select id="severity"><option value="">All severities</option></select>
      </label>
      <label>Rule
        <select id="rule"><option value="">All rules</option></select>
      </label>
      <label>Mod
        <select id="mod"><option value="">All mods</option></select>
      </label>
      <button id="clear" type="button">Clear</button>
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

  <script id="report-data" type="application/json">__REPORT_DATA__</script>
  <script>
    "use strict";
    const report = JSON.parse(document.getElementById("report-data").textContent);
    const findings = report.findings;
    const severityOrder = ["error", "conflict", "warning", "review", "info"];
    const controls = {
      search: document.getElementById("search"), severity: document.getElementById("severity"),
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
      }
      return values.join(" ");
    }

    for (const finding of findings) {
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

    const severityCounts = new Map(), ruleCounts = new Map(), modCounts = new Map();
    for (const finding of findings) {
      severityCounts.set(finding.severity, (severityCounts.get(finding.severity) || 0) + 1);
      ruleCounts.set(finding.rule_id, (ruleCounts.get(finding.rule_id) || 0) + 1);
      for (const mod of finding.participants || []) modCounts.set(mod, (modCounts.get(mod) || 0) + 1);
    }
    addOptions(controls.severity, severityOrder.filter(value => severityCounts.has(value)), severityCounts);
    addOptions(controls.rule, [...ruleCounts.keys()].sort(), ruleCounts);
    addOptions(controls.mod, [...modCounts.keys()].sort((a, b) => a.localeCompare(b)), modCounts);

    const summary = report.summary;
    const stats = [
      [summary.mods, "Mods"], [summary.artifacts, "Files"],
      [summary.archive_manifests, "Archives"], [summary.archive_members, "Archive members"],
      [summary.archivexl_references, "ArchiveXL references"], [findings.length, "Findings"]
    ];
    const statsElement = document.getElementById("stats");
    for (const [value, label] of stats) {
      const card = document.createElement("div"); card.className = "stat";
      const number = document.createElement("span"); number.className = "stat-value";
      number.textContent = Number(value || 0).toLocaleString();
      const caption = document.createElement("span"); caption.className = "stat-label"; caption.textContent = label;
      card.append(number, caption); statsElement.append(card);
    }
    const generated = report.metadata.generated_at ? new Date(report.metadata.generated_at).toLocaleString() : "unknown";
    document.getElementById("generated").textContent = `Generated ${generated} · Scanner ${report.metadata.scanner_version || "unknown"} · Archive scope ${report.metadata.archive_scope || "unknown"}`;

    function filteredFindings() {
      const query = controls.search.value.trim().toLocaleLowerCase();
      return findings.filter(finding =>
        (!query || finding._search.includes(query)) &&
        (!controls.severity.value || finding.severity === controls.severity.value) &&
        (!controls.rule.value || finding.rule_id === controls.rule.value) &&
        (!controls.mod.value || (finding.participants || []).includes(controls.mod.value))
      );
    }

    function findingElement(finding) {
      const details = document.createElement("details"); details.className = "finding";
      details.dataset.severity = finding.severity;
      const heading = document.createElement("summary");
      const title = document.createElement("div"); title.className = "finding-title";
      const badge = document.createElement("span"); badge.className = "badge"; badge.textContent = finding.severity;
      const rule = document.createElement("span"); rule.className = "rule"; rule.textContent = finding.rule_id;
      const summary = document.createElement("span"); summary.className = "summary"; summary.textContent = finding.summary;
      title.append(badge, rule, summary); heading.append(title);
      const body = document.createElement("div"); body.className = "finding-body";
      const explanation = document.createElement("div"); explanation.className = "explanation"; explanation.textContent = finding.explanation;
      body.append(explanation);
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
            const pre = document.createElement("pre"); pre.textContent = JSON.stringify(finding.evidence, null, 2);
            evidence.append(pre); evidence.dataset.loaded = "true";
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
      document.getElementById("result-count").textContent = `${filtered.length.toLocaleString()} of ${findings.length.toLocaleString()} findings`;
      document.getElementById("page-label").textContent = `Page ${page} of ${pageCount}`;
      document.getElementById("previous").disabled = page <= 1;
      document.getElementById("next").disabled = page >= pageCount;
      document.getElementById("pager").hidden = filtered.length <= pageSize;
    }

    for (const control of Object.values(controls)) control.addEventListener("input", () => { page = 1; render(); });
    document.getElementById("clear").addEventListener("click", () => {
      controls.search.value = ""; controls.severity.value = ""; controls.rule.value = ""; controls.mod.value = ""; page = 1; render();
    });
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
