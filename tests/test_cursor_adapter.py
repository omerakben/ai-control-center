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
