# Codex TODO

Last reviewed: 2026-08-05

This list describes planned scanner work. Reorder it when user priorities
change. Check an item only after implementation, relevant tests, and a real
frozen-corpus validation pass are complete.

## Manual compatibility packages

- [x] Build `Immersive First Person - Settings Shutdown Guard-1.0.0.zip` with a
  nil-safe `GameSettings.Set` for the CET `onShutdown` lifecycle.
- [x] After the user imports and deploys the Immersive First Person guard as the
  winning `GameSettings.lua`, launch and exit the game, then rescan to confirm
  the latest CET session has no Lua callback error.
- [x] Retire the Immersive First Person shutdown guard after the author's major
  update made the local compatibility package unnecessary. Keep the old ZIP
  only as historical output; do not deploy it over the updated mod.
- [x] Diagnose why `Cyberware EX Keybinds - Localization Resource
  Fix-1.0.0.zip` did not resolve the runtime error: cooked resources were
  deployed loose instead of indexed inside a REDengine `.archive`.
- [x] Replace the incomplete Cyberware EX Keybinds 1.0.0 repair with a revised
  Vortex package containing the two cooked localization resources inside a
  game `.archive`.
- [x] After the user imports and deploys the package through Vortex, rerun the
  game and scanner to confirm the ArchiveXL runtime finding is resolved.
- [x] Exclude CR2W-magic `.json` resource files from the shared textual
  configuration analyzer so valid cooked resources do not produce
  `CFG-PARSE-ERROR` findings.
- [x] Build `Night City Skies - Malformed Schema Fix-1.0.0.zip` as a neutral
  `{}` override. The shipped file concatenates unrelated `NCSSkywatch` and
  duplicate `NightCitySkies` JSON roots; the framework accepts one object per
  file, the main mod registers programmatically, and no installed code consumes
  the `NCSSkywatch` settings.
- [x] After the user imports and deploys the Night City Skies schema fix as the
  winner, launch the game and rescan to confirm the active parse error resolves
  without changing the programmatically registered settings panel. The user
  redeployed it, loaded a save, confirmed the settings panel remained available,
  and confirmed the parse error disappeared on the next scan.
- [x] Classify Windows Core Audio `Mmdevapi.dll` as a system dependency. The
  Audioware 1.9.9-rc.0 update imports it normally, RED4ext loads and initializes
  the plugin, and the v0.28.4 real-corpus scan confirms the false missing-DLL
  error is resolved without a downgrade or compatibility package.
- [x] Build `Attachments Crafting System - Balanced Base Case Fix-1.0.0.zip`.
  The repair excludes `w_att_scope_sniper_02` from a lowercase legendary-clone
  template and applies the same edits directly to the official
  `Items.w_att_scope_sniper_02_Legendary` record, avoiding both the missing
  lowercase base and a self-inheritance cycle.
- [x] After the user imports and deploys the Attachments Crafting System fix as
  the winning `r6/tweaks/Attachments Crafting System.yaml`, rescan to confirm
  `TXL-BASE-CASE-MISMATCH` is gone. The user confirmed the finding disappeared.
- [ ] During the consolidated in-game validation pass after all report findings
  have been reviewed, sanity-check the affected legendary sniper-scope crafting
  and upgrading behavior. Do not advance the intro solely for this individual
  check; include it in the final accumulated runtime checklist.
- [x] Build `More Mods More Fun - 6 More Weapon Mod Slots Ambiguous Record
  Fix-1.0.0.zip`. It removes only 20 nonexistent weapon-mod tier IDs from the
  duplicated `$instances` lists across More Mods More Fun, 6 More Weapon Mod
  Slots, and their compatibility patch; all 206 remaining mutation targets are
  present in the installed TweakDB.
- [x] After the user imports and deploys the ambiguous-record fix as winner for
  all six YAML conflicts, launch the game and rescan to confirm the 20
  `TXL-RUNTIME-AMBIGUOUS-DEFINITION` identities disappear from the latest
  TweakXL session. The user confirmed the errors are gone.
- [ ] During the consolidated in-game validation pass, sanity-check the combined
  behavior of More Mods More Fun, 6 More Weapon Mod Slots, and their compatible
  patch: inspect representative melee and ranged weapons for the intended added
  slots; install compatible mods into both original and added slots; confirm the
  attachments are accepted and remain after inventory close/reopen or save
  reload; and watch for duplicate, empty, or unusable slots. Do not advance the
  intro solely for this check.
- [x] Build `NCEE NPC - Invalid Vendor Property Fix-1.0.0.zip`, removing the one
  rejected `enabledPhotoModePuppet: Loot.TygerClawsShotgunBikerT3` assignment
  from `Vendors.maels_ripper`. The property belongs to the photo-mode setup and
  expects booleans; the value is an NPC loot record and cannot be a vendor field.
- [x] After the user imports and deploys the NCEE NPC fix as winner for
  `r6/tweaks/NCEE NPC/ncee_characters.yaml`, refresh the game log and rescan to
  confirm `TXL-RUNTIME-UNKNOWN-PROPERTY` disappears. The user confirmed the
  repair is clean.
- [ ] During the consolidated in-game validation pass, verify representative
  NCEE NPC content loads through its intended feature and, if accessible, that
  the Maelstrom ripper NPC/vendor interaction opens and behaves normally. The
  rejected line was never applied, so no separate photo-mode behavior is
  expected from this repair.
- [x] Build `Better Living Buffs - Unknown Property Fix-1.0.0.zip`, removing one
  rejected `isActive: []` field and eleven rejected `maxFactor: 0` fields from
  their separate inline-record YAML files. TweakXL never applied those fields;
  the intended duration and UI values remain unchanged.
- [x] After the user imports and deploys the Better Living Buffs fix as winner
  for all 12 YAML conflicts, refresh the game log and rescan to confirm all 12
  `TXL-RUNTIME-UNKNOWN-PROPERTY` identities disappear. The user confirmed the
  errors are gone.
- [ ] During the consolidated in-game validation pass, verify Better Living's
  housing refresh/rested-style buff duration and representative food, drink,
  health, stamina, memory, and black-market booster effects and UI values. Do
  not obtain or advance to all affected consumables solely for this check.
- [x] Build `TheNullifier - GIM ArchiveXL Node Fix-1.0.0.zip`. The installed
  sector has 1,263 node setups; the author entry transposed its count and target
  index. The fix changes `expectedNodes` from 1,237 to 1,263 and the named GIM
  front-door proxy deletion index from 1,263 to the verified setup index 1,237.
- [x] After the user imports the TheNullifier fix, make it win the exact
  `archive/pc/mod/TheNullifier-removals.xl` conflict, deploy, launch/load the
  baseline save, and rescan. Confirm `AXL-NODE-DELETION-SHAPE` for TheNullifier
  disappears and the shared sector with INCF is informational/node-disjoint.
  The user confirmed the former conflict/finding is gone.
- [ ] During the consolidated in-game validation pass, visit the Grand Imperial
  Mall exterior and verify TheNullifier's front-door proxy removal and nearby
  INCF world cleanup both behave normally after streaming/reloading the area.
  Do not advance the intro solely for this check.
- [x] Repair the separate v0.28.5 `AXL-NODE-DELETION-SHAPE` in `INCF.xl` at
  line 13,550. The installed sector has 2,510 setups and the documented
  Northside lantern center mesh is a matching `worldStaticMeshNode` at setup
  1,812; source index 18,812 contains one extra `8`. Built
  `Immersive Night City Fixes - Lantern Node Fix-1.0.0.zip` as a one-line full
  INCF override.
- [x] After the user imports the INCF lantern fix, make it win the exact
  `archive/pc/mod/INCF.xl` conflict, deploy, refresh the runtime baseline, and
  rescan to confirm the INCF `AXL-NODE-DELETION-SHAPE` finding disappears. The
  user deployed it correctly; after scanner v0.28.6 stopped analyzing the
  overridden original as active, the error and duplicate warning pile vanished.
- [ ] During the consolidated in-game validation pass, visit the documented
  Watson/Northside position near `(-1084.44, 2135.39, 13.33)` and verify the
  intended lamp/lantern cleanup is visually correct after streaming/reloading
  the area. Do not advance the intro solely for this check.

## Configuration foundation

- [x] Add tracked, versioned YAML configuration for paths and scan settings.
- [x] Resolve relative YAML paths from the configuration directory.
- [x] Make explicit CLI options override YAML values.
- [x] Reject duplicate keys, unknown settings, invalid schema versions, and
  invalid typed values.
- [ ] Consider optional per-user override configuration if the repository is
  later used on multiple machines with different external paths.

## Next milestone: selective ArchiveXL payload inspection

- [x] Add an archive-provider interface separating member indexing from payload
  materialization.
- [x] Add exact, selective extraction into
  `.cache/archives/<archive-sha256>/extracted` using WolvenKit filters.
- [x] Verify every resolved extraction path remains inside the scanner-owned
  cache.
- [x] Add WolvenKit CR2W serialization to JSON, preferably capturing
  `convert serialize --print` output without writing a second permanent copy.
- [x] Record WolvenKit command, version, source archive hash, resource path,
  timeout, and conversion result in cache metadata.
- [x] Add cache invalidation and failure findings for partial or corrupt cached
  payloads.
- [x] Add small synthetic archive/extraction fixtures where practical; never
  write into the frozen staging or game directories.

## ArchiveXL semantic coverage

- [x] Resolve WolvenKit serialized `HandleRefId` nodes while traversing journal
  payloads. Immersive Gigs' Regina journal contains two such references under
  `contacts/regina_jones/sts_random`; v0.28 resolves them without false
  empty-ID findings or fingerprint collisions.
- [x] Inspect serialized localization resources and detect duplicate
  `secondaryKey` definitions across mods.
- [x] Detect competing edits to the same localization `primaryKey`.
- [x] Inspect serialized factory CSV resources and compare factory entity names
  and target `.ent`/`.app` paths.
- [x] Verify factory target resources exist in the declaring mod or document an
  implicit cross-mod dependency.
- [x] Parse and analyze `quest.phases` operations and parent targets.
- [x] Parse and analyze `journal` resources.
- [x] Parse and analyze `overrides` operations.
- [x] Parse `resource.patch`, `copy`, `link`, `scope`, and `fix`, preserving
  custom tags and source lines.
- [x] Compare resource patch targets, copy/link destinations, scope members,
  and fix rewrites across mods.
- [x] Inspect identities inside serialized resource patch payloads when two or
  more mods patch the same target.
- [x] Add `customizations` identity and slot/group collision checks.
- [x] Determine whether duplicate streaming node deletions are always unsafe,
  idempotent, or rule-dependent; adjust confidence/severity accordingly.
- [x] Parse the one installed ArchiveXL `player` declaration and compare its
  effective player-state operation identities.
- [x] Parse `streaming.nodeMutations` below sector level and distinguish
  disjoint property/element mutations from incompatible writes.
- [x] Correlate the newest rotated ArchiveXL log session with semantic
  references, pairing consequence messages and
  consolidating repeated events without discarding evidence.

## TweakXL analyzer

- [x] Reuse the YAML loader while preserving TweakXL-specific tags and
  operations such as append/prepend/remove.
- [x] Preserve anchors, aliases, repeated template roots, and expand
  `$instances` before comparison.
- [x] Preserve structural source lines through aliases and `$instances`
  expansion.
- [x] Extract record and flat identities.
- [x] Distinguish additive operations from destructive assignments.
- [x] Detect multiple mods assigning incompatible values to the same record
  property.
- [x] Detect assignment/mutation load-order risks, opposing add/remove
  operations, and non-unique duplicate array additions.
- [x] Detect missing/case-mismatched `$base` clone sources, base cycles,
  explicit foreign keys, and exact installed custom-record dependencies using
  local official REDmod/TweakDB data.
- [x] Parse the newest TweakXL runtime log, attribute file-scoped and
  identity-scoped events, correlate compatible static findings, and consolidate
  repeated events without discarding log evidence.

## REDscript analyzer

- [x] Implement class-and-method-aware extraction for `@wrapMethod`,
  `@replaceMethod`, `@addMethod`, and `@addField`.
- [x] Pair annotations with full method signatures rather than only class names.
- [x] Flag multiple replacements of the same method.
- [x] Detect duplicate added symbols and fields.
- [x] Review wrappers that do not invoke `wrappedMethod` where invocation is
  expected.
- [x] Correlate findings with `redscript_rCURRENT.log` compiler diagnostics.

## CET Lua and shared configuration

- [x] Detect CET mods sharing the same deployed mod directory or entry file.
- [x] Extract registered event, hotkey, input, and settings identifiers.
- [x] Resolve literal Lua modules, detect missing and cross-package providers,
  and respect CET's isolated per-root global namespaces.
- [x] Detect explicit global-symbol collisions inside CET roots assembled from
  multiple Vortex packages.
- [x] Inventory shared JSON, TOML, INI, and XML ownership.
- [x] Parse input mapping IDs and identify duplicate or overwritten mappings.
- [x] Correlate CET findings with CET framework, scripting, and per-mod logs.
- [x] Bound append-only CET framework, scripting, and canonical per-mod events
  to the newest game session so resolved historical errors become inactive.

## Cross-ecosystem analysis

- [x] Compare active literal CET observers/overrides with REDscript wrappers
  and replacements by class, method, and available NativeDB signature.
- [x] Distinguish additive observers, wrapped override chains, uncertain
  callbacks, and visibly terminating CET overrides.
- [x] Count same-package integration, overload-ambiguous short names, and
  dynamic hook targets without promoting them to false conflicts.
- [x] Extract literal CET `TweakDB` record/flat writes and compare them with
  concrete TweakXL operations.
- [ ] Consider explicit cross-language dependency/detection declarations after
  method and TweakDB effect coverage is complete.

## RED4ext and framework validation

- [x] Inventory native plugin versions and declared dependencies.
- [x] Compare bundled framework binaries across staging mods and deployed
  winners.
- [x] Add game-version/framework-version compatibility rules from authoritative
  local metadata or official sources.
- [x] Parse RED4ext, ArchiveXL, TweakXL, Codeware, and other framework logs.
- [x] Report missing DLL dependencies and native plugin load failures.

## Reporting and performance

- [x] Add analyzer-coverage tables for installed ArchiveXL sections and
  resource operations, including analyzed/partial/unsupported status.
- [x] Attach structural source lines to all current ArchiveXL and TweakXL
  references instead of relying on synthesized-identity text searches.
- [x] Add URL/hash-backed HTML filter state so a filtered finding view can be
  bookmarked or shared.
- [ ] Add export of the currently filtered HTML findings to JSON/CSV.
- [x] Add optional finding suppression/acknowledgement configuration without
  changing source mods.
- [x] Add scan-to-scan diff reporting for new, resolved, and changed findings.
- [x] Store acknowledgements separately and allow checkbox/note editing plus
  user-approved YAML saving from the HTML report.
- [x] Replace overly wide ArchiveXL runtime and CET registration coverage rows
  with responsive metric cards.
- [x] Make absolute `source_path` values in HTML evidence link to their parent
  folders without changing the displayed path or finding fingerprints.
- [ ] Avoid re-hashing unchanged archives by caching a verified
  size/mtime/file-identity fingerprint before SHA-256 fallback.
- [ ] Separate the large ArchiveXL reference list from the primary findings JSON
  if future report sizes become inconvenient.
- [ ] Add structured progress output and a final CLI severity summary.
- [ ] Consider HTML virtual scrolling if result counts grow beyond pagination's
  comfortable range.

## Packaging and repository maintenance

- [x] Locate or configure a usable Git executable for status/diff checks in the
  execution environment. It resolves from `C:\Program Files\Git\cmd\git.exe`.
- [ ] Add a license if the user chooses one.
- [ ] Add contributor/development documentation when the analyzer API stabilizes.
- [ ] Add CI for Python tests after GitHub Actions requirements are decided.
- [ ] Decide whether generated example reports should remain ignored or whether
  a small sanitized sample report belongs in the repository.
