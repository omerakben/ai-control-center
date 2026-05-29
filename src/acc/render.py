from pathlib import Path
from .schema import canonical_json

_TEMPLATES = Path(__file__).resolve().parent.parent.parent / "templates"


def _read(name: str) -> str:
    return (_TEMPLATES / name).read_text(encoding="utf-8")


def render_html(data: dict) -> str:
    template = _read("dashboard.html.tmpl")
    css = _read("styles.css")
    app_js = _read("app.js")
    island = canonical_json(data).replace("</", "<\\/")
    return (
        template
        .replace("/*__CSS__*/", css)
        .replace("/*__APP_JS__*/", app_js)
        .replace("__DATA_ISLAND__", island)
        .replace("__SCHEMA_VERSION__", data["schemaVersion"])
    )
