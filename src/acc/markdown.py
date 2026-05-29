import html
import re
from urllib.parse import urlparse

_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_CODE = re.compile(r"`([^`]+)`")
_HEADING = re.compile(r"(#{1,6})\s+(.*)")
_LIST_ITEM = re.compile(r"\s*[-*+]\s+")


def _safe_link(match: re.Match) -> str:
    label, url = match.group(1), match.group(2)
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    is_relative = not parsed.scheme and not url.startswith("//")
    if scheme in ("http", "https") or is_relative:
        return f'<a href="{url}">{label}</a>'
    return f"{label} ({url})"


def _inline(text: str) -> str:
    text = html.escape(text)
    text = _CODE.sub(lambda m: f"<code>{m.group(1)}</code>", text)
    text = _LINK.sub(_safe_link, text)
    return text


def render_markdown_safe(md: str) -> str:
    out: list[str] = []
    list_buf: list[str] = []
    code_buf: list[str] = []
    in_code = False

    def flush_list() -> None:
        if list_buf:
            items = "".join(f"<li>{_inline(x)}</li>" for x in list_buf)
            out.append(f"<ul>{items}</ul>")
            list_buf.clear()

    for line in md.splitlines():
        if line.strip().startswith("```"):
            if in_code:
                out.append("<pre><code>" + html.escape("\n".join(code_buf)) + "</code></pre>")
                code_buf.clear()
                in_code = False
            else:
                flush_list()
                in_code = True
            continue
        if in_code:
            code_buf.append(line)
            continue
        heading = _HEADING.match(line)
        if heading:
            flush_list()
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
        elif _LIST_ITEM.match(line):
            list_buf.append(_LIST_ITEM.sub("", line, count=1))
        elif line.strip() == "":
            flush_list()
        else:
            flush_list()
            out.append(f"<p>{_inline(line)}</p>")

    flush_list()
    if in_code:
        out.append("<pre><code>" + html.escape("\n".join(code_buf)) + "</code></pre>")
    return "\n".join(out)
