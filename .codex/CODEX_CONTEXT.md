# Codex Project Context

Last updated: 2026-08-02

## Purpose

This repository contains `cp77compat`, a read-only compatibility scanner for a
large Vortex-managed Cyberpunk 2077 mod collection. It inventories individual
mod packages, attributes deployed files through Vortex metadata, indexes
resources inside `.archive` files with WolvenKit CLI, and performs
ecosystem-specific semantic compatibility checks.

The scanner is being developed incrementally. ArchiveXL and TweakXL are the
currently supported ecosystems. Planned ecosystems include REDscript, CET Lua,
input/config files, RED4ext native plugins, and runtime logs.

## Workspace paths

- Scanner repository: `C:\Games\Programs\Mods\cyberpunk2077`
- Frozen Vortex staging collection:
  `C:\Games\Programs\Vortex Mods\cyberpunk2077`
- Deployed game:
  `C:\Games\Steam\steamapps\common\Cyberpunk 2077`
- WolvenKit CLI:
  `C:\Games\Programs\WolvenKit-Console\WolvenKit.CLI.exe`
- Scanner configuration:
  `C:\Games\Programs\Mods\cyberpunk2077\cp77compat.yaml`
- Vortex deployment manifest:
  `C:\Games\Steam\steamapps\common\Cyberpunk 2077\vortex.deployment.json`

## Safety and ownership rules

1. The Vortex staging collection and game directory are frozen reference
   inputs. Do not edit, rename, delete, redeploy, or extract files into them.
2. Scanner source, tests, reports, and caches belong only under the scanner
   repository.
3. WolvenKit inspection must remain read-only with respect to source archives.
   Temporary/selective extraction must use a scanner-owned cache directory.
4. Generated `reports/` and `.cache/` contents are ignored by Git.
5. Existing Vortex conflict decisions are authoritative unless the user asks to
   change them. The known winners are:
   - Damage Scaling and Balance - Extended over Damage Scaling.
   - Classic Drinks over the standalone No Paper Bags copy.

## Runtime and dependencies

- Python: 3.12.10 during initial implementation.
- YAML parser: PyYAML 6.0.3.
- WolvenKit CLI: 8.19.0.
- The scanner otherwise prefers the Python standard library and offline assets.
- Git: 2.55.0.windows.3 at `C:\Program Files\Git\cmd\git.exe`; its directory is
  available on the active PowerShell `PATH`.
- Repository branch: `main`. At the 2026-08-02 verification, `main` matched
  `origin/main` and the worktree was clean.

## How to run

From the repository root:

```powershell
.\run-scanner.cmd
```

Useful options:

```powershell
.\run-scanner.cmd --archive-scope none --hash-mode none
.\run-scanner.cmd --archive-scope xl --workers 4
.\run-scanner.cmd --archive-scope all
.\run-scanner.cmd --refresh-cache
```

Defaults point to the workspace paths above. The normal report destination is
`reports\current`.

`cp77compat.yaml` is the authoritative default configuration. It stores input,
tool, output, cache, archive scope, hash mode, worker, refresh, and WolvenKit
timeout settings. Relative paths are resolved from the config file directory.
CLI values override YAML. The schema is versioned and rejects duplicate or
unknown keys.

Run tests without installing the package:

```powershell
$env:PYTHONPATH = "C:\Games\Programs\Mods\cyberpunk2077\src"
python -m unittest discover -s tests -v
```

## Current architecture

- `src/cp77compat/models.py`
  Shared artifacts, references, findings, archive manifests, path normalization,
  and severity ordering.
- `src/cp77compat/deployment.py`
  Reads `vortex.deployment.json` and maps deployed relative paths to winning
  staging mods.
- `src/cp77compat/config.py`
  Strictly loads the versioned `cp77compat.yaml` schema, resolves paths, applies
  defaults, and validates choices, booleans, workers, and timeouts.
- `src/cp77compat/inventory.py`
  Discovers mod directories, inventories files, hashes selected artifacts, and
  reports exact relative-path collisions.
- `src/cp77compat/archives.py`
  Invokes `WolvenKit.CLI.exe archiveinfo --list`, parses archive member paths,
  and caches manifests by archive SHA-256. It does not extract payloads yet.
- `src/cp77compat/archivexl.py`
  Parses YAML and JSON `.xl` files, rejects duplicate YAML keys, tolerates the
  tab variants present in the frozen corpus, extracts ArchiveXL references,
  retains mapping/sequence source locations, compares streaming operations, and
  resolves resources against indexed archives or loose mod files.
- `src/cp77compat/tweakxl.py`
  Parses deployed `.yaml` and `.yml` files under `r6/tweaks`, preserves YAML
  anchors, aliases, duplicate template roots, and TweakXL tags, expands
  `$instances`, extracts concrete record/flat/property operations, and compares
  destructive assignments with additive array mutations. Source lines survive
  aliases and template expansion.
- `src/cp77compat/reporting.py`
  Writes inventory, archive manifest, per-ecosystem reference/finding JSON,
  combined findings JSON, Markdown, and HTML reports.
- `src/cp77compat/html_report.py`
  Generates a self-contained offline HTML report with search, severity/rule/mod
  and ecosystem filters, pagination, and lazily expanded evidence.
- `src/cp77compat/cli.py`
  Orchestrates the scan and exposes CLI options.
- `tests/`
  Unit tests for ArchiveXL and TweakXL parsing/comparison, archive output
  parsing, loose resource resolution, configuration, and safe HTML embedding.

## Data model and report semantics

Every analyzer should emit the same shared types:

- `Artifact`: a physical file owned by one staging mod.
- `Reference`: a semantic resource, method, record, key, or operation extracted
  from an ecosystem file.
- `Finding`: rule ID, severity, confidence, summary, explanation, participants,
  and evidence.

Severity meanings:

- `error`: definite parsing/loading/tool failure.
- `conflict`: strong evidence that operations overlap incompatibly.
- `warning`: likely problem or missing dependency/resource.
- `review`: overlap that may still be additive and needs manual inspection.
- `info`: expected state, deliberate override, or contextual observation.

Do not treat a shared ArchiveXL top-level key such as `streaming` or
`localization` as a conflict. Compare identities and operations below it.
For TweakXL, compare concrete identities after `$instances` expansion and keep
full assignments distinct from tagged array mutations. Cross-mod tagged array
operations are compatible when they neither add/remove the same value nor add
the same value through a non-unique operation.
Consolidate repeated findings by participant set when possible so reports remain
usable at large scale.

## Current verified baseline

The successful v0.2.1 scan on 2026-08-02 reported:

- 266 Vortex mod directories.
- 3,476 files.
- 104 `.xl` files: 103 non-empty configs parsed and one expected empty ArchiveXL
  framework bundle placeholder.
- 78 ArchiveXL-related archives indexed.
- 5,458 indexed archive members.
- 14,315 extracted ArchiveXL references.
- 216 deployed TweakXL YAML files: 214 non-empty configs parsed and two empty
  configs reported informationally.
- 57,455 concrete TweakXL references after `$instances` expansion.
- 36 consolidated findings overall:
  - 6 conflict candidates.
  - 2 warnings.
  - 16 review groups.
  - 12 informational findings.
- Zero WolvenKit indexing failures.
- Twenty-three automated tests passing.
- Cached normal scan time with both analyzers was approximately 43 seconds.
- All 71,770 ArchiveXL and TweakXL references have one-based source lines in the
  generated reports. For minified one-line JSON-shaped `.xl` files, line 1 is
  correctly shared by every operation in that physical source line.

Important current findings:

1. Immersive Night City Fixes and TheNullifier patch the same streaming sector
   with different `expectedNodes` values: 1237 versus 1263.
2. Five participant groups delete identical streaming node indices. The largest
   is 29 overlaps between Immersive Night City Fixes and Road Fix V2.
3. Better Armor Tooltip declares
   `better_armor_tooltip\localization\es-mx.json`, but that resource is absent.
4. NCEE NPC declares
   `localization\it-it\onscreens\ncee_onscreens.json`, but that resource is
   absent.
5. Sixteen consolidated mod groups patch some of the same streaming sectors;
   these are review candidates, not automatically confirmed incompatibilities.
6. TweakXL found 251 concrete TweakDB array identities shared across four mod
   participant groups. All use composable tagged operations in the frozen
   collection; no TweakXL conflict, warning, review, or parser error was found.

## Generated reports

- `reports/current/compatibility-report.html`
  Primary human interface. Self-contained, searchable, filterable, paginated,
  and safe to open locally.
- `reports/current/compatibility-report.md`
  Concise text report suitable for diffs and quick reading.
- `reports/current/archivexl-findings.json`
  Full ArchiveXL references and evidence.
- `reports/current/tweakxl-findings.json`
  Full TweakXL references and ecosystem findings. This is intentionally large
  because it retains all 57,455 expanded references.
- `reports/current/compatibility-findings.json`
  Combined machine-readable findings without the full reference inventories.
- `reports/current/archive-manifests.json`
  Indexed WolvenKit archive contents.
- `reports/current/inventory.json`
  Complete mod/file/deployment inventory.

## Continuity procedure

At the start of a restored Codex session, read these files in order:

1. `.codex/CODEX_CONTEXT.md`
2. `.codex/CODEX_WORKLOG.md`
3. `.codex/CODEX_TODO.md`

After material project work:

- Update `CODEX_WORKLOG.md` with what changed and how it was validated.
- Update checkbox/status information in `CODEX_TODO.md`.
- Update this context file only when stable architecture, paths, constraints,
  commands, dependencies, or baseline facts change.
