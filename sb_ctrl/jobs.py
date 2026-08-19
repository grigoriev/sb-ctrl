"""Transfer job state under ``<staging_root>/.jobs/<id>/``.

Each job holds ``spec.json`` (the immutable transfer plan) and ``state.json``
(the live state read by ``sb-ctrl status``). See SPEC.md section 8.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def jobs_dir(staging_root: str) -> Path:
    return Path(staging_root) / ".jobs"


def new_job_id() -> str:
    """A sortable, unique job id: timestamp plus a short random suffix."""
    return time.strftime("%Y%m%d-%H%M%S") + "-" + os.urandom(2).hex()


def release_name(base_rel: str) -> str:
    """The last path component of a remote path, which names the release."""
    return str(base_rel).rstrip("/").rsplit("/", 1)[-1]


def by_source(states: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index job states by what each one pulled.

    Both the torrent hash and the release name are keys, because a job made
    before the hash was recorded can still be found by its release.
    """
    index: dict[str, dict[str, Any]] = {}
    for state in states:
        for key in (str(state.get("hash", "")), str(state.get("release", ""))):
            if key:
                index[key] = state
    return index


def summary(spec: dict[str, Any]) -> dict[str, Any]:
    """The parts of the plan a client shows beside the progress bar.

    The release name is what tells two transfers of the same show apart, and
    it carries the season the pack came from.
    """
    source = spec.get("source") or {}
    return {
        "kind": str(spec.get("kind", "")),
        "hash": str(source.get("hash", "")),
        "release": release_name(str(source.get("base_rel", ""))),
        "size": int(source.get("size", 0)),
        "dest": str(spec.get("dest_path", "")),
    }


def create_job(staging_root: str, spec: dict[str, Any], job_id: str | None = None) -> Path:
    """Create the job directory, write its spec, and mark it queued."""
    job_id = job_id or new_job_id()
    job = jobs_dir(staging_root) / job_id
    job.mkdir(parents=True, exist_ok=True)
    spec = {**spec, "id": job_id}
    (job / "spec.json").write_text(json.dumps(spec, indent=2))
    write_state(job, state="queued", pct=0, created=int(time.time()), **summary(spec))
    return job


def read_spec(job_dir: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((job_dir / "spec.json").read_text())
    return data


def write_state(job_dir: Path, **fields: Any) -> None:
    """Merge ``fields`` into the job's state file, keeping id and name."""
    state: dict[str, Any] = {}
    path = job_dir / "state.json"
    if path.is_file():
        try:
            state = json.loads(path.read_text())
        except OSError, json.JSONDecodeError:
            state = {}
    state.setdefault("id", job_dir.name)
    with contextlib.suppress(OSError, json.JSONDecodeError):
        state.setdefault("name", read_spec(job_dir).get("name", job_dir.name))
    state.update(fields)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(path)


def pid_alive(pid: int) -> bool:
    """Whether a process with ``pid`` still exists.

    The worker runs beside the API, in the same process namespace, so its pid
    is one this process can ask about.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _mark_if_stalled(job_dir: Path, state: dict[str, Any]) -> None:
    """Move an active job with no live worker to stalled.

    A worker dies with its container, and nothing else would ever move the
    job off ``active``: the list would show a frozen bar, and the job could
    be neither deleted nor understood.
    """
    if state.get("state") != "active" or pid_alive(int(state.get("pid", 0))):
        return
    write_state(
        job_dir,
        state="stalled",
        error="the worker stopped before the transfer finished",
        rate="",
        eta="",
    )


def _backfill_summary(job_dir: Path, state: dict[str, Any]) -> None:
    """Give a job written by an older version the fields a client now reads.

    The plan beside it holds them all along, so a job from before this
    release still shows its release name and links to its torrent.
    """
    if "release" in state:
        return
    try:
        spec = read_spec(job_dir)
    except OSError, json.JSONDecodeError:
        return
    write_state(job_dir, **summary(spec))


def reconcile(staging_root: str) -> None:
    """Bring the stored job states up to date before a client reads them."""
    for state in list_jobs(staging_root):
        job_dir = jobs_dir(staging_root) / str(state["id"])
        _backfill_summary(job_dir, state)
        _mark_if_stalled(job_dir, state)


def read_state(job_dir: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((job_dir / "state.json").read_text())
    return data


def log_path(staging_root: str, job_id: str) -> Path:
    """Where a job keeps the output of the transfer tool."""
    return jobs_dir(staging_root) / job_id / "job.log"


def tail_log(job_dir: Path, lines: int = 200) -> str:
    """The last ``lines`` of the job log, or an empty string when there is none."""
    path = job_dir / "job.log"
    if not path.is_file():
        return ""
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-lines:])


def delete_job(staging_root: str, job_dir: Path) -> None:
    """Remove a job and whatever it left in staging.

    Staging is named after the job, so a half-finished pull goes with it and
    does not sit on the disk forever.
    """
    staging = Path(staging_root) / ".staging" / job_dir.name
    shutil.rmtree(staging, ignore_errors=True)
    shutil.rmtree(job_dir, ignore_errors=True)


def list_jobs(staging_root: str) -> list[dict[str, Any]]:
    """Return every job's state, oldest id first. Empty when nothing is staged."""
    if not staging_root:
        return []
    root = jobs_dir(staging_root)
    if not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for entry in sorted(root.iterdir()):
        state = entry / "state.json"
        if not state.is_file():
            continue
        try:
            out.append(json.loads(state.read_text()))
        except OSError, json.JSONDecodeError:
            continue
    return out
