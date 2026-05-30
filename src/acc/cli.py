import argparse
from pathlib import Path
from .generate import generate


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="acc", description="Generate the AI control center dashboard")
    parser.add_argument("--root", default=".", help="repo root to scan")
    parser.add_argument("--out", default=None, help="output directory (default: auto-detect provider folder)")
    args = parser.parse_args(argv)
    out_dir = Path(args.out) if args.out else None
    dashboard = generate(Path(args.root), out_dir)
    print(f"wrote {dashboard}")


if __name__ == "__main__":
    main()
