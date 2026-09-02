"""The transfer worker: pull into staging, set permissions, atomically move into
the library, and record job state (SPEC.md section 8).

The lftp transfer and the ownership change are injected so the orchestration is
tested against a real temp filesystem without a seedbox or root privileges.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from sb_ctrl import episodes, lftp
from sb_ctrl.config import DEFAULT_SKIP_PATTERNS, DEFAULT_SUB_EXT, DEFAULT_VIDEO_EXT
from sb_ctrl.jobs import jobs_dir, log_path, read_spec, write_state

# progress(pct, rate, eta)
ProgressCb = Callable[[int, str, str], None]
# transfer(spec, staging_item_path, progress)
Transfer = Callable[[dict[str, Any], Path, ProgressCb], None]
# chowner(path, owner, group)
Chowner = Callable[[Path, str, str], None]

# How often a running transfer reports how far it has got.
PROGRESS_INTERVAL = 2.0
# Headroom demanded on top of the transfer size, so the disk never fills up.
SPACE_MARGIN = 1 << 30


def default_chowner(path: Path, owner: str, group: str) -> None:  # pragma: no cover - needs privileges
    import grp
    import pwd

    uid = pwd.getpwnam(owner).pw_uid
    gid = grp.getgrnam(group).gr_gid
    os.chown(path, uid, gid)


def path_size(path: Path) -> int:
    """Bytes on disk under ``path``. A missing path counts as nothing yet."""
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def human_eta(seconds: float) -> str:
    """A short, readable time left: 45s, 3m, 1h 5m."""
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    if total < 3600:
        return f"{total // 60}m"
    return f"{total // 3600}h {(total % 3600) // 60}m"


def transfer_progress(done: int, total: int, elapsed: float) -> tuple[int, str, str]:
    """Percent, rate and ETA from what has landed so far.

    Reports at most 99: the hundred belongs to a transfer that actually ended.
    Before the first bytes there is nothing to extrapolate from.
    """
    if total <= 0 or done <= 0 or elapsed <= 0:
        return 0, "", ""
    speed = done / elapsed
    pct = min(99, int(done * 100 / total))
    remaining = max(0.0, (total - done) / speed)
    return pct, f"{speed / 1048576:.1f} MB/s", human_eta(remaining)


def default_transfer(spec: dict[str, Any], item: Path, progress: ProgressCb) -> None:  # pragma: no cover - network
    src = spec["source"]
    argv = lftp.build_command(
        src["host"],
        src["base_rel"],
        src["is_multi"],
        str(item),
        spec["lftp"].get("limit_rate", ""),
        int(spec["lftp"].get("parallel", 1)),
        src.get("user", ""),
    )
    # Sample the staging dir while lftp runs; it reports nothing itself.
    total = int(src.get("size", 0))
    started = time.monotonic()
    # Keep what lftp says. Without it a failure is a bare exit status.
    log = log_path(spec["staging_root"], str(spec["id"]))
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8", errors="replace") as sink:
        sink.write(f"$ {' '.join(argv)}\n")
        sink.flush()
        proc = subprocess.Popen(argv, stdout=sink, stderr=subprocess.STDOUT)
        while proc.poll() is None:
            time.sleep(PROGRESS_INTERVAL)
            progress(*transfer_progress(path_size(item), total, time.monotonic() - started))
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, argv)
    progress(100, "", "")


def enough_space(path: Path, needed: int, usage: Callable[[Path], Any] | None = None) -> bool:
    """Whether ``path`` holds ``needed`` bytes plus a small margin.

    A transfer that fills the disk fails halfway and leaves the leftovers
    behind, which is a worse way to learn the same fact.
    """
    if needed <= 0:
        return True
    # resolved here, not in the signature, so a caller can substitute it
    measure = usage or shutil.disk_usage
    try:
        free = int(measure(path).free)
    except OSError:
        return True
    return free >= needed + SPACE_MARGIN


def _apply_perms(root: Path, perms: dict[str, Any], chowner: Chowner) -> None:
    owner, group = perms.get("owner", ""), perms.get("group", "")
    dir_mode = int(str(perms["dir_mode"]), 8)
    file_mode = int(str(perms["file_mode"]), 8)
    paths = [root, *root.rglob("*")] if root.is_dir() else [root]
    for path in paths:
        path.chmod(dir_mode if path.is_dir() else file_mode)
        if owner:
            chowner(path, owner, group)


def _new_parents(path: Path) -> list[Path]:
    """The directories above ``path`` that do not exist yet, outermost first.

    A directory the delivery creates gets the configured mode and owner like
    everything else. Without that it keeps root's umask, and Plex cannot
    delete what sits inside it.
    """
    return [parent for parent in reversed(path.parents) if not parent.exists()]


def season_summary(targets: Iterable[tuple[Path, str]]) -> list[dict[str, int]]:
    """How many distinct episodes landed in each season.

    Counts pairs, not files, so a subtitle beside its video is not a second
    episode. The client reports which seasons a pack delivered.
    """
    seen: dict[int, set[int]] = {}
    for _, target in targets:
        parsed = episodes.parse_episode(Path(target).name)
        if parsed is not None:
            season, number = parsed
            seen.setdefault(season, set()).add(number)
    return [{"season": season, "episodes": len(seen[season])} for season in sorted(seen)]


def _finalize_episodes(spec: dict[str, Any], item: Path, chowner: Chowner) -> list[dict[str, int]]:
    show_dir = spec["dest_path"]
    created = _new_parents(Path(show_dir))
    files = spec.get("files") or {}
    targets = episodes.episode_targets(
        item,
        show_dir,
        video_ext=files.get("video_ext", DEFAULT_VIDEO_EXT),
        sub_ext=files.get("sub_ext", DEFAULT_SUB_EXT),
        skip_patterns=files.get("skip_patterns", DEFAULT_SKIP_PATTERNS),
    )
    if not targets:
        raise ValueError("no episodes recognized in the pack")
    for src, target in targets:
        dest = Path(target)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            dest.unlink()
        os.replace(src, dest)
    for directory in created:
        _apply_perms(directory, spec["perms"], chowner)
    _apply_perms(Path(show_dir), spec["perms"], chowner)
    return season_summary(targets)


def _finalize(spec: dict[str, Any], item: Path, chowner: Chowner) -> list[dict[str, int]]:
    """Deliver the staged item and report the seasons it held, if any."""
    if spec.get("mode") == "episodes":
        return _finalize_episodes(spec, item, chowner)
    _apply_perms(item, spec["perms"], chowner)
    dest = Path(spec["dest_path"])
    created = _new_parents(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        if dest.is_dir():
            shutil.rmtree(dest)
        else:
            dest.unlink()
    os.replace(item, dest)
    for directory in created:
        _apply_perms(directory, spec["perms"], chowner)
    return []


def run_job(job_dir: Path, *, transfer: Transfer = default_transfer, chowner: Chowner = default_chowner) -> None:
    """Execute a job: transfer, permission, move, and record state throughout."""
    spec = read_spec(job_dir)
    staging = Path(spec["staging_root"]) / ".staging" / spec["id"]
    # the pid lets the API tell a running transfer from one whose worker died
    write_state(job_dir, state="active", pct=0, pid=os.getpid(), error="")
    try:
        staging.mkdir(parents=True, exist_ok=True)
        needed = int((spec.get("source") or {}).get("size", 0))
        if not enough_space(staging, needed):
            raise OSError(f"not enough free space for {needed} bytes")
        item = staging / spec["staging_item"]

        def progress(pct: int, rate: str, eta: str) -> None:
            write_state(job_dir, state="active", pct=pct, rate=rate, eta=eta)

        transfer(spec, item, progress)
        seasons = _finalize(spec, item, chowner)
        # The delivery emptied staging of everything worth keeping. What is left
        # is the pack directory and its junk, so it goes with the job.
        shutil.rmtree(staging, ignore_errors=True)
        write_state(job_dir, state="done", pct=100, seasons=seasons, finished=int(time.time()))
    except Exception as exc:  # noqa: BLE001 - any failure becomes a failed job
        write_state(job_dir, state="failed", error=str(exc), finished=int(time.time()))


def run_job_by_id(staging_root: str, job_id: str) -> None:  # pragma: no cover - thin wrapper over run_job
    run_job(jobs_dir(staging_root) / job_id)
