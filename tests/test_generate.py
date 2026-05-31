import json
import logging
import os
import re
from acc.generate import generate, detect_out_dir
from tests.builders import make_multi_provider_repo, make_claude_repo, make_codex_repo, make_large_repo


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


def test_generate_includes_provider_folder_markdown(tmp_path):
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "CLAUDE.md").write_text("# Claude Instructions\n\nProject rules.")
    out = generate(tmp_path)
    # out_dir is .claude when that folder exists
    assert out.resolve() == (tmp_path / ".claude" / "dashboard.html").resolve()
    html = out.read_text(encoding="utf-8")
    assert "Claude Instructions" in html
    assert ".claude/CLAUDE.md" in html


def _island(out_path) -> dict:
    html = out_path.read_text(encoding="utf-8")
    raw = html.split('id="acc-data"', 1)[1].split(">", 1)[1].split("</script>", 1)[0]
    return json.loads(raw.replace("<\\/", "</"))


def test_generate_merges_all_providers(tmp_path):
    make_multi_provider_repo(tmp_path)
    out = generate(tmp_path)
    data = _island(out)
    ids = {p["id"] for p in data["providers"]}
    assert {"claude", "codex", "cursor", "generic"} <= ids
    assert any(a["typeLabel"] == "Claude agent" for a in data["inventory"]["agents"])
    assert any(r["typeLabel"] == "Cursor rule" for r in data["inventory"]["rules"])
    assert data["inventory"]["mcpServers"], "expected merged mcp servers"


def test_generate_owner_is_dot_claude_for_multi(tmp_path):
    make_multi_provider_repo(tmp_path)
    out = generate(tmp_path)
    assert out.resolve() == (tmp_path / ".claude" / "dashboard.html").resolve()


def test_generate_multi_provider_is_deterministic(tmp_path):
    make_multi_provider_repo(tmp_path)
    first = generate(tmp_path).read_text(encoding="utf-8")
    second = generate(tmp_path).read_text(encoding="utf-8")
    assert first == second


def test_generic_does_not_double_list_provider_files(tmp_path):
    make_multi_provider_repo(tmp_path)
    data = _island(generate(tmp_path))
    ref_paths = [d["path"] for d in data["docs"]["references"]]
    # provider files appear via their adapters, never duplicated by generic
    assert ref_paths == sorted(set(ref_paths))
    # the loose doc is indexed; the agent file is NOT a generic reference
    assert "docs/notes.md" in ref_paths
    assert ".claude/agents/reviewer.md" not in ref_paths


def test_generate_preserves_provider_doc_todos(tmp_path):
    # CLAUDE.md is claimed by the Claude adapter (which does not extract TODOs)
    # and excluded from generic indexing — its open TODOs must still surface
    (tmp_path / ".claude").mkdir()
    (tmp_path / "CLAUDE.md").write_text(
        "# Rules\n\n- [ ] wire up CI\n- [x] already done\n")
    data = _island(generate(tmp_path))
    todos = [t["text"] for t in data["project"]["openTodos"]]
    assert "wire up CI" in todos
    assert "already done" not in todos  # checked items are not open TODOs


def test_generate_survives_list_valued_mcp_command(tmp_path):
    # valid JSON, wrong leaf shape: `command` is a list, not a string. It must
    # degrade to an empty summary, not crash generate() when display fields are
    # html-escaped (a list has no .replace). Mirrors the no-crash contract that
    # test_survives_wrong_shape_mcp_and_hooks holds for container shapes.
    (tmp_path / ".claude").mkdir()
    (tmp_path / "CLAUDE.md").write_text("# Rules\n")
    (tmp_path / ".mcp.json").write_text(
        '{"mcpServers": {"weird": {"command": ["node", "server.js"], "type": "stdio"}}}')
    data = _island(generate(tmp_path))
    weird = next(m for m in data["inventory"]["mcpServers"] if m["title"] == "weird")
    assert weird["summary"] == ""


def test_generate_drops_mcp_env_secret(tmp_path):
    make_claude_repo(tmp_path)
    out = generate(tmp_path)
    assert "s3cr3tpassword" not in out.read_text(encoding="utf-8")


def test_generate_tripwire_blocks_unredacted_leak(tmp_path):
    # an agent whose frontmatter description carries a token shape
    make_claude_repo(tmp_path, with_secret=True)
    out = generate(tmp_path)
    # the description is redacted, so the token never reaches the file
    assert "ghp_0123456789abcdefghij" not in out.read_text(encoding="utf-8")


def test_generate_escapes_hostile_title(tmp_path):
    # a hostile frontmatter name lands in an item title — must be escaped in the island
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "x.md").write_text(
        '---\nname: "<img src=x onerror=alert(1)>"\ndescription: ok\n---\n')
    html = generate(tmp_path).read_text(encoding="utf-8")
    assert "onerror=alert(1)>" not in html
    assert "&lt;img" in html


def test_generate_digest_ignores_stale_other_dashboard(tmp_path):
    make_codex_repo(tmp_path)
    out_dir = tmp_path / ".codex"
    first = generate(tmp_path, out_dir=out_dir).read_text(encoding="utf-8")
    # a stale dashboard left in another provider folder must not perturb the digest
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "dashboard.html").write_text("<stale>" * 100)
    second = generate(tmp_path, out_dir=out_dir).read_text(encoding="utf-8")

    def dig(h):
        return re.search(r'"sourceDigest":"([0-9a-f]+)"', h).group(1)

    assert dig(first) == dig(second)


def test_pathprefix_is_dotdot_for_provider_owner(tmp_path):
    make_claude_repo(tmp_path)
    data = _island(generate(tmp_path))
    assert data["source"]["pathPrefix"] == ".."


def test_pathprefix_is_dot_when_out_is_root(tmp_path):
    make_claude_repo(tmp_path)
    data = _island(generate(tmp_path, out_dir=tmp_path))
    assert data["source"]["pathPrefix"] == "."


def test_pathprefix_for_nested_out_dir(tmp_path):
    make_claude_repo(tmp_path)
    data = _island(generate(tmp_path, out_dir=tmp_path / "a" / "b"))
    assert data["source"]["pathPrefix"] == "../.."


def test_pathprefix_empty_when_relpath_fails(tmp_path, monkeypatch):
    make_claude_repo(tmp_path)

    def boom(*a, **k):
        raise ValueError("different drive")

    # acc.generate calls os.path.relpath, and os.path is a shared module object, so patching it here affects the generator too.
    monkeypatch.setattr(os.path, "relpath", boom)
    data = _island(generate(tmp_path))
    assert data["source"]["pathPrefix"] == ""


def test_generator_truncated_defaults_false(tmp_path):
    make_claude_repo(tmp_path)
    data = _island(generate(tmp_path))
    assert data["generator"]["truncated"] is False


def test_over_2mb_truncates_to_summary_only(tmp_path):
    make_claude_repo(tmp_path)        # real inventory items (agent/command/skill/hook/mcp)
    make_large_repo(tmp_path, 150)    # bulk docs to exceed 2 MB
    data = _island(generate(tmp_path))
    assert data["generator"]["truncated"] is True
    assert data["search"] and all(r["text"] == "" for r in data["search"])
    for d in data["docs"]["references"]:
        assert d["summary"] == "" and d["html"] == ""
        assert "id" in d and "title" in d and "path" in d  # shape intact
    # inventory summaries are blanked too (heaviest non-doc strings)
    inv_items = [it for bucket in data["inventory"].values() for it in bucket]
    assert inv_items, "fixture must have inventory to test inventory blanking"
    for it in inv_items:
        assert it["summary"] == ""


def test_between_1_and_2mb_warns_and_keeps_full(tmp_path, caplog):
    make_large_repo(tmp_path, 45)
    with caplog.at_level(logging.WARNING):
        data = _island(generate(tmp_path))
    assert data["generator"]["truncated"] is False
    assert any(d["html"] for d in data["docs"]["references"])  # full kept
    assert "exceeds" in caplog.text


def test_small_repo_not_truncated(tmp_path):
    make_claude_repo(tmp_path)
    data = _island(generate(tmp_path))
    assert data["generator"]["truncated"] is False


def test_todo_records_have_ids(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / "CLAUDE.md").write_text("# Rules\n\n- [ ] wire up CI\n")
    data = _island(generate(tmp_path))
    todos = data["project"]["openTodos"]
    assert todos and all(t.get("id") and len(t["id"]) == 12 for t in todos)


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
    # "héllo " has no HTML-special chars so html.escape is a no-op here; escape
    # correctness on hostile input is covered at the island level in a later task.
    assert slice_ == long_body[:_SEARCH_BODY_CHARS]    # clean codepoint cut


def test_build_search_record_shape_and_doc_type_label(tmp_path):
    make_multi_provider_repo(tmp_path)
    data = _island(generate(tmp_path))
    recs = data["search"]
    assert recs, "expected search records"
    required = {"id", "type", "typeLabel", "title", "path", "text"}
    for r in recs:
        assert required <= set(r.keys())
        assert all(isinstance(r[k], str) for k in required)
    agent = next(r for r in recs if r["typeLabel"] == "Claude agent")
    assert agent["type"] == "agent"
    doc = next(r for r in recs if r["type"] == "doc")
    assert doc["typeLabel"] in {"Reference", "PRD", "ADR", "Decision", "Workflow"}


def test_build_search_includes_todos(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / "CLAUDE.md").write_text("# Rules\n\n- [ ] wire up CI pipeline\n")
    data = _island(generate(tmp_path))
    todo_recs = [r for r in data["search"] if r["type"] == "todo"]
    assert todo_recs, "TODOs must be in the search index"
    r = todo_recs[0]
    assert r["typeLabel"] == "TODO"
    assert "wire up CI pipeline" in r["title"]
    assert {"id", "type", "typeLabel", "title", "path", "text"} <= set(r.keys())
    # the todo id matches the rendered row id (jumpable)
    todo_ids = {t["id"] for t in data["project"]["openTodos"]}
    assert r["id"] in todo_ids


def test_build_search_appends_escaped_body_slice():
    from acc.generate import _build_search
    inv = {"agents": [{"id": "i1", "type": "agent", "typeLabel": "Claude agent",
                       "title": "A", "path": "a.md", "summary": "sum",
                       "_searchBody": "BODYSLICE"}]}
    docs = {"references": []}
    recs = _build_search(inv, docs, [])
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


def test_private_search_body_key_not_in_island(tmp_path):
    make_multi_provider_repo(tmp_path)
    html = generate(tmp_path).read_text(encoding="utf-8")
    assert "_searchBody" not in html


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


def test_reduce_keeps_declares_caps_references():
    from acc.generate import _reduce_for_size, _MAX_DEGRADED_REFERENCE_EDGES
    refs = [{"from": f"d{i:04d}", "to": f"t{i:04d}", "type": "reference", "evidence": "p"}
            for i in range(_MAX_DEGRADED_REFERENCE_EDGES + 50)]
    decl = [{"from": "c", "to": f"m{i}", "type": "declares", "evidence": "cfg"}
            for i in range(10)]
    data = {
        "inventory": {"agents": [], "skills": [], "hooks": [], "commands": [],
                      "mcpServers": [], "rules": []},
        "docs": {"references": [], "prds": [], "adrs": [], "decisions": [], "workflows": []},
        "search": [], "generator": {"truncated": False},
        "relationships": decl + refs,
    }
    reduced = _reduce_for_size(data)
    kept = reduced["relationships"]
    assert sum(1 for e in kept if e["type"] == "declares") == 10
    assert sum(1 for e in kept if e["type"] == "reference") == _MAX_DEGRADED_REFERENCE_EDGES
    assert kept == sorted(kept, key=lambda e: (e["from"], e["to"], e["type"]))
