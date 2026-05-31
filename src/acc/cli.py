import argparse
import json
import sys
from pathlib import Path

from .generate import generate_result, OwnerAmbiguousError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="acc", description="Generate the AI control center dashboard")
    parser.add_argument("--root", default=".", help="repo root to scan")
    parser.add_argument("--out", default=None, help="output directory (default: auto-detect provider folder)")
    parser.add_argument("--owner", default=None,
                        help="provider folder to own the dashboard when more than one exists")
    parser.add_argument("--json", action="store_true",
                        help="emit a machine-readable result (path, digest, file count, providers)")
    args = parser.parse_args(argv)
    out_dir = Path(args.out) if args.out else None
    try:
        res = generate_result(Path(args.root), out_dir, owner=args.owner)
    except OwnerAmbiguousError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({
            "dashboardPath": str(res.path),
            "sourceDigest": res.source_digest,
            "scannedFileCount": res.scanned_file_count,
            "providers": res.providers,
            "truncated": res.truncated,
        }))
    else:
        print(f"wrote {res.path}")
        print(f"  digest {res.source_digest} · {res.scanned_file_count} files scanned "
              f"· providers: {', '.join(res.providers)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
