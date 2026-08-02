# Codex Worklog

This is a chronological handoff log. Add new entries at the top of the History
section. Record material changes, decisions, validation, and generated outputs;
do not use it as a raw command transcript.

## Current state

- Scanner version: `0.2.1`
- Implemented ecosystems: ArchiveXL and TweakXL
- Primary report: `reports/current/compatibility-report.html`
- Automated tests: 23 passing
- Last complete scan: successful on 2026-08-02
- Frozen inputs were not modified

## History

### 2026-08-02 — Structural source-line tracking

Replaced best-effort identity text searches with parser-owned source locations.

Changes:

- TweakXL mappings now retain key/value lines and tagged values retain their
  operation line.
- `$instances` substitutions and YAML aliases preserve the originating source
  location on every expanded reference.
- ArchiveXL mappings and sequences now retain YAML node lines for localization,
  factories, streaming blocks, sectors, and node deletions.
- JSON-shaped `.xl` files use the same located safe loader; valid tab whitespace
  is normalized only for parsing and does not create a spurious warning.
- Text lookup remains only as a fallback for values without structural marks.
- Bumped the scanner patch version to 0.2.1.
- Added exact-line regression tests for nested TweakXL tags, duplicate template
  expansion, anchored aliases, ArchiveXL sectors, and deletion indices.

Validation:

- Twenty-three unit tests passed.
- Full frozen-corpus scan completed successfully with unchanged compatibility
  results and zero WolvenKit failures.
- All 57,455 TweakXL references and all 14,315 ArchiveXL references now have a
  non-null one-based source line.
- The reported Double RAM and Lower Quickhack Cost operations both resolve to
  line 3. The vending-machine deletion resolves to line 13,992. NCEE resolves
  to line 1 because its entire `.xl` JSON document is physically one line.
- Regenerated `reports/current` and confirmed the corrected lines are embedded
  in the HTML report.
- Frozen staging and game inputs were not modified.

### 2026-08-02 — TweakXL YAML compatibility analyzer

Added semantic support for deployed TweakXL `.yaml` and `.yml` files.

Changes:

- Added `src/cp77compat/tweakxl.py` with safe custom-tag parsing and source-order
  duplicate-key preservation.
- Preserved anchors and aliases, and expanded repeated `$instances` templates
  into concrete TweakDB identities without silently dropping duplicate template
  roots.
- Extracted record `$base`/`$type`, full flat/property assignments, and
  `!append`, `!append-once`, `!append-from`, `!prepend`, `!prepend-once`,
  `!prepend-from`, and `!remove` operations.
- Added conflict rules for incompatible assignments and record definitions,
  assignment/mutation load-order risk, add/remove opposition, and duplicate
  non-unique additions.
- Added a consolidated informational rule for safe cross-mod array operations.
- Added `tweakxl-findings.json` and `compatibility-findings.json`, a TweakXL
  reference statistic, and an ecosystem filter to the offline HTML report.
- Kept high-volume informational evidence compact in HTML while retaining the
  complete reference inventory in the ecosystem JSON report.
- Bumped the scanner version to 0.2.0 and documented the analyzer.

Validation:

- Twenty-one unit tests passed.
- Parsed all 216 deployed TweakXL YAML files: 214 non-empty and two empty, with
  no parser errors.
- Extracted 57,455 concrete references after template expansion.
- Found 251 shared TweakDB array identities consolidated into four compatible
  participant groups, with no TweakXL conflict or warning in the frozen corpus.
- Full cached scan completed in approximately 43 seconds with 78 archives and
  zero WolvenKit failures.
- Final HTML report is approximately 0.69 MB; complete TweakXL JSON is
  approximately 39.83 MB.
- Frozen staging and game inputs were not modified.

### 2026-08-02 — Versioned YAML scanner configuration

Moved workspace paths and normal scan settings into tracked configuration.

Changes:

- Added `cp77compat.yaml` schema version 1.
- Added `src/cp77compat/config.py` with safe YAML parsing, duplicate-key
  rejection, unknown-key rejection, schema-version validation, relative path
  resolution, environment/user expansion, and typed option validation.
- Changed CLI values to override YAML values instead of duplicating defaults.
- Added `--config`, `--no-refresh-cache`, and `--wolvenkit-timeout` support.
- Updated `run-scanner.cmd` to pass the repository config by absolute launcher
  location, allowing it to be invoked from another working directory.
- Added configuration documentation and three configuration tests.

Validation:

- Twelve total unit tests passed.
- A normal no-argument launcher run completed successfully from the YAML config.
- The launcher also found the repository config when invoked from the external
  Cyberpunk 2077 game directory.
- Full baseline remained 266 mods, 3,476 files, 78 indexed archives, and zero
  WolvenKit indexing failures.
- Report metadata records the config path, schema version, effective paths, scan
  modes, workers, and WolvenKit timeout.

### 2026-08-02 — Git availability rechecked

Rechecked Git after it was previously unavailable to the shell.

Validation:

- `git.exe` resolves to `C:\Program Files\Git\cmd\git.exe`.
- Version: 2.55.0.windows.3.
- Repository root resolves correctly.
- Active branch: `main`.
- `main` matched `origin/main` at commit `a16f39e` before this documentation
  correction.
- Worktree was clean before editing these continuity files.

### 2026-08-02 — Searchable HTML report

Implemented a self-contained offline HTML compatibility report.

Changes:

- Added `src/cp77compat/html_report.py`.
- Added free-text search across rule IDs, mods, paths, sectors, summaries, and
  explanations.
- Added severity, rule, and mod filters.
- Added pagination and selectable page size.
- Added expandable finding details and lazily rendered evidence JSON.
- Embedded report JSON safely without external JavaScript, CSS, CDNs, or a web
  server.
- Updated `reporting.py` so every scan creates
  `compatibility-report.html` automatically.
- Updated `README.md`.
- Added an HTML safety/embedding unit test.

Validation:

- Nine unit tests passed.
- Regenerated the full current report.
- Validated that the HTML embeds all 30 findings and all filter controls.
- Final HTML size was approximately 390 KB.

### 2026-08-02 — ArchiveXL scanner MVP

Created the initial Python scanner in an empty project directory.

Changes:

- Added Python package structure and `pyproject.toml`.
- Added read-only Vortex inventory and deployment attribution.
- Added exact relative-path collision reporting.
- Added WolvenKit 8.19.0 archive indexing via `archiveinfo --list`.
- Added parallel indexing and SHA-256 keyed manifest cache.
- Added ArchiveXL YAML/JSON parsing, including duplicate-key detection and
  lenient handling for installed files containing tab characters.
- Added localization, factory, streaming block, streaming sector, and streaming
  node deletion references.
- Added loose-file and indexed-archive resource resolution.
- Added streaming-sector overlap analysis.
- Consolidated repeated sector findings by participant set to avoid hundreds of
  nearly identical report entries.
- Added JSON and Markdown reports.
- Added `run-scanner.cmd` because PowerShell script execution was disabled.

Validation:

- Parsed all 104 installed `.xl` files without an unexplained parser failure.
- Indexed 78 relevant archives and 5,458 members with zero WolvenKit failures.
- Extracted 14,315 ArchiveXL semantic references.
- Confirmed Vortex attribution for the four known non-archive physical path
  collisions.
- Second cached full scan completed in approximately 33 seconds.
- Eight tests passed at the end of this milestone.

### 2026-08-02 — Initial compatibility assessment and design

Inspected the frozen game and Vortex staging layouts and established the scanner
approach.

Observed corpus:

- 266 mod directories and 3,476 files.
- 3,309 non-archive files, including 1,235 REDscript files, 250 CET Lua files,
  194 YAML files, 104 `.xl` files, and 18 DLL/ASI files.
- Four exact non-archive path collisions representing two known Vortex conflict
  groups.

Design decisions:

- Build a universal inventory/evidence model before ecosystem analyzers.
- Start ecosystem analysis with ArchiveXL, then reuse YAML infrastructure for
  TweakXL.
- Use `archiveinfo --list` without extraction for archive manifests.
- Add selective, scanner-owned extraction only when semantic payload inspection
  requires it.
- Keep findings confidence-aware and distinguish definite conflicts from review
  candidates.

## Worklog entry template

### YYYY-MM-DD — Short title

Goal:

- What outcome was requested.

Changes:

- Important files and behavior changed.
- Stable design decisions made.

Validation:

- Tests or scans run.
- Relevant counts and failures.

Follow-up:

- Remaining work moved to `CODEX_TODO.md`.
