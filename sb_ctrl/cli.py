"""Command-line entry point for sb-ctrl.

Every subcommand prints one JSON object to stdout. Errors print
``{"error": ...}`` to stderr and exit non-zero. This is the contract the Alfred
front-end depends on (SPEC.md section 4). ``plan`` and ``run`` read their JSON
input from stdin.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from typing import IO, Any

from sb_ctrl import __version__, launcher, planner, worker
from sb_ctrl.config import Config, load_config
from sb_ctrl.jobs import create_job, jobs_dir, list_jobs, write_state
from sb_ctrl.rtorrent import RTorrent


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sb-ctrl", description="Seedbox to Plex pull agent.")
    parser.add_argument("--version", action="version", version=f"sb-ctrl {__version__}")
    parser.add_argument("--json", action="store_true", help="JSON output (default and only format)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List completed torrents on the seedbox")
    sub.add_parser("status", help="List transfer jobs")
    cfg = sub.add_parser("config", help="Show configuration")
    cfg.add_argument("action", choices=["get"], nargs="?", default="get")
    sub.add_parser("plan", help="Plan a transfer (reads JSON from stdin)")
    sub.add_parser("run", help="Start a transfer (reads a job spec from stdin)")
    rj = sub.add_parser("run-job", help="Run a job in the foreground (internal)")
    rj.add_argument("job_id")
    rt = sub.add_parser("retry", help="Re-run a failed job")
    rt.add_argument("job_id")
    return parser


def _client(cfg: Config) -> RTorrent:
    return RTorrent(cfg.rtorrent_url, cfg.rtorrent_user, cfg.rtorrent_pass, cfg.sftp_base)


def _cmd_list() -> dict[str, Any]:
    cfg = load_config()
    return {"items": [dataclasses.asdict(t) for t in _client(cfg).list_completed()]}


def _cmd_status() -> dict[str, Any]:
    return {"jobs": list_jobs(load_config().staging_root)}


def _cmd_config() -> dict[str, Any]:
    return load_config().as_dict()


def _cmd_plan(stream: IO[str]) -> dict[str, Any]:
    cfg = load_config()
    data = json.loads(stream.read())
    torrents = _client(cfg).list_completed()
    match = next((t for t in torrents if t.hash == data["hash"]), None)
    if match is None:
        raise ValueError("torrent not found")
    return planner.plan(cfg, dataclasses.asdict(match), data["kind"], data.get("name"))


def _cmd_run(stream: IO[str]) -> dict[str, Any]:
    cfg = load_config()
    data = json.loads(stream.read())
    spec = data["job_spec"]
    collision = data.get("collision", "overwrite")
    if os.path.exists(spec["dest_path"]) and collision != "overwrite":
        return {"skipped": True, "dest_path": spec["dest_path"]}
    job = create_job(cfg.staging_root, spec)
    mode = launcher.launch(job.name)
    return {"job_id": job.name, "launcher": mode}


def _cmd_run_job(job_id: str) -> dict[str, Any]:
    cfg = load_config()
    worker.run_job(jobs_dir(cfg.staging_root) / job_id)
    return {"ok": True, "job_id": job_id}


def _cmd_retry(job_id: str) -> dict[str, Any]:
    cfg = load_config()
    write_state(jobs_dir(cfg.staging_root) / job_id, state="queued", error="", pct=0)
    mode = launcher.launch(job_id)
    return {"job_id": job_id, "launcher": mode}


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            payload = _cmd_list()
        elif args.command == "status":
            payload = _cmd_status()
        elif args.command == "config":
            payload = _cmd_config()
        elif args.command == "plan":
            payload = _cmd_plan(sys.stdin)
        elif args.command == "run":
            payload = _cmd_run(sys.stdin)
        elif args.command == "run-job":
            payload = _cmd_run_job(args.job_id)
        else:
            payload = _cmd_retry(args.job_id)
    except Exception as exc:  # noqa: BLE001 - surface any failure as JSON to the caller
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
