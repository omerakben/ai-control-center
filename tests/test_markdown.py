from acc.markdown import render_markdown_safe


def test_renders_heading_and_paragraph():
    html = render_markdown_safe("# Title\n\nHello world")
    assert "<h1>Title</h1>" in html
    assert "<p>Hello world</p>" in html


def test_renders_list():
    html = render_markdown_safe("- one\n- two")
    assert "<ul>" in html and "<li>one</li>" in html and "<li>two</li>" in html


def test_escapes_raw_html_and_scripts():
    html = render_markdown_safe("normal <script>alert(1)</script> text")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_blocks_javascript_links():
    html = render_markdown_safe("[click](javascript:alert(1))")
    assert 'href="javascript:' not in html


def test_blocks_javascript_md_suffix_bypass():
    html = render_markdown_safe("[x](javascript:void0//y.md)")
    assert 'href="javascript:' not in html


def test_blocks_protocol_relative_links():
    html = render_markdown_safe("[x](//evil.com/exfil)")
    assert 'href="//evil.com' not in html


def test_allows_relative_and_https_links():
    html = render_markdown_safe("[doc](./x.md) and [site](https://example.com)")
    assert 'href="./x.md"' in html
    assert 'href="https://example.com"' in html


def test_renders_plus_bullet_list():
    html = render_markdown_safe("+ alpha\n+ beta")
    assert "<ul>" in html and "<li>alpha</li>" in html and "<li>beta</li>" in html
