"""Command-line entry point for sb-pull.

Every subcommand prints one JSON object to stdout. Errors print
``{"error": ...}`` to stderr and exit non-zero. This is the contract the Alfred
front-end depends on (SPEC.md section 4).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys

from sb_pull import __version__
from sb_pull.config import load_config
from sb_pull.jobs import list_jobs
from sb_pull.rtorrent import RTorrent


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sb-pull", description="Seedbox to Plex pull agent.")
    parser.add_argument("--version", action="version", version=f"sb-pull {__version__}")
    parser.add_argument("--json", action="store_true", help="JSON output (default and only format)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List completed torrents on the seedbox")
    sub.add_parser("status", help="List transfer jobs")
    cfg = sub.add_parser("config", help="Show configuration")
    cfg.add_argument("action", choices=["get"], nargs="?", default="get")
    return parser


def _cmd_list() -> dict[str, object]:
    cfg = load_config()
    client = RTorrent(cfg.rtorrent_url, cfg.rtorrent_user, cfg.rtorrent_pass, cfg.sftp_base)
    return {"items": [dataclasses.asdict(t) for t in client.list_completed()]}


def _cmd_status() -> dict[str, object]:
    cfg = load_config()
    return {"jobs": list_jobs(cfg.staging_root)}


def _cmd_config() -> dict[str, object]:
    return load_config().as_dict()


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            payload = _cmd_list()
        elif args.command == "status":
            payload = _cmd_status()
        else:
            payload = _cmd_config()
    except Exception as exc:  # noqa: BLE001 - surface any failure as JSON to the caller
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
