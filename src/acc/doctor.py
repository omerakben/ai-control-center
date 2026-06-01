"""`acc doctor` — deterministic, read-only repo AI-context findings.

Findings, never a score: every check is a concrete, reproducible fact about the
repo's AI context (a stale dashboard, a skill with no description, a broken
relative link). No git history, no mtimes, no network, no model judgment — so the
same repo always yields the same report. `doctor` reuses the generator's
`_assemble` core, so it inspects exactly what the dashboard would show.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from . import __version__
from .generate import _assemble, OwnerAmbiguousError
from .scan import scan_files
from .ids import rel_posix
from .redaction import redact_text

_NEAR_EMPTY_CHARS = 40
_LARGE_BYTES = 50_000
_INSTRUCTION_MARKERS = ("CLAUDE.md", "AGENTS.md", ".cursorrules")
_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)\s]+)\)")
_FENCE_RE = re.compile(r"^\s*```")


@dataclass
class Finding:
    level: str   # "warn" (counts toward --strict) or "info"
    code: str
    message: str


def _rel(p: Path, root: Path) -> str:
    try:
        return p.relative_to(root).as_posix()
    except ValueError:
        return str(p)


def _embedded_island(path: Path) -> dict | None:
    """Parse the JSON island out of an existing dashboard.html, or None."""
    try:
        txt = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r'<script id="acc-data"[^>]*>(.*?)</script>', txt, re.S)
    if not m:
        return None
    try:
        island = json.loads(m.group(1).replace("<\\/", "</"))
    except ValueError:
        return None
    # A valid-but-non-object island (a list/number from a corrupted file) would
    # crash the later `.get(...)` calls; treat it as unparseable instead.
    return island if isinstance(island, dict) else None


def _relative_links(text: str):
    """Yield repo-relative markdown link targets, conservatively.

    Skips fenced code, external schemes (http:, mailto:, …), in-page anchors, and
    absolute paths; strips fragments. Conservative on purpose so `--strict` CI
    does not fail on false positives.
    """
    in_code = False
    for line in text.splitlines():
        if _FENCE_RE.match(line):
            in_code = not in_code
            continue
        if in_code:
            continue
        # Drop inline-code spans: a `[x](path)` written as code is an example of
        # link syntax, not a live link, so it must not be flagged as broken.
        line = re.sub(r"`[^`]*`", " ", line)
        for url in _LINK_RE.findall(line):
            # Decode first, then guard on the *decoded* target. Guarding the
            # still-encoded URL is bypassable — `%2Fetc` -> `/etc`, `..%2F` ->
            # `../`, `%00` -> NUL — which would let the existence check escape the
            # repo (an out-of-tree probe on a CI runner). `a%20b.md` -> `a b.md`
            # is the legitimate case this decode is for.
            target = unquote(url.split("#", 1)[0].split("?", 1)[0])
            if not target or "\x00" in target:         # empty, or NUL (crashes resolve())
                continue
            head = target.split("/", 1)[0]
            if ":" in head:                             # scheme (http:, mailto:, drive:)
                continue
            if target.startswith(("#", "/", "\\")):     # in-page anchor or absolute path
                continue
            yield target


def collect_findings(root: Path, owner: str | None = None) -> tuple[list[Finding], dict]:
    """Return (findings, machine-readable report) for the repo at `root`."""
    root = root.resolve()
    data, dashboard, scanned = _assemble(root, owner=owner)
    findings: list[Finding] = []
    fresh_digest = data["source"]["sourceDigest"]

    # --- dashboard freshness: purely the embedded digest, no git/mtime ---
    if not dashboard.exists():
        findings.append(Finding("info", "missing-dashboard",
            f"No dashboard at {_rel(dashboard, root)} yet — run `acc --root .` to create one."))
    else:
        island = _embedded_island(dashboard)
        if island is None:
            findings.append(Finding("warn", "unreadable-dashboard",
                f"{_rel(dashboard, root)} exists but its data island could not be parsed."))
        else:
            embedded = (island.get("source") or {}).get("sourceDigest")
            gen = island.get("generator") or {}
            if embedded and embedded != fresh_digest:
                findings.append(Finding("warn", "stale-dashboard",
                    f"{_rel(dashboard, root)} is stale (built from {embedded}, current is "
                    f"{fresh_digest}) — re-run `acc --root .`."))
            if gen.get("truncated"):
                findings.append(Finding("info", "truncated-dashboard",
                    f"{_rel(dashboard, root)} is a truncated summary (repo exceeds the size budget)."))
            ev = gen.get("version")
            if ev and ev != __version__:
                findings.append(Finding("info", "generator-version",
                    f"{_rel(dashboard, root)} was built by acc {ev}; installed acc is {__version__}."))

    # --- weak metadata: inventory items with no description ---
    weak = [it["path"] for kind in ("agents", "skills", "commands", "rules")
            for it in data["inventory"].get(kind, []) if not (it.get("summary") or "").strip()]
    if weak:
        findings.append(Finding("warn", "weak-metadata",
            f"{len(weak)} agent/skill/command/rule file(s) have no description "
            f"(e.g. {weak[0]}) — add a `description:` so humans and agents know the intent."))

    # --- file pass: near-empty / large instruction files, redactions, broken links ---
    redactions = 0
    broken: list[str] = []
    for f in scan_files(root):
        if f.suffix.lower() not in (".md", ".mdc"):
            continue
        rel = rel_posix(f, root)
        try:
            raw = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        clean, n = redact_text(raw)
        redactions += n
        if f.name in _INSTRUCTION_MARKERS and len(clean.strip()) < _NEAR_EMPTY_CHARS:
            findings.append(Finding("warn", "near-empty-instruction",
                f"{rel} is nearly empty ({len(clean.strip())} chars) — agents get little context from it."))
        # Count bytes of the already-normalized text (newline- and encoding-
        # normalized by read_text above), not f.stat().st_size: the size feeds
        # the doctor.v1 report, which must stay byte-identical across OSes
        # regardless of CRLF/LF or invalid-UTF-8 on disk.
        nbytes = len(raw.encode("utf-8"))
        if nbytes > _LARGE_BYTES:
            findings.append(Finding("info", "large-file",
                f"{rel} is large ({nbytes // 1000} KB) — oversized context files drift easily."))
        for target in _relative_links(clean):
            try:
                resolved = (f.parent / target).resolve()
            except (OSError, ValueError):
                continue                       # unresolvable target: skip, never crash
            if not resolved.is_relative_to(root):
                continue                       # link escapes the repo: not ours to probe
            if not resolved.exists():
                broken.append(f"{rel} -> {target}")
    if broken:
        findings.append(Finding("warn", "broken-link",
            f"{len(broken)} relative markdown link(s) point at a missing file (e.g. {broken[0]})."))
    if redactions:
        findings.append(Finding("info", "redactions",
            f"{redactions} secret-shaped value(s) were redacted before rendering."))

    todos = len((data.get("project") or {}).get("openTodos", []))
    if todos:
        findings.append(Finding("info", "open-todos", f"{todos} open `- [ ]` TODO(s) found."))

    findings.sort(key=lambda f: (f.level != "warn", f.code))
    report = {
        "schemaVersion": "doctor.v1",
        "root": str(root),
        "dashboardPath": data["source"]["dashboardPath"],
        "sourceDigest": fresh_digest,
        "scannedFileCount": scanned,
        "providers": [p["id"] for p in data["providers"]],
        "findings": [{"level": f.level, "code": f.code, "message": f.message} for f in findings],
    }
    return findings, report


def run_doctor(root: Path, owner: str | None = None,
               strict: bool = False, as_json: bool = False) -> int:
    """Print a doctor report. Exit 0 (clean / warnings without --strict),
    1 (warnings with --strict), or 2 (execution error)."""
    try:
        findings, report = collect_findings(root, owner=owner)
    except OwnerAmbiguousError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # never crash with a stack trace
        print(f"error: {e}", file=sys.stderr)
        return 2

    warns = [f for f in findings if f.level == "warn"]
    report["status"] = "warning" if warns else "ok"
    if as_json:
        print(json.dumps(report))
    else:
        print("Agent Context Center — doctor")
        print(f"Root: {report['root']}")
        print(f"Files scanned: {report['scannedFileCount']} · "
              f"providers: {', '.join(report['providers'])}")
        print(f"Dashboard: {report['dashboardPath']}")
        print(f"Status: {'needs attention' if warns else 'looks healthy'}")
        if findings:
            print("Findings:")
            for f in findings:
                print(f"  {'!' if f.level == 'warn' else '·'} [{f.code}] {f.message}")
        print("Next: run `acc --root .` to (re)generate the dashboard.")
    return 1 if (warns and strict) else 0
