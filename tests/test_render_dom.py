"""DOM tests: render the real HTML in a browser and assert behavior.

set_content loads the self-contained dashboard with no server and no file://,
so inline <script> runs and the JSON island is parsed exactly as in the wild.
"""
from pathlib import Path

from acc.generate import generate
from tests.builders import make_multi_provider_repo, make_brownfield_repo, make_large_repo


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


def test_overview_bento_cards(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    ov = page.locator("#acc-overview .acc-bento")
    assert ov.count() == 1
    cards = ov.locator(".acc-card")
    assert cards.count() >= 4  # Providers, Inventory, TODOs, Docs
    # generic is not shown when real providers exist
    prov = ov.locator(".acc-card", has_text="Providers")
    assert prov.locator(".acc-chip", has_text="Generic").count() == 0
    assert prov.locator(".acc-chip", has_text="Claude Code").count() == 1


def test_overview_generic_only_when_sole(page, tmp_path):
    make_brownfield_repo(tmp_path)  # no AI provider -> generic only
    page.set_content(_html(tmp_path))
    prov = page.locator("#acc-overview .acc-card", has_text="Providers")
    assert prov.locator(".acc-chip", has_text="Generic").count() == 1
    assert prov.locator(".acc-chip").count() == 1  # only generic, no phantom provider


def test_truncation_banner_when_truncated(page, tmp_path):
    make_large_repo(tmp_path, 150)  # forces summary-only
    page.set_content(_html(tmp_path))
    banner = page.locator("#acc-banner")
    assert banner.inner_text().strip() != ""


def test_no_banner_when_full(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    assert page.locator("#acc-banner").inner_text().strip() == ""


def test_rows_carry_dataset_id(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    rows = page.locator(".acc-item")
    n = rows.count()
    assert n > 0
    for i in range(n):
        assert rows.nth(i).get_attribute("data-id")


def test_htmlunescape_decodes_entities(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    decoded = page.evaluate(
        "() => window.__accHtmlUnescape('AT&amp;T &lt;b&gt; &quot;q&quot; &#x27;s')")
    assert decoded == "AT&T <b> \"q\" 's"


def test_omnibox_and_filter_inputs_distinct(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    omni = page.locator("#acc-omnibox")
    filt = page.locator("#acc-search")
    assert omni.count() == 1 and filt.count() == 1
    assert "find" in (omni.get_attribute("aria-label") or "").lower()
    assert "filter" in (filt.get_attribute("aria-label") or "").lower()
    assert page.locator("#acc-omnibox-results").count() == 1


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
    assert page.evaluate("() => { window.__accJump('nope_no_row'); return true; }") is True
