# AI Control Center — Phase 1 (deterministic core + generic dashboard) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic extraction core and a generic-fallback adapter that stamps one self-contained, redacted, byte-stable `dashboard.html` for any repo.

**Architecture:** A stdlib-only `python3` package scans a repo's files, a generic adapter turns markdown into normalized data, secrets are redacted at extraction, the data is canonicalized and inlined as a JSON island, and a bundled HTML template plus classic inline JS renders the view. No third-party runtime dependencies. Output is deterministic so re-stamping produces no diff when content is unchanged.

**Tech Stack:** Python 3.12 (stdlib only at runtime), pytest (dev only), HTML + classic JS template.

This is Phase 1 of 4 (see the design spec at `docs/superpowers/specs/2026-05-29-ai-control-center-design.md`). Phases 2-4 (first-class adapters, full renderer, refresh + packaging) get their own plans.

---

## File structure

```text
ai-control-center/
  pyproject.toml                 # package metadata, pytest config (dev)
  src/acc/
    __init__.py                  # version constant
    ids.py                       # stable_id(), rel_posix()
    redaction.py                 # redact_text(), allowlist_config()
    scan.py                      # scan_files(), DEFAULT_EXCLUDES
    markdown.py                  # render_markdown_safe()
    digest.py                    # source_digest()
    schema.py                    # SCHEMA_VERSION, canonical_json(), validate()
    render.py                    # render_html()
    generate.py                  # generate(), detect_out_dir()
    cli.py                       # main() entry point
    adapters/
      __init__.py
      base.py                    # ScanContext, ProviderRoot, ProviderAdapter
      generic.py                 # GenericAdapter
  templates/
    dashboard.html.tmpl          # static shell, layout B, placeholders
    styles.css                   # inlined at render
    app.js                       # classic JS, builds DOM from JSON island
  tests/
    test_ids.py
    test_redaction.py
    test_scan.py
    test_markdown.py
    test_digest.py
    test_schema.py
    test_generic_adapter.py
    test_render.py
    test_generate.py             # determinism, redaction, XSS integration
    fixtures/
      sample_repo/               # built inside the test, not committed raw
```

Each module has one responsibility. `generate.py` is the only place that wires them together. Adapters depend on `ids`, `redaction`, `markdown` but never on each other.

---

## Task 0: Scaffold the package

**Files:**
- Create: `pyproject.toml`
- Create: `src/acc/__init__.py`
- Create: `src/acc/adapters/__init__.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "ai-control-center"
version = "0.1.0"
description = "Self-contained HTML control center generated from a repo's AI markdown"
requires-python = ">=3.12"

[project.scripts]
acc = "acc.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: Create the package init files**

`src/acc/__init__.py`:

```python
__version__ = "0.1.0"
```

`src/acc/adapters/__init__.py`:

```python
```

(empty file)

- [ ] **Step 3: Verify the dev environment**

Run: `python -m pytest --version`
Expected: pytest prints its version (install with `pip install pytest` if missing).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml src/acc/__init__.py src/acc/adapters/__init__.py
git commit -m "chore: scaffold acc package"
```

---

## Task 1: Stable IDs and repo-relative paths

**Files:**
- Create: `src/acc/ids.py`
- Test: `tests/test_ids.py`

- [ ] **Step 1: Write the failing test**

`tests/test_ids.py`:

```python
from pathlib import Path
from acc.ids import stable_id, rel_posix


def test_stable_id_is_deterministic_and_12_chars():
    a = stable_id("generic", "doc", "docs/x.md", "Title")
    b = stable_id("generic", "doc", "docs/x.md", "Title")
    assert a == b
    assert len(a) == 12
    assert a.isalnum()


def test_stable_id_changes_with_inputs():
    base = stable_id("generic", "doc", "docs/x.md", "Title")
    assert base != stable_id("claude", "doc", "docs/x.md", "Title")
    assert base != stable_id("generic", "skill", "docs/x.md", "Title")
    assert base != stable_id("generic", "doc", "docs/y.md", "Title")


def test_rel_posix_uses_forward_slashes(tmp_path):
    root = tmp_path
    f = root / "sub" / "a.md"
    f.parent.mkdir(parents=True)
    f.write_text("hi")
    assert rel_posix(f, root) == "sub/a.md"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ids.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acc.ids'`

- [ ] **Step 3: Write minimal implementation**

`src/acc/ids.py`:

```python
import hashlib
from pathlib import Path


def stable_id(provider: str, kind: str, rel_path: str, heading: str = "") -> str:
    raw = f"{provider}\0{kind}\0{rel_path}\0{heading}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def rel_posix(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ids.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/acc/ids.py tests/test_ids.py
git commit -m "feat: stable IDs and repo-relative paths"
```

---

## Task 2: Redaction at extraction

**Files:**
- Create: `src/acc/redaction.py`
- Test: `tests/test_redaction.py`

- [ ] **Step 1: Write the failing test**

`tests/test_redaction.py`:

```python
from acc.redaction import redact_text, allowlist_config


def test_redacts_bearer_token():
    out, n = redact_text("Authorization: Bearer abcDEF123456789")
    assert "abcDEF123456789" not in out
    assert n == 1


def test_redacts_keyword_assignment():
    out, n = redact_text('api_key = "sk-supersecretvalue123"')
    assert "supersecretvalue" not in out
    assert n >= 1


def test_redacts_provider_prefixed_key():
    out, n = redact_text("token ghp_0123456789abcdefghij")
    assert "ghp_0123456789abcdefghij" not in out
    assert n >= 1


def test_redacts_url_with_credentials():
    out, n = redact_text("postgres://user:p4ssw0rd@db.example.com/app")
    assert "p4ssw0rd" not in out
    assert n == 1


def test_leaves_clean_text_untouched():
    text = "This is a normal sentence about skills and agents."
    out, n = redact_text(text)
    assert out == text
    assert n == 0


def test_allowlist_drops_unlisted_keys_and_redacts_values():
    cfg = {"command": "npx", "args": ["-y", "pkg", "--token", "ghp_0123456789abcdefghij"],
           "env": {"SECRET": "x"}}
    clean = allowlist_config(cfg, {"command", "args"})
    assert "env" not in clean
    assert clean["command"] == "npx"
    assert "ghp_0123456789abcdefghij" not in " ".join(clean["args"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_redaction.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acc.redaction'`

- [ ] **Step 3: Write minimal implementation**

`src/acc/redaction.py`:

```python
import re

REDACTED = "[redacted]"

_SECRET_PATTERNS = [
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|secret|access[_-]?token|token|password|passwd|pwd|client[_-]?secret)\b"
        r"\s*[:=]\s*[\"']?[^\s\"']{6,}"
    ),
    re.compile(r"\b(?:sk|pk|gho|ghp|ghs|xox[baprs])[-_][A-Za-z0-9]{10,}"),
    re.compile(r"(?i)\b[a-z][a-z0-9+.\-]*://[^/\s:@]+:[^/\s:@]+@\S+"),
]


def redact_text(text: str) -> tuple[str, int]:
    n = 0
    for pat in _SECRET_PATTERNS:
        text, count = pat.subn(REDACTED, text)
        n += count
    return text, n


def allowlist_config(config: dict, allowed: set[str]) -> dict:
    clean: dict = {}
    for key, value in config.items():
        if key not in allowed:
            continue
        clean[key] = _redact_value(value)
    return clean


def _redact_value(value):
    if isinstance(value, str):
        return redact_text(value)[0]
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    return value
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_redaction.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/acc/redaction.py tests/test_redaction.py
git commit -m "feat: redaction-at-extraction with allowlist"
```

---

## Task 3: File scanning with exclusions

**Files:**
- Create: `src/acc/scan.py`
- Test: `tests/test_scan.py`

- [ ] **Step 1: Write the failing test**

`tests/test_scan.py`:

```python
from acc.scan import scan_files, DEFAULT_EXCLUDES


def test_scan_is_sorted_and_relative(tmp_path):
    (tmp_path / "b.md").write_text("b")
    (tmp_path / "a.md").write_text("a")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.md").write_text("c")
    rels = [p.relative_to(tmp_path).as_posix() for p in scan_files(tmp_path)]
    assert rels == ["a.md", "b.md", "sub/c.md"]


def test_scan_excludes_known_dirs(tmp_path):
    (tmp_path / "keep.md").write_text("k")
    for bad in DEFAULT_EXCLUDES:
        d = tmp_path / bad
        d.mkdir()
        (d / "skip.md").write_text("s")
    rels = [p.relative_to(tmp_path).as_posix() for p in scan_files(tmp_path)]
    assert rels == ["keep.md"]


def test_scan_skips_symlinks(tmp_path):
    real = tmp_path / "real.md"
    real.write_text("r")
    (tmp_path / "link.md").symlink_to(real)
    rels = [p.relative_to(tmp_path).as_posix() for p in scan_files(tmp_path)]
    assert rels == ["real.md"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scan.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acc.scan'`

- [ ] **Step 3: Write minimal implementation**

`src/acc/scan.py`:

```python
from pathlib import Path

DEFAULT_EXCLUDES = {
    ".git", "node_modules", ".venv", "venv", "__pycache__",
    ".superpowers", ".remember", "dist", "build", ".next", "vendor",
}


def scan_files(root: Path, excludes: set[str] = DEFAULT_EXCLUDES) -> list[Path]:
    root = root.resolve()
    out: list[Path] = []
    for p in root.rglob("*"):
        if p.is_symlink() or not p.is_file():
            continue
        rel_parts = set(p.relative_to(root).parts)
        if rel_parts & excludes:
            continue
        out.append(p)
    return sorted(out, key=lambda x: x.relative_to(root).as_posix())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_scan.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/acc/scan.py tests/test_scan.py
git commit -m "feat: deterministic file scan with exclusions"
```

---

## Task 4: Safe markdown rendering

**Files:**
- Create: `src/acc/markdown.py`
- Test: `tests/test_markdown.py`

- [ ] **Step 1: Write the failing test**

`tests/test_markdown.py`:

```python
from acc.markdown import render_markdown_safe


def test_renders_heading_and_paragraph():
    html = render_markdown_safe("# Title\n\nHello world")
    assert "<h1>Title</h1>" in html
    assert "<p>Hello world</p>" in html


def test_renders_list():
    html = render_markdown_safe("- one\n- two")
    assert "<ul>" in html and "<li>one</li>" in html and "<li>two</li>" in html


def test_escapes_raw_html_and_scripts():
    html = render_markdown_safe("normal <script>alert(1)</script> text")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_blocks_javascript_links():
    html = render_markdown_safe("[click](javascript:alert(1))")
    assert 'href="javascript:' not in html


def test_blocks_javascript_md_suffix_bypass():
    html = render_markdown_safe("[x](javascript:void0//y.md)")
    assert 'href="javascript:' not in html


def test_blocks_protocol_relative_links():
    html = render_markdown_safe("[x](//evil.com/exfil)")
    assert 'href="//evil.com' not in html


def test_allows_relative_and_https_links():
    html = render_markdown_safe("[doc](./x.md) and [site](https://example.com)")
    assert 'href="./x.md"' in html
    assert 'href="https://example.com"' in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_markdown.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acc.markdown'`

- [ ] **Step 3: Write minimal implementation**

`src/acc/markdown.py`:

```python
import html
import re
from urllib.parse import urlparse

_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_CODE = re.compile(r"`([^`]+)`")
_HEADING = re.compile(r"(#{1,6})\s+(.*)")
_LIST_ITEM = re.compile(r"\s*[-*]\s+")


def _safe_link(match: re.Match) -> str:
    # validate the scheme explicitly — never by suffix. A suffix check like
    # url.endswith(".md") lets `javascript:void0//y.md` through with a live href.
    label, url = match.group(1), match.group(2)
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    is_relative = not parsed.scheme and not url.startswith("//")  # block //host too
    if scheme in ("http", "https") or is_relative:
        return f'<a href="{url}">{label}</a>'
    return f"{label} ({url})"


def _inline(text: str) -> str:
    text = html.escape(text)
    text = _CODE.sub(lambda m: f"<code>{m.group(1)}</code>", text)
    text = _LINK.sub(_safe_link, text)
    return text


def render_markdown_safe(md: str) -> str:
    out: list[str] = []
    list_buf: list[str] = []
    code_buf: list[str] = []
    in_code = False

    def flush_list() -> None:
        if list_buf:
            items = "".join(f"<li>{_inline(x)}</li>" for x in list_buf)
            out.append(f"<ul>{items}</ul>")
            list_buf.clear()

    for line in md.splitlines():
        if line.strip().startswith("```"):
            if in_code:
                out.append("<pre><code>" + html.escape("\n".join(code_buf)) + "</code></pre>")
                code_buf.clear()
                in_code = False
            else:
                flush_list()
                in_code = True
            continue
        if in_code:
            code_buf.append(line)
            continue
        heading = _HEADING.match(line)
        if heading:
            flush_list()
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
        elif _LIST_ITEM.match(line):
            list_buf.append(_LIST_ITEM.sub("", line, count=1))
        elif line.strip() == "":
            flush_list()
        else:
            flush_list()
            out.append(f"<p>{_inline(line)}</p>")

    flush_list()
    if in_code:
        out.append("<pre><code>" + html.escape("\n".join(code_buf)) + "</code></pre>")
    return "\n".join(out)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_markdown.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/acc/markdown.py tests/test_markdown.py
git commit -m "feat: safe markdown subset renderer"
```

---

## Task 5: Source digest

**Files:**
- Create: `src/acc/digest.py`
- Test: `tests/test_digest.py`

- [ ] **Step 1: Write the failing test**

`tests/test_digest.py`:

```python
from acc.digest import source_digest
from acc.scan import scan_files


def test_digest_is_stable(tmp_path):
    (tmp_path / "a.md").write_text("hello")
    files = scan_files(tmp_path)
    assert source_digest(files, tmp_path) == source_digest(files, tmp_path)


def test_digest_changes_with_content(tmp_path):
    (tmp_path / "a.md").write_text("hello")
    before = source_digest(scan_files(tmp_path), tmp_path)
    (tmp_path / "a.md").write_text("hello world")
    after = source_digest(scan_files(tmp_path), tmp_path)
    assert before != after
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_digest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acc.digest'`

- [ ] **Step 3: Write minimal implementation**

`src/acc/digest.py`:

```python
import hashlib
from pathlib import Path


def source_digest(files: list[Path], root: Path) -> str:
    root = root.resolve()
    h = hashlib.sha256()
    for p in sorted(files, key=lambda x: x.resolve().relative_to(root).as_posix()):
        rel = p.resolve().relative_to(root).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()[:16]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_digest.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/acc/digest.py tests/test_digest.py
git commit -m "feat: content-derived source digest"
```

---

## Task 6: Schema canonicalization and validation

**Files:**
- Create: `src/acc/schema.py`
- Test: `tests/test_schema.py`

- [ ] **Step 1: Write the failing test**

`tests/test_schema.py`:

```python
import pytest
from acc.schema import SCHEMA_VERSION, canonical_json, validate


def _minimal_data() -> dict:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generator": {"name": "ai-control-center", "version": "0.1.0", "rendererDigest": "x"},
        "source": {"repoName": "r", "dashboardPath": ".ai-control-center/dashboard.html",
                   "sourceDigest": "abc", "vcs": {"kind": "none"}},
        "providers": [],
        "project": {"title": "r", "openTodos": [], "recentDocs": [], "warnings": []},
        "inventory": {"agents": [], "skills": [], "hooks": [], "commands": [], "mcpServers": [], "rules": []},
        "docs": {"prds": [], "adrs": [], "decisions": [], "workflows": [], "references": []},
        "relationships": [],
        "search": [],
    }


def test_canonical_json_is_sorted_and_stable():
    a = canonical_json({"b": 1, "a": 2})
    b = canonical_json({"a": 2, "b": 1})
    assert a == b == '{"a":2,"b":1}'


def test_validate_accepts_minimal_data():
    validate(_minimal_data())  # no exception


def test_validate_rejects_missing_keys():
    data = _minimal_data()
    del data["docs"]
    with pytest.raises(ValueError, match="docs"):
        validate(data)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acc.schema'`

- [ ] **Step 3: Write minimal implementation**

`src/acc/schema.py`:

```python
import json

SCHEMA_VERSION = "1.0"

_REQUIRED_TOP = {
    "schemaVersion", "generator", "source", "providers",
    "project", "inventory", "docs", "relationships", "search",
}


def canonical_json(data: dict) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def validate(data: dict) -> None:
    missing = _REQUIRED_TOP - data.keys()
    if missing:
        raise ValueError(f"missing required keys: {sorted(missing)}")
    if data["schemaVersion"] != SCHEMA_VERSION:
        raise ValueError(f"unexpected schemaVersion: {data['schemaVersion']!r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_schema.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/acc/schema.py tests/test_schema.py
git commit -m "feat: schema canonical JSON and validation"
```

---

## Task 7: Adapter base and generic adapter

**Files:**
- Create: `src/acc/adapters/base.py`
- Create: `src/acc/adapters/generic.py`
- Test: `tests/test_generic_adapter.py`

- [ ] **Step 1: Write the failing test**

`tests/test_generic_adapter.py`:

```python
from acc.adapters.base import ScanContext
from acc.adapters.generic import GenericAdapter
from acc.scan import scan_files


def _ctx(tmp_path):
    return ScanContext(root=tmp_path, files=scan_files(tmp_path))


def test_generic_extracts_docs_and_headings(tmp_path):
    (tmp_path / "notes.md").write_text("# Notes\n\nSome body text.")
    part = GenericAdapter().normalize(_ctx(tmp_path), GenericAdapter().detect(_ctx(tmp_path))[0])
    refs = part["docs"]["references"]
    assert len(refs) == 1
    assert refs[0]["title"] == "Notes"
    assert refs[0]["path"] == "notes.md"
    assert "<p>Some body text.</p>" in refs[0]["html"]


def test_generic_collects_open_todos(tmp_path):
    (tmp_path / "plan.md").write_text("- [ ] ship it\n- [x] done already")
    part = GenericAdapter().normalize(_ctx(tmp_path), GenericAdapter().detect(_ctx(tmp_path))[0])
    todos = [t["text"] for t in part["project"]["openTodos"]]
    assert todos == ["ship it"]


def test_generic_redacts_secrets_in_docs(tmp_path):
    (tmp_path / "config.md").write_text("token ghp_0123456789abcdefghij")
    part = GenericAdapter().normalize(_ctx(tmp_path), GenericAdapter().detect(_ctx(tmp_path))[0])
    blob = str(part)
    assert "ghp_0123456789abcdefghij" not in blob


def test_generic_uses_readme_title(tmp_path):
    (tmp_path / "README.md").write_text("# My Project\n\nintro")
    part = GenericAdapter().normalize(_ctx(tmp_path), GenericAdapter().detect(_ctx(tmp_path))[0])
    assert part["project"]["title"] == "My Project"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_generic_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acc.adapters.base'`

- [ ] **Step 3: Write the base interface**

`src/acc/adapters/base.py`:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


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
```

- [ ] **Step 4: Write the generic adapter**

`src/acc/adapters/generic.py`:

```python
import re
from .base import ScanContext, ProviderRoot
from ..ids import stable_id, rel_posix
from ..redaction import redact_text
from ..markdown import render_markdown_safe

_TODO = re.compile(r"^\s*[-*]\s*\[ \]\s*(.+)$")
_HEADING = re.compile(r"^\s*#{1,6}\s+(.*)$")


def _first_heading(text: str) -> str:
    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            return m.group(1).strip()
    return ""


def _first_paragraph(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return s
    return ""


class GenericAdapter:
    id = "generic"
    display_name = "Generic"

    def detect(self, ctx: ScanContext) -> list[ProviderRoot]:
        return [ProviderRoot(provider="generic", path=ctx.root)]

    def normalize(self, ctx: ScanContext, root: ProviderRoot) -> dict:
        docs: list[dict] = []
        todos: list[dict] = []
        title = ctx.root.name
        for p in ctx.files:
            if p.suffix.lower() != ".md":
                continue
            rel = rel_posix(p, ctx.root)
            raw = p.read_text(encoding="utf-8", errors="replace")
            clean, _ = redact_text(raw)
            heading = _first_heading(clean) or rel
            docs.append({
                "id": stable_id("generic", "doc", rel, heading),
                "title": heading,
                "path": rel,
                "summary": _first_paragraph(clean),
                "html": render_markdown_safe(clean),
            })
            for line in clean.splitlines():
                m = _TODO.match(line)
                if m:
                    todos.append({"text": m.group(1).strip(), "path": rel})
            if rel.lower() == "readme.md" and heading:
                title = heading
        docs.sort(key=lambda d: d["path"])
        todos.sort(key=lambda t: (t["path"], t["text"]))
        return {
            "project": {"title": title, "openTodos": todos, "recentDocs": [], "warnings": []},
            "docs": {"references": docs, "prds": [], "adrs": [], "decisions": [], "workflows": []},
            "inventory": {"agents": [], "skills": [], "hooks": [], "commands": [], "mcpServers": [], "rules": []},
            "relationships": [],
        }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_generic_adapter.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add src/acc/adapters/base.py src/acc/adapters/generic.py tests/test_generic_adapter.py
git commit -m "feat: adapter base and generic fallback adapter"
```

---

## Task 8: HTML template, styles, and client JS

**Files:**
- Create: `templates/dashboard.html.tmpl`
- Create: `templates/styles.css`
- Create: `templates/app.js`

These are rendered/exercised by Tasks 9-10, so this task creates them and the render tests verify their wiring.

- [ ] **Step 1: Create `templates/styles.css`**

```css
:root { color-scheme: light dark; --fg: #1a1a1a; --muted: #666; --line: #ddd; --bg: #fff; }
@media (prefers-color-scheme: dark) { :root { --fg: #e6e6e6; --muted: #999; --line: #333; --bg: #111; } }
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.6 system-ui, sans-serif; color: var(--fg); background: var(--bg); }
header.acc-head { position: sticky; top: 0; background: var(--bg); border-bottom: 1px solid var(--line);
  padding: 10px 16px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
header.acc-head strong { font-size: 16px; }
.acc-meta { color: var(--muted); font-size: 11px; margin-left: auto; }
nav.acc-nav { position: sticky; top: 44px; background: var(--bg); border-bottom: 1px solid var(--line);
  padding: 6px 16px; display: flex; gap: 8px; }
nav.acc-nav a { text-decoration: none; border: 1px solid var(--line); border-radius: 10px;
  padding: 2px 10px; color: var(--fg); font-size: 12px; }
#acc-search { padding: 4px 10px; border: 1px solid var(--line); border-radius: 6px; background: transparent; color: var(--fg); }
section { padding: 16px; border-bottom: 1px solid var(--line); }
.acc-label { text-transform: uppercase; letter-spacing: .05em; font-size: 11px; color: var(--muted); }
.acc-row { border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; margin: 6px 0; }
.acc-row .badge { border: 1px solid var(--line); border-radius: 8px; padding: 0 6px; font-size: 10px; color: var(--muted); }
.acc-row .path { color: var(--muted); font-size: 11px; }
footer.acc-foot { padding: 16px; color: var(--muted); font-size: 11px; }
.acc-hidden { display: none; }
```

- [ ] **Step 2: Create `templates/app.js`**

```javascript
(function () {
  var node = document.getElementById("acc-data");
  var data = JSON.parse(node.textContent);

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function renderHead() {
    document.getElementById("acc-title").textContent = data.project.title;
    var m = data.source;
    document.getElementById("acc-meta").textContent =
      "stamped · digest " + m.sourceDigest + " · vcs: " + m.vcs.kind + " · freshness is manual";
  }

  function renderDocs() {
    var host = document.getElementById("acc-docs");
    var groups = data.docs;
    Object.keys(groups).sort().forEach(function (g) {
      groups[g].forEach(function (doc) {
        var row = el("div", "acc-row acc-item");
        row.appendChild(el("span", null, doc.title));
        row.appendChild(document.createTextNode(" "));
        row.appendChild(el("span", "badge", g));
        row.appendChild(document.createTextNode(" "));
        row.appendChild(el("span", "path", doc.path));
        row.dataset.search = (doc.title + " " + doc.path + " " + (doc.summary || "")).toLowerCase();
        host.appendChild(row);
      });
    });
  }

  function renderTodos() {
    var host = document.getElementById("acc-todos");
    (data.project.openTodos || []).forEach(function (t) {
      var row = el("div", "acc-row acc-item", t.text + "  —  " + t.path);
      row.dataset.search = (t.text + " " + t.path).toLowerCase();
      host.appendChild(row);
    });
  }

  function wireSearch() {
    var box = document.getElementById("acc-search");
    box.addEventListener("input", function () {
      var q = box.value.toLowerCase();
      document.querySelectorAll(".acc-item").forEach(function (row) {
        var hit = !q || (row.dataset.search || "").indexOf(q) !== -1;
        row.classList.toggle("acc-hidden", !hit);
      });
    });
  }

  renderHead();
  renderDocs();
  renderTodos();
  wireSearch();
})();
```

- [ ] **Step 3: Create `templates/dashboard.html.tmpl`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="ai-control-center __SCHEMA_VERSION__">
<title>AI Control Center</title>
<style>/*__CSS__*/</style>
</head>
<body>
<header class="acc-head">
  <strong id="acc-title">Dashboard</strong>
  <input id="acc-search" placeholder="search…" aria-label="search">
  <span class="acc-meta" id="acc-meta"></span>
</header>
<nav class="acc-nav">
  <a href="#overview">Overview</a>
  <a href="#docs">Docs</a>
  <a href="#todos">TODOs</a>
</nav>
<section id="overview"><div class="acc-label">Overview</div><div id="acc-overview"></div></section>
<section id="docs"><div class="acc-label">Docs</div><div id="acc-docs"></div></section>
<section id="todos"><div class="acc-label">Open TODOs</div><div id="acc-todos"></div></section>
<footer class="acc-foot">Generated offline by ai-control-center. Refresh with the dashboard command.</footer>
<script id="acc-data" type="application/json">__DATA_ISLAND__</script>
<script>/*__APP_JS__*/</script>
</body>
</html>
```

- [ ] **Step 4: Commit**

```bash
git add templates/
git commit -m "feat: dashboard HTML template, styles, and client JS"
```

---

## Task 9: HTML render with safe JSON island

**Files:**
- Create: `src/acc/render.py`
- Test: `tests/test_render.py`

- [ ] **Step 1: Write the failing test**

`tests/test_render.py`:

```python
from acc.render import render_html
from acc.schema import SCHEMA_VERSION


def _data():
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generator": {"name": "ai-control-center", "version": "0.1.0", "rendererDigest": "x"},
        "source": {"repoName": "r", "dashboardPath": "d.html", "sourceDigest": "abc", "vcs": {"kind": "none"}},
        "providers": [],
        "project": {"title": "Demo", "openTodos": [], "recentDocs": [], "warnings": []},
        "inventory": {"agents": [], "skills": [], "hooks": [], "commands": [], "mcpServers": [], "rules": []},
        "docs": {"prds": [], "adrs": [], "decisions": [], "workflows": [], "references": []},
        "relationships": [],
        "search": [],
    }


def test_render_inlines_data_and_template_pieces():
    html = render_html(_data())
    assert "<!DOCTYPE html>" in html
    assert '"sourceDigest":"abc"' in html
    assert "__CSS__" not in html and "__APP_JS__" not in html and "__DATA_ISLAND__" not in html


def test_render_neutralizes_script_close_in_island():
    data = _data()
    data["project"]["title"] = "</script><script>alert(1)</script>"
    html = render_html(data)
    # the raw closing tag must not appear inside the JSON island
    island = html.split('id="acc-data"', 1)[1].split("</script>", 1)[0]
    assert "</script>" not in island
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_render.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acc.render'`

- [ ] **Step 3: Write minimal implementation**

`src/acc/render.py`:

```python
from pathlib import Path
from .schema import canonical_json

_TEMPLATES = Path(__file__).resolve().parent.parent.parent / "templates"


def _read(name: str) -> str:
    return (_TEMPLATES / name).read_text(encoding="utf-8")


def render_html(data: dict) -> str:
    template = _read("dashboard.html.tmpl")
    css = _read("styles.css")
    app_js = _read("app.js")
    island = canonical_json(data).replace("</", "<\\/")
    return (
        template
        .replace("/*__CSS__*/", css)
        .replace("/*__APP_JS__*/", app_js)
        .replace("__DATA_ISLAND__", island)
        .replace("__SCHEMA_VERSION__", data["schemaVersion"])
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_render.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/acc/render.py tests/test_render.py
git commit -m "feat: render HTML with neutralized JSON island"
```

---

## Task 10: Generate pipeline, CLI, and integration tests

**Files:**
- Create: `src/acc/generate.py`
- Create: `src/acc/cli.py`
- Test: `tests/test_generate.py`

- [ ] **Step 1: Write the failing test**

`tests/test_generate.py`:

```python
from pathlib import Path
from acc.generate import generate, detect_out_dir


def _make_repo(tmp_path):
    (tmp_path / "README.md").write_text("# Demo\n\nA demo repo.")
    (tmp_path / "PLAN.md").write_text("- [ ] build the thing\ntoken ghp_0123456789abcdefghij")
    return tmp_path


def test_generate_writes_dashboard(tmp_path):
    out = generate(_make_repo(tmp_path))
    assert out.exists()
    assert out.name == "dashboard.html"
    assert "<!DOCTYPE html>" in out.read_text(encoding="utf-8")


def test_generate_is_deterministic(tmp_path):
    _make_repo(tmp_path)
    first = generate(tmp_path).read_text(encoding="utf-8")
    second = generate(tmp_path).read_text(encoding="utf-8")
    assert first == second


def test_generate_redacts_secrets_from_output(tmp_path):
    out = generate(_make_repo(tmp_path))
    assert "ghp_0123456789abcdefghij" not in out.read_text(encoding="utf-8")


def test_generate_escapes_hostile_markdown(tmp_path):
    (tmp_path / "evil.md").write_text("# Evil\n\n<img src=x onerror=alert(1)>")
    out = generate(tmp_path)
    html = out.read_text(encoding="utf-8")
    assert "onerror=alert(1)>" not in html
    assert "&lt;img" in html


def test_detect_out_dir_prefers_provider_folder(tmp_path):
    (tmp_path / ".claude").mkdir()
    assert detect_out_dir(tmp_path) == (tmp_path / ".claude").resolve()


def test_detect_out_dir_falls_back(tmp_path):
    assert detect_out_dir(tmp_path) == (tmp_path / ".ai-control-center").resolve()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_generate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acc.generate'`

- [ ] **Step 3: Write the generate pipeline**

`src/acc/generate.py`:

```python
from pathlib import Path
from .scan import scan_files
from .digest import source_digest
from .schema import SCHEMA_VERSION, validate
from .render import render_html
from .adapters.base import ScanContext
from .adapters.generic import GenericAdapter
from . import __version__

_PROVIDER_DIRS = (".claude", ".codex", ".cursor")


def detect_out_dir(root: Path) -> Path:
    root = root.resolve()
    for prov in _PROVIDER_DIRS:
        if (root / prov).is_dir():
            return (root / prov).resolve()
    return (root / ".ai-control-center").resolve()


def _build_search(part: dict) -> list[dict]:
    records: list[dict] = []
    for group in part["docs"].values():
        for doc in group:
            records.append({"id": doc["id"], "title": doc["title"],
                            "path": doc["path"], "text": doc.get("summary", "")})
    records.sort(key=lambda r: (r["path"], r["title"]))
    return records


def generate(root: Path, out_dir: Path | None = None) -> Path:
    root = root.resolve()
    files = scan_files(root)
    ctx = ScanContext(root=root, files=files)
    adapter = GenericAdapter()
    proot = adapter.detect(ctx)[0]
    part = adapter.normalize(ctx, proot)

    out_dir = (out_dir or detect_out_dir(root))
    out_dir.mkdir(parents=True, exist_ok=True)
    dashboard = out_dir / "dashboard.html"

    data = {
        "schemaVersion": SCHEMA_VERSION,
        "generator": {"name": "ai-control-center", "version": __version__, "rendererDigest": ""},
        "source": {
            "repoName": root.name,
            "dashboardPath": dashboard.resolve().relative_to(root).as_posix(),
            "sourceDigest": source_digest(files, root),
            "vcs": {"kind": "none"},
        },
        "providers": [{"id": "generic", "displayName": "Generic", "root": "."}],
        "project": part["project"],
        "inventory": part["inventory"],
        "docs": {**part["docs"], "references": part["docs"]["references"]},
        "relationships": part["relationships"],
        "search": _build_search(part),
    }
    validate(data)
    dashboard.write_text(render_html(data), encoding="utf-8")
    return dashboard
```

- [ ] **Step 4: Write the CLI**

`src/acc/cli.py`:

```python
import argparse
from pathlib import Path
from .generate import generate


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="acc", description="Generate the AI control center dashboard")
    parser.add_argument("--root", default=".", help="repo root to scan")
    parser.add_argument("--out", default=None, help="output directory (default: auto-detect provider folder)")
    args = parser.parse_args(argv)
    out_dir = Path(args.out) if args.out else None
    dashboard = generate(Path(args.root), out_dir)
    print(f"wrote {dashboard}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_generate.py -v`
Expected: PASS (6 passed)

- [ ] **Step 6: Run the whole suite**

Run: `python -m pytest -v`
Expected: PASS (all tests green)

- [ ] **Step 7: Smoke-test the CLI on this repo**

Run: `python -m acc.cli --root . --out /tmp/acc-demo && open /tmp/acc-demo/dashboard.html`
Expected: prints `wrote /tmp/acc-demo/dashboard.html`; the file opens in a browser and lists the repo's markdown docs and open TODOs.

- [ ] **Step 8: Commit**

```bash
git add src/acc/generate.py src/acc/cli.py tests/test_generate.py
git commit -m "feat: generate pipeline and CLI with determinism/redaction/XSS tests"
```

---

## Self-review notes

- **Spec coverage (Phase 1 slice):** deterministic output (Task 5, 6, 10 determinism test), redaction-at-extraction (Task 2, integration in Task 10), sanitized render / no XSS (Task 4, render island neutralization in Task 9, integration in Task 10), one HTML under the provider folder with fallback (Task 10 `detect_out_dir`), `sourceDigest` freshness (Task 5, surfaced in Task 8 JS), non-git first-class (`vcs.kind: "none"` throughout), file exclusions (Task 3). Provider-specific inventory, search polish, relationships, and refresh tiers are intentionally Phase 2-4.
- **Naming consistency:** `stable_id`, `rel_posix`, `redact_text`, `allowlist_config`, `scan_files`, `DEFAULT_EXCLUDES`, `render_markdown_safe`, `source_digest`, `SCHEMA_VERSION`, `canonical_json`, `validate`, `ScanContext`, `ProviderRoot`, `GenericAdapter`, `render_html`, `generate`, `detect_out_dir` are used identically across tasks.
- **No placeholders:** every code step contains complete, runnable code.

## What Phase 1 deliberately leaves for later

Provider adapters (Phase 2), the full layout-B renderer with bento Overview and relationship map (Phase 3), and the three-tier refresh plus skill/plugin packaging (Phase 4). Each gets its own plan that builds on this core.
