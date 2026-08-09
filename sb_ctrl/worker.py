"""The transfer worker: pull into staging, set permissions, atomically move into
the library, and record job state (SPEC.md section 8).

The lftp transfer and the ownership change are injected so the orchestration is
tested against a real temp filesystem without a seedbox or root privileges.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sb_ctrl import episodes, lftp
from sb_ctrl.jobs import jobs_dir, read_spec, write_state

# progress(pct, rate, eta)
ProgressCb = Callable[[int, str, str], None]
# transfer(spec, staging_item_path, progress)
Transfer = Callable[[dict[str, Any], Path, ProgressCb], None]
# chowner(path, owner, group)
Chowner = Callable[[Path, str, str], None]


def default_chowner(path: Path, owner: str, group: str) -> None:  # pragma: no cover - needs privileges
    import grp
    import pwd

    uid = pwd.getpwnam(owner).pw_uid
    gid = grp.getgrnam(group).gr_gid
    os.chown(path, uid, gid)


def default_transfer(spec: dict[str, Any], item: Path, progress: ProgressCb) -> None:  # pragma: no cover - network
    src = spec["source"]
    argv = lftp.build_command(
        src["host"],
        src["base_rel"],
        src["is_multi"],
        str(item),
        spec["lftp"].get("limit_rate", ""),
        int(spec["lftp"].get("parallel", 1)),
    )
    subprocess.check_call(argv)
    progress(100, "", "")


def _apply_perms(root: Path, perms: dict[str, Any], chowner: Chowner) -> None:
    owner, group = perms.get("owner", ""), perms.get("group", "")
    dir_mode = int(str(perms["dir_mode"]), 8)
    file_mode = int(str(perms["file_mode"]), 8)
    paths = [root, *root.rglob("*")] if root.is_dir() else [root]
    for path in paths:
        path.chmod(dir_mode if path.is_dir() else file_mode)
        if owner:
            chowner(path, owner, group)


def _finalize_episodes(spec: dict[str, Any], item: Path, chowner: Chowner) -> None:
    show_dir = spec["dest_path"]
    targets = episodes.episode_targets(item, show_dir)
    if not targets:
        raise ValueError("no episodes recognized in the pack")
    for src, target in targets:
        dest = Path(target)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            dest.unlink()
        os.replace(src, dest)
    _apply_perms(Path(show_dir), spec["perms"], chowner)


def _finalize(spec: dict[str, Any], item: Path, chowner: Chowner) -> None:
    if spec.get("mode") == "episodes":
        _finalize_episodes(spec, item, chowner)
        return
    _apply_perms(item, spec["perms"], chowner)
    dest = Path(spec["dest_path"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        if dest.is_dir():
            shutil.rmtree(dest)
        else:
            dest.unlink()
    os.replace(item, dest)


def run_job(job_dir: Path, *, transfer: Transfer = default_transfer, chowner: Chowner = default_chowner) -> None:
    """Execute a job: transfer, permission, move, and record state throughout."""
    spec = read_spec(job_dir)
    staging = Path(spec["staging_root"]) / ".staging" / spec["id"]
    write_state(job_dir, state="active", pct=0)
    try:
        staging.mkdir(parents=True, exist_ok=True)
        item = staging / spec["staging_item"]

        def progress(pct: int, rate: str, eta: str) -> None:
            write_state(job_dir, state="active", pct=pct, rate=rate, eta=eta)

        transfer(spec, item, progress)
        _finalize(spec, item, chowner)
        write_state(job_dir, state="done", pct=100)
    except Exception as exc:  # noqa: BLE001 - any failure becomes a failed job
        write_state(job_dir, state="failed", error=str(exc))


def run_job_by_id(staging_root: str, job_id: str) -> None:  # pragma: no cover - thin wrapper over run_job
    run_job(jobs_dir(staging_root) / job_id)
