# CP77 Compatibility Scanner

Read-only compatibility analysis for a Vortex-managed Cyberpunk 2077 mod
collection. The scanner reads the Vortex staging directory, deployed game
directory, and `vortex.deployment.json`. It writes only to its report and cache
directories.

The first milestone includes:

- per-mod file inventory and Vortex deployment attribution;
- exact relative-path collision reporting;
- ArchiveXL YAML/JSON parsing;
- WolvenKit CLI archive member indexing without extraction;
- ArchiveXL reference resolution and streaming overlap checks;
- deterministic JSON and Markdown reports.

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

Use `--refresh-cache` to rebuild WolvenKit archive manifests. Archive payloads
are not extracted in this milestone.

## Reports

- `reports/current/inventory.json`: mods, files, hashes, and deployment state.
- `reports/current/archive-manifests.json`: WolvenKit archive member indexes.
- `reports/current/archivexl-findings.json`: complete references and evidence.
- `reports/current/compatibility-report.html`: searchable, filterable offline report.
- `reports/current/compatibility-report.md`: concise human-readable report.

The HTML report supports free-text search, severity/rule/mod filters, pagination,
and expandable evidence. It is self-contained and does not require a web server.
