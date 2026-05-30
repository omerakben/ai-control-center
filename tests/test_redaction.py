from acc.redaction import redact_text, allowlist_config, find_secrets


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


def test_redacts_compound_env_credential_names():
    # UPPER_SNAKE_CASE credential names must not slip past the keyword redactor
    cases = {
        'AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMIK7MDENGbValueXYZ"': "wJalrXUtnFEMIK",
        "GITHUB_TOKEN=ghp_realtokenvalue1234567": "realtokenvalue",
        "OPENAI_API_KEY: sk-projlongsecretvalue123": "longsecretvalue",
        "DATABASE_PASSWORD = hunter2hunter2": "hunter2hunter2",
        "MY_CLIENT_SECRET=abcdef123456": "abcdef123456",
    }
    for line, secret in cases.items():
        out, n = redact_text(line)
        assert secret not in out, line
        assert n >= 1, line


def test_redacts_hard_secret_formats():
    aws, n1 = redact_text("id AKIAIOSFODNN7EXAMPLE here")
    assert "AKIAIOSFODNN7EXAMPLE" not in aws and n1 >= 1
    jwt_tok = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
               "eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJVadQssw5c")
    jwt, n2 = redact_text(f"token {jwt_tok}")
    assert "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJVadQssw5c" not in jwt and n2 >= 1
    pem, n3 = redact_text("-----BEGIN RSA PRIVATE KEY-----")
    assert n3 >= 1


def test_does_not_over_redact_compound_lookalikes():
    # keyword glued to letters (no separator, no assignment) is prose, not a secret
    for clean in ("the tokenizer parses input", "ask the secretary today",
                  "a passwordless login flow"):
        out, n = redact_text(clean)
        assert out == clean and n == 0, clean


def test_find_secrets_counts_without_mutating():
    assert find_secrets("a normal sentence") == 0
    assert find_secrets("GITHUB_TOKEN=ghp_realtokenvalue1234567") >= 1
