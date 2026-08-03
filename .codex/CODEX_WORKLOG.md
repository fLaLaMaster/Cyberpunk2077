# Codex Worklog

This is a chronological handoff log. Add new entries at the top of the History
section. Record material changes, decisions, validation, and generated outputs;
do not use it as a raw command transcript.

## Current state

- Scanner version: `0.19.0`
- Implemented ecosystems: ArchiveXL, TweakXL, REDscript, and CET Lua
- Primary report: `reports/current/compatibility-report.html`
- Automated tests: 89 passing
- Last complete scan: successful on 2026-08-03
- Frozen inputs were not modified

## History

### 2026-08-03 — CET explicit global-symbol analysis

Completed conservative global-namespace analysis for CET roots assembled from
multiple Vortex packages.

Changes:

- Extracted definite top-level global assignments and named functions while
  suppressing known `local` roots and fields inside table constructors.
- Added explicit `_G`, `_ENV`, literal indexed, and `rawset` writes, including
  an inventory count for computed keys that cannot be resolved statically.
- Compared exact symbols only among reachable active files from different
  packages inside the same CET root. Separate roots remain isolated.
- Added `CET-GLOBAL-SYMBOL-SHARED` review findings and global/merged-root
  coverage to JSON, Markdown, and HTML.
- Bumped scanner version to 0.19.0 and completed the corresponding TODO item.

Validation:

- All 89 tests pass with warnings promoted to errors, including merged-root,
  separate-root, local-table, explicit-environment, and computed-key cases.
- The frozen corpus contains 492 reachable definite global writes and two
  reachable computed global writes across 64 source files.
- `DamageScaling` is the only active CET root assembled from more than one
  Vortex package. It contains no exact global symbol written by both packages;
  the imported standalone GameUI/GameSettings modules keep their tables local.
- The full cached scan completed in 27.5 seconds. CET references increased to
  3,105 with no null source lines and no new finding; the combined result stays
  at 177 findings.
- Frozen Vortex and game inputs were not modified.

### 2026-08-03 — CET Lua and runtime-log analysis

Implemented the first CET compatibility analyzer using the frozen Vortex
corpus, current CET logs, and official Cyber Engine Tweaks source at commit
`9a8522f2a3d66729d971c48ae48f1053abfb5208`.

Changes:

- Added a source-preserving Lua lexer and CET root/entrypoint discovery without
  executing mod code.
- Extracted lifecycle events, shared hotkey/input IDs, literal `require` and
  `GetMod` dependencies, observers, overrides, and Native Settings paths.
- Resolved modules through CET's exact/`.lua`/`init.lua` root-local lookup and
  followed top-level literal imports to determine reachable active code.
- Distinguished Vortex-overridden entries, isolated per-root sandboxes,
  additive observer targets, pass-through override chains, duplicate
  terminating callbacks, shared settings containers, and shared leaf controls.
- Parsed `cyber_engine_tweaks.log`, `scripting.log`, and canonical per-root logs
  for load state, missing hook targets, registration/module failures, and Lua
  source errors.
- Added `cet-findings.json`, CET summary and coverage panels in Markdown/HTML,
  a CET HTML ecosystem filter, documentation, and scanner version 0.18.0.

Validation:

- All 88 tests pass with Python warnings promoted to errors.
- A full cached scan completed in 26.9 seconds and parsed 248 Lua files across
  61 active roots into 2,533 references; none has a null source line.
- Current CET 1.37.1 logs show 61 loaded roots, two intentionally ignored
  folders without `init.lua`, zero failed roots, one Lua error, and one missing
  hook warning.
- The Lua error maps to Immersive First Person
  `Modules\GameSettings.lua:171` (`attempt to index a nil value`). The hook
  warning targets absent `MenuScenario_PauseMenu.OnSwitchToCredits` but CET's
  global scripting log does not identify which bundled GameUI helper emitted it.
- No Shooting Delay `init.lua:3` requires absent `Modules/main.lua`. Six missing
  literal `GetMod` targets remain review-level because the surrounding code may
  treat those integrations as optional.
- The known Damage Scaling and Classic Drinks entry winners were recognized.
  Damage Scaling Extended intentionally imports two modules supplied by the
  standalone package in their merged root.
- Thirty-six cross-root observer groups are additive. Two legacy GameHUD
  override targets contain identical terminating callbacks, and two shared
  Native Settings tab paths are informational rather than compatibility
  conflicts.
- The combined report contains 177 findings: 2 conflicts, 10 errors, 17
  warnings, 13 reviews, and 135 informational findings.
- Frozen Vortex and game inputs were not modified.

### 2026-08-03 — REDscript annotation and compiler-log analysis

Implemented the first complete REDscript compatibility analyzer using the
installed corpus, current compiler log, and official redscript compiler source
at commit `3ca666c8ec14cfc803ef3888aab6ebc7a1c2bb86`.

Changes:

- Added source-preserving lexical parsing for `@wrapMethod`, `@replaceMethod`,
  `@addMethod`, and `@addField`, including multiline declarations, nested
  generic/array types, callback return fallback, and expression-bodied methods.
- Identified methods by exact target class, name, parameter types, and return
  type; parameter names and visibility are intentionally excluded to match the
  compiler's annotation resolution.
- Indexed installed module declarations and evaluated every observed
  `@if(ModuleExists(...))` / negated branch. Vortex-overridden scripts remain in
  the reference inventory but are excluded from effective comparisons.
- Classified competing versus normalized-identical method replacements,
  duplicate added methods/fields, annotations targeting added methods,
  compatible wrapper chains, terminating shared wrapper chains, and wrappers
  that never invoke `wrappedMethod`.
- Added `redscript_rCURRENT.log` parsing with source-path/line attribution,
  exact static-signature correlation, compilation status, and compact
  diagnostic findings.
- Added `redscript-findings.json`, REDscript summary/coverage panels in
  Markdown and HTML, a REDscript HTML ecosystem filter, and scanner version
  0.17.0.

Validation:

- All 83 automated tests pass with warnings promoted to errors.
- The frozen corpus contains 1,235 REDscript artifacts. The current compiler
  compiled 1,234 deployed files; the remaining staging file is the expected
  Vortex-overridden standalone Damage Scaling script.
- Parsed 16,775 real annotations with exact source lines and zero parser
  failures. Effective active operations are 700 wrappers, 139 replacements,
  14,024 added methods, and 1,885 added fields; 27 conditional/overridden
  annotations are inactive in the installed setup.
- Found 70 exact signatures wrapped across mods. Sixty-nine chains preserve
  all lower behavior; one `CraftingSystem.UpgradeItem` chain combines Better
  Leveling Skill Progression with Upgrade Weapons Unlocked and contains a
  wrapper that does not call `wrappedMethod`.
- Found one genuine competing replacement:
  `DoubleJumpDecisions.EnterCondition` from Cyberware-EX and VanillaPlus
  Parkour. The compiler log confirms the later replacement overwrite.
- Found seven normalized-identical replacement duplicates between 6 More
  Weapon Mod Slots and the Cyberdeck 2x Quickhack Slots package. The compiler
  confirms all seven overwrites, but the final replacement bodies are
  equivalent.
- The 1,277-line current compiler log reports zero errors, eight warnings,
  successful compilation, and a saved modded output. All eight diagnostics are
  attributed and statically confirmed in two compact runtime findings.
- The full cached scan completed successfully in about 26 seconds. The combined
  report now contains 130 findings: 2 conflicts, 9 errors, 15 warnings, 12
  reviews, and 92 informational findings.
- Frozen Vortex and game inputs were not modified.

### 2026-08-03 — ArchiveXL streaming node-mutation semantics

Completed static and runtime-aware analysis of ArchiveXL
`streaming.nodeMutations` using the installed upstream WorldStreaming
implementation.

Changes:

- Parsed node transforms, effective resource/appearance/record aliases,
  positive proxy-node deltas, expected actor/instance counts, and nested
  actor/instance transform mutations with exact source lines.
- Compared same-node writes by effective property and classified type/count
  disagreements, conflicting last-wins values, idempotent repeats, disjoint
  operations, and the special destructive-instance reset behavior.
- Compared node mutations against full and partial deletions, including the
  static-mesh and instanced-mesh scale cases that can revive deleted content.
- Added compact warnings for unknown fields and accepted-but-ignored mutation
  operations rather than silently discarding them.
- Replaced generic review findings for shared sectors with high-confidence
  node-disjoint information when every cross-mod node index is distinct.
- Added ArchiveXL runtime parsing and attribution for node-type and
  actor/instance-count validation failures, including their following
  `No patches have been applied` consequence messages.
- Added world-streaming operation coverage to JSON, Markdown, and HTML reports
  and bumped the scanner to version 0.16.0.

Validation:

- All 79 automated tests pass with warnings promoted to errors.
- The complete cached scan succeeded in about 20 seconds and now emits 60,343
  ArchiveXL references: 1,314 node mutations and 279 nested element mutations
  add 1,593 references to the v0.15 baseline.
- The mutation analyzer records 1,728 node-property writes and 422 effective
  element-property writes. No node mutation identity is shared by two mods.
- It found 10 ignored operations and 9 unknown fields in the installed corpus,
  consolidated into two high-confidence warnings with exact evidence lines.
- Thirteen Immersive Night City Fixes mutations overlap full deletions from 4x
  Vending Machine Framework; the deletions dominate, so the result is
  informational redundancy rather than incompatibility.
- Across shared sectors, 344 sectors in 14 participant groups touch disjoint
  node indices. The previous 16 generic streaming review groups are gone.
- The overall report contains 60 findings: 1 conflict, 9 errors, 11 warnings,
  no review findings, and 39 informational findings.
- Frozen Vortex and game inputs were not modified.

### 2026-08-03 — ArchiveXL player body-type semantics

Completed declaration-level analysis of ArchiveXL `player.bodyTypes` using the
installed upstream PuppetState implementation.

Changes:

- Accepted ArchiveXL's scalar-or-sequence form and retained exact one-based
  source lines for every valid scalar.
- Added `AXL-PLAYER-SHAPE` for non-scalar declarations while preserving valid
  scalar registrations from a mixed sequence, matching ArchiveXL's behavior.
- Extracted case-sensitive `player.body_type` references and their effective
  `Body:<name>` tag identities.
- Added high-confidence informational detection for exact cross-mod duplicate
  registrations. Distinct names compose; exact repeats are idempotent because
  ArchiveXL inserts the body types and tags into global set/map containers.
- Added player-operation coverage to JSON, Markdown, and HTML reports and
  bumped the scanner to version 0.15.0.

Validation:

- All 74 automated tests pass with warnings promoted to errors.
- The frozen corpus contains one player document and one registration:
  `ANGEL` / `Body:ANGEL` at `ANGEL.xl` line 27.
- No installed mod shares that body type, so the new analyzer adds no finding.
- The complete cached scan succeeded in about 20 seconds and now emits 58,750
  ArchiveXL references. The overall 59-finding distribution is unchanged.
- No PuppetState-specific error appears in the newest ArchiveXL runtime logs.
- Frozen Vortex and game inputs were not modified.

### 2026-08-03 — ArchiveXL streaming-node deletion semantics

Replaced the blanket duplicate-deletion conflict with classifications derived
from ArchiveXL's installed WorldStreaming implementation.

Changes:

- Preserved full/partial/effective deletion scope, native node type, expected
  actor/instance counts, and scalar or actor/shape element identities.
- Classified repeated same-type full-node deletions as high-confidence
  idempotent information because ArchiveXL hides/moves nodes without erasing or
  renumbering the node buffer.
- Classified ordinary partial actor/instance deletions as composable, and
  full-plus-partial overlaps as redundant but safe.
- Kept native-type and expected-element disagreements as conflicts because
  ArchiveXL validates them before applying the complete sector patch.
- Added a dedicated conflict for multiple collision-shape deletion patches on
  one node. ArchiveXL reuses a sector/node collision-preset allocation while
  increasing its logical size on a later patch, so that path is not safely
  idempotent.
- Bumped the scanner to version 0.14.0 and updated README/TODO guidance.

Validation:

- All 70 automated tests pass, including full, partial, type/count mismatch,
  and collision-shape cases.
- The corpus contains 10,812 node-deletion references: 10,635 declared full and
  177 declared partial, resolving to 10,672 effective full and 140 effective
  partial operations. ArchiveXL treats 36 foliage and one instanced-occluder
  declaration with element lists as whole-node deletions.
- All 40 cross-mod overlaps across five participant groups are same-type full
  deletions and are now informational. No installed partial or collision-shape
  overlap exists.
- The report remains at 59 findings, but the distribution changes from six
  conflicts and 19 infos to one conflict and 24 infos.
- Frozen Vortex and game inputs were not modified.

### 2026-08-03 — ArchiveXL character-customization analysis

Completed static and payload-level analysis of ArchiveXL `customizations`.

Changes:

- Parsed exact `female`/`male` declarations with structural source lines and
  resolved every resource against its declaring mod archive.
- Added selective serialization of `.inkcharcustomization` resources and
  ArchiveXL-equivalent identities for arms/body/head groups, named options,
  anonymous `uiSlot`/`link` selectors, and appearance/morph/switcher choices.
- Modeled anonymous appearance inheritance, named linked-option content,
  case-sensitive identities, wildcard slot matching, native-type rejection,
  and last-wins choice replacement.
- Added composable, duplicate, conflict, metadata-review, and selector-review
  rules with participant-set consolidation.
- Added `customizations` as a payload-scope choice and exposed group, option,
  choice, cache, and outcome counts in Markdown/HTML coverage.
- Added ArchiveXL runtime recognition and attribution for character
  customization native-type mismatch warnings.
- Bumped the scanner to version 0.13.0 and updated README/config guidance.

Validation:

- All 65 automated tests pass; bytecode compilation and `git diff --check`
  succeed.
- The frozen corpus contains 30 declarations over 29 unique payloads; all 29
  serialized successfully with zero failures.
- Extracted 720 group entries, 335 options, and 8,455 choices (9,510 merge
  identities).
- Found two composable overlaps: the female and male `eyebrows` switchers from
  Beautiful Eyebrows 01 and 02. No customization conflict, duplicate, or review
  identity remains.
- First population took 110.9 seconds; the fully cached complete scan took
  19.7 seconds and regenerated the searchable HTML report.
- Frozen Vortex and game inputs were not modified.

### 2026-08-03 — ArchiveXL visual-tag override analysis

Completed static `overrides.tags` parsing and comparison against the frozen
collection.

Changes:

- Added structural parsing for tag/component definitions using `hide` and
  `show` chunk lists, shorthand hide lists, and unsigned decimal masks.
- Converted declarations to ArchiveXL-equivalent 64-bit component masks while
  retaining tag, component, operation, chunk, and one-based line evidence.
- Added strict shape checks for invalid operations, mask types, and out-of-range
  chunk indices.
- Added case-sensitive, whole-tag comparisons: identical same-name definitions
  are informational duplicates, while differing definitions are conflicts
  because ArchiveXL replaces the complete earlier tag in load order.
- Added review findings for redefinitions of ArchiveXL's built-in garment tags
  and dedicated override coverage tables in Markdown and HTML.
- Bumped the scanner to version 0.12.0.

Validation:

- All 60 automated tests pass.
- A full cached frozen-corpus scan completed successfully in 19.7 seconds;
  staging and game inputs were not modified.
- Four documents contain 12 tag definitions, 14 component definitions, and 31
  chunk references.
- No tag is shared across mods, no installed definition replaces an ArchiveXL
  built-in tag, and no override finding was added.
- Reports remain at 58 findings: 6 conflicts, 9 errors, 9 warnings, 16 reviews,
  and 18 infos.
- Semantics were verified against ArchiveXL's official Garment `Config.cpp`,
  `Extension.cpp`, `Tags.cpp`, and `ChunkMask.hpp` at source revision
  `55f48569f415b443debba4f4ad4cf241194cd06e`.

### 2026-08-03 — ArchiveXL journal analysis

Completed static journal-resource inspection and runtime correlation against
the frozen collection.

Changes:

- Added structural extraction and validation of scalar/list `journal`
  declarations, including one-based source lines and archive/loose-resource
  resolution.
- Selectively serialized `gameJournalResource` payloads and reconstructed
  effective slash-delimited entry paths, final `*` edit markers, entry types,
  properties, and stable payload fingerprints.
- Added case-sensitive comparison rules for composable shared containers,
  duplicate/conflicting leaf entries, and duplicate, overlapping, or
  incompatible property edits.
- Added `journals` as a payload scope, journal payload statistics to Markdown
  and HTML coverage, and ArchiveXL journal runtime error attribution.
- Bumped the scanner to version 0.11.0.

Validation:

- All 57 automated tests pass.
- A full cached frozen-corpus scan completed successfully in 19.8 seconds;
  staging and game inputs were not modified.
- All three declared journal resources serialized successfully into 232 entry
  references. The only shared identity is the `contacts` folder, which is a
  composable container across NCEE NPC, Shard Audio Framework, and They Will
  Remember.
- No journal duplicate, conflicting, or review-worthy leaf/edit identity was
  found. The current ArchiveXL runtime session also reports that all three
  journal resources merged successfully.
- Reports now contain 58 findings: 6 conflicts, 9 errors, 9 warnings, 16
  reviews, and 18 infos.

### 2026-08-03 — ArchiveXL quest phase analysis

Completed static `quest.phases` parsing, comparison, dependency resolution, and
runtime confirmation against the frozen collection.

Changes:

- Added structural extraction of child phase paths, parent targets, and
  `connection`/`input` attachment descriptors with one-based lines.
- Added shape validation, exact duplicate-merge warnings, and conservative
  review findings for the same child/parent pair using different attachment
  points. Merely sharing a parent remains explicitly composable.
- Resolved child and custom parent paths against indexed mod archives and loose
  resources. Official `base`, `ep1`, and `dlc` parents are recognized without
  indexing the game's large vanilla archives.
- Consolidated repeated missing targets while retaining every declaration as
  evidence, and correlated ArchiveXL runtime missing-phase messages with the
  exact static child or parent rule.
- Added a Quest operations table to Markdown and HTML coverage and bumped the
  scanner to version 0.10.0.

Validation:

- All 53 automated tests pass.
- A full cached frozen-corpus scan completed successfully in 19.5 seconds;
  staging and game inputs were not modified.
- Parsed 298 phase merges from 13 documents. There are no cross-mod duplicate
  child/parent operations or competing attachment points.
- 296 child declarations resolve in their own mods. Two declarations share one
  missing They Will Remember phase resource.
- 229 parent references are official game targets. The remaining 69 references
  consolidate to three absent New Game Plus parents used by HG Enemies, NCEE
  Enemies, and NCEE NPC.
- All four static missing targets exactly confirm the four runtime quest
  missing-phase events.
- Reports now contain 57 findings: 6 conflicts, 9 errors, 9 warnings, 16
  reviews, and 17 infos.

### 2026-08-03 — ArchiveXL runtime log correlation

Finished ArchiveXL runtime analysis using the user's fresh new-save launch.

Changes:

- Added newest-session discovery for ArchiveXL logs and chronological parsing
  of numbered rotation chunks before the continuing unnumbered log.
- Streamed large logs instead of loading them into memory; the real session is
  about 138 MB across two files.
- Added focused rules for missing quest phases, failed localization resources,
  rejected streaming patches, and generic future errors/warnings.
- Paired localization summary warnings and streaming “no patches applied”
  warnings with their preceding root-cause errors while retaining both log
  lines as evidence.
- Attributed localization and streaming failures through semantic ArchiveXL
  references. Missing quest phases are attributed through exact source-text
  declarations because static quest parsing remains a later milestone.
- Added ArchiveXL session/file/byte/line/event coverage to JSON, Markdown, and
  HTML reports, and marked quest coverage partial rather than unsupported.
- Bumped the scanner to version 0.9.0 and documented session-aware analysis.

Validation:

- All 50 automated tests pass.
- A full cached frozen-corpus scan completed successfully in 34.2 seconds;
  staging and game inputs were not modified.
- Parsed session `2026-08-02-23-32-59`: two files, 137,845,003 bytes, 472,639
  lines, two errors, and six warnings.
- All eight events were source-attributed and consolidated into four findings.
- Cyberware EX Keybinds failed to load its English localization resource from
  the declaration at line 3.
- Immersive Night City Fixes expected four nodes for the sector declared at
  line 11,134, but runtime found six and skipped the patch.
- Three missing New Game Plus phase parents affect HG Enemies, NCEE Enemies,
  and NCEE NPC. A separate missing retaliation phase affects They Will
  Remember at lines 63 and 65.
- No runtime event matched an existing static finding, demonstrating that these
  failures complement rather than duplicate current static coverage.
- Reports now contain 53 findings: 6 conflicts, 9 errors, 5 warnings, 16
  reviews, and 17 infos.

### 2026-08-02 — TweakXL runtime log correlation

Finished the planned TweakXL runtime-log pass using the user's clean new-save
launch on the frozen mod collection.

Changes:

- Added newest-log discovery and parsing for timestamped TweakXL logs under the
  configured game directory.
- Tracked `Reading "..."` context so import errors map to the responsible
  deployed tweak file, Vortex staging mod, and source line.
- Correlated post-import hash-only validation warnings through the owning
  TweakDB flat and all matching installed source candidates.
- Added focused rules for failed clones, unknown properties, ambiguous
  definitions, dangling references, and generic future errors/warnings.
- Preserved each runtime event as evidence while consolidating results by rule
  and attributed participant set.
- Correlated failed clone events with matching static missing/case-mismatched
  `$base` findings and added runtime coverage to JSON, Markdown, and HTML.
- Bumped the scanner to version 0.8.0 and documented automatic log analysis.

Validation:

- All 47 automated tests pass.
- A full cached frozen-corpus scan completed successfully in 31.9 seconds;
  staging and game inputs were not modified.
- Parsed the 333-line `TweakXL-2026-08-02-23-33-11.log`: 74 errors and 12
  warnings became seven consolidated findings, with all 86 events attributed
  to staging sources.
- The static capitalization error in Attachments Crafting System was directly
  confirmed at runtime and maps back to line 94.
- Runtime-only failures comprise 12 unknown properties in Better Living Buffs,
  one unknown property in NCEE NPC, 60 ambiguous definitions across More Mods
  More Fun / its compatible patch / 6 More Weapon Mod Slots, and 12 dangling
  references from `Items.TechMod2_Common.placementSlots`.
- Reports now contain 49 findings: 6 conflicts, 7 errors, 3 warnings, 16
  reviews, and 17 infos.
- The same launch also produced ArchiveXL errors/warnings suitable for the next
  planned ArchiveXL runtime-correlation pass; RED4ext and redscript showed no
  matched error/warning lines in the focused sanity check.

### 2026-08-02 — TweakXL record dependency analysis

Finished the planned static `$base`, clone, and foreign-record dependency pass.

Changes:

- Indexed 74,829 named vanilla/expansion records from 2,684 local official
  REDmod `.tweak` sources without modifying the game directory.
- Added exact generated `_inlineN` record verification using CRC32/length
  TweakDBIDs in `tweakdb.bin` and `tweakdb_ep1.bin`.
- Resolved installed `$base` targets against official records and concrete
  `$base`/`$type` providers, and added missing-base, capitalization-mismatch,
  and base-cycle rules.
- Added explicit `t"..."`/`TweakDBID("...")` foreign-key resolution plus a
  conservative implicit pass limited to values exactly matching installed
  custom record providers.
- Compactly aggregated cross-mod dependencies by consumer/provider pair so
  expanded `$instances` references do not overwhelm the HTML report.
- Added TweakXL dependency coverage tables to JSON, Markdown, and HTML reports,
  and bumped the scanner to version 0.7.0.

Validation:

- All 45 unit tests pass.
- A complete frozen-corpus scan finished in 17.83 seconds with cached archive
  payloads; staging and game inputs were not modified.
- All 1,284 `$base` targets resolve except one exact capitalization error, and
  no base cycle or otherwise missing base was found.
- The error is `Items.w_att_scope_sniper_02_legendary` at line 94 of
  Attachments Crafting System; the official record is capitalized
  `Items.w_att_scope_sniper_02_Legendary`.
- Three valid cross-mod custom-record relationships compact 18,758 base and
  foreign-key references. No explicit foreign-key syntax occurs in the frozen
  corpus.
- Reports now contain 42 findings: 6 conflicts, 1 error, 2 warnings, 16
  reviews, and 17 infos. All 57,455 TweakXL references still have source lines.

### 2026-08-02 — ArchiveXL resource patch payload identities

Replaced generic shared-target patch assumptions with selective CR2W payload
comparison for compatibility-relevant sources.

Changes:

- Selected only resource patch sources participating in cross-mod target
  overlaps: 23 unique sources covering 43 targets and 86 declarations.
- Serialized `.mesh`, `.ent`, and `.devices` payloads through the existing safe
  WolvenKit provider.
- Extracted stable identities from named CR2W objects, patchable scalar
  properties, and C2dArray-like rows, with canonical fingerprints that omit
  serializer bookkeeping such as handle IDs and version metadata.
- Restricted default inspection to documented patchable resource properties;
  explicit ArchiveXL `props` declarations still control the selected fields.
- Added conflict, identical-duplicate, disjoint, and uninspected outcomes with
  medium confidence and consolidated evidence by participant set.
- Removed the declaration-only `AXL-RESOURCE-PATCH-COMPOSABLE` findings when
  payload analysis is enabled, and added a `patches` payload scope option.
- Bumped the scanner to version 0.6.0 and extended report coverage metrics.

Validation:

- Forty unit tests passed.
- First patch payload pass completed in 73.9 seconds; cached scans remain about
  9.5 seconds.
- All 23 selected sources serialized without failure and produced 8,302
  target-scoped stable inner-identity references with non-null declaration
  lines.
- All 43 shared targets are disjoint at meaningful inner identities: 36 citizen
  entities patch components versus appearances, six player hair resources use
  distinct appearance identities, and the shared device database receives
  different device hashes.
- No patch target was conflicting, duplicated, or left uninspected. Overall
  severity totals remain 6 conflicts, 2 warnings, 16 reviews, and 16 infos.
- Regenerated `reports/current`; frozen staging and game inputs were not
  modified.

### 2026-08-02 — ArchiveXL factory payload analysis

Extended selective payload inspection to ArchiveXL factory CSV resources.

Changes:

- Parsed serialized `C2dArray` factory payloads using their `name`, `path`, and
  optional `preload` columns while retaining declaration lines and payload row
  indices.
- Added conflict/informational rules for factory entity names registered by
  multiple mods with different/identical targets.
- Validated every factory target against resources owned by the declaring mod,
  then distinguished cross-mod providers from entirely missing resources.
- Expanded payload scope to `none`, `localization`, `factories`, or `all`, with
  `all` as the tracked configuration default.
- Updated nested payload coverage tables in JSON, Markdown, and HTML, and bumped
  the scanner to version 0.5.0.

Validation:

- Thirty-seven unit tests passed.
- Serialized all six installed factory payloads with zero failures and extracted
  14 factory entity rows.
- All 14 target resources resolve inside their declaring mods. No duplicate or
  competing entity names, cross-mod targets, missing targets, or malformed rows
  were found.
- The first factory-enabled run completed in 29.9 seconds and populated six new
  extraction/serialization cache entries; the fully cached run completed in
  8.97 seconds.
- The overall result remains 40 findings, and all 40,064 ArchiveXL references
  have non-null source lines.
- Regenerated `reports/current`; frozen staging and game inputs were not
  modified. The scanner-cache-only factory probe directory was removed.

### 2026-08-02 — Selective payload provider and localization analysis

Added safe, cache-backed ArchiveXL payload inspection and used it for on-screen
localization resources.

Changes:

- Added an archive payload provider interface and WolvenKit implementation.
- Verified requested resources against indexed archive manifests, mapped them
  only below `.cache/archives/<sha256>/extracted`, and rejected absolute or
  traversal paths before tool execution.
- Used numeric FNV-1a resource hashes for exact extraction after confirming that
  passing a resource path to WolvenKit `--hash` can extract multiple related
  members.
- Captured `convert serialize --print` JSON, cached it separately, and recorded
  commands, tool/source versions and hashes, timing, output hashes, and failures
  in per-resource metadata.
- Added cache validation and automatic recovery from missing, corrupt, stale,
  or mismatched payload and serialization entries.
- Added locale-scoped ArchiveXL localization entry references and comparison
  rules for duplicate/conflicting `secondaryKey` and nonzero `primaryKey`
  definitions.
- Added `payload_scope: localization` configuration and CLI override, payload
  coverage statistics in Markdown/HTML, and scanner version 0.4.0.

Validation:

- Thirty-four unit tests passed.
- Cold frozen-corpus scan completed in 546 seconds; the immediate warm-cache
  scan completed in 9.51 seconds.
- Serialized all 181 archive-owned localization payloads with zero failures and
  extracted 4,124 entry references. Four declarations without a resource in
  their own indexed archive remained covered by existing missing/cross-mod
  resource findings.
- Every warm run used 181 extraction and 181 serialization cache hits.
- No duplicate or conflicting cross-mod localization keys were found, so the
  overall result remained 40 findings: 6 conflicts, 2 warnings, 16 reviews, and
  16 informational findings.
- Regenerated `reports/current`; frozen staging and game inputs were not
  modified. Two scanner-cache-only probe directories were removed after the CLI
  behavior check.

### 2026-08-02 — ArchiveXL resource declarations and coverage

Added declaration-level semantic analysis for every ArchiveXL `resource`
operation installed in the frozen corpus.

Changes:

- Preserved ArchiveXL custom tags such as `!include` with source locations.
- Parsed `resource.patch`, `copy`, `link`, `scope`, and `fix` in their installed
  list and structured `props`/`targets` forms.
- Added references for patch targets, copy/link destinations, scope members,
  and individual fix rewrites.
- Added conflict rules for competing copy/link targets and contradictory fix
  rewrites.
- Added informational rules for composable patch targets, identical redirects,
  and duplicate scope members, plus review handling for patch/redirect overlap.
- Added malformed-shape errors and unknown-operation review findings so future
  syntax cannot be silently ignored.
- Added ArchiveXL analyzer coverage to JSON, Markdown, and a collapsible HTML
  table with analyzed, partial, and unsupported states.
- Bumped scanner version to 0.3.0.

Validation:

- Twenty-seven unit tests passed.
- Full frozen-corpus scan parsed 21,611 resource references with zero null source
  lines and no malformed declarations.
- Observed operations: 19,281 `fix`, 1,267 `scope`, 1,010 `patch`, 39 `link`,
  and 14 `copy` references.
- Found no new resource conflict, warning, review, or parser error.
- Found 43 composable patch-target overlaps across three participant groups and
  four identical redirect targets across the two Beautiful Eyebrows variants.
- Overall baseline is now 35,926 ArchiveXL references and 40 findings: 6
  conflicts, 2 warnings, 16 reviews, and 16 informational findings.
- Regenerated `reports/current`; HTML remains approximately 0.75 MB.
- Frozen staging and game inputs were not modified.

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
