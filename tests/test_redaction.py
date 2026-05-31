from acc.redaction import redact_text, allowlist_config, find_secrets
from acc.markdown import render_markdown_safe


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


def test_redacts_quoted_key_json_assignment():
    # JSON / config form, e.g. an .mcp.json snippet pasted into a doc
    out, n = redact_text('{"PGPASSWORD": "s3cr3tpassword"}')
    assert "s3cr3tpassword" not in out
    assert n >= 1
    out2, _ = redact_text('"api_key":"sk-livesecretvalue123"')
    assert "sk-livesecretvalue123" not in out2


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


def test_doc_example_credentials_do_not_trip_tripwire_after_render():
    # Regression: redaction runs on raw markdown, the tripwire on rendered html.
    # An inline-code placeholder must not be inflated past the 6-char value floor
    # by the trailing </code>/</p> tag once rendered, or every doc that documents
    # a credential env var (e.g. `export XAI_API_KEY=...`) would block the build.
    for raw in (
        "Set `export XAI_API_KEY=...` per shell.",
        "Use `API_KEY=<value>` then rerun.",
        "Detect the `SECRET=`, `TOKEN=`, `PASSWORD=` shapes.",
    ):
        clean, _ = redact_text(raw)
        assert find_secrets(render_markdown_safe(clean)) == 0, raw


def test_real_credential_in_doc_is_redacted_before_render():
    # a genuine long value is still caught at extraction and never reaches html
    raw = "Example: `API_KEY=sk-liverealsecretvalue123456` do not commit."
    clean, _ = redact_text(raw)
    assert "liverealsecretvalue" not in clean
    assert find_secrets(render_markdown_safe(clean)) == 0


def test_redacts_values_containing_html_special_chars():
    # recall must stay on the raw side: a real password with & or < is redacted
    # at extraction. The raw-vs-rendered mismatch is solved in find_secrets, not
    # by weakening this value class (which would leak these straight through).
    cases = {
        "PASSWORD=abc&def456789": "abc&def456789",
        "PASSWORD=abc123&def456789": "abc123&def456789",
        "PASSWORD=<abc123def456": "<abc123def456",
        'PASSWORD="abc&def456789"': "abc&def456789",
        "DATABASE_PASSWORD=postgres://user:p&ssword123@db.example.com/app": "p&ssword123",
    }
    for line, secret in cases.items():
        out, n = redact_text(line)
        assert secret not in out, line
        assert n >= 1, line


def test_tripwire_is_markup_safe():
    # rendered markup — a tag inflating a value, an escaped entity, or a bare
    # KEYWORD= at a code-span end bridging to the next word — must NOT create a
    # false match (these false-blocked a real repo's docs)...
    assert find_secrets("<code>export XAI_API_KEY=...</code>") == 0
    assert find_secrets("<p>SECRET=</p>") == 0
    assert find_secrets("<code>API_KEY=</code> inside a code block") == 0
    assert find_secrets("Use <code>API_KEY=&lt;value&gt;</code> then rerun") == 0
    # ...but a real alphanumeric secret in rendered html is still caught
    assert find_secrets("<code>GITHUB_TOKEN=ghp_realtokenvalue1234567</code>") >= 1
    assert find_secrets("<code>API_KEY=sk-liverealsecretvalue123456</code>") >= 1


def test_generate_does_not_leak_html_special_char_secret(tmp_path):
    # end-to-end: a real password with & in a doc must not reach the dashboard,
    # in either raw or html-escaped form.
    from acc.generate import generate_result
    (tmp_path / "CLAUDE.md").write_text("# Project\n")
    (tmp_path / "README.md").write_text("Set `PASSWORD=abc&def456789` in local env.\n")
    out = generate_result(tmp_path).path.read_text()
    assert "abc&def456789" not in out
    assert "abc&amp;def456789" not in out


def test_generate_redacts_secret_in_author_title(tmp_path):
    # author-derived TITLES (a skill/agent frontmatter `name:`) bypass markdown
    # rendering, so they are redacted at the central display-field pass — the
    # markup-safe tripwire is not a backstop for a short &/<-prefixed value here.
    from acc.generate import generate_result
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "a.md").write_text(
        "---\nname: PASSWORD=abc&def456789\ndescription: harmless\n---\n\nbody\n")
    (agents / "b.md").write_text(
        "---\nname: TOKEN=<abc123def456>\ndescription: harmless\n---\n\nbody\n")
    (tmp_path / "CLAUDE.md").write_text("# Project\n")
    out = generate_result(tmp_path).path.read_text()
    for leak in ("abc&def456789", "abc&amp;def456789", "abc123def456"):
        assert leak not in out, leak


def test_generate_redacts_secret_in_filename_path(tmp_path):
    # author-controlled FILENAMES can hold a secret-shaped string and reach the
    # island for links without going through markdown render, so paths are
    # redacted centrally too (the markup-safe tripwire stops at & and would miss
    # `PASSWORD=abc&...`).
    from acc.generate import generate_result
    (tmp_path / "CLAUDE.md").write_text("# Project\n")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "PASSWORD=abc&genericpath456789.md").write_text("# Doc\n\nbody\n")
    out = generate_result(tmp_path).path.read_text()
    assert "abc&genericpath456789" not in out
    assert "abc&amp;genericpath456789" not in out


def test_generate_redacts_secret_in_repo_dir_name(tmp_path):
    # source.repoName / dashboardPath derive from the repo's own dir name
    from acc.generate import generate_result
    root = tmp_path / "PASSWORD=abc&reponame456789"
    (root / ".claude").mkdir(parents=True)
    (root / "CLAUDE.md").write_text("# P\n")
    out = generate_result(root).path.read_text()
    assert "abc&reponame456789" not in out
    assert "abc&amp;reponame456789" not in out


def test_generate_redacts_secret_in_todo_path(tmp_path):
    # a TODO carries the path of the file it came from; that path is redacted too
    from acc.generate import generate_result
    (tmp_path / "CLAUDE.md").write_text("# P\n")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "PASSWORD=abc&todopath456789.md").write_text("# Doc\n\n- [ ] do the thing\n")
    out = generate_result(tmp_path).path.read_text()
    assert "abc&todopath456789" not in out
    assert "abc&amp;todopath456789" not in out


def test_allowlist_redacts_secret_dict_key():
    # a nested config key can itself be secret-shaped
    clean = allowlist_config({"args": {"PASSWORD=abc&nestedkey456789": "v"}}, {"args"})
    assert "abc&nestedkey456789" not in str(clean)
