"""Run the generator as `python3 -m acc`.

The plugin invokes the bundled generator from its cache with the package on
PYTHONPATH, so `python3 -m acc` and `python3 -m acc.cli` both reach the CLI.
"""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
