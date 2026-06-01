# Contributing

Agent Context Center is public developer infrastructure. The repo and package id is
`ai-control-center`; the CLI is `acc`. It is a stdlib-only Python generator that scans a
repo's AI context files and emits one offline, deterministic `dashboard.html`. Markdown
stays the source of truth; the dashboard is the human map. Contributions that keep it
offline, deterministic, and dependency-free are welcome.

## Local setup

You need Python 3.12 or newer. The runtime has no third-party dependencies. The only
extra packages are for the test suite.

```bash
git clone https://github.com/omerakben/ai-control-center
cd ai-control-center
python -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"
```

The `[test]` extra installs `pytest` and `pytest-playwright`. The DOM test drives a real
Chromium, so install the browser once:

```bash
playwright install chromium
```

## Run the tests

```bash
python -m pytest
```

Two tests are worth knowing about:

- `tests/test_render_dom.py` loads a generated dashboard in real Chromium and asserts on
  the rendered DOM. It needs the Chromium install above.
- `tests/test_appjs_guard.py` greps the renderer (`src/acc/templates/app.js`) for
  `innerHTML`, `outerHTML`, and `insertAdjacentHTML`. Any HTML sink fails CI. The renderer
  must stay `textContent`-only.

## Generate a dashboard

Run the generator against this repo, or any repo, to see your change end to end:

```bash
acc --root .              # writes into the detected provider folder, prints path + digest
acc --root . --out .      # writes ./dashboard.html at the repo root (--out is a directory)
acc --root . --json       # machine-readable metadata: dashboardPath, sourceDigest, etc.
```

## Run doctor

`acc doctor` reports deterministic findings about a repo's AI context. Use it to check
your own work:

```bash
acc doctor --root .            # findings report; exit 0 unless an execution error (exit 2)
acc doctor --root . --strict   # exit 1 if any warning is present
acc doctor --root . --json     # a doctor.v1 report with a findings list and a status
```

## Add a provider adapter

Adapters live in `src/acc/adapters/`. Each one maps a provider's native files into the
single inventory + docs schema. Use the existing `claude`, `codex`, and `cursor` adapters
as templates.

1. Implement the `ProviderAdapter` protocol from `src/acc/adapters/base.py`: an `id`, a
   `display_name`, a `detect(ctx)` that returns `ProviderRoot`s, and a
   `normalize(ctx, root)` that returns a dict.
2. Build inventory and docs with `empty_inventory()`, `empty_docs()`, and `make_item(...)`
   from `base.py`. Do not hand-roll item dicts — `make_item` assigns the stable id and the
   type label.
3. Read structured config through the allowlisting helpers in `src/acc/config.py`
   (`safe_mcp`, `load_toml`, `as_dict`). Run free-form prose through `redact_text` from
   `src/acc/redaction.py` before it enters an item. Redaction happens at extraction, not at
   render time.
4. Add a builder in `tests/builders.py` that lays down the provider's native files, then a
   `tests/test_<provider>_adapter.py` that asserts the normalized output.

Keep new providers honest: only classify what you actually parse. Files you do not
recognize should fall through to the generic markdown adapter, not be mislabeled.

## Add a doctor detector

Detectors live in `src/acc/doctor.py`. Each one inspects the same assembled data the
dashboard shows and yields `Finding` objects (`level` is `warn` or `info`, plus a `code`
and a `message`).

Rules for a detector:

- Deterministic only. No git history, no mtimes, no network, no model judgment. The same
  repo must always produce the same findings.
- Use `warn` only for something a reader should act on, since `--strict` exits 1 on any
  warning. Use `info` for counts and context.
- Add a test in `tests/test_doctor.py` that builds a fixture repo, runs the detector, and
  asserts the finding codes.

## Add fixtures

Test repos are built in code, not checked in as trees. `tests/builders.py` has
`make_claude_repo`, `make_codex_repo`, and friends. Each writes a small set of native
files into a `tmp_path` so a test can scan a known repo. Extend an existing builder or add
a new one when you add an adapter or a detector.

## Style rules

These are hard requirements, not preferences:

- Output is deterministic and byte-stable. Sort every list explicitly. Re-stamping a repo
  with no content change must produce an identical file.
- The renderer is `textContent`-only. No `innerHTML`-family sinks in `app.js`. Repo content
  must not be able to inject script into the committed HTML.
- Redaction runs before render, through `redaction.py` and the `config.py` allowlist.
- No third-party runtime dependencies. The package is stdlib Python 3.12+. Test-only
  packages go in the `[test]` extra.

## Tests and docs expectations

Every adapter or detector lands with a fixture and a test. If you change a flag, a schema
field, or generator behavior, update the README and `AGENTS.md` to match. Keep claims
accurate — say "supported" only for what the code parses today, and label planned work as
planned.

## Good first issues

- A new provider adapter (a markdown-based agent tool that today only lands as generic).
- A new doctor detector (a deterministic, reproducible finding).
- An example repo under fixtures that exercises an edge case.
- Dashboard CSS in `src/acc/templates/styles.css`.
- Docs: README, `AGENTS.md`, examples, and this file.
