# Codex Project Context

Last updated: 2026-08-06

## Purpose

This repository contains `cp77compat`, a read-only compatibility scanner for a
large Vortex-managed Cyberpunk 2077 mod collection. It inventories individual
mod packages, attributes deployed files through Vortex metadata, indexes
resources inside `.archive` files with WolvenKit CLI, and performs
ecosystem-specific semantic compatibility checks.

The scanner is being developed incrementally. ArchiveXL, TweakXL, REDscript,
CET Lua, Input Loader XML, and RED4ext/native plugins are supported, including
their relevant runtime/compiler logs. Shared JSON/TOML/INI/XML ownership,
CET-to-REDscript method-hook analysis, and CET runtime TweakDB-to-TweakXL
cross-ecosystem analysis are also supported.

## Workspace paths

- Scanner repository: `C:\Games\Programs\Mods\cyberpunk2077`
- Vortex staging collection:
  `C:\Games\Programs\Vortex Mods\cyberpunk2077`
- Locally built Vortex-ready compatibility/repair packages:
  `C:\Games\Programs\Mods\cyberpunk2077-mods`
- Deployed game:
  `C:\Games\Steam\steamapps\common\Cyberpunk 2077`
- WolvenKit CLI:
  `C:\Games\Programs\WolvenKit-Console\WolvenKit.CLI.exe`
- Scanner configuration:
  `C:\Games\Programs\Mods\cyberpunk2077\cp77compat.yaml`
- Finding acknowledgements:
  `C:\Games\Programs\Mods\cyberpunk2077\acknowledgements.yaml`
- Vortex deployment manifest:
  `C:\Games\Steam\steamapps\common\Cyberpunk 2077\vortex.deployment.json`

## Safety and ownership rules

1. The v0.27.0 report is the final frozen reference baseline. Starting after
   that scan, the user is manually reviewing and may add compatibility mods or
   change Vortex deployment. Existing author-provided mod packages remain
   read-only: never edit, rename, delete, or place our files inside them. Treat
   deployed state as mutable and rescan before relying on old findings. Codex
   must not install or redeploy anything unless the user explicitly requests
   that exact action.
2. Scanner source, tests, reports, and caches belong only under the scanner
   repository.
3. WolvenKit inspection must remain read-only with respect to source archives.
   Temporary/selective extraction must use a scanner-owned cache directory.
4. Generated `reports/` and `.cache/` contents are ignored by Git.
5. Existing Vortex conflict decisions are authoritative unless the user asks to
   change them. The known winners are:
   - Damage Scaling and Balance - Extended over Damage Scaling.
   - Classic Drinks over the standalone No Paper Bags copy.
6. Local fixes belong in independently named Vortex packages under
   `C:\Games\Programs\Mods\cyberpunk2077-mods`. The user imports and deploys
   them; Codex must not modify the upstream package or deploy the fix unless
   explicitly requested.
7. Defer gameplay checks that require meaningful story progression until the
   user finishes reviewing the static/runtime report. Maintain an accumulated
   checklist and provide one consolidated in-game validation plan afterward,
   rather than asking the user to replay or advance the intro after every fix.
8. For routine runtime-log refreshes, the user launches the game and loads an
   early Street Kid save at the starting bar in central Night City. The populated
   location is the standard baseline because it initializes an actual save plus
   UI, streaming, crowds, NPCs, and common gameplay systems. Use it for general
   startup/log validation, while retaining feature-specific checks for the final
   consolidated pass when the save has access to the required items or systems.

## Runtime and dependencies

- Python: 3.12.10 during initial implementation.
- YAML parser: PyYAML 6.0.3.
- WolvenKit CLI: 8.20.0 (verified from both executable metadata and
  `WolvenKit.CLI.exe --version` on 2026-08-06). The executable path is
  unchanged, so `cp77compat.yaml` requires no path update.
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
  are reconstructed into effective entry paths after resolving WolvenKit
  `HandleId`/`HandleRefId` graphs, then compared using ArchiveXL's container,
  leaf, and final-`*` property-edit semantics. Missing references and ancestor
  cycles are consolidated into per-resource structural findings. Character
  customization resources are compared by gender, body part, group entry,
  named option, anonymous slot/link selector, native type, and type-specific
  choice identity.
- `src/cp77compat/archivexl.py`
  Parses YAML and JSON `.xl` files, rejects duplicate YAML keys, tolerates the
  tab variants present in the frozen corpus, extracts ArchiveXL references,
  retains mapping/sequence source locations, compares streaming, resource, and
  quest phase operations, resolves resources plus custom quest parents against
  indexed archives, loose mod files, and active `resource.scope` aliases
  (including ArchiveXL's bundled `cyberpunk2077.quest` root), and compares whole-definition,
  case-sensitive visual-tag component overrides. Streaming node deletion
  references preserve native type, declared/effective scope, expected element
  counts, and actor/instance/shape indices. Streaming node and nested element
  mutations are reduced to their effective property writes and compared with
  other mutations and deletions using ArchiveXL's application semantics.
  Vortex-overridden `.xl` providers are retained by inventory/exact-path
  provenance but excluded from active ArchiveXL semantics. A unique minimally
  edited exact-path winner inherits its overridden provider as logical ownership
  so compatibility repair packages resolve the upstream companion archives and
  do not appear as duplicate independent mods.
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
- `src/cp77compat/redscript.py`
  Lexically parses REDscript annotations with exact source lines, target class,
  parameter/return signature, field type, normalized body fingerprint, wrapper
  calls, installed `ModuleExists` condition state, and Vortex deployment state.
  Minimally edited exact-path winners retain their overridden upstream package
  as logical ownership while preserving physical repair-package provenance. It
  compares replacements, added symbols, and wrapper chains using official
  compiler semantics.
- `src/cp77compat/redscript_runtime.py`
  Parses `redscript_rCURRENT.log`, records compilation/output success, maps
  deployed diagnostic paths and lines back to staging artifacts and exact
  annotation signatures, and correlates static REDscript findings.
- `src/cp77compat/cet.py`
  Lexically parses CET Lua without executing it; resolves per-root entrypoints
  and literal modules; extracts lifecycle events, hotkeys, inputs, `GetMod`
  dependencies, observers, overrides, Native Settings paths, and literal
  TweakDB flat/record mutations with static scalar/array values; and compares
  registrations using the installed CET sandbox and callback-chain semantics.
- `src/cp77compat/cet_runtime.py`
  Parses current CET framework, scripting, and canonical per-mod logs; records
  selects the newest appended game session, records loaded/ignored/failed roots,
  and attributes missing hooks, rejected registrations, module failures, and
  Lua errors to staging sources where possible.
- `src/cp77compat/cross_ecosystem.py`
  Compares active literal CET observers and overrides with active REDscript
  wrappers and replacements by class, method, and available NativeDB full
  signature. It distinguishes additive observers, wrapped chains, uncertain
  callbacks, terminating overrides, same-package integration, overload-
  ambiguous short names, and unguessable dynamic hooks. It also compares active
  literal CET `SetFlat`/record mutations with concrete TweakXL assignments,
  tagged arrays, `$base`, `$type`, and descendant record properties.
- `src/cp77compat/shared_config.py`
  Inventories JSON, TOML, INI, and XML ownership; parses each format strictly;
  excludes cooked CR2W resources that use a `.json` game extension; tracks
  encoding and duplicate JSON keys; computes format-normalized semantic hashes;
  compares exact-path providers; and reports broader multi-package configuration
  scopes without treating them as conflicts.
- `src/cp77compat/input_mapping.py`
  Parses `r6/input/*.xml` with structural source lines; models Input Loader's
  exact whole-node replacement and child-append semantics; resolves mapping,
  context, and action targets; compares vanilla definitions; validates the two
  generated cache files; and correlates `input_loader.log`.
- `src/cp77compat/native.py`
  Inventories DLL/ASI providers without executing them; compares staging and
  deployed hashes; extracts Windows fixed file versions and PE normal/delay
  imports; resolves native dependencies; correlates RED4ext plugin load states,
  framework/game versions, and structured plugin logs; and delegates
  ArchiveXL, TweakXL, and Input Loader diagnostics to dedicated analyzers.
- `src/cp77compat/finding_state.py`
  Computes stable finding fingerprints, applies strict YAML acknowledgements,
  detects stale acknowledgements, and classifies scan-to-scan new, changed,
  resolved, and unchanged state while ignoring evidence ordering noise.
- `src/cp77compat/reporting.py`
  Writes inventory, archive manifest, per-ecosystem reference/finding JSON,
  combined findings JSON, Markdown, and HTML reports.
- `src/cp77compat/html_report.py`
  Generates a self-contained offline HTML report with search, status/change and
  ecosystem filters, responsive coverage tables/cards, pagination, lazily
  expanded evidence, inline acknowledgement controls, and user-approved YAML
  saving with a download fallback. Absolute Windows `source_path` values retain
  their full JSON text while linking to encoded `file:///` parent directories.
- `src/cp77compat/cli.py`
  Orchestrates the scan and exposes CLI options.
- `tests/`
  Unit tests for ArchiveXL, TweakXL, REDscript, CET, cross-ecosystem method and
  TweakDB comparison, and shared configuration parsing/comparison; archive
  output parsing; loose resource resolution; runtime/compiler-log correlation;
  configuration; and safe HTML embedding.

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

The successful v0.27.0 scan on 2026-08-03 reported:

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
- 1,235 REDscript artifacts and 16,775 parsed annotation references with exact
  source lines and zero parser failures. The effective installed set contains
  700 wrappers, 139 replacements, 14,024 added methods, and 1,885 added fields;
  27 conditional or Vortex-overridden annotations are inactive.
- 248 CET Lua files across 61 active CET roots and 3,540 extracted references,
  all with source lines. Effective registrations include 161 events, 18
  hotkey/input bindings, 182 literal module imports, 47 `GetMod` dependencies,
  806 observers, 239 overrides, 495 Native Settings paths, 363 literal TweakDB
  flat writes, and seven literal TweakDB record mutations. Another 286
  dynamically constructed calls are inventoried, including 15 TweakDB calls
  whose targets are computed and intentionally not guessed.
- Cross-ecosystem comparison found 33 class-and-method targets shared by active
  CET hooks and REDscript wrappers/replacements. Thirty targets include
  additive CET observers and three include overrides that visibly call their
  wrapped/next callback. No uncertain or terminating override was found. All
  installed CET names are short-name, overload-ambiguous matches; 129 dynamic
  hook calls are counted but intentionally not guessed. The 33 targets are
  consolidated into 30 informational findings.
- CET/TweakXL analysis found 22 exact TweakDB flat targets: 21 are intentional
  same-package integrations and one is cross-package. Clothing Improved writes
  `Items.IntrinsicFabricEnhancer10_inline2.value` as `-0.01` at runtime while
  Quickhack Fixes assigns `1` through TweakXL, producing one high-confidence
  runtime-override warning. No record target overlap was found.
- Definite global-symbol extraction found 492 reachable writes plus two
  computed-name writes across 64 files. `DamageScaling` is the only active root
  assembled from multiple Vortex packages, and it has zero shared exact globals.
- 161 shared configuration documents were inventoried: 138 JSON, 9 TOML, 4
  INI, and 10 XML. They contain 75,392 normalized entries across 22 ownership
  scopes; four scopes have multiple package owners and no exact path is shared.
- All TOML, INI, and XML documents parse. JSON parses 137 of 138 documents;
  one JSON file uses CP-1252 and no duplicate JSON key was found.
- Seven active Input Loader XML fragments provide 449 source-lined references
  across 189 top-level nodes: 72 mappings, 101 contexts, 15 timing/event
  policies, and one button group. Twenty-one shared targets compose through
  `append="true"`; no cross-mod whole-node conflicts, child conflicts, missing
  targets, cache mismatches, or runtime diagnostics were found.
- Current CET logs cover 63 files and 19,285 lines. CET 1.37.1 loaded all 61
  active roots, ignored two data directories without `init.lua`, and failed no
  mod roots. Four runtime events produced three consolidated findings.
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
- The 1,277-line current REDscript compiler log successfully compiled 1,234
  deployed files and saved the modded output. Its zero errors and eight
  warnings were all source-attributed and statically confirmed.
- 216 consolidated findings overall:
  - 2 conflict candidates.
  - 11 errors.
  - 19 warnings.
  - 13 review groups.
  - 171 informational findings.
- Zero WolvenKit indexing failures.
- 110 automated tests passing with warnings promoted to errors.
- First payload-populating scan time was 546 seconds; the immediate fully cached
  normal scan completed in 9.51 seconds. The fully cached factory-enabled scan
  completed in 8.97 seconds. The first shared-patch pass completed in 73.9
  seconds. The v0.7 dependency-enabled fully cached scan completes in about
  17.8 seconds, including indexing the local official TweakDB sources. The first
  customization payload pass completed in 110.9 seconds; the fully cached
  v0.13 normal scan completed in 19.7 seconds; the fully cached v0.15 and v0.16
  scans complete in about 20 seconds; the REDscript-enabled v0.17 scan completed
  in about 26 seconds, the CET-enabled v0.18 scan completed in 26.9 seconds,
  the global-analysis v0.19 scan completed in 27.5 seconds, and the shared-config
  v0.20 scan completed in 27.2 seconds. The fully cached v0.27 scan completed
  in 28 seconds.
- All 138,274 ArchiveXL, TweakXL, REDscript, CET, and configuration references have one-based declaration/source
  lines in the generated reports. Serialized localization, factory, and journal
  entries additionally carry their zero-based payload `entry_index` or
  `row_index`. For minified one-line
  JSON-shaped `.xl` files, line 1 is correctly shared by every declaration on
  that physical source line.

Important current findings:

## Post-baseline review phase

After the v0.27.0 validation scan, the user began manual finding review and
explicitly unfroze the mod collection. They may modify the installed/staged set
before returning. On resumption:

- inspect current deployment and Git state instead of assuming the v0.27.0
  inventory still matches;
- preserve the v0.27.0 report as historical context, not current truth;
- rescan after requested mod changes or compatibility patches;
- never modify a source mod merely because a finding recommends it—confirm the
  exact desired outcome with the user first;
- prefer a separately owned compatibility patch/package when practical instead
  of destructively editing an upstream mod.

Compatibility fixes follow a strict overlay-mod workflow:

- every change is created as a new, independently named mod/package;
- a compatibility mod contains only the minimal new or overriding files needed
  for its purpose;
- original mod folders and files are never modified, even when an override is
  simple;
- the compatibility mod is imported into Vortex, and Vortex deployment rules
  make its files win over the original providers;
- multiple unrelated fixes should remain separate small mods unless the user
  explicitly chooses to combine them;
- after import/deployment, rescan the effective collection and verify both the
  intended winner and any new semantic interactions;
- keep our package identity and filenames distinct enough that later author
  updates cannot be confused with locally maintained fixes.

### Current post-baseline state

The first successful scan after the user's collection changes is v0.28.0 on
2026-08-04. It supersedes v0.27.0 for current issue review while v0.27.0 remains
the historical frozen baseline.

- 271 mod directories and 3,597 files.
- 79 archives indexed; 104 non-empty ArchiveXL and 214 non-empty TweakXL
  configurations.
- 1,278 REDscript and 304 CET Lua files.
- Twelve journal payloads serialized into 388 effective entry occurrences.
  WolvenKit `HandleRefId` graph references in Immersive Gigs resolve correctly;
  there are no journal shape, duplicate, conflict, or review findings.
- 225 consolidated findings: 2 conflicts, 10 errors, 20 warnings, 13 reviews,
  and 180 informational findings.
- 221 findings are active and four acknowledged; no acknowledgement is stale.
- Compared with the v0.27 report: 27 new, 18 changed, 17 resolved, and 180
  unchanged findings.
- 112 automated tests pass with warnings promoted to errors.

1. The earlier Immersive Night City Fixes/TheNullifier `expectedNodes` conflict
   was a scanner-side misclassification of an operation that ArchiveXL rejects
   during config parsing. The installed GIM sector has 1,263 node setups. INCF
   correctly deletes setup 251; TheNullifier transposed its values by declaring
   `expectedNodes: 1237` and out-of-range index 1263. The named front-door proxy
   is setup 1237. Scanner v0.28.5 now emits `AXL-NODE-DELETION-SHAPE` and omits
   such inert sectors from cross-mod comparison. A two-line TheNullifier Vortex
   override corrects the values and composes with INCF as disjoint deletions.
   The user subsequently deployed it and confirmed the former conflict/finding
   disappeared.
   Scanner v0.28.5 also exposed an independent INCF deletion typo in
   `exterior_-18_33_0_0.streamingsector`: the current sector has 2,510 node
   setups, and the intended Northside `japanese_lantern_a_center.mesh` is a
   `worldStaticMeshNode` at setup 1,812, while INCF declared impossible index
   18,812. A one-line full `INCF.xl` Vortex override has been packaged; user
   deployment is confirmed. Scanner v0.28.6 corrected exact-path winner and
   logical-owner handling; the fixed full-file override now replaces rather
   than duplicates INCF semantics, and the invalid deletion is absent.
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
    produced 20 ambiguous-definition errors for the same set of weapon-mod
    records, for 60 runtime events total. Version 1.0.0 of the local ambiguity
    repair removed only the 20 nonexistent template instances; the user
    deployed it and confirmed those errors disappeared.
17. TweakXL subsequently reported 12 hash-only missing targets from
    `Items.TechMod2_Common.placementSlots`. The hashes resolve to 12 nonexistent
    `_Collectible` attachment slots repeated by More Mods More Fun and
    Attachments Unrestricted. Version 1.1.0 supersedes the ambiguity repair,
    retains its six existing overrides, and removes the no-op references from
    both active ranged templates. The user deployed 1.1.0 and confirmed the
    report is clear after launch and rescan.
18. Cyberware EX Keybinds declares its English localization resource at line
    3, but ArchiveXL fails to load it at runtime.
19. Immersive Night City Fixes declares an `expectedNodes: 4` streaming guard
    at line 11,134; runtime sees six nodes and skips that sector patch.
20. HG Enemies, NCEE Enemies, and NCEE NPC referenced three absent New Game
    Plus quest parents through 69 optional merge declarations. Their deployed
    cleanup package removes only those hooks while NG+ is absent, and the user
    confirmed the findings disappeared. They Will Remember 2.5a separately
    misspells its packaged Maelstrom redemption phase as a nonexistent
    retaliation phase at lines 63 and 65. A two-line exact-path override is
    packaged and pending user deployment.
21. The Beautiful Eyebrows 01 and 02 packs intentionally extend the same
    female and male `eyebrows` switcher options with disjoint choice names.
    ArchiveXL composes both overlaps; there are no customization conflicts,
    duplicate choices, or review findings in the frozen collection.
22. No streaming node-mutation identity is shared across mods. Thirteen
    Immersive Night City Fixes mutations target nodes fully deleted by 4x
    Vending Machine Framework; the deletion dominates in either order, so the
    overlap is informational redundancy.
23. The node-mutation parser found 10 accepted-but-ignored operations and nine
    unknown fields in INCF. ArchiveXL 1.27.1 only applies positive proxy deltas,
    does not parse `nodeRefHash`, and cannot apply actor transforms to foliage;
    those 17 evidence records have no safe `.xl` translation. The remaining two
    fields were spelling mistakes (`sscale`, `rientation`) and are corrected in
    `Immersive Night City Fixes - Combined Streaming Fixes-1.1.0.zip`, which
    also includes the earlier lantern correction. After deployment, the unknown
    group should fall to seven while the 10 unsupported operations remain for
    explicit acknowledgement.
24. Cyberware-EX and VanillaPlus Parkour both replace
    `DoubleJumpDecisions.EnterCondition(ref<StateContext>,
    ref<StateGameScriptInterface>)->Bool` with different bodies. VanillaPlus
    Parkour's later body preserves Cyberware-EX's removal of the charge/hover
    exclusion and additionally removes the fall-speed rejection, making it a
    functional superset. A version-specific Cyberware-EX 1.5.6 full-script
    override removes only the redundant earlier replacement; it is packaged as
    `Cyberware-EX - VanillaPlus Parkour Compatibility-1.0.0.zip` and awaits user
    import/deployment validation.
25. 6 More Weapon Mod Slots and Slots Slots Slots - Cyberdeck 2x Quickhack
    Slots duplicate seven exact method replacements. Their normalized bodies
    are identical, so the compiler warnings represent redundant rather than
    behaviorally conflicting replacements.
26. Better Leveling Addon - Skill Progression and Upgrade Weapons Unlocked both
    shipped complete `CraftingSystem.UpgradeItem(wref<GameObject>, ItemID)->Void`
    implementations as wrappers without `wrappedMethod`. Calling through is
    unsafe because it would run material removal, XP, and item mutation twice.
    `Better Leveling Addon - Upgrade Weapons Unlocked Compatibility-1.0.0.zip`
    removes Better Leveling's duplicate annotation, converts Upgrade Weapons
    Unlocked's full implementation to explicit replacement semantics, and
    integrates Better Leveling's Technical 150 double-step and weapon-damage
    bonus into that single body. Focused static validation is clean, and the
    user confirmed the wrapper-chain report disappeared after deployment and
    rescan. Full gameplay verification remains deferred.
27. Sixty-nine other exact method signatures form compatible cross-mod wrapper
    chains in which every installed wrapper invokes `wrappedMethod`. Twenty-six
    active wrappers across 12 mods omit that call and remain explicit review
    findings even when no other installed mod wraps the same signature.
28. Immersive First Person raised a live CET Lua error at
    `Modules\GameSettings.lua:171`: `attempt to index a nil value`.
29. No Shooting Delay `init.lua:3` requires `Modules/main.lua`, which does not
    exist in its deployed CET root. The complete `main()` implementation is
    already defined later in the same entrypoint and invoked during `onInit`,
    so this is a stale import rather than a missing functional dependency.
    Empirical pre-fix state confirms CET 1.37.1 continued past it: the mod was
    repeatedly logged as loaded, its per-mod log contained no error, and its
    `onInit` code created `buffer.json` and updated `config.json`. Treat the
    finding as a real but currently non-fatal packaging defect.
    `No Shooting Delay - Missing Module Require Fix-1.0.0.zip` removes only
    that import and bundles the three unchanged module files so the complete
    CET root remains under one package. The user deployed it and confirmed the
    missing-module report disappeared.
30. CET rejected `MenuScenario_PauseMenu.OnSwitchToCredits` because the method
    is absent in current game RTTI. Five active mods bundle table-driven GameUI
    helpers with that legacy row, but only `CsBreachingBreached` requests the
    `MenuNav` event that initializes the affected observer table; the other
    four use only session events. Newer GameUI copies omit the row. A complete
    three-file Breaching override removes only that dead mapping. The user
    deployed it and confirmed the runtime finding disappeared.
31. Six literal `GetMod` calls target five absent CET roots. All were manually
    verified as safe optional/detection integrations: Immersive First Person
    converts `BetterVehicleFirstPerson` presence directly to a boolean; Minimap
    Widgets gates and falls back from its `TimeIsRunningOut` clock mode;
    Personal Link Animations Patch looks for its obsolete predecessor; RadioExt
    guards both `trainSystem` and `stationSys`; and Redscript and CET Mods
    Settings checks for incompatible `UnifiedModSettings`. No package or
    dependency is needed; acknowledge the consolidated review finding.
32. The known Damage Scaling Extended and Classic Drinks CET entry winners are
    detected. Extended intentionally imports two active helper modules supplied
    by the standalone Damage Scaling package in the merged `DamageScaling` root.
33. Thirty-six participant groups observe 81 shared hook targets. CET retains
    those callbacks, so the overlaps are informational rather than replacement
    conflicts.
34. Two legacy GameHUD targets have normalized-identical terminating overrides
    across 0-Engine, Missing Persons, and Pacifica Typhoon. Two Native Settings
    tab paths are also deliberately shared; neither case remains a review-level
    finding.
35. `DamageScaling` is the only active CET root built from multiple Vortex
    packages. Its 14 reachable explicit global functions all belong to the
    Extended entry; the imported standalone GameUI/GameSettings modules expose
    local returned tables, so no cross-package global collision exists.
36. Night City Skies concatenates two root objects in
    `NightCitySkies.schema.json`; strict parsing stops at line 51. The installed
    Redscript Config Framework reads each schema file as one JSON object. The
    deployed local repair intentionally replaces that malformed provider with
    a valid empty `{}` schema. `CFG-PATH-OVERRIDE` remains factually correct but
    is an expected repair-lineage notice and should be acknowledged, not fixed
    again.
37. Missing Persons `languages\es-es.json` is a complete Windows-1252 JSON
    document rather than an isolated bad byte: 16 non-ASCII bytes encode its
    en dash and accented Spanish characters. A one-file UTF-8 exact-path
    override preserves the same 25 entries and semantic hash. The user deployed
    it and confirmed the encoding report disappeared.
38. Four configuration scopes have multiple intentional owners:
    `cet:WeatherSwitcher`, `engine-config`, `r6-input`, and
    `redscript-user-hints`. No exact JSON/TOML/INI/XML path is supplied by more
    than one package.
39. Twenty-one Input Loader targets are shared by multiple mods, and every
    provider uses `append="true"`. Their nested action/include identities do not
    conflict, so Input Loader retains all contributions.
40. Dodge Dash Sprint with Shift intentionally replaces the vanilla
    `Dodge_Button`; its `ToggleSprint_Button` definition is identical to the
    current vanilla definition. Both generated caches match all seven active
    fragments, and the startup log contains no diagnostics.
41. All 19 selected native DLL/ASI files match their deployed copies. Their PE
    tables contain 232 hard imports; the only game-local import is RadioExt's
    resolved `fmod.dll` companion. RED4ext 1.30.0 confirms 13 plugin
    entrypoints on game product 2.31 / executable 3.0.80.51928. CET 1.37.1
    reports the same executable version, and native logs add no diagnostics.
42. Better Armor Tooltip 1.0.1 declares 19 on-screen localization resources but
    packages only 18; `es-mx.json` alone is absent. A version-specific package
    removes the broken declaration from the original exact-path config and
    re-registers `es-mx` through a one-resource companion archive using the
    author's existing Spanish translation. The user deployed it and confirmed
    the report finding disappeared.
43. NCEE NPC 2.0.3 similarly declares 19 on-screen localization resources but
    omits only its Italian payload. Cleanup 1.1.0 supplied a cooked 14-entry
    resource through a separate Italian-only `.xl`; ArchiveXL treated its sole
    locale as fallback under English and then reported seven secondary-key
    overwrites when the main NCEE config loaded. Cleanup 1.1.1 removes that
    separate config, keeps Italian in NCEE's main locale map, and supplies only
    the companion archive. The user deployed 1.1.1 and confirmed the remaining
    localization warnings disappeared after the next launch/rescan.
44. Quickhack Fixes changes `Items.IntrinsicFabricEnhancer10_inline2` into a
    combined modifier with value `1` to transfer the Wreath clothing mod's
    intrinsic upload bonus into a custom stat; a separate GLP applies the final
    `0.01` conversion to quickhack upload-time decrease. Clothing Improved's
    CET `onInit` later overwrites that value with `-0.01`, reversing and reducing
    the transfer by 100 times. Its source labels the flat unknown and merely
    repeats the old vanilla value. The one-file
    `Clothing Improved - Quickhack Fixes Wreath Compatibility-1.0.0.zip`
    removes only that redundant runtime write. Focused static/cross validation
    is clean, and the user confirmed the report disappeared after deployment
    and rescan. Functional Wreath verification remains deferred.
45. Always First Equip 2.1.5 intentionally terminates
    `EquipCycleDecisions.ToFirstEquip(ref<StateContext>,
    ref<StateGameScriptInterface>)->Bool` by returning `false` without calling
    `wrappedMethod`. It disables the vanilla transition decision and supplies
    its own configurable first-equip flow through
    `FirstEquipSystem.HasPlayedFirstEquip` and a complete
    `EquipmentBaseTransition.HandleWeaponEquip` replacement. It is the only
    installed annotation for `EquipCycleDecisions`, and the current compiler
    session succeeds. `RS-WRAPPER-SKIPS-WRAPPED-METHOD` is therefore an
    intentional single-mod review finding, not a current compatibility fault.
46. Cyberware-EX 1.5.6 intentionally terminates
    `PlayerDevelopmentData.HandleAddingPerkLevel(Int32,Int32)->Void`. The
    locally decompiled vanilla method powers up musculoskeletal slots 0–2 when
    Technical Central Milestone 3 reaches level 3; Cyberware-EX supersedes that
    fixed three-slot body with `ApplyAreaPowerUps`, which iterates every slot in
    the expanded area. No other active installed annotation targets the exact
    signature. Calling the vanilla body as well would duplicate its work on
    slots 0–2, so the scanner review finding should be acknowledged rather than
    patched.
47. Dodging Fix 0.11 intentionally terminates
    `TweakAIActionRecord.GetActionRecordFromSelector(...)`. Its body is the
    current vanilla selector traversal plus an in-loop dodge fallback: if the
    normal activation check rejects an action with the Dodge ticket, it accepts
    that action when its own activation condition succeeds. Calling vanilla
    before or after cannot reproduce an edit inside that traversal, and no
    other installed script annotates the exact signature. The scanner finding
    is an intentional full-method repair rather than a missing cooperative
    call.
48. Equipment-EX 1.2.9 intentionally terminates
    `UIInventoryItemsManager.IsItemTransmog(ItemID)->Bool`. Vanilla checks its
    six-slot transmog cache, while Equipment-EX reports ownership from its
    active persistent `OutfitSystem`. Equipment-EX imports vanilla clothing
    sets on first use, invalidates the active vanilla set on restore, disables
    vanilla wardrobe equip/unequip handlers, and routes wardrobe UI behavior
    through the replacement system. Combining both answers would retain stale
    vanilla ownership. No other installed script targets the signature, so the
    scanner review finding should be acknowledged without a patch.
49. NCA Standard Density 2.2.1 intentionally terminates
    `ReactionManagerComponent.CanTriggerAlertedFromHostileStim(...)`. Vanilla
    rejects all Prevention-system owners before applying the direct-alert
    stimulus filter; NCA removes that blanket exclusion while retaining the
    filter. Adjacent NCA hooks explicitly process selected Prevention stimuli
    and turn non-player gunshot Intruder reactions into lower-priority
    Investigate reactions. Restoring vanilla would defeat that coordinated
    behavior. No other installed script targets the signature, so acknowledge
    the scanner review finding without a patch.
50. Retrievable Weapon Mods 1 intentionally terminates
    `InventoryItemModeLogicController.EquipPart(...)`. Its full edited vanilla
    body changes every occupied eligible slot into the game's normal
    `SwapItemPart` transaction so the displaced non-base weapon mod is removed
    with uninstall/UI updates and the selected mod is installed, rather than
    following vanilla's occupied-weapon rejection/destructive replacement
    route. Calling vanilla too would perform a second attachment transaction.
    Attachments Unrestricted has an old wrapper for the exact method only in a
    block comment, so there is no active cross-mod annotation conflict. The
    scanner finding should be acknowledged without a patch.
51. Attachments Unrestricted 1 intentionally terminates the paired
    `InventoryItemModeLogicController.GetMatchingSlot(...)` and
    `IsMatchingSlot(...)` selectors. They reproduce vanilla routing while
    adding the mod's TweakXL-defined `HasScopeEquipped` and
    `HasMuzzleEquipped` classifications plus selected-slot fallback needed for
    unrestricted attachments. Its `EquipItem` wrapper uses these results and
    applies the optional one-scope/silencer/muzzle-brake rules before calling
    `EquipPart`. No other installed script targets either exact selector, and
    the flow composes with Retrievable Weapon Mods' occupied-slot swap. The two
    scanner references should be acknowledged without a patch.
52. Inventory Adjustments Hub 1.4 intentionally terminates both
    `ItemTooltipModController.SetData` attachment-data overloads. They reproduce
    vanilla widget construction while selecting description, name, or both;
    calling vanilla too would clear/rebuild the same container. No other
    installed script targets either overload. There is a separate upstream
    edge case when IAH is globally disabled with its default `Name` scheme:
    neither the disabled name nor skipped descriptions are rendered, leaving a
    non-empty attachment tooltip blank. Normal default operation has IAH
    enabled. Acknowledge the compatibility finding, retaining disabled-mode
    testing as a possible small fix package.
53. They Will Remember 2.5a intentionally terminates two detection methods.
    Its `SecurityTurret.SetAsIntrestingTarget` returns `false` only for the
    player when TWR classifies the turret as friendly and otherwise performs
    vanilla's sole action, the superclass call. Its
    `SenseComponent.OnDetectionReachedZero` clears TWR's three monitoring flags
    and then performs vanilla's sole detection reevaluation. Calling vanilla too
    would respectively defeat the friendly-turret exclusion or duplicate the
    reevaluation. No other installed scripts target the exact methods; both
    scanner references should be acknowledged without a patch.
54. Better Leveling Addon - Skill Progression 1.0.1 has four terminating
    wrappers. The two skill-bar methods are intentional level-150 UI
    replacements. The two movement methods reproduce vanilla while multiplying
    air-dodge/air-dash impulse by `1.5`, so they also cannot call vanilla a
    second time. However, the movement code has no Reflexes >=85 check and the
    `BTL.ReflexesLevel85` record contains only UI data, so the advertised
    level-85 bonus is active from a fresh character. No other installed scripts
    target the four signatures. `Better Leveling Addon - Reflexes Level 85 Gate
    Fix-1.0.0.zip` is a one-file exact-path override that makes the two movement
    wrappers cooperative: each calls the existing method, then adds only the
    extra 50% eligible air impulse when Reflexes is at least 85. The unchanged
    skill-bar replacements remain intentional review findings. The fix passes
    the official REDscript linter against the installed `final.redscripts`.
    The user deployed it and confirmed the two movement findings disappeared;
    the remaining intentional skill-bar finding was acknowledged. Deferred
    below/at-level-85 gameplay validation remains pending.
55. Smaller Cyberware Slots (7x3) has four terminating wrappers on
    `CyberwareInventoryMiniGrid`: `SetupData`, `UpdateData`, `SetPosition`, and
    `SetPosition_Animation`. Each is a current-vanilla-derived full replacement
    that changes the wrapping-column cap and matching panel offsets for a
    seven-column grid. Calling vanilla as well would rebuild the slot grid or
    start its positioning animation twice. No other installed script targets
    these exact four signatures; Cyberware-EX replaces only the distinct
    `GetSlotToEquipe` method. The grouped review finding is intentional and can
    be acknowledged without a patch.
56. Upgrade Weapons Unlocked has four additional terminating wrappers retained
    by the Better Leveling compatibility package: `GetUpgradableList`,
    `FillInventoryData`, `GetItemTierForUpgrades`, and `ApplyQualityModifier`.
    They are intentional full replacements implementing non-iconic weapon
    enumeration, corrupt tier repair/filtering, tier reconciliation, and the
    complete quality/Plus progression state machine. Calling vanilla too would
    duplicate inventory processing or quality mutation. No unrelated installed
    mod targets the four exact signatures; the grouped review finding can be
    acknowledged without another patch.
57. The archive overlap on
    `base\open_world\minor_activities\watson\northside\ma_wat_nid_22\`
    `ma_wat_nid_22_phase.questphase` between Immersive Gigs 2.1 and Minor
    Activities Quest Fixes 1.12.1 is a real, mergeable conflict. WolvenKit
    extraction and CR2W JSON serialization showed that the Minor Activities
    resource differs from current vanilla in exactly one non-handle value:
    phase node 171, nested event node 25,
    `VehicleQuestVisualDestructionEvent.frontLeft` changes from `1` to `0`.
    Immersive Gigs retains `1` but adds 16 top-level nodes and rewires the graph
    for its cyberpsycho acquisition/call behavior. The private package
    `Immersive Gigs - Minor Activities Quest Fixes Compatibility-1.0.0.zip`
    starts from the Immersive Gigs file and changes only this flag to `0`.
    WolvenKit JSON/CR2W round-trip validation preserved all 114 top-level nodes,
    and archive re-extraction matched the validated CR2W hash exactly. Its
    archive is named `! 00_immersive_gigs_minor_activities_compat.archive`.
    Because the game currently has `archive/pc/mod/modlist.txt`, the user must
    place this compatibility archive before both source archives in that list
    (normally through Archive Conflict Checker); filename order alone is not
    effective while the modlist exists.

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
CET coverage records active roots, entrypoints, lifecycle/binding registrations,
literal module and `GetMod` dependencies, hook and Native Settings operations,
dynamic calls, inactive references, unresolved imports, and shared hook targets.
The current framework/scripting/per-mod log pass records CET/game versions,
loaded/ignored/failed roots, source-attributed runtime events, and compact
findings. Definite explicit global writes are compared across packages inside
merged roots. Computed names and ambiguous lexical writes remain partial rather
than being guessed.
Configuration coverage records format-level parse/entry/encoding results,
format-normalized semantic fingerprints, exact shared paths, and broader
multi-package ownership scopes. Input Loader coverage separately records XML
node/reference counts, vanilla replacements/appends, cross-mod identities,
missing targets, generated-cache mismatches, and current startup-log results.
Native coverage records DLL/ASI hashes and deployed equality, PE imports,
fixed file versions, RED4ext runtime names/versions/authors, companion-library
classification, framework/game versions, and direct/delegated plugin-log state.
All findings carry fingerprints plus active/acknowledged and scan-change state.
The four known Vortex exact-path winners are acknowledged in
`acknowledgements.yaml`,
leaving 181 active and four acknowledged findings. The current diff baseline
contains 185 unchanged findings and no new, changed, or resolved entries.
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
REDscript coverage analyzes all four installed compatibility annotations using
exact class and method signatures. It normalizes array shorthand, legacy
callback return fallback, and expression-bodied methods; evaluates all observed
installed-module conditions; and excludes the one Vortex-overridden script from
effective comparisons while retaining it in the reference inventory. The
current compiler log confirms all eight active replacement-overwrite warnings.

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
- `reports/current/redscript-findings.json`
  All REDscript annotation references, condition/deployment state, static
  compatibility findings, and correlated compiler diagnostics.
- `reports/current/cet-findings.json`
  CET Lua registrations, dependencies, hooks, namespace findings, and runtime
  diagnostics.
- `reports/current/config-findings.json`
  Shared JSON/TOML/INI/XML ownership, parsing, and exact-path findings.
- `reports/current/input-findings.json`
  All Input Loader XML references with source lines, merge findings, vanilla
  comparison, generated-cache validation, and startup-log coverage.
- `reports/current/native-findings.json`
  Native DLL/ASI references, hashes, versions, PE dependencies,
  deployed/runtime state, and native framework findings.
- `reports/current/cross-ecosystem-findings.json`
  CET-to-REDscript method overlaps with operation-aware classifications and
  both ecosystems' source references.
- `reports/current/compatibility-findings.json`
  Combined machine-readable findings without the full reference inventories.
- `reports/current/compatibility-diff.json`
  New, changed, resolved, and unchanged findings relative to the previous
  report generated in the same output directory.
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
