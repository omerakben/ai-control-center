import json
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
