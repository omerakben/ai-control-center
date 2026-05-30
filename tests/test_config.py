import json
import logging
from acc.config import load_json, load_toml, safe_mcp, MCP_ALLOWED


def test_load_json_reads_object(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"a": 1}))
    assert load_json(p) == {"a": 1}


def test_load_json_returns_empty_on_missing(tmp_path):
    assert load_json(tmp_path / "nope.json") == {}


def test_load_json_returns_empty_on_malformed(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{ not valid json")
    assert load_json(p) == {}


def test_load_toml_reads_tables(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('model = "gpt-5.5"\n[mcp_servers.ctx]\ncommand = "npx"\n')
    data = load_toml(p)
    assert data["model"] == "gpt-5.5"
    assert data["mcp_servers"]["ctx"]["command"] == "npx"


def test_load_toml_returns_empty_on_malformed(tmp_path):
    p = tmp_path / "bad.toml"
    p.write_text("this is = not [valid toml")
    assert load_toml(p) == {}


def test_load_json_warns_on_malformed(tmp_path, caplog):
    p = tmp_path / "bad.json"
    p.write_text("{ not valid json")
    with caplog.at_level(logging.WARNING):
        assert load_json(p) == {}
    assert "bad.json" in caplog.text


def test_load_toml_warns_on_malformed(tmp_path, caplog):
    p = tmp_path / "bad.toml"
    p.write_text("this is = not [valid toml")
    with caplog.at_level(logging.WARNING):
        assert load_toml(p) == {}
    assert "bad.toml" in caplog.text


def test_missing_config_does_not_warn(tmp_path, caplog):
    # absent config files are the common case — they must not produce noise
    with caplog.at_level(logging.WARNING):
        assert load_json(tmp_path / "nope.json") == {}
        assert load_toml(tmp_path / "nope.toml") == {}
    assert caplog.text == ""


def test_safe_mcp_keeps_allowlisted_drops_env():
    server = {"command": "npx", "args": ["-y", "pg-mcp"],
              "type": "stdio", "url": "https://h",
              "env": {"PGPASSWORD": "s3cr3tpassword"}, "headers": {"X": "y"}}
    clean = safe_mcp(server)
    assert set(clean.keys()) <= MCP_ALLOWED
    assert "env" not in clean and "headers" not in clean
    assert "s3cr3tpassword" not in str(clean)
    assert clean["command"] == "npx"


def test_safe_mcp_redacts_credential_url():
    clean = safe_mcp({"url": "https://user:p4ssw0rd@h/x"})
    assert "p4ssw0rd" not in str(clean)
