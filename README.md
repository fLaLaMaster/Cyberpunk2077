# CP77 Compatibility Scanner

Read-only compatibility analysis for a Vortex-managed Cyberpunk 2077 mod
collection. The scanner reads the Vortex staging directory, deployed game
directory, and `vortex.deployment.json`. It writes only to its report and cache
directories.

Implemented analysis includes:

- per-mod file inventory and Vortex deployment attribution;
- exact relative-path collision reporting;
- ArchiveXL YAML/JSON parsing;
- WolvenKit CLI archive member indexing plus exact, cache-backed selective
  payload extraction;
- ArchiveXL reference resolution and streaming overlap checks;
- ArchiveXL `resource.patch`, `copy`, `link`, `scope`, and `fix` declaration
  analysis;
- ArchiveXL on-screen localization payload serialization and locale-scoped
  `secondaryKey`/`primaryKey` collision analysis;
- ArchiveXL factory CSV serialization, entity-name collision checks, and
  factory target resource validation;
- ArchiveXL shared-target resource patch serialization and comparison of stable
  inner identities for the installed `.mesh`, `.ent`, and `.devices` overlaps;
- ArchiveXL `quest.phases` parsing with structural source lines, child/parent
  resource resolution, attachment-point comparison, and compact missing-target
  findings;
- ArchiveXL journal resource resolution and payload-tree comparison using
  case-sensitive entry paths, recursive container semantics, and `*` property
  edit markers;
- ArchiveXL `overrides.tags` parsing for hide/show chunk lists, shorthand hide
  lists, and raw masks, with whole-tag last-wins collision checks;
- ArchiveXL character-customization payload inspection with case-sensitive
  group, named-option, anonymous slot/link selector, native-type, and
  type-specific choice comparison;
- newest-session ArchiveXL runtime parsing across rotated log chunks, with
  localization, quest-phase, and streaming-sector source attribution plus
  static quest-target confirmation;
- TweakXL `.yaml`/`.yml` parsing under `r6/tweaks`;
- TweakDB record, flat, property, `$base`, `$type`, and `$instances` extraction;
- semantic comparison of complete assignments and tagged array operations;
- `$base` validation against installed definitions, official REDmod `.tweak`
  sources, and generated inline record IDs in the local TweakDB binaries;
- TweakXL base-chain cycle, case-mismatch, missing-record, and compact
  cross-mod custom-record dependency analysis;
- newest-log TweakXL runtime error/warning parsing, source-file attribution,
  static-finding confirmation, and compact event consolidation;
- deterministic JSON and Markdown reports.

Reports include an analyzer-coverage panel that distinguishes analyzed,
partially analyzed, and unsupported installed sections. Resource operations are
compared at declaration-identity level. Localization and factory payload entries
are inspected, and patch sources sharing targets are compared by stable inner
identities. Unshared patch payload contents remain outside the selective scope.
Quest phase analysis treats multiple mods attaching different children to the
same parent as normal composition. It reports only duplicated child/parent
merges or competing attachment points, and resolves custom child and parent
resources against indexed mod archives and loose files.
Journal analysis selectively serializes declared `.journal` resources and
compares the effective entry paths used by ArchiveXL itself. Shared containers
are composable; incompatible leaf definitions, competing edits, and mixed
edit/merge operations receive distinct findings.
Visual-tag override analysis compares effective 64-bit component masks. Tag
names are case-sensitive, and a later same-name tag replaces the entire earlier
definition. Identical definitions are informational duplicates; different
definitions are load-order conflicts even when their component lists are
disjoint.

Character-customization analysis follows ArchiveXL's two-pass merge model:
named options merge first, then anonymous `uiSlot`/`link` selectors. Compatible
shared options with distinct choices are normal composition. A native-type
mismatch is a conflict, while a repeated appearance, morph, or switcher choice
with different content is a load-order replacement conflict. Wildcard slot
selectors are checked using the same directional prefix rule as ArchiveXL.

The TweakXL parser preserves YAML anchors, aliases, repeated template roots,
and the `!append`, `!append-once`, `!append-from`, `!prepend`,
`!prepend-once`, `!prepend-from`, and `!remove` operations. It expands
`$instances` before comparing concrete TweakDB identities. Findings distinguish
incompatible complete assignments, assignment-versus-mutation load-order risks,
add/remove opposition, non-unique duplicate additions, and safely composable
cross-mod array operations. Parser node locations are retained through aliases
and template expansion so report evidence points to the originating source line.
Dependency checks resolve explicit `t"..."`/`TweakDBID("...")` foreign keys and
implicit values that exactly match an installed custom record provider. Other
implicit scalar values are intentionally left unclassified until property type
metadata is available.

Each scan also reads the newest timestamped TweakXL log below the configured
game directory. Runtime errors emitted while a file is being read are mapped
back to its Vortex staging artifact and source line where possible. Later
hash-only validation warnings are correlated through their owning TweakDB flat.
The runtime log remains a read-only input and repeated events are consolidated
without discarding their individual log evidence.

ArchiveXL logs are session-aware: the scanner selects the newest timestamp and
reads its numbered rotation chunks before the continuing unnumbered log. Paired
messages such as a node-count error followed by “no patches applied” remain one
actionable finding while both physical log lines are preserved as evidence.

## Run

From this directory:

```powershell
.\run-scanner.cmd `
  --staging "C:\Games\Programs\Vortex Mods\cyberpunk2077" `
  --game "C:\Games\Steam\steamapps\common\Cyberpunk 2077" `
  --wolvenkit "C:\Games\Programs\WolvenKit-Console\WolvenKit.CLI.exe"
```

Those paths are also the defaults for this workspace, so a normal scan can be
started with just:

```powershell
.\run-scanner.cmd
```

## Configuration

The tracked `cp77compat.yaml` file stores workspace paths and normal scan
settings:

```yaml
version: 1

paths:
  staging: 'C:\Games\Programs\Vortex Mods\cyberpunk2077'
  game: 'C:\Games\Steam\steamapps\common\Cyberpunk 2077'
  wolvenkit: 'C:\Games\Programs\WolvenKit-Console\WolvenKit.CLI.exe'
  output: 'reports\current'
  cache: '.cache\archives'

scan:
  archive_scope: xl
  payload_scope: all
  hash_mode: archives
  workers: 4
  refresh_cache: false
  wolvenkit_timeout_seconds: 120
```

Relative paths are resolved from the YAML file's directory. Command-line
options override YAML values, so temporary changes do not require editing the
configuration. A different file can be selected with `--config <path>`.

The loader rejects duplicate keys, unknown settings, unsupported schema
versions, invalid choices, and non-positive worker/timeout values.

Archive modes:

- `--archive-scope xl` indexes archives belonging to mods with `.xl` files
  (default).
- `--archive-scope all` indexes every mod archive.
- `--archive-scope none` skips WolvenKit execution.
- `--no-refresh-cache` overrides a YAML `refresh_cache: true` value.
- `--payload-scope all` inspects every implemented ArchiveXL payload type
  (default).
- `--payload-scope customizations`, `--payload-scope localization`,
  `--payload-scope factories`, `--payload-scope journals`, or
  `--payload-scope patches` limits inspection to that payload type.
- `--payload-scope none` keeps the scan declaration-only and does not
  materialize payloads.

Use `--refresh-cache` to rebuild WolvenKit archive manifests and payload caches.
Every payload is written only beneath
`.cache/archives/<archive-sha256>/extracted`; metadata records the exact command,
tool version, source hash, resource hash, result, timing, size, and payload hash.
CR2W JSON serialization is cached separately for fast repeat scans.

Customization inspection selectively serializes declared male/female
`.inkcharcustomization` resources. It compares case-sensitive group entries,
named options, anonymous `uiSlot`/`link` selectors, native option types, and the
type-specific choice identities used by ArchiveXL. Distinct choices on a
compatible shared option are reported as composable; repeated choices with
different payloads are load-order conflicts.

## Reports

- `reports/current/inventory.json`: mods, files, hashes, and deployment state.
- `reports/current/archive-manifests.json`: WolvenKit archive member indexes.
- `reports/current/archivexl-findings.json`: complete references and evidence.
- `reports/current/tweakxl-findings.json`: TweakXL references and findings.
- `reports/current/compatibility-findings.json`: combined machine-readable findings.
- `reports/current/compatibility-report.html`: searchable, filterable offline report.
- `reports/current/compatibility-report.md`: concise human-readable report.

The HTML report supports free-text search, severity/rule/mod filters, pagination,
and expandable evidence. It is self-contained and does not require a web server.
