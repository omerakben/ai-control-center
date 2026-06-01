from acc.generate import generate
from acc.render import render_html
from acc.schema import SCHEMA_VERSION
from tests.builders import make_multi_provider_repo


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


def test_render_meta_generator_uses_tool_version_not_schema():
    # The <meta name="generator"> convention carries the SOFTWARE version, so it
    # must show generator.version (the acc release), never schemaVersion. The
    # fixture pins them apart (generator 0.1.0 vs schema 1.0) to catch a regression
    # that interpolates the schema version into the human-facing tag.
    html = render_html(_data())
    assert '<meta name="generator" content="Agent Context Center (ai-control-center) 0.1.0">' in html
    assert "ai-control-center) " + SCHEMA_VERSION + '"' not in html


def test_render_neutralizes_script_close_in_island():
    data = _data()
    data["project"]["title"] = "</script><script>alert(1)</script>"
    html = render_html(data)
    # the raw closing tag must not appear inside the JSON island
    island = html.split('id="acc-data"', 1)[1].split("</script>", 1)[0]
    assert "</script>" not in island


def test_render_does_not_corrupt_island_with_placeholder_text():
    data = _data()
    data["project"]["title"] = "mentions __SCHEMA_VERSION__ and __DATA_ISLAND__"
    html = render_html(data)
    island = html.split('id="acc-data"', 1)[1].split("</script>", 1)[0]
    assert "__SCHEMA_VERSION__" in island
    assert "__DATA_ISLAND__" in island


def test_template_and_app_have_inventory():
    html = render_html(_data())
    assert 'id="inventory"' in html
    assert ">Inventory<" in html        # nav link
    assert "renderInventory" in html    # app.js embedded
    assert "function itemRow" in html


def test_template_has_crossref_section_and_nav(tmp_path):
    make_multi_provider_repo(tmp_path)
    html = generate(tmp_path).read_text(encoding="utf-8")
    assert 'id="crossref"' in html
    assert 'id="acc-crossref"' in html
    assert 'href="#crossref"' in html and ">Cross-references<" in html
