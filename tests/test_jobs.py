from __future__ import annotations

import json
from pathlib import Path

from sb_pull.jobs import list_jobs


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
