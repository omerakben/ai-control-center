from importlib.resources import files


def test_templates_are_bundled_as_package_data():
    # templates must live inside the installed `acc` package, not at repo root,
    # so a pip-installed CLI can find them.
    root = files("acc").joinpath("templates")
    for name in ("dashboard.html.tmpl", "styles.css", "app.js"):
        assert root.joinpath(name).is_file(), name
