# Phase 3 renderer (Overview + Inventory) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the Phase 1/2 JSON island into a human-facing dashboard — a bento Overview and an Inventory view grouped by type with linked source paths — and add the output size budget.

**Architecture:** Extend the existing classic-IIFE renderer (`src/acc/templates/app.js`) with two new render functions and a shared `itemRow` builder; add `source.pathPrefix` and `generator.truncated` plus a render-then-measure size budget to `src/acc/generate.py`. No adapter changes. `textContent` everywhere; the one `href` is built by per-segment URL-encoding the combined relative path.

**Tech Stack:** Python 3.12 stdlib (generator), vanilla browser JS (renderer, no framework, file://-safe), `pytest` for contract tests, `pytest-playwright` (test-only) for DOM tests.

**Spec:** `docs/superpowers/specs/2026-05-30-ai-control-center-phase-3-renderer-design.md`

**Branch:** `feature/phase-3-renderer` (already created; the spec is committed there).

---

### Task 1: `source.pathPrefix` and `generator.truncated`

**Files:**
- Modify: `src/acc/generate.py` (imports near top; the `data` dict at `src/acc/generate.py:165-183`)
- Test: `tests/test_generate.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_generate.py`:

```python
import os
import acc.generate as gen


def test_pathprefix_is_dotdot_for_provider_owner(tmp_path):
    make_claude_repo(tmp_path)
    data = _island(generate(tmp_path))
    assert data["source"]["pathPrefix"] == ".."


def test_pathprefix_is_dot_when_out_is_root(tmp_path):
    make_claude_repo(tmp_path)
    data = _island(generate(tmp_path, out_dir=tmp_path))
    assert data["source"]["pathPrefix"] == "."


def test_pathprefix_for_nested_out_dir(tmp_path):
    make_claude_repo(tmp_path)
    data = _island(generate(tmp_path, out_dir=tmp_path / "a" / "b"))
    assert data["source"]["pathPrefix"] == "../.."


def test_pathprefix_empty_when_relpath_fails(tmp_path, monkeypatch):
    make_claude_repo(tmp_path)

    def boom(*a, **k):
        raise ValueError("different drive")

    monkeypatch.setattr(os.path, "relpath", boom)
    data = _island(generate(tmp_path))
    assert data["source"]["pathPrefix"] == ""


def test_generator_truncated_defaults_false(tmp_path):
    make_claude_repo(tmp_path)
    data = _island(generate(tmp_path))
    assert data["generator"]["truncated"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_generate.py -k "pathprefix or truncated" -q`
Expected: FAIL with `KeyError: 'pathPrefix'` / `KeyError: 'truncated'`.

- [ ] **Step 3: Implement**

At the top of `src/acc/generate.py`, ensure these imports exist (add what is missing):

```python
import os
```

Add this helper above `def generate(`:

```python
def _path_prefix(root: Path, out_dir: Path) -> str:
    """Posix relative path from the dashboard's dir back to the repo root.

    Normally "..", "." when out_dir == root, "../.." when nested. Returns ""
    when the path is not expressible (e.g. a different Windows drive), in which
    case the renderer falls back to plain-text paths instead of a broken href.
    """
    try:
        return Path(os.path.relpath(root, out_dir)).as_posix()
    except ValueError:
        return ""
```

In the `data` dict (`src/acc/generate.py:165-183`), change the `generator` line and add `pathPrefix` to `source`:

```python
        "generator": {"name": "ai-control-center", "version": __version__,
                      "rendererDigest": "", "truncated": False},
        "source": {
            "repoName": root.name,
            "pathPrefix": _path_prefix(root, out_dir),
            "dashboardPath": (
                dashboard.relative_to(root).as_posix()
                if dashboard.is_relative_to(root) else str(dashboard)
            ),
            "sourceDigest": source_digest(files, root),
            "vcs": {"kind": "none"},
        },
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_generate.py -q`
Expected: PASS (all, including the existing tests).

- [ ] **Step 5: Commit**

```bash
git add src/acc/generate.py tests/test_generate.py
git commit -m "feat(phase-3): add source.pathPrefix and generator.truncated"
```

---

### Task 2: Output size budget (warn + summary-only reducer)

**Files:**
- Modify: `src/acc/generate.py` (logging import; constants; `_reduce_for_size`; the render/write at `src/acc/generate.py:184-186`)
- Modify: `tests/builders.py` (add `make_large_repo`)
- Test: `tests/test_generate.py`

- [ ] **Step 1: Write the large-repo builder**

Append to `tests/builders.py`:

```python
def make_large_repo(root: Path, n: int) -> Path:
    """A repo whose markdown is large enough to exceed the size budget.

    Each file carries a heading and a big body so the rendered island grows
    with n. Use a small n for the warn band and a large n to force truncation.
    """
    docs = root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    body = ("lorem ipsum dolor sit amet " * 400) + "\n"
    for i in range(n):
        (docs / f"big_{i:04d}.md").write_text(f"# Doc {i}\n\n{body}")
    return root
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_generate.py`:

```python
import logging
from tests.builders import make_large_repo


def test_over_2mb_truncates_to_summary_only(tmp_path):
    make_large_repo(tmp_path, 150)
    data = _island(generate(tmp_path))
    assert data["generator"]["truncated"] is True
    # heavy values blanked, keys/shapes preserved
    assert data["search"] == []
    for d in data["docs"]["references"]:
        assert d["summary"] == "" and d["html"] == ""
        assert "id" in d and "title" in d and "path" in d  # shape intact


def test_between_1_and_2mb_warns_and_keeps_full(tmp_path, caplog):
    make_large_repo(tmp_path, 45)
    with caplog.at_level(logging.WARNING):
        data = _island(generate(tmp_path))
    assert data["generator"]["truncated"] is False
    assert any(d["html"] for d in data["docs"]["references"])  # full kept
    assert "exceeds" in caplog.text


def test_small_repo_not_truncated(tmp_path):
    make_claude_repo(tmp_path)
    data = _island(generate(tmp_path))
    assert data["generator"]["truncated"] is False
```

Note: each `big_*.md` contributes roughly 30 KB to the island (its `html` body, its `summary`, and its search entry each hold the ~11 KB body). The `n` values (150 ≈ >2 MB, 45 ≈ 1–2 MB) target each band; if a run lands in the wrong band, adjust `n` so the assertion's band is hit — do not change the thresholds.

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_generate.py -k "2mb or truncat" -q`
Expected: FAIL (`truncated` stays `False`; nothing blanked).

- [ ] **Step 4: Implement**

At the top of `src/acc/generate.py` add:

```python
import copy
import logging

logger = logging.getLogger(__name__)

_WARN_BYTES = 1_000_000
_TRUNCATE_BYTES = 2_000_000
```

Add this helper above `def generate(`:

```python
def _reduce_for_size(data: dict) -> dict:
    """Summary-only island: deep-copy then blank known heavy values.

    Blanks every inventory/doc summary, every doc html body, and the search
    array, and sets generator.truncated. Deep-copy-then-blank preserves every
    key and optional field (item id, MCP config, doc id), so validate() and
    assert_no_secrets still pass on the result.
    """
    reduced = copy.deepcopy(data)
    for bucket in reduced["inventory"].values():
        for item in bucket:
            item["summary"] = ""
    for bucket in reduced["docs"].values():
        for doc in bucket:
            doc["summary"] = ""
            if "html" in doc:
                doc["html"] = ""
    reduced["search"] = []
    reduced["generator"]["truncated"] = True
    return reduced
```

Replace the render/write at `src/acc/generate.py:184-186`:

```python
    validate(data)
    html = render_html(data)
    size = len(html.encode("utf-8"))
    if size > _TRUNCATE_BYTES:
        reduced = _reduce_for_size(data)
        validate(reduced)
        html = render_html(reduced)
        rsize = len(html.encode("utf-8"))
        logger.warning("dashboard %d bytes exceeds %d; reduced to %d bytes",
                       size, _TRUNCATE_BYTES, rsize)
        if rsize > _TRUNCATE_BYTES:
            logger.warning("reduced dashboard still %d bytes (over budget)", rsize)
    elif size > _WARN_BYTES:
        logger.warning("dashboard %d bytes exceeds %d", size, _WARN_BYTES)
    dashboard.write_text(html, encoding="utf-8")
    return dashboard
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_generate.py -q`
Expected: PASS. If a budget test lands in the wrong band, adjust `n` in that test and re-run.

- [ ] **Step 6: Commit**

```bash
git add src/acc/generate.py tests/builders.py tests/test_generate.py
git commit -m "feat(phase-3): output size budget (warn >1MB, summary-only >2MB)"
```

---

### Task 3: Playwright DOM test harness

**Files:**
- Modify: `pyproject.toml` (add a `test` optional-dependency group)
- Create: `tests/test_render_dom.py`

- [ ] **Step 1: Add the test dependency**

In `pyproject.toml`, after the `[project]` table add:

```toml
[project.optional-dependencies]
test = ["pytest", "pytest-playwright"]
```

- [ ] **Step 2: Install and prepare the browser**

Run:
```bash
python -m pip install -e ".[test]"
python -m playwright install chromium
```
Expected: installs `pytest-playwright` and the Chromium browser.

- [ ] **Step 3: Write a smoke DOM test that passes on the current renderer**

Create `tests/test_render_dom.py`:

```python
"""DOM tests: render the real HTML in a browser and assert behavior.

set_content loads the self-contained dashboard with no server and no file://,
so inline <script> runs and the JSON island is parsed exactly as in the wild.
"""
from pathlib import Path

from acc.generate import generate
from tests.builders import make_multi_provider_repo, make_brownfield_repo


def _html(repo: Path) -> str:
    return generate(repo).read_text(encoding="utf-8")


def test_dom_renders_title(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    assert page.locator("#acc-title").inner_text() != ""
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_render_dom.py -q`
Expected: PASS (1 test). This proves the harness works against the current renderer.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/test_render_dom.py
git commit -m "test(phase-3): add Playwright DOM test harness"
```

---

### Task 4: `encodedRelHref` + `itemRow`; route docs/todos through it

**Files:**
- Modify: `src/acc/templates/app.js` (add helpers; rewrite `renderDocs`/`renderTodos`)
- Modify: `src/acc/templates/styles.css` (add `.acc-chip`, `.acc-summary`)
- Test: `tests/test_render_dom.py`

- [ ] **Step 1: Write the failing DOM test**

Append to `tests/test_render_dom.py`:

```python
def test_doc_path_renders_as_encoded_link(page, tmp_path):
    # a doc with reserved chars in its name must produce a correctly encoded href
    (tmp_path / "weird name#1.md").write_text("# Weird\n\nbody")
    page.set_content(_html(tmp_path))
    link = page.locator('#acc-docs a.path', has_text="weird name#1.md")
    assert link.count() == 1
    href = link.first.get_attribute("href")
    assert "weird%20name%231.md" in href  # space->%20, #->%23
    assert "#1.md" not in href             # raw # would start a fragment
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_render_dom.py::test_doc_path_renders_as_encoded_link -q`
Expected: FAIL — docs currently render the path as a `<span class="path">`, not an `<a>`, so `a.path` count is 0.

- [ ] **Step 3: Implement the helpers and refactor**

In `src/acc/templates/app.js`, after the `el(...)` helper add:

```javascript
  function encodedRelHref(prefix, path) {
    var raw = (prefix === "." ? path : prefix + "/" + path);
    return raw.split("/").map(function (seg) {
      return seg === "." || seg === ".." ? seg : encodeURIComponent(seg);
    }).join("/");
  }

  function itemRow(opts) {
    var row = el("div", "acc-row acc-item");
    var head = el("div", "acc-rowhead");
    if (opts.provider) head.appendChild(el("span", "acc-chip", opts.provider));
    if (opts.typeLabel) head.appendChild(el("span", "badge", opts.typeLabel));
    head.appendChild(el("span", "acc-itemtitle", opts.title));
    row.appendChild(head);
    if (opts.summary) row.appendChild(el("div", "acc-summary", opts.summary));
    var prefix = (data.source && data.source.pathPrefix) || "";
    if (prefix) {
      var a = el("a", "path", opts.path);
      a.href = encodedRelHref(prefix, opts.path);
      row.appendChild(a);
    } else {
      row.appendChild(el("span", "path", opts.path));
    }
    row.dataset.search =
      (opts.title + " " + opts.path + " " + (opts.summary || "")).toLowerCase();
    return row;
  }
```

Replace `renderDocs` and `renderTodos` with:

```javascript
  function renderDocs() {
    var host = document.getElementById("acc-docs");
    var groups = data.docs;
    Object.keys(groups).sort().forEach(function (g) {
      groups[g].forEach(function (doc) {
        host.appendChild(itemRow({
          typeLabel: g, title: doc.title, path: doc.path, summary: doc.summary
        }));
      });
    });
  }

  function renderTodos() {
    var host = document.getElementById("acc-todos");
    (data.project.openTodos || []).forEach(function (t) {
      host.appendChild(itemRow({ title: t.text, path: t.path }));
    });
  }
```

In `src/acc/templates/styles.css` append:

```css
.acc-rowhead { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.acc-chip { border: 1px solid var(--line); border-radius: 8px; padding: 0 6px; font-size: 10px; }
.acc-itemtitle { font-weight: 600; }
.acc-summary { color: var(--muted); margin: 2px 0; }
.acc-row a.path { display: inline-block; color: var(--muted); font-size: 11px; text-decoration: none; }
.acc-row a.path:hover { text-decoration: underline; }
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_render_dom.py -q`
Expected: PASS (both DOM tests).

- [ ] **Step 5: Commit**

```bash
git add src/acc/templates/app.js src/acc/templates/styles.css tests/test_render_dom.py
git commit -m "feat(phase-3): shared itemRow + per-segment-encoded path links"
```

---

### Task 5: `renderInventory` + Inventory section/nav

**Files:**
- Modify: `src/acc/templates/app.js` (add `INV_ORDER`/`INV_LABEL`, `renderInventory`, call it)
- Modify: `src/acc/templates/dashboard.html.tmpl` (nav link + `<section id="inventory">`)
- Test: `tests/test_render_dom.py`, `tests/test_render.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_render_dom.py`:

```python
def test_inventory_groups_by_type_with_chips(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    inv = page.locator("#acc-inventory")
    assert inv.locator(".acc-item").count() >= 11
    # a Codex prompt keeps its native label and provider
    codex_cmd = inv.locator(".acc-item", has_text="refactor")
    assert codex_cmd.locator(".acc-chip", has_text="codex").count() == 1
    assert codex_cmd.locator(".badge", has_text="Codex prompt").count() == 1
    # MCP servers block exists and is labeled with its count
    assert inv.locator(".acc-sublabel", has_text="MCP servers").count() == 1


def test_search_filters_rows(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    visible = lambda: page.locator(".acc-item:not(.acc-hidden)").count()
    before = visible()
    page.fill("#acc-search", "figma")
    after = visible()
    assert 0 < after < before  # typing narrows the visible rows
    assert page.locator(".acc-item:not(.acc-hidden)", has_text="figma").count() >= 1
```

Append to `tests/test_render.py`:

```python
def test_template_and_app_have_inventory():
    html = render_html(_data())
    assert 'id="inventory"' in html
    assert ">Inventory<" in html        # nav link
    assert "renderInventory" in html    # app.js embedded
    assert "function itemRow" in html
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_render_dom.py::test_inventory_groups_by_type_with_chips tests/test_render.py::test_template_and_app_have_inventory -q`
Expected: FAIL — no `#inventory` host, `renderInventory` undefined.

- [ ] **Step 3: Implement**

In `src/acc/templates/dashboard.html.tmpl`, add the nav link after the Overview link and the section after the Overview section:

```html
<nav class="acc-nav">
  <a href="#overview">Overview</a>
  <a href="#inventory">Inventory</a>
  <a href="#docs">Docs</a>
  <a href="#todos">TODOs</a>
</nav>
<section id="overview"><div class="acc-label">Overview</div><div id="acc-overview"></div></section>
<section id="inventory"><div class="acc-label">Inventory</div><div id="acc-inventory"></div></section>
```

In `src/acc/templates/app.js`, before `renderHead` add the constants:

```javascript
  var INV_ORDER = ["agents", "commands", "skills", "hooks", "mcpServers", "rules"];
  var INV_LABEL = {
    agents: "Agents", commands: "Commands", skills: "Skills",
    hooks: "Hooks", mcpServers: "MCP servers", rules: "Rules"
  };
```

Add the function:

```javascript
  function renderInventory() {
    var host = document.getElementById("acc-inventory");
    var inv = data.inventory || {};
    INV_ORDER.forEach(function (bucket) {
      var items = inv[bucket] || [];
      if (!items.length) return;
      host.appendChild(el("div", "acc-sublabel",
        INV_LABEL[bucket] + " (" + items.length + ")"));
      items.forEach(function (it) {
        host.appendChild(itemRow({
          provider: it.provider, typeLabel: it.typeLabel,
          title: it.title, path: it.path, summary: it.summary
        }));
      });
    });
  }
```

Add `renderInventory();` to the call block at the bottom, after `renderHead();`:

```javascript
  renderHead();
  renderInventory();
  renderDocs();
  renderTodos();
  wireSearch();
```

In `src/acc/templates/styles.css` append:

```css
.acc-sublabel { font-weight: 600; margin: 12px 0 4px; }
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/test_render_dom.py tests/test_render.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/acc/templates/app.js src/acc/templates/dashboard.html.tmpl src/acc/templates/styles.css tests/test_render_dom.py tests/test_render.py
git commit -m "feat(phase-3): Inventory view grouped by type with provider chips"
```

---

### Task 6: `renderOverview` bento grid

**Files:**
- Modify: `src/acc/templates/app.js` (add `renderOverview`, call it)
- Modify: `src/acc/templates/styles.css` (bento + card)
- Test: `tests/test_render_dom.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_render_dom.py`:

```python
def test_overview_bento_cards(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    ov = page.locator("#acc-overview .acc-bento")
    assert ov.count() == 1
    cards = ov.locator(".acc-card")
    assert cards.count() >= 3  # Providers, Inventory, Docs (+ TODOs)
    # generic is not shown when real providers exist
    prov = ov.locator(".acc-card", has_text="Providers")
    assert prov.locator(".acc-chip", has_text="Generic").count() == 0
    assert prov.locator(".acc-chip", has_text="Claude Code").count() == 1


def test_overview_generic_only_when_sole(page, tmp_path):
    make_brownfield_repo(tmp_path)  # no AI provider -> generic only
    page.set_content(_html(tmp_path))
    prov = page.locator("#acc-overview .acc-card", has_text="Providers")
    assert prov.locator(".acc-chip", has_text="Generic").count() == 1
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_render_dom.py -k overview -q`
Expected: FAIL — `#acc-overview` is empty (`renderOverview` undefined).

- [ ] **Step 3: Implement**

This task reuses `INV_ORDER` and `INV_LABEL` defined in Task 5 — do not redeclare them (a duplicate `var` would be a syntax error). In `src/acc/templates/app.js` add the function (above the call block):

```javascript
  function card(title, target) {
    var c = el("div", "acc-card");
    if (target) {
      var a = el("a", "acc-card-h", title);
      a.href = "#" + target;
      c.appendChild(a);
    } else {
      c.appendChild(el("div", "acc-card-h", title));
    }
    return c;
  }

  function renderOverview() {
    var host = document.getElementById("acc-overview");
    var bento = el("div", "acc-bento");

    var provs = data.providers || [];
    var firstClass = provs.filter(function (p) { return p.id !== "generic"; });
    var show = firstClass.length ? firstClass : provs;
    if (show.length) {
      var pc = card("Providers");
      show.forEach(function (p) { pc.appendChild(el("span", "acc-chip", p.displayName)); });
      bento.appendChild(pc);
    }

    var inv = data.inventory || {};
    var nonEmpty = INV_ORDER.filter(function (b) { return (inv[b] || []).length; });
    if (nonEmpty.length) {
      var ic = card("Inventory", "inventory");
      nonEmpty.forEach(function (b) {
        ic.appendChild(el("div", null, inv[b].length + " " + INV_LABEL[b].toLowerCase()));
      });
      bento.appendChild(ic);
    }

    var todos = (data.project && data.project.openTodos) || [];
    if (todos.length) {
      var tc = card("Open TODOs (" + todos.length + ")", "todos");
      todos.slice(0, 3).forEach(function (t) { tc.appendChild(el("div", null, t.text)); });
      bento.appendChild(tc);
    }

    var docs = data.docs || {};
    var docCount = 0;
    Object.keys(docs).forEach(function (k) { docCount += (docs[k] || []).length; });
    if (docCount) {
      var dc = card("Docs", "docs");
      dc.appendChild(el("div", null, docCount + " referenced"));
      bento.appendChild(dc);
    }

    if (bento.childNodes.length) host.appendChild(bento);
  }
```

Add `renderOverview();` right after `renderHead();` in the call block:

```javascript
  renderHead();
  renderOverview();
  renderInventory();
  renderDocs();
  renderTodos();
  wireSearch();
```

In `src/acc/templates/styles.css` append:

```css
.acc-bento { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
.acc-card { border: 1px solid var(--line); border-radius: 8px; padding: 10px; }
.acc-card-h { display: block; font-weight: 600; margin-bottom: 6px; color: var(--fg); text-decoration: none; }
.acc-card a.acc-card-h:hover { text-decoration: underline; }
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/test_render_dom.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/acc/templates/app.js src/acc/templates/styles.css tests/test_render_dom.py
git commit -m "feat(phase-3): bento Overview grid (real-data cards)"
```

---

### Task 7: Truncation banner

**Files:**
- Modify: `src/acc/templates/dashboard.html.tmpl` (banner host after `<nav>`)
- Modify: `src/acc/templates/app.js` (`renderBanner`, call it)
- Modify: `src/acc/templates/styles.css` (banner style)
- Test: `tests/test_render_dom.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_render_dom.py`:

```python
def test_truncation_banner_when_truncated(page, tmp_path):
    make_large_repo(tmp_path, 150)  # forces summary-only
    page.set_content(_html(tmp_path))
    banner = page.locator("#acc-banner")
    assert banner.inner_text().strip() != ""


def test_no_banner_when_full(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    assert page.locator("#acc-banner").inner_text().strip() == ""
```

Add the import at the top of `tests/test_render_dom.py`:

```python
from tests.builders import make_multi_provider_repo, make_brownfield_repo, make_large_repo
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_render_dom.py -k banner -q`
Expected: FAIL — no `#acc-banner` element.

- [ ] **Step 3: Implement**

In `src/acc/templates/dashboard.html.tmpl`, add the banner host immediately after the closing `</nav>`:

```html
</nav>
<div id="acc-banner" class="acc-banner"></div>
```

In `src/acc/templates/app.js` add the function and call it after `renderHead();`:

```javascript
  function renderBanner() {
    if (!(data.generator && data.generator.truncated)) return;
    document.getElementById("acc-banner").appendChild(el("div", "acc-noticetext",
      "This dashboard was reduced to a summary because the full output exceeded the size budget."));
  }
```

```javascript
  renderHead();
  renderBanner();
  renderOverview();
  renderInventory();
  renderDocs();
  renderTodos();
  wireSearch();
```

In `src/acc/templates/styles.css` append:

```css
.acc-banner:empty { display: none; }
.acc-banner { padding: 8px 16px; border-bottom: 1px solid var(--line); }
.acc-noticetext { color: var(--muted); font-size: 12px; }
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_render_dom.py -q`
Expected: PASS (all DOM tests).

- [ ] **Step 5: Commit**

```bash
git add src/acc/templates/dashboard.html.tmpl src/acc/templates/app.js src/acc/templates/styles.css tests/test_render_dom.py
git commit -m "feat(phase-3): summary-only truncation banner"
```

---

### Task 8: Full verification and manual acceptance

**Files:** none (verification only)

- [ ] **Step 1: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS (all Python contract tests + Playwright DOM tests).

- [ ] **Step 2: Determinism check**

Run:
```bash
PYTHONPATH=src python3 -c "
from pathlib import Path; from acc.generate import generate
a = generate(Path('.')).read_text('utf-8'); b = generate(Path('.')).read_text('utf-8')
print('deterministic:', a == b)"
```
Expected: `deterministic: True`.

- [ ] **Step 3: Lint the source**

Run: `python -m ruff check src/`
Expected: clean (no errors).

- [ ] **Step 4: Manual acceptance — screenshot a multi-provider dashboard**

Generate a multi-provider dashboard to a temp dir, serve it, and screenshot with Playwright (the renderer extension may be offline; serve over local HTTP). Confirm visually: the Overview bento shows Providers/Inventory/TODOs/Docs cards; the Inventory view lists all items grouped by type with provider chips; path links resolve; search filters rows.

- [ ] **Step 5: Final commit if any verification fix was needed**

```bash
git add -A
git commit -m "test(phase-3): verification pass"
```

---

## Notes for the implementer

- Do not introduce `innerHTML` anywhere in `app.js`. Every author value uses `textContent` (via `el`); the only `href` is built by `encodedRelHref`.
- Keep `app.js` a single classic IIFE — no ES modules, no imports. It must run from `file://`.
- The size-budget thresholds are exact byte counts on the rendered HTML; the `n` values in the budget tests are tuned to land in each band, so adjust `n` (not the thresholds) if a band is missed.
- Runtime stays stdlib-only. `pytest-playwright` is test-only; never import it from `src/acc`.
