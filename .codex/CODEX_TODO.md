# Codex TODO

Last reviewed: 2026-08-06

This list describes planned scanner work. Reorder it when user priorities
change. Check an item only after implementation, relevant tests, and a real
frozen-corpus validation pass are complete.

## Manual compatibility packages

- [x] Diagnose Immersive Relic Malfunctions / Immersive Relic English 1.5.1
  versus False Encumbrance Fix 1.0. Immersive Relic intentionally reapplies
  `BaseStatusEffect.Encumbered` throughout its malfunction, while False
  Encumbrance Fix immediately calls `EvaluateEncumbrance(true)` for every new
  Encumbered event and therefore removes the intentional status at normal
  inventory weight.
- [x] Build
  `Immersive Relic - False Encumbrance Fix Compatibility-1.0.0.zip` as an
  exact-path override of False Encumbrance Fix's single REDscript file. It
  suppresses only the immediate false-encumbrance reconciliation while either
  of Immersive Relic's overlapping malfunction markers is active; normal False
  Encumbrance Fix behavior is unchanged. The scanner's REDscript parser reports
  one document, 12 references, and zero findings. Package SHA-256:
  `4EAD2F3EFA3B8876FE0135604AED7DD237551135A897F6BE6A1DB86DB3C9A233`.
- [ ] Import and deploy the compatibility package after False Encumbrance Fix,
  making it win
  `r6\scripts\FalseEncumbranceFix\FalseEncumbranceFix.reds`. Launch/load/exit
  and confirm REDscript compiles without errors.
- [ ] During the consolidated in-game validation pass, trigger an Immersive
  Relic malfunction and confirm its forced encumbrance remains for the sequence
  and clears at the end. Separately reproduce a genuinely stale encumbrance at
  normal carry weight and confirm False Encumbrance Fix still clears it. Rebuild
  this compatibility copy after either upstream mod updates.

- [x] Diagnose the CET/TweakXL runtime overwrite of
  `Items.IntrinsicFabricEnhancer10_inline2.value`. Quickhack Fixes repurposes
  the record with multiplier `1` to transfer the Wreath clothing mod's upload
  bonus into its custom stat and applies the final `0.01` conversion in a GLP;
  Clothing Improved later writes `-0.01`, reversing and reducing that transfer
  by 100 times. Clothing Improved labels the field unknown and only repeats its
  old vanilla value.
- [x] Build
  `Clothing Improved - Quickhack Fixes Wreath Compatibility-1.0.0.zip` as a
  one-file `Clothing Improved_Unique/init.lua` override removing only the
  redundant conflicting `SetFlat`. Focused parsing and cross-analysis are clean
  and the 13 CET/cross-ecosystem tests pass.
- [x] Import and deploy the compatibility package after Clothing Improved and
  make it win the single `Clothing Improved_Unique/init.lua` conflict. Launch,
  load, exit, and rescan; confirm
  `XEC-CET-TWEAKDB-FLAT-RUNTIME-OVERRIDE` disappears and no Clothing Improved
  CET error appears. The user confirmed the report is gone. Rebuild after
  Clothing Improved or Quickhack Fixes updates.
- [ ] During the consolidated in-game validation pass, obtain/equip the Wreath
  quickhack-upload clothing mod and compare quickhack upload time with it
  equipped and unequipped. Also confirm Clothing Improved's other weight and
  clothing-mod adjustments remain active. Do not advance the intro solely for
  this check.

- [x] Diagnose the shared
  `CraftingSystem.UpgradeItem(wref<GameObject>, ItemID)->Void` wrapper in Better
  Leveling Addon - Skill Progression and Upgrade Weapons Unlocked. Both bodies
  are complete upgrade implementations and neither calls `wrappedMethod`, so a
  direct cooperative-call edit would consume materials and apply upgrade/XP
  logic twice.
- [x] Build
  `Better Leveling Addon - Upgrade Weapons Unlocked Compatibility-1.0.0.zip` as
  a two-file exact-path override. It removes Better Leveling's duplicate
  wrapper, makes Upgrade Weapons Unlocked's full body an explicit replacement,
  and integrates Better Leveling's Technical 150 double-step and weapon-damage
  bonus. Focused parsing leaves one active replacement and no finding for the
  shared signature; the REDscript unit suite passes.
- [x] Import and deploy the compatibility package after both upstream mods,
  make it win both `.reds` file conflicts, launch/load/exit, and rescan. Confirm
  REDscript compiles with no new error and `RS-WRAPPER-CHAIN-TERMINATED` for
  `CraftingSystem.UpgradeItem` disappears. The user confirmed the report is
  gone. Rebuild after either upstream mod updates.
- [ ] During the consolidated in-game validation pass, upgrade one ordinary
  weapon before Technical Ability Skill 150 and confirm Upgrade Weapons
  Unlocked's quality/plus and material behavior. After reaching Technical 150,
  upgrade another weapon and confirm Better Leveling's two-step advancement
  and intended damage bonus. Also test `upgradeToMax` if that option is enabled;
  do not advance the intro solely for these checks.

- [x] Diagnose No Shooting Delay 1.2-fix's unresolved
  `require("Modules/main.lua")`. The package contains no such module, while
  `init.lua` itself defines the complete `main()` implementation and calls it
  during `onInit`; the import is a stale packaging/editing remnant rather than
  a required dependency.
- [x] Build `No Shooting Delay - Missing Module Require Fix-1.0.0.zip` as a
  complete four-file CET-root override. It removes only the obsolete import
  from `init.lua`; the three bundled `Modules/*.lua` files are byte-identical
  to upstream so the root retains single-package ownership. Focused scanner
  validation parses all four documents, resolves every remaining import, and
  produces no CET findings.
- [x] Import and deploy the No Shooting Delay fix after the upstream package,
  make it win all four `NoShootingDelay` Lua file conflicts, launch/load/exit,
  and rescan. Confirm `CET-MODULE-MISSING` disappears and no replacement CET
  parse, runtime, or cross-package finding appears. The user confirmed the
  report disappeared. Rebuild the fix after any upstream No Shooting Delay
  update.
- [ ] During the consolidated in-game validation pass, confirm the Native
  Settings page opens, its close/medium/long/boss multipliers can be changed,
  and representative enemies fire with the expected reduced delay. Do not
  advance the intro solely for this check.

- [x] Diagnose the unattributed
  `MenuScenario_PauseMenu.OnSwitchToCredits` runtime hook failure. Five active
  mods bundle an old GameUI helper containing that table row, but only
  `CsBreachingBreached` subscribes to `MenuNav` and initializes the affected
  menu-observer table. Newer installed GameUI copies already omit the method,
  and the current RTTI confirms it no longer exists.
- [x] Build `Breaching - Obsolete Credits Hook Fix-1.0.0.zip` as a complete
  three-file `CsBreachingBreached` root override. It removes only the dead
  `OnSwitchToCredits` mapping; `init.lua` and `GameSettings.lua` are
  byte-identical to upstream. Both roots have the same unrelated optional
  `GetMod` review finding, while all literal modules remain resolved.
- [x] Import and deploy the Breaching fix after the upstream package, make it
  win all three Lua conflicts, launch/load/exit, and rescan. Confirm
  `CET-RUNTIME-HOOK-TARGET-MISSING` disappears and no new Breaching Lua error
  appears. The user confirmed the runtime finding disappeared. Rebuild the
  package after any upstream Breaching update.
- [ ] During the consolidated in-game validation pass, open Settings through
  the pause menu, return to the game, and confirm Breaching retains its saved
  language/settings and normal breach behavior. The removed Credits submenu
  hook was already rejected and should not change gameplay.

- [x] Diagnose Missing Persons 2.3.0's Spanish language file. The complete
  document is valid JSON encoded as Windows-1252, not a single-character typo:
  it contains 16 non-ASCII CP-1252 bytes covering the en dash and all accented
  Spanish characters.
- [x] Build `Missing Persons - Spanish UTF-8 Fix-1.0.0.zip` as a one-file
  exact-path override. The UTF-8 document has no BOM or replacement characters,
  parses to the same 25 entries and semantic hash as the CP-1252 source, and
  produces no `CFG-NON-UTF8` finding in simulated deployment.
- [x] Import and deploy the Missing Persons Spanish UTF-8 fix after the
  upstream package, make it win the single `languages/es-es.json` conflict,
  and rescan. Confirm the encoding warning disappears. The user confirmed the
  result looks good. Rebuild the fix after any upstream Missing Persons update.
- [ ] During the consolidated in-game validation pass, optionally select
  Spanish and inspect the Missing Persons Native Settings labels/descriptions,
  especially accented text and the en dash in the title.

- [x] Diagnose the shared missing New Game Plus parents in HG Enemies 1.0.0,
  NCEE Enemies 2.6.0, and NCEE NPC 2.0.3. ArchiveXL successfully merges all 23
  unique child phases into the base-game and Phantom Liberty parents, but skips
  69 optional declarations targeting three absent `mod\quest\newgameplus*`
  resources. The mods do not list NG+ as a requirement.
- [x] Build `HG Enemies and NCEE - Missing NG Plus Hook Cleanup-1.0.0.zip` as
  three full exact-path `.xl` overrides that remove only the unavailable NG+
  path/parent pairs and preserve all other declarations byte-for-line.
- [x] Import and deploy the NG+ hook cleanup as winner for
  `hidden_gem_enemies.xl`, `ncee_inimigos.xl`, and `ncee_npcs.xl`; launch/load
  the baseline save, exit, and rescan. Confirm the three static missing-parent
  findings and three runtime warnings disappear while all 23 normal phase
  resources still merge. The user confirmed the report is gone after deployment
  and rescan. Disable/rebuild this package if an actual New Game Plus provider
  is installed or any of the three source mods updates.
- [ ] During the consolidated in-game validation pass, visit representative HG
  Enemies, NCEE Enemies, and NCEE NPC locations and check for intended spawns,
  obvious duplicate NPC/enemy placements, and normal quest-state gating. Do not
  advance the intro solely for this check.

- [x] Diagnose They Will Remember 2.5a's missing Maelstrom quest phase. Its
  `.xl` declares the nonexistent
  `retaliation_quests\retaliation_maelstrom_pt1.questphase` twice, while the
  archive contains the otherwise undeclared
  `redemption_quests\redemption_maelstrom_pt1.questphase`. Serialized phase and
  REDscript facts confirm this is the intended Maelstrom redemption step.
- [x] Build `They Will Remember - Maelstrom Redemption Phase Fix-1.0.0.zip` as
  a full exact-path `.xl` override changing only those two child paths. The real
  parser reports no findings; all 32 child declarations resolve in the mod and
  all 32 parent declarations resolve as official quest roots.
- [x] Import and deploy the They Will Remember fix as winner for
  `archive/pc/mod/they_will_remember.xl`, launch/load the baseline save, exit,
  and rescan. Confirm `AXL-QUEST-PHASE-NOT-FOUND` and its ArchiveXL runtime
  warning disappear. The user confirmed the result looks good. Rebuild the
  package before accepting any upstream update.
- [ ] During the consolidated in-game validation pass, exercise the first
  Maelstrom redemption flow and confirm its message/payment/forgiveness state
  completes and survives save/reload. Do not advance the intro solely for this
  check.

- [x] Diagnose Better Armor Tooltip 1.0.1's missing `es-mx` localization. Its
  `.xl` declares 19 languages, but the archive contains only 18 resources and
  omits exactly `better_armor_tooltip\localization\es-mx.json`. The author says
  the corrected tooltip is intended for all languages.
- [x] Build `Better Armor Tooltip - Missing Latin American Spanish
  Fix-1.0.0.zip`. Its exact-path `.xl` override removes only the broken
  declaration, while a separate patch `.xl` registers the same locale from a
  one-resource companion archive containing the mod's existing Spanish text.
  The full simulated deployment resolves all 19 localizations with no parse,
  missing-resource, cross-mod-resource, or archive-collision findings.
- [x] Import the Better Armor Tooltip localization fix, make its
  `BetterArmorTooltip.archive.xl` win over the upstream file, deploy,
  launch/load/exit, and rescan. Confirm `AXL-RESOURCE-NOT-INDEXED` disappears
  and no replacement ArchiveXL warning appears. The user confirmed the report
  is gone. The resulting `CORE-EXACT-PATH` INFO finding is the required Vortex
  winner and can be acknowledged. Rebuild it after any upstream Better Armor
  Tooltip update.
- [ ] During the consolidated in-game validation pass, optionally select Latin
  American Spanish and inspect the Cyberware/Ripperdoc armor tooltip. Confirm
  it shows the corrected damage-reduction description in understandable
  Spanish; the repair deliberately reuses the author's `es-es` translation.

- [x] Diagnose NCEE NPC 2.0.3's missing Italian localization. Its active
  NG-cleaned `ncee_npcs.xl` declares 19 locales, while `NCEE NPC.archive`
  contains 18 corresponding resources and omits only
  `localization\it-it\onscreens\ncee_onscreens.json`.
- [x] Build `HG Enemies and NCEE - Missing NG Plus Hook Cleanup-1.1.0.zip` as a
  replacement for cleanup 1.0.0. It preserves the earlier HG Enemies/NCEE NG+
  removals, moves the Italian registration to a patch-owned `.xl`, and supplies
  a valid one-resource archive with 14 translated Italian entries. Simulated
  deployment has no parse, missing-resource, cross-mod-resource, quest, or
  archive-collision findings.
- [x] Remove/uninstall cleanup package 1.0.0 from Vortex, import cleanup 1.1.0,
  make it win the three original `.xl` conflicts, deploy, launch/load/exit, and
  rescan. Confirm the NCEE Italian `AXL-RESOURCE-NOT-INDEXED` finding disappears
  without restoring any NG+ missing-parent finding. The user confirmed the
  missing-resource report disappeared, but ArchiveXL then revealed seven
  localization-overwrite warnings caused by the standalone Italian-only `.xl`.
- [x] Diagnose cleanup 1.1.0's seven runtime warnings. The Italian-only config
  falls back to its sole locale even when the game uses English; NCEE's main
  config then loads `en-us` and overwrites the seven custom secondary keys.
  The report's Mod Settings attribution was stale runtime config context.
- [x] Build `HG Enemies and NCEE - Missing NG Plus Hook Cleanup-1.1.1.zip`.
  It keeps all three cleanup `.xl` files byte-identical to 1.0.0, removes the
  standalone locale config, and retains only the one-resource Italian companion
  archive. Scanner v0.28.10 recognizes resources supplied by the active
  exact-path override package; all 121 tests pass.
- [x] Remove/uninstall cleanup 1.1.0 from Vortex, import cleanup 1.1.1, make it
  win the three original `.xl` conflicts, deploy, launch/load/exit, and rescan.
  Confirm the seven localization-overwrite warnings disappear, the Italian
  resource stays resolved, and no NG+ missing-parent finding returns. The user
  confirmed the remaining warnings disappeared after deployment and rescan.
- [ ] During the consolidated in-game validation pass, optionally select
  Italian and inspect representative NCEE vendor labels, the Clouds message,
  the Maelstrom clinic message, and Rocky Ridge notifications. The Italian text
  is a local compatibility translation and should be reviewed by a native
  speaker if it will be distributed beyond this collection.

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
- [x] Diagnose the 12 follow-on `TXL-RUNTIME-DANGLING-REFERENCE` hashes on
  `Items.TechMod2_Common.placementSlots`. They map to 12 nonexistent
  `_Collectible` attachment-slot records repeated by More Mods More Fun and
  Attachments Unrestricted. Since no weapon owns those missing slots, removing
  the no-op references is safer than inventing unused records.
- [x] Build `More Mods More Fun - 6 More Weapon Mod Slots Ambiguous Record
  Fix-1.1.0.zip` as the replacement for 1.0.0. It retains all six original
  ambiguity fixes and adds an Attachments Unrestricted override; only the same
  12 invalid collectible references are removed from each affected ranged
  template. All seven YAML documents parse and the 14 TweakXL tests pass.
- [x] Disable/remove version 1.0.0, import version 1.1.0, and make 1.1.0 win its
  six existing mod-slot YAML conflicts plus `Attachments Unrestricted.yaml`.
  Launch/load/exit and rescan; confirm both the 20 ambiguous-definition errors
  remain absent and the 12 dangling-reference warnings disappear. The user
  confirmed the report is clear. Rebuild after More Mods More Fun, 6 More
  Weapon Mod Slots, their compatibility patch, or Attachments Unrestricted
  updates.
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
- [x] Diagnose INCF's 10 ignored mutation operations and nine unknown mutation
  fields against the exact installed ArchiveXL 1.27.1 source and selectively
  serialized vanilla sectors. Seven negative proxy deltas plus their
  `nodeRefHash` fields and three scalar foliage `actorMutations` have no safe
  ArchiveXL equivalent; only `sscale` and `rientation` are repairable typos.
- [x] Build `Immersive Night City Fixes - Combined Streaming Fixes-1.1.0.zip`,
  superseding the lantern-only package. It retains the corrected lantern index
  and changes only `sscale` to `scale` and `rientation` to `orientation`.
- [x] Replace/disable the older `Immersive Night City Fixes - Lantern Node
  Fix-1.0.0` package, import the combined 1.1.0 package, and make it the sole
  exact-path winner over upstream `INCF.xl`. After deployment, launch/load the
  baseline save and rescan. Expect unknown mutation fields to fall from nine to
  seven while the 10 unsupported operations remain; confirm no new ArchiveXL
  runtime errors appear. The user confirmed the combined package produced the
  expected result with no unexpected errors.
- [x] Acknowledge the two residual INCF mutation findings together after the
  combined package is verified. Suggested reason: ArchiveXL 1.27.1 does not
  support negative `nbNodesUnderProxyDiff`, `nodeRefHash`, or per-actor foliage
  mutations; retaining the findings documents upstream INCF operations that
  cannot be translated safely without direct sector-resource edits. The user
  acknowledged the remaining supported-by-evidence limitations after rescanning.
- [ ] During the consolidated in-game validation pass, verify INCF's repositioned
  Japantown doors/frame near `(-804.67, 766.78, 22.46)` and the Northside
  generator/collision near `(-1942.83, 2739.66, 7.20)`, as well as the existing
  lantern check. Do not advance the intro solely for these checks.
- [x] Build `Cyberware-EX - VanillaPlus Parkour Compatibility-1.0.0.zip` for
  Cyberware-EX 1.5.6. VanillaPlus Parkour's later
  `DoubleJumpDecisions.EnterCondition` replacement preserves Cyberware-EX's
  charge/hover compatibility and additionally removes the fall-speed rejection,
  so the repair removes only Cyberware-EX's redundant replacement from a full
  exact-path override of `CyberwareEx.Global.reds`.
- [ ] After the user imports the Cyberware-EX / VanillaPlus Parkour package,
  make it win the exact `r6/scripts/CyberwareEx/CyberwareEx.Global.reds`
  conflict over Cyberware-EX, deploy, launch/load the baseline save, and rescan.
  Confirm REDscript compiles without the duplicate-replacement warning and
  `RS-METHOD-REPLACEMENT-CONFLICT` disappears. Remove or rebuild this package
  before accepting any Cyberware-EX update because the override is based on
  version 1.5.6.
- [ ] During the consolidated in-game validation pass, equip representative
  Cyberware-EX leg-cyberware combinations and verify double jump, charge/hover
  coexistence, the intended VanillaPlus Parkour high-fall jump behavior, and
  normal jump-count limits. When Technical Central Milestone 3 reaches level 3,
  also confirm installed musculoskeletal cyberware—including expanded slots—is
  powered up normally. Do not advance the intro solely for these checks.

- [x] Review Cyberware-EX's terminating
  `PlayerDevelopmentData.HandleAddingPerkLevel` wrapper. The vanilla body powers
  musculoskeletal slots 0–2 at Technical Central Milestone 3 level 3, while
  Cyberware-EX intentionally supersedes it with an all-expanded-slots loop.
  Calling `wrappedMethod` would duplicate slots 0–2; acknowledge the finding
  without a compatibility package.

- [x] Review Dodging Fix's terminating
  `TweakAIActionRecord.GetActionRecordFromSelector` wrapper against the locally
  decompiled current vanilla method. It preserves the full selector algorithm
  and inserts its dodge-ticket fallback inside the action loop, which cannot be
  implemented by calling vanilla before or after. No other installed script
  targets the signature; acknowledge the finding without a package.
- [ ] During the consolidated in-game validation pass, engage several mobile
  human enemies and confirm they can dodge attacks without becoming stuck,
  repeatedly cancelling actions, or losing their other combat behaviors. Do
  not advance the intro solely for this check.

- [x] Review Equipment-EX's terminating
  `UIInventoryItemsManager.IsItemTransmog` wrapper. Equipment-EX deliberately
  replaces vanilla's six-slot transmog cache with its persistent custom outfit
  state, imports vanilla sets, and disables the vanilla equip/unequip path. No
  other installed script targets the method; acknowledge without a package.
- [ ] During the consolidated in-game validation pass, open Equipment-EX's
  wardrobe, confirm imported vanilla sets are present, save and activate a
  custom outfit, verify its pieces are marked/equipped correctly in inventory,
  then deactivate it and confirm normal equipment visuals return. Do not
  advance the intro solely for this check.

- [x] Review NCA Standard Density's terminating
  `ReactionManagerComponent.CanTriggerAlertedFromHostileStim` wrapper. It
  deliberately removes vanilla's blanket Prevention-NPC rejection while
  retaining the stimulus filter, coordinated with NCA's other Prevention and
  non-player-gunshot reaction hooks. No other installed script targets the
  method; acknowledge without a package.
- [ ] During the consolidated in-game validation pass, observe police or other
  Prevention NPCs near a hostile stimulus not caused by the player. Confirm
  they become alerted/investigate appropriately without instantly treating the
  player as the offender or remaining permanently alerted. Do not advance the
  intro solely for this check.

- [x] Review Always First Equip's terminating wrapper for
  `EquipCycleDecisions.ToFirstEquip`. Its unconditional `false` deliberately
  disables the vanilla route while the mod implements the feature through its
  own `HasPlayedFirstEquip` logic and full `HandleWeaponEquip` replacement. No
  other installed annotation targets the class, REDscript compiles, and no
  compatibility package is needed; acknowledge the scanner review finding.
- [ ] During the consolidated in-game validation pass, draw the same weapon
  repeatedly and confirm Always First Equip follows its configured probability
  or cooldown, then exercise its additional hotkey and one skip context such as
  climbing or an interaction. Do not advance the intro solely for this check.

- [x] Review Retrievable Weapon Mods' terminating
  `InventoryItemModeLogicController.EquipPart` wrapper. It intentionally uses
  the game's `SwapItemPart` request for occupied slots so the displaced
  non-base weapon mod receives the standard uninstall/UI updates before the new
  part is installed. Calling vanilla too would perform a second transaction.
  Attachments Unrestricted's same-method experiment is fully commented out;
  acknowledge the finding without a compatibility package.
- [ ] During the consolidated in-game validation pass, put an ordinary weapon
  mod into an occupied compatible slot and confirm the old mod returns to
  inventory exactly once, the new mod installs once, quantities do not change
  unexpectedly, and the attachment UI refreshes. Repeat with an iconic weapon
  if available and exercise direct mod removal. Do not advance the intro solely
  for these checks.

- [x] Review Attachments Unrestricted's terminating `GetMatchingSlot` and
  `IsMatchingSlot` wrappers. They intentionally extend vanilla routing with the
  mod's `HasScopeEquipped`/`HasMuzzleEquipped` stat markers and selected-slot
  fallback; its related `EquipItem` wrapper consumes those decisions and
  enforces the optional attachment-count limits. No other installed script
  targets either selector, and the result composes with Retrievable Weapon
  Mods; acknowledge both references without a package.
- [ ] During the consolidated in-game validation pass, equip a scope and muzzle
  into representative nonstandard weapon-mod slots, replace one in an occupied
  slot, and confirm the selected slot, inventory quantities, weapon stats, and
  attachment UI update correctly. Toggle the one-scope, one-silencer, and
  one-muzzle-brake settings and confirm only the intended duplicate category is
  blocked. Do not advance the intro solely for these checks.

- [x] Review Inventory Adjustments Hub's two terminating
  `ItemTooltipModController.SetData` attachment overloads. They intentionally
  rebuild the vanilla tooltip entries to implement description-only, name-only,
  and name-plus-description modes; calling vanilla too would clear or duplicate
  that presentation. No other installed script targets either overload, so the
  compatibility finding can be acknowledged without a package.
- [ ] During the consolidated in-game validation pass, inspect empty and filled
  weapon/cyberware attachment tooltips under IAH's Description, Name, and
  Name-and-Description schemes. Then temporarily disable IAH globally while the
  scheme is Name and confirm whether filled attachment tooltips become blank.
  If disabled-mode fallback is desired, build a small exact-path fix that uses
  vanilla description rendering whenever `xIAHub.isEnabled` is false. Do not
  advance the intro solely for these checks.

- [x] Review They Will Remember's terminating
  `SecurityTurret.SetAsIntrestingTarget` and
  `SenseComponent.OnDetectionReachedZero` wrappers. The turret method preserves
  vanilla's superclass delegation except for TWR-classified friendly turrets
  targeting the player; the detection callback clears TWR monitoring state and
  then performs vanilla's same reevaluation. No other installed scripts target
  either exact method; acknowledge both without a package.
- [ ] During the consolidated in-game validation pass, confirm a turret treated
  as friendly by They Will Remember does not acquire the player, while a hostile
  turret still detects and attacks normally. Break detection until its meter
  reaches zero, then re-enter perception and confirm identification can begin
  again without a stuck or rapidly looping meter. Do not advance the intro
  solely for these checks.

- [x] Review Better Leveling Addon - Skill Progression's four terminating
  wrappers. The two skill-bar bodies intentionally extend/filter the level-150
  milestone UI. The two movement bodies intentionally replace vanilla impulse
  calculation, but lack any Reflexes-level gate; `BTL.ReflexesLevel85` supplies
  only UI data, so the 50% air-dodge/air-dash bonus is active from level 1. Do
  not acknowledge the grouped finding yet.
- [x] Build `Better Leveling Addon - Reflexes Level 85 Gate Fix-1.0.0.zip` as a
  one-file exact-path override. Its movement wrappers call the existing method
  and add only the extra 50% air impulse after confirming Reflexes >=85, so
  ordinary/ground movement and wrapper behavior below them remain intact. Both
  exhausted and non-exhausted air-dash defaults and `DodgeAirEvents.Dodge` use
  the corresponding extra half-impulse. The official REDscript CLI lints the
  file successfully against the installed `final.redscripts` bundle.
- [x] Deploy the Reflexes level-85 fix after Better Leveling, rescan, and
  acknowledge the remaining two intentional level-150 skill-bar replacements.
  The two movement-wrapper findings disappeared as intended.
- [ ] During the consolidated in-game pass, confirm the skill milestone bar
  shows the intended 35/40/45/50/55/60/65/75/85/100/120/150 window, air
  movement is vanilla below Reflexes 85, and the 50% bonus begins only at level
  85. Do not advance the intro solely for these checks.

- [x] Review Smaller Cyberware Slots (7x3)'s four terminating
  `CyberwareInventoryMiniGrid` wrappers. They are intentional full
  vanilla-derived replacements that cap wrapping at seven columns and apply
  the corresponding narrower panel offsets. Calling vanilla would duplicate
  grid rebuilding or animation work, and no other installed script targets the
  four exact signatures. Acknowledge the grouped finding without a patch.

- [x] Review the four remaining Upgrade Weapons Unlocked terminating wrappers
  in the Better Leveling compatibility override. They intentionally replace
  vanilla item enumeration, tier repair/selection, tier lookup, and
  quality/Plus mutation. Calling vanilla would duplicate work or advance item
  quality twice; no unrelated installed mod targets the exact signatures.
  Acknowledge the grouped finding without another patch.

- [x] Review Beautiful Eyebrows 01 and 02 ArchiveXL customization overlap.
  ArchiveXL already composes both packs: each contributes 2,880 distinct
  customization choices, 240 group entries, 240 scoped resources, and 160
  patch identities, with zero shared identities in those categories. Their
  archives share no internal member paths. The only overlap is four identical
  base-resource copy redirects, which are harmless and informational.
  Acknowledge both INFO findings; no compatibility package is needed.
- [x] Verify ArchiveXL 1.27.0's empty bundled
  `PlayerCustomizationScope.xl`. The installed framework-owned file is exactly
  zero bytes and sits beside populated specialized brows, eyes, hair, lashes,
  beard, base, and photo-mode scope files. It is an intentional bundle
  placeholder; acknowledge `AXL-EMPTY` without a fix.
- [x] Review the shared ArchiveXL journal `contacts` container from Immersive
  Gigs, NCEE NPC, Shard Audio Framework, and They Will Remember. The container
  is the only shared journal identity; there are no conflicting descendant
  definitions among these mods. ArchiveXL recursively composes their children,
  so acknowledge `AXL-JOURNAL-CONTAINER-COMPOSABLE` without a merge package.
- [x] Review the repeated ArchiveXL deletion of
  `exterior_-40_-37_0_0.streamingsector` node 179 by 4x Vending Machine
  Framework and NCEE NPC. These are the only operations on that exact identity;
  both fully delete the same `worldEntityNode`, with no mutation, partial
  deletion, or type disagreement. Acknowledge `AXL-NODE-DELETION-IDEMPOTENT`
  without a patch or load-order rule.
- [x] Review the repeated deletion of
  `interior_-44_41_3_0.streamingsector` node 816 by NCEE NPC and Immersive
  Night City Fixes through the active Combined Streaming Fixes override. These
  are the only two operations on the identity and both fully delete the same
  `worldStaticMeshNode`; acknowledge the idempotent INFO finding without a
  patch or load-order rule.
- [x] Review the 29 grouped full-node deletion overlaps between Immersive Night
  City Fixes (through Combined Streaming Fixes) and Road Fix V2. Across four
  sectors, every identity has exactly two matching full deletions with the same
  node type (14 static-mesh and 15 instanced-mesh nodes), and no third-party
  mutation or additional operation. Acknowledge the grouped idempotent INFO
  finding without a patch or load-order rule.
- [x] Review the remaining grouped idempotent deletions involving Immersive
  Night City Fixes: four overlaps with 4x Vending Machine Framework and five
  with TheNullifier (through the active GIM ArchiveXL Node Fix). All nine are
  exact two-provider full deletions of matching `worldEntityNode` identities,
  with no extra mutation, partial deletion, or type mismatch. Acknowledge both
  INFO findings without another patch or load-order rule.
- [x] Review the 13 `AXL-NODE-MUTATION-DELETION-REDUNDANT` overlaps between
  Immersive Night City Fixes and 4x Vending Machine Framework. All are vanilla
  vending-machine mutations dominated by 4x's intentional full deletions; its
  archive supplies replacement vending entities in all eight affected sectors.
  The replacements intentionally use 4x appearances/layouts rather than exact
  INCF values, so acknowledge the INFO finding when preferring 4x's machines;
  no merge or load-order rule is required.
- [x] Review `AXL-NONSTANDARD-TABS` for the active combined `INCF.xl`. Its only
  two tab characters are trailing whitespace after `expectedNodes: 122` and a
  comment; neither is indentation or scalar content. Acknowledge the INFO
  finding as harmless formatting without a patch.
- [x] Review the shared `03_night_city.devices` ArchiveXL resource patch from
  NCEE NPC and Immersive Night City Fixes. NCEE adds five distinct hashed
  device entries while INCF adds a sixth different hash; none of their stable
  inner identities overlap. ArchiveXL composes the additions automatically, so
  acknowledge `AXL-RESOURCE-PATCH-DISJOINT` without a compatibility patch.
- [x] Review the 36 disjoint citizen-entity patches shared by Citizen Breast
  Physics and Expanded Citizens. The physics package adds one distinct
  component identity per template, while Expanded Citizens supplies appearance
  entries and other citizen data without touching those component identities.
  ArchiveXL composes all 36 targets; acknowledge the INFO finding without a
  compatibility patch or load-order rule.
- [x] Review the six disjoint player hair/brow/lash mesh patches shared by
  ArchiveXL's bundled customization support and Hair Profiles CCXL. The bundle
  adds its base-color appearance data while Hair Profiles contributes different
  stable mesh identities; none overlap across the male/female hair, brow, and
  lash targets. Acknowledge the INFO finding without a patch or load-order rule.
- [x] Review the shared `interior_-17_21_0_1.streamingsector` between 4x Vending
  Machine Framework and General Shadows Fix. Both declare 817 expected nodes;
  4x fully deletes entity nodes 197-199 while General Shadows partially deletes
  instances from instanced-mesh node 622. The indices and operation scopes are
  disjoint, so acknowledge `AXL-SECTOR-NODE-DISJOINT` without a patch.
- [x] Bulk-audit all 13 active `AXL-SECTOR-NODE-DISJOINT` findings, covering
  360 shared streaming sectors. By construction this rule is emitted only when
  all supplied `expectedNodes` values agree and no node index is shared by more
  than one participating mod; shared indices are routed to the more specific
  node-level rules instead. Acknowledge every current finding under this exact
  INFO rule without individual patches or load-order rules.
- [x] Audit all five active `CET-ENTRY-OVERRIDE` winners. The deployed entries
  are the Clothing Improved/Quickhack compatibility package, Breaching obsolete
  hook fix, Damage Scaling and Balance Extended, Classic Drinks' bundled
  NoPaperBags entry, and the No Shooting Delay module-require fix; each original
  provider is correctly marked overridden. Acknowledge all five intended Vortex
  file overrides without further patches.
- [x] Verify Damage Scaling and Balance Extended's two
  `CET-MODULE-CROSS-PACKAGE` imports. Its deployed `init.lua` intentionally
  reuses `GameUI.lua` and `GameSettings.lua` from the original Damage Scaling
  package; both imports resolve in the merged `DamageScaling` CET root. Keep the
  original package installed and acknowledge this INFO dependency.
- [x] Bulk-audit all 38 active `CET-OBSERVER-SHARED` report items, representing
  80 exact CET hook targets and 610 `Observe`/`ObserveBefore`/`ObserveAfter`
  registrations. CET retains these callbacks additively, none is an override,
  and the current runtime scan has no related Lua callback or missing-target
  failures. Acknowledge all current INFO findings under this exact rule; revisit
  only if a gameplay symptom or a later runtime error identifies a callback.
- [x] Audit the two `CET-OVERRIDE-CHAIN-DUPLICATE` targets supplied by 0-Engine,
  Missing Persons, and Pacifica Typhoon. Their `GameHUD 0.4.1` callbacks for
  `WarningMessageGameController.UpdateWidgets` and `.OnShown` have identical
  normalized bodies and no different surrounding state dependency. They are
  also guarded to register only on game versions 1.30-1.31, so they do not
  register on the current 2.x game. Acknowledge the INFO finding without a patch.
- [x] Audit the two `CET-RUNTIME-MOD-IGNORED` folders. `nativeInteractions` is
  intentional NCEE NPC project-data storage containing
  `projects/ncee_redwood.json`, not a CET Lua mod. `ReferencePathTracing`
  contains only Vortex's folder-management marker and has no current staging
  provider, making it harmless deployment residue. Acknowledge the INFO finding;
  a later Vortex purge/redeploy may remove the empty residue.
- [x] Audit the shared Native Settings `/DNBNHLP` tab registered by Enhanced
  Edgerunner and Lifepath Changer. Both guard `addTab` with `pathExists`, use the
  same `DNBNHLP Mods` label, and place controls in disjoint subcategories
  `/EnhancedEdgerunner` and `/NoLifepathRestriction`. No child-control collision
  is present; acknowledge `CET-SETTINGS-CONTAINER-SHARED` without a patch.
- [x] Audit the shared Native Settings `/DarkMods` tab registered by Missing
  Persons and Pacifica Typhoon. Both guard `addTab` with `pathExists`, use the
  same `Dark Mods` label, and place controls in disjoint subcategories
  `/MissingPersons` and `/PacificaTyphoon`. No child-control collision is
  present; acknowledge `CET-SETTINGS-CONTAINER-SHARED` without a patch.
- [x] Bulk-audit the six current `CFG-SCOPE-MULTI-PACKAGE` ownership findings:
  `cet:MissingPersons`, `cet:WeatherSwitcher`, `engine-config`,
  `redscript-config-framework`, `r6-input`, and `redscript-user-hints`. All
  contributed documents parse successfully, and none of these scope findings
  contains an exact-path overlap; exact paths remain covered by separate rules.
  Acknowledge all six INFO findings as intentional multi-package ownership.
- [x] Audit ten `CORE-EXACT-PATH` winners belonging to private fixes: the three
  HG Enemies/NCEE cleanup `.xl` files, combined INCF streaming fix, TheNullifier
  GIM fix, They Will Remember phase fix, Clothing Improved/Quickhack
  compatibility entry, and the three-file Breaching root. All are the intended
  Vortex winners. In the Breaching root, `init.lua` and `GameSettings.lua` are
  byte-identical support copies and only `GameUI.lua` removes the obsolete hook.
  Acknowledge these ten INFO findings and rebuild after relevant upstream updates.
- [x] Audit eleven more `CORE-EXACT-PATH` private-fix winners: Missing Persons
  UTF-8 localization; the four-file No Shooting Delay root; Better Leveling
  Reflexes gate fix; both Better Leveling/Upgrade Weapons compatibility scripts;
  Cyberware-EX/VanillaPlus compatibility; Night City Skies schema neutralizer;
  and Attachments Crafting base-case fix. All are intentional. In No Shooting
  Delay only `init.lua` differs, while its three support modules are byte-identical
  upstream copies. Acknowledge all eleven and rebuild after upstream updates.
- [x] Audit sixteen additional `CORE-EXACT-PATH` private-fix winners: three
  More Mods More Fun 1.1 overrides (Attachments Unrestricted plus the melee and
  ranged More Mods More Fun files), twelve Better Living Buffs rejected-field
  overrides, and the NCEE NPC invalid vendor-property override. Every deployed
  copy is the intended repair already validated by a clean runtime rescan.
  Acknowledge all sixteen and rebuild the relevant repair package after any
  affected upstream mod update.
- [x] Audit the four remaining `CORE-EXACT-PATH` winners from More Mods More Fun
  repair 1.1: the compatibility patch and 6 More Weapon Mod Slots melee/ranged
  YAML pairs. These are the other four documents in the validated seven-file
  repair package; acknowledge them and rebuild 1.1 after any related upstream
  package changes.
- [x] Audit `INPUT-BASELINE-OVERWRITE` fingerprint `fc44f76c…` from Dodge Dash
  Sprint with Shift. Its `Dodge_Button` replacement intentionally preserves the
  controller B/Circle binding while replacing the base-game Left Control entry
  with Left Shift, matching the mod's purpose. Acknowledge as intentional input
  rebinding and verify dodge/dash/sprint behavior during the consolidated
  in-game validation pass.
- [x] Audit `INPUT-NODE-APPEND-COMPOSABLE` fingerprint `8c12bc94…`: 21 shared
  input contexts from Attachments Unrestricted, DigitalVixenCore, Redscript
  Config Framework, Status Effects Hotkey, and Stealthrunner all explicitly use
  `append="true"`. Input Loader retains every provider's children, while any
  incompatible child repetitions are covered by separate scanner rules.
  Acknowledge this composable INFO finding without a patch.
- [x] Bulk-audit fifteen `RS-WRAPPER-CHAIN` fingerprints beginning `07de9a52…`
  through `01728d27…`. Every REDscript wrapper on every reported exact signature
  invokes `wrappedMethod`, including the large `PlayerPuppet.OnGameAttached`
  chain; therefore the original methods and earlier wrappers remain reachable.
  Acknowledge all fifteen compatible INFO findings without a patch. Treat any
  future `RS-WRAPPER-SKIPS-WRAPPED-METHOD` or replacement rule separately.
- [x] Bulk-add acknowledgements for all 34 still-active `RS-WRAPPER-CHAIN`
  findings directly to `acknowledgements.yaml`, preserving the user's existing
  entries. Post-edit verification found 205 total acknowledgement fingerprints,
  zero duplicates, and zero active wrapper-chain fingerprints missing from the
  file. A fresh scan is still required for the HTML report to reflect them.
- [x] Audit three `TXL-ARRAY-COMPOSABLE` fingerprints (`764d3d8a…`,
  `e4291cf2…`, and `189caf03…`). They respectively append distinct player stat
  modifiers, distinct DigitalVixenCore/Stealthrunner ripperdoc stock entries,
  and distinct attachment tags. No provider replaces a whole array, duplicates
  another provider's value, or removes a value another provider adds.
  Acknowledge all three INFO findings without a patch.
- [x] Audit `TXL-CROSS-MOD-DEPENDENCY` fingerprint `372254b9…`. The generated
  More Mods More Fun repair intentionally consumes the custom attachment-slot
  records from 6 More Weapon Mod Slots (21,232 references across 60 targets)
  and clones 98 scope records supplied in the installed attachment/crafting
  stack. Both provider relationships are expected for this combined repair;
  acknowledge the INFO finding, keep the providers installed, and re-audit if
  either provider or the repair package is removed or updated.
- [x] Audit `TXL-EMPTY` fingerprints `c7124a8e…` and `e98e679c…`. Both source
  files are exactly zero bytes. Iconic Shops' `IconicShop/fix.yaml` is an inert
  leftover/placeholder beside its populated `duplicateItems.yaml`, while Night
  City Alive's `cdpr-to-low.yml` is the no-op baseline counterpart to the
  populated `low-to-std.yml` preset. Neither overrides another staged provider
  or contributes a TweakDB operation; acknowledge both INFO findings.
- [x] Audit all 30 currently active consolidated
  `XEC-CET-OBSERVER-REDSCRIPT-METHOD` findings. The 78 REDscript references
  comprise 74 wrappers that all invoke `wrappedMethod` and four intentional
  menu/shard replacements. CET contributes only additive `Observe`,
  `ObserveBefore`, or `ObserveAfter` callbacks; source review found the
  lifecycle, quest, settings, shard, vendor, and menu side effects compatible
  with the final REDscript implementations. Acknowledge all 30 INFO findings;
  no compatibility package or load-order rule is required. All 30 fingerprints
  were subsequently added directly to `acknowledgements.yaml`; validation found
  241 total entries, zero duplicates, and zero active findings under this rule
  left unacknowledged. The four `XEC-CET-OVERRIDE-REDSCRIPT-CHAIN` findings were
  deliberately left untouched for separate review.
- [x] Audit all four active `XEC-CET-OVERRIDE-REDSCRIPT-CHAIN` findings. The
  Killstreak XP override adjusts `AddExperience.amount` and unconditionally
  invokes the effective REDscript chain; Better Leveling then observes the
  resulting Street Cred transition and refreshes its discount. The other three
  findings are settings-framework dispatch: Native Settings handles only its
  `fromMods` controls, MCM handles only MCM-managed controls, and mod_settings
  handles only its active screen; every non-owned path delegates to the wrapped
  implementation. The grouped Native Settings/MCM item covers seven compatible
  page-button and integer/float selector methods. All four are safe to
  acknowledge; no compatibility package or load-order rule is required.
- [ ] During the consolidated in-game validation pass, exercise representative
  scripted/flashback and vehicle combat while Flashback Fixer, Damage Scaling
  and Balance Extended, and Lifepath Bonuses are active. Flashback Fixer's CET
  observer intentionally adjusts `hitEvent.attackComputed` before the two
  REDscript damage/one-shot-protection wrappers run, so the systems compose but
  their numerical effects are cumulative. Confirm incoming damage and one-shot
  protection feel intentional; do not advance the intro solely for this check.

- [x] Three-way inspect the Immersive Gigs / Minor Activities Quest Fixes
  `ma_wat_nid_22_phase.questphase` overlap with WolvenKit. Minor Activities
  changes only `VehicleQuestVisualDestructionEvent.frontLeft` from `1` to `0`;
  Immersive Gigs adds 16 nodes and graph rewiring while retaining `1`.
- [x] Build private Vortex package `Immersive Gigs - Minor Activities Quest
  Fixes Compatibility-1.0.0.zip` from the Immersive Gigs resource with only
  `frontLeft` changed to `0`. WolvenKit JSON/CR2W round-trip validation retained
  all 114 nodes; archive extraction matched the validated CR2W hash exactly.
  Do not publish it because Minor Activities Quest Fixes permits only personal
  modifications without author consent.
- [x] Revalidate the merged Immersive Gigs / Minor Activities quest archive
  after upgrading WolvenKit Console to 8.20.0. The extracted CR2W hash remains
  exact, serialization still reports 114 nodes with `frontLeft: 0`, and a real
  scanner-provider integration succeeds. Scanner v0.28.11 also accepts valid
  serialized JSON defensively if WolvenKit returns a spurious nonzero status.
- [ ] Import and deploy that compatibility package, then use Archive Conflict
  Checker to put `! 00_immersive_gigs_minor_activities_compat.archive` before
  both `!Immersive_gigs.archive` and `! minor_activities_quest_fixes.archive` in
  the active `modlist.txt`. Rescan, acknowledge the expected three-provider
  overlap as merged, and during the consolidated gameplay pass verify Six Feet
  Under's vehicle damage plus Immersive Gigs acquisition/briefing behavior.

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
- [x] Resolve quest parents through active ArchiveXL `resource.scope` aliases.
  This removes the false Immersive Gigs missing-parent warning for the bundled
  `cyberpunk2077.quest` root while preserving genuine missing-resource findings.
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
