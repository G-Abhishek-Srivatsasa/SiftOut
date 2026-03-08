"""
siftout.cli
~~~~~~~~~~~

Command-line interface for Siftout.

Usage
-----
    siftout clean   [OPTIONS]
    siftout secure  [OPTIONS]
    siftout scan    [OPTIONS]
    siftout summary [OPTIONS]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path


def _get_janitor(args: argparse.Namespace):
    from siftout import Janitor  # lazy import for faster help output

    extra = args.patterns if hasattr(args, "patterns") and args.patterns else []
    return Janitor(
        extra_patterns=extra,
        root=getattr(args, "root", None),
        dry_run=getattr(args, "dry_run", False),
        backup=not getattr(args, "no_backup", False),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sub-command handlers
# ─────────────────────────────────────────────────────────────────────────────
def _cmd_clean(args: argparse.Namespace) -> int:
    j = _get_janitor(args)
    if args.list_only:
        items = j.list_trash()
        if not items:
            print("✅  Nothing to clean.")
        else:
            for item in items:
                print(item)
        return 0

    report = j.self_destruct()
    if args.json:
        print(json.dumps(dict(report), indent=2))
    else:
        print(
            f"\n🧹  Siftout Clean Report\n"
            f"   Files   removed : {report['files']}\n"
            f"   Folders removed : {report['folders']}\n"
            f"   Bytes   freed   : {report['bytes_freed']:,}\n"
            f"   Errors          : {report['errors']}\n"
            + ("   [DRY RUN — no changes made]\n" if j.dry_run else "")
        )
    return 0 if report["errors"] == 0 else 1


def _cmd_secure(args: argparse.Namespace) -> int:
    j = _get_janitor(args)
    report = j.secure_env()
    if args.json:
        print(json.dumps(dict(report), indent=2))
    else:
        print(
            f"\n🛡️   Siftout Secure Report\n"
            f"   Secrets found       : {report['secrets_found']}\n"
            f"   Files patched       : {report['files_patched']}\n"
            f"   .env entries written: {report['env_entries_written']}\n"
            + ("   [DRY RUN — no changes made]\n" if j.dry_run else "")
        )
    return 0


def _cmd_scan(args: argparse.Namespace) -> int:
    j = _get_janitor(args)
    duplicates = j.scan_duplicates()
    if args.json:
        print(json.dumps({k: [str(p) for p in v] for k, v in duplicates.items()}, indent=2))
    else:
        if not duplicates:
            print("✅  No duplicate files found.")
        else:
            print(f"\n🔍  Siftout Duplicate Scan — {len(duplicates)} group(s) found\n")
            for i, (h, paths) in enumerate(duplicates.items(), 1):
                print(f"  Group {i}  [{h[:12]}…]")
                for p in paths:
                    print(f"    {p}")
    return 0


def _cmd_summary(args: argparse.Namespace) -> int:
    j = _get_janitor(args)
    data = j.summary()
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(
            f"\n📊  Siftout Workspace Summary\n"
            f"   Root              : {data['root']}\n"
            f"   Platform          : {data['platform']}\n"
            f"   Trash items       : {data['trash_items']}\n"
            f"   Trash size        : {data['trash_size_bytes']:,} bytes\n"
            f"   Potential secrets : {data['potential_secrets']}\n"
            f"   Duplicate groups  : {data['duplicate_groups']}\n"
            f"   Generated at      : {data['generated_at']}\n"
        )
        if data["secret_locations"]:
            print("   Secret locations:")
            for loc in data["secret_locations"]:
                print(f"     ⚠️   {loc}")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────────────────────────────────────
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="siftout",
        description="🧹  Siftout — smart workspace cleaner & security hardener",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  siftout clean\n"
            "  siftout clean --dry-run --patterns '*.bak' '*.swp'\n"
            "  siftout secure --dry-run\n"
            "  siftout scan --json\n"
            "  siftout summary\n"
        ),
    )
    parser.add_argument("--version", action="version", version="siftout 1.0.0")

    # Common flags
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--root", metavar="DIR", default=None, help="Root directory (default: cwd)"
    )
    common.add_argument(
        "--patterns",
        nargs="*",
        metavar="GLOB",
        help="Extra glob patterns to include",
    )
    common.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview changes without modifying anything",
    )
    common.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output report as JSON",
    )
    common.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Verbose logging",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # clean
    p_clean = sub.add_parser("clean", parents=[common], help="Delete trash files/folders")
    p_clean.add_argument(
        "--list",
        dest="list_only",
        action="store_true",
        help="List items without deleting",
    )
    p_clean.set_defaults(func=_cmd_clean)

    # secure
    p_secure = sub.add_parser("secure", parents=[common], help="Detect & remove hardcoded secrets")
    p_secure.add_argument(
        "--no-backup",
        action="store_true",
        default=False,
        help="Skip .siftout.bak backup files when patching",
    )
    p_secure.set_defaults(func=_cmd_secure)

    # scan
    p_scan = sub.add_parser("scan", parents=[common], help="Find duplicate files")
    p_scan.set_defaults(func=_cmd_scan)

    # summary
    p_summary = sub.add_parser("summary", parents=[common], help="Workspace health overview")
    p_summary.set_defaults(func=_cmd_summary)

    return parser


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    level = logging.DEBUG if getattr(args, "verbose", False) else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())