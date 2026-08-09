from __future__ import annotations

import json
from pathlib import Path

from sb_ctrl.jobs import create_job, list_jobs, read_spec, read_state, write_state


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
    assert state == {"id": "J1", "name": "X", "state": "queued", "pct": 0}


def test_write_state_merges_and_keeps_identity(tmp_path: Path) -> None:
    job = create_job(str(tmp_path), {"name": "X"}, job_id="J2")
    write_state(job, state="active", pct=42, rate="1M/s")
    state = read_state(job)
    assert state["state"] == "active"
    assert state["pct"] == 42
    assert state["rate"] == "1M/s"
    assert state["name"] == "X"
