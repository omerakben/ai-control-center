from acc.adapters.base import make_item, empty_inventory, empty_docs, doc_type_label


def test_make_item_has_full_shape_and_stable_id():
    a = make_item("claude", "agent", "Claude agent", "reviewer", ".claude/agents/reviewer.md", "sums")
    b = make_item("claude", "agent", "Claude agent", "reviewer", ".claude/agents/reviewer.md", "sums")
    assert a == b
    assert a["provider"] == "claude"
    assert a["type"] == "agent"
    assert a["typeLabel"] == "Claude agent"
    assert a["title"] == "reviewer"
    assert a["path"] == ".claude/agents/reviewer.md"
    assert a["summary"] == "sums"
    assert len(a["id"]) == 12


def test_make_item_id_varies_with_inputs():
    base = make_item("claude", "agent", "Claude agent", "reviewer", ".claude/agents/reviewer.md", "")
    other = make_item("cursor", "rule", "Cursor rule", "reviewer", ".claude/agents/reviewer.md", "")
    assert base["id"] != other["id"]


def test_empty_shapes_have_expected_buckets():
    assert set(empty_inventory()) == {"agents", "skills", "hooks", "commands", "mcpServers", "rules"}
    assert set(empty_docs()) == {"prds", "adrs", "decisions", "workflows", "references"}
    assert all(v == [] for v in empty_inventory().values())


def test_doc_type_label_maps_buckets():
    assert doc_type_label("references") == "Reference"
    assert doc_type_label("prds") == "PRD"
    assert doc_type_label("adrs") == "ADR"
    assert doc_type_label("decisions") == "Decision"
    assert doc_type_label("workflows") == "Workflow"


def test_doc_type_label_unknown_bucket_titlecases():
    assert doc_type_label("misc") == "Misc"


def test_extract_metadata_safe_fields():
    from acc.adapters.base import extract_metadata
    fields = {
        "name": "omit",
        "title": "omit",
        "description": "omit",
        "summary": "omit",
        "version": "1.0.0",
        "status": True,
        "priority": 5,
        "tags": ["dev", "prod"],
        "nested": {"complex": "omit"}
    }
    meta = extract_metadata(fields)
    assert meta == {
        "version": "1.0.0",
        "status": True,
        "priority": 5,
        "tags": ["dev", "prod"]
    }
    assert extract_metadata(None) == {}
    assert extract_metadata(["bad", "frontmatter"]) == {}
