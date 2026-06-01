# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] — 2026-05-31

### Changed

- Repositioned the project as "Agent Context Center" (the `acc` CLI now stands for
  Agent Context Center); the tool maps and reviews AI context, it does not control agents.
- The CLI gained subcommands (`generate` default, `doctor`); `acc --root .` and
  `acc --json` keep working unchanged.

### Added

- `acc doctor`: deterministic findings report with `--strict` and `--json` (doctor.v1).
- README, docs, and community files for the public repository.
- Example repos under `examples/`.
- A GitHub Pages demo of a generated dashboard.

## [1.2.0]

### Added

- TUEL brand theme: emerald, teal, and navy palette.

## [1.1.2]

### Added

- Reading pane links to the full source file when a rendered body is capped.

## [1.1.1]

### Changed

- Decode YAML frontmatter escapes before display.
- Cap summaries to the lead sentence.

### Added

- Render markdown tables in the reading pane.

## [1.1.0]

### Added

- Client-side markdown rendering with an inline reading pane.
- Graduated truncation for large repos.

## [1.0.1]

### Fixed

- Redaction render-mismatch between the scanned source and the rendered output.

## [1.0.0]

### Added

- First release: deterministic, offline `dashboard.html` generation.
- Adapters for Claude Code, Codex, and Cursor, plus a generic markdown index.
- Redaction before rendering.
- Claude Code marketplace plugin.
