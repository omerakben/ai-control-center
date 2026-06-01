from importlib.resources import files
from .schema import canonical_json


def _read(name: str) -> str:
    # Load templates as package data so render works both in-tree and after a
    # `pip install` (templates live at src/acc/templates and ship as package data).
    return files("acc").joinpath("templates", name).read_text(encoding="utf-8")


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
        # The <meta name="generator"> tag carries the tool release (generator.version),
        # not schemaVersion — those are different axes (the data island still holds
        # schemaVersion). Done before the island so island content cannot be perturbed.
        .replace("__GENERATOR_VERSION__", data["generator"]["version"])
        .replace("__DATA_ISLAND__", island)
    )
