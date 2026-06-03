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

    def visible():
        return page.locator(".acc-item:not(.acc-hidden)").count()

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
    # Enough big docs that graduated truncation runs past dropping bodies and
    # capping summaries all the way to the search-body step, where the index goes
    # light. make_large_repo yields docs titled "Doc N" at docs/big_NNNN.md, so we
    # query a unique path fragment; names+paths stay searchable while the body-off
    # note is shown.
    make_large_repo(tmp_path, 300)
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


def test_inline_related_is_bidirectional_and_jumps(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    (tmp_path / "docs" / "links.md").write_text(
        "# Links\n\nThe .claude/agents/reviewer.md agent handles reviews.")
    page.set_content(_html(tmp_path))
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


def test_crossref_view_grouped_by_source_and_sorted(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    (tmp_path / "docs" / "links.md").write_text(
        "# Links\n\nSee .claude/agents/reviewer.md.")
    page.set_content(_html(tmp_path))
    cross = page.locator("#acc-crossref")
    assert cross.locator(".acc-xref-source", has_text=".claude/settings.json").count() == 1
    assert cross.locator(".acc-xref-source", has_text=".cursor/mcp.json").count() == 1
    src_headers = cross.locator(".acc-xref-source")
    texts = [src_headers.nth(i).inner_text() for i in range(src_headers.count())]
    assert texts == sorted(texts)  # display-sorted
    cross.locator("button", has_text="reviewer").first.click()
    flashed = page.locator("#acc-inventory .acc-item.acc-flash", has_text="reviewer")
    assert flashed.count() == 1


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


def test_degraded_mode_keeps_declares_and_renders(page, tmp_path):
    # a repo large enough to trip the 2 MB truncate budget; declares edges are
    # bounded, so the Cross-references view still renders its source groups.
    make_multi_provider_repo(tmp_path)
    make_large_repo(tmp_path, 200)
    page.set_content(_html(tmp_path))
    assert page.locator("#acc-crossref .acc-xref-source").count() >= 1


# ---- v1.1.0 UI/UX pass: markdown rendering, reading pane, empty states ----

def test_markdown_renders_bold_code_link_not_literal(page, tmp_path):
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "md.md").write_text(
        '---\nname: mdagent\n'
        'description: "Use **const** over `let`; see [docs](https://x.test)."\n---\n# Body\n')
    page.set_content(_html(tmp_path))
    summary = page.locator('.acc-item', has_text="mdagent").first.locator('.acc-summary')
    assert summary.locator('strong', has_text="const").count() == 1
    assert summary.locator('code', has_text="let").count() == 1
    link = summary.locator('a.acc-mdlink', has_text="docs")
    assert link.count() == 1 and link.first.get_attribute("href") == "https://x.test"
    assert "**const**" not in summary.inner_text()  # no raw markers


def test_markdown_hostile_summary_is_inert(page, tmp_path):
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "x.md").write_text(
        '---\nname: pwn2\n'
        'description: "</script><img src=x onerror=window.__pwn2=1> and **bold**"\n---\n')
    page.set_content(_html(tmp_path))
    row = page.locator('.acc-item', has_text="pwn2").first
    assert row.locator('img').count() == 0
    assert page.evaluate("() => window.__pwn2") is None
    assert row.locator('.acc-summary strong', has_text="bold").count() == 1  # md still works


def test_markdown_javascript_link_is_neutralized(page, tmp_path):
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "j.md").write_text(
        '---\nname: jlink\ndescription: "click [here](javascript:window.__js=1)"\n---\n')
    page.set_content(_html(tmp_path))
    summary = page.locator('.acc-item', has_text="jlink").first.locator('.acc-summary')
    assert summary.locator('a').count() == 0           # no anchor for unsafe scheme
    assert "javascript:" in summary.inner_text()       # degraded to plain text
    assert page.evaluate("() => window.__js") is None


def test_reading_pane_expands_and_renders_body(page, tmp_path):
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "r.md").write_text(
        "---\nname: reader\ndescription: short\n---\n"
        "# Heading\n\nA **bold** body line.\n\n- item one\n")
    page.set_content(_html(tmp_path))
    row = page.locator('.acc-item', has_text="reader").first
    detail = row.locator('.acc-detail')
    assert detail.count() == 1
    assert detail.first.evaluate("el => el.classList.contains('acc-hidden')")  # collapsed
    row.locator('.acc-toggle').click()
    assert not detail.first.evaluate("el => el.classList.contains('acc-hidden')")
    assert detail.locator('h1', has_text="Heading").count() == 1
    assert detail.locator('strong', has_text="bold").count() == 1
    assert detail.locator('li', has_text="item one").count() == 1


def test_empty_inventory_has_graceful_note(page, tmp_path):
    (tmp_path / "README.md").write_text("# Readme\n\nNo providers here.")
    (tmp_path / "AGENTS.md").write_text("# Guide\n\n- [ ] do a thing\n")  # doc, no inventory
    page.set_content(_html(tmp_path))
    inv = page.locator("#acc-inventory")
    assert inv.locator(".acc-empty").count() == 1
    assert "no agents" in inv.locator(".acc-empty").inner_text().lower()
    assert inv.locator(".acc-item").count() == 0  # empty note is not an indexable row


def test_overview_todo_card_matches_section_text(page, tmp_path):
    # escape-consistency: the Overview TODO preview equals the TODOs-section row
    (tmp_path / ".claude").mkdir()
    (tmp_path / "CLAUDE.md").write_text(
        "# Rules\n\n- [ ] handle the `<os>` case in **build**\n")
    page.set_content(_html(tmp_path))
    card_line = page.locator("#acc-overview .acc-card-todos .acc-card-line").first.inner_text()
    row_title = page.locator("#acc-todos .acc-item .acc-itemtitle").first.inner_text()
    assert "<os>" in card_line and "&lt;os&gt;" not in card_line  # decoded, not double-escaped
    assert card_line.strip() == row_title.strip()


def test_todos_render_all_in_scroll_box_and_remain_jumpable(page, tmp_path):
    # all TODOs render (so the omnibox can jump to any), bounded by a scroll box
    (tmp_path / ".claude").mkdir()
    body = "# Rules\n\n" + "".join("- [ ] task number %d\n" % i for i in range(70))
    (tmp_path / "CLAUDE.md").write_text(body)
    page.set_content(_html(tmp_path))
    box = page.locator("#acc-todos .acc-todos")
    assert box.count() == 1
    assert box.locator(".acc-item").count() == 70  # every TODO rendered
    assert box.evaluate("el => getComputedStyle(el).overflowY") in ("auto", "scroll")
    # a TODO past any visual fold is still reachable via the omnibox
    page.fill("#acc-omnibox", "task number 69")
    page.wait_for_timeout(120)
    page.locator("#acc-omnibox-results .acc-omni-hit").first.click()
    flashed = page.locator(".acc-item.acc-flash")
    assert flashed.count() == 1 and "task number 69" in flashed.inner_text()


def test_markdown_control_char_link_is_neutralized(page, tmp_path):
    # a C0 control char before the scheme must not smuggle a live javascript: href
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "c.md").write_text(
        '---\nname: clink\ndescription: "x [run](\x01javascript:window.__c0=1)"\n---\n')
    page.set_content(_html(tmp_path))
    summary = page.locator('.acc-item', has_text="clink").first.locator('.acc-summary')
    assert summary.locator('a').count() == 0       # control-char url rejected
    assert page.evaluate("() => window.__c0") is None


def test_scroll_spy_activates_lower_section_on_scroll(page, tmp_path):
    make_multi_provider_repo(tmp_path)
    (tmp_path / "docs" / "big.md").write_text("# Big\n\n" + ("filler paragraph. " * 1500))
    page.set_viewport_size({"width": 1000, "height": 600})
    page.set_content(_html(tmp_path))
    page.wait_for_timeout(150)
    page.evaluate("() => document.getElementById('crossref').scrollIntoView({block:'start'})")
    page.wait_for_timeout(300)
    active = page.locator("nav.acc-nav a.acc-nav-active")
    assert active.count() == 1
    assert active.first.get_attribute("data-spy") != "overview"


# ---- v1.1.1 production-review fixes: escapes, summary cap, tables ----

def test_agent_summary_is_lead_sentence_not_a_wall(page, tmp_path):
    # a real-shaped agent: one double-quoted description line with \n and examples
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "rev.md").write_text(
        '---\nname: bigdesc\n'
        'description: "Use this agent for accessibility review of UI components. '
        'Invoke proactively after edits.\\n\\nExamples:\\nuser: \\"Check the form\\""\n'
        '---\n# Body\n')
    page.set_content(_html(tmp_path))
    summary = page.locator('.acc-item', has_text="bigdesc").first.locator('.acc-summary').inner_text()
    assert summary.startswith("Use this agent for accessibility review of UI components.")
    assert "Examples:" not in summary       # capped to the lead sentence
    assert "\\n" not in summary             # no literal backslash-n
    assert 'user: "Check' not in summary    # tail dropped


def test_reading_pane_renders_markdown_table(page, tmp_path):
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "t.md").write_text(
        "---\nname: tabler\ndescription: short\n---\n"
        "# Stack\n\n"
        "| Technology | Version |\n| --- | --- |\n| React | 19 |\n| Next | 16 |\n")
    page.set_content(_html(tmp_path))
    row = page.locator('.acc-item', has_text="tabler").first
    row.locator('.acc-toggle').click()
    table = row.locator('.acc-detail table.acc-md-table')
    assert table.count() == 1
    assert table.locator('th', has_text="Technology").count() == 1
    assert table.locator('td', has_text="React").count() == 1
    assert table.locator('tbody tr').count() == 2   # two data rows, delimiter consumed
    # the raw pipe row must not leak as a paragraph
    assert "| --- |" not in row.locator('.acc-detail').inner_text()


def test_reading_pane_links_to_full_file_when_body_truncated(page, tmp_path):
    # a body past the cap must end with an "open the full file" link, never silently
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    body = "# Big agent\n\n" + ("Lots of detail here. " * 400)  # well over _BODY_CHARS
    (agents / "big.md").write_text("---\nname: bigbody\ndescription: short\n---\n" + body)
    page.set_content(_html(tmp_path))
    row = page.locator('.acc-item', has_text="bigbody").first
    row.locator('.acc-toggle').click()
    more = row.locator('.acc-detail .acc-detail-more')
    assert more.count() == 1
    link = more.locator('a', has_text="full file")
    assert link.count() == 1
    assert (link.first.get_attribute("href") or "").endswith(".claude/agents/big.md")


def test_short_body_has_no_truncation_footer(page, tmp_path):
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "small.md").write_text("---\nname: smallbody\ndescription: short\n---\n# Tiny\n\nDone.\n")
    page.set_content(_html(tmp_path))
    row = page.locator('.acc-item', has_text="smallbody").first
    row.locator('.acc-toggle').click()
    assert row.locator('.acc-detail-more').count() == 0


def test_metadata_badges_render_in_dom(page, tmp_path):
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "meta_agent.md").write_text(
        "---\nname: meta_agent\nstatus: \"active & ready\"\npriority: 5\nversion: 1.2.3\ntags: [tag1 & tag2, tag3]\n---\n# Body\n"
    )
    page.set_content(_html(tmp_path))
    row = page.locator('.acc-item', has_text="meta_agent").first
    meta_badges = row.locator('.acc-meta-badges')
    assert meta_badges.count() == 1
    assert meta_badges.locator('.acc-badge-meta', has_text="status:active & ready").count() == 1
    assert meta_badges.locator('.acc-badge-meta', has_text="priority:5").count() == 1
    assert meta_badges.locator('.acc-badge-meta', has_text="version:1.2.3").count() == 1
    assert meta_badges.locator('.acc-badge-meta', has_text="tags:tag1 & tag2, tag3").count() == 1
    assert "&amp;" not in meta_badges.inner_text()


def test_todo_interaction_and_diff(page, tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / "CLAUDE.md").write_text("# Rules\n\n- [ ] task one\n- [ ] task two\n")
    page.set_content(_html(tmp_path))

    check = page.locator('.acc-todo-check').first
    assert check.count() == 1
    assert not check.is_checked()

    btn = page.locator('.acc-todo-copy')
    assert btn.count() == 1
    assert btn.is_disabled()

    check.check()
    assert check.is_checked()
    assert not btn.is_disabled()
    assert "Copy Markdown Diff (1)" in btn.inner_text()

    diff_text = page.evaluate("() => window.__accBuildTodoDiff()")
    assert "diff --git a/CLAUDE.md b/CLAUDE.md" in diff_text
    assert "@@ -3,1 +3,1 @@" in diff_text
    assert "-- [ ] task one" in diff_text
    assert "+- [x] task one" in diff_text


def test_redacted_todos_do_not_emit_patch_diff(page, tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / "CLAUDE.md").write_text("# Rules\n\n- [ ] rotate token=abcdefghijkl\n")
    page.set_content(_html(tmp_path))

    check = page.locator('.acc-todo-check').first
    btn = page.locator('.acc-todo-copy')
    check.check()
    assert check.is_checked()
    assert btn.is_disabled()
    assert "Copy Markdown Diff (0)" in btn.inner_text()
    assert page.evaluate("() => window.__accBuildTodoDiff()") == ""


def test_copy_buttons_handle_missing_or_rejected_clipboard(page, tmp_path):
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    (tmp_path / ".claude").mkdir()
    (tmp_path / "CLAUDE.md").write_text("# Rules\n\n- [ ] task one\n")
    page.set_content(_html(tmp_path))

    page.evaluate("""() => {
      Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });
    }""")
    page.locator('.acc-todo-check').first.check()
    page.locator('.acc-todo-copy').click()
    assert "Copy unavailable" in page.locator('.acc-todo-copy').inner_text()

    page.evaluate("""() => {
      Object.defineProperty(navigator, "clipboard", {
        value: { writeText: function () { return Promise.reject(new Error("denied")); } },
        configurable: true
      });
    }""")
    page.locator('.acc-cmd-copy-btn').first.click()
    page.wait_for_function("""() => {
      var btn = document.querySelector(".acc-cmd-copy-btn");
      return btn && btn.textContent === "Unavailable";
    }""")
    assert errors == []


def test_actions_card_renders_with_commands(page, tmp_path):
    (tmp_path / "README.md").write_text("# Readme\n")
    page.set_content(_html(tmp_path))
    actions_card = page.locator('.acc-card-actions')
    assert actions_card.count() == 1
    assert actions_card.locator('.acc-cmd-code', has_text="acc doctor --strict").count() == 1
    assert actions_card.locator('.acc-cmd-code', has_text="acc --root .").count() == 1


def test_global_expand_collapse_groups(page, tmp_path):
    (tmp_path / "dir1").mkdir()
    (tmp_path / "dir2").mkdir()
    (tmp_path / "dir1" / "doc1.md").write_text("# Doc 1\nbody")
    (tmp_path / "dir2" / "doc2.md").write_text("# Doc 2\nbody")

    page.set_content(_html(tmp_path))
    expand_btn = page.locator('.acc-docs-expand')
    collapse_btn = page.locator('.acc-docs-collapse')
    assert expand_btn.count() == 1
    assert collapse_btn.count() == 1

    collapse_btn.click()
    assert page.locator('.acc-group.acc-hidden').count() == 2
    expand_btn.click()
    assert page.locator('.acc-group:not(.acc-hidden)').count() == 2
