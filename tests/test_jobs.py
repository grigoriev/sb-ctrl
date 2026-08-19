from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from sb_ctrl.jobs import (
    by_source,
    create_job,
    list_jobs,
    log_path,
    pid_alive,
    read_spec,
    read_state,
    reconcile,
    release_name,
    summary,
    tail_log,
    write_state,
)


def test_empty_staging_root_returns_nothing() -> None:
    assert list_jobs("") == []


def test_missing_jobs_dir_returns_nothing(tmp_path: Path) -> None:
    assert list_jobs(str(tmp_path)) == []


def test_reads_job_states_and_skips_bad_json(tmp_path: Path) -> None:
    jobs = tmp_path / ".jobs"
    (jobs / "001").mkdir(parents=True)
    (jobs / "001" / "state.json").write_text(json.dumps({"id": "001", "state": "done"}))
    (jobs / "002").mkdir(parents=True)
    (jobs / "002" / "state.json").write_text("{not json")
    (jobs / "003").mkdir(parents=True)  # no state.json

    result = list_jobs(str(tmp_path))
    assert result == [{"id": "001", "state": "done"}]


def test_create_job_writes_spec_and_state(tmp_path: Path) -> None:
    job = create_job(str(tmp_path), {"name": "X", "kind": "movie"}, job_id="J1")
    assert job.name == "J1"
    spec = read_spec(job)
    assert spec["name"] == "X"
    assert spec["id"] == "J1"
    state = read_state(job)
    assert state["id"] == "J1"
    assert state["name"] == "X"
    assert state["state"] == "queued"
    assert state["pct"] == 0
    assert state["created"] > 0


def test_create_job_records_what_the_list_shows(tmp_path: Path) -> None:
    spec = {
        "name": "1670 (2023)",
        "kind": "series",
        "dest_path": "/media/series/1670 (2023)",
        "source": {"base_rel": "files/1670.S03.WEB-DL.1080p", "size": 17_000_000_000},
    }
    state = read_state(create_job(str(tmp_path), spec, job_id="J3"))
    assert state["release"] == "1670.S03.WEB-DL.1080p"
    assert state["kind"] == "series"
    assert state["size"] == 17_000_000_000
    assert state["dest"] == "/media/series/1670 (2023)"


def test_summary_of_a_bare_spec_is_empty() -> None:
    assert summary({}) == {"kind": "", "hash": "", "release": "", "size": 0, "dest": ""}


def test_write_state_merges_and_keeps_identity(tmp_path: Path) -> None:
    job = create_job(str(tmp_path), {"name": "X"}, job_id="J2")
    write_state(job, state="active", pct=42, rate="1M/s")
    state = read_state(job)
    assert state["state"] == "active"
    assert state["pct"] == 42
    assert state["rate"] == "1M/s"
    assert state["name"] == "X"


def test_pid_alive_knows_this_process_and_rejects_nonsense() -> None:
    assert pid_alive(os.getpid()) is True
    assert pid_alive(0) is False
    assert pid_alive(-1) is False


def test_reconcile_marks_a_job_whose_worker_is_gone(tmp_path: Path) -> None:
    job = create_job(str(tmp_path), {"name": "X"}, job_id="J10")
    write_state(job, state="active", pct=40, rate="9 MB/s", eta="2m", pid=_dead_pid())
    reconcile(str(tmp_path))
    state = read_state(job)
    assert state["state"] == "stalled"
    assert state["error"]
    assert state["rate"] == ""


def test_reconcile_leaves_a_live_job_alone(tmp_path: Path) -> None:
    job = create_job(str(tmp_path), {"name": "X"}, job_id="J11")
    write_state(job, state="active", pct=40, pid=os.getpid())
    reconcile(str(tmp_path))
    assert read_state(job)["state"] == "active"


def test_reconcile_ignores_a_finished_job(tmp_path: Path) -> None:
    job = create_job(str(tmp_path), {"name": "X"}, job_id="J12")
    write_state(job, state="done", pct=100, pid=_dead_pid())
    reconcile(str(tmp_path))
    assert read_state(job)["state"] == "done"


def test_tail_log_returns_the_last_lines(tmp_path: Path) -> None:
    job = create_job(str(tmp_path), {"name": "X"}, job_id="J13")
    assert tail_log(job) == ""
    (job / "job.log").write_text("one\ntwo\nthree\n")
    assert tail_log(job, lines=2) == "two\nthree"


def _dead_pid() -> int:
    """A pid that has surely gone: a child that already exited."""
    proc = subprocess.Popen([sys.executable, "-c", ""])
    proc.wait()
    return proc.pid


def test_pid_alive_treats_a_forbidden_process_as_running(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(_pid: int, _sig: int) -> None:
        raise PermissionError

    monkeypatch.setattr(os, "kill", forbidden)
    assert pid_alive(1) is True


def test_log_path_sits_next_to_the_spec(tmp_path: Path) -> None:
    assert log_path(str(tmp_path), "J14") == tmp_path / ".jobs" / "J14" / "job.log"


def test_tail_log_survives_an_unreadable_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    job = create_job(str(tmp_path), {"name": "X"}, job_id="J15")
    (job / "job.log").write_text("something")

    def unreadable(*_args: object, **_kwargs: object) -> str:
        raise OSError("gone")

    monkeypatch.setattr(Path, "read_text", unreadable)
    assert tail_log(job) == ""


def test_release_name_takes_the_last_component() -> None:
    assert release_name("files/1670.S03.WEB-DL.1080p") == "1670.S03.WEB-DL.1080p"
    assert release_name("files/Show/") == "Show"
    assert release_name("") == ""


def test_by_source_indexes_a_job_under_both_keys() -> None:
    index = by_source([{"id": "J1", "hash": "H1", "release": "R1"}])
    assert index["H1"]["id"] == "J1"
    assert index["R1"]["id"] == "J1"


def test_by_source_keeps_the_newest_job_for_a_source() -> None:
    index = by_source([{"id": "J1", "hash": "H1"}, {"id": "J2", "hash": "H1"}])
    assert index["H1"]["id"] == "J2"


def test_by_source_skips_a_job_with_neither_key() -> None:
    assert by_source([{"id": "J1"}]) == {}
