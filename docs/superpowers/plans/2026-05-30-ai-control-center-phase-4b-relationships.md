# Phase 4b — Relationships Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Populate the empty `relationships: []` with deterministic `reference` (doc→item path mention) and `declares` (config-file→MCP/hook) edges, and render them as inline "Related" blocks plus a "Cross-references" view.

**Architecture:** A new `generate._build_relationships(inv, docs)` emits a sorted, deduped edge list after the search index is built; docs carry a private `_refScanBody` (redacted body, dropped before serialization) for the reference scan; `declares` edges are sourced from synthetic config-file nodes. `schema._validate_relationships` enforces shape + type-aware referential integrity. `app.js` builds an adjacency index and renders Related blocks (non-indexed jump controls) and a source-grouped Cross-references view.

**Tech Stack:** Python 3.12 stdlib (generator), vanilla JS (renderer in a JSON island), pytest + pytest-playwright (real-Chromium DOM tests), ruff.

**Spec:** `docs/specs/phase-4b-relationships.md` (final at commit `1b7333c`).

**Conventions for every task:** stdlib only; deterministic output (sort every list); renderer is `textContent`/`createElement` only — never `innerHTML`; run from the repo root with `python3 -m pytest`. New relationship tests live in `tests/test_relationships.py` unless noted.

---

### Task 1: Adapters carry `_refScanBody` on every doc

**Files:**
- Modify: `src/acc/adapters/claude.py:82-91` (the `doc` branch)
- Modify: `src/acc/adapters/codex.py:55-61` (the `AGENTS.md` branch)
- Modify: `src/acc/adapters/generic.py:114-120` (the doc append)
- Test: `tests/test_relationships.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_relationships.py
from acc.adapters.base import ScanContext
from acc.adapters.claude import ClaudeAdapter
from tests.builders import make_claude_repo


def _claude_docs(tmp_path):
    make_claude_repo(tmp_path)
    files = list(tmp_path.rglob("*"))
    ctx = ScanContext(root=tmp_path, files=[f for f in files if f.is_file()])
    adapter = ClaudeAdapter()
    part = adapter.normalize(ctx, adapter.detect(ctx)[0])
    return part["docs"]["references"]


def test_claude_doc_carries_refscanbody(tmp_path):
    docs = _claude_docs(tmp_path)
    claude_md = next(d for d in docs if d["path"] == "CLAUDE.md")
    assert "_refScanBody" in claude_md
    assert "Project memory and rules." in claude_md["_refScanBody"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_relationships.py::test_claude_doc_carries_refscanbody -v`
Expected: FAIL with `KeyError`/`assert '_refScanBody' in ...` (the key is absent).

- [ ] **Step 3: Add `_refScanBody = clean` in all three doc builders**

In `src/acc/adapters/claude.py`, the `else` (doc) branch currently appends:

```python
            else:  # "doc" — CLAUDE.md at root or nested under .claude/
                clean, _ = redact_text(raw)
                heading = _first_heading(clean) or rel
                docs["references"].append({
                    "id": make_item("claude", "doc", "Claude instructions", heading, rel, "")["id"],
                    "title": heading,
                    "path": rel,
                    "summary": _first_paragraph(clean),
                    "html": render_markdown_safe(clean),
                    "_refScanBody": clean,
                })
```

In `src/acc/adapters/codex.py`, the `AGENTS.md` branch:

```python
                docs["references"].append({
                    "id": make_item("codex", "doc", "Codex instructions", heading, rel, "")["id"],
                    "title": heading,
                    "path": rel,
                    "summary": _first_paragraph(clean),
                    "html": render_markdown_safe(clean),
                    "_refScanBody": clean,
                })
```

In `src/acc/adapters/generic.py`, the doc append in `normalize`:

```python
            docs.append({
                "id": stable_id("generic", "doc", rel, heading),
                "title": heading,
                "path": rel,
                "summary": _first_paragraph(clean),
                "html": render_markdown_safe(clean),
                "_refScanBody": clean,
            })
```

- [ ] **Step 4: Add codex + generic coverage to the test, run to verify it passes**

```python
# append to tests/test_relationships.py
from acc.adapters.codex import CodexAdapter
from acc.adapters.generic import GenericAdapter
from tests.builders import make_codex_repo, make_brownfield_repo


def test_codex_and_generic_docs_carry_refscanbody(tmp_path):
    make_codex_repo(tmp_path)
    make_brownfield_repo(tmp_path)
    files = [f for f in tmp_path.rglob("*") if f.is_file()]
    ctx = ScanContext(root=tmp_path, files=files)
    cod = CodexAdapter().normalize(ctx, CodexAdapter().detect(ctx)[0])
    agents = next(d for d in cod["docs"]["references"] if d["path"] == "AGENTS.md")
    assert "Guide." in agents["_refScanBody"]
    gen = GenericAdapter().normalize(ctx, GenericAdapter().detect(ctx)[0])
    assert all("_refScanBody" in d for d in gen["docs"]["references"])
```

Run: `python3 -m pytest tests/test_relationships.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add src/acc/adapters/claude.py src/acc/adapters/codex.py src/acc/adapters/generic.py tests/test_relationships.py
git commit -m "feat(phase-4b): carry redacted _refScanBody on docs for the reference scan"
```

---

### Task 2: `_build_relationships` — reference pass

**Files:**
- Modify: `src/acc/generate.py` (add `_CONFIG_PATHS`, `_build_relationships`; extend the `.ids` import)
- Test: `tests/test_relationships.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_relationships.py
from acc.generate import _build_relationships
from acc.adapters.base import make_item, empty_inventory, empty_docs


def _doc(doc_id, path, body):
    return {"id": doc_id, "title": path, "path": path, "summary": "",
            "html": "", "_refScanBody": body}


def test_reference_edge_from_doc_body_path_mention():
    agent = make_item("claude", "agent", "Claude agent", "reviewer",
                      ".claude/agents/reviewer.md", "")
    inv = empty_inventory()
    inv["agents"].append(agent)
    docs = empty_docs()
    docs["references"].append(
        _doc("docid", "CLAUDE.md", "See .claude/agents/reviewer.md for review rules."))
    edges = _build_relationships(inv, docs)
    refs = [e for e in edges if e["type"] == "reference"]
    assert refs == [{"from": "docid", "to": agent["id"], "type": "reference",
                     "evidence": ".claude/agents/reviewer.md"}]


def test_reference_dedup_and_boundary_and_unique():
    a1 = make_item("claude", "agent", "Claude agent", "x", ".claude/agents/x.md", "")
    inv = empty_inventory()
    inv["agents"].append(a1)
    docs = empty_docs()
    # path appears twice (dedup to 1) and once as a .bak prefix (boundary: no match)
    docs["references"].append(_doc(
        "d", "CLAUDE.md",
        ".claude/agents/x.md and again .claude/agents/x.md but not .claude/agents/x.md.bak"))
    refs = [e for e in _build_relationships(inv, docs) if e["type"] == "reference"]
    assert len(refs) == 1 and refs[0]["to"] == a1["id"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_relationships.py::test_reference_edge_from_doc_body_path_mention -v`
Expected: FAIL with `ImportError: cannot import name '_build_relationships'`.

- [ ] **Step 3: Add the constant, the import, and the reference pass**

In `src/acc/generate.py`, extend the ids import:

```python
from .ids import rel_posix, stable_id
```

Add `import re` near the top imports, and a module constant near the other constants:

```python
# The provider config files that declare MCP servers and hooks. They are the
# `declares` channel, so they are never `reference` targets — otherwise a
# single-server config (one id, unique path) would draw a stray reference edge.
_CONFIG_PATHS = frozenset({
    ".claude/settings.json", ".mcp.json", ".codex/config.toml", ".cursor/mcp.json",
})
```

Add the builder (reference pass only for now; `declares` lands in Task 3):

```python
def _build_relationships(inv: dict, docs: dict) -> list[dict]:
    """Deterministic edges over the merged inventory + docs.

    `reference`: a doc body mentions an inventory item's exact, unique,
    boundary-delimited repo-relative path. `declares` (Task 3): a config-file
    node -> the MCP servers / hooks it declares.
    """
    edges: list[dict] = []

    # reference pass: path -> set(ids) over inventory items only, keep unique
    # paths that are not a provider config file.
    path_ids: dict[str, set[str]] = {}
    for items in inv.values():
        for it in items:
            path_ids.setdefault(it["path"], set()).add(it["id"])
    unique = {p: next(iter(ids)) for p, ids in path_ids.items()
              if len(ids) == 1 and p not in _CONFIG_PATHS}
    # boundary match: reject a hit that is part of a longer path/word token
    matchers = {p: re.compile(r"(?<![\w./-])" + re.escape(p) + r"(?![\w./-])")
                for p in unique}
    for bucket in docs.values():
        for doc in bucket:
            body = doc.get("_refScanBody", "")
            if not body:
                continue
            for path, item_id in unique.items():
                if item_id == doc["id"]:
                    continue  # self-edge guard
                if matchers[path].search(body):
                    edges.append({"from": doc["id"], "to": item_id,
                                  "type": "reference", "evidence": path})

    return _dedup_sort_edges(edges)


def _dedup_sort_edges(edges: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for e in edges:
        key = (e["from"], e["to"], e["type"])
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    out.sort(key=lambda e: (e["from"], e["to"], e["type"]))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_relationships.py -v`
Expected: PASS (both new reference tests, plus the Task 1 tests).

- [ ] **Step 5: Commit**

```bash
git add src/acc/generate.py tests/test_relationships.py
git commit -m "feat(phase-4b): _build_relationships reference pass (unique boundary path match)"
```

---

### Task 3: `_build_relationships` — `declares` pass (config-file nodes)

**Files:**
- Modify: `src/acc/generate.py` (`_build_relationships`)
- Test: `tests/test_relationships.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_relationships.py
from acc.ids import stable_id


def test_declares_edges_from_config_file_nodes():
    inv = empty_inventory()
    hook = make_item("claude", "hook", "Claude hook", "PreToolUse (Bash)",
                     ".claude/settings.json", "echo hi")
    mcp1 = make_item("claude", "mcpServer", "MCP server", "local",
                     ".claude/settings.json", "node")
    mcp2 = make_item("cursor", "mcpServer", "MCP server", "figma",
                     ".cursor/mcp.json", "")
    inv["hooks"].append(hook)
    inv["mcpServers"].extend([mcp1, mcp2])
    edges = _build_relationships(inv, empty_docs())
    declares = [e for e in edges if e["type"] == "declares"]
    settings_node = stable_id("config", "configFile", ".claude/settings.json", "")
    cursor_node = stable_id("config", "configFile", ".cursor/mcp.json", "")
    assert {(e["from"], e["to"], e["evidence"]) for e in declares} == {
        (settings_node, hook["id"], ".claude/settings.json"),
        (settings_node, mcp1["id"], ".claude/settings.json"),
        (cursor_node, mcp2["id"], ".cursor/mcp.json"),
    }


def test_declares_excludes_commands():
    inv = empty_inventory()
    inv["commands"].append(make_item("claude", "command", "Claude command",
                                     "ship", ".claude/commands/ship.md", ""))
    declares = [e for e in _build_relationships(inv, empty_docs())
                if e["type"] == "declares"]
    assert declares == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_relationships.py::test_declares_edges_from_config_file_nodes -v`
Expected: FAIL (`assert set() == {...}` — no declares edges yet).

- [ ] **Step 3: Add the `declares` pass before `return _dedup_sort_edges(edges)`**

```python
    # declares pass: config-file node -> each MCP server / hook it declares.
    # Commands are file-discovered, not config-declared, so they are excluded.
    config_items: dict[str, list[str]] = {}
    for kind in ("mcpServers", "hooks"):
        for it in inv.get(kind, []):
            config_items.setdefault(it["path"], []).append(it["id"])
    for config_path, item_ids in config_items.items():
        node_id = stable_id("config", "configFile", config_path, "")
        for item_id in item_ids:
            edges.append({"from": node_id, "to": item_id,
                          "type": "declares", "evidence": config_path})

    return _dedup_sort_edges(edges)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_relationships.py -v`
Expected: PASS (all relationship tests).

- [ ] **Step 5: Commit**

```bash
git add src/acc/generate.py tests/test_relationships.py
git commit -m "feat(phase-4b): _build_relationships declares pass (config-file source nodes)"
```

---

### Task 4: Wire `relationships` into `generate()` with the pinned pop order

**Files:**
- Modify: `src/acc/generate.py:266-295` (search build, private-field pop, data assembly)
- Test: `tests/test_relationships.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_relationships.py
import json
from acc.generate import generate
from tests.builders import make_multi_provider_repo


def _island(html: str) -> dict:
    start = html.index('<script id="acc-data" type="application/json">') + \
        len('<script id="acc-data" type="application/json">')
    end = html.index("</script>", start)
    return json.loads(html[start:end])


def test_generate_populates_relationships_and_drops_private_fields(tmp_path):
    make_multi_provider_repo(tmp_path)
    # add a doc that references an inventory item by path
    (tmp_path / "docs" / "links.md").write_text(
        "# Links\n\nUses .claude/agents/reviewer.md and the figma server.")
    html = generate(tmp_path).read_text(encoding="utf-8")
    assert "_refScanBody" not in html and "_rawBody" not in html
    data = _island(html)
    assert isinstance(data["relationships"], list) and data["relationships"]
    kinds = {e["type"] for e in data["relationships"]}
    assert kinds <= {"reference", "declares"}
    # the links.md doc references the reviewer agent
    assert any(e["type"] == "reference" and e["evidence"] == ".claude/agents/reviewer.md"
               for e in data["relationships"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_relationships.py::test_generate_populates_relationships_and_drops_private_fields -v`
Expected: FAIL (`data["relationships"]` is `[]`, so the truthiness assert fails).

- [ ] **Step 3: Wire the builder and extend the pop loop**

In `src/acc/generate.py`, replace the block at lines 266-271:

```python
    search = _build_search(inv, docs, project["openTodos"])  # reads the escaped fields (Phase 1 contract)
    relationships = _build_relationships(inv, docs)  # reads docs' _refScanBody
    # Drop the private slice keys so they never reach the serialized island.
    # Order is load-bearing: _build_relationships must read _refScanBody first.
    for bucket in (inv, docs):
        for items in bucket.values():
            for it in items:
                it.pop("_searchBody", None)
                it.pop("_refScanBody", None)
```

And change the `data` assembly (line ~293) from `"relationships": [],` to:

```python
        "relationships": relationships,
```

- [ ] **Step 4: Run the test + the full suite to verify**

Run: `python3 -m pytest tests/test_relationships.py::test_generate_populates_relationships_and_drops_private_fields -v && python3 -m pytest -q`
Expected: PASS; full suite still green (relationships was `[]` before, now populated — existing tests do not assert it empty).

- [ ] **Step 5: Commit**

```bash
git add src/acc/generate.py tests/test_relationships.py
git commit -m "feat(phase-4b): wire relationships into the island; pop _refScanBody before serialize"
```

---

### Task 5: Schema validation for relationships

**Files:**
- Modify: `src/acc/schema.py` (add `_validate_relationships`, call from `validate`, import `stable_id`)
- Test: `tests/test_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_schema.py
import pytest
from acc.schema import validate
from acc.ids import stable_id


def _base_data(relationships):
    item_id = stable_id("claude", "mcpServer", ".claude/settings.json", "local")
    doc_id = stable_id("claude", "doc", "CLAUDE.md", "My Project")
    inv = {"agents": [], "skills": [], "hooks": [], "commands": [],
           "mcpServers": [{"id": item_id, "provider": "claude", "type": "mcpServer",
                           "typeLabel": "MCP server", "title": "local",
                           "path": ".claude/settings.json", "summary": "node",
                           "config": {}}],
           "rules": []}
    docs = {"prds": [], "adrs": [], "decisions": [], "workflows": [],
            "references": [{"id": doc_id, "title": "My Project", "path": "CLAUDE.md",
                            "summary": "", "html": ""}]}
    return {
        "schemaVersion": "1.0",
        "generator": {"name": "x", "version": "0", "rendererDigest": "", "truncated": False},
        "source": {"repoName": "r", "pathPrefix": "..", "dashboardPath": "d",
                   "sourceDigest": "0", "vcs": {"kind": "none"}},
        "providers": [], "project": {"title": "", "openTodos": []},
        "inventory": inv, "docs": docs, "relationships": relationships, "search": [],
    }, item_id, doc_id


def test_valid_declares_and_reference_pass():
    data, item_id, doc_id = _base_data([])
    node = stable_id("config", "configFile", ".claude/settings.json", "")
    data["relationships"] = [
        {"from": node, "to": item_id, "type": "declares", "evidence": ".claude/settings.json"},
        {"from": doc_id, "to": item_id, "type": "reference", "evidence": ".claude/settings.json"},
    ]
    validate(data)  # no raise


@pytest.mark.parametrize("bad", [
    {"from": "nope", "to": "nope", "type": "reference", "evidence": "x"},   # dangling to
    {"from": "nope", "to": "__ITEM__", "type": "reference", "evidence": "x"},  # reference from not a doc
    {"from": "nope", "to": "__ITEM__", "type": "declares", "evidence": "x"},   # declares from not a config node
    {"from": "__DOC__", "to": "__ITEM__", "type": "owns", "evidence": "x"},    # unknown type
    {"from": "__DOC__", "to": "__ITEM__", "type": "reference", "evidence": 5}, # non-string field
])
def test_invalid_relationship_rejected(bad):
    data, item_id, doc_id = _base_data([])
    edge = {k: (item_id if v == "__ITEM__" else doc_id if v == "__DOC__" else v)
            for k, v in bad.items()}
    data["relationships"] = [edge]
    with pytest.raises(ValueError):
        validate(data)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_schema.py::test_valid_declares_and_reference_pass -v`
Expected: FAIL (`validate` does not yet check relationships, but the dangling-`to` reject test fails because nothing raises).

- [ ] **Step 3: Add `_validate_relationships` and call it from `validate`**

In `src/acc/schema.py`, add the import:

```python
from .ids import stable_id
```

Add the validator and constants:

```python
_REL_TYPES = {"reference", "declares"}
_REL_KEYS = ("from", "to", "type", "evidence")


def _validate_relationships(edges, item_ids: set, doc_ids: set, config_node_ids: set) -> None:
    if not isinstance(edges, list):
        raise ValueError("relationships must be a list")
    for i, e in enumerate(edges):
        if not isinstance(e, dict):
            raise ValueError(f"relationships[{i}] is not an object")
        for key in _REL_KEYS:
            if key not in e:
                raise ValueError(f"relationships[{i}] missing key: {key!r}")
            if not isinstance(e[key], str):
                raise ValueError(f"relationships[{i}].{key} must be a string")
        if e["type"] not in _REL_TYPES:
            raise ValueError(f"relationships[{i}] unknown type: {e['type']!r}")
        if e["to"] not in item_ids:
            raise ValueError(f"relationships[{i}] dangling 'to': {e['to']!r}")
        if e["type"] == "reference" and e["from"] not in doc_ids:
            raise ValueError(f"relationships[{i}] reference 'from' not a doc: {e['from']!r}")
        if e["type"] == "declares" and e["from"] not in config_node_ids:
            raise ValueError(f"relationships[{i}] declares 'from' not a config node: {e['from']!r}")
```

In `validate(data)`, after `_validate_search(data["search"])` and before `assert_no_secrets(data)`:

```python
    inv = data["inventory"]
    item_ids = {it["id"] for items in inv.values() for it in items}
    doc_ids = {d["id"] for bucket in data["docs"].values() for d in bucket}
    config_node_ids = {
        stable_id("config", "configFile", it["path"], "")
        for kind in ("mcpServers", "hooks") for it in inv.get(kind, [])
    }
    _validate_relationships(data["relationships"], item_ids, doc_ids, config_node_ids)
```

- [ ] **Step 4: Run the schema tests + full suite**

Run: `python3 -m pytest tests/test_schema.py tests/test_relationships.py -q && python3 -m pytest -q`
Expected: PASS (valid edges accepted; each malformed edge rejected; full suite green — `generate()` output validates because `_build_relationships` only emits well-formed edges).

- [ ] **Step 5: Commit**

```bash
git add src/acc/schema.py tests/test_schema.py
git commit -m "feat(phase-4b): schema validation + type-aware referential integrity for relationships"
```

---

### Task 6: Degraded-mode relationship cap in `_reduce_for_size`

**Files:**
- Modify: `src/acc/generate.py` (`_reduce_for_size`, add `_MAX_DEGRADED_REFERENCE_EDGES`)
- Test: `tests/test_generate.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_generate.py
from acc.generate import _reduce_for_size, _MAX_DEGRADED_REFERENCE_EDGES


def test_reduce_keeps_declares_caps_references():
    refs = [{"from": f"d{i:04d}", "to": f"t{i:04d}", "type": "reference", "evidence": "p"}
            for i in range(_MAX_DEGRADED_REFERENCE_EDGES + 50)]
    decl = [{"from": "c", "to": f"m{i}", "type": "declares", "evidence": "cfg"}
            for i in range(10)]
    data = {
        "inventory": {"agents": [], "skills": [], "hooks": [], "commands": [],
                      "mcpServers": [], "rules": []},
        "docs": {"references": [], "prds": [], "adrs": [], "decisions": [], "workflows": []},
        "search": [], "generator": {"truncated": False},
        "relationships": decl + refs,
    }
    reduced = _reduce_for_size(data)
    kept = reduced["relationships"]
    assert sum(1 for e in kept if e["type"] == "declares") == 10
    assert sum(1 for e in kept if e["type"] == "reference") == _MAX_DEGRADED_REFERENCE_EDGES
    # deterministic: sorted by (from, to, type)
    assert kept == sorted(kept, key=lambda e: (e["from"], e["to"], e["type"]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_generate.py::test_reduce_keeps_declares_caps_references -v`
Expected: FAIL with `ImportError` (`_MAX_DEGRADED_REFERENCE_EDGES` not defined).

- [ ] **Step 3: Add the constant and the cap in `_reduce_for_size`**

In `src/acc/generate.py`, add near the other module constants:

```python
# Degraded mode keeps all `declares` edges (bounded by MCP+hook count) but caps
# `reference` edges, which are unbounded in the worst case, to a deterministic prefix.
_MAX_DEGRADED_REFERENCE_EDGES = 200
```

In `_reduce_for_size`, before `reduced["generator"]["truncated"] = True`:

```python
    declares = [e for e in reduced["relationships"] if e["type"] == "declares"]
    refs = [e for e in reduced["relationships"] if e["type"] == "reference"]
    if len(refs) > _MAX_DEGRADED_REFERENCE_EDGES:
        logger.warning("degraded mode: capping %d reference edges to %d",
                       len(refs), _MAX_DEGRADED_REFERENCE_EDGES)
        refs = refs[:_MAX_DEGRADED_REFERENCE_EDGES]
    reduced["relationships"] = sorted(
        declares + refs, key=lambda e: (e["from"], e["to"], e["type"]))
```

- [ ] **Step 4: Run the test + full suite**

Run: `python3 -m pytest tests/test_generate.py::test_reduce_keeps_declares_caps_references -v && python3 -m pytest -q`
Expected: PASS; full suite green.

- [ ] **Step 5: Commit**

```bash
git add src/acc/generate.py tests/test_generate.py
git commit -m "feat(phase-4b): cap reference edges in degraded mode, keep all declares"
```

---

### Task 7: Template — `#crossref` section and nav anchor

**Files:**
- Modify: `src/acc/templates/dashboard.html.tmpl:20-30`
- Test: `tests/test_render.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_render.py
from acc.generate import generate
from tests.builders import make_multi_provider_repo


def test_template_has_crossref_section_and_nav(tmp_path):
    make_multi_provider_repo(tmp_path)
    html = generate(tmp_path).read_text(encoding="utf-8")
    assert 'id="crossref"' in html
    assert 'id="acc-crossref"' in html
    assert '<a href="#crossref">Cross-references</a>' in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_render.py::test_template_has_crossref_section_and_nav -v`
Expected: FAIL (`id="crossref"` absent).

- [ ] **Step 3: Add the nav anchor and the section**

In `src/acc/templates/dashboard.html.tmpl`, add to the `<nav>` after the TODOs link:

```html
  <a href="#todos">TODOs</a>
  <a href="#crossref">Cross-references</a>
</nav>
```

And add the section after the `todos` section:

```html
<section id="todos"><div class="acc-label">Open TODOs</div><div id="acc-todos"></div></section>
<section id="crossref"><div class="acc-label">Cross-references</div><div id="acc-crossref"></div></section>
```

- [ ] **Step 4: Run the test + `node --check`**

Run: `python3 -m pytest tests/test_render.py::test_template_has_crossref_section_and_nav -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/acc/templates/dashboard.html.tmpl tests/test_render.py
git commit -m "feat(phase-4b): add #crossref section + nav anchor to the template"
```

---

### Task 8: `app.js` — edge/label indexes + inline "Related" blocks

**Files:**
- Modify: `src/acc/templates/app.js` (add `metaById`, `edgesByEndpoint`, `decorateRelated`; wire into init)
- Test: `tests/test_render_dom.py`

- [ ] **Step 1: Write the failing DOM test**

```python
# append to tests/test_render_dom.py
def test_inline_related_is_bidirectional_and_jumps(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    (tmp_path / "docs" / "links.md").write_text(
        "# Links\n\nThe .claude/agents/reviewer.md agent handles reviews.")
    page.set_content(_html(tmp_path))
    # the reviewer agent row shows a "referenced by" related entry
    agent_row = page.locator('.acc-item', has_text="reviewer").first
    rel = agent_row.locator('.acc-related')
    assert rel.count() == 1
    assert rel.locator('button', has_text="referenced by").count() >= 1
    # related controls are not indexable rows
    assert agent_row.locator('.acc-related .acc-item').count() == 0
    assert agent_row.locator('.acc-related [data-id]').count() == 0
    # a declares label appears on an MCP server row, as text (not a jump button)
    mcp_row = page.locator('#acc-inventory .acc-item', has_text="local").first
    assert mcp_row.locator('.acc-related', has_text="declared in").count() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_render_dom.py::test_inline_related_is_bidirectional_and_jumps -v`
Expected: FAIL (`.acc-related` count is 0).

- [ ] **Step 3: Add the indexes and the Related decorator to `app.js`**

In `src/acc/templates/app.js`, after the `rowById` declaration and `buildRowIndex`/`jumpTo`, add:

```javascript
  var metaById = {};
  function buildMeta() {
    var inv = data.inventory || {};
    Object.keys(inv).forEach(function (b) {
      (inv[b] || []).forEach(function (it) {
        metaById[it.id] = { title: it.title, typeLabel: it.typeLabel, path: it.path };
      });
    });
    var docs = data.docs || {};
    Object.keys(docs).forEach(function (g) {
      (docs[g] || []).forEach(function (d) {
        metaById[d.id] = { title: d.title, typeLabel: g, path: d.path };
      });
    });
    (data.project.openTodos || []).forEach(function (t) {
      metaById[t.id] = { title: t.text, typeLabel: "TODO", path: t.path };
    });
  }

  // id -> [{otherId, dir, type, evidence}]; "out" on the from side, "in" on the to side.
  var edgesByEndpoint = {};
  function buildEdgeIndex() {
    (data.relationships || []).forEach(function (e) {
      (edgesByEndpoint[e.from] || (edgesByEndpoint[e.from] = []))
        .push({ otherId: e.to, dir: "out", type: e.type, evidence: e.evidence });
      (edgesByEndpoint[e.to] || (edgesByEndpoint[e.to] = []))
        .push({ otherId: e.from, dir: "in", type: e.type, evidence: e.evidence });
    });
  }

  var REL_VERB = {
    "reference|out": "references", "reference|in": "referenced by",
    "declares|out": "declares", "declares|in": "declared in"
  };

  function relatedEntry(edge) {
    var verb = REL_VERB[edge.type + "|" + edge.dir] || edge.type;
    var meta = metaById[edge.otherId];
    // declares-in: the source is a config-file node (no row) -> render a label.
    if (edge.type === "declares" && edge.dir === "in") {
      var label = el("span", "acc-rel-line");
      label.appendChild(el("span", "acc-rel-verb", verb));
      label.appendChild(el("span", "path", edge.evidence));
      return label;
    }
    if (!meta) return null; // endpoint has no canonical row (defensive)
    var btn = el("button", "acc-rel-line");
    btn.type = "button";
    btn.appendChild(el("span", "acc-rel-verb", verb));
    btn.appendChild(el("span", "acc-chip", meta.typeLabel));
    btn.appendChild(el("span", "acc-rel-title", htmlUnescape(meta.title)));
    btn.addEventListener("click", function () { jumpTo(edge.otherId); });
    return btn;
  }

  function decorateRelated() {
    rowById.forEach(function (row, id) {
      var edges = edgesByEndpoint[id];
      if (!edges || !edges.length) return;
      var box = el("div", "acc-related");
      edges.forEach(function (e) {
        var node = relatedEntry(e);
        if (node) box.appendChild(node);
      });
      if (box.children.length) row.appendChild(box);
    });
  }
```

Update the init block at the bottom — add `buildMeta()` and `buildEdgeIndex()` before the render passes, and `decorateRelated()` after `buildRowIndex()`:

```javascript
  buildMeta();
  buildEdgeIndex();
  renderHead();
  renderBanner();
  renderOverview();
  renderInventory();
  renderDocs();
  renderTodos();
  buildRowIndex();
  decorateRelated();
  wireOmnibox();
  wireSearch();
```

- [ ] **Step 4: Run the DOM test + `node --check` + the innerHTML guard**

Run: `node --check src/acc/templates/app.js && python3 -m pytest tests/test_render_dom.py::test_inline_related_is_bidirectional_and_jumps tests/test_appjs_guard.py -v`
Expected: PASS; the guard confirms no `innerHTML`/`outerHTML`/`insertAdjacentHTML`.

- [ ] **Step 5: Commit**

```bash
git add src/acc/templates/app.js tests/test_render_dom.py
git commit -m "feat(phase-4b): inline Related blocks (non-indexed controls, bidirectional verbs)"
```

---

### Task 9: `app.js` — `renderCrossReferences` + Overview card

**Files:**
- Modify: `src/acc/templates/app.js` (add `renderCrossReferences`; call it in init; add an Overview card)
- Test: `tests/test_render_dom.py`

- [ ] **Step 1: Write the failing DOM test**

```python
# append to tests/test_render_dom.py
def test_crossref_view_grouped_by_source_and_sorted(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    (tmp_path / "docs" / "links.md").write_text(
        "# Links\n\nSee .claude/agents/reviewer.md.")
    page.set_content(_html(tmp_path))
    cross = page.locator("#acc-crossref")
    # config-file sources appear as group headers labeled by their path
    assert cross.locator(".acc-xref-source", has_text=".claude/settings.json").count() == 1
    assert cross.locator(".acc-xref-source", has_text=".cursor/mcp.json").count() == 1
    # a doc source group exists and its endpoint jumps to the canonical row
    src_headers = cross.locator(".acc-xref-source")
    texts = [src_headers.nth(i).inner_text() for i in range(src_headers.count())]
    assert texts == sorted(texts)  # display-sorted by path/title
    cross.locator("button", has_text="reviewer").first.click()
    flashed = page.locator("#acc-inventory .acc-item.acc-flash", has_text="reviewer")
    assert flashed.count() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_render_dom.py::test_crossref_view_grouped_by_source_and_sorted -v`
Expected: FAIL (`#acc-crossref` is empty).

- [ ] **Step 3: Add `renderCrossReferences`, the Overview card, and wire init**

In `src/acc/templates/app.js`, add:

```javascript
  // Source label + sort key. Docs/items come from metaById; a config-file
  // source (declares `from`) has no metaById entry, so it is labeled by the
  // shared evidence path carried on its edges.
  function sourceLabel(fromId, sampleEdge) {
    var meta = metaById[fromId];
    if (meta) return { title: htmlUnescape(meta.title), type: meta.typeLabel, sort: meta.path || meta.title };
    return { title: sampleEdge.evidence, type: "config", sort: sampleEdge.evidence };
  }

  function renderCrossReferences() {
    var host = document.getElementById("acc-crossref");
    var edges = data.relationships || [];
    if (!edges.length) {
      host.appendChild(el("div", "acc-xref-empty", "No cross-references found"));
      return;
    }
    var bySource = {};
    edges.forEach(function (e) { (bySource[e.from] || (bySource[e.from] = [])).push(e); });
    var groups = Object.keys(bySource).map(function (fromId) {
      var list = bySource[fromId];
      var lbl = sourceLabel(fromId, list[0]);
      return { fromId: fromId, label: lbl, edges: list };
    });
    groups.sort(function (a, b) { return a.label.sort < b.label.sort ? -1 : a.label.sort > b.label.sort ? 1 : 0; });
    groups.forEach(function (g) {
      var head = el("div", "acc-xref-source");
      head.appendChild(el("span", "acc-chip", g.label.type));
      head.appendChild(el("span", "acc-xref-srctitle", g.label.title));
      host.appendChild(head);
      var targets = g.edges.map(function (e) {
        var m = metaById[e.to] || {};
        return { e: e, title: htmlUnescape(m.title || ""), type: m.typeLabel || "", sort: (m.path || m.title || "") };
      });
      targets.sort(function (a, b) { return a.sort < b.sort ? -1 : a.sort > b.sort ? 1 : 0; });
      targets.forEach(function (t) {
        var btn = el("button", "acc-xref-edge");
        btn.type = "button";
        btn.appendChild(el("span", "acc-rel-verb", t.e.type === "declares" ? "declares" : "references"));
        btn.appendChild(el("span", "acc-chip", t.type));
        btn.appendChild(el("span", "acc-rel-title", t.title));
        btn.appendChild(el("span", "path", t.e.evidence));
        btn.addEventListener("click", function () { jumpTo(t.e.to); });
        host.appendChild(btn);
      });
    });
  }
```

In `renderOverview`, after the docs card block, add a Cross-references card:

```javascript
    var rels = data.relationships || [];
    if (rels.length) {
      var xc = card("Cross-references", "crossref");
      xc.appendChild(el("div", null, plural(rels.length, "edges")));
      bento.appendChild(xc);
    }
```

In the init block, add `renderCrossReferences()` after `decorateRelated()`:

```javascript
  buildRowIndex();
  decorateRelated();
  renderCrossReferences();
  wireOmnibox();
  wireSearch();
```

- [ ] **Step 4: Run the DOM test + `node --check` + guard**

Run: `node --check src/acc/templates/app.js && python3 -m pytest tests/test_render_dom.py::test_crossref_view_grouped_by_source_and_sorted tests/test_appjs_guard.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/acc/templates/app.js tests/test_render_dom.py
git commit -m "feat(phase-4b): Cross-references view (source-grouped, path/title sort) + Overview card"
```

---

### Task 10: `styles.css` — Related + Cross-references styles

**Files:**
- Modify: `src/acc/templates/styles.css`
- Test: none (visual); verified via `node --check` of the app and the existing DOM suite.

- [ ] **Step 1: Add styles**

Append to `src/acc/templates/styles.css`:

```css
.acc-related { margin-top: .4rem; display: flex; flex-direction: column; gap: .15rem; }
.acc-rel-line { display: flex; align-items: center; gap: .4rem; background: none;
  border: 0; padding: .1rem 0; font: inherit; color: inherit; text-align: left; cursor: default; }
button.acc-rel-line { cursor: pointer; }
.acc-rel-verb { font-size: .72rem; text-transform: uppercase; letter-spacing: .03em; opacity: .6; min-width: 6.5rem; }
.acc-rel-title { font-weight: 500; }
#acc-crossref .acc-xref-source { margin-top: .8rem; display: flex; align-items: center; gap: .4rem; font-weight: 600; }
#acc-crossref .acc-xref-edge { display: flex; align-items: center; gap: .4rem; background: none;
  border: 0; padding: .12rem 0 .12rem 1.2rem; font: inherit; color: inherit; text-align: left; cursor: pointer; }
.acc-xref-empty { opacity: .6; }
```

- [ ] **Step 2: Verify the app still parses and the suite is green**

Run: `node --check src/acc/templates/app.js && python3 -m pytest tests/test_render_dom.py -q`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/acc/templates/styles.css
git commit -m "feat(phase-4b): styles for Related blocks and the Cross-references view"
```

---

### Task 11: Hardening DOM tests — degraded mode, redaction, config-path exclusion

**Files:**
- Test: `tests/test_render_dom.py`, `tests/test_relationships.py`

- [ ] **Step 1: Write the tests**

```python
# append to tests/test_relationships.py
def test_redaction_drops_keyword_prefixed_path(tmp_path):
    # leak.md is the ONLY mention of reviewer.md, and it sits behind a secret
    # keyword, so redact_text removes the path before the scan -> no edge.
    make_claude_repo(tmp_path)
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "leak.md").write_text(
        "# Leak\n\ntoken: .claude/agents/reviewer.md")
    data = _island(generate(tmp_path).read_text(encoding="utf-8"))
    assert not any(e["type"] == "reference" and e["evidence"] == ".claude/agents/reviewer.md"
                   for e in data["relationships"])


def test_config_path_not_a_reference_target(tmp_path):
    make_codex_repo(tmp_path)  # single mcpServer -> .codex/config.toml is a unique path
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "ref.md").write_text("# Ref\n\nconfigured in .codex/config.toml")
    data = _island(generate(tmp_path).read_text(encoding="utf-8"))
    # the doc mention of the config file must NOT create a reference edge
    assert not any(e["type"] == "reference" and e["evidence"] == ".codex/config.toml"
                   for e in data["relationships"])
    # but the config-file node still declares the codex MCP server
    assert any(e["type"] == "declares" and e["evidence"] == ".codex/config.toml"
               for e in data["relationships"])
```

```python
# append to tests/test_render_dom.py
def test_degraded_mode_keeps_declares_and_renders(page, tmp_path):
    # a repo large enough to trip the 2 MB truncate budget; declares edges are
    # bounded, so the Cross-references view still renders its source groups.
    make_multi_provider_repo(tmp_path)
    make_large_repo(tmp_path, 200)
    page.set_content(_html(tmp_path))
    assert page.locator("#acc-crossref .acc-xref-source").count() >= 1
```

- [ ] **Step 2: Run to verify they fail or pass appropriately**

Run: `python3 -m pytest tests/test_relationships.py -k "redaction or config_path" tests/test_render_dom.py::test_degraded_mode_keeps_declares_and_renders -v`
Expected: PASS (behavior implemented in Tasks 2-9; these lock it in). If `test_redaction_drops_keyword_prefixed_path` fails, confirm `_refScanBody` is the redacted body (Task 1) and the doc's edges are checked by source path.

- [ ] **Step 3: Commit**

```bash
git add tests/test_relationships.py tests/test_render_dom.py
git commit -m "test(phase-4b): redaction false-negative, config-path exclusion, degraded crossref"
```

---

### Task 12: Final verification

**Files:** none (verification only).

- [ ] **Step 1: Determinism — byte-identical repeated runs**

Add to `tests/test_relationships.py`:

```python
def test_relationships_byte_identical_across_runs(tmp_path):
    make_multi_provider_repo(tmp_path)
    (tmp_path / "docs" / "links.md").write_text("# L\n\n.claude/agents/reviewer.md")
    first = generate(tmp_path).read_text(encoding="utf-8")
    second = generate(tmp_path).read_text(encoding="utf-8")
    assert _island(first)["relationships"] == _island(second)["relationships"]
    assert first == second
```

Run: `python3 -m pytest tests/test_relationships.py::test_relationships_byte_identical_across_runs -v`
Expected: PASS.

- [ ] **Step 2: Full gate**

Run:
```bash
python3 -m pytest -q
ruff check .
node --check src/acc/templates/app.js
grep -nE 'innerHTML|outerHTML|insertAdjacentHTML' src/acc/templates/app.js && echo "SINKS (bad)" || echo "0 sinks"
```
Expected: all tests pass; ruff clean; `node --check` OK; `0 sinks`.

- [ ] **Step 3: Commit any test-only additions**

```bash
git add tests/test_relationships.py
git commit -m "test(phase-4b): relationships output is byte-identical across runs"
```

---

## Self-review (run before execution)

**Spec coverage:** reference pass (T2), declares/config-nodes (T3), `_refScanBody` lifecycle + pop order (T1, T4), schema integrity (T5), degraded cap (T6), template (T7), inline Related non-indexed controls (T8), Cross-references source-grouped + display sort + Overview card (T9), styles (T10), boundary/redaction/config-path/degraded tests (T11), determinism + guard (T12). All spec sections map to a task.

**Decisions honored:** path-only evidence (no snippet/escape machinery anywhere); inventory-only reference targets (path→id over `inv` only); config-file node `declares` (T3) covering cursor; commands excluded (T3 test); jump controls are `<button>` without `data-id`/`.acc-item` (T8 test asserts it); display sort by path/title not hash (T9 test).

**Type consistency:** `_build_relationships(inv, docs)`, `_dedup_sort_edges`, `_CONFIG_PATHS`, `_MAX_DEGRADED_REFERENCE_EDGES`, `stable_id("config", "configFile", path, "")`, edge keys `{from,to,type,evidence}`, JS `metaById`/`edgesByEndpoint`/`decorateRelated`/`renderCrossReferences` — names are consistent across tasks.

**Note for the executor:** `app.js` and `generate.py` are each touched by several tasks. Per the project's hard rule, dispatch implementers **serially** when files overlap; re-verify `git status` after each task.
