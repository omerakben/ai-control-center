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


def test_omnibox_groups_hits_with_counts(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    page.fill("#acc-omnibox", "re")
    page.wait_for_timeout(120)
    panel = page.locator("#acc-omnibox-results")
    assert panel.is_visible()
    groups = panel.locator(".acc-omni-group")
    assert groups.count() >= 1
    head = groups.first.locator(".acc-omni-grouphead")
    assert head.count() == 1
    import re as _re
    assert _re.search(r"\(\d+\)", head.inner_text())
    assert groups.first.locator(".acc-omni-hit").count() >= 1


def test_omnibox_matches_inventory_and_docs(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    page.fill("#acc-omnibox", "notes")
    page.wait_for_timeout(120)
    panel = page.locator("#acc-omnibox-results")
    assert panel.locator(".acc-omni-group", has_text="Reference").count() == 1


def test_omnibox_highlights_with_mark_not_innerhtml(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    page.fill("#acc-omnibox", "review")
    page.wait_for_timeout(120)
    mark = page.locator("#acc-omnibox-results mark")
    assert mark.count() >= 1
    assert mark.first.inner_text().lower() == "review"


def test_omnibox_caps_group_with_more_line(page, tmp_path):
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
    page.fill("#acc-omnibox", "at&t")
    page.wait_for_timeout(120)
    hit = page.locator("#acc-omnibox-results .acc-omni-hit", has_text="AT&T")
    assert hit.count() == 1
    assert "&amp;" not in hit.first.inner_text()


def test_omnibox_hostile_body_is_inert(page, tmp_path):
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "evil.md").write_text(
        '---\nname: pwn\ndescription: "</script><img src=x onerror=window.__pwned=1>"\n---\n')
    page.set_content(_html(tmp_path))
    page.fill("#acc-omnibox", "pwn")
    page.wait_for_timeout(120)
    panel = page.locator("#acc-omnibox-results")
    assert panel.locator("img").count() == 0
    assert page.evaluate("() => window.__pwned") is None


def test_omnibox_light_index_note(page, tmp_path):
    # 150 big docs exceed the 2 MB budget -> summary-only truncation -> light
    # index (every search record's body text is blanked). make_large_repo only
    # yields docs titled "Doc N" at docs/big_NNNN.md, so we query a unique path
    # fragment; names+paths stay searchable while the body-off note is shown.
    make_large_repo(tmp_path, 150)
    page.set_content(_html(tmp_path))
    page.fill("#acc-omnibox", "big_0001")
    page.wait_for_timeout(120)
    panel = page.locator("#acc-omnibox-results")
    assert panel.locator(".acc-omni-hit", has_text="big_0001").count() >= 1
    assert "body search is off" in panel.inner_text().lower()


def test_omnibox_finds_and_jumps_to_todo(page, tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / "CLAUDE.md").write_text("# Rules\n\n- [ ] wire up CI pipeline\n")
    page.set_content(_html(tmp_path))
    page.fill("#acc-omnibox", "wire up CI")
    page.wait_for_timeout(120)
    panel = page.locator("#acc-omnibox-results")
    grp = panel.locator(".acc-omni-group", has_text="TODO")
    assert grp.count() == 1
    assert grp.locator(".acc-omni-hit").count() >= 1
    grp.locator(".acc-omni-hit").first.click()
    flashed = page.locator(".acc-item.acc-flash")
    assert flashed.count() == 1
    assert "wire up ci pipeline" in flashed.inner_text().lower()


def test_omnibox_panel_styled_and_flash_defined(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    page.set_content(_html(tmp_path))
    page.fill("#acc-omnibox", "re")
    page.wait_for_timeout(120)
    panel = page.locator("#acc-omnibox-results")
    assert panel.evaluate("el => getComputedStyle(el).position") == "absolute"
    bg = page.locator("#acc-omnibox-results mark").first.evaluate(
        "el => getComputedStyle(el).backgroundColor")
    assert bg not in ("rgba(0, 0, 0, 0)", "transparent")
