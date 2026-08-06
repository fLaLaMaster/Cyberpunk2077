# Codex Worklog

This is a chronological handoff log. Add new entries at the top of the History
section. Record material changes, decisions, validation, and generated outputs;
do not use it as a raw command transcript.

## Current state

- Scanner version: `0.28.11`
- Implemented ecosystems: ArchiveXL, TweakXL, REDscript, CET Lua, Input Loader XML, RED4ext/native frameworks, CET-to-REDscript hooks, and CET-to-TweakXL TweakDB cross-analysis
- Primary report: `reports/current/compatibility-report.html`
- Automated tests: 123 passing
- Last complete scan: successful on 2026-08-06
- The v0.27.0 frozen baseline was not modified by Codex; the user has now begun
  manual review and may change the mod collection

## History

### 2026-08-06 — Immersive Relic / False Encumbrance compatibility

Traced a behavioral conflict between Immersive Relic English 1.5.1 and False
Encumbrance Fix 1.0. Immersive Relic intentionally applies
`BaseStatusEffect.Encumbered` every 0.1 seconds during its malfunction. False
Encumbrance Fix wraps `PlayerPuppet.OnStatusEffectApplied` and immediately
reevaluates every Encumbered application, removing it whenever carried weight
does not justify the status.

Built the Vortex-ready package
`C:\Games\Programs\Mods\cyberpunk2077-mods\Immersive Relic - False Encumbrance Fix Compatibility-1.0.0.zip`.
It overrides only False Encumbrance Fix's
`r6\scripts\FalseEncumbranceFix\FalseEncumbranceFix.reds` and retains the
upstream file verbatim except for a narrow guard around that immediate
reevaluation. The guard recognizes Immersive Relic's overlapping
`IconicDetectorRushPlayerBuffLegendaryPlusPlus` and `JohnnySicknessHeavy`
markers, which cover the forced-encumbrance interval. Outside that interval,
False Encumbrance Fix follows its original behavior.

Verified the ZIP contains only the README and expected REDscript path. The
scanner's REDscript parser extracted one document and 12 annotations with zero
findings. Package SHA-256 is
`4EAD2F3EFA3B8876FE0135604AED7DD237551135A897F6BE6A1DB86DB3C9A233`.
Runtime REDscript compilation and both intentional/stale encumbrance behaviors
remain to be checked after the user imports and deploys the package after False
Encumbrance Fix.

### 2026-08-06 — CET override / REDscript chain cross-audit

Audited all four active `XEC-CET-OVERRIDE-REDSCRIPT-CHAIN` findings at source
level. Killstreak XP's `PlayerDevelopmentSystem.OnExperienceAdded` override
modifies the request amount and always calls its `wrapped` callback; Better
Leveling's REDscript wrapper remains reachable and refreshes its Street Cred
discount after the effective XP operation.

The other three findings are intentional settings-framework dispatch chains.
Native Settings owns controls only while `nativeSettings.fromMods` is true;
MCM's REDscript wrappers own only MCM-managed/active controls; mod_settings owns
only its active settings screen. Non-owned branches delegate to `wrapped` or
`wrappedMethod`. The grouped Native Settings/MCM finding covers seven compatible
page-button and integer/float selector methods. No suppressed cross-framework
behavior, compatibility patch, or load-order requirement was found. All four
INFO findings are safe to acknowledge; this audit did not modify
`acknowledgements.yaml`.

### 2026-08-06 — CET observer / REDscript method cross-audit

Audited every currently active `XEC-CET-OBSERVER-REDSCRIPT-METHOD` finding in
`reports/current/compatibility-findings.json`: 30 consolidated findings spanning
player lifecycle/input, quest state, settings and menu controllers, shards,
vendors, damage processing, and HUD initialization. The report contains 74
REDscript wrappers and four replacements across these findings. Every wrapper
invokes `wrappedMethod`; the replacements are intentional menu/shard
implementations, and all CET participants are additive observers around the
effective REDscript method.

Source-level review found no suppressed method implementation, competing
replacement, or required compatibility patch. The menu/settings integrations
operate on the final generated controls, while lifecycle and quest observers
update separate mod-owned state. All 30 current INFO findings are safe to
acknowledge. One intentional cumulative interaction remains on the gameplay
checklist: Flashback Fixer's CET callback changes `hitEvent.attackComputed`
before Damage Scaling and Balance Extended and Lifepath Bonuses process the same
hit through REDscript. This is deterministic composition rather than a loader
conflict, but representative scripted/vehicle combat should be sanity-checked.

At the user's request, added acknowledgements for all 30 audited fingerprints
directly to `acknowledgements.yaml`. Post-edit validation parsed the YAML as
version 1 with 241 entries, found zero duplicate fingerprints and zero active
observer/REDscript findings missing, and confirmed that none of the four active
`XEC-CET-OVERRIDE-REDSCRIPT-CHAIN` findings was acknowledged by this operation.

### 2026-08-06 — Beautiful Eyebrows 01/02 automatic merge verified

Reviewed the ArchiveXL declarations, serialized customization references, and
archive manifests for Beautiful Eyebrows 01 and 02. Both intentionally extend
the female and male `head/name/eyebrows` switcher. Each pack contributes 2,880
choice identities, 240 customization group entries, 240 scoped resources, and
160 resource-patch identities; the two sets have zero identity intersections
in all four categories. Their 402-member archives also have no shared internal
paths. The only common declarations are four identical copy redirects for the
male/female base eyebrow morph and mesh resources, already classified as INFO.
ArchiveXL therefore performs the required merge itself; no private
compatibility package or archive ordering rule is needed.

### 2026-08-06 — WolvenKit Console upgraded to 8.20.0

Verified that `C:\Games\Programs\WolvenKit-Console\WolvenKit.CLI.exe` now has
file/product version `8.20.0.0` / `8.20.0` and reports `8.20.0` through the CLI.
The configured executable path in `cp77compat.yaml` is unchanged, so no scanner
configuration migration was required.

Because 8.20.0 includes quest and scene graph handling changes, re-opened the
private Immersive Gigs / Minor Activities compatibility archive with the new
CLI, selectively extracted its merged questphase, and serialized it back to
JSON. The extracted CR2W retained the previously validated SHA-256
`053AE455A3A0C22939A10F90E6D7003D60B3BBB90F3AF95EA5D5097971F279A7`; the
serialized graph still has 114 top-level nodes and the intended
`VehicleQuestVisualDestructionEvent.frontLeft: 0` value. A manual invocation
using the old `-p` option form emitted valid JSON but returned exit code 160;
the scanner's actual positional `convert serialize <path> --print` invocation
returned 0 and completed a real provider/cache integration successfully.

Hardened serialization so complete, parseable JSON is accepted even if a
future WolvenKit invocation supplies an erroneous nonzero status, while a
nonzero status without valid JSON remains an error. Added both regression
cases, bumped the scanner to v0.28.11, and passed all 123 tests.

### 2026-08-06 — Immersive Gigs / Minor Activities compatibility archive built

Built private Vortex package `Immersive Gigs - Minor Activities Quest Fixes
Compatibility-1.0.0.zip`. Used the serialized Immersive Gigs 2.1 resource as
the merge base and changed only nested phase node 171 / event node 25
`VehicleQuestVisualDestructionEvent.frontLeft` from `1` to `0`, incorporating
the Minor Activities Quest Fixes vehicle-damage correction without discarding
Immersive Gigs' 16 added nodes and graph rewiring.

WolvenKit successfully deserialized the merged JSON, serialized the resulting
CR2W back to JSON, and produced an exact semantic match with 114 top-level
nodes and `frontLeft: 0`. Packed the single resource into
`! 00_immersive_gigs_minor_activities_compat.archive`, re-extracted it by its
resource hash, and confirmed the extracted CR2W SHA-256 exactly matched the
validated source. The final ZIP was extracted again and its embedded archive
also matched exactly.

The deployed game contains `archive/pc/mod/modlist.txt`, currently listing
Immersive Gigs before Minor Activities Quest Fixes. That file overrides normal
ASCII filename sorting, so after Vortex deployment the compatibility archive
must be placed before both source archives through Archive Conflict Checker.
Deployment, rescan, and deferred quest behavior testing remain pending. Keep
the package private under the source author's personal-modification terms.

### 2026-08-06 — Immersive Gigs / Minor Activities questphase three-way review

Investigated the archive-member overlap on
`ma_wat_nid_22_phase.questphase`. Extracted the resource separately from
Immersive Gigs 2.1 and Minor Activities Quest Fixes 1.12.1, extracted current
vanilla by its FNV1A resource hash from `basegame_4_gamedata.archive`, and
serialized all three CR2W files to WolvenKit JSON.

The Minor Activities version differs from vanilla in exactly one semantic
value after excluding WolvenKit handle IDs: phase node 171 contains nested event
node 25, where `VehicleQuestVisualDestructionEvent.frontLeft` is changed from
`1` to `0`. Immersive Gigs retains `1`, adds 16 top-level nodes (263-278), and
rewires the surrounding quest flow for its cyberpsycho call/randomizer logic.
The mod authors' public guidance confirms the load-order tradeoff: letting
Minor Activities win preserves its Six Feet Under vehicle fix but may cause a
second briefing call with the Immersive Gigs cyberpsycho randomizer; letting
Immersive Gigs win loses that vehicle fix.

Concluded that this exact conflict is safely mergeable as a private package by
using Immersive Gigs as the base and changing only `frontLeft` to `0`, then
deserializing and packing with the already installed WolvenKit Console. No
additional tool is needed. Package creation awaits an explicit user request;
the Minor Activities author permits private modifications but not redistribution
without consent.

### 2026-08-06 — Upgrade Weapons Unlocked terminating-wrapper review

Reviewed the four `RS-WRAPPER-SKIPS-WRAPPED-METHOD` references retained in the
deployed Better Leveling/Upgrade Weapons Unlocked compatibility override:
`UpgradingScreenController.GetUpgradableList`, `FillInventoryData`,
`RPGManager.GetItemTierForUpgrades`, and
`UpgradingScreenController.ApplyQualityModifier`.

Each is an intentional full replacement. They respectively enumerate ordinary
weapons rather than vanilla's iconic-only set, repair/filter item tier state,
reconcile upgrade tier with the actual tier statistic, and implement the full
quality/Plus transition logic. Calling vanilla as well would duplicate list
processing, return the wrong tier result, or increment quality twice. The only
duplicate references in staging are the overridden upstream file and its
deployed exact-path compatibility winner; no unrelated installed mod targets
the signatures. Classified the grouped finding as safe to acknowledge without
another patch.

### 2026-08-06 — Smaller Cyberware Slots terminating-wrapper review

Reviewed the four `RS-WRAPPER-SKIPS-WRAPPED-METHOD` references in Smaller
Cyberware Slots (7x3): `CyberwareInventoryMiniGrid.SetupData`, `UpdateData`,
`SetPosition`, and `SetPosition_Animation`. All four copy the current vanilla
method bodies and intentionally replace the wrapping-count or positioning
formula for a maximum seven-column grid. Calling `wrappedMethod` would rebuild
the same inventory grid or run competing positioning animations twice.

The current REDscript reference inventory contains no other annotations for
the four exact signatures. Cyberware-EX touches the same class but replaces the
separate `GetSlotToEquipe` method, so it does not conflict here. Classified the
grouped review finding as intentional and safe to acknowledge without a patch.

### 2026-08-06 — Better Leveling Reflexes level-85 movement fix packaged

Built `Better Leveling Addon - Reflexes Level 85 Gate Fix-1.0.0.zip` as a
Vortex-ready one-file exact-path override for
`03_BetterLeveling_ReflexesLevel85Bonus.reds`. The existing Cool level-85 jump
bonus and attachment logic remain semantically unchanged. The two affected
movement wrappers now invoke the existing method first and add only a second
half-strength impulse when the player has Reflexes Skill level 85 or higher.
Ground dash is untouched; exhausted air dash, normal air dash, and air dodge
each use the matching vanilla static impulse parameter for the extra 50%.

Validated the override with the official REDscript CLI `lint` command against
the installed game's `r6/cache/final.redscripts` bundle. The package contains
only the expected `r6/scripts/Better Leveling Addon/Skill Progression/`
override and was written to
`C:\Games\Programs\Mods\cyberpunk2077-mods\Better Leveling Addon - Reflexes
Level 85 Gate Fix-1.0.0.zip`. Vortex deployment, rescan, and deferred
below/at-level-85 gameplay checks remain pending.

### 2026-08-06 — Better Leveling four-wrapper review and level-gate defect

Reviewed the four `RS-WRAPPER-SKIPS-WRAPPED-METHOD` references in Better
Leveling Addon - Skill Progression 1.0.1. The two
`NewPerksSkillBarLogicController` wrappers (`UpdateSkillsCount` and
`OnSkillLevelSpawned`) are intentional full vanilla-derived replacements: they
extend the skill reward UI through level 150 and switch to a selected milestone
window once the displayed proficiency reaches level 35. Calling vanilla too
would repopulate the same controller set without that filtering.

The two movement wrappers (`DodgeAirEvents.Dodge` and `DodgeEvents.Dash`) also
copy current vanilla and change only eligible air impulse from `1.0` to `1.5`,
so calling vanilla afterward would apply a second impulse and duplicate its
side effects. Their omission of `wrappedMethod` is structurally deliberate, but
the implementation has a real upstream gating defect: the file is named for
the Reflexes level-85 bonus, `BTL.ReflexesLevel85` contains only UI data with no
effector, and neither wrapper nor any adjacent code checks Reflexes proficiency.
The 50% air movement bonus therefore applies from a fresh character rather than
unlocking at Reflexes 85. No other installed script targets any of the four
exact signatures. Decided not to acknowledge the grouped finding yet; retained
a compatibility/fix package and before/after-level functional check as pending.

### 2026-08-06 — They Will Remember detection terminating-wrapper review

Reviewed the two `RS-WRAPPER-SKIPS-WRAPPED-METHOD` references in They Will
Remember 2.5a: `SecurityTurret.SetAsIntrestingTarget(wref<GameObject>)->Bool`
and `SenseComponent.OnDetectionReachedZero(ref<OnRemoveDetection>)->Bool`.

The current vanilla turret override only returns
`super.SetAsIntrestingTarget(target)`. TWR preserves that exact delegation for
ordinary targets but returns `false` when its `NPCClassifier` marks the turret
friendly and the target is the player. Calling vanilla afterward would discard
that friendly-turret exclusion. The current vanilla zero-detection callback only
calls `ReevaluateDetectionOverwrite(evt.target)`; TWR clears its own
identification, faction-identification, and turf-protection monitoring flags and
then performs the same reevaluation. Calling vanilla too would merely reevaluate
the same target twice. No other installed script targets either exact method,
so both references can be acknowledged without a compatibility package.
Deferred friendly/hostile turret and reacquisition checks to the consolidated
in-game validation pass.

### 2026-08-06 — Inventory Adjustments Hub tooltip terminating-wrapper review

Reviewed the two `RS-WRAPPER-SKIPS-WRAPPED-METHOD` references for
`ItemTooltipModController.SetData`, covering the
`MinimalItemTooltipModAttachmentData` and `UIInventoryItemModAttachment`
overloads in Inventory Adjustments Hub 1.4. Both bodies copy the current
vanilla widget population and deliberately alter it according to the configured
mod-info scheme: description, name, or name plus description. Calling vanilla
afterward would clear and repopulate the same container, defeating or
duplicating the selected presentation. No other installed script annotates
either exact overload, so the compatibility finding itself can be acknowledged
without a package.

Found a separate upstream disabled-state edge case: the global IAH switch can
set `xIAHub.isEnabled` false while the default `modInfoScheme` remains `Name`.
In that combination the wrappers clear the entries, skip the name because IAH
is disabled, and skip descriptions because the scheme is `Name`, producing an
empty non-empty attachment tooltip. This is not a cross-mod conflict and does
not affect normal default operation because IAH is enabled by default. Deferred
the three schemes plus global-disable behavior to the consolidated in-game pass;
a small exact-path guard/fallback package can be made if disabled mode matters.

### 2026-08-06 — Attachments Unrestricted slot-selector terminating-wrapper review

Reviewed the two `RS-WRAPPER-SKIPS-WRAPPED-METHOD` references for
`InventoryItemModeLogicController.GetMatchingSlot(...)` and
`InventoryItemModeLogicController.IsMatchingSlot(...)` in Attachments
Unrestricted 1. Both are intentional full selector replacements. They retain
vanilla's attachment-list and standard item-type checks while also recognizing
the mod's TweakXL-defined `HasScopeEquipped` and `HasMuzzleEquipped` stat
markers, preferring empty native slots and permitting the selected compatible
slot for the unrestricted behavior.

The active `EquipItem` wrapper uses both selectors for attachment items,
enforces the optional one-scope, one-silencer, and one-muzzle-brake policies,
then invokes `EquipPart`; non-attachment items still call vanilla. Calling the
vanilla selectors as well would discard the custom stat classification and
cannot meaningfully merge two `TweakDBID`/`Bool` return decisions. No other
installed script annotates either exact method. The flow composes with
Retrievable Weapon Mods: Attachments Unrestricted selects the slot and the
latter handles an occupied-slot swap. No compatibility package is needed;
deferred representative custom-slot and limit checks to the consolidated
in-game pass.

### 2026-08-06 — Retrievable Weapon Mods EquipPart terminating-wrapper review

Reviewed `RS-WRAPPER-SKIPS-WRAPPED-METHOD` for
`InventoryItemModeLogicController.EquipPart(script_ref<InventoryItemData>,
TweakDBID)->Void` in Retrievable Weapon Mods 1. The wrapper deliberately
replaces vanilla's occupied-slot handling: instead of rejecting an occupied
weapon-mod slot or using the destructive replacement path, it immediately
queues the game's `SwapItemPart` request and records the normal installation
telemetry.

The current vanilla request removes the existing non-base part, sends the
equipment/UI uninstall updates, and installs the selected part. Calling
`wrappedMethod` afterward would run a second install/replacement transaction
and could duplicate, consume, or reject the operation, so terminating the
chain is required for the mod's purpose. Attachments Unrestricted contains an
old wrapper for the same method only inside a block comment; it is not an
active competitor. No compatibility package is needed. Deferred an in-game
occupied-slot inventory-count check to the consolidated validation pass.

### 2026-08-06 — NCA Prevention-alert terminating-wrapper review

Reviewed `RS-WRAPPER-SKIPS-WRAPPED-METHOD` for
`ReactionManagerComponent.CanTriggerAlertedFromHostileStim(ref<StimuliEvent>)`
in NCA Standard Density 2.2.1. The locally decompiled vanilla body returns
`false` immediately for every Prevention-system NPC and otherwise delegates to
`StimFilters.CanTriggerAlertedDirectly`.

NCA deliberately removes only that blanket Prevention exclusion and applies
the same stimulus filter to all owners. Its adjacent reaction hooks form a
coherent policy: Prevention NPCs are allowed to process selected stimuli, and
non-player gunshots that would be Intruder reactions have their priorities
downgraded to Investigate. Calling vanilla would preserve the early `false` and
defeat this behavior. No other installed script targets the exact method and
REDscript compiles successfully. The finding can be acknowledged without a
compatibility package.

### 2026-08-06 — Equipment-EX transmog terminating-wrapper review

Reviewed `RS-WRAPPER-SKIPS-WRAPPED-METHOD` for
`UIInventoryItemsManager.IsItemTransmog(ItemID)->Bool` in Equipment-EX 1.2.9.
The vanilla method checks a cached list of the six active wardrobe override
items. Equipment-EX intentionally replaces that ownership model with
`OutfitSystem.IsActive() && OutfitSystem.IsEquipped(itemID)`.

The surrounding implementation confirms a complete wardrobe subsystem swap:
on first use it imports vanilla clothing sets as named Equipment-EX outfits; on
restore it invalidates any active vanilla clothing set; vanilla wardrobe
equip/unequip handlers are replaced with no-ops; and the inventory, wardrobe,
preview, and photo-mode paths use Equipment-EX's persistent outfit state.
Combining the stale vanilla cache with the custom state would misclassify items.
No other installed script targets the exact method and REDscript compiles
successfully. The finding can be acknowledged without a compatibility package.

### 2026-08-06 — Dodging Fix AI-selector terminating-wrapper review

Reviewed `RS-WRAPPER-SKIPS-WRAPPED-METHOD` for
`TweakAIActionRecord.GetActionRecordFromSelector(...)` in Dodging Fix 0.11.
Compared the complete 90-line mod body with the same method from the locally
decompiled current vanilla script bundle.

The mod preserves the vanilla selector traversal, alternatives limit, null
handling, animation-variation blackboard state, iterator updates, and default
action fallback. Its intended delta is inside the traversal: after normal
`AICondition.ActivationCheck` rejects an action carrying `AITicketType.Dodge`,
the mod accepts it when that action's own activation condition passes. This
cannot be added by calling the already-completed vanilla method before or after
the wrapper. No other installed script targets the exact method, and current
REDscript compilation succeeds. The finding is an intentional full-method
repair and can be acknowledged without another compatibility package.

### 2026-08-06 — Cyberware-EX perk-level terminating-wrapper review

Reviewed `RS-WRAPPER-SKIPS-WRAPPED-METHOD` for
`PlayerDevelopmentData.HandleAddingPerkLevel(Int32,Int32)->Void` in the
deployed Cyberware-EX / VanillaPlus Parkour compatibility override. Used the
official redscript 0.5.31 CLI from `jac3km4/redscript` in the ignored scanner
cache to decompile the local vanilla `final.redscripts` bundle.

The vanilla method handles Technical Central Milestone 3 level 3 by powering up
musculoskeletal cyberware slots 0, 1, and 2. Cyberware-EX deliberately replaces
that body with `ApplyAreaPowerUps(MusculoskeletalSystemCW)`, which iterates all
slots so its expanded slots receive the same treatment. It is the only active
installed annotation for the exact signature. Calling `wrappedMethod` would
repeat the vanilla effect on slots 0–2 and is not appropriate. No compatibility
package is needed; acknowledge this as an intentional superseding wrapper.

### 2026-08-06 — Always First Equip terminating-wrapper review

Reviewed the single `RS-WRAPPER-SKIPS-WRAPPED-METHOD` finding for
`EquipCycleDecisions.ToFirstEquip(ref<StateContext>,
ref<StateGameScriptInterface>)->Bool` in Always First Equip 2.1.5. The wrapper
unconditionally returns `false`, but this is deliberate: the mod disables the
vanilla transition decision and implements its configurable first-equip choice
through its `FirstEquipSystem.HasPlayedFirstEquip` wrapper and full
`EquipmentBaseTransition.HandleWeaponEquip` replacement.

No other installed `.reds` file annotates `EquipCycleDecisions`, and the current
REDscript log compiled the mod successfully into `final.redscripts.modded`.
Calling `wrappedMethod` here would re-enable the vanilla decision path and work
against the mod's replacement design. No compatibility package is needed; the
review finding can be acknowledged as an intentional terminating wrapper. A
basic first-equip/cooldown/hotkey behavior check was added to the consolidated
gameplay checklist.

### 2026-08-05 — Missing CET GetMod target review

Reviewed all six active `CET-GETMOD-TARGET-MISSING` call sites. Every absent
target is an optional integration or a deliberate presence/conflict probe, and
all usages are nil-safe:

- Immersive First Person returns only a boolean presence check for
  `BetterVehicleFirstPerson`.
- Minimap Widgets uses `TimeIsRunningOut` to enable a fifth clock mode, falls
  back to modes 1–4 when absent, and checks the handle again before use.
- Personal Link Animations Patch checks for the obsolete predecessor `Jacking
  Animation Patch`; absence is the desired state.
- RadioExt stores the optional `trainSystem` handle, and `handleTS()` guards
  both the handle and its `stationSys` member.
- Redscript and CET Mods Settings checks for incompatible
  `UnifiedModSettings`; absence is likewise the desired state.

No package or dependency installation is needed. The consolidated review
finding can be acknowledged as expected optional integrations with nil guards.

The user also confirmed the Clothing Improved / Quickhack Fixes runtime-flat
override report disappeared after deploying its compatibility package and
rescanning.

### 2026-08-05 — Clothing Improved / Quickhack Fixes Wreath compatibility

Investigated the cross-ecosystem runtime overwrite of
`Items.IntrinsicFabricEnhancer10_inline2.value`. Quickhack Fixes repurposes the
record as a combined modifier with `value: 1`: it transfers
`IntrinsicQuickHackUploadBonus` into `Transfer_USpeed_QHF`, then its Wreath GLP
applies that custom stat to `QuickHackUploadTimeDecrease` with a separate
`0.01` factor. Clothing Improved's CET `onInit` subsequently writes `-0.01` to
the same flat. That reverses and reduces the transferred stat by 100 times
before the GLP factor, largely breaking the Wreath upload-speed correction.

Clothing Improved labels the field as unknown and writes the documented old
vanilla value, so the write is redundant without Quickhack Fixes and harmful
with it. Created
`C:\Games\Programs\Mods\cyberpunk2077-mods\Clothing Improved - Quickhack Fixes Wreath Compatibility-1.0.0.zip`
as a one-file exact CET entrypoint override that removes only this `SetFlat`
call. Exact diff confirms the single-line removal. Focused CET and TweakXL
parsing is clean, no active CET write remains for the target, the cross finding
disappears in simulated deployment, and the CET/cross-ecosystem unit suites
pass (13 tests). ZIP SHA-256:
`C8774DA35019A5D6BFCA39E844FB8E0F693BFA6486ACEC63FCC4D7ACD9282FC2`.
The user subsequently deployed the package and confirmed the cross-ecosystem
report disappeared after launch and rescan. Wreath behavior remains on the
consolidated gameplay checklist.

### 2026-08-05 — Weapon-slot dangling collectible references

The user confirmed the Better Leveling / Upgrade Weapons Unlocked terminated
wrapper-chain report disappeared after deploying the compatibility package and
rescanning.

Resolved all 12 hash-only `TXL-RUNTIME-DANGLING-REFERENCE` events on
`Items.TechMod2_Common.placementSlots`. Each hash maps exactly to an
`AttachmentSlots.*_Collectible` name; the length displayed by TweakXL is
hexadecimal. The missing set is the two Smart AR/SMG/LMG, two Tech AR/SMG/LMG,
two Tech handgun, two Power precision/sniper, two Smart shotgun, and two Tech
shotgun collectible slots. TweakXL's post-import validation proves those
records remain absent after every installed config loads. More Mods More Fun
and Attachments Unrestricted both append the same invalid set; creating new
records would be ineffective because no weapon owns these nonexistent slots.

Created the replacement package
`C:\Games\Programs\Mods\cyberpunk2077-mods\More Mods More Fun - 6 More Weapon Mod Slots Ambiguous Record Fix-1.1.0.zip`.
It retains all six 1.0.0 ambiguity-repair overrides, removes only the 12 invalid
collectible references from `MoreModsMoreFun_Ranged.yaml`, and adds one exact
`Attachments Unrestricted.yaml` override removing the same 12 references.
All seven YAML documents parse without errors; 36,193 expanded references were
extracted, the TweakXL unit suite passes (14 tests), and exact diffs confirm no
other content change apart from the source file's final newline normalization.
ZIP SHA-256:
`9702C02680D0ACA6E1BEE798327E5BE400D807FD597AA5E31FB07765AB1889DE`.
The user subsequently replaced 1.0.0 with 1.1.0 and confirmed the report is
clear after launch and rescan. Functional slot/attachment verification remains
deferred to the consolidated gameplay pass.

### 2026-08-05 — Better Leveling / Upgrade Weapons Unlocked upgrade merge

Investigated the terminated REDscript wrapper chain for
`CraftingSystem.UpgradeItem(wref<GameObject>, ItemID)->Void`. Both Better
Leveling Addon - Skill Progression and Upgrade Weapons Unlocked contain full
standalone upgrade implementations and neither calls `wrappedMethod`; adding a
call would execute two material-removal, XP, and item-upgrade routines and is
therefore unsafe.

Created
`C:\Games\Programs\Mods\cyberpunk2077-mods\Better Leveling Addon - Upgrade Weapons Unlocked Compatibility-1.0.0.zip`
as a two-file exact-path overlay. It removes Better Leveling's duplicate
`UpgradeItem` annotation while retaining its Technical 150 helper, converts
Upgrade Weapons Unlocked's complete implementation from a terminating wrapper
to an explicit replacement, and folds in Better Leveling's Technical 150
double upgrade-marker step plus persistent per-upgrade weapon damage bonus.
The Upgrade Weapons Unlocked material, quality/plus, iconic, XP, and
upgrade-to-max logic otherwise remains intact.

Focused scanner validation found one active `method.replace` reference for the
exact signature, no parse findings, and no comparison finding for it. The
REDscript unit suite passes (3 tests). ZIP SHA-256:
`8337E7B9ADE0C68FFBD0E27F20CA5A5CE7F58390ED5102EBBB5B6935AC4F4867`.
The user subsequently deployed the package and confirmed the report
disappeared after the next launch and rescan. Full upgrade-behavior testing
remains deferred to the consolidated gameplay pass.

### 2026-08-05 — Night City Skies intentional schema override review

Verified the remaining `CFG-PATH-OVERRIDE` for
`NightCitySkies.schema.json`. The local repair is the deployed winner and is a
valid three-byte `{}` JSON document; the upstream provider is correctly marked
overridden and still fails at line 51 because it concatenates two root objects.
This is not a new compatibility defect. The finding is technically accurate
configuration provenance but expected for the deliberate repair and should be
acknowledged with that reason rather than patched again.

The user also confirmed the Missing Persons Spanish UTF-8 warning disappeared
after deploying its one-file repair and rescanning.

### 2026-08-05 — Missing Persons Spanish UTF-8 repair

Investigated Missing Persons 2.3.0's `languages\es-es.json` encoding warning.
The source is structurally valid JSON, but the entire localized document is
Windows-1252: 16 non-ASCII bytes encode the title's en dash and all accented
characters. This is not safely repairable by replacing only byte `0x96`.

Created
`C:\Games\Programs\Mods\cyberpunk2077-mods\Missing Persons - Spanish UTF-8 Fix-1.0.0.zip`
as a one-file exact-path override. Strict UTF-8 parsing succeeds without a BOM
or replacement characters. The converted document has the same 25 entries and
the exact same scanner semantic hash as the CP-1252 source. Simulated deployment
has zero `CFG-NON-UTF8` findings and only the expected informational identical
path notice. ZIP SHA-256:
`72CC1D07716FD69D17D4634579E57A70D333C651D8203203EB4BF48D2C6B3017`.

The user confirmed the preceding Breaching obsolete-hook runtime finding
disappeared after deployment and rescan.

### 2026-08-05 — Breaching obsolete pause-menu Credits hook repair

Attributed CET's otherwise anonymous runtime failure for
`MenuScenario_PauseMenu.OnSwitchToCredits`. Five deployed mods contain an old
GameUI table with that row, but reachability and subscription analysis isolates
the emitter to `CsBreachingBreached`: it alone calls `GameUI.Listen("MenuNav")`
and therefore initializes the menu-observer table. Weather Switcher, Missing
Persons, Pacifica Typhoon, and RadioExt load their copies only for session
events. Multiple newer installed GameUI variants already omit the obsolete
method, and CET confirms it is absent from current RTTI.

Created
`C:\Games\Programs\Mods\cyberpunk2077-mods\Breaching - Obsolete Credits Hook Fix-1.0.0.zip`.
It bundles the complete three-file `CsBreachingBreached` CET root to avoid a
cross-package module notice, removes only the `OnSwitchToCredits` table row,
and leaves `init.lua` plus `GameSettings.lua` byte-identical to upstream. All
literal imports resolve and both upstream/patched roots retain the same
unrelated optional `GetMod` review finding. ZIP SHA-256:
`EDDFC756A070DA52359EA847F3188346C890DC1744AA0FB9627F737FF9C03D1B`.

The user confirmed the preceding No Shooting Delay missing-module report
disappeared after deploying its repair and rescanning.

### 2026-08-05 — No Shooting Delay stale module import repair

Investigated No Shooting Delay 1.2-fix's `CET-MODULE-MISSING` finding. Its
entrypoint requires `Modules/main.lua`, but the source and deployed roots
contain only `functions.lua`, `Language File.lua`, and `Native Settings.lua`.
The allegedly missing implementation is not missing: the same `init.lua`
defines the complete global `main()` function later in the file and invokes it
from `onInit`. The per-mod runtime log is empty, consistent with CET continuing
past the ignored module return. Pre-fix `buffer.json` creation and later
`config.json` updates prove that the registered `onInit` callback ran under CET
1.37.1, so the upstream mod was likely functional despite this warning. The
literal require remains structurally invalid and fragile across loader changes.

Created
`C:\Games\Programs\Mods\cyberpunk2077-mods\No Shooting Delay - Missing Module Require Fix-1.0.0.zip`.
It removes only `require("Modules/main.lua")` from the upstream entrypoint and
bundles all three unchanged upstream module files. Bundling the complete
four-file root avoids introducing a scanner cross-package dependency after the
exact-path override. Focused validation parsed all four Lua documents, resolved
the three remaining requires, and produced zero CET findings; hashes confirm
all bundled module files are byte-identical to upstream. ZIP SHA-256:
`0A00EF9A151C7216344E1887469A8E1630C4A65600688466BFBAA2F9BC3E0961`.

The user also confirmed cleanup 1.1.1 removed the seven NCEE localization
warnings after deployment and rescan.

### 2026-08-05 — NCEE localization fallback correction and cleanup 1.1.1

The user confirmed cleanup 1.1.0 removed the missing Italian resource finding,
but its next game session produced seven ArchiveXL localization-overwrite
warnings. Exact rotated-log context showed the standalone Italian-only config
loaded `localization\it-it\onscreens\ncee_onscreens.json` under an English game
session, after which NCEE's main config loaded `en-us` and overwrote the seven
custom secondary-key entries (`clouds_reaberta`, `Micky`, `ncee_maelsripper`,
and four Rocky Ridge/Panam keys). ArchiveXL uses a config's sole locale as a
fallback, so the separate one-locale `.xl` architecture was incorrect. The
reported Mod Settings participant came from stale `Loading` context rather than
the localization resource actually preceding the warnings.

Created
`C:\Games\Programs\Mods\cyberpunk2077-mods\HG Enemies and NCEE - Missing NG Plus Hook Cleanup-1.1.1.zip`.
It keeps `hidden_gem_enemies.xl`, `ncee_inimigos.xl`, and `ncee_npcs.xl`
byte-identical to cleanup 1.0.0, retains the valid one-resource Italian archive,
and removes the standalone Italian `.xl`. Italian is therefore selected only
through NCEE's complete 19-locale map. Simulated ownership and resolution show
no parse, resource, quest, or archive-collision findings. ZIP SHA-256:
`780099E4A39D1A31214CEA07051CFE2B6D6A418D1126ED4409B817A07A9CE640`.

Extended archive-resource resolution so a logical original mod reference can
be satisfied by a companion archive belonging to the package that supplied the
active exact-path `.xl` override. Also added precise parsing of ArchiveXL's
`Merging entries from` / `Item #... overwrites entry` sequence: overwrite
events now carry the actual resource path and key instead of inheriting stale
config attribution. Bumped the scanner to v0.28.10. All 121 tests pass, and the
user's exact log now parses as seven NCEE `en-us` overwrite events with no Mod
Settings attribution. The user later deployed cleanup 1.1.1 and confirmed the
seven warnings disappeared after launch and rescan.

### 2026-08-05 — NCEE NPC missing Italian localization and cleanup 1.1.0

Investigated NCEE NPC 2.0.3's missing
`localization\it-it\onscreens\ncee_onscreens.json`. Its active NG-cleaned
`ncee_npcs.xl` declares 19 locales, but the source archive contains 18 and omits
only Italian. No alternate Italian resource exists in the installed collection
or local downloads. The current mod file on Nexus is version 2.0.3.

Created a proper 14-entry Italian CR2W localization from the mod's English
source entries, preserving identifiers, primary keys, Cyberpunk terminology,
names, and line breaks. WolvenKit 8.19.0 compiled the resource, packed it into a
one-member archive, unpacked it, and successfully serialized it again with all
14 expected entries.

Because `ncee_npcs.xl` was already overridden by the optional NG+ cleanup,
created
`C:\Games\Programs\Mods\cyberpunk2077-mods\HG Enemies and NCEE - Missing NG Plus Hook Cleanup-1.1.0.zip`
as a replacement for version 1.0.0. It retains `hidden_gem_enemies.xl` and
`ncee_inimigos.xl` byte-for-byte, removes only the missing Italian declaration
from the cleaned `ncee_npcs.xl`, and re-registers Italian through a separate
patch-owned `.xl` and archive. A simulated deployment after removal of cleanup
1.0.0 resolves all 19 localizations and all 18 retained quest attachments with
no parse, missing-resource, implicit cross-mod, quest, or archive-collision
findings. ZIP SHA-256:
`9D16106E9ACCC34B32FA22586649B44874A6DEA528983BC412E53AA76A4E75A4`.

The user must uninstall cleanup 1.0.0 from Vortex before importing 1.1.0, then
make 1.1.0 win the original three `.xl` conflicts. The user also confirmed the
preceding Better Armor Tooltip localization finding disappeared.

### 2026-08-05 — Better Armor Tooltip missing es-mx localization repair

Investigated Better Armor Tooltip 1.0.1's
`AXL-RESOURCE-NOT-INDEXED` finding. `BetterArmorTooltip.archive.xl` declares
19 locales, while the 16 KiB archive contains exactly 18 cooked localization
resources and omits only
`better_armor_tooltip\localization\es-mx.json`. The author describes the
corrected tooltip as available in all languages, so deleting the declaration
without replacement would suppress the warning while leaving Latin American
Spanish users with the original inaccurate tooltip text.

Created
`C:\Games\Programs\Mods\cyberpunk2077-mods\Better Armor Tooltip - Missing Latin American Spanish Fix-1.0.0.zip`.
Its exact-path `BetterArmorTooltip.archive.xl` override removes only the bad
line. A separate `BetterArmorTooltip-es-mx-fix.archive.xl` registers that locale
from a one-member companion archive containing a cooked copy of the author's
existing `es-es` translation. This keeps every valid original localization in
the original archive and gives the repair package explicit ownership of the
new resource.

WolvenKit 8.19.0 indexed the generated archive with exactly one resolved member.
Its unpacked member is byte-identical to the packed input (SHA-256
`483A6E58D44A5BCB9826F56C53113EB13FF441761765C3570B99D005F005DC2C`).
The real ArchiveXL parser and a simulated active deployment resolve all 19
localization declarations with no parse, missing-resource, implicit cross-mod,
or archive-collision findings. ZIP SHA-256:
`3B8A39C73CF693E9859A0874680B7F0AA4D9EB68A90096F8947A2526BAC829AB`.
Deployment/rescan and optional Latin American Spanish UI validation remain with
the user. The user also reported that the preceding They Will Remember repair
looks good.

### 2026-08-05 — They Will Remember Maelstrom redemption phase repair

Investigated They Will Remember 2.5a's two missing-child declarations. The
source `.xl` points both the base-game and Phantom Liberty roots at nonexistent
`mod\they_will_remember\quest\retaliation_quests\retaliation_maelstrom_pt1.questphase`.
The mod archive instead contains the otherwise undeclared
`redemption_quests\redemption_maelstrom_pt1.questphase`. Selective WolvenKit
serialization shows that phase consumes the Maelstrom degree-one fact and sets
`twr_redemption_part1_0`, matching the mod's REDscript redemption database and
flow. This is a directory/name copy-paste typo rather than an optional missing
dependency.

Created
`C:\Games\Programs\Mods\cyberpunk2077-mods\They Will Remember - Maelstrom Redemption Phase Fix-1.0.0.zip`.
Its full exact-path `they_will_remember.xl` override changes only the two bad
paths to `redemption_quests\redemption_maelstrom_pt1.questphase`. The real
ArchiveXL parser accepts the document with no findings; archive-manifest
resolution reports 32 owned child phases, zero missing children, 32 official
parents, and zero missing parents. ZIP SHA-256:
`3FA8F2122A1EA8A8209C50DF98A54C3AB99FAA0D15BE53B397CBF5D079B8CD10`.
Deployment, refreshed runtime verification, and later Maelstrom redemption
gameplay validation remain with the user.

The user also confirmed that the previously deployed HG Enemies/NCEE optional
NG+ hook cleanup removed its report findings.

### 2026-08-05 — HG Enemies/NCEE optional NG+ hook cleanup

Investigated three missing quest parents shared by HG Enemies 1.0.0, NCEE
Enemies 2.6.0, and NCEE NPC 2.0.3. Their `.xl` files attach 23 distinct child
phases to both `base\quest\cyberpunk2077.quest` and
`ep1\quest\ep1_standalone.quest`, then repeat every child against three absent
`mod\quest\newgameplus*` roots. This produces 69 skipped declarations,
consolidated by ArchiveXL into three warnings. The latest runtime session
confirms all 23 normal child phases merged successfully. None of the authors'
current Nexus requirements list a New Game Plus provider; NCEE Enemies 2.5
explicitly added compatibility with Hidden Gems Enemies.

Created
`C:\Games\Programs\Mods\cyberpunk2077-mods\HG Enemies and NCEE - Missing NG Plus Hook Cleanup-1.0.0.zip`.
It contains only `hidden_gem_enemies.xl`, `ncee_inimigos.xl`, and
`ncee_npcs.xl`. Automated exact-line comparison confirms every override differs
from its installed source only by removal of the NG+ path/parent pairs. The real
ArchiveXL parser accepts all three documents with no findings, retains 46 child
and 46 parent references, and contains no NG+ reference. ZIP SHA-256:
`2C4EEA79B60A61ED454D6C6FF4897C1E213BD42FA55D636311E2E4DF33F7C362`.

Extended ArchiveXL exact-path logical ownership to accept arbitrarily large
deletion-only overrides when there is one unique source provider. This keeps
the cleanup's surviving declarations attributed to their original mods rather
than creating false cross-mod dependencies. Bumped the scanner to v0.28.9 and
added regression coverage; all 119 tests pass. Deployment and refreshed runtime
verification remain with the user. The package must be disabled or rebuilt if
an actual NG+ provider is installed or any affected source mod updates.

### 2026-08-05 — ArchiveXL quest scope-alias resolution

Investigated Immersive Gigs' reported missing parent `cyberpunk2077.quest`.
The declaration is valid: ArchiveXL's deployed `Bundle/QuestBaseScope.xl`
defines that identifier as a resource scope combining the base-game and
Phantom Liberty quest roots. The latest runtime log confirms ArchiveXL merged
`mod\manual_gigs\quest\manual_gigs_update_2_1.questphase` successfully from
`!Immersive_gigs.archive.xl`.

Updated quest-parent resolution to index active `resource.scope` declarations.
Framework-bundled scopes are classified as official parents; custom scopes
retain own-provider or cross-mod dependency semantics. Added a regression case
for the bundled quest root and bumped the scanner to v0.28.8. All 118 tests
pass. A full current-corpus scan completed successfully and removed the
Immersive Gigs finding. The three genuinely absent New Game Plus parent
resources used by HG Enemies/NCEE remain active, confirming that missing-parent
detection was not weakened. No compatibility package is needed for Immersive
Gigs.

### 2026-08-05 — INCF streaming-mutation syntax repair and unsupported operations

Investigated the 10 `AXL-NODE-MUTATION-IGNORED` and nine
`AXL-NODE-MUTATION-UNKNOWN-FIELD` occurrences in the active lantern-fixed
`INCF.xl`. Cloned the official ArchiveXL source at commit
`55f48569f415b443debba4f4ad4cf241194cd06e`; its declared version is 1.27.1,
matching the installed runtime/file version. The implementation parses only
mapping-shaped actor/instance mutations, applies element transforms only to
collision/instanced mesh/destructible nodes, ignores unknown `nodeRefHash`, and
explicitly applies `nbNodesUnderProxyDiff` only when it is positive.

Seven negative proxy-count mutations and their seven `nodeRefHash` fields have
no safe ArchiveXL equivalent. Three scalar `actorMutations` entries target a
`worldFoliageNode`; translating them to partial deletions would be unsafe because
ArchiveXL 1.27.1 falls through to deleting the whole unsupported node type.
These 17 evidence records therefore remain visible for acknowledgement and an
author report rather than being hidden by a behavior-changing guess.

Two unknown fields are unambiguous spelling mistakes. Selectively extracted and
serialized the seven affected vanilla sectors with WolvenKit 8.19.0. Setup 815
in `exterior_-13_12_0_0` is the expected `worldStaticMeshNode`, and `sscale`
was corrected to `scale`. Setup 2353 in `exterior_-31_42_0_0` resolves to the
expected `worldCollisionNode` with 64 instances, and element 42's `rientation`
was corrected to `orientation`.

Created
`C:\Games\Programs\Mods\cyberpunk2077-mods\Immersive Night City Fixes - Combined Streaming Fixes-1.1.0.zip`.
It supersedes the former lantern-only package and differs from upstream INCF
0.31-HF by exactly three semantic lines: the lantern index 18,812 to 1,812 plus
the two spelling corrections. Scanner parsing produces both corrected mutation
references, reduces unknown mutation fields from nine to seven, and preserves
the 10 intentionally unresolved ignored operations. The ZIP contains only
`archive/pc/mod/INCF.xl` and has SHA-256
`DC71E52496BC13CB436F56560B0A7180E66F9FED482D18BB4AD60FD6D197D67F`.
The user disabled/replaced the older lantern-only package, deployed the combined
package as the sole winner, and rescanned. The result matched the prediction:
the two repairable unknown fields disappeared, the unsupported operations
remained without new unexpected errors, and the user acknowledged the residual
findings with their ArchiveXL limitation documented.

### 2026-08-05 — Cyberware-EX / VanillaPlus Parkour REDscript compatibility

Investigated the competing
`DoubleJumpDecisions.EnterCondition(ref<StateContext>,
ref<StateGameScriptInterface>)->Bool` replacements. VanillaPlus Parkour's
effective body already preserves Cyberware-EX's compatibility behavior: both
allow modded charge/hover cyberware to coexist with double jump. Parkour also
intentionally removes the fall-speed rejection. Its later replacement is
therefore a functional superset of the Cyberware-EX body, but REDscript still
reports the earlier annotation as overwritten.

Created the Vortex-ready package
`C:\Games\Programs\Mods\cyberpunk2077-mods\Cyberware-EX - VanillaPlus Parkour Compatibility-1.0.0.zip`.
It overrides only `r6/scripts/CyberwareEx/CyberwareEx.Global.reds` from
Cyberware-EX 1.5.6 and removes exactly the redundant 28-line replacement block;
all other Cyberware-EX code is preserved. VanillaPlus Parkour remains the sole
active replacement. This full-file override is version-specific and must be
removed or rebuilt when Cyberware-EX updates.

Simulated Vortex deployment with the upstream Cyberware-EX file overridden,
the compatibility copy deployed, and VanillaPlus Parkour deployed. The parser
found one active target reference, owned by VanillaPlus Parkour, with no target
finding and no REDscript conflicts. REDscript exact-path winners now inherit a
unique upstream logical owner when the winning file is a small edit (no more
than 64 changed lines and 10% of the source), while retaining the physical
compatibility package in provenance. This prevents full-file repair overlays
from appearing as unrelated mods. Bumped the scanner to v0.28.7 and added a
regression test. All 118 automated tests pass with warnings as errors. The ZIP
contains the one intended script and has SHA-256
`A72B8D965EA82FF607C36152A3A27D000CF3852FBD312139DB805D1979066039`.
The author packages and deployed game were not modified.

### 2026-08-05 — ArchiveXL exact-path winner and repair-lineage correction

After the user imported and correctly ordered the INCF lantern fix after the
upstream package, the report expanded from the normal range to 621 findings.
The user's diagnosis was correct: ArchiveXL analysis parsed both the Vortex-
overridden original `INCF.xl` and the deployed repair copy. This retained the
old index-18,812 error, duplicated all streaming operations as cross-package
conflicts, and attributed hundreds of upstream archive resources to the repair
package as implicit dependencies.

Updated ArchiveXL parsing to exclude artifacts marked `overridden` from active
semantic analysis. For a unique exact-path winner differing from its overridden
provider by at most 20 changed lines, the deployed file now inherits the
upstream provider as its logical ArchiveXL owner while retaining the repair
package and absolute path in reference provenance. This lets payload/resource
resolution use INCF's still-deployed companion archives and prevents a small
full-file repair from masquerading as a second independent mod.

Bumped the scanner to v0.28.6 and added a deployment regression using an
invalid overridden original plus a minimally corrected deployed winner. All
117 tests pass with warnings as errors. A complete scan of 280 mods and 3,637
files succeeded with 237 findings: one conflict, 21 warnings, 13 reviews, and
202 informational items. There are zero `AXL-NODE-DELETION-SHAPE`,
`AXL-CROSS-MOD-RESOURCE`, `AXL-NODE-MUTATION-DELETION-CONFLICT`, or
`AXL-NODE-MUTATION-WRITE-CONFLICT` findings. The physical lantern repair appears
only in the expected exact-path Vortex provenance item; the invalid `#18812`
identity is absent.

### 2026-08-05 — Immersive Night City Fixes lantern node repair

The user imported/deployed the TheNullifier GIM repair and confirmed its former
conflict/finding disappeared. Investigated the newly visible
`AXL-NODE-DELETION-SHAPE` in `INCF.xl` line 13,550 for
`exterior_-18_33_0_0.streamingsector`. The author block declares 2,510 expected
node setups but targets impossible index 18,812. Selective WolvenKit extraction
of the installed EP1 sector confirmed 2,510 setups. The documented
`japanese_lantern_a_center.mesh` target at the coordinates in INCF's comment is
a `worldStaticMeshNode` at setup index 1,812, establishing that the extra `8`
is a source typo rather than a removed target.

Created the Vortex-ready package
`C:\Games\Programs\Mods\cyberpunk2077-mods\Immersive Night City Fixes - Lantern Node Fix-1.0.0.zip`.
It overrides only `archive/pc/mod/INCF.xl` and differs from INCF 0.31-HF by one
line, changing index 18,812 to 1,812. Scanner parsing retains the valid deletion
at index 298, accepts the corrected deletion at 1,812 with the intended native
type, and emits no `AXL-NODE-DELETION-SHAPE`. The ZIP contains the one intended
file and has SHA-256
`978B213A96D6D1AC754A14C3E34204D3131F6F4A4CA46BD4277AC139AA9D6A3B`.
The author staging package was not edited. The user imported and deployed the
repair as the exact-path winner. Scanner v0.28.6 subsequently confirmed the
invalid deletion is gone after correcting overridden-provider semantics.

### 2026-08-05 — TheNullifier GIM node repair and ArchiveXL parser correction

Investigated the apparent `AXL-SECTOR-EXPECTED-NODES` conflict between
Immersive Night City Fixes and TheNullifier for
`exterior_-5_-5_0_3.streamingsector`. Neither mod replaces the sector in its
companion archive, and no deployed mod archive replaces it. The installed EP1
sector has 1,263 node setups. Immersive Night City Fixes correctly targets
setup index 251, a `worldStaticMeshNode`. TheNullifier's declaration had the
two significant numbers transposed: `expectedNodes: 1237` with out-of-range
index `1263`. The named `{q110_mall_front_door}_ProxyMesh` is actually setup
index 1,237 and has the declared `worldGenericProxyMeshNode` type.

Created the Vortex-ready package
`C:\Games\Programs\Mods\cyberpunk2077-mods\TheNullifier - GIM ArchiveXL Node Fix-1.0.0.zip`.
It overrides only `archive/pc/mod/TheNullifier-removals.xl`, preserves the full
author file, and changes exactly two lines: expected node count 1,237 to 1,263
and node index 1,263 to 1,237. Its SHA-256 is
`23543B160971251C567F9C525AB2D7649BAC8128177C72EA75F619D03220D3FC`.
Scanner validation with INCF reports matching expected counts and disjoint node
deletions, with no fix parse errors.

The scanner previously retained sector references even when ArchiveXL itself
discarded every invalid deletion in that sector. Updated the ArchiveXL parser
to reject invalid or out-of-range node deletion declarations, emit
`AXL-NODE-DELETION-SHAPE`, and omit empty sector declarations before cross-mod
comparison. Bumped the scanner to v0.28.5. All 116 tests pass with warnings as
errors, and a full scan of 279 mods and 3,636 files succeeded. The misleading
cross-mod conflict is gone and TheNullifier's invalid source line is now
reported directly. The same scan exposed one separate out-of-range deletion in
INCF at line 13,550; review it independently rather than folding it into this
package.

The user confirmed the Better Living Buffs unknown-property errors disappeared
after deploying its repair. Feature behavior remains deferred to the final
consolidated gameplay pass.

### 2026-08-05 — Better Living Buffs rejected-field repair

Diagnosed 12 `TXL-RUNTIME-UNKNOWN-PROPERTY` identities in Better Living Buffs.
One constant stat modifier contained invalid exporter residue `isActive: []`;
eleven `gamedataGameplayLogicPackageUIData_Record` definitions contained the
unrelated field `maxFactor: 0`. The current schemas do not expose those fields
on the declared record types, and TweakXL rejected them while accepting the
actual duration, localized UI, float, and integer values. Removing the rejected
fields therefore preserves the mod's current effective behavior.

Created the Vortex-ready package
`C:\Games\Programs\Mods\cyberpunk2077-mods\Better Living Buffs - Unknown Property Fix-1.0.0.zip`.
It contains the 12 affected YAML paths. Each override differs from its author
file by exactly one removed rejected line, for 12 removals and no additions.
All 12 documents parse with 49 references, no findings, and no residual
`isActive` or `maxFactor` assignments. The ZIP SHA-256 is
`4B90FCC4263246806089044DC8B27C94165A4D0D37168F2F78A3D45B15CB7EEA`.

The original staged package was not modified. The user later deployed the
repair, refreshed the runtime log, and confirmed all related errors disappeared.
Housing-buff duration and representative consumable/booster effects remain on
the consolidated gameplay checklist.

### 2026-08-05 — NCEE NPC invalid vendor-property repair

Diagnosed `TXL-RUNTIME-UNKNOWN-PROPERTY` on
`Vendors.maels_ripper.enabledPhotoModePuppet`. NCEE declares the target as a
`gamedataVendor_Record`, but the current game sources define
`enabledPhotoModePuppet` as a boolean-array field on the global photo-mode setup.
The assigned `Loot.TygerClawsShotgunBikerT3` value is instead an NPC loot-drop
record used by a Tyger Claws shotgunner. No other installed mod uses that field
on a vendor. TweakXL rejected the assignment, so removing it preserves the
current effective behavior rather than deleting an applied feature.

Created the Vortex-ready package
`C:\Games\Programs\Mods\cyberpunk2077-mods\NCEE NPC - Invalid Vendor Property Fix-1.0.0.zip`.
It contains only `r6/tweaks/NCEE NPC/ncee_characters.yaml`. Exact comparison
against the author file reports one removed line and no additions; the patched
document parses with 1,719 references and no findings, retains the
`Vendors.maels_ripper` type declaration, and no longer emits the invalid flat.
The ZIP SHA-256 is
`7DC80DD9052A7064CF034AF407B14AEA4C884E06A277047B9F137688065AE889`.

The original staged package and deployed game were not modified. The user later
deployed the fix, refreshed the runtime log, and confirmed the unknown-property
finding disappeared. Representative NCEE content and the Maelstrom ripper
interaction, if accessible, remain on the final consolidated gameplay checklist.

### 2026-08-05 — More Mods More Fun / weapon slots ambiguous-record repair

Diagnosed 20 `TXL-RUNTIME-AMBIGUOUS-DEFINITION` identities repeated while
TweakXL loaded More Mods More Fun, 6 More Weapon Mod Slots, and their dedicated
compatibility patch. The installed TweakDB confirms all 20 exact IDs are absent:
four `BladeMod2` tiers, three `BluntMod3`, two `ThrowMod2`, three `RangedMod1`,
one `PowerMod2`, three `SmartMod1`, and four `ShotgunMod2`. Their other existing
tiers remain valid. Each package attempted an array mutation against these
absent records, so TweakXL could not infer a record/value type. This is not a
load-order issue, and synthesizing the absent tiers would risk changing loot or
item behavior.

Created the Vortex-ready package
`C:\Games\Programs\Mods\cyberpunk2077-mods\More Mods More Fun - 6 More Weapon Mod Slots Ambiguous Record Fix-1.0.0.zip`.
It overrides the six affected melee/ranged YAML paths and removes only the
invalid `$instances` entries. Exact comparisons show 9 removals from each of
the three melee files and 11 removals from each of the three ranged files, with
no added or otherwise changed lines. Scanner parsing reports six documents,
18,520 references, no parse findings, 206 distinct mutation targets, and zero
missing targets against the installed game index.

The ZIP contains exactly the six intended YAML files and has SHA-256
`75B2163EE05FBE4395D17190A19AA3640DED968F627EB48D6C724B04FFCF72DB`.
The original staged packages and deployed game were not modified. Vortex
deployment and a fresh game-log rescan were subsequently completed by the user;
the 20 ambiguous-definition errors disappeared. Functional verification remains
deferred to the consolidated gameplay pass and will cover the combined behavior
of More Mods More Fun, 6 More Weapon Mod Slots, and their compatible patch on
representative melee and ranged weapons, including slot visibility, attachment
acceptance and persistence, and duplicate/empty/unusable slots.

The user also established an early Street Kid save at the populated starting
bar in central Night City as the standard runtime-log baseline. It exercises a
loaded save, streaming, crowds, NPCs, UI, and common systems without requiring
additional story progression. Feature-specific checks that need unavailable
items or later systems remain on the final accumulated checklist.

### 2026-08-05 — Attachments Crafting System base-case repair package

Created the Vortex-ready package
`C:\Games\Programs\Mods\cyberpunk2077-mods\Attachments Crafting System - Balanced Base Case Fix-1.0.0.zip`
for the Balanced Version's `Items.w_att_scope_sniper_02_legendary` base typo.
The obvious capitalization-only edit is unsafe because the generated record is
already `Items.w_att_scope_sniper_02_Legendary`, which would make it inherit
from itself. Instead, the patch removes that scope from the lowercase-clone
template and applies the same quality, modifier-group, and tag operations
directly to the official uppercase record.

Validation: the installed TweakDB index contains the uppercase record and not
the lowercase spelling; isolated TweakXL analysis reports no parse finding,
missing base, case mismatch, or inheritance cycle. The ZIP contains exactly
`r6/tweaks/Attachments Crafting System.yaml` and has SHA-256
`5886C4620D465C93B02E95140C5BCB009E2E7A251F4C9331A71255E84AF676F6`.
The original author package and deployed game were not modified. Vortex
deployment was subsequently completed by the user, and the next scan confirmed
that `TXL-BASE-CASE-MISMATCH` disappeared. Only an optional in-game sanity check
of the affected legendary sniper-scope crafting behavior remains. The user will
perform it during a consolidated validation pass after reviewing all report
findings, because advancing through the intro separately for each repair would
be counterproductive. Future repairs that need gameplay verification should be
added to the same final checklist.

### 2026-08-05 — Audioware MMDevAPI false missing-dependency correction

Diagnosed `NATIVE-DEPENDENCY-MISSING` after the Audioware update. The staged PE
imports `mmdevapi.dll`, Microsoft Windows' Core Audio system component; it is
not supposed to ship beside the plugin. Current RED4ext logs independently
confirm Audioware 1.9.9-rc.0 loads and initializes successfully, with no errors
or warnings in its plugin log. Added `mmdevapi.dll` to the scanner's system DLL
classification, extended the native dependency regression, documented the
classification, and bumped the scanner to `0.28.4`.

Validation: all 115 tests pass with warnings promoted to errors. A complete
scan of 275 mods and 3,616 files succeeded; the Audioware missing-dependency
finding moved to `resolved`. Native coverage reports Audioware loaded, deployed
bytes matching staging, 18 imports, and zero non-system imports. No downgrade,
downloaded DLL, or compatibility package is needed.

The user also reported the malformed Night City Skies schema to its author and
noted that a major Immersive First Person update supersedes the local shutdown
guard package. The historical ZIP remains available but should not be deployed
over the updated upstream mod.

### 2026-08-04 — Night City Skies repair runtime verification

The user redeployed `Night City Skies - Malformed Schema Fix-1.0.0`, launched
the game, loaded a save, and confirmed that the normal Night City Skies settings
panel remained available. The following scanner run no longer reported the
`CFG-PARSE-ERROR`, confirming that the neutral `{}` schema preserves the mod's
programmatic REDscript registration while safely replacing the malformed loose
schema file.

### 2026-08-04 — Overridden configuration diagnostics correction

The Night City Skies report showed that Vortex had correctly selected the
neutral schema fix, but `CFG-PARSE-ERROR` was still active because the shared
configuration parser emitted content diagnostics for every staged provider,
including providers marked `overridden`. Updated `shared_config.py` so
overridden documents remain parsed and inventoried for exact-path provenance
but cannot emit active parse, non-UTF-8, or duplicate-key diagnostics. Added a
regression using a malformed original plus valid deployed winner, documented
the behavior, and bumped the scanner to `0.28.3`.

Validation: all 115 tests pass with warnings promoted to errors. A complete
real-corpus scan also succeeded. That scan correctly saw the author file as
active because the user had intentionally removed the fix deployment before
the scan; the user will deploy the neutral package again for final confirmation.

### 2026-08-04 — Night City Skies neutral schema repair package

Created the Vortex-ready package
`C:\Games\Programs\Mods\cyberpunk2077-mods\Night City Skies - Malformed Schema Fix-1.0.0.zip`.
It contains only
`r6/storages/RedscriptConfigFramework/NightCitySkies.schema.json`, replaced by
the valid neutral object `{}`. This preserves the effective behavior of the
currently rejected author file, avoids duplicate `NightCitySkies` registration,
and does not expose inert `NCSSkywatch` controls.

Validation: the source parsed as JSON, the ZIP member path and three-byte
payload were inspected, and the package SHA-256 is
`190EB1855AAC70723CF16DB0F90F5BCBF9F150923C5433F07477E5866C0E975B`.
The upstream staging package and deployed game were not modified. Vortex
deployment, game launch, and scanner confirmation remain pending.

### 2026-08-04 — Night City Skies malformed schema diagnosis

Confirmed that `NightCitySkies.schema.json` is genuinely malformed: a complete
`NCSSkywatch` object is directly concatenated with a complete
`NightCitySkies` object at line 51. Redscript Config Framework documents one
`<modId>.schema.json` per mod and its installed loader calls `ReadAsJson()` once
per file, accepting one `JsonObject`; it does not support streamed roots.

The main `NightCitySkies` panel remains functional because `NCS_System.reds`
registers it programmatically and `NCS_Settings.reds` builds the same settings.
Deployed `NightCitySkies.json`, defaults, and cache files confirm that path is
active. No `NCSSkywatch` state file or code references to its keys exist, so the
first object is inactive and appears to be accidentally included content.
No author or deployed mod file was changed; remediation remains a user decision.

### 2026-08-04 — Complete command-line reference

Expanded `README.md` with every supported `scan` argument, accepted scope and
hash values, current YAML defaults, command-line precedence, relative-path
behavior, cache controls, help/version commands, and quick versus complete scan
examples. Documented that acknowledgements remain YAML-only and that the
non-archive analyzers currently run on every scan.

Validation: `git diff --check` passed; only the repository's existing line-ending
conversion warnings were emitted.

### 2026-08-04 — Immersive First Person shutdown guard and CET session bounds

Diagnosed the recurring `CET-RUNTIME-LUA-ERROR` in Immersive First Person.
`module.parsePath` successfully matches both literal mouse-sensitivity paths;
the nil receiver is `Game.GetSettingsSystem()` during the mod's `onShutdown`
callback after the game settings system has already been destroyed.

Created the independent Vortex-ready patch:

- `C:\Games\Programs\Mods\cyberpunk2077-mods\Immersive First Person - Settings Shutdown Guard-1.0.0.zip`
- SHA-256:
  `2DF375856F0B89607582FCF7389449BB3C4C19F41B7DBDF0BF2A839D109ECA8E`
- The ZIP contains only the patched
  `bin/x64/plugins/cyber_engine_tweaks/mods/ImmersiveFirstPerson/Modules/GameSettings.lua`.
- `GameSettings.Set` now validates the parsed path/name and settings-system
  handle before calling `GetVar`; normal in-session behavior is unchanged.

Scanner changes:

- CET runtime analysis now selects the latest appended `scripting.log` mod-load
  block and bounds framework plus canonical per-mod events to that session's
  timestamp.
- Mixed CET timestamps with and without explicit timezones are normalized to
  local wall-clock time before comparison.
- Added regression coverage proving errors from an older appended game session
  do not remain active after a clean later session.
- Updated documentation and bumped the scanner to 0.28.2.

Validation:

- All 114 tests pass with warnings promoted to errors.
- A complete real scan succeeded with 272 staged mods and 224 findings.
- CET coverage for the newest session contains one Lua error and one hook
  warning instead of historical totals; the Immersive First Person evidence now
  points to the latest `2026-08-04 20:30:18 UTC+03:00` occurrence.
- ArchiveXL's prior Cyberware localization error is absent from the newest
  runtime session, independently confirming that repair.
- Upstream mod packages and deployed game files were not modified by Codex.

### 2026-08-04 — Archive-based Cyberware EX fix and CR2W config exclusion

Replaced the incomplete loose-resource repair design with a corrected
Vortex-ready version 1.0.1 package and fixed the scanner false positives it
exposed.

Package:

- `C:\Games\Programs\Mods\cyberpunk2077-mods\Cyberware EX Keybinds - Localization Resource Fix-1.0.1.zip`
- SHA-256:
  `24AB5153809BAAF38DE0349BBE4B3A913B67C3EF873762C5C7289C67B414423E`
- The ZIP contains only
  `archive/pc/mod/cyberware-ex-keybinds-localization-resource-fix.archive`.
- The game archive indexes exactly
  `cyberware_ex_keybinds\localization\en-us.json` and `fr-fr.json`.
- Both cooked resources begin with CR2W magic and round-trip through WolvenKit
  with all 22 entries, keys, and localized texts preserved per language.

Scanner changes:

- `shared_config.py` now identifies CR2W binary magic before attempting text
  decoding and excludes cooked game resources from JSON/TOML/INI/XML config
  analysis.
- Added a regression test using a CR2W-magic `.json` file.
- Updated documentation and bumped the scanner to 0.28.1.

Validation:

- All 113 tests pass with warnings promoted to errors.
- A complete cached scan finished in 29.1 seconds with scanner 0.28.1.
- Neither loose cooked Cyberware localization file produces a configuration
  parse finding. The single remaining `CFG-PARSE-ERROR` belongs to the
  unrelated Night City Skies schema.
- The prior ArchiveXL runtime error correctly remains until the user disables
  repair 1.0.0, imports/deploys 1.0.1, launches the game, and rescans.
- No upstream staging package or deployed game file was modified by Codex.

### 2026-08-04 — Cyberware EX Keybinds localization repair package

Diagnosed `AXL-RUNTIME-LOCALIZATION-FAILED` for Cyberware EX Keybinds. Its
`en-us.json` and `fr-fr.json` files were valid WolvenKit serialized JSON text,
but had been shipped under the cooked single-extension filenames. ArchiveXL
resolved the declared paths and then rejected the text files because the game
resource loader requires binary CR2W resources.

Created the independent Vortex-ready package:

- `C:\Games\Programs\Mods\cyberpunk2077-mods\Cyberware EX Keybinds - Localization Resource Fix-1.0.0.zip`
- SHA-256:
  `DDF22169167AA4FA7B9A712BB5BB164C0FA0200399E231FBA15BDF7C2612D754`

The package contains only compiled replacements for:

- `archive/pc/mod/cyberware_ex_keybinds/localization/en-us.json`
- `archive/pc/mod/cyberware_ex_keybinds/localization/fr-fr.json`

Validation:

- Both compiled files begin with the `CR2W` resource signature.
- WolvenKit round-trip serialization preserved all 22 entries, secondary keys,
  and localized text in each language.
- The ZIP contains exactly the two intended resources under the proper Vortex
  deployment hierarchy.
- Upstream staging and deployed game files were not modified. The user will
  import the ZIP and make it the Vortex winner for the two paths.

Correction after deployment testing:

- Version 1.0.0 of this repair package is incomplete and must not be treated as
  the final fix. It deploys the cooked CR2W resources loose under
  `archive/pc/mod`; ArchiveXL's resource loader still cannot resolve them
  because the resources must be indexed inside a REDengine `.archive`.
- The scanner also incorrectly inventories the loose cooked `.json` resources
  as textual shared configuration, producing two false `CFG-PARSE-ERROR`
  findings. CR2W-magic `.json` files must be excluded from that analyzer.
- The visible Native Settings menu is not evidence that ArchiveXL localization
  succeeded. The mod's Lua source embeds English and French strings and falls
  back to them when `Game.GetLocalizedText` returns no usable translation.
- An isolated WolvenKit packing test produced an 8,192-byte archive whose
  indexed members exactly matched
  `cyberware_ex_keybinds\localization\en-us.json` and `fr-fr.json`. A revised
  package should contain that game archive rather than loose cooked files.

### 2026-08-04 — Journal HandleRefId resolution and collision fix

Fixed the fingerprint stop triggered by the newly installed Immersive Gigs
journals.

Changes:

- Indexed WolvenKit journal handle wrappers by `HandleId` before traversing the
  serialized graph.
- Resolved forward and repeated `HandleRefId` nodes to their shared journal
  objects while preserving each effective occurrence and source declaration.
- Added ancestor-path cycle detection so shared sibling references remain valid
  but true recursive graphs stop safely.
- Consolidated multiple structural issues in one journal resource into one
  finding with per-location evidence, preventing identical diagnostics from
  colliding even for genuinely malformed payloads.
- Added regression tests for forward/repeated references, missing targets, and
  cycles; updated documentation and scanner version 0.28.0.

Validation:

- All 112 tests pass with warnings promoted to errors.
- Real cached Regina and Wakako payloads resolve two and one handle-reference
  occurrences respectively, with zero shape findings.
- A complete updated-collection scan completed in 27.4 seconds: 271 mods, 3,597
  files, 79 indexed archives, 104 non-empty ArchiveXL configs, 214 non-empty
  TweakXL configs, 1,278 REDscript files, and 304 CET Lua files.
- All 12 journal payloads serialized successfully into 388 entry identities;
  no journal duplicate, conflict, review, or shape finding remains.
- The report contains 225 findings: 221 active and four acknowledged, with no
  stale acknowledgements. Relative to v0.27 it records 27 new, 18 changed, 17
  resolved, and 180 unchanged findings.
- Original mod packages and deployed game files were not modified.

### 2026-08-04 — Fingerprint collision diagnosed after collection update

The first scan after the user's mod changes stopped before report writing with
fingerprint `31e8fa680b32d441367c768a173d3a3bbb655826a9985f3c6606e6967d29b5be`.
The collision guard itself worked as designed; two identical current findings
would otherwise make acknowledgements and scan diffs ambiguous.

Both findings came from Immersive Gigs' serialized Regina journal. At
`contacts/regina_jones/sts_random`, two child handles contain `HandleRefId`
rather than inline `Data`. The journal analyzer does not yet resolve serialized
handle references, so it incorrectly emitted the same
`AXL-JOURNAL-PAYLOAD-SHAPE` empty-ID finding twice. This result did not establish
that the mod payload was invalid. The pre-scan report remained intact because
classification failed before report files were written. This defect was fixed
and validated in v0.28.0.

### 2026-08-03 — Collection moved into manual review

The user confirmed that manual finding review is starting and that the mod
collection is no longer frozen. The generated v0.27.0 report remains the last
verified frozen baseline, but future sessions must rediscover current staged and
deployed state before treating its findings as current. Codex remains
unauthorized to modify mods or deployment state unless the user returns with an
explicit change or compatibility-patch request. Prefer separately owned patches
when practical and run a fresh scan after changes.

The user subsequently made the patch policy explicit: existing author mods stay
read-only. Every local change must be packaged as a new, independently named,
minimal mod, imported through Vortex, and given deployment precedence over the
original provider. Separate fixes should normally remain separate small mods so
local work, author updates, and Vortex winners remain unambiguous.

### 2026-08-03 — CET TweakDB-to-TweakXL cross-ecosystem analysis

Completed the remaining concrete cross-ecosystem effect pass before manual
finding review.

Changes:

- Extended the CET lexer-based analyzer to extract source-lined literal
  `TweakDB:SetFlat`, `SetFlatNoUpdate`, `CloneRecord`, `CreateRecord`, and
  `DeleteRecord` calls without executing Lua.
- Added static decoding for scalar values, simple array tables, and common
  `TweakDBID`/`CName` constructors; computed targets and values remain explicit
  partial coverage.
- Compared active CET flat and record mutations with concrete TweakXL
  assignments, tagged arrays, `$base`, `$type`, and record descendants.
- Classified equivalent values, different runtime overwrites, whole-array
  replacement, dynamic values, record overlaps/deletions, and same-package
  integration with dedicated `XEC-CET-TWEAKDB-*` rules.
- Added CET and cross-ecosystem coverage metrics to HTML/Markdown, tests,
  documentation, and scanner version 0.27.0.

Validation:

- All 110 tests pass with warnings promoted to errors.
- A complete frozen-corpus scan completed in 28 seconds and regenerated the
  v0.27.0 reports.
- The scan extracted 363 active literal CET flat writes, seven record writes,
  and 15 active computed-target TweakDB calls. It found 22 exact CET/TweakXL
  flat targets: 21 same-package integrations and one cross-package overlap.
- The new warning shows Clothing Improved writing
  `Items.IntrinsicFabricEnhancer10_inline2.value = -0.01` at runtime over Quickhack
  Fixes' TweakXL assignment of `1`, with both exact source paths and lines.
- Reports now contain 212 active and four acknowledged findings. The first
  validation scan identified one new finding; the final stability scan records
  all 216 unchanged, with no stale acknowledgements.
- Frozen Vortex and game inputs were not modified.

### 2026-08-03 — Clickable source folders in HTML evidence

Made source evidence easier to navigate from the offline report.

Changes:

- Replaced the lazy evidence block's plain JSON insertion with a safe DOM
  renderer that preserves all JSON formatting and values.
- Absolute `source_path` string tokens now display the same complete escaped
  file path as before while linking to the file's parent directory.
- Added `file:///` drive-path and UNC-folder generation with per-segment URL
  encoding for spaces and special characters.
- Added dedicated link styling without using HTML string interpolation, so
  evidence remains protected from markup injection.
- Updated documentation and scanner version 0.26.0.

Validation:

- All 106 tests pass with warnings promoted to errors.
- A complete frozen-corpus scan completed in 28.4 seconds and regenerated the
  v0.26.0 reports.
- Generated HTML contains the lazy source-link renderer, drive/UNC URL paths,
  and unchanged embedded evidence.
- Current state is 211 active and four acknowledged findings, no stale
  acknowledgements, and all 215 findings unchanged from the preceding scan.
- Frozen Vortex and game inputs were not modified.

### 2026-08-03 — CET-to-REDscript cross-ecosystem method analysis

Added the first operation-aware cross-ecosystem compatibility pass.

Changes:

- Added `cross_ecosystem.py` to compare active literal CET observers and
  overrides with active REDscript wrappers and replacements by class/method.
- Added NativeDB full-signature matching when supplied, medium-confidence
  short-name matching for overload-ambiguous hooks, and explicit counts for
  dynamic targets that are not guessed.
- Classified additive observers, visibly wrapped CET override chains, unknown
  chains, and visibly terminating overrides with distinct rule IDs and
  severities. Same-package dual-language components are counted without
  creating findings.
- Added Cross-ecosystem coverage/filter support, a summary card, Markdown
  coverage, and `cross-ecosystem-findings.json` with both source references.
- Updated README/TODO documentation and scanner version 0.25.0.

Validation:

- All 106 tests pass with warnings promoted to errors.
- A complete frozen-corpus scan completed in 28.4 seconds.
- The pass compared 518 active literal CET hook targets with 678 active
  REDscript method targets. It matched 33 shared cross-package targets:
  30 have additive observers and three have wrapped CET override chains.
- The 33 targets produced 30 consolidated informational findings, with no
  uncertain or terminating cross-ecosystem override in the current corpus.
- The report contains 211 active and four acknowledged findings, with no stale
  acknowledgements. The scan diff records the 30 new cross-ecosystem findings
  and all 185 prior findings unchanged.
- HTML structure, cross-ecosystem filter mapping, coverage card data, and
  dedicated JSON output were verified. Local headless browser processes could
  not render under their isolated sandbox; all temporary QA files were removed.
- Frozen Vortex and game inputs were not modified.

### 2026-08-03 — Responsive coverage and browser acknowledgement editor

Improved dense coverage presentation and made acknowledgement maintenance
interactive without granting the report silent filesystem access.

Changes:

- Widened the report shell to 1,740 pixels while retaining narrow-screen
  margins and responsive toolbar behavior.
- Replaced the dense CET registration and per-framework runtime rows with
  responsive metric cards. Long log paths and notes now receive full-width
  fields instead of compressing neighboring columns.
- Moved acknowledgements out of `cp77compat.yaml` into the strict, versioned
  `acknowledgements.yaml` file referenced through `paths.acknowledgements`.
- Added an acknowledgement checkbox and editable note to every expanded
  finding. Changes update status filters and summary counts immediately.
- Added Save acknowledgements using Chromium's explicit file picker, with a
  YAML download fallback when direct user-approved writing is unavailable.
- Updated documentation and scanner version 0.24.0.

Validation:

- All 102 tests pass with warnings promoted to errors.
- The project configuration resolves the separate acknowledgement file and
  strictly loads all four known Vortex winner entries.
- A complete frozen-corpus scan completed in about 28 seconds and regenerated
  the v0.24.0 reports with 181 active findings, four acknowledged findings,
  no stale acknowledgements, and all 185 findings unchanged.
- A 1920x1200 headless Edge render confirmed the wider coverage layout; the
  two dense analyzer rows render as seven responsive cards and the temporary
  screenshot was removed afterward.
- Frozen Vortex and game inputs were not modified.

### 2026-08-03 — Finding acknowledgements, report diffs, and HTML fixes

Added persistent finding state management and corrected two report UI defects.

Changes:

- Prevented analyzer coverage tables from exceeding their panel by allowing
  grid/table wrappers to shrink and scroll within the available width.
- Corrected Clear so it resets Ecosystem together with every other finding
  filter, and made the expanded toolbar responsive.
- Added stable SHA-256 finding fingerprints and strict YAML acknowledgements.
  Acknowledgements preserve evidence and become stale if their fingerprint no
  longer matches a current finding.
- Recorded the four exact-path findings covered by the established Damage
  Scaling Extended and Classic Drinks Vortex winner decisions.
- Added active/acknowledged/stale and baseline/new/changed/unchanged HTML
  filtering, visible state/fingerprint details, URL-hash filter persistence,
  and state summary cards.
- Added `compatibility-diff.json`, comparing each scan with the preceding
  combined report while ignoring irrelevant evidence ordering.
- Updated README/configuration documentation and scanner version 0.23.0.

Validation:

- All 102 tests pass with warnings promoted to errors.
- Two consecutive frozen-corpus scans completed in about 28 seconds each.
- The current state is 181 active findings, four acknowledged findings, and no
  stale acknowledgements. All 185 findings are unchanged from the prior scan;
  no entry is new, changed, or resolved.
- A 1600x1200 headless Edge render confirmed the responsive toolbar and report
  layout; the temporary screenshot was removed afterward.
- Frozen Vortex and game inputs were not modified.

### 2026-08-03 — RED4ext and native-framework analyzer

Implemented read-only native binary, dependency, deployment, and runtime
validation.

Changes:

- Added `native.py` with DLL/ASI classification, SHA-256 deployment comparison,
  Windows fixed-version extraction, and direct PE normal/delay import parsing.
- Added exact-path provider duplicate/override rules, unresolved hard-import
  checks, missing/mismatched deployment checks, and PE parse diagnostics.
- Correlated RED4ext loader paths with staged binaries and runtime plugin
  name/version/author metadata; distinguished imported companion DLLs from
  plugin entrypoints.
- Compared RED4ext and CET game executable versions and consolidated structured
  RED4ext/Codeware/other plugin diagnostics. ArchiveXL, TweakXL, and Input
  Loader logs remain delegated to their dedicated analyzers.
- Added `native-findings.json`, Native frameworks HTML filtering/statistics,
  four native coverage tables, README documentation, and scanner version
  0.22.0.

Validation:

- All 97 tests pass with warnings promoted to errors, including synthetic PE
  imports, missing dependencies, runtime plugin/companion correlation, and
  competing native providers.
- The frozen corpus has 19 active native files and 251 native references from
  19 binary records plus 232 hard imports. All deployed hashes match.
- RED4ext 1.30.0 confirms 13 loaded plugin entrypoints on game product 2.31 /
  executable 3.0.80.51928. RadioExt's `fmod.dll` is correctly recognized as its
  one resolved companion library. CET 1.37.1 reports the same executable.
- No missing hard imports, shared native paths, deployment mismatches, PE parse
  failures, plugin-load failures, version disagreements, or non-delegated log
  diagnostics were found.
- The full cached scan completed in about 27 seconds. The combined report
  remains at 185 findings: 2 conflicts, 11 errors, 18 warnings, 13 reviews, and
  141 info; the native analyzer added no finding to the healthy current state.
- Frozen Vortex and game inputs were not modified.

### 2026-08-03 — Input Loader XML semantic analyzer

Implemented mapping/context compatibility analysis using Input Loader's actual
merge behavior and current generated state.

Changes:

- Added `input_mapping.py` with Expat-based structural parsing and exact source
  lines for top-level nodes and their direct children.
- Modeled Input Loader's `(tag, name)` whole-node replacement and
  `append="true"` child-copy behavior from the installed plugin/source model.
- Added cross-mod whole-node overwrite, identical duplicate, composable append,
  appended-child conflict, and action-policy conflict rules.
- Resolved action `map`, context `include`, and timing/event action targets
  against the effective generated input files.
- Compared active fragments to vanilla input definitions and to both generated
  cache files, and correlated the current `input_loader.log` session.
- Added `input-findings.json`, Input mapping HTML filtering/statistics, Input
  Loader coverage tables, README documentation, and scanner version 0.21.0.

Validation:

- All 94 tests pass with warnings promoted to errors.
- The frozen corpus contains seven active input fragments and 449 source-lined
  references across 189 top-level nodes: 72 mappings, 101 contexts, 15
  timing/event policies, and one button group.
- Twenty-one cross-mod top-level targets use compatible append semantics. No
  competing whole-node providers, incompatible appended children, or missing
  mapping/context/action targets were found.
- Every active node/child matches the generated `inputContexts.xml` and
  `inputUserMappings.xml`; the startup log loaded all seven fragments with no
  errors or warnings.
- Dodge Dash Sprint with Shift intentionally replaces the base-game
  `Dodge_Button`. Its `ToggleSprint_Button` definition is semantically identical
  to vanilla and produces no behavioral overwrite finding.
- The full cached scan completed in 27.7 seconds. The combined report contains
  185 findings: 2 conflicts, 11 errors, 18 warnings, 13 reviews, and 141 info.
- Frozen Vortex and game inputs were not modified.

### 2026-08-03 — Shared configuration ownership and validation

Added format-aware inventory and exact-path comparison for staged JSON, TOML,
INI, and XML configuration files.

Changes:

- Added `shared_config.py` with strict parsers, CP-1252 fallback tracking,
  duplicate JSON key detection, semantic fingerprints, and one-based parser
  error lines.
- Attributed exact deployment paths and broader CET root, engine config,
  REDscript user-hint, and input configuration scopes to Vortex packages.
- Compared same-path providers semantically so formatting/key order do not make
  equivalent JSON/TOML documents look different.
- Added parse/encoding/duplicate-key, exact-path duplicate/override, and
  informational multi-package-scope rules.
- Added `config-findings.json`, configuration HTML filtering/statistics,
  format/ownership coverage tables, documentation, and scanner version 0.20.0.

Validation:

- All 91 tests pass with warnings promoted to errors.
- The frozen corpus contains 161 active documents: 138 JSON, 9 TOML, 4 INI,
  and 10 XML, with 75,392 normalized leaf/element entries.
- All TOML, INI, and XML files parse. JSON parses 137 of 138 files; no duplicate
  JSON key was found.
- Night City Skies `NightCitySkies.schema.json` begins a second top-level JSON
  object at line 51. The installed Redscript Config Framework calls
  `ReadAsJson()` once per schema file, so the concatenated document is invalid.
- Missing Persons `languages\es-es.json` is valid only under CP-1252 because it
  contains byte `0x96`; this is retained as a compatibility warning.
- Twenty-two ownership scopes were found. Four are multi-package and
  informational: `cet:WeatherSwitcher`, `engine-config`, `r6-input`, and
  `redscript-user-hints`. No exact configuration path has multiple providers.
- The full cached scan completed in 27.2 seconds. The combined report contains
  183 findings: 2 conflicts, 11 errors, 18 warnings, 13 reviews, and 139 info.
- Frozen Vortex and game inputs were not modified.

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
