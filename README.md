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
- ArchiveXL reference resolution and streaming overlap checks, including
  ArchiveXL-aware classification of full-node, partial-element, and collision
  shape deletions;
- ArchiveXL node and actor/instance mutation parsing with effective transform,
  resource, appearance, record, and proxy-property comparison;
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
- ArchiveXL `player.bodyTypes` parsing with exact body-type and `Body:<name>`
  tag identities, scalar/list validation, and idempotent duplicate detection;
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
- REDscript `@wrapMethod`, `@replaceMethod`, `@addMethod`, and `@addField`
  parsing with exact class plus parameter/return-type signatures;
- REDscript replacement, added-symbol, and wrapper-chain compatibility checks,
  including installed `@if(ModuleExists(...))` evaluation;
- `redscript_rCURRENT.log` compiler diagnostic attribution and correlation with
  exact static annotation overlaps;
- CET Lua root/entrypoint discovery, literal `require` and `GetMod` dependency
  resolution, lifecycle event and binding validation, observer/override-chain
  comparison, Native Settings path analysis, and source-lined literal TweakDB
  flat/record mutations;
- current CET framework, scripting, and per-mod log parsing with load-state,
  missing-hook, registration, module, and Lua error attribution;
- cross-ecosystem CET hook versus REDscript method comparison, including
  additive observers, wrapped override chains, uncertain callbacks, terminating
  overrides, full NativeDB signatures, and overload-ambiguous short names;
- cross-ecosystem CET runtime TweakDB writes versus concrete TweakXL flat,
  array, and record operations, with equivalent, destructive, dynamic-value,
  same-package, and cross-package classifications;
- JSON, TOML, INI, and XML ownership inventory with strict structural parsing,
  encoding/duplicate-key diagnostics, semantic fingerprints, exact-path
  provider comparison, and shared CET/framework scope attribution;
- Input Loader XML analysis with structural source lines, exact whole-node
  replacement versus child-append semantics, nested action identity checks,
  mapping/context/action target resolution, vanilla override detection,
  generated-cache validation, and startup-log correlation;
- RED4ext/native binary inventory with byte-level deployment verification,
  Windows file versions, PE normal/delay import resolution, plugin load-state
  correlation, framework/game version comparison, and plugin-log diagnostics;
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
WolvenKit's serialized journal graph is indexed by `HandleId`, so forward and
repeated `HandleRefId` entries resolve to their shared objects before effective
paths are reconstructed. Missing references and true ancestor cycles remain
structural errors and are consolidated per resource with graph-location
evidence.
Visual-tag override analysis compares effective 64-bit component masks. Tag
names are case-sensitive, and a later same-name tag replaces the entire earlier
definition. Identical definitions are informational duplicates; different
definitions are load-order conflicts even when their component lists are
disjoint.

Player body-type analysis follows ArchiveXL's PuppetState configuration and
accepts either one scalar name or a list of scalar names. Each name registers a
case-sensitive body type and matching `Body:<name>` tag. Distinct names compose
in ArchiveXL's global containers; an exact registration repeated by multiple
mods is reported as informational and idempotent.

Character-customization analysis follows ArchiveXL's two-pass merge model:
named options merge first, then anonymous `uiSlot`/`link` selectors. Compatible
shared options with distinct choices are normal composition. A native-type
mismatch is a conflict, while a repeated appearance, morph, or switcher choice
with different content is a load-order replacement conflict. Wildcard slot
selectors are checked using the same directional prefix rule as ArchiveXL.

Streaming node deletions are compared at sector/node level while retaining
native type, full-versus-partial scope, expected actor/instance counts, and
individual actor/instance/shape indices. Repeated full-node deletion is
informational because ArchiveXL hides nodes in place and keeps indices stable.
Compatible partial element deletions compose. Type/count disagreements and
multiple collision-shape patches remain conflicts; the latter exercise a
non-idempotent shared collision-preset override path in ArchiveXL.

Streaming node mutations are compared at effective node-property and
actor/instance-property level. Identical writes are idempotent, disjoint writes
compose, and differing values on the same property are load-order conflicts.
The analyzer also models ArchiveXL's special destructible-instance transform
replacement, positive-only proxy-node deltas, mutation/deletion interactions,
and node type plus actor/instance count guards. Shared sectors whose mods touch
only distinct node indices are reported as high-confidence composition instead
of requiring manual review. Fields or operations silently ignored by the
installed ArchiveXL implementation are surfaced as warnings.

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

REDscript analysis uses source-preserving lexical parsing rather than matching
method names alone. Parameter names and visibility do not affect annotation
target resolution, while parameter types and return type do. Legacy callback
annotations declared as returning `Void` are normalized to the compiler's
`Bool` fallback. Array shorthand and expression-bodied functions are also
normalized before comparison. Installed module declarations are used to exclude
inactive `@if(ModuleExists(...))` branches, and Vortex-overridden scripts remain
in the reference inventory but are excluded from effective collision checks.

Multiple wrappers of one signature are compatible when each calls
`wrappedMethod`; a wrapper that skips it is a review finding because it
terminates the chain. Different replacements of one exact signature are a
conflict because only the last remains active. Identical replacements are a
compiler-confirmed warning with equivalent final behavior. Duplicate added
methods and fields are checked independently, and the current compiler log is
used to confirm which static overlaps are active in the deployed game.

CET analysis follows the framework's per-directory sandbox model: every direct
child of the CET `mods` directory with an `init.lua` is a separate mod root.
Literal module imports are resolved only inside that root, while Vortex packages
that contribute files to the same root are treated as one merged CET mod. The
scanner reports selected entrypoint winners, unresolved imports, and explicit
cross-package module dependencies without treating symbols in separate CET
roots as one global namespace.

Within a merged root, definite top-level global assignments and function
declarations are inventoried alongside explicit `_G`, `_ENV`, indexed, and
`rawset` writes. The same symbol written by different Vortex packages becomes a
review finding because execution/import order determines the effective value.
Computed keys and assignments whose lexical scope cannot be proven remain
partial coverage instead of being treated as collisions.

Literal `TweakDB:SetFlat`, `SetFlatNoUpdate`, `CloneRecord`, `CreateRecord`, and
`DeleteRecord` calls are also inventoried with exact source lines. The parser
decodes static Lua strings, numbers, booleans, nil values, simple array tables,
and common `TweakDBID`/`CName` constructors without executing mod code. Computed
targets and values remain visible as dynamic coverage rather than being guessed.

Lifecycle event registrations and hotkey/input IDs are compared within their
own root. Shared observers are informational because CET retains each callback.
Override chains are considered structurally compatible when every inline
callback visibly invokes its final wrapped/next parameter; dynamic or terminating
chains remain review findings. Native Settings tab/subcategory sharing is
informational, while duplicate leaf control paths remain review findings.

After both language analyzers finish, the cross-ecosystem pass compares active
literal CET `Observe`/`ObserveBefore`/`ObserveAfter`/`Override` targets with
active REDscript `@wrapMethod` and `@replaceMethod` targets. CET observers and
overrides that visibly invoke the wrapped callback preserve the compiled
REDscript method and are informational. An indirect callback is a review;
an inline CET override that visibly omits the wrapped callback is a warning
because it can bypass the REDscript behavior. NativeDB full method names are
matched against REDscript parameter signatures when present. Short CET method
names are retained as medium-confidence, overload-ambiguous matches, while
dynamic targets are counted but never guessed. Same-package CET and REDscript
components are counted as intentional integration and do not create findings.

The same pass compares active literal CET TweakDB targets with concrete TweakXL
identities after template expansion. A runtime `SetFlat` with the same value is
informational; a different value is a warning because CET can replace the
TweakXL-initialized flat. Replacing a flat that TweakXL mutates as an array is
also a warning because the complete CET value can discard composed entries.
Record creation, cloning, and deletion are compared with TweakXL `$type`,
`$base`, and descendant properties. Same-package dual-ecosystem definitions are
counted as integration without producing findings. Dynamic Lua expressions are
reported in coverage but never matched speculatively.

Each scan also reads the current `cyber_engine_tweaks.log`, `scripting.log`, and
canonical `<mod-root>.log` files. Loaded, ignored, and failed roots are counted;
missing RTTI hook targets and Lua source errors are mapped to Vortex artifacts
and source lines where the logs provide enough information.

Shared configuration analysis covers every staged `.json`, `.toml`, `.ini`,
and `.xml` file. Format-normalized fingerprints ignore irrelevant JSON/TOML key
order and formatting when comparing multiple providers of one deployed path.
Different files contributed to the same CET root, input directory, engine
configuration domain, or REDscript user-hint directory are retained as
informational ownership context. Input XML receives additional semantic
analysis from the dedicated Input Loader analyzer.

Parsing is strict for each underlying format. JSON duplicate keys and non-UTF-8
fallback decoding are warnings, while malformed documents are errors with a
source line when the parser exposes one. A failed document remains in the
ownership inventory and makes semantic coverage partial rather than silently
disappearing.

Input mapping analysis follows Input Loader's installed merge algorithm. A
same-tag, same-name top-level node replaces the earlier whole definition unless
the incoming node has `append="true"`; append mode copies only its children.
The scanner compares cross-mod providers using those rules, checks repeated
actions and timing/event policies, resolves action mappings and included
contexts against the effective cache, and validates every active fragment
against `r6/cache/inputContexts.xml`, `r6/cache/inputUserMappings.xml`, and the
current `red4ext/logs/input_loader.log`. Ordinary shared append targets remain
informational; incompatible whole-node providers are conflicts.

Native framework analysis never loads or executes staged code. It hashes each
DLL/ASI provider and its deployed copy, reads Windows fixed-version resources,
and parses PE import tables directly. Non-system imports are resolved against
the binary directory and normal game-local framework locations. The newest
RED4ext loader session supplies the exact framework/game versions and confirms
successful plugin entrypoints; imported DLLs are retained as companion
libraries rather than misclassified as failed plugins. CET and RED4ext game
executable versions are compared to detect stale cross-framework logs.
Structured Codeware and other plugin logs are checked here, while ArchiveXL,
TweakXL, and Input Loader logs remain owned by their dedicated analyzers.

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
  acknowledgements: 'acknowledgements.yaml'

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
versions, invalid choices, non-positive worker/timeout values, duplicate
acknowledgements, and malformed fingerprints.

Acknowledgements live in the separate, versioned `acknowledgements.yaml` file:

```yaml
version: 1

acknowledgements:
  - fingerprint: <64-character fingerprint copied from a report>
    note: Why this exact finding is expected
```

Every finding receives a stable SHA-256 fingerprint based on its rule,
participants, summary shape, and semantic evidence identities. An
acknowledgement changes its report status without removing the finding or its
evidence. If the provider set or target identities change, the old entry becomes
stale so acceptance is never inherited silently. The tracked acknowledgement
file currently contains the four exact-path findings covered by the selected
Damage Scaling Extended and Classic Drinks Vortex winners.

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
- `reports/current/redscript-findings.json`: REDscript annotations and findings.
- `reports/current/cet-findings.json`: CET Lua references and runtime findings.
- `reports/current/config-findings.json`: shared configuration ownership,
  parsing, and exact-path findings.
- `reports/current/input-findings.json`: Input Loader mappings, contexts,
  source lines, cache validation, and startup-log findings.
- `reports/current/native-findings.json`: DLL/ASI providers, hashes, versions,
  PE imports, deployed state, runtime plugin state, and native findings.
- `reports/current/cross-ecosystem-findings.json`: CET-to-REDscript method and
  CET-to-TweakXL TweakDB overlap classifications with both source references.
- `reports/current/compatibility-findings.json`: combined machine-readable findings.
- `reports/current/compatibility-diff.json`: new, changed, resolved, and
  unchanged findings compared with the preceding report in the same output
  directory.
- `reports/current/compatibility-report.html`: searchable, filterable offline report.
- `reports/current/compatibility-report.md`: concise human-readable report.

The HTML report supports free-text search; severity, ecosystem, status, change,
rule, and mod filters; pagination; and expandable evidence. Filter state is
stored in the URL hash so a view can be bookmarked or shared. Acknowledged and
stale entries remain inspectable. Expanding a finding exposes an acknowledgement
checkbox and editable note. `Save acknowledgements` uses a Chromium file picker
to write the separate YAML file after explicit user approval; browsers without
that API download a replacement file instead. The report is self-contained and
does not require a web server. Every absolute Windows `source_path` value in
expanded evidence remains displayed as the complete JSON path but is also a
`file:///` link to its parent directory. Drive-letter and UNC paths are encoded
segment by segment so spaces and URL-special characters remain valid.
