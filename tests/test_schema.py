import pytest
from acc.schema import SCHEMA_VERSION, canonical_json, validate, assert_no_secrets
from acc.ids import stable_id


def _minimal_data() -> dict:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generator": {"name": "ai-control-center", "version": "0.1.0", "rendererDigest": "x"},
        "source": {"repoName": "r", "dashboardPath": ".ai-control-center/dashboard.html",
                   "sourceDigest": "abc", "vcs": {"kind": "none"}},
        "providers": [],
        "project": {"title": "r", "openTodos": [], "recentDocs": [], "warnings": []},
        "inventory": {"agents": [], "skills": [], "hooks": [], "commands": [], "mcpServers": [], "rules": []},
        "docs": {"prds": [], "adrs": [], "decisions": [], "workflows": [], "references": []},
        "relationships": [],
        "search": [],
    }


def test_canonical_json_is_sorted_and_stable():
    a = canonical_json({"b": 1, "a": 2})
    b = canonical_json({"a": 2, "b": 1})
    assert a == b == '{"a":2,"b":1}'


def test_validate_accepts_minimal_data():
    validate(_minimal_data())  # no exception


def test_validate_rejects_missing_keys():
    data = _minimal_data()
    del data["docs"]
    with pytest.raises(ValueError, match="docs"):
        validate(data)


def test_assert_no_secrets_passes_clean_data():
    assert_no_secrets(_minimal_data())  # no exception


def test_assert_no_secrets_raises_on_leaked_token():
    data = _minimal_data()
    data["project"]["summary"] = "token ghp_0123456789abcdefghij"
    with pytest.raises(ValueError, match="tripwire"):
        assert_no_secrets(data)


def test_validate_runs_the_tripwire():
    data = _minimal_data()
    data["project"]["summary"] = "secret = supersecretvalue123"
    with pytest.raises(ValueError, match="tripwire"):
        validate(data)


def test_tripwire_catches_compound_env_secret():
    # the tripwire must not share the keyword redactor's old compound-name blind spot
    data = _minimal_data()
    data["project"]["summary"] = 'AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMIK7MDENGbValueXYZ"'
    with pytest.raises(ValueError, match="tripwire"):
        validate(data)


def _data_with_search(rec) -> dict:
    data = _minimal_data()
    data["search"] = [rec]
    return data


def _good_record() -> dict:
    return {"id": "i1", "type": "agent", "typeLabel": "Claude agent",
            "title": "A", "path": "a.md", "text": "body"}


def test_validate_accepts_good_search_record():
    validate(_data_with_search(_good_record()))  # no exception


def test_validate_accepts_light_record_empty_text():
    rec = _good_record()
    rec["text"] = ""
    validate(_data_with_search(rec))  # no exception


def test_validate_rejects_search_record_missing_key():
    rec = _good_record()
    del rec["typeLabel"]
    with pytest.raises(ValueError, match="search"):
        validate(_data_with_search(rec))


def test_validate_rejects_search_record_non_string_value():
    rec = _good_record()
    rec["title"] = 123
    with pytest.raises(ValueError, match="search"):
        validate(_data_with_search(rec))


def test_validate_rejects_unknown_search_type():
    rec = _good_record()
    rec["type"] = "bogus"
    with pytest.raises(ValueError, match="search"):
        validate(_data_with_search(rec))


def _base_data(relationships):
    item_id = stable_id("claude", "mcpServer", ".claude/settings.json", "local")
    doc_id = stable_id("claude", "doc", "CLAUDE.md", "My Project")
    inv = {"agents": [], "skills": [], "hooks": [], "commands": [],
           "mcpServers": [{"id": item_id, "provider": "claude", "type": "mcpServer",
                           "typeLabel": "MCP server", "title": "local",
                           "path": ".claude/settings.json", "summary": "node",
                           "config": {}}],
           "rules": []}
    docs = {"prds": [], "adrs": [], "decisions": [], "workflows": [],
            "references": [{"id": doc_id, "title": "My Project", "path": "CLAUDE.md",
                            "summary": "", "html": ""}]}
    return {
        "schemaVersion": "1.0",
        "generator": {"name": "x", "version": "0", "rendererDigest": "", "truncated": False},
        "source": {"repoName": "r", "pathPrefix": "..", "dashboardPath": "d",
                   "sourceDigest": "0", "vcs": {"kind": "none"}},
        "providers": [], "project": {"title": "", "openTodos": []},
        "inventory": inv, "docs": docs, "relationships": relationships, "search": [],
    }, item_id, doc_id


def test_valid_declares_and_reference_pass():
    data, item_id, doc_id = _base_data([])
    node = stable_id("config", "configFile", ".claude/settings.json", "")
    data["relationships"] = [
        {"from": node, "to": item_id, "type": "declares", "evidence": ".claude/settings.json"},
        {"from": doc_id, "to": item_id, "type": "reference", "evidence": ".claude/settings.json"},
    ]
    validate(data)  # no raise


@pytest.mark.parametrize("bad", [
    {"from": "nope", "to": "nope", "type": "reference", "evidence": "x"},
    {"from": "nope", "to": "__ITEM__", "type": "reference", "evidence": "x"},
    {"from": "nope", "to": "__ITEM__", "type": "declares", "evidence": "x"},
    {"from": "__DOC__", "to": "__ITEM__", "type": "owns", "evidence": "x"},
    {"from": "__DOC__", "to": "__ITEM__", "type": "reference", "evidence": 5},
])
def test_invalid_relationship_rejected(bad):
    data, item_id, doc_id = _base_data([])
    edge = {k: (item_id if v == "__ITEM__" else doc_id if v == "__DOC__" else v)
            for k, v in bad.items()}
    data["relationships"] = [edge]
    with pytest.raises(ValueError):
        validate(data)
