# Phase 4a — Find Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the dead `data.search` index into a real global omnibox — type-grouped results with counts, a `<mark>`-highlighted snippet, keyboard nav, focus via `/`, and jump-to-row — plus the reusable per-row-id + id→row jump infra, all via `textContent` only.

**Architecture:** The Python generator (`generate.py`) enriches each search record with generator-controlled `type`/`typeLabel` (synthesized for docs from their bucket key) and a capped, html-escaped body slice; `_reduce_for_size` rebuilds a light names+paths index instead of emptying `search`; every searchable item (incl. TODOs) gets a `stable_id`. `schema.py` enforces the record shape at build time. The renderer (`app.js`) decodes escaped values with a new `htmlUnescape` helper at the `textContent` boundary and the match key, builds an omnibox over `data.search`, builds an `id→row` map during view render, and jumps with scrollIntoView + a transient flash. The data island stays uniformly html-escaped (Phase 1 contract); `textContent`/`<mark>` keep it inert.

**Tech Stack:** stdlib-only Python 3.12 (no runtime deps), vanilla ES5-style IIFE JS in `app.js`, a `<style>`/JSON-island single-file HTML template, pytest + pytest-playwright (test-only extra) DOM tests via `page.set_content`.

---

## File structure

- `src/acc/generate.py` — `_build_search` (add `type`/`typeLabel` incl. docs + capped escaped body slice + `_SEARCH_BODY_CHARS`), `_reduce_for_size` (light index rebuild), the escape pass capturing a raw body slice, TODO `id`s.
- `src/acc/adapters/base.py` — add `_DOC_TYPE_LABELS` (bucket-key → human label) so docs can get a `typeLabel`; helper `doc_type_label(bucket)`.
- `src/acc/adapters/generic.py` — give each open-TODO record a `stable_id`.
- `src/acc/schema.py` — `validate()` enforces every `search` record's keys, string types, and known `type`.
- `src/acc/templates/app.js` — `htmlUnescape` helper; per-row `dataset.id` in `itemRow`/`renderDocs`/`renderTodos`; an `id→row` Map; the omnibox (build/consume/group/snippet/`<mark>`/keyboard/jump); relabel the per-view filter input.
- `src/acc/templates/dashboard.html.tmpl` — omnibox `<input id="acc-omnibox">` + result panel `<div id="acc-omnibox-results">`; relabel `#acc-search`.
- `src/acc/templates/styles.css` — omnibox input/panel, `<mark>`, type chip, `.acc-flash` highlight-flash, active-hit styles.
- `tests/test_generate.py` — `_build_search` type/typeLabel/escaped-slice/cap/sort; `_reduce_for_size` light index; TODO ids.
- `tests/test_schema.py` — malformed search-record rejection.
- `tests/test_render_dom.py` — Playwright DOM: grouping+counts, keyboard, jump+flash, `<mark>`, empty states, `AT&T`, hostile-body inertness.
- `tests/test_appjs_guard.py` — CI guard grepping `app.js` for banned `innerHTML`/`outerHTML`/`insertAdjacentHTML`.

---

### Task 0: Reconcile branch base (Phase 3 must be present)

The current branch `feature/phase-4a-find` was cut from a commit **before** Phase 3 merged. The working tree `app.js` (60 lines), `generate.py` (no `_reduce_for_size`/`_WARN_BYTES`), and templates are the pre-Phase-3 versions, but this spec was written against Phase 3 (`itemRow`, `renderInventory`, `_reduce_for_size`, `pathPrefix`, `generator.truncated`, `tests/test_render_dom.py`). All code blocks below assume the Phase 3 base. This task rebases Phase 4a onto Phase 3 so the planned edits apply to real current code.

**Files:**
- Modify (git history only): branch `feature/phase-4a-find` (currently at `89a2fa5`, parent chain ends at `17bb59a`; Phase 3 lives on `feature/phase-3-renderer` tip `32bf625`).

- [ ] Confirm the mismatch: `git -C /Users/ozzy-mac/Projects/html-dash merge-base --is-ancestor feature/phase-3-renderer HEAD; echo $?` — expect `1` (Phase 3 NOT an ancestor).
- [ ] Confirm only the spec commit is unique to this branch: `git -C /Users/ozzy-mac/Projects/html-dash log --oneline feature/phase-3-renderer..feature/phase-4a-find` — expect a single line `89a2fa5 docs(phase-4a): spec for Find (global omnibox)`.
- [ ] Rebase the spec commit onto Phase 3: `git -C /Users/ozzy-mac/Projects/html-dash rebase --onto feature/phase-3-renderer 17bb59a feature/phase-4a-find`.
- [ ] Verify Phase 3 is now present: `git -C /Users/ozzy-mac/Projects/html-dash merge-base --is-ancestor feature/phase-3-renderer HEAD; echo $?` — expect `0`; and `test -f /Users/ozzy-mac/Projects/html-dash/tests/test_render_dom.py && grep -c "_reduce_for_size" /Users/ozzy-mac/Projects/html-dash/src/acc/generate.py` — expect a non-zero count.
- [ ] Install the test extra and confirm the full suite is green on the new base: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pip install -e '.[test]' && python3 -m playwright install chromium` then `python3 -m pytest -q` — expect all tests pass (Phase 3 unit + DOM).
- [ ] No commit (rebase already rewrote history). If the rebase is undesired, the fallback is `git merge feature/phase-3-renderer` on this branch; either way Phase 3 code must be in the tree before Task 1.

---

### Task 1: Doc type-label lookup in base.py

Docs are built by `claude.py`/`codex.py`/`generic.py` with keys `{id,title,path,summary,html}` and carry no `type`/`typeLabel`. They live in `_DOC_BUCKETS = ("prds","adrs","decisions","workflows","references")`. Add a bucket-key→label map and a helper so `_build_search` can synthesize a doc `typeLabel`. These are generator-controlled constants (not author input), so they are not escaped — same convention as `provider`/`typeLabel` in `_escape_text_fields`.

**Files:**
- Modify: `src/acc/adapters/base.py` (after line 38, the `empty_docs` block)
- Test: `tests/test_adapter_base.py`

- [ ] Write failing test. Append to `tests/test_adapter_base.py`:
```python
def test_doc_type_label_maps_buckets():
    from acc.adapters.base import doc_type_label
    assert doc_type_label("references") == "Reference"
    assert doc_type_label("prds") == "PRD"
    assert doc_type_label("adrs") == "ADR"
    assert doc_type_label("decisions") == "Decision"
    assert doc_type_label("workflows") == "Workflow"


def test_doc_type_label_unknown_bucket_titlecases():
    from acc.adapters.base import doc_type_label
    assert doc_type_label("misc") == "Misc"
```
- [ ] Run it — expect FAIL: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_adapter_base.py -q` → `ImportError: cannot import name 'doc_type_label'`.
- [ ] Implement. In `src/acc/adapters/base.py`, after the `empty_docs()` function (line 38), add:
```python
# Human group headings for the doc buckets. Generator-controlled constants
# (never author input), so they are not html-escaped — same convention as the
# inventory typeLabel set by make_item.
_DOC_TYPE_LABELS = {
    "prds": "PRD",
    "adrs": "ADR",
    "decisions": "Decision",
    "workflows": "Workflow",
    "references": "Reference",
}


def doc_type_label(bucket: str) -> str:
    """Map a doc bucket key to its human group heading.

    Unknown buckets fall back to a title-cased key so a future bucket still
    gets a non-empty, deterministic label instead of an undefined group.
    """
    return _DOC_TYPE_LABELS.get(bucket, bucket.title())
```
- [ ] Run to pass: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_adapter_base.py -q` → all pass.
- [ ] Commit: `git -C /Users/ozzy-mac/Projects/html-dash add src/acc/adapters/base.py tests/test_adapter_base.py && git -C /Users/ozzy-mac/Projects/html-dash commit -m "feat(phase-4a): doc bucket type-label lookup for search records"`

---

### Task 2: TODO records carry a stable id

Open-TODO records (`{text, path}`, built in `generic.py:_extract_todos` and `harvest_todos`) have no `id`, so omnibox hits in the TODO group cannot be jumped to. Add a `stable_id` to each TODO at extraction. The id must be deterministic and stable across runs. Use `stable_id("generic", "todo", path, text)`.

**Files:**
- Modify: `src/acc/adapters/generic.py` (line 8 `_TODO`, line 55-59 `_extract_todos`; `stable_id` already imported at line 4)
- Test: `tests/test_generic_adapter.py`, `tests/test_generate.py`

- [ ] Write failing unit test. Append to `tests/test_generic_adapter.py`:
```python
def test_extract_todos_carry_stable_id():
    from acc.adapters.generic import _extract_todos
    todos = _extract_todos("- [ ] first thing\n- [ ] second thing\n", "PLAN.md")
    assert len(todos) == 2
    for t in todos:
        assert t["id"].startswith("") and len(t["id"]) == 12
        assert set(t.keys()) == {"id", "text", "path"}
    # deterministic: same input -> same id
    again = _extract_todos("- [ ] first thing\n", "PLAN.md")
    assert again[0]["id"] == todos[0]["id"]
```
- [ ] Write failing generate test. Append to `tests/test_generate.py`:
```python
def test_todo_records_have_ids(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / "CLAUDE.md").write_text("# Rules\n\n- [ ] wire up CI\n")
    data = _island(generate(tmp_path))
    todos = data["project"]["openTodos"]
    assert todos and all(t.get("id") and len(t["id"]) == 12 for t in todos)
```
- [ ] Run them — expect FAIL: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_generic_adapter.py::test_extract_todos_carry_stable_id tests/test_generate.py::test_todo_records_have_ids -q` → `KeyError: 'id'` / `AssertionError`.
- [ ] Implement. In `src/acc/adapters/generic.py`, replace `_extract_todos` (lines 55-59):
```python
def _extract_todos(text: str, rel: str) -> list[dict]:
    """Open-checkbox (`- [ ]`) lines from already-redacted markdown.

    Each TODO carries a stable_id so the omnibox can jump to its rendered row,
    matching the id contract every inventory/doc item already has.
    """
    out: list[dict] = []
    for line in text.splitlines():
        m = _TODO.match(line)
        if m:
            todo_text = m.group(1).strip()
            out.append({"id": stable_id("generic", "todo", rel, todo_text),
                        "text": todo_text, "path": rel})
    return out
```
- [ ] Run to pass: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_generic_adapter.py tests/test_generate.py -q` → all pass (existing TODO tests still green; they read `t["text"]`).
- [ ] Commit: `git -C /Users/ozzy-mac/Projects/html-dash add src/acc/adapters/generic.py tests/test_generic_adapter.py tests/test_generate.py && git -C /Users/ozzy-mac/Projects/html-dash commit -m "feat(phase-4a): stable id on every open-TODO record"`

---

### Task 3: `_SEARCH_BODY_CHARS` cap + escaped body slice captured in the escape pass

The search record's `text` must be `summary` plus a capped slice of the item's raw body. The slice must be escaped on the **same pass** as `title`/`summary` so the island stays uniformly escaped and `_build_search` reads escaped fields (Phase 1 contract). Per spec open-question default: slice the doc `summary` for docs; for inventory items use a raw body if present, else `summary`. Current inventory items have no raw body field, so this resolves to `summary` today, with the plumbing ready if a future adapter adds one. Capture the escaped slice onto each record under a private key `_searchBody` during `_escape_text_fields`, then `_build_search` appends it. `str` slicing is codepoint-based, so a char cap is already multibyte-safe at the cut.

**Files:**
- Modify: `src/acc/generate.py` (add constant near `_WARN_BYTES` line 20-21; extend `_escape_text_fields` lines 104-125)
- Test: `tests/test_generate.py`

- [ ] Write failing test. Append to `tests/test_generate.py`:
```python
def test_search_body_char_cap_is_200():
    from acc.generate import _SEARCH_BODY_CHARS
    assert _SEARCH_BODY_CHARS == 200


def test_escape_pass_caps_body_slice_multibyte_safe():
    from acc.generate import _escape_text_fields, _SEARCH_BODY_CHARS
    long_body = "héllo " * 100  # multibyte chars, well over the cap
    inv = {"agents": [{"id": "i1", "title": "A", "path": "a.md",
                       "summary": "s", "_rawBody": long_body}]}
    docs = {"references": []}
    project = {"title": "p", "openTodos": []}
    _escape_text_fields(inv, docs, project)
    slice_ = inv["agents"][0]["_searchBody"]
    assert len(slice_) <= _SEARCH_BODY_CHARS          # char-capped
    assert slice_ == long_body[:_SEARCH_BODY_CHARS]    # clean codepoint cut
```
- [ ] Run it — expect FAIL: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_generate.py::test_search_body_char_cap_is_200 tests/test_generate.py::test_escape_pass_caps_body_slice_multibyte_safe -q` → `ImportError: cannot import name '_SEARCH_BODY_CHARS'`.
- [ ] Implement constant. In `src/acc/generate.py`, after line 21 (`_TRUNCATE_BYTES = 2_000_000`), add:
```python
# Cap on the per-item body slice appended to each search record's `text`.
# Budget math vs _WARN_BYTES (1 MB): at ~500 indexable items, 500 * 200 =
# 100 KB pre-escape — an order of magnitude under the warn line, so the slice
# does not threaten the size budget. _reduce_for_size is the safety valve above
# it (it drops the slice entirely). str slicing is codepoint-based, so a char
# cap cuts cleanly on multibyte boundaries.
_SEARCH_BODY_CHARS = 200
```
- [ ] Implement the slice capture in `_escape_text_fields`. In `src/acc/generate.py`, replace the inventory/doc loop body (lines 112-121) so it also escapes-and-caps a body slice. Replace:
```python
    for bucket in (inv, docs):
        for items in bucket.values():
            for it in items:
                for field in ("title", "summary"):
                    if field in it:
                        # display fields are strings by contract; coerce any
                        # wrong-shape leaf from a malformed config so escape
                        # (and the renderer) never sees a list/dict here
                        value = it[field]
                        it[field] = _html.escape(value if isinstance(value, str) else "")
```
with:
```python
    for bucket in (inv, docs):
        for items in bucket.values():
            for it in items:
                for field in ("title", "summary"):
                    if field in it:
                        # display fields are strings by contract; coerce any
                        # wrong-shape leaf from a malformed config so escape
                        # (and the renderer) never sees a list/dict here
                        value = it[field]
                        it[field] = _html.escape(value if isinstance(value, str) else "")
                # Capture a capped, escaped body slice on the SAME pass so the
                # island stays uniformly escaped and _build_search reads escaped
                # fields (Phase 1 contract). Source: a raw body if the adapter
                # carries one, else the (now-escaped) summary. char-cap before
                # escape so the visible length, not the entity-expanded one, is
                # what _SEARCH_BODY_CHARS bounds.
                raw = it.get("_rawBody")
                src = raw if isinstance(raw, str) else (it.get("summary_src") or "")
                if src:
                    it["_searchBody"] = _html.escape(src[:_SEARCH_BODY_CHARS])
                else:
                    # no raw body: reuse the already-escaped summary as the slice
                    it["_searchBody"] = it.get("summary", "")
```

  Note: docs have no `_rawBody` and no `summary_src`, so `_searchBody` becomes the escaped `summary` — exactly the spec default (slice the doc summary). Inventory items today also lack `_rawBody`, so they fall back to the escaped summary; the `_rawBody` branch is live for any future adapter that sets it.
- [ ] Run to pass: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_generate.py -q` → all pass.
- [ ] Commit: `git -C /Users/ozzy-mac/Projects/html-dash add src/acc/generate.py tests/test_generate.py && git -C /Users/ozzy-mac/Projects/html-dash commit -m "feat(phase-4a): _SEARCH_BODY_CHARS cap + escaped body slice on escape pass"`

---

### Task 4: `_build_search` adds type/typeLabel (incl. docs) and the escaped body slice

Grow each record from `{id,title,path,text}` to `{id,type,typeLabel,title,path,text}`. Inventory items already carry `type`/`typeLabel` (via `make_item`); docs do not — synthesize them from the bucket key with `doc_type_label` (Task 1) and a fixed `type="doc"`. `text` = escaped `summary` + the escaped capped slice from `_searchBody` (Task 3). Keep the deterministic `(path, title, id)` sort (load-bearing: `json.dumps(sort_keys=True)` does not sort lists). The `docs` loop must know its bucket key, so iterate `bucket.items()` for docs.

**Files:**
- Modify: `src/acc/generate.py` (`_build_search` lines 93-101; import `doc_type_label` at line 11)
- Test: `tests/test_generate.py`

- [ ] Write failing test. Append to `tests/test_generate.py`:
```python
def test_build_search_record_shape_and_doc_type_label(tmp_path):
    make_multi_provider_repo(tmp_path)
    data = _island(generate(tmp_path))
    recs = data["search"]
    assert recs, "expected search records"
    required = {"id", "type", "typeLabel", "title", "path", "text"}
    for r in recs:
        assert required <= set(r.keys())
        assert all(isinstance(r[k], str) for k in required)
    # inventory record keeps its make_item type/typeLabel
    agent = next(r for r in recs if r["typeLabel"] == "Claude agent")
    assert agent["type"] == "agent"
    # doc record gets a synthesized type/typeLabel (no undefined group)
    doc = next(r for r in recs if r["type"] == "doc")
    assert doc["typeLabel"] in {"Reference", "PRD", "ADR", "Decision", "Workflow"}


def test_build_search_appends_escaped_body_slice():
    from acc.generate import _build_search
    inv = {"agents": [{"id": "i1", "type": "agent", "typeLabel": "Claude agent",
                       "title": "A", "path": "a.md", "summary": "sum",
                       "_searchBody": "BODYSLICE"}]}
    docs = {"references": []}
    recs = _build_search(inv, docs)
    assert recs[0]["text"] == "sum BODYSLICE"


def test_build_search_escapes_hostile_slice_in_island(tmp_path):
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "x.md").write_text(
        '---\nname: ok\ndescription: "</script><img onerror=alert(1)>"\n---\n')
    data = _island(generate(tmp_path))
    blob = " ".join(r["text"] for r in data["search"])
    assert "onerror=alert(1)>" not in blob
    assert "&lt;img" in blob


def test_build_search_stays_sorted(tmp_path):
    make_multi_provider_repo(tmp_path)
    data = _island(generate(tmp_path))
    recs = data["search"]
    keys = [(r["path"], r["title"], r["id"]) for r in recs]
    assert keys == sorted(keys)
```
- [ ] Run them — expect FAIL: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_generate.py -k "build_search" -q` → `KeyError`/`AssertionError` (records lack `type`/`typeLabel`, `text` lacks the slice).
- [ ] Implement import. In `src/acc/generate.py` line 11, change:
```python
from .adapters.base import ScanContext, empty_inventory, empty_docs
```
to:
```python
from .adapters.base import ScanContext, empty_inventory, empty_docs, doc_type_label
```
- [ ] Implement `_build_search`. In `src/acc/generate.py`, replace `_build_search` (lines 93-101):
```python
def _build_search(inv: dict, docs: dict) -> list[dict]:
    records: list[dict] = []
    # Docs lack type/typeLabel (built by a separate adapter path keyed only by
    # bucket); synthesize a fixed type="doc" + a bucket-derived typeLabel so doc
    # hits group correctly instead of landing in an undefined group. Inventory
    # items already carry both via make_item.
    for bucket_key, items in docs.items():
        label = doc_type_label(bucket_key)
        for it in items:
            records.append(_search_record(it, "doc", label))
    for items in inv.values():
        for it in items:
            records.append(_search_record(it, it.get("type", ""), it.get("typeLabel", "")))
    # Explicit sort is load-bearing: render.py's json.dumps(sort_keys=True) sorts
    # dict keys but NOT list order, so determinism depends on this.
    records.sort(key=lambda r: (r["path"], r["title"], r["id"]))
    return records


def _search_record(it: dict, type_: str, type_label: str) -> dict:
    # text = escaped summary + escaped capped body slice (both escaped on the
    # same pass in _escape_text_fields, preserving the "search reads escaped
    # fields" contract). type/type_label are generator-controlled constants,
    # not author input, so they are not escaped.
    summary = it.get("summary", "")
    body = it.get("_searchBody", "")
    text = (summary + " " + body).strip() if body and body != summary else summary
    return {"id": it["id"], "type": type_, "typeLabel": type_label,
            "title": it["title"], "path": it["path"], "text": text}
```
- [ ] Run to pass: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_generate.py -q` → all pass.
- [ ] Confirm island stays free of the private `_searchBody` key (it is never written into `data` — only `inv`/`docs` carry it, and those dicts ARE in `data`). Add a guard test to `tests/test_generate.py`:
```python
def test_private_search_body_key_not_in_island(tmp_path):
    make_multi_provider_repo(tmp_path)
    html = generate(tmp_path).read_text(encoding="utf-8")
    assert "_searchBody" not in html
```
- [ ] Run it — expect FAIL (the key leaks into `inv`/`docs` which are serialized into the island). Then fix by stripping the private key before assembly. In `src/acc/generate.py`, immediately after the `search = _build_search(inv, docs)` line (line 208), add:
```python
    # Drop the private slice key so it never reaches the serialized island.
    for bucket in (inv, docs):
        for items in bucket.values():
            for it in items:
                it.pop("_searchBody", None)
```
- [ ] Run to pass: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_generate.py -q` → all pass.
- [ ] Commit: `git -C /Users/ozzy-mac/Projects/html-dash add src/acc/generate.py tests/test_generate.py && git -C /Users/ozzy-mac/Projects/html-dash commit -m "feat(phase-4a): search records carry type/typeLabel + escaped body slice"`

---

### Task 5: `_reduce_for_size` rebuilds a light search index

Replace `reduced["search"] = []` with a light rebuild keeping `{id,type,typeLabel,title,path,text:""}` per record (names + paths still searchable; body slice dropped). Re-validate must stay under budget and pass the schema check from Task 6.

**Files:**
- Modify: `src/acc/generate.py` (`_reduce_for_size` lines 141-160)
- Test: `tests/test_generate.py`

- [ ] Write failing test. Append to `tests/test_generate.py`:
```python
def test_reduce_keeps_light_index_without_body():
    from acc.generate import _reduce_for_size
    data = {
        "schemaVersion": "1.0",
        "generator": {"truncated": False},
        "inventory": {"agents": [], "skills": [], "hooks": [], "commands": [],
                      "mcpServers": [], "rules": []},
        "docs": {"prds": [], "adrs": [], "decisions": [], "workflows": [], "references": []},
        "search": [
            {"id": "i1", "type": "agent", "typeLabel": "Claude agent",
             "title": "A", "path": "a.md", "text": "sum BODY"},
            {"id": "i2", "type": "doc", "typeLabel": "Reference",
             "title": "B", "path": "b.md", "text": "docsum BODY"},
        ],
    }
    reduced = _reduce_for_size(data)
    assert len(reduced["search"]) == 2          # not emptied
    for r in reduced["search"]:
        assert r["text"] == ""                   # body dropped
        assert set(r.keys()) == {"id", "type", "typeLabel", "title", "path", "text"}
    assert reduced["search"][0]["title"] == "A"  # names + paths kept


def test_over_2mb_truncates_keeps_light_search(tmp_path):
    make_claude_repo(tmp_path)
    make_large_repo(tmp_path, 150)  # forces summary-only
    data = _island(generate(tmp_path))
    assert data["generator"]["truncated"] is True
    assert data["search"], "light index must survive truncation"
    for r in data["search"]:
        assert r["text"] == ""
        assert {"id", "type", "typeLabel", "title", "path", "text"} <= set(r.keys())
```
- [ ] Update the existing Phase 3 assertion that the spec changes. In `tests/test_generate.py`, find `test_over_2mb_truncates_to_summary_only` and change `assert data["search"] == []` to `assert data["search"] and all(r["text"] == "" for r in data["search"])` (the light index now survives).
- [ ] Run them — expect FAIL: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_generate.py -k "reduce or truncat" -q` → `AssertionError` (search emptied).
- [ ] Implement. In `src/acc/generate.py`, replace `reduced["search"] = []` (line 158):
```python
    # Light index: keep names + paths searchable after truncation, drop the
    # body slice. The omnibox still finds items by name/path in degraded mode.
    reduced["search"] = [
        {"id": r["id"], "type": r["type"], "typeLabel": r["typeLabel"],
         "title": r["title"], "path": r["path"], "text": ""}
        for r in reduced["search"]
    ]
```
- [ ] Run to pass: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_generate.py -q` → all pass.
- [ ] Commit: `git -C /Users/ozzy-mac/Projects/html-dash add src/acc/generate.py tests/test_generate.py && git -C /Users/ozzy-mac/Projects/html-dash commit -m "feat(phase-4a): light name/path search index on size truncation"`

---

### Task 6: schema.py enforces the search-record shape

`validate()` must reject a malformed search record: missing key, non-string value, or unknown `type`. This is the build-time backstop. Known types = inventory kinds + `"doc"`. The light index (`text:""`) is still valid (empty string is a string).

**Files:**
- Modify: `src/acc/schema.py` (after `_REQUIRED_TOP` block; inside `validate()` lines 45-51)
- Test: `tests/test_schema.py`

- [ ] Write failing test. Append to `tests/test_schema.py`:
```python
def _data_with_search(rec) -> dict:
    data = _minimal_data()
    data["search"] = [rec]
    return data


def _good_record() -> dict:
    return {"id": "i1", "type": "agent", "typeLabel": "Claude agent",
            "title": "A", "path": "a.md", "text": "body"}


def test_validate_accepts_good_search_record():
    validate(_data_with_search(_good_record()))  # no exception


def test_validate_accepts_light_record_empty_text():
    rec = _good_record()
    rec["text"] = ""
    validate(_data_with_search(rec))  # no exception


def test_validate_rejects_search_record_missing_key():
    rec = _good_record()
    del rec["typeLabel"]
    with pytest.raises(ValueError, match="search"):
        validate(_data_with_search(rec))


def test_validate_rejects_search_record_non_string_value():
    rec = _good_record()
    rec["title"] = 123
    with pytest.raises(ValueError, match="search"):
        validate(_data_with_search(rec))


def test_validate_rejects_unknown_search_type():
    rec = _good_record()
    rec["type"] = "bogus"
    with pytest.raises(ValueError, match="search"):
        validate(_data_with_search(rec))
```
- [ ] Run them — expect FAIL: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_schema.py -k "search" -q` → the reject tests fail (no enforcement yet).
- [ ] Implement. In `src/acc/schema.py`, after the `_REQUIRED_TOP` set (line 10), add:
```python
_SEARCH_KEYS = ("id", "type", "typeLabel", "title", "path", "text")
_KNOWN_SEARCH_TYPES = {
    "agent", "skill", "hook", "command", "mcpServer", "rule", "doc",
}


def _validate_search(records: list) -> None:
    if not isinstance(records, list):
        raise ValueError("search must be a list")
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            raise ValueError(f"search[{i}] is not an object")
        for key in _SEARCH_KEYS:
            if key not in rec:
                raise ValueError(f"search[{i}] missing key: {key!r}")
            if not isinstance(rec[key], str):
                raise ValueError(f"search[{i}].{key} must be a string")
        if rec["type"] not in _KNOWN_SEARCH_TYPES:
            raise ValueError(f"search[{i}] unknown type: {rec['type']!r}")
```
- [ ] Call it from `validate()`. In `src/acc/schema.py`, inside `validate()`, before `assert_no_secrets(data)` (line 51), add:
```python
    _validate_search(data["search"])
```
- [ ] Run to pass: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_schema.py tests/test_generate.py -q` → all pass (generate's real records satisfy the new check; light index passes via empty-string `text`).
- [ ] Commit: `git -C /Users/ozzy-mac/Projects/html-dash add src/acc/schema.py tests/test_schema.py && git -C /Users/ozzy-mac/Projects/html-dash commit -m "feat(phase-4a): validate enforces search-record shape and known type"`

---

### Task 7: app.js `htmlUnescape` helper + per-row `dataset.id`

Add `htmlUnescape(s)` that decodes the five entities `html.escape` produces — note Python emits `&#x27;` for `'` (not `&#39;`), and `&quot;` for `"`. Decode `&amp;` LAST so a literal `&amp;lt;` does not double-decode. Apply per-row `dataset.id` in `itemRow` and the docs/todos render paths so the id→row map (Task 9) can resolve hits. This is foundation for the omnibox.

**Files:**
- Modify: `src/acc/templates/app.js` (`el` at lines 6-11; `itemRow` lines 20-38; `renderDocs` lines 72-82; `renderTodos` lines 84-89)
- Test: `tests/test_render_dom.py`

- [ ] Write failing DOM test. Append to `tests/test_render_dom.py`:
```python
def test_rows_carry_dataset_id(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    # every rendered item row exposes a non-empty data-id for jump resolution
    rows = page.locator(".acc-item")
    n = rows.count()
    assert n > 0
    for i in range(n):
        assert rows.nth(i).get_attribute("data-id")


def test_htmlunescape_decodes_entities(page, tmp_path):
    make_brownfield_repo(tmp_path)
    page.set_content(_html(tmp_path))
    decoded = page.evaluate(
        "() => window.__accHtmlUnescape('AT&amp;T &lt;b&gt; &quot;q&quot; &#x27;s')")
    assert decoded == "AT&T <b> \"q\" 's"
```
- [ ] Run them — expect FAIL: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_render_dom.py -k "dataset_id or htmlunescape" -q` → no `data-id` / `window.__accHtmlUnescape is not a function`.
- [ ] Implement `htmlUnescape`. In `src/acc/templates/app.js`, after the `el` function (line 11), add:
```javascript
  // Decode the five entities html.escape (Python) produces. Applied ONLY at
  // textContent display and when building the omnibox match key, so search and
  // display see logical text (AT&T, not AT&amp;T) without an HTML sink — the
  // decoded value still reaches the DOM via textContent and stays inert.
  // Order matters: decode &amp; LAST so "&amp;lt;" does not double-decode.
  function htmlUnescape(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"')
      .replace(/&#x27;/g, "'")
      .replace(/&#39;/g, "'")
      .replace(/&amp;/g, "&");
  }
  // expose for DOM tests; harmless in production (no behavior, just a handle)
  window.__accHtmlUnescape = htmlUnescape;
```
- [ ] Apply `htmlUnescape` at display + add `dataset.id` in `itemRow`. In `src/acc/templates/app.js`, replace `itemRow` (lines 20-38):
```javascript
  function itemRow(opts) {
    var row = el("div", "acc-row acc-item");
    if (opts.id) row.dataset.id = opts.id;
    var head = el("div", "acc-rowhead");
    if (opts.provider) head.appendChild(el("span", "acc-chip", opts.provider));
    if (opts.typeLabel) head.appendChild(el("span", "badge", opts.typeLabel));
    head.appendChild(el("span", "acc-itemtitle", htmlUnescape(opts.title)));
    row.appendChild(head);
    if (opts.summary) row.appendChild(el("div", "acc-summary", htmlUnescape(opts.summary)));
    if (pathPrefix) {
      var a = el("a", "path", opts.path);
      a.href = encodedRelHref(pathPrefix, opts.path);
      row.appendChild(a);
    } else {
      row.appendChild(el("span", "path", opts.path));
    }
    row.dataset.search =
      (htmlUnescape(opts.title) + " " + opts.path + " " +
       htmlUnescape(opts.summary || "")).toLowerCase();
    return row;
  }
```
- [ ] Pass the id through the three render paths. In `renderDocs` (lines 72-82) change the `itemRow({...})` call to include `id: doc.id`:
```javascript
        host.appendChild(itemRow({
          id: doc.id, typeLabel: g, title: doc.title, path: doc.path, summary: doc.summary
        }));
```
  In `renderTodos` (lines 84-89) change the call to include `id: t.id`:
```javascript
      host.appendChild(itemRow({ id: t.id, title: t.text, path: t.path }));
```
  In `renderInventory` (lines 56-61) change the call to include `id: it.id`:
```javascript
        host.appendChild(itemRow({
          id: it.id, provider: it.provider, typeLabel: it.typeLabel,
          title: it.title, path: it.path, summary: it.summary
        }));
```
- [ ] Run to pass: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_render_dom.py -q` → all pass (existing Phase 3 DOM tests still green; `AT&T`-style display now decoded).
- [ ] Commit: `git -C /Users/ozzy-mac/Projects/html-dash add src/acc/templates/app.js tests/test_render_dom.py && git -C /Users/ozzy-mac/Projects/html-dash commit -m "feat(phase-4a): htmlUnescape helper + per-row data-id in render paths"`

---

### Task 8: dashboard.html.tmpl omnibox markup + relabel the per-view filter

Add the omnibox input and result panel to the header, and relabel the existing `#acc-search` so the two inputs do not read as duplicates. The omnibox is global Find; `#acc-search` is the per-view row filter.

**Files:**
- Modify: `src/acc/templates/dashboard.html.tmpl` (header lines 11-15)
- Test: `tests/test_render_dom.py`, `tests/test_render.py`

- [ ] Write failing test. Append to `tests/test_render_dom.py`:
```python
def test_omnibox_and_filter_inputs_distinct(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    omni = page.locator("#acc-omnibox")
    filt = page.locator("#acc-search")
    assert omni.count() == 1 and filt.count() == 1
    # relabeled so they don't read as duplicates
    assert "find" in (omni.get_attribute("aria-label") or "").lower()
    assert "filter" in (filt.get_attribute("aria-label") or "").lower()
    assert page.locator("#acc-omnibox-results").count() == 1
```
- [ ] Run it — expect FAIL: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_render_dom.py::test_omnibox_and_filter_inputs_distinct -q` → `#acc-omnibox` count 0.
- [ ] Implement. In `src/acc/templates/dashboard.html.tmpl`, replace the header block (lines 11-15):
```html
<header class="acc-head">
  <strong id="acc-title">Dashboard</strong>
  <div class="acc-omnibox-wrap">
    <input id="acc-omnibox" placeholder="Find anything…  ( / )" aria-label="Find across everything" autocomplete="off">
    <div id="acc-omnibox-results" class="acc-omnibox-results" hidden></div>
  </div>
  <input id="acc-search" placeholder="filter this view…" aria-label="Filter rows in view">
  <span class="acc-meta" id="acc-meta"></span>
</header>
```
- [ ] Run to pass: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_render_dom.py::test_omnibox_and_filter_inputs_distinct tests/test_render.py -q` → pass.
- [ ] Commit: `git -C /Users/ozzy-mac/Projects/html-dash add src/acc/templates/dashboard.html.tmpl tests/test_render_dom.py && git -C /Users/ozzy-mac/Projects/html-dash commit -m "feat(phase-4a): omnibox markup + relabel per-view filter input"`

---

### Task 9: app.js id→row map + jump (scrollIntoView + flash)

Build an `id → rowElement` Map while rendering the views, after all render paths run. Jump = look up the id in the map, `scrollIntoView`, toggle a transient `.acc-flash` class. Degrade cleanly when the id has no rendered row (empty bucket skipped, or light/truncated mode). Resolve through the map, never a selector built from item text.

**Files:**
- Modify: `src/acc/templates/app.js` (bootstrap lines 165-172)
- Test: `tests/test_render_dom.py`

- [ ] Write failing test. Append to `tests/test_render_dom.py`:
```python
def test_jump_scrolls_and_flashes_exact_row(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    target_id = page.evaluate("() => document.querySelector('#acc-inventory .acc-item').dataset.id")
    page.evaluate("(id) => window.__accJump(id)", target_id)
    row = page.locator('.acc-item[data-id="%s"]' % target_id)
    assert row.evaluate("el => el.classList.contains('acc-flash')")


def test_jump_unknown_id_does_not_throw(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    # an id with no rendered row must degrade silently (no exception)
    assert page.evaluate("() => { window.__accJump('nope_no_row'); return true; }") is True
```
- [ ] Run them — expect FAIL: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_render_dom.py -k "jump" -q` → `window.__accJump is not a function`.
- [ ] Implement. In `src/acc/templates/app.js`, after `wireSearch` (before the bootstrap at line 165), add:
```javascript
  var rowById = new Map();

  function buildRowIndex() {
    rowById.clear();
    document.querySelectorAll(".acc-item[data-id]").forEach(function (row) {
      // first rendered row wins for a given id (ids are stable + unique anyway)
      if (!rowById.has(row.dataset.id)) rowById.set(row.dataset.id, row);
    });
  }

  function jumpTo(id) {
    var row = rowById.get(id);
    if (!row) return; // degrade: empty bucket skipped, or light/truncated mode
    row.scrollIntoView({ block: "center" });
    row.classList.remove("acc-flash");
    // reflow so re-adding the class restarts the flash animation
    void row.offsetWidth;
    row.classList.add("acc-flash");
    window.setTimeout(function () { row.classList.remove("acc-flash"); }, 1600);
  }
  window.__accJump = jumpTo;
```
- [ ] Wire `buildRowIndex` into the bootstrap. In `src/acc/templates/app.js`, replace the bootstrap (lines 165-172):
```javascript
  renderHead();
  renderBanner();
  renderOverview();
  renderInventory();
  renderDocs();
  renderTodos();
  buildRowIndex();
  wireSearch();
})();
```
- [ ] Run to pass: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_render_dom.py -q` → all pass.
- [ ] Commit: `git -C /Users/ozzy-mac/Projects/html-dash add src/acc/templates/app.js tests/test_render_dom.py && git -C /Users/ozzy-mac/Projects/html-dash commit -m "feat(phase-4a): id->row map + scrollIntoView/flash jump infra"`

---

### Task 10: app.js omnibox — build/consume/group/snippet/`<mark>`/keyboard

The omnibox over `data.search`: focus via `/`, `Esc` clears+closes; debounced (~60 ms) literal lowercased substring match over `htmlUnescape(title + path + text)` (match key built once per record); group hits by `type` (heading = `typeLabel`) with per-group counts; cap rendered hits per group at 8 with a `+N more` line; each hit row = `htmlUnescape`d title + type chip + path + matched snippet, all via `el()`/`textContent`; highlight via splitting on the query and appending text nodes + `createElement('mark')` (no `innerHTML`); `↑`/`↓` move the active hit, `Enter` jumps via `jumpTo`; empty query hides the panel; no hits → "No matches"; light index (all `text===""`) → a one-line note that body search is off.

**Files:**
- Modify: `src/acc/templates/app.js` (add `wireOmnibox`; call in bootstrap)
- Test: `tests/test_render_dom.py`

- [ ] Write failing tests. Append to `tests/test_render_dom.py`:
```python
def test_omnibox_groups_hits_with_counts(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    page.fill("#acc-omnibox", "re")  # matches reviewer (agent) + refactor + references etc.
    page.wait_for_timeout(120)
    panel = page.locator("#acc-omnibox-results")
    assert panel.is_visible()
    groups = panel.locator(".acc-omni-group")
    assert groups.count() >= 1
    # each group has a heading with a count and at least one hit
    head = groups.first.locator(".acc-omni-grouphead")
    assert head.count() == 1
    import re as _re
    assert _re.search(r"\(\d+\)", head.inner_text())
    assert groups.first.locator(".acc-omni-hit").count() >= 1


def test_omnibox_matches_inventory_and_docs(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    page.fill("#acc-omnibox", "notes")  # docs/notes.md is a doc reference
    page.wait_for_timeout(120)
    panel = page.locator("#acc-omnibox-results")
    assert panel.locator(".acc-omni-group", has_text="Reference").count() == 1


def test_omnibox_highlights_with_mark_not_innerhtml(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    page.fill("#acc-omnibox", "review")  # reviewer agent
    page.wait_for_timeout(120)
    mark = page.locator("#acc-omnibox-results mark")
    assert mark.count() >= 1
    assert mark.first.inner_text().lower() == "review"


def test_omnibox_caps_group_with_more_line(page, tmp_path):
    # 12 docs so a single-letter query overflows the 8-hit cap in one group
    docs = tmp_path / "docs"
    docs.mkdir()
    for i in range(12):
        (docs / ("alpha_%02d.md" % i)).write_text("# Alpha %d\n\nbody" % i)
    page.set_content(_html(tmp_path))
    page.fill("#acc-omnibox", "alpha")
    page.wait_for_timeout(120)
    grp = page.locator("#acc-omnibox-results .acc-omni-group", has_text="Reference")
    assert grp.locator(".acc-omni-hit").count() == 8
    assert grp.locator(".acc-omni-more").count() == 1
    import re as _re
    assert _re.search(r"\+\s*\d+\s+more", grp.locator(".acc-omni-more").inner_text())


def test_omnibox_slash_focus_and_esc_close(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    page.locator("body").click()
    page.keyboard.press("/")
    assert page.evaluate("() => document.activeElement.id") == "acc-omnibox"
    page.fill("#acc-omnibox", "review")
    page.wait_for_timeout(120)
    assert page.locator("#acc-omnibox-results").is_visible()
    page.keyboard.press("Escape")
    assert page.locator("#acc-omnibox-results").is_hidden()
    assert page.input_value("#acc-omnibox") == ""


def test_omnibox_keyboard_nav_and_enter_jumps(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    page.fill("#acc-omnibox", "reviewer")
    page.wait_for_timeout(120)
    page.locator("#acc-omnibox").press("ArrowDown")
    assert page.locator("#acc-omnibox-results .acc-omni-hit.acc-omni-active").count() == 1
    page.locator("#acc-omnibox").press("Enter")
    # jump flashes the matching inventory row
    flashed = page.locator(".acc-item.acc-flash")
    assert flashed.count() == 1
    assert "reviewer" in flashed.inner_text().lower()


def test_omnibox_no_hits_message(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    page.fill("#acc-omnibox", "zzzznotathing")
    page.wait_for_timeout(120)
    panel = page.locator("#acc-omnibox-results")
    assert panel.is_visible()
    assert "no matches" in panel.inner_text().lower()


def test_omnibox_empty_query_hides_panel(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    page.fill("#acc-omnibox", "review")
    page.wait_for_timeout(120)
    page.fill("#acc-omnibox", "")
    page.wait_for_timeout(120)
    assert page.locator("#acc-omnibox-results").is_hidden()


def test_omnibox_at_and_t_logical_match_and_display(page, tmp_path):
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "att.md").write_text('---\nname: "AT&T"\ndescription: telecom\n---\n')
    page.set_content(_html(tmp_path))
    page.fill("#acc-omnibox", "at&t")  # logical text, not the entity
    page.wait_for_timeout(120)
    hit = page.locator("#acc-omnibox-results .acc-omni-hit", has_text="AT&T")
    assert hit.count() == 1
    assert "&amp;" not in hit.first.inner_text()  # decoded for display


def test_omnibox_hostile_body_is_inert(page, tmp_path):
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "evil.md").write_text(
        '---\nname: pwn\ndescription: "</script><img src=x onerror=window.__pwned=1>"\n---\n')
    page.set_content(_html(tmp_path))
    page.fill("#acc-omnibox", "pwn")
    page.wait_for_timeout(120)
    panel = page.locator("#acc-omnibox-results")
    assert panel.locator("img").count() == 0          # no raw HTML built
    assert page.evaluate("() => window.__pwned") is None  # no script ran


def test_omnibox_light_index_note(page, tmp_path):
    make_claude_repo(tmp_path)
    make_large_repo(tmp_path, 150)  # forces light index (text == "")
    page.set_content(_html(tmp_path))
    page.fill("#acc-omnibox", "reviewer")  # still matches by name
    page.wait_for_timeout(120)
    panel = page.locator("#acc-omnibox-results")
    assert panel.locator(".acc-omni-hit", has_text="reviewer").count() >= 1
    assert "body search is off" in panel.inner_text().lower()
```
- [ ] Run them — expect FAIL: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_render_dom.py -k omnibox -q` → no results panel populated.
- [ ] Implement `wireOmnibox`. In `src/acc/templates/app.js`, after `jumpTo`/`window.__accJump` (Task 9) and before the bootstrap, add:
```javascript
  var OMNI_GROUP_CAP = 8;
  var INV_TYPE_ORDER = ["agent", "command", "skill", "hook", "mcpServer", "rule", "doc"];

  function searchRecords() { return data.search || []; }

  function matchKey(rec) {
    if (rec.__key == null) {
      rec.__key = htmlUnescape(
        (rec.title || "") + " " + (rec.path || "") + " " + (rec.text || "")
      ).toLowerCase();
    }
    return rec.__key;
  }

  function isLightIndex() {
    var recs = searchRecords();
    return recs.length > 0 && recs.every(function (r) { return (r.text || "") === ""; });
  }

  // Append text + <mark> nodes by splitting the logical string on the query.
  // No innerHTML, no string-built markup — every node uses textContent.
  function appendHighlighted(target, logical, qLower) {
    if (!qLower) { target.appendChild(document.createTextNode(logical)); return; }
    var hay = logical.toLowerCase();
    var from = 0, idx;
    while ((idx = hay.indexOf(qLower, from)) !== -1) {
      if (idx > from) target.appendChild(document.createTextNode(logical.slice(from, idx)));
      var m = document.createElement("mark");
      m.textContent = logical.slice(idx, idx + qLower.length);
      target.appendChild(m);
      from = idx + qLower.length;
    }
    if (from < logical.length) target.appendChild(document.createTextNode(logical.slice(from)));
  }

  function snippetFor(rec, qLower) {
    var logical = htmlUnescape(rec.text || "");
    var idx = logical.toLowerCase().indexOf(qLower);
    if (idx === -1) return logical.slice(0, 120);
    var start = Math.max(0, idx - 40);
    var end = Math.min(logical.length, idx + qLower.length + 80);
    return (start > 0 ? "…" : "") + logical.slice(start, end) + (end < logical.length ? "…" : "");
  }

  function wireOmnibox() {
    var box = document.getElementById("acc-omnibox");
    var panel = document.getElementById("acc-omnibox-results");
    if (!box || !panel) return;
    var hits = [];        // flat list of {rec} in render order
    var active = -1;
    var timer = null;

    function close() { panel.hidden = true; panel.textContent = ""; hits = []; active = -1; }

    function setActive(i) {
      var nodes = panel.querySelectorAll(".acc-omni-hit");
      if (active >= 0 && nodes[active]) nodes[active].classList.remove("acc-omni-active");
      active = i;
      if (active >= 0 && nodes[active]) {
        nodes[active].classList.add("acc-omni-active");
        nodes[active].scrollIntoView({ block: "nearest" });
      }
    }

    function render(q) {
      panel.textContent = "";
      hits = [];
      active = -1;
      var qLower = q.toLowerCase();
      if (!qLower) { close(); return; }
      panel.hidden = false;

      if (isLightIndex()) {
        panel.appendChild(el("div", "acc-omni-note",
          "Body search is off (index reduced for size); searching names and paths only."));
      }

      // group records by type, preserving a stable type order
      var byType = {};
      searchRecords().forEach(function (rec) {
        if (matchKey(rec).indexOf(qLower) === -1) return;
        (byType[rec.type] || (byType[rec.type] = [])).push(rec);
      });
      var types = INV_TYPE_ORDER.filter(function (t) { return byType[t]; });
      Object.keys(byType).forEach(function (t) {
        if (types.indexOf(t) === -1) types.push(t);
      });

      if (!types.length) {
        panel.appendChild(el("div", "acc-omni-note", "No matches"));
        return;
      }

      types.forEach(function (t) {
        var recs = byType[t];
        var group = el("div", "acc-omni-group");
        group.appendChild(el("div", "acc-omni-grouphead",
          (recs[0].typeLabel || t) + " (" + recs.length + ")"));
        recs.slice(0, OMNI_GROUP_CAP).forEach(function (rec) {
          var hit = el("div", "acc-omni-hit");
          hit.dataset.id = rec.id;
          var titleEl = el("span", "acc-omni-title");
          appendHighlighted(titleEl, htmlUnescape(rec.title || ""), qLower);
          hit.appendChild(titleEl);
          hit.appendChild(el("span", "acc-chip", rec.typeLabel || t));
          hit.appendChild(el("span", "path", rec.path || ""));
          if ((rec.text || "") !== "") {
            var snipEl = el("span", "acc-omni-snippet");
            appendHighlighted(snipEl, snippetFor(rec, qLower), qLower);
            hit.appendChild(snipEl);
          }
          hit.addEventListener("click", function () { jumpTo(rec.id); });
          group.appendChild(hit);
          hits.push(rec);
        });
        if (recs.length > OMNI_GROUP_CAP) {
          group.appendChild(el("div", "acc-omni-more",
            "+" + (recs.length - OMNI_GROUP_CAP) + " more"));
        }
        panel.appendChild(group);
      });
    }

    box.addEventListener("input", function () {
      if (timer) window.clearTimeout(timer);
      timer = window.setTimeout(function () { render(box.value); }, 60);
    });
    box.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { box.value = ""; close(); return; }
      if (e.key === "ArrowDown") { e.preventDefault(); if (hits.length) setActive(Math.min(active + 1, hits.length - 1)); }
      else if (e.key === "ArrowUp") { e.preventDefault(); if (hits.length) setActive(Math.max(active - 1, 0)); }
      else if (e.key === "Enter") {
        e.preventDefault();
        var pick = active >= 0 ? active : 0;
        if (hits[pick]) jumpTo(hits[pick].id);
      }
    });
    // "/" focuses the omnibox unless a field is already focused
    document.addEventListener("keydown", function (e) {
      if (e.key !== "/") return;
      var a = document.activeElement;
      var tag = a && a.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || (a && a.isContentEditable)) return;
      e.preventDefault();
      box.focus();
    });
  }
```
- [ ] Wire it in. In `src/acc/templates/app.js`, in the bootstrap (after `buildRowIndex();` from Task 9, before `wireSearch();`), add `wireOmnibox();`:
```javascript
  buildRowIndex();
  wireOmnibox();
  wireSearch();
})();
```
- [ ] Run to pass: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_render_dom.py -q` → all pass.
- [ ] Commit: `git -C /Users/ozzy-mac/Projects/html-dash add src/acc/templates/app.js tests/test_render_dom.py && git -C /Users/ozzy-mac/Projects/html-dash commit -m "feat(phase-4a): global omnibox over data.search (group/snippet/mark/keyboard/jump)"`

---

### Task 11: styles.css — omnibox panel, `<mark>`, type chip, flash

Style the omnibox input/panel, hit rows, group heads, `+N more`, the note line, `<mark>` highlight, and the `.acc-flash` jump-flash animation. Reuse existing vars/classes (`--fg`, `--muted`, `--line`, `--bg`, `.acc-chip`, `.path`). This is presentation; a DOM smoke test confirms the panel positions and the flash class is defined.

**Files:**
- Modify: `src/acc/templates/styles.css` (append after line 34)
- Test: `tests/test_render_dom.py`

- [ ] Write failing test. Append to `tests/test_render_dom.py`:
```python
def test_omnibox_panel_styled_and_flash_defined(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    page.fill("#acc-omnibox", "review")
    page.wait_for_timeout(120)
    panel = page.locator("#acc-omnibox-results")
    # panel is absolutely positioned (a dropdown), not static
    assert panel.evaluate("el => getComputedStyle(el).position") == "absolute"
    # mark has a non-transparent background (highlight is visible)
    bg = page.locator("#acc-omnibox-results mark").first.evaluate(
        "el => getComputedStyle(el).backgroundColor")
    assert bg not in ("rgba(0, 0, 0, 0)", "transparent")
```
- [ ] Run it — expect FAIL: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_render_dom.py::test_omnibox_panel_styled_and_flash_defined -q` → position `static`.
- [ ] Implement. Append to `src/acc/templates/styles.css`:
```css
.acc-omnibox-wrap { position: relative; flex: 1 1 280px; max-width: 520px; }
#acc-omnibox { width: 100%; padding: 4px 10px; border: 1px solid var(--line); border-radius: 6px; background: transparent; color: var(--fg); }
.acc-omnibox-results { position: absolute; top: calc(100% + 4px); left: 0; right: 0; z-index: 20;
  max-height: 60vh; overflow: auto; background: var(--bg); border: 1px solid var(--line); border-radius: 8px; padding: 4px; }
.acc-omnibox-results[hidden] { display: none; }
.acc-omni-group { padding: 4px 2px; }
.acc-omni-grouphead { text-transform: uppercase; letter-spacing: .05em; font-size: 11px; color: var(--muted); margin: 6px 2px 2px; }
.acc-omni-hit { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; padding: 4px 6px; border-radius: 6px; cursor: pointer; }
.acc-omni-hit:hover, .acc-omni-hit.acc-omni-active { background: color-mix(in srgb, var(--fg) 8%, transparent); }
.acc-omni-title { font-weight: 600; }
.acc-omni-snippet { color: var(--muted); font-size: 12px; flex-basis: 100%; }
.acc-omni-more { color: var(--muted); font-size: 11px; padding: 2px 6px; }
.acc-omni-note { color: var(--muted); font-size: 12px; padding: 4px 6px; }
mark { background: #ffe066; color: #1a1a1a; border-radius: 2px; padding: 0 1px; }
@keyframes acc-flash-kf { from { background: #ffe066; } to { background: transparent; } }
.acc-flash { animation: acc-flash-kf 1.6s ease-out; }
```
- [ ] Run to pass: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_render_dom.py -q` → all pass.
- [ ] Commit: `git -C /Users/ozzy-mac/Projects/html-dash add src/acc/templates/styles.css tests/test_render_dom.py && git -C /Users/ozzy-mac/Projects/html-dash commit -m "feat(phase-4a): omnibox panel, mark highlight, and jump-flash styles"`

---

### Task 12: CI guard — no `innerHTML`/`outerHTML`/`insertAdjacentHTML` in app.js

A pytest test that reads the shipped `app.js` and fails if any banned HTML sink appears. This is the regression guard the spec requires.

**Files:**
- Create: `tests/test_appjs_guard.py`

- [ ] Write the test (it doubles as the failing check if a sink exists). Create `tests/test_appjs_guard.py`:
```python
import re
from importlib.resources import files

_BANNED = re.compile(r"innerHTML|outerHTML|insertAdjacentHTML")


def _app_js() -> str:
    return files("acc").joinpath("templates", "app.js").read_text(encoding="utf-8")


def test_app_js_has_no_html_sinks():
    src = _app_js()
    matches = [ln for ln in src.splitlines() if _BANNED.search(ln)]
    assert not matches, "banned HTML sink in app.js: %r" % matches
```
- [ ] Run it — expect PASS now (the omnibox uses only `el()`/`textContent`/`createElement('mark')`): `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_appjs_guard.py -q` → pass. (To confirm the guard actually bites: temporarily add a line `x.innerHTML = "y";` to `app.js`, rerun → FAIL `banned HTML sink`, then revert.)
- [ ] Commit: `git -C /Users/ozzy-mac/Projects/html-dash add tests/test_appjs_guard.py && git -C /Users/ozzy-mac/Projects/html-dash commit -m "test(phase-4a): CI guard rejecting innerHTML/outerHTML/insertAdjacentHTML in app.js"`

---

### Task 13: Full-suite + lint + determinism gate

Final gate: whole test suite green, ruff clean, output byte-identical across runs.

**Files:**
- Test: all of `tests/`

- [ ] Run the full suite: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest -q` → all pass (unit + schema + DOM + guard).
- [ ] Lint: `cd /Users/ozzy-mac/Projects/html-dash && ruff check src/` → no errors. (If `ruff` is not on PATH, `python3 -m ruff check src/`.)
- [ ] Determinism spot-check: `cd /Users/ozzy-mac/Projects/html-dash && python3 -m pytest tests/test_generate.py -k deterministic -q` → pass (byte-identical output already asserted by `test_generate_is_deterministic` and `test_generate_multi_provider_is_deterministic`; the explicit `_build_search` sort keeps the new fields ordered).
- [ ] No commit (gate only). If any step fails, fix in the owning task and re-run.

---

## Plan author notes

**Spec-vs-code mismatches found (and how the plan handles them):**

1. **Branch base is wrong — the biggest one.** The spec was written against the Phase 3 branch (`feature/phase-3-renderer`, tip `32bf625`), which contains every symbol the spec references: `itemRow`, `renderInventory`/`renderDocs`/`renderTodos`, `_reduce_for_size`, `_WARN_BYTES`/`_TRUNCATE_BYTES`, `_path_prefix`, `source.pathPrefix`, `generator.truncated`, the Overview bento, and the Playwright DOM harness `tests/test_render_dom.py`. But the current branch `feature/phase-4a-find` (HEAD `89a2fa5`) was cut from before Phase 3 merged — its parent chain ends at `17bb59a`, and `git merge-base --is-ancestor feature/phase-3-renderer HEAD` returns 1 (NOT an ancestor). The working-tree files are the pre-Phase-3 versions: `app.js` is 60 lines with no `itemRow`; `generate.py` has no `_reduce_for_size`/`_WARN_BYTES`. **Task 0 rebases the spec commit onto Phase 3** before any code task; every code block in the plan is written against the verified Phase 3 source (read via `git show feature/phase-3-renderer:<path>`).

2. **`html.escape` emits `&#x27;`, not `&#39;`.** The spec says `htmlUnescape` should decode `&#39;`. Python's `html.escape` actually produces `&#x27;` for `'` (verified: `html.escape("'")` → `&#x27;`). Task 7's helper decodes **both** `&#x27;` and `&#39;` (and `&quot;` for `"`), so it is correct against the real island and robust to either form.

3. **Docs lack `type`/`typeLabel` AND a usable raw body.** Confirmed: doc records carry only `{id,title,path,summary,html}` (no `type`/`typeLabel`), and the body lives in the separately-sanitized `html` field. The plan synthesizes `type="doc"` + a bucket-derived `typeLabel` (Task 1 `doc_type_label`, Task 4) and, per the spec's resolved open question, slices the doc `summary` (not `html`) for the body slice (Task 3).

4. **Inventory items have no raw body field today.** Confirmed `make_item` yields `{id,provider,type,typeLabel,title,path,summary}` — no body. The plan's slice source falls back to the escaped `summary` for inventory, with a live `_rawBody` branch ready for any future adapter that adds one (matches the spec's "raw body for inventory items that have one" wording without inventing a field).

5. **TODOs lack ids — confirmed** (`_extract_todos` builds `{text,path}` only). Task 2 adds `stable_id("generic","todo",path,text)`.

6. **`_searchBody` private key would leak into the island.** Because `inv`/`docs` are serialized whole into `data`, the temporary slice key must be stripped after `_build_search`. Task 4 adds an explicit `.pop("_searchBody", None)` pass and a guard test (`test_private_search_body_key_not_in_island`).

7. **The Phase 3 test `test_over_2mb_truncates_to_summary_only` asserts `data["search"] == []`.** Task 5 updates that assertion (the light index now survives truncation) — flagged so the implementer does not treat it as a regression.

**Test directory / naming convention matched:** `tests/` flat layout, `pythonpath=["src"]` + `testpaths=["tests"]` in `pyproject.toml`, no `conftest.py`. Unit/generate tests are plain `def test_*(tmp_path)` importing `from acc.generate import ...` and `from tests.builders import ...`, reading the island via the local `_island(out_path)` helper. Playwright DOM tests live in `tests/test_render_dom.py`, take the `page` fixture from `pytest-playwright` (declared in the `[project.optional-dependencies] test` extra on the Phase 3 branch), and load HTML with `page.set_content(_html(repo))` (real Chromium, no server/`file://`) — the plan's DOM tests copy that exact pattern, fixture, and the `_html`/builder imports. Tests run with `python3 -m pytest -q`; lint with `ruff check src/`.

**Self-review result:**
- *Spec coverage* — every acceptance criterion maps to a step: `/` focus + `Esc` (Task 10 `test_omnibox_slash_focus_and_esc_close`); `↑`/`↓` + `Enter` jump (Task 10 `test_omnibox_keyboard_nav_and_enter_jumps`); group + count across inventory **and** docs, no undefined group (Tasks 4/10 `test_build_search_record_shape_and_doc_type_label`, `test_omnibox_matches_inventory_and_docs`); jump scrolls + flashes exact row (Task 9 `test_jump_scrolls_and_flashes_exact_row`); match name/path/summary/body (Task 10 group tests + Task 4 body-slice test); `AT&T` logical match + display (Task 10 `test_omnibox_at_and_t_logical_match_and_display`); hostile `</script><img onerror>` inert (Tasks 4/10 `test_build_search_escapes_hostile_slice_in_island`, `test_omnibox_hostile_body_is_inert`); grep returns nothing (Task 12); byte-identical + under budget + light-mode find (Tasks 5/13 + `test_omnibox_light_index_note`); per-view filter distinct (Task 8 `test_omnibox_and_filter_inputs_distinct`). Every item in the spec's "Testing" list has a corresponding test. No coverage gaps remained after review; the `_searchBody`-leak gap was caught and closed with Task 4's pop + guard test.
- *Placeholder scan* — no "TBD"/"similar to"/"add error handling"/"write tests for the above". Every step shows complete code or an exact command + expected message.
- *Type/signature consistency* — helper names are spelled identically across tasks: `doc_type_label` (Tasks 1, 4), `_SEARCH_BODY_CHARS` (Tasks 3, 4), `_searchBody` private key (Tasks 3, 4), `_search_record` (Task 4), `_validate_search`/`_KNOWN_SEARCH_TYPES` (Task 6), `htmlUnescape`/`window.__accHtmlUnescape` (Task 7), `buildRowIndex`/`rowById`/`jumpTo`/`window.__accJump` (Task 9), `wireOmnibox`/`matchKey`/`appendHighlighted`/`snippetFor`/`OMNI_GROUP_CAP`/`INV_TYPE_ORDER` (Task 10), CSS classes `acc-omni-group`/`acc-omni-grouphead`/`acc-omni-hit`/`acc-omni-active`/`acc-omni-snippet`/`acc-omni-more`/`acc-omni-note`/`acc-flash` (Tasks 10, 11). DOM ids `#acc-omnibox`/`#acc-omnibox-results` consistent across Tasks 8, 10, 11.agentId: ad3e4ec3e311616fe (use SendMessage with to: 'ad3e4ec3e311616fe' to continue this agent)
<usage>subagent_tokens: 195313
tool_uses: 145
duration_ms: 1520470</usage>
