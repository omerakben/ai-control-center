from acc.redaction import redact_text, allowlist_config


def test_redacts_bearer_token():
    out, n = redact_text("Authorization: Bearer abcDEF123456789")
    assert "abcDEF123456789" not in out
    assert n == 1


def test_redacts_keyword_assignment():
    out, n = redact_text('api_key = "sk-supersecretvalue123"')
    assert "supersecretvalue" not in out
    assert n >= 1


def test_redacts_provider_prefixed_key():
    out, n = redact_text("token ghp_0123456789abcdefghij")
    assert "ghp_0123456789abcdefghij" not in out
    assert n >= 1


def test_redacts_url_with_credentials():
    out, n = redact_text("postgres://user:p4ssw0rd@db.example.com/app")
    assert "p4ssw0rd" not in out
    assert n == 1


def test_leaves_clean_text_untouched():
    text = "This is a normal sentence about skills and agents."
    out, n = redact_text(text)
    assert out == text
    assert n == 0


def test_allowlist_drops_unlisted_keys_and_redacts_values():
    cfg = {"command": "npx", "args": ["-y", "pkg", "--token", "ghp_0123456789abcdefghij"],
           "env": {"SECRET": "x"}}
    clean = allowlist_config(cfg, {"command", "args"})
    assert "env" not in clean
    assert clean["command"] == "npx"
    assert "ghp_0123456789abcdefghij" not in " ".join(clean["args"])


def test_redacts_closed_quote_without_dangling_quote():
    # the closing quote must be redacted too — no `[redacted]"` left behind
    out, n = redact_text('api_key = "abc123defXYZ"')
    assert "abc123defXYZ" not in out
    assert n >= 1
    assert '"' not in out


def test_redacts_unclosed_quote_assignment():
    # a malformed/unclosed quote must STILL be redacted (no leak)
    out, n = redact_text('api_key = "abc123defXYZ')
    assert "abc123defXYZ" not in out
    assert n >= 1


def test_redacts_multi_segment_provider_tokens():
    for token in ("sk-proj-abc123DEF456ghi", "sk_live_abc123DEF456ghi", "xoxb-123-456-abcdefghij"):
        out, n = redact_text(f"key: {token}")
        assert token not in out, token
        assert n >= 1
