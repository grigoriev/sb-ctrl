from __future__ import annotations

from pathlib import Path
from typing import Any

from sb_ctrl.config import Config
from sb_ctrl.jobs import create_job, read_state
from sb_ctrl.planner import plan
from sb_ctrl.worker import run_job


def _cfg(tmp_path: Path, movie_layout: str = "folder") -> Config:
    return Config(
        root_movies=str(tmp_path / "movies"),
        root_series=str(tmp_path / "series"),
        owner="plex",
        group="media",
        dir_mode="775",
        file_mode="664",
        movie_layout=movie_layout,
        staging_root=str(tmp_path / "staging"),
    )


def _chowner_recorder() -> tuple[list[tuple[str, str, str]], Any]:
    calls: list[tuple[str, str, str]] = []

    def chowner(path: Path, owner: str, group: str) -> None:
        calls.append((path.name, owner, group))

    return calls, chowner


def test_folder_job_moves_into_library_and_sets_state(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    spec = plan(cfg, {"name": "The Show S01", "size": 4, "is_multi": True, "base_rel": "files/The Show S01"}, "series")[
        "job_spec"
    ]
    job = create_job(cfg.staging_root, spec, job_id="J1")

    def transfer(spec: dict[str, Any], item: Path, progress: Any) -> None:
        item.mkdir(parents=True, exist_ok=True)
        (item / "ep.mkv").write_text("x")
        progress(50, "1M/s", "1m")

    calls, chowner = _chowner_recorder()
    run_job(job, transfer=transfer, chowner=chowner)

    dest = tmp_path / "series" / "The Show S01"
    assert (dest / "ep.mkv").is_file()
    state = read_state(job)
    assert state["state"] == "done"
    assert state["pct"] == 100
    assert ("ep.mkv", "plex", "media") in calls
    assert (dest / "ep.mkv").stat().st_mode & 0o777 == 0o664


def test_single_file_job(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, "flat")
    spec = plan(cfg, {"name": "Film 2024", "size": 1, "is_multi": False, "base_rel": "files/Film.2024.mkv"}, "movie")[
        "job_spec"
    ]
    job = create_job(cfg.staging_root, spec, job_id="J2")

    def transfer(spec: dict[str, Any], item: Path, progress: Any) -> None:
        item.parent.mkdir(parents=True, exist_ok=True)
        item.write_text("x")

    calls, chowner = _chowner_recorder()
    run_job(job, transfer=transfer, chowner=chowner)
    assert (tmp_path / "movies" / "Film 2024.mkv").is_file()
    assert read_state(job)["state"] == "done"


def test_overwrite_replaces_existing(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, "flat")
    dest = tmp_path / "movies" / "Film 2024.mkv"
    dest.parent.mkdir(parents=True)
    dest.write_text("old")
    spec = plan(cfg, {"name": "Film 2024", "size": 1, "is_multi": False, "base_rel": "files/Film.2024.mkv"}, "movie")[
        "job_spec"
    ]
    job = create_job(cfg.staging_root, spec, job_id="J3")

    def transfer(spec: dict[str, Any], item: Path, progress: Any) -> None:
        item.parent.mkdir(parents=True, exist_ok=True)
        item.write_text("new")

    _, chowner = _chowner_recorder()
    run_job(job, transfer=transfer, chowner=chowner)
    assert dest.read_text() == "new"


def test_failure_records_error(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    spec = plan(cfg, {"name": "X", "size": 1, "is_multi": True, "base_rel": "files/X"}, "series")["job_spec"]
    job = create_job(cfg.staging_root, spec, job_id="J4")

    def transfer(spec: dict[str, Any], item: Path, progress: Any) -> None:
        raise RuntimeError("lftp died")

    _, chowner = _chowner_recorder()
    run_job(job, transfer=transfer, chowner=chowner)
    state = read_state(job)
    assert state["state"] == "failed"
    assert state["error"] == "lftp died"
