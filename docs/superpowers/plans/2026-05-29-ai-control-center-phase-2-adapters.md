# AI Control Center — Phase 2 (first-class provider adapters) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add first-class Claude Code, Codex, and Cursor adapters that map native conventions into the superset schema, activate the allowlist redaction tier for structured config, and merge every detected provider into one dashboard via the owner rule.

**Architecture:** Two new stdlib helpers (`frontmatter.py`, `config.py`) feed three thin per-provider adapters. `generate.py` detects all providers, each first-class adapter claims its provider folder, the generic adapter indexes the unclaimed markdown, and the partials merge into one deterministic dashboard. A `validate()` tripwire re-scans the serialized output for surviving secrets. Phase 2 is data-only; the renderer is unchanged (Phase 3).

**Tech Stack:** Python 3.12 (stdlib only at runtime — `tomllib`, `json`, `re`, `html`), pytest (dev only).

This is Phase 2 of 4. Spec: `docs/superpowers/specs/2026-05-29-ai-control-center-phase-2-adapters-design.md`. Builds on Phase 1 (merged). Phase 3 (renderer) and Phase 4 (refresh + packaging) get their own plans.

---

## File structure

```text
src/acc/
  frontmatter.py          # NEW  parse_frontmatter()
  config.py               # NEW  load_json(), load_toml(), MCP_ALLOWED, safe_mcp()
  adapters/
    base.py               # MODIFY  add make_item(), empty_inventory(), empty_docs()
    claude.py             # NEW  ClaudeAdapter
    codex.py              # NEW  CodexAdapter
    cursor.py             # NEW  CursorAdapter
    generic.py            # unchanged
  schema.py               # MODIFY  add assert_no_secrets(); validate() calls it
  generate.py             # MODIFY  detect-all + file-claiming merge + resolve_owner + providers
  cli.py                  # MODIFY  add --owner; handle OwnerAmbiguousError
tests/
  builders.py             # NEW  make_<provider>_repo() helpers
  test_builders.py        # NEW  smoke test for builders
  test_frontmatter.py     # NEW
  test_config.py          # NEW
  test_adapter_base.py    # NEW
  test_claude_adapter.py  # NEW
  test_codex_adapter.py   # NEW
  test_cursor_adapter.py  # NEW
  test_owner_rule.py      # NEW
  test_schema.py          # MODIFY  assert_no_secrets cases
  test_generate.py        # MODIFY  multi-provider merge, determinism, no-double-list, tripwire
```

Each adapter depends on `ids`, `redaction`, `markdown`, `frontmatter`, `config`, and `adapters.base` — never on another adapter. `generate.py` is the only module that wires adapters together.

**Item shape (inventory):** `{id, provider, type, typeLabel, title, path, summary}`.
**Doc shape (docs buckets):** `{id, title, path, summary, html}` (same as Phase 1 generic docs).
**ProviderSummary:** `{id, displayName, root, detected}` (+ optional `config` facts for Codex).

---

## Task 1: Frontmatter parser

**Files:**
- Create: `src/acc/frontmatter.py`
- Test: `tests/test_frontmatter.py`

- [ ] **Step 1: Write the failing test**

`tests/test_frontmatter.py`:

```python
from acc.frontmatter import parse_frontmatter


def test_no_fence_returns_empty_fields_and_full_body():
    fields, body = parse_frontmatter("# Title\n\nbody text")
    assert fields == {}
    assert body == "# Title\n\nbody text"


def test_parses_simple_keys_and_body():
    text = "---\nname: reviewer\ndescription: Reviews code\n---\n\n# Reviewer\n\nbody"
    fields, body = parse_frontmatter(text)
    assert fields["name"] == "reviewer"
    assert fields["description"] == "Reviews code"
    assert body == "\n# Reviewer\n\nbody"


def test_strips_quotes_and_parses_booleans():
    text = '---\ndescription: "Quoted value"\nalwaysApply: true\ndraft: false\n---\nx'
    fields, _ = parse_frontmatter(text)
    assert fields["description"] == "Quoted value"
    assert fields["alwaysApply"] is True
    assert fields["draft"] is False


def test_parses_inline_list():
    fields, _ = parse_frontmatter('---\ntools: [Read, Grep, Bash]\n---\nx')
    assert fields["tools"] == ["Read", "Grep", "Bash"]


def test_parses_block_list():
    text = "---\ntools:\n  - Read\n  - Grep\n---\nx"
    fields, _ = parse_frontmatter(text)
    assert fields["tools"] == ["Read", "Grep"]


def test_unclosed_fence_is_not_treated_as_frontmatter():
    text = "---\nname: x\nno closing fence here"
    fields, body = parse_frontmatter(text)
    assert fields == {}
    assert body == text


def test_malformed_lines_are_skipped_not_raised():
    text = "---\nname: ok\n:::garbage:::\nmodel: opus\n---\nx"
    fields, _ = parse_frontmatter(text)
    assert fields["name"] == "ok"
    assert fields["model"] == "opus"
    assert ":::garbage:::" not in fields
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_frontmatter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acc.frontmatter'`

- [ ] **Step 3: Write minimal implementation**

`src/acc/frontmatter.py`:

```python
import re

_KEY = re.compile(r"([A-Za-z0-9_-]+):\s*(.*)$")
_BLOCK_ITEM = re.compile(r"\s*-\s+(.*)$")


def _scalar(s: str):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    if s == "true":
        return True
    if s == "false":
        return False
    return s


def _parse_block(lines: list[str]) -> dict:
    fields: dict = {}
    key: str | None = None
    for line in lines:
        if not line.strip():
            continue
        item = _BLOCK_ITEM.match(line)
        if item and key is not None and isinstance(fields.get(key), list):
            fields[key].append(_scalar(item.group(1)))
            continue
        m = _KEY.match(line)
        if not m:
            # unparseable line — skip, never raise
            continue
        key = m.group(1)
        val = m.group(2).strip()
        if val == "":
            fields[key] = []          # may be filled by a following block list
        elif val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            fields[key] = [_scalar(x) for x in inner.split(",")] if inner else []
        else:
            fields[key] = _scalar(val)
    return fields


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse a leading --- fenced frontmatter block. Returns (fields, body).

    Handles the shallow YAML subset real Claude/Cursor artifacts use:
    key: value, quoted strings, inline [a, b] and block (- item) lists, booleans.
    No nested maps. Unparseable lines are skipped. No fence -> ({}, text).
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text
    return _parse_block(lines[1:end]), "\n".join(lines[end + 1:])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_frontmatter.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/acc/frontmatter.py tests/test_frontmatter.py
git commit -m "feat: stdlib frontmatter parser for provider artifacts"
```

---

## Task 2: Safe config loaders and MCP allowlist

**Files:**
- Create: `src/acc/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:

```python
import json
from acc.config import load_json, load_toml, safe_mcp, MCP_ALLOWED


def test_load_json_reads_object(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"a": 1}))
    assert load_json(p) == {"a": 1}


def test_load_json_returns_empty_on_missing(tmp_path):
    assert load_json(tmp_path / "nope.json") == {}


def test_load_json_returns_empty_on_malformed(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{ not valid json")
    assert load_json(p) == {}


def test_load_toml_reads_tables(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('model = "gpt-5.5"\n[mcp_servers.ctx]\ncommand = "npx"\n')
    data = load_toml(p)
    assert data["model"] == "gpt-5.5"
    assert data["mcp_servers"]["ctx"]["command"] == "npx"


def test_load_toml_returns_empty_on_malformed(tmp_path):
    p = tmp_path / "bad.toml"
    p.write_text("this is = not [valid toml")
    assert load_toml(p) == {}


def test_safe_mcp_keeps_allowlisted_drops_env():
    server = {"command": "npx", "args": ["-y", "pg-mcp"],
              "type": "stdio", "url": "https://h",
              "env": {"PGPASSWORD": "s3cr3tpassword"}, "headers": {"X": "y"}}
    clean = safe_mcp(server)
    assert set(clean.keys()) <= MCP_ALLOWED
    assert "env" not in clean and "headers" not in clean
    assert "s3cr3tpassword" not in str(clean)
    assert clean["command"] == "npx"


def test_safe_mcp_redacts_credential_url():
    clean = safe_mcp({"url": "https://user:p4ssw0rd@h/x"})
    assert "p4ssw0rd" not in str(clean)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acc.config'`

- [ ] **Step 3: Write minimal implementation**

`src/acc/config.py`:

```python
import json
import tomllib
from pathlib import Path

from .redaction import allowlist_config

# MCP server config keys that are safe to surface. `type` is the transport
# (stdio/http/sse); `url` is redacted for embedded credentials. Everything
# else (env, headers, tokens, ...) is dropped — this tier fails closed.
MCP_ALLOWED = {"command", "args", "type", "url"}


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_toml(path: Path) -> dict:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def safe_mcp(server: dict) -> dict:
    """Allowlist a single MCP server config, redacting surviving values."""
    return allowlist_config(server, MCP_ALLOWED)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/acc/config.py tests/test_config.py
git commit -m "feat: safe json/toml config loaders with MCP allowlist"
```

---

## Task 3: Adapter shape helpers

**Files:**
- Modify: `src/acc/adapters/base.py`
- Test: `tests/test_adapter_base.py`

- [ ] **Step 1: Write the failing test**

`tests/test_adapter_base.py`:

```python
from acc.adapters.base import make_item, empty_inventory, empty_docs


def test_make_item_has_full_shape_and_stable_id():
    a = make_item("claude", "agent", "Claude agent", "reviewer", ".claude/agents/reviewer.md", "sums")
    b = make_item("claude", "agent", "Claude agent", "reviewer", ".claude/agents/reviewer.md", "sums")
    assert a == b
    assert a["provider"] == "claude"
    assert a["type"] == "agent"
    assert a["typeLabel"] == "Claude agent"
    assert a["title"] == "reviewer"
    assert a["path"] == ".claude/agents/reviewer.md"
    assert a["summary"] == "sums"
    assert len(a["id"]) == 12


def test_make_item_id_varies_with_inputs():
    base = make_item("claude", "agent", "Claude agent", "reviewer", ".claude/agents/reviewer.md", "")
    other = make_item("cursor", "rule", "Cursor rule", "reviewer", ".claude/agents/reviewer.md", "")
    assert base["id"] != other["id"]


def test_empty_shapes_have_expected_buckets():
    assert set(empty_inventory()) == {"agents", "skills", "hooks", "commands", "mcpServers", "rules"}
    assert set(empty_docs()) == {"prds", "adrs", "decisions", "workflows", "references"}
    assert all(v == [] for v in empty_inventory().values())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_adapter_base.py -v`
Expected: FAIL with `ImportError: cannot import name 'make_item'`

- [ ] **Step 3: Modify `src/acc/adapters/base.py`**

Append to the existing file (keep the existing `ScanContext`, `ProviderRoot`, `ProviderAdapter`). Add the `ids` import at the top alongside the existing imports:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..ids import stable_id


@dataclass
class ScanContext:
    root: Path
    files: list[Path]


@dataclass
class ProviderRoot:
    provider: str
    path: Path


class ProviderAdapter(Protocol):
    id: str
    display_name: str

    def detect(self, ctx: ScanContext) -> list[ProviderRoot]: ...

    def normalize(self, ctx: ScanContext, root: ProviderRoot) -> dict: ...


_INV_BUCKETS = ("agents", "skills", "hooks", "commands", "mcpServers", "rules")
_DOC_BUCKETS = ("prds", "adrs", "decisions", "workflows", "references")


def empty_inventory() -> dict:
    return {k: [] for k in _INV_BUCKETS}


def empty_docs() -> dict:
    return {k: [] for k in _DOC_BUCKETS}


def make_item(provider: str, kind: str, type_label: str,
              title: str, path: str, summary: str) -> dict:
    return {
        "id": stable_id(provider, kind, path, title),
        "provider": provider,
        "type": kind,
        "typeLabel": type_label,
        "title": title,
        "path": path,
        "summary": summary,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_adapter_base.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/acc/adapters/base.py tests/test_adapter_base.py
git commit -m "feat: adapter shape helpers (make_item, empty inventory/docs)"
```

---

## Task 4: Test fixture builders

**Files:**
- Create: `tests/builders.py`
- Test: `tests/test_builders.py`

These helpers stamp realistic provider layouts into a `tmp_path` for the adapter and integration tests. Nothing is committed as a fixture tree.

- [ ] **Step 1: Write the failing test**

`tests/test_builders.py`:

```python
from acc.scan import scan_files
from tests.builders import (
    make_claude_repo, make_codex_repo, make_cursor_repo,
    make_multi_provider_repo, make_brownfield_repo,
)


def _rels(root):
    return {p.relative_to(root).as_posix() for p in scan_files(root)}


def test_claude_repo_has_expected_files(tmp_path):
    make_claude_repo(tmp_path)
    rels = _rels(tmp_path)
    assert ".claude/agents/reviewer.md" in rels
    assert ".claude/commands/ship.md" in rels
    assert ".claude/skills/pdf/SKILL.md" in rels
    assert ".claude/settings.json" in rels
    assert ".mcp.json" in rels
    assert "CLAUDE.md" in rels


def test_codex_repo_has_expected_files(tmp_path):
    make_codex_repo(tmp_path)
    rels = _rels(tmp_path)
    assert ".codex/config.toml" in rels
    assert ".codex/prompts/refactor.md" in rels
    assert "AGENTS.md" in rels


def test_cursor_repo_has_expected_files(tmp_path):
    make_cursor_repo(tmp_path)
    rels = _rels(tmp_path)
    assert ".cursor/rules/style.mdc" in rels
    assert ".cursorrules" in rels
    assert ".cursor/mcp.json" in rels


def test_multi_provider_repo_has_all_three(tmp_path):
    make_multi_provider_repo(tmp_path)
    rels = _rels(tmp_path)
    assert ".claude/agents/reviewer.md" in rels
    assert ".codex/config.toml" in rels
    assert ".cursor/rules/style.mdc" in rels
    assert "docs/notes.md" in rels


def test_brownfield_repo_has_only_loose_markdown(tmp_path):
    make_brownfield_repo(tmp_path)
    rels = _rels(tmp_path)
    assert "README.md" in rels
    assert not any(r.startswith((".claude/", ".codex/", ".cursor/")) for r in rels)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_builders.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tests.builders'`
(If `tests` is not importable, add an empty `tests/__init__.py`; create it in Step 3.)

- [ ] **Step 3: Write the builders**

Create `tests/__init__.py` (empty file) so `tests.builders` imports cleanly.

`tests/builders.py`:

```python
import json
from pathlib import Path


def make_claude_repo(root: Path, *, with_secret: bool = False) -> Path:
    (root / ".claude" / "agents").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "agents" / "reviewer.md").write_text(
        "---\nname: reviewer\ndescription: Reviews code for bugs\n"
        "model: opus\ntools: [Read, Grep]\n---\n\n# Reviewer\n\nReviews diffs."
    )
    (root / ".claude" / "commands").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "commands" / "ship.md").write_text(
        "---\ndescription: Ship the release\nargument-hint: <version>\n---\n\nShip it."
    )
    (root / ".claude" / "skills" / "pdf").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "skills" / "pdf" / "SKILL.md").write_text(
        "---\nname: pdf\ndescription: Process PDF files\n---\n\n# PDF skill"
    )
    settings = {
        "hooks": {"PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo hi"}]}
        ]},
        "mcpServers": {"local": {"command": "node", "args": ["server.js"]}},
    }
    (root / ".claude" / "settings.json").write_text(json.dumps(settings))
    mcp = {"mcpServers": {"postgres": {
        "command": "npx", "args": ["-y", "pg-mcp"],
        "env": {"PGPASSWORD": "s3cr3tpassword"},
    }}}
    (root / ".mcp.json").write_text(json.dumps(mcp))
    (root / "CLAUDE.md").write_text("# My Project\n\nProject memory and rules.")
    if with_secret:
        (root / ".claude" / "agents" / "leaky.md").write_text(
            "---\nname: leaky\ndescription: uses token ghp_0123456789abcdefghij\n---\n"
        )
    return root


def make_codex_repo(root: Path) -> Path:
    (root / ".codex").mkdir(parents=True, exist_ok=True)
    (root / ".codex" / "config.toml").write_text(
        'model = "gpt-5.5"\nmodel_reasoning_effort = "xhigh"\n'
        'sandbox = "workspace-write"\napproval_policy = "on-request"\n\n'
        '[mcp_servers.context7]\ncommand = "npx"\nargs = ["-y", "@upstash/context7-mcp"]\n'
    )
    (root / ".codex" / "prompts").mkdir(parents=True, exist_ok=True)
    (root / ".codex" / "prompts" / "refactor.md").write_text("# Refactor\n\nRefactor steps.")
    (root / "AGENTS.md").write_text("# html-dash\n\nGuide.\n\n- [ ] pick a framework")
    return root


def make_cursor_repo(root: Path) -> Path:
    (root / ".cursor" / "rules").mkdir(parents=True, exist_ok=True)
    (root / ".cursor" / "rules" / "style.mdc").write_text(
        '---\ndescription: TypeScript style rules\nglobs: ["*.ts"]\nalwaysApply: true\n---\n\nUse const.'
    )
    (root / ".cursorrules").write_text("Legacy single-file Cursor rules.")
    (root / ".cursor" / "mcp.json").write_text(
        json.dumps({"mcpServers": {"figma": {"url": "https://mcp.figma.com"}}})
    )
    return root


def make_multi_provider_repo(root: Path) -> Path:
    make_claude_repo(root)
    make_codex_repo(root)
    make_cursor_repo(root)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "notes.md").write_text("# Notes\n\nLoose project notes.")
    return root


def make_brownfield_repo(root: Path) -> Path:
    (root / "README.md").write_text("# Brownfield\n\nNo AI provider here.")
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "guide.md").write_text("# Guide\n\nSome guide text.")
    return root
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_builders.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/__init__.py tests/builders.py tests/test_builders.py
git commit -m "test: hybrid in-test fixture builders for provider repos"
```

---

## Task 5: Claude Code adapter

**Files:**
- Create: `src/acc/adapters/claude.py`
- Test: `tests/test_claude_adapter.py`

- [ ] **Step 1: Write the failing test**

`tests/test_claude_adapter.py`:

```python
from acc.adapters.base import ScanContext
from acc.adapters.claude import ClaudeAdapter
from acc.scan import scan_files
from tests.builders import make_claude_repo, make_brownfield_repo


def _normalize(tmp_path):
    ctx = ScanContext(root=tmp_path, files=scan_files(tmp_path))
    ad = ClaudeAdapter()
    roots = ad.detect(ctx)
    return ad, roots, ad.normalize(ctx, roots[0]) if roots else None


def test_detects_claude_provider(tmp_path):
    make_claude_repo(tmp_path)
    ad, roots, _ = _normalize(tmp_path)
    assert roots and roots[0].provider == "claude"


def test_does_not_detect_on_brownfield(tmp_path):
    make_brownfield_repo(tmp_path)
    ctx = ScanContext(root=tmp_path, files=scan_files(tmp_path))
    assert ClaudeAdapter().detect(ctx) == []


def test_inventories_agents_commands_skills(tmp_path):
    make_claude_repo(tmp_path)
    _, _, part = _normalize(tmp_path)
    inv = part["inventory"]
    assert [a["title"] for a in inv["agents"]] == ["reviewer"]
    assert inv["agents"][0]["typeLabel"] == "Claude agent"
    assert inv["agents"][0]["summary"] == "Reviews code for bugs"
    assert [c["title"] for c in inv["commands"]] == ["ship"]
    assert [s["title"] for s in inv["skills"]] == ["pdf"]


def test_inventories_hooks_and_mcp(tmp_path):
    make_claude_repo(tmp_path)
    _, _, part = _normalize(tmp_path)
    inv = part["inventory"]
    assert inv["hooks"], "expected a hook from settings.json"
    names = {m["title"] for m in inv["mcpServers"]}
    assert {"postgres", "local"} <= names


def test_mcp_env_secret_is_dropped(tmp_path):
    make_claude_repo(tmp_path)
    _, _, part = _normalize(tmp_path)
    assert "s3cr3tpassword" not in str(part)


def test_surfaces_claude_md_doc(tmp_path):
    make_claude_repo(tmp_path)
    _, _, part = _normalize(tmp_path)
    refs = part["docs"]["references"]
    assert any(d["path"] == "CLAUDE.md" and d["title"] == "My Project" for d in refs)


def test_provider_summary_shape(tmp_path):
    make_claude_repo(tmp_path)
    _, _, part = _normalize(tmp_path)
    prov = part["provider"]
    assert prov["id"] == "claude"
    assert prov["displayName"] == "Claude Code"
    assert prov["detected"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_claude_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acc.adapters.claude'`

- [ ] **Step 3: Write the adapter**

`src/acc/adapters/claude.py`:

```python
from pathlib import Path

from .base import ScanContext, ProviderRoot, make_item, empty_inventory, empty_docs
from ..ids import rel_posix
from ..redaction import redact_text
from ..markdown import render_markdown_safe
from ..frontmatter import parse_frontmatter
from ..config import load_json, safe_mcp
from .generic import _first_heading, _first_paragraph


def _title(fields: dict, fallback: str) -> str:
    name = fields.get("name")
    return name if isinstance(name, str) and name else fallback


def _desc(fields: dict) -> str:
    d = fields.get("description", "")
    return redact_text(d)[0] if isinstance(d, str) else ""


class ClaudeAdapter:
    id = "claude"
    display_name = "Claude Code"

    def detect(self, ctx: ScanContext) -> list[ProviderRoot]:
        root = ctx.root
        if (root / ".claude").is_dir() or (root / "CLAUDE.md").is_file():
            base = root / ".claude" if (root / ".claude").is_dir() else root
            return [ProviderRoot(provider="claude", path=base)]
        return []

    def normalize(self, ctx: ScanContext, root: ProviderRoot) -> dict:
        inv = empty_inventory()
        docs = empty_docs()

        for p in ctx.files:
            rel = rel_posix(p, ctx.root)
            try:
                raw = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            stem = p.stem

            if rel.startswith(".claude/agents/") and rel.endswith(".md"):
                fields, _ = parse_frontmatter(raw)
                inv["agents"].append(make_item(
                    "claude", "agent", "Claude agent",
                    _title(fields, stem), rel, _desc(fields)))
            elif rel.startswith(".claude/commands/") and rel.endswith(".md"):
                fields, _ = parse_frontmatter(raw)
                inv["commands"].append(make_item(
                    "claude", "command", "Claude command",
                    _title(fields, stem), rel, _desc(fields)))
            elif rel.startswith(".claude/skills/") and rel.endswith("/SKILL.md"):
                fields, _ = parse_frontmatter(raw)
                name = _title(fields, Path(rel).parent.name)
                inv["skills"].append(make_item(
                    "claude", "skill", "Claude skill", name, rel, _desc(fields)))
            elif rel == "CLAUDE.md" or (rel.startswith(".claude/") and rel.endswith("/CLAUDE.md")):
                clean, _ = redact_text(raw)
                heading = _first_heading(clean) or rel
                docs["references"].append({
                    "id": make_item("claude", "doc", "Claude instructions", heading, rel, "")["id"],
                    "title": heading,
                    "path": rel,
                    "summary": _first_paragraph(clean),
                    "html": render_markdown_safe(clean),
                })

        inv["hooks"].extend(self._hooks(ctx.root))
        inv["mcpServers"].extend(self._mcp(ctx.root))

        return {
            "provider": {"id": self.id, "displayName": self.display_name,
                         "root": rel_posix(root.path, ctx.root) if root.path != ctx.root else ".",
                         "detected": True},
            "inventory": inv,
            "docs": docs,
        }

    # Reuses generic's prose helpers (_first_heading/_first_paragraph) to derive
    # the heading/summary for CLAUDE.md. No import cycle: generic imports only
    # base/ids/redaction/markdown, none of which import this adapter.
    def _hooks(self, root: Path) -> list[dict]:
        settings = load_json(root / ".claude" / "settings.json")
        out: list[dict] = []
        for event, entries in (settings.get("hooks") or {}).items():
            for entry in entries if isinstance(entries, list) else []:
                matcher = entry.get("matcher", "")
                for h in entry.get("hooks", []):
                    cmd = redact_text(str(h.get("command", "")))[0]
                    title = f"{event} ({matcher})" if matcher else event
                    out.append(make_item(
                        "claude", "hook", "Claude hook", title,
                        ".claude/settings.json", cmd))
        return out

    def _mcp(self, root: Path) -> list[dict]:
        merged: dict[str, tuple[str, dict]] = {}
        # settings.json first, then .mcp.json overrides on name conflict
        for rel in (".claude/settings.json", ".mcp.json"):
            path = root / rel
            servers = load_json(path).get("mcpServers") or {}
            for name, cfg in servers.items():
                merged[name] = (rel, cfg if isinstance(cfg, dict) else {})
        out: list[dict] = []
        for name, (rel, cfg) in merged.items():
            clean = safe_mcp(cfg)
            summary = clean.get("command") or clean.get("url") or ""
            item = make_item("claude", "mcpServer", "MCP server", name, rel, summary)
            item["config"] = clean
            out.append(item)
        return out
```

> Note: the `from ..adapters.generic import _first_heading, _first_paragraph` import reuses Phase 1's prose helpers for the instruction-doc heading/summary. It is a local import to avoid a module-load cycle through `generate.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_claude_adapter.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/acc/adapters/claude.py tests/test_claude_adapter.py
git commit -m "feat: Claude Code adapter (agents, commands, skills, hooks, mcp, CLAUDE.md)"
```

---

## Task 6: Codex adapter

**Files:**
- Create: `src/acc/adapters/codex.py`
- Test: `tests/test_codex_adapter.py`

- [ ] **Step 1: Write the failing test**

`tests/test_codex_adapter.py`:

```python
from acc.adapters.base import ScanContext
from acc.adapters.codex import CodexAdapter
from acc.scan import scan_files
from tests.builders import make_codex_repo, make_brownfield_repo


def _normalize(tmp_path):
    ctx = ScanContext(root=tmp_path, files=scan_files(tmp_path))
    ad = CodexAdapter()
    roots = ad.detect(ctx)
    return roots, (ad.normalize(ctx, roots[0]) if roots else None)


def test_detects_codex_provider(tmp_path):
    make_codex_repo(tmp_path)
    roots, _ = _normalize(tmp_path)
    assert roots and roots[0].provider == "codex"


def test_does_not_detect_on_brownfield(tmp_path):
    make_brownfield_repo(tmp_path)
    ctx = ScanContext(root=tmp_path, files=scan_files(tmp_path))
    assert CodexAdapter().detect(ctx) == []


def test_inventories_mcp_from_toml(tmp_path):
    make_codex_repo(tmp_path)
    _, part = _normalize(tmp_path)
    names = {m["title"] for m in part["inventory"]["mcpServers"]}
    assert "context7" in names


def test_prompts_map_into_commands_bucket(tmp_path):
    make_codex_repo(tmp_path)
    _, part = _normalize(tmp_path)
    cmds = part["inventory"]["commands"]
    assert any(c["title"] == "refactor" and c["typeLabel"] == "Codex prompt" for c in cmds)


def test_surfaces_agents_md_doc(tmp_path):
    make_codex_repo(tmp_path)
    _, part = _normalize(tmp_path)
    refs = part["docs"]["references"]
    assert any(d["path"] == "AGENTS.md" for d in refs)


def test_provider_summary_has_config_facts(tmp_path):
    make_codex_repo(tmp_path)
    _, part = _normalize(tmp_path)
    prov = part["provider"]
    assert prov["id"] == "codex"
    assert prov["displayName"] == "Codex"
    assert prov["config"]["model"] == "gpt-5.5"
    assert prov["config"]["approval_policy"] == "on-request"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_codex_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acc.adapters.codex'`

- [ ] **Step 3: Write the adapter**

`src/acc/adapters/codex.py`:

```python
from pathlib import Path

from .base import ScanContext, ProviderRoot, make_item, empty_inventory, empty_docs
from ..ids import rel_posix
from ..redaction import redact_text
from ..markdown import render_markdown_safe
from ..config import load_toml, safe_mcp
from .generic import _first_heading, _first_paragraph

_CONFIG_FACTS = ("model", "model_reasoning_effort", "sandbox", "approval_policy")


class CodexAdapter:
    id = "codex"
    display_name = "Codex"

    def detect(self, ctx: ScanContext) -> list[ProviderRoot]:
        root = ctx.root
        if (root / ".codex").is_dir() or (root / "AGENTS.md").is_file():
            base = root / ".codex" if (root / ".codex").is_dir() else root
            return [ProviderRoot(provider="codex", path=base)]
        return []

    def normalize(self, ctx: ScanContext, root: ProviderRoot) -> dict:
        inv = empty_inventory()
        docs = empty_docs()
        toml = load_toml(ctx.root / ".codex" / "config.toml")

        for name, cfg in (toml.get("mcp_servers") or {}).items():
            clean = safe_mcp(cfg if isinstance(cfg, dict) else {})
            item = make_item("codex", "mcpServer", "MCP server", name,
                             ".codex/config.toml", clean.get("command") or clean.get("url") or "")
            item["config"] = clean
            inv["mcpServers"].append(item)

        for p in ctx.files:
            rel = rel_posix(p, ctx.root)
            if rel.startswith(".codex/prompts/") and rel.endswith(".md"):
                try:
                    raw = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                clean, _ = redact_text(raw)
                # prompts are invoked by filename, so the stem is the title
                inv["commands"].append(make_item(
                    "codex", "command", "Codex prompt", p.stem, rel,
                    _first_paragraph(clean)))
            elif rel == "AGENTS.md" or (rel.startswith(".codex/") and rel.endswith("/AGENTS.md")):
                try:
                    raw = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                clean, _ = redact_text(raw)
                heading = _first_heading(clean) or rel
                docs["references"].append({
                    "id": make_item("codex", "doc", "Codex instructions", heading, rel, "")["id"],
                    "title": heading,
                    "path": rel,
                    "summary": _first_paragraph(clean),
                    "html": render_markdown_safe(clean),
                })

        facts = {k: redact_text(str(toml[k]))[0] for k in _CONFIG_FACTS if k in toml}
        return {
            "provider": {"id": self.id, "displayName": self.display_name,
                         "root": rel_posix(root.path, ctx.root) if root.path != ctx.root else ".",
                         "detected": True, "config": facts},
            "inventory": inv,
            "docs": docs,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_codex_adapter.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/acc/adapters/codex.py tests/test_codex_adapter.py
git commit -m "feat: Codex adapter (mcp from toml, prompts, AGENTS.md, config facts)"
```

---

## Task 7: Cursor adapter

**Files:**
- Create: `src/acc/adapters/cursor.py`
- Test: `tests/test_cursor_adapter.py`

- [ ] **Step 1: Write the failing test**

`tests/test_cursor_adapter.py`:

```python
from acc.adapters.base import ScanContext
from acc.adapters.cursor import CursorAdapter
from acc.scan import scan_files
from tests.builders import make_cursor_repo, make_brownfield_repo


def _normalize(tmp_path):
    ctx = ScanContext(root=tmp_path, files=scan_files(tmp_path))
    ad = CursorAdapter()
    roots = ad.detect(ctx)
    return roots, (ad.normalize(ctx, roots[0]) if roots else None)


def test_detects_cursor_provider(tmp_path):
    make_cursor_repo(tmp_path)
    roots, _ = _normalize(tmp_path)
    assert roots and roots[0].provider == "cursor"


def test_does_not_detect_on_brownfield(tmp_path):
    make_brownfield_repo(tmp_path)
    ctx = ScanContext(root=tmp_path, files=scan_files(tmp_path))
    assert CursorAdapter().detect(ctx) == []


def test_inventories_mdc_rule(tmp_path):
    make_cursor_repo(tmp_path)
    _, part = _normalize(tmp_path)
    rules = part["inventory"]["rules"]
    style = next(r for r in rules if r["path"] == ".cursor/rules/style.mdc")
    assert style["typeLabel"] == "Cursor rule"
    assert style["title"] == "style"
    assert style["summary"] == "TypeScript style rules"


def test_inventories_legacy_cursorrules(tmp_path):
    make_cursor_repo(tmp_path)
    _, part = _normalize(tmp_path)
    assert any(r["path"] == ".cursorrules" for r in part["inventory"]["rules"])


def test_inventories_mcp(tmp_path):
    make_cursor_repo(tmp_path)
    _, part = _normalize(tmp_path)
    assert any(m["title"] == "figma" for m in part["inventory"]["mcpServers"])


def test_provider_summary_shape(tmp_path):
    make_cursor_repo(tmp_path)
    _, part = _normalize(tmp_path)
    assert part["provider"]["id"] == "cursor"
    assert part["provider"]["displayName"] == "Cursor"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cursor_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acc.adapters.cursor'`

- [ ] **Step 3: Write the adapter**

`src/acc/adapters/cursor.py`:

```python
from .base import ScanContext, ProviderRoot, make_item, empty_inventory, empty_docs
from ..ids import rel_posix
from ..redaction import redact_text
from ..frontmatter import parse_frontmatter
from ..config import load_json, safe_mcp


class CursorAdapter:
    id = "cursor"
    display_name = "Cursor"

    def detect(self, ctx: ScanContext) -> list[ProviderRoot]:
        root = ctx.root
        if (root / ".cursor").is_dir() or (root / ".cursorrules").is_file():
            base = root / ".cursor" if (root / ".cursor").is_dir() else root
            return [ProviderRoot(provider="cursor", path=base)]
        return []

    def normalize(self, ctx: ScanContext, root: ProviderRoot) -> dict:
        inv = empty_inventory()
        docs = empty_docs()

        for p in ctx.files:
            rel = rel_posix(p, ctx.root)
            if rel.startswith(".cursor/rules/") and rel.endswith(".mdc"):
                try:
                    raw = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                fields, _ = parse_frontmatter(raw)
                desc = fields.get("description", "")
                summary = redact_text(desc)[0] if isinstance(desc, str) else ""
                inv["rules"].append(make_item(
                    "cursor", "rule", "Cursor rule", p.stem, rel, summary))
            elif rel == ".cursorrules":
                inv["rules"].append(make_item(
                    "cursor", "rule", "Cursor rule", ".cursorrules", rel,
                    "Legacy single-file Cursor rules"))

        servers = load_json(ctx.root / ".cursor" / "mcp.json").get("mcpServers") or {}
        for name, cfg in servers.items():
            clean = safe_mcp(cfg if isinstance(cfg, dict) else {})
            item = make_item("cursor", "mcpServer", "MCP server", name,
                             ".cursor/mcp.json", clean.get("command") or clean.get("url") or "")
            item["config"] = clean
            inv["mcpServers"].append(item)

        return {
            "provider": {"id": self.id, "displayName": self.display_name,
                         "root": rel_posix(root.path, ctx.root) if root.path != ctx.root else ".",
                         "detected": True},
            "inventory": inv,
            "docs": docs,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cursor_adapter.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/acc/adapters/cursor.py tests/test_cursor_adapter.py
git commit -m "feat: Cursor adapter (.mdc rules, legacy .cursorrules, mcp)"
```

---

## Task 8: Secret tripwire in schema validation

**Files:**
- Modify: `src/acc/schema.py`
- Test: `tests/test_schema.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_schema.py` (keep the existing imports and tests; extend the import line):

```python
import pytest
from acc.schema import SCHEMA_VERSION, canonical_json, validate, assert_no_secrets


def test_assert_no_secrets_passes_clean_data():
    assert_no_secrets(_minimal_data())  # no exception


def test_assert_no_secrets_raises_on_leaked_token():
    data = _minimal_data()
    data["project"]["summary"] = "token ghp_0123456789abcdefghij"
    with pytest.raises(ValueError, match="tripwire"):
        assert_no_secrets(data)


def test_validate_runs_the_tripwire():
    data = _minimal_data()
    data["project"]["summary"] = "secret = supersecretvalue123"
    with pytest.raises(ValueError, match="tripwire"):
        validate(data)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_schema.py -v`
Expected: FAIL with `ImportError: cannot import name 'assert_no_secrets'`

- [ ] **Step 3: Modify `src/acc/schema.py`**

Replace the file with (adds the `redact_text` import, `assert_no_secrets`, and the `validate` call):

```python
import json

from .redaction import redact_text

SCHEMA_VERSION = "1.0"

_REQUIRED_TOP = {
    "schemaVersion", "generator", "source", "providers",
    "project", "inventory", "docs", "relationships", "search",
}


def canonical_json(data: dict) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def assert_no_secrets(data: dict) -> None:
    """Final tripwire: re-scan the serialized output for surviving secrets.

    Everything reaching `data` is already redacted at extraction. A match here
    means an adapter skipped redaction on a structured-config value — fail loud
    rather than ship a leak.
    """
    _, n = redact_text(canonical_json(data))
    if n:
        raise ValueError(f"redaction tripwire: {n} secret-shaped value(s) survived into output")


def validate(data: dict) -> None:
    missing = _REQUIRED_TOP - data.keys()
    if missing:
        raise ValueError(f"missing required keys: {sorted(missing)}")
    if data["schemaVersion"] != SCHEMA_VERSION:
        raise ValueError(f"unexpected schemaVersion: {data['schemaVersion']!r}")
    assert_no_secrets(data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_schema.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/acc/schema.py tests/test_schema.py
git commit -m "feat: assert_no_secrets tripwire in schema validate"
```

---

## Task 9: Owner rule and provider detection

**Files:**
- Modify: `src/acc/generate.py`
- Test: `tests/test_owner_rule.py`

This task adds detection + the owner rule to `generate.py` without yet wiring the merge (Task 10). `detect_out_dir` is preserved as a delegating wrapper so Phase 1 tests stay green.

- [ ] **Step 1: Write the failing test**

`tests/test_owner_rule.py`:

```python
import pytest
from acc.generate import resolve_owner, detect_providers, OwnerAmbiguousError
from tests.builders import make_claude_repo, make_codex_repo, make_multi_provider_repo


def test_detect_providers_lists_present(tmp_path):
    make_multi_provider_repo(tmp_path)
    assert detect_providers(tmp_path) == ["claude", "codex", "cursor"]


def test_detect_providers_empty_on_brownfield(tmp_path):
    (tmp_path / "README.md").write_text("# x")
    assert detect_providers(tmp_path) == []


def test_owner_none_existing_uses_precedence(tmp_path):
    make_multi_provider_repo(tmp_path)
    out = resolve_owner(tmp_path, detect_providers(tmp_path))
    assert out == (tmp_path / ".claude").resolve()


def test_owner_codex_only(tmp_path):
    make_codex_repo(tmp_path)
    out = resolve_owner(tmp_path, detect_providers(tmp_path))
    assert out == (tmp_path / ".codex").resolve()


def test_owner_falls_back_when_no_provider(tmp_path):
    out = resolve_owner(tmp_path, [])
    assert out == (tmp_path / ".ai-control-center").resolve()


def test_owner_single_existing_dashboard_wins(tmp_path):
    make_codex_repo(tmp_path)
    (tmp_path / ".cursor").mkdir()
    (tmp_path / ".cursor" / "dashboard.html").write_text("<html>")
    out = resolve_owner(tmp_path, detect_providers(tmp_path))
    assert out == (tmp_path / ".cursor").resolve()


def test_owner_multiple_existing_raises(tmp_path):
    for d in (".claude", ".codex"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "dashboard.html").write_text("<html>")
    with pytest.raises(OwnerAmbiguousError, match="--owner"):
        resolve_owner(tmp_path, ["claude", "codex"])


def test_owner_override_wins(tmp_path):
    for d in (".claude", ".codex"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "dashboard.html").write_text("<html>")
    out = resolve_owner(tmp_path, ["claude", "codex"], owner_override=".codex")
    assert out == (tmp_path / ".codex").resolve()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_owner_rule.py -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_owner'`

- [ ] **Step 3: Add detection and the owner rule to `src/acc/generate.py`**

Add these near the top of `generate.py`, after the existing imports and `_PROVIDER_DIRS`:

```python
_PROVIDER_MARKERS = {"claude": "CLAUDE.md", "codex": "AGENTS.md", "cursor": ".cursorrules"}
_PROVIDER_DIR_BY_ID = {"claude": ".claude", "codex": ".codex", "cursor": ".cursor"}
_PRECEDENCE = ("claude", "codex", "cursor")
_KNOWN_OWNER_DIRS = (".claude", ".codex", ".cursor", ".ai-control-center")


class OwnerAmbiguousError(Exception):
    pass


def detect_providers(root: Path) -> list[str]:
    root = root.resolve()
    out: list[str] = []
    for pid in _PRECEDENCE:
        if (root / _PROVIDER_DIR_BY_ID[pid]).is_dir() or (root / _PROVIDER_MARKERS[pid]).is_file():
            out.append(pid)
    return out


def _existing_dashboards(root: Path) -> list[Path]:
    return [root / d / "dashboard.html" for d in _KNOWN_OWNER_DIRS
            if (root / d / "dashboard.html").is_file()]


def resolve_owner(root: Path, detected_ids: list[str], owner_override: str | None = None) -> Path:
    root = root.resolve()
    if owner_override:
        return (root / owner_override).resolve()
    existing = _existing_dashboards(root)
    if len(existing) == 1:
        return existing[0].parent.resolve()
    if len(existing) >= 2:
        names = ", ".join(d.parent.relative_to(root).as_posix() for d in existing)
        raise OwnerAmbiguousError(
            f"multiple dashboards found ({names}); pick one with --owner <dir>")
    for pid in _PRECEDENCE:
        if pid in detected_ids:
            return (root / _PROVIDER_DIR_BY_ID[pid]).resolve()
    return (root / ".ai-control-center").resolve()
```

Then replace the existing `detect_out_dir` with a delegating wrapper (keeps Phase 1 tests green):

```python
def detect_out_dir(root: Path) -> Path:
    root = root.resolve()
    return resolve_owner(root, detect_providers(root))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_owner_rule.py tests/test_generate.py -v`
Expected: PASS (owner-rule tests pass; existing `test_detect_out_dir_*` still pass via the wrapper)

- [ ] **Step 5: Commit**

```bash
git add src/acc/generate.py tests/test_owner_rule.py
git commit -m "feat: provider detection and merged-dashboard owner rule"
```

---

## Task 10: Multi-provider merge in the generate pipeline

**Files:**
- Modify: `src/acc/generate.py`
- Test: `tests/test_generate.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_generate.py` (keep existing imports/tests; extend the import line and add the builders import):

```python
import json
from pathlib import Path
from acc.generate import generate, detect_out_dir
from tests.builders import make_multi_provider_repo, make_claude_repo


def _island(out_path) -> dict:
    html = out_path.read_text(encoding="utf-8")
    raw = html.split('id="acc-data"', 1)[1].split(">", 1)[1].split("</script>", 1)[0]
    return json.loads(raw.replace("<\\/", "</"))


def test_generate_merges_all_providers(tmp_path):
    make_multi_provider_repo(tmp_path)
    out = generate(tmp_path)
    data = _island(out)
    ids = {p["id"] for p in data["providers"]}
    assert {"claude", "codex", "cursor", "generic"} <= ids
    assert any(a["typeLabel"] == "Claude agent" for a in data["inventory"]["agents"])
    assert any(r["typeLabel"] == "Cursor rule" for r in data["inventory"]["rules"])
    assert data["inventory"]["mcpServers"], "expected merged mcp servers"


def test_generate_owner_is_dot_claude_for_multi(tmp_path):
    make_multi_provider_repo(tmp_path)
    out = generate(tmp_path)
    assert out.resolve() == (tmp_path / ".claude" / "dashboard.html").resolve()


def test_generate_multi_provider_is_deterministic(tmp_path):
    make_multi_provider_repo(tmp_path)
    first = generate(tmp_path).read_text(encoding="utf-8")
    second = generate(tmp_path).read_text(encoding="utf-8")
    assert first == second


def test_generic_does_not_double_list_provider_files(tmp_path):
    make_multi_provider_repo(tmp_path)
    data = _island(generate(tmp_path))
    ref_paths = [d["path"] for d in data["docs"]["references"]]
    # provider files appear via their adapters, never duplicated by generic
    assert ref_paths == sorted(set(ref_paths))
    # the loose doc is indexed; the agent file is NOT a generic reference
    assert "docs/notes.md" in ref_paths
    assert ".claude/agents/reviewer.md" not in ref_paths


def test_generate_drops_mcp_env_secret(tmp_path):
    make_claude_repo(tmp_path)
    out = generate(tmp_path)
    assert "s3cr3tpassword" not in out.read_text(encoding="utf-8")


def test_generate_tripwire_blocks_unredacted_leak(tmp_path):
    # an agent whose frontmatter description carries a token shape
    make_claude_repo(tmp_path, with_secret=True)
    out = generate(tmp_path)
    # the description is redacted, so the token never reaches the file
    assert "ghp_0123456789abcdefghij" not in out.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_generate.py -v`
Expected: FAIL — `generate` still runs the generic-only Phase 1 pipeline, so `test_generate_merges_all_providers` fails on missing providers/inventory.

- [ ] **Step 3: Rewrite the pipeline body of `src/acc/generate.py`**

Add imports at the top (alongside the existing ones):

```python
from .adapters.claude import ClaudeAdapter
from .adapters.codex import CodexAdapter
from .adapters.cursor import CursorAdapter
```

Add the claiming rule and merge helpers (after the owner-rule code from Task 9):

```python
_FIRST_CLASS = (ClaudeAdapter, CodexAdapter, CursorAdapter)
_CLAIM_DIRS = (".claude", ".codex", ".cursor")
_CLAIM_MARKERS = ("CLAUDE.md", "AGENTS.md", ".cursorrules")


def _claimed_by_provider(rel: str) -> bool:
    top = rel.split("/", 1)[0]
    return top in _CLAIM_DIRS or rel in _CLAIM_MARKERS


def _merge_parts(parts: list[dict]) -> tuple[dict, dict]:
    inv = empty_inventory()
    docs = empty_docs()
    for part in parts:
        for k, items in part.get("inventory", {}).items():
            inv.setdefault(k, []).extend(items)
        for k, items in part.get("docs", {}).items():
            docs.setdefault(k, []).extend(items)
    for bucket in (inv, docs):
        for k in bucket:
            bucket[k].sort(key=lambda x: (x["path"], x["title"], x["id"]))
    return inv, docs


def _build_search(inv: dict, docs: dict) -> list[dict]:
    records: list[dict] = []
    for bucket in (docs, inv):
        for items in bucket.values():
            for it in items:
                records.append({"id": it["id"], "title": it["title"],
                                "path": it["path"], "text": it.get("summary", "")})
    records.sort(key=lambda r: (r["path"], r["title"], r["id"]))
    return records


def _escape_summaries(inv: dict, docs: dict) -> None:
    for bucket in (inv, docs):
        for items in bucket.values():
            for it in items:
                if "summary" in it:
                    it["summary"] = _html.escape(it["summary"])
```

Update the imports from `adapters.base` so `empty_inventory`/`empty_docs` are available:

```python
from .adapters.base import ScanContext, empty_inventory, empty_docs
```

Replace the `generate` function body with:

```python
def generate(root: Path, out_dir: Path | None = None, owner: str | None = None) -> Path:
    root = root.resolve()
    all_files = scan_files(root)

    detected_ids = detect_providers(root)
    out_dir = out_dir.resolve() if out_dir else resolve_owner(root, detected_ids, owner)
    dashboard = (out_dir / "dashboard.html").resolve()

    files = [f for f in all_files if f.resolve() != dashboard]
    ctx = ScanContext(root=root, files=files)

    parts: list[dict] = []
    provider_summaries: list[dict] = []
    for adapter_cls in _FIRST_CLASS:
        adapter = adapter_cls()
        roots = adapter.detect(ctx)
        if not roots:
            continue
        part = adapter.normalize(ctx, roots[0])
        parts.append(part)
        provider_summaries.append(part["provider"])

    # generic indexes only the markdown not claimed by a provider folder/marker
    unclaimed = [f for f in files if not _claimed_by_provider(rel_posix(f, root))]
    gctx = ScanContext(root=root, files=unclaimed)
    gadapter = GenericAdapter()
    gpart = gadapter.normalize(gctx, gadapter.detect(gctx)[0])
    parts.append(gpart)
    provider_summaries.append({"id": "generic", "displayName": "Generic",
                               "root": ".", "detected": True})

    inv, docs = _merge_parts(parts)
    _escape_summaries(inv, docs)        # escape plain-text summaries for the island
    search = _build_search(inv, docs)   # search reads escaped summaries (Phase 1 contract)

    out_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "schemaVersion": SCHEMA_VERSION,
        "generator": {"name": "ai-control-center", "version": __version__, "rendererDigest": ""},
        "source": {
            "repoName": root.name,
            "dashboardPath": (
                dashboard.relative_to(root).as_posix()
                if dashboard.is_relative_to(root) else str(dashboard)
            ),
            "sourceDigest": source_digest(files, root),
            "vcs": {"kind": "none"},
        },
        "providers": provider_summaries,
        "project": gpart["project"],
        "inventory": inv,
        "docs": docs,
        "relationships": [],
        "search": search,
    }
    validate(data)
    dashboard.write_text(render_html(data), encoding="utf-8")
    return dashboard
```

Add the `rel_posix` import at the top (used by `_claimed_by_provider`):

```python
from .ids import rel_posix
```

Remove the now-unused `_escape_plain_text_fields` and the old `_build_search(part)` (single-arg) definitions; the new `_build_search(inv, docs)` and `_escape_summaries` replace them.

> Note: summaries are HTML-escaped before the search index is built, so no raw markup (e.g. `<img onerror=...>`) reaches the data island via `search[].text`. This preserves Phase 1's XSS guarantee (`test_generate_escapes_hostile_markdown`). The cosmetic "`search[].text` holds escaped entities" item stays deferred — `app.js` never reads `data.search`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_generate.py -v`
Expected: PASS (all existing Phase 1 tests + the new multi-provider tests)

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS (all green)

- [ ] **Step 6: Commit**

```bash
git add src/acc/generate.py tests/test_generate.py
git commit -m "feat: multi-provider detect/claim/merge in generate pipeline"
```

---

## Task 11: CLI `--owner`, ambiguity handling, and final verification

**Files:**
- Modify: `src/acc/cli.py`
- Test: covered by `tests/test_owner_rule.py` (resolve_owner) and a CLI smoke run

- [ ] **Step 1: Modify `src/acc/cli.py`**

Replace the file with:

```python
import argparse
import sys
from pathlib import Path

from .generate import generate, OwnerAmbiguousError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="acc", description="Generate the AI control center dashboard")
    parser.add_argument("--root", default=".", help="repo root to scan")
    parser.add_argument("--out", default=None, help="output directory (default: auto-detect provider folder)")
    parser.add_argument("--owner", default=None,
                        help="provider folder to own the dashboard when more than one exists")
    args = parser.parse_args(argv)
    out_dir = Path(args.out) if args.out else None
    try:
        dashboard = generate(Path(args.root), out_dir, owner=args.owner)
    except OwnerAmbiguousError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"wrote {dashboard}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify the CLI entry behaves**

Run: `python -m pytest -q`
Expected: PASS (whole suite green; `main` now returns an int — no test asserts the old `None` return)

- [ ] **Step 3: Smoke-test the CLI on a multi-provider temp repo**

Run:
```bash
python - <<'PY'
import tempfile, pathlib, sys
sys.path.insert(0, "tests")
from builders import make_multi_provider_repo
d = pathlib.Path(tempfile.mkdtemp())
make_multi_provider_repo(d)
from importlib import import_module
sys.path.insert(0, "src")
cli = import_module("acc.cli")
rc = cli.main(["--root", str(d)])
print("rc", rc)
print((d / ".claude" / "dashboard.html").read_text()[:120])
PY
```
Expected: prints `wrote .../.claude/dashboard.html`, `rc 0`, and the start of a valid HTML document.

- [ ] **Step 4: Smoke-test the ambiguity path**

Run:
```bash
python - <<'PY'
import tempfile, pathlib, sys
sys.path.insert(0, "src")
from importlib import import_module
cli = import_module("acc.cli")
d = pathlib.Path(tempfile.mkdtemp())
for prov in (".claude", ".codex"):
    (d / prov).mkdir()
    (d / prov / "dashboard.html").write_text("<html>")
rc = cli.main(["--root", str(d)])
print("rc", rc)   # expect 2
PY
```
Expected: prints an `error: multiple dashboards found ...` line and `rc 2`.

- [ ] **Step 5: Run the CLI on this repo itself (real Codex + Claude fixture)**

Run: `python -m acc.cli --root . --out /tmp/acc-phase2 && head -c 200 /tmp/acc-phase2/dashboard.html`
Expected: `wrote /tmp/acc-phase2/dashboard.html`; the island lists this repo's `.codex/config.toml` MCP (none active), `AGENTS.md`, and the docs index, with no secrets.

- [ ] **Step 6: Commit**

```bash
git add src/acc/cli.py
git commit -m "feat: CLI --owner flag and ambiguous-owner exit code"
```

---

## Self-review notes

- **Spec coverage (Phase 2):** frontmatter parser (Task 1), safe config loaders + MCP allowlist (Task 2), shape helpers (Task 3), hybrid builders (Task 4), Claude/Codex/Cursor adapters with native labels + inventory parity (Tasks 5-7), `assert_no_secrets` tripwire (Task 8), detection + owner rule with precedence/override/ambiguity (Task 9), file-claiming merge + providers[] + determinism + no-double-list (Task 10), `--owner` CLI (Task 11). Data-only — no renderer changes, matching the locked decision.
- **Naming consistency:** `parse_frontmatter`, `load_json`, `load_toml`, `safe_mcp`, `MCP_ALLOWED`, `make_item`, `empty_inventory`, `empty_docs`, `ClaudeAdapter`/`CodexAdapter`/`CursorAdapter`, `detect_providers`, `resolve_owner`, `OwnerAmbiguousError`, `_claimed_by_provider`, `_merge_parts`, `_build_search`, `_escape_summaries` are used identically across tasks. Item shape `{id, provider, type, typeLabel, title, path, summary}` and doc shape `{id, title, path, summary, html}` are consistent.
- **Backward compatibility:** `detect_out_dir` is kept as a wrapper over `resolve_owner`, so Phase 1's `test_detect_out_dir_*` and `test_generate_includes_provider_folder_markdown` stay green. `assert_no_secrets` does not fire on the existing hostile-markdown test (`onerror` is not a secret keyword).
- **Redaction paths:** MCP config -> `safe_mcp` allowlist (drops env/headers); frontmatter text and hook commands -> `redact_text`; `assert_no_secrets` is the backstop over the serialized output.
- **No placeholders:** every code step contains complete, runnable code.

## What Phase 2 leaves for later

The full layout-B renderer (bento Overview, Inventory badges, relationship-list Map, client search over the new inventory) and the size budget are Phase 3. The three-tier refresh and skill/plugin packaging are Phase 4. Loose non-structured markdown inside a provider folder (e.g. a stray `.claude/notes.md` no adapter inventories) is intentionally not surfaced in v1.
