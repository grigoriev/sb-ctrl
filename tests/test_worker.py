from __future__ import annotations

from pathlib import Path
from typing import Any

from sb_ctrl import worker
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
    spec = plan(cfg, {"name": "The Show S01", "size": 4, "is_multi": True, "base_rel": "files/The Show S01"}, "movie")[
        "job_spec"
    ]
    job = create_job(cfg.staging_root, spec, job_id="J1")

    def transfer(spec: dict[str, Any], item: Path, progress: Any) -> None:
        item.mkdir(parents=True, exist_ok=True)
        (item / "ep.mkv").write_text("x")
        progress(50, "1M/s", "1m")

    calls, chowner = _chowner_recorder()
    run_job(job, transfer=transfer, chowner=chowner)

    dest = tmp_path / "movies" / "The Show S01"
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


def test_series_pack_lays_out_episodes(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    spec = plan(cfg, {"name": "The Show", "size": 4, "is_multi": True, "base_rel": "files/The Show S01"}, "series")[
        "job_spec"
    ]
    job = create_job(cfg.staging_root, spec, job_id="J5")

    def transfer(spec: dict[str, Any], item: Path, progress: Any) -> None:
        item.mkdir(parents=True, exist_ok=True)
        (item / "The.Show.S01E01.mkv").write_text("v")
        (item / "The.Show.S01E02.mkv").write_text("v")
        (item / "The.Show.S01E01.en.srt").write_text("s")

    _, chowner = _chowner_recorder()
    run_job(job, transfer=transfer, chowner=chowner)
    season = tmp_path / "series" / "The Show" / "Season 01"
    assert (season / "S01E01.mkv").is_file()
    assert (season / "S01E02.mkv").is_file()
    assert (season / "S01E01.en.srt").is_file()
    state = read_state(job)
    assert state["state"] == "done"
    assert state["seasons"] == [{"season": 1, "episodes": 2}]
    assert state["finished"] > 0


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


# --- progress ------------------------------------------------------------


def test_path_size_counts_a_file_a_tree_and_nothing(tmp_path: Path) -> None:
    assert worker.path_size(tmp_path / "gone") == 0

    single = tmp_path / "one.mkv"
    single.write_bytes(b"x" * 10)
    assert worker.path_size(single) == 10

    tree = tmp_path / "show"
    (tree / "s01").mkdir(parents=True)
    (tree / "s01" / "e01.mkv").write_bytes(b"y" * 7)
    (tree / "s01" / "e02.mkv").write_bytes(b"z" * 3)
    assert worker.path_size(tree) == 10


def test_human_eta_scales() -> None:
    assert worker.human_eta(45) == "45s"
    assert worker.human_eta(200) == "3m"
    assert worker.human_eta(3900) == "1h 5m"


def test_transfer_progress_reports_percent_rate_and_eta() -> None:
    # A quarter of 4 MiB in one second: 1 MiB/s, three seconds left.
    pct, rate, eta = worker.transfer_progress(1048576, 4194304, 1.0)
    assert pct == 25
    assert rate == "1.0 MB/s"
    assert eta == "3s"


def test_transfer_progress_never_reports_a_hundred() -> None:
    pct, _, eta = worker.transfer_progress(1000, 1000, 1.0)
    assert pct == 99
    assert eta == "0s"


def test_transfer_progress_says_nothing_before_the_first_bytes() -> None:
    assert worker.transfer_progress(0, 1000, 1.0) == (0, "", "")
    assert worker.transfer_progress(500, 0, 1.0) == (0, "", "")
    assert worker.transfer_progress(500, 1000, 0.0) == (0, "", "")


def test_season_summary_counts_episodes_not_files() -> None:
    targets = [
        (Path("a"), "/lib/Show/Season 01/S01E01.mkv"),
        (Path("b"), "/lib/Show/Season 01/S01E01.en.srt"),
        (Path("c"), "/lib/Show/Season 01/S01E02.mkv"),
        (Path("d"), "/lib/Show/Season 02/S02E01.mkv"),
        (Path("e"), "/lib/Show/extras/readme.txt"),
    ]
    assert worker.season_summary(targets) == [{"season": 1, "episodes": 2}, {"season": 2, "episodes": 1}]


def test_season_summary_of_nothing_is_empty() -> None:
    assert worker.season_summary([]) == []
