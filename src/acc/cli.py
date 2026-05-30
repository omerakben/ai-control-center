import argparse
import sys
from pathlib import Path

from .generate import generate, OwnerAmbiguousError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="acc", description="Generate the AI control center dashboard")
    parser.add_argument("--root", default=".", help="repo root to scan")
    parser.add_argument("--out", default=None, help="output directory (default: auto-detect provider folder)")
    parser.add_argument("--owner", default=None,
                        help="provider folder to own the dashboard when more than one exists")
    args = parser.parse_args(argv)
    out_dir = Path(args.out) if args.out else None
    try:
        dashboard = generate(Path(args.root), out_dir, owner=args.owner)
    except OwnerAmbiguousError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"wrote {dashboard}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
