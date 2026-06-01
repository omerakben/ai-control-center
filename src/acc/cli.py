import argparse
import json
import sys
from pathlib import Path

from .generate import generate_result, OwnerAmbiguousError
from .doctor import run_doctor


def _generate(args) -> int:
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


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    # Back-compat: a bare `acc` or a leading flag (`acc --root .`, `acc --json`)
    # means the default `generate` command. Only -h/--help fall through to the
    # top-level parser so users still discover the subcommands.
    if not argv or (argv[0].startswith("-") and argv[0] not in ("-h", "--help")):
        argv = ["generate", *argv]

    parser = argparse.ArgumentParser(
        prog="acc",
        description="Agent Context Center — map a repo's AI context (AGENTS.md, "
                    "CLAUDE.md, Cursor rules, skills, hooks, commands, MCP, docs) into "
                    "one self-contained offline HTML dashboard.")
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="generate the dashboard (default command)")
    g.add_argument("--root", default=".", help="repo root to scan")
    g.add_argument("--out", default=None, help="output directory (default: auto-detect provider folder)")
    g.add_argument("--owner", default=None,
                   help="provider folder to own the dashboard when more than one exists")
    g.add_argument("--json", action="store_true",
                   help="emit a machine-readable result (path, digest, file count, providers)")

    d = sub.add_parser("doctor", help="report stale/weak/broken findings for the repo's AI context")
    d.add_argument("--root", default=".", help="repo root to check")
    d.add_argument("--strict", action="store_true", help="exit non-zero when any warning is found")
    d.add_argument("--json", action="store_true", help="emit a machine-readable doctor.v1 report")

    args = parser.parse_args(argv)
    if args.command == "doctor":
        return run_doctor(Path(args.root), strict=args.strict, as_json=args.json)
    return _generate(args)


if __name__ == "__main__":
    raise SystemExit(main())
