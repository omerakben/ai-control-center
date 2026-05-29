from pathlib import Path
from .schema import canonical_json

_TEMPLATES = Path(__file__).resolve().parent.parent.parent / "templates"


def _read(name: str) -> str:
    path = _TEMPLATES / name
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise FileNotFoundError(f"template not found: {path}") from e


def render_html(data: dict) -> str:
    template = _read("dashboard.html.tmpl")
    css = _read("styles.css")
    app_js = _read("app.js")
    island = canonical_json(data).replace("</", "<\\/")
    # Substitute the untrusted data island LAST, so later replacements cannot
    # corrupt island content that happens to contain a placeholder string.
    return (
        template
        .replace("/*__CSS__*/", css)
        .replace("/*__APP_JS__*/", app_js)
        .replace("__SCHEMA_VERSION__", data["schemaVersion"])
        .replace("__DATA_ISLAND__", island)
    )
