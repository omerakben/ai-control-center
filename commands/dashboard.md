---
name: dashboard
description: Generate or refresh the AI Control Center dashboard — one offline HTML file inventorying this repo's AI configuration (agents, skills, hooks, commands, MCP servers, rules, docs, open TODOs). Use when asked to build, refresh, regenerate, stamp, or open the AI control center / repo AI dashboard.
allowed-tools:
  - Bash
  - Read
---

# /dashboard — stamp the AI Control Center

Run the bundled generator against the **user's project** (never the plugin dir) and
report what it wrote. The generator is stdlib Python 3.12+, offline, deterministic, and
redacts secrets at extraction — there is no build step and nothing is installed.

Run exactly this in one Bash call:

```bash
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$ROOT" ]; then
  echo "AI Control Center: CLAUDE_PROJECT_DIR is not set; refusing to scan an unknown directory." >&2
  exit 1
fi

PLUGIN="${CLAUDE_PLUGIN_ROOT:-}"
if [ -z "$PLUGIN" ] || [ ! -d "$PLUGIN/src/acc" ]; then
  echo "AI Control Center: cannot locate the bundled generator (CLAUDE_PLUGIN_ROOT/src/acc)." >&2
  exit 1
fi

# Pick the first interpreter that is actually >=3.12. The generator uses 3.10+
# syntax that is evaluated at import, so a stale system python3 (macOS ships
# 3.9) must be rejected with a clear message, never a stack trace.
PY=""
for cand in python3.13 python3.12 python3; do
  if command -v "$cand" >/dev/null 2>&1 \
     && "$cand" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)' 2>/dev/null; then
    PY="$cand"; break
  fi
done
if [ -z "$PY" ]; then
  found="$(command -v python3 >/dev/null 2>&1 && python3 -c 'import sys;print("%d.%d.%d"%tuple(sys.version_info[:3]))' 2>/dev/null || echo none)"
  echo "AI Control Center needs Python 3.12+ on PATH (found: $found)." >&2
  echo "Install it — macOS: 'brew install python@3.12'; or use pyenv — then retry /dashboard." >&2
  exit 1
fi

PYTHONPATH="$PLUGIN/src" "$PY" -m acc.cli --root "$ROOT" --json
```

Then:

1. On success the last line is JSON: `{"dashboardPath","sourceDigest","scannedFileCount","providers","truncated"}`. Tell the user the dashboard was written to `dashboardPath` (it lives under the owning provider folder, e.g. `.claude/dashboard.html`), and report `scannedFileCount` files and digest `sourceDigest`. Remind them freshness is manual: re-run `/dashboard` after editing AI markdown, or install an opt-in template from the plugin's `templates/refresh/`.
2. If it exits with `error: multiple dashboards found (...)`, the repo has more than one provider dashboard. Ask the user which folder owns it, then re-run the same command with `--owner <dir>` (e.g. `--owner .claude`) added before `--json`.
3. If it prints the "needs Python 3.12+" or "CLAUDE_PROJECT_DIR" message, relay that line verbatim — do not retry or improvise another interpreter.

Never hand-edit the generated `dashboard.html`. To change its content, edit the source
AI markdown and re-run `/dashboard` so redaction and the secret tripwire re-fire.
