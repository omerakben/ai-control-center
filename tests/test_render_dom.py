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


def test_doc_path_renders_as_encoded_link(page, tmp_path):
    # a doc with reserved chars in its name must produce a correctly encoded href
    (tmp_path / "weird name#1.md").write_text("# Weird\n\nbody")
    page.set_content(_html(tmp_path))
    link = page.locator('#acc-docs a.path', has_text="weird name#1.md")
    assert link.count() == 1
    href = link.first.get_attribute("href")
    assert href == "../weird%20name%231.md"  # prefix + per-segment encoding
    assert "#1.md" not in href                # raw # would start a fragment


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
    # "figma" matches exactly one item (the Cursor figma MCP server) in the
    # multi-provider fixture, so the visible count must strictly drop.
    page.fill("#acc-search", "figma")
    after = visible()
    assert 0 < after < before  # typing narrows the visible rows
    assert page.locator(".acc-item:not(.acc-hidden)", has_text="figma").count() >= 1
