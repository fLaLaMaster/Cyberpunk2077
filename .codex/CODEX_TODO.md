# Codex TODO

Last reviewed: 2026-08-02

This list describes planned scanner work. Reorder it when user priorities
change. Check an item only after implementation, relevant tests, and a real
frozen-corpus validation pass are complete.

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

- [x] Inspect serialized localization resources and detect duplicate
  `secondaryKey` definitions across mods.
- [x] Detect competing edits to the same localization `primaryKey`.
- [x] Inspect serialized factory CSV resources and compare factory entity names
  and target `.ent`/`.app` paths.
- [x] Verify factory target resources exist in the declaring mod or document an
  implicit cross-mod dependency.
- [x] Parse and analyze `quest.phases` operations and parent targets.
- [x] Parse and analyze `journal` resources.
- [ ] Parse and analyze `overrides` operations.
- [x] Parse `resource.patch`, `copy`, `link`, `scope`, and `fix`, preserving
  custom tags and source lines.
- [x] Compare resource patch targets, copy/link destinations, scope members,
  and fix rewrites across mods.
- [x] Inspect identities inside serialized resource patch payloads when two or
  more mods patch the same target.
- [ ] Add `customizations` identity and slot/group collision checks.
- [ ] Determine whether duplicate streaming node deletions are always unsafe,
  idempotent, or rule-dependent; adjust confidence/severity accordingly.
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

- [ ] Implement class-and-method-aware extraction for `@wrapMethod`,
  `@replaceMethod`, `@addMethod`, and `@addField`.
- [ ] Pair annotations with full method signatures rather than only class names.
- [ ] Flag multiple replacements of the same method.
- [ ] Detect duplicate added symbols and fields.
- [ ] Review wrappers that do not invoke `wrappedMethod` where invocation is
  expected.
- [ ] Correlate findings with `redscript_rCURRENT.log` compiler errors.

## CET Lua and shared configuration

- [ ] Detect CET mods sharing the same deployed mod directory or entry file.
- [ ] Extract registered event, hotkey, input, and settings identifiers.
- [ ] Detect likely global/module namespace collisions.
- [ ] Inventory shared JSON, TOML, INI, and XML ownership.
- [ ] Parse input mapping IDs and identify duplicate or overwritten mappings.
- [ ] Correlate CET findings with the CET runtime log.

## RED4ext and framework validation

- [ ] Inventory native plugin versions and declared dependencies.
- [ ] Compare bundled framework binaries across staging mods and deployed
  winners.
- [ ] Add game-version/framework-version compatibility rules from authoritative
  local metadata or official sources.
- [ ] Parse RED4ext, ArchiveXL, TweakXL, Codeware, and other framework logs.
- [ ] Report missing DLL dependencies and native plugin load failures.

## Reporting and performance

- [x] Add analyzer-coverage tables for installed ArchiveXL sections and
  resource operations, including analyzed/partial/unsupported status.
- [x] Attach structural source lines to all current ArchiveXL and TweakXL
  references instead of relying on synthesized-identity text searches.
- [ ] Add URL/hash-backed HTML filter state so a filtered finding view can be
  bookmarked or shared.
- [ ] Add export of the currently filtered HTML findings to JSON/CSV.
- [ ] Add optional finding suppression/acknowledgement configuration without
  changing source mods.
- [ ] Add scan-to-scan diff reporting for new, resolved, and changed findings.
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
