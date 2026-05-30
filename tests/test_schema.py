import pytest
from acc.schema import SCHEMA_VERSION, canonical_json, validate, assert_no_secrets


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
