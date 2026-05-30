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


def test_render_does_not_corrupt_island_with_placeholder_text():
    data = _data()
    data["project"]["title"] = "mentions __SCHEMA_VERSION__ and __DATA_ISLAND__"
    html = render_html(data)
    island = html.split('id="acc-data"', 1)[1].split("</script>", 1)[0]
    assert "__SCHEMA_VERSION__" in island
    assert "__DATA_ISLAND__" in island
