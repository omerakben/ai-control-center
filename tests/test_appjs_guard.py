import re
from importlib.resources import files

_BANNED = re.compile(r"innerHTML|outerHTML|insertAdjacentHTML")


def _app_js() -> str:
    return files("acc").joinpath("templates", "app.js").read_text(encoding="utf-8")


def test_app_js_has_no_html_sinks():
    src = _app_js()
    matches = [ln for ln in src.splitlines() if _BANNED.search(ln)]
    assert not matches, "banned HTML sink in app.js: %r" % matches
