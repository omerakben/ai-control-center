from acc.frontmatter import parse_frontmatter


def test_no_fence_returns_empty_fields_and_full_body():
    fields, body = parse_frontmatter("# Title\n\nbody text")
    assert fields == {}
    assert body == "# Title\n\nbody text"


def test_parses_simple_keys_and_body():
    text = "---\nname: reviewer\ndescription: Reviews code\n---\n\n# Reviewer\n\nbody"
    fields, body = parse_frontmatter(text)
    assert fields["name"] == "reviewer"
    assert fields["description"] == "Reviews code"
    assert body == "\n# Reviewer\n\nbody"


def test_strips_quotes_and_parses_booleans():
    text = '---\ndescription: "Quoted value"\nalwaysApply: true\ndraft: false\n---\nx'
    fields, _ = parse_frontmatter(text)
    assert fields["description"] == "Quoted value"
    assert fields["alwaysApply"] is True
    assert fields["draft"] is False


def test_parses_inline_list():
    fields, _ = parse_frontmatter('---\ntools: [Read, Grep, Bash]\n---\nx')
    assert fields["tools"] == ["Read", "Grep", "Bash"]


def test_parses_block_list():
    text = "---\ntools:\n  - Read\n  - Grep\n---\nx"
    fields, _ = parse_frontmatter(text)
    assert fields["tools"] == ["Read", "Grep"]


def test_unclosed_fence_is_not_treated_as_frontmatter():
    text = "---\nname: x\nno closing fence here"
    fields, body = parse_frontmatter(text)
    assert fields == {}
    assert body == text


def test_malformed_lines_are_skipped_not_raised():
    text = "---\nname: ok\n:::garbage:::\nmodel: opus\n---\nx"
    fields, _ = parse_frontmatter(text)
    assert fields["name"] == "ok"
    assert fields["model"] == "opus"
    assert ":::garbage:::" not in fields


def test_double_quoted_escapes_are_decoded():
    # real Claude agent descriptions are one double-quoted line with \n and \"
    text = '---\ndescription: "Line one.\\n\\nExamples:\\nuser: \\"hi\\""\n---\nx'
    fields, _ = parse_frontmatter(text)
    assert fields["description"] == 'Line one.\n\nExamples:\nuser: "hi"'
    assert "\\n" not in fields["description"]   # no literal backslash-n
    assert '\\"' not in fields["description"]    # no literal backslash-quote


def test_single_quoted_does_not_decode_backslashes():
    # YAML single-quotes: only '' -> ', backslashes stay literal (e.g. a regex)
    text = "---\npattern: 'a\\nb'\nname: 'O''Brien'\n---\nx"
    fields, _ = parse_frontmatter(text)
    assert fields["pattern"] == "a\\nb"          # backslash-n stays literal
    assert fields["name"] == "O'Brien"           # '' collapses to one quote


def test_unknown_double_quoted_escape_is_left_literal():
    fields, _ = parse_frontmatter('---\nx: "a\\qb"\n---\ny')
    assert fields["x"] == "a\\qb"                 # \q is not a known escape
