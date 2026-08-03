# Codex Project Context

Last updated: 2026-08-03

## Purpose

This repository contains `cp77compat`, a read-only compatibility scanner for a
large Vortex-managed Cyberpunk 2077 mod collection. It inventories individual
mod packages, attributes deployed files through Vortex metadata, indexes
resources inside `.archive` files with WolvenKit CLI, and performs
ecosystem-specific semantic compatibility checks.

The scanner is being developed incrementally. ArchiveXL and TweakXL are the
currently supported ecosystems. ArchiveXL and TweakXL runtime logs are
supported. Planned ecosystems include REDscript, CET Lua, input/config files,
RED4ext native plugins, and runtime correlation for the remaining frameworks.

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
.\run-scanner.cmd --payload-scope none
.\run-scanner.cmd --refresh-cache
```

Defaults point to the workspace paths above. The normal report destination is
`reports\current`.

`cp77compat.yaml` is the authoritative default configuration. It stores input,
tool, output, cache, archive scope, hash mode, worker, refresh, and WolvenKit
timeout settings. Relative paths are resolved from the config file directory.
CLI values override YAML. The schema includes archive and payload scope and is
versioned; it rejects duplicate or unknown keys.

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
  and caches manifests by archive SHA-256.
- `src/cp77compat/archive_payloads.py`
  Materializes exact archive members into a SHA-256-keyed scanner cache using
  numeric FNV-1a hashes, rejects unsafe paths, serializes CR2W resources through
  WolvenKit, validates cached hashes, and records per-resource metadata.
- `src/cp77compat/archivexl_payload_analysis.py`
  Extracts locale-scoped localization entry identities from serialized payloads
  and compares cross-mod `secondaryKey` and nonzero `primaryKey` definitions. It
  also parses factory C2dArray rows, compares entity names and targets, and
  validates target resources against indexed archives and loose files. Shared
  resource patch sources are serialized and compared through stable named
  objects, scalar properties, and C2dArray row identities. Journal resources
  are reconstructed into effective entry paths and compared using ArchiveXL's
  container, leaf, and final-`*` property-edit semantics. Character
  customization resources are compared by gender, body part, group entry,
  named option, anonymous slot/link selector, native type, and type-specific
  choice identity.
- `src/cp77compat/archivexl.py`
  Parses YAML and JSON `.xl` files, rejects duplicate YAML keys, tolerates the
  tab variants present in the frozen corpus, extracts ArchiveXL references,
  retains mapping/sequence source locations, compares streaming, resource, and
  quest phase operations, resolves resources plus custom quest parents against
  indexed archives or loose mod files, and compares whole-definition,
  case-sensitive visual-tag component overrides. Streaming node deletion
  references preserve native type, declared/effective scope, expected element
  counts, and actor/instance/shape indices. Streaming node and nested element
  mutations are reduced to their effective property writes and compared with
  other mutations and deletions using ArchiveXL's application semantics.
  Player body-type declarations are parsed into exact case-sensitive body type
  and `Body:<name>` tag identities.
- `src/cp77compat/archivexl_runtime.py`
  Selects the newest ArchiveXL session, streams all rotated chunks in
  chronological order, pairs root-cause and consequence messages, attributes
  localization/streaming events through semantic references, and maps missing
  quest phases through exact child or parent references. Streaming node-type
  and element-count validation failures are attributed to sector/node
  identities. Journal resource and merge failures are also attributed to their
  static declarations, and customization native-type mismatch warnings are
  mapped to option names.
- `src/cp77compat/tweakxl.py`
  Parses deployed `.yaml` and `.yml` files under `r6/tweaks`, preserves YAML
  anchors, aliases, duplicate template roots, and TweakXL tags, expands
  `$instances`, extracts concrete record/flat/property operations, and compares
  destructive assignments with additive array mutations. Source lines survive
  aliases and template expansion.
- `src/cp77compat/tweakxl_runtime.py`
  Selects the newest timestamped TweakXL log, parses runtime errors and
  warnings, attributes file-scoped events through `Reading` context, resolves
  late validation events through TweakDB identities, and correlates compatible
  static findings.
- `src/cp77compat/reporting.py`
  Writes inventory, archive manifest, per-ecosystem reference/finding JSON,
  combined findings JSON, Markdown, and HTML reports.
- `src/cp77compat/html_report.py`
  Generates a self-contained offline HTML report with search, severity/rule/mod
  and ecosystem filters, analyzer-coverage tables, pagination, and lazily
  expanded evidence.
- `src/cp77compat/cli.py`
  Orchestrates the scan and exposes CLI options.
- `tests/`
  Unit tests for ArchiveXL and TweakXL parsing/comparison, archive output
  parsing, loose resource resolution, TweakXL runtime correlation,
  configuration, and safe HTML embedding.

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

The successful v0.16.0 scan on 2026-08-03 reported:

- 266 Vortex mod directories.
- 3,476 files.
- 104 `.xl` files: 103 non-empty configs parsed and one expected empty ArchiveXL
  framework bundle placeholder.
- 78 ArchiveXL-related archives indexed.
- 5,458 indexed archive members.
- 60,343 extracted ArchiveXL references, including 1,314 streaming node
  mutations, 279 nested element mutations, one `player.body_type`
  registration, 596 child/parent references from 298 quest phase merges, 4,124
  serialized localization entries, 14
  factory entity rows, 232 serialized journal entries, and 8,302 target-scoped
  resource patch inner identities.
- Thirty male/female customization declarations resolved to 29 unique archive
  payloads. All serialized successfully into 720 group entries, 335 options,
  and 8,455 choices (9,510 merge identities total).
- 216 deployed TweakXL YAML files: 214 non-empty configs parsed and two empty
  configs reported informationally.
- 57,455 concrete TweakXL references after `$instances` expansion.
- 181 archive-owned localization payloads serialized with zero failures; four
  declarations without an own indexed archive payload were skipped and remain
  covered by resource-resolution findings.
- Six factory payloads serialized into 14 entity rows. All 14 target resources
  resolve inside their declaring mods, with no name collisions, missing targets,
  or cross-mod dependencies.
- Twenty-three compatibility-relevant patch sources serialized for all 43
  targets shared across mods. Every shared target uses disjoint stable inner
  identities; none remained uninspected or produced a conflict.
- Three journal payloads serialized successfully into 232 entry references.
  Their only shared identity is the composable `contacts` container; no journal
  leaf or property-edit duplicate, conflict, or review finding was produced.
- Four override documents define 12 case-sensitive visual tags over 14
  components and 31 chunk references. No tag name is shared across mods and no
  installed definition replaces one of ArchiveXL's built-in garment tags.
- TweakXL dependency analysis indexed 74,829 named records from 2,684 official
  REDmod `.tweak` files and verified generated `_inlineN` IDs against both
  local TweakDB binaries.
- All 1,284 `$base` targets were classified: 1,110 vanilla/generated-inline,
  75 same-mod, 98 cross-mod, and one capitalization mismatch; no truly missing
  target and no base cycle was found.
- 27,374 implicit values exactly match installed custom record providers;
  18,660 of those references form three compact cross-mod dependency
  relationships. No explicit `t"..."`/`TweakDBID("...")` foreign keys occur in
  the frozen TweakXL corpus.
- The newest 333-line TweakXL runtime log contained 74 errors and 12 warnings.
  All 86 events were attributed to staging sources and consolidated into seven
  runtime findings; the static `$base` capitalization error was confirmed.
- The newest ArchiveXL runtime session spans two rotated files, 137,845,003
  bytes, and 472,639 lines. Its two errors and six warnings were fully
  attributed and consolidated into four findings; all four quest events have
  exact static missing-target confirmations.
- 60 consolidated findings overall:
  - 1 conflict candidate.
  - 9 errors.
  - 11 warnings.
  - 0 review groups.
  - 39 informational findings.
- Zero WolvenKit indexing failures.
- Seventy-nine automated tests passing.
- First payload-populating scan time was 546 seconds; the immediate fully cached
  normal scan completed in 9.51 seconds. The fully cached factory-enabled scan
  completed in 8.97 seconds. The first shared-patch pass completed in 73.9
  seconds. The v0.7 dependency-enabled fully cached scan completes in about
  17.8 seconds, including indexing the local official TweakDB sources. The first
  customization payload pass completed in 110.9 seconds; the fully cached
  v0.13 normal scan completed in 19.7 seconds; the fully cached v0.15 and v0.16
  scans complete in about 20 seconds.
- All 117,798 ArchiveXL and TweakXL references have one-based declaration/source
  lines in the generated reports. Serialized localization, factory, and journal
  entries additionally carry their zero-based payload `entry_index` or
  `row_index`. For minified one-line
  JSON-shaped `.xl` files, line 1 is correctly shared by every declaration on
  that physical source line.

Important current findings:

1. Immersive Night City Fixes and TheNullifier patch the same streaming sector
   with different `expectedNodes` values: 1237 versus 1263.
2. Five participant groups repeat 40 full streaming-node deletions. ArchiveXL
   hides these nodes in place without removing or renumbering them, so all five
   groups are high-confidence informational/idempotent overlaps. The largest is
   29 shared deletions between Immersive Night City Fixes and Road Fix V2.
3. Better Armor Tooltip declares
   `better_armor_tooltip\localization\es-mx.json`, but that resource is absent.
4. NCEE NPC declares
   `localization\it-it\onscreens\ncee_onscreens.json`, but that resource is
   absent.
5. Fourteen participant groups share 344 streaming sectors while touching only
   disjoint node indices. These are high-confidence informational overlaps, not
   compatibility review candidates.
6. TweakXL found 251 concrete TweakDB array identities shared across four mod
   participant groups. All use composable tagged operations in the frozen
   collection; no assignment or tagged-array incompatibility was found.
7. ArchiveXL resource declarations add 43 composable cross-mod patch targets,
   consolidated into three participant groups. No contradictory fix or
   copy/link target was found.
8. Two Beautiful Eyebrows variants provide four identical copy targets. This is
   recorded as one informational duplicate-redirect group.
9. All 181 available localization payloads were inspected; no cross-mod
   duplicate or conflicting locale/key identities were found.
10. All six factory payloads were inspected; 14 entity names are unique and all
    target resources resolve within their declaring mods.
11. All 43 cross-mod resource patch targets were inspected at payload level:
    36 citizen entity targets patch components versus appearances, six player
    hair targets use distinct appearance identities, and one device database
    target adds distinct device hashes.
12. `Attachments Crafting System.yaml` line 94 clones
    `Items.w_att_scope_sniper_02_legendary`, but the installed vanilla record is
    `Items.w_att_scope_sniper_02_Legendary`. This is the only high-confidence
    TweakXL dependency error.
13. Three valid custom-record dependency relationships were identified:
    Attachments Unrestricted consumes records from Attachments Crafting System
    and 6 More Weapon Mod Slots, while More Mods More Fun Compatible Patch also
    consumes records from 6 More Weapon Mod Slots.
14. The latest runtime log directly confirms the Attachments Crafting System
    capitalization error at source line 94.
15. Better Living Buffs produces 12 unknown-property errors: `isActive` once
    and `maxFactor` on 11 records. NCEE NPC separately assigns the unknown
    `enabledPhotoModePuppet` property at line 5,064.
16. More Mods More Fun, its compatible patch, and 6 More Weapon Mod Slots each
    produce 20 ambiguous-definition errors for the same set of weapon-mod
    records, for 60 runtime events total.
17. TweakXL validation reports 12 hash-only missing targets from
    `Items.TechMod2_Common.placementSlots`; all three mods above mutate that
    flat and are retained as source candidates.
18. Cyberware EX Keybinds declares its English localization resource at line
    3, but ArchiveXL fails to load it at runtime.
19. Immersive Night City Fixes declares an `expectedNodes: 4` streaming guard
    at line 11,134; runtime sees six nodes and skips that sector patch.
20. HG Enemies, NCEE Enemies, and NCEE NPC reference three absent New Game Plus
    quest parents. They Will Remember separately references an absent
    retaliation phase at lines 63 and 65.
21. The Beautiful Eyebrows 01 and 02 packs intentionally extend the same
    female and male `eyebrows` switcher options with disjoint choice names.
    ArchiveXL composes both overlaps; there are no customization conflicts,
    duplicate choices, or review findings in the frozen collection.
22. No streaming node-mutation identity is shared across mods. Thirteen
    Immersive Night City Fixes mutations target nodes fully deleted by 4x
    Vending Machine Framework; the deletion dominates in either order, so the
    overlap is informational redundancy.
23. The node-mutation parser found 10 accepted-but-ignored operations and nine
    unknown fields. These are consolidated into two warnings with exact source
    lines; the unknown fields include seven `nodeRefHash` uses plus the
    `sscale` and `rientation` spellings.

Analyzer coverage is embedded in all primary reports. It currently records 45
ArchiveXL documents with `resource` sections and marks all five installed
resource operations (`copy`, `fix`, `link`, `patch`, and `scope`) as analyzed at
declaration level. The `resource` section remains partial until payload contents
are selectively extracted and compared. Localization is now marked analyzed for
archive-owned on-screen resources and its extraction/serialization cache counts
are embedded in report coverage. Factory declarations are also marked analyzed,
with row counts, cache counts, and target-resolution results in the same panel.
Shared-target resource patch payload counts and disjoint/duplicate/conflict/
uninspected outcomes are recorded there as well. Journal coverage is analyzed
for all three installed resources, including 232 effective entry identities and
ArchiveXL's container/leaf/edit merge semantics. The current runtime session
confirms that all three journal resources merged successfully. ArchiveXL
runtime coverage records the selected session, rotated files, byte/line counts, event
attribution, static correlations, and consolidated findings. Quest coverage is
analyzed for all 298 installed `quest.phases` merges: child resources and custom
parents are resolved, attachment identities are compared, official parents are
classified, and all four runtime missing targets confirm matching static rules.
TweakXL coverage now includes record-provider indexing, `$base` resolution and
cycle counts, explicit foreign-key results, and conservative implicit
custom-provider matches. Arbitrary implicit scalar values remain partial rather
than being guessed without property type metadata. The newest TweakXL runtime
log is also analyzed automatically; coverage records the selected path, line
and event counts, source attribution, static confirmations, and consolidated
finding count.
The four installed `overrides.tags` documents are fully analyzed using
ArchiveXL-equivalent effective component masks and whole-definition last-wins
semantics. Their 12 tag names are all distinct.
All 19 installed `customizations` documents are analyzed at declaration and
payload level. Coverage includes exact resource resolution, ArchiveXL's
anonymous appearance inheritance, named linked-option behavior, wildcard slot
matching, group append semantics, native option types, and appearance/morph/
switcher choice replacement identities.
The one installed `player.bodyTypes` document is fully analyzed. It registers
the case-sensitive `ANGEL` body type and `Body:ANGEL` tag at source line 27;
there are no cross-mod duplicates. Exact duplicates would be informational and
idempotent, while distinct body-type registrations compose.
World-streaming mutation coverage is fully analyzed: 3,110 sector patches,
1,314 node mutations, 279 nested element mutations, 1,728 effective node
property writes, and 422 effective element-property writes. Comparisons account
for alias precedence, node and element validation guards, destructible-instance
replacement behavior, and mutation/deletion ordering.
Streaming deletion analysis distinguishes full nodes, partial actors/instances,
and collision shapes. Same-type full deletions and ordinary partial deletions
are idempotent/composable; native-type or expected-element disagreements are
conflicts. Multiple collision-shape deletion patches on one node remain a
conflict because ArchiveXL's shared collision-preset override is not safely
resized on later patches. The frozen corpus has 10,812 deletion references:
10,635 declared full and 177 declared partial, resolving to 10,672 effective
full and 140 effective partial operations. All 40 cross-mod overlaps are safe
full-node repetitions.

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
