# Codex TODO

Last reviewed: 2026-08-02

This list describes planned scanner work. Reorder it when user priorities
change. Check an item only after implementation, relevant tests, and a real
frozen-corpus validation pass are complete.

## Next milestone: selective ArchiveXL payload inspection

- [ ] Add an archive-provider interface separating member indexing from payload
  materialization.
- [ ] Add exact, selective extraction into
  `.cache/archives/<archive-sha256>/extracted` using WolvenKit filters.
- [ ] Verify every resolved extraction path remains inside the scanner-owned
  cache.
- [ ] Add WolvenKit CR2W serialization to JSON, preferably capturing
  `convert serialize --print` output without writing a second permanent copy.
- [ ] Record WolvenKit command, version, source archive hash, resource path,
  timeout, and conversion result in cache metadata.
- [ ] Add cache invalidation and failure findings for partial or corrupt cached
  payloads.
- [ ] Add small synthetic archive/extraction fixtures where practical; never
  write into the frozen staging or game directories.

## ArchiveXL semantic coverage

- [ ] Inspect serialized localization resources and detect duplicate
  `secondaryKey` definitions across mods.
- [ ] Detect competing edits to the same localization `primaryKey`.
- [ ] Inspect serialized factory CSV resources and compare factory entity names
  and target `.ent`/`.app` paths.
- [ ] Verify factory target resources exist in the declaring mod or document an
  implicit cross-mod dependency.
- [ ] Parse and analyze `quest.phases` operations and parent targets.
- [ ] Parse and analyze `journal` resources.
- [ ] Parse and analyze `overrides` operations.
- [ ] Add deeper `resource.fix`, `resource.scope`, and related identity-level
  checks.
- [ ] Add `customizations` identity and slot/group collision checks.
- [ ] Determine whether duplicate streaming node deletions are always unsafe,
  idempotent, or rule-dependent; adjust confidence/severity accordingly.
- [ ] Correlate ArchiveXL static findings with ArchiveXL/RED4ext runtime logs
  after the user produces a fresh modded-game launch log.

## TweakXL analyzer

- [ ] Reuse the YAML loader while preserving TweakXL-specific tags and
  operations such as append/prepend/remove.
- [ ] Extract record and flat identities.
- [ ] Distinguish additive operations from destructive assignments.
- [ ] Detect multiple mods assigning incompatible values to the same record
  property.
- [ ] Detect missing bases, clones, or referenced records where feasible.
- [ ] Parse and correlate TweakXL runtime logs.

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

- [ ] Locate or configure a usable Git executable for status/diff checks in the
  execution environment.
- [ ] Add a license if the user chooses one.
- [ ] Add contributor/development documentation when the analyzer API stabilizes.
- [ ] Add CI for Python tests after GitHub Actions requirements are decided.
- [ ] Decide whether generated example reports should remain ignored or whether
  a small sanitized sample report belongs in the repository.

