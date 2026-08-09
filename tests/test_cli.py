from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from sb_ctrl import cli, launcher, tmdb, worker
from sb_ctrl.jobs import create_job, read_state
from sb_ctrl.rtorrent import Torrent
from sb_ctrl.tmdb import Candidate


class _FakeTMDb:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def search(self, query: str, media: str = "multi") -> list[Candidate]:
        return [Candidate(7, "movie", "T", "Orig", "2020", "o", False)]


def _write_cfg(tmp_path: Path) -> Path:
    path = tmp_path / "c.toml"
    path.write_text(
        f'staging_root = "{tmp_path}/staging"\n'
        f'[roots]\nmovies = "{tmp_path}/movies"\nseries = "{tmp_path}/series"\n'
        f'[perms]\nowner = "plex"\ngroup = "plex"\n'
    )
    return path


ONE = Torrent(
    hash="H1",
    name="Movie",
    size=1,
    is_multi=False,
    base_path="/home/u/files/Movie.mkv",
    base_rel="files/Movie.mkv",
    finished=10,
)


class _FakeRT:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def list_completed(self) -> list[Torrent]:
        return [ONE]


def test_list_prints_items(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(cli, "RTorrent", _FakeRT)
    assert cli.main(["list"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["items"][0]["name"] == "Movie"
    assert out["items"][0]["base_rel"] == "files/Movie.mkv"


def test_status_reads_jobs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    cfg = tmp_path / "c.toml"
    cfg.write_text(f'staging_root = "{tmp_path}"\n')
    jobs = tmp_path / ".jobs" / "001"
    jobs.mkdir(parents=True)
    (jobs / "state.json").write_text(json.dumps({"id": "001", "state": "active"}))
    monkeypatch.setenv("SB_CTRL_CONFIG", str(cfg))
    assert cli.main(["status"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["jobs"] == [{"id": "001", "state": "active"}]


def test_config_get_redacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = tmp_path / "c.toml"
    cfg.write_text('[tmdb]\nkey = "k"\n')
    monkeypatch.setenv("SB_CTRL_CONFIG", str(cfg))
    assert cli.main(["config", "get"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["tmdb_key"] == "***"


def test_error_is_reported_as_json(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def boom() -> dict[str, object]:
        raise RuntimeError("nope")

    monkeypatch.setattr(cli, "_cmd_list", boom)
    assert cli.main(["list"]) == 1
    err = json.loads(capsys.readouterr().err)
    assert err["error"] == "nope"


def test_search_cmd(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(tmdb, "TMDb", _FakeTMDb)
    assert cli.main(["search", "Some.Movie.2020"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["candidates"][0]["kind"] == "movie"


def test_plan_via_stdin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("SB_CTRL_CONFIG", str(_write_cfg(tmp_path)))
    monkeypatch.setattr(cli, "RTorrent", _FakeRT)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"hash": "H1", "kind": "movie"})))
    assert cli.main(["plan"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["job_spec"]["kind"] == "movie"
    assert out["job_spec"]["dest_path"].endswith("/movies/Movie/Movie.mkv")


def test_plan_unknown_hash_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SB_CTRL_CONFIG", str(_write_cfg(tmp_path)))
    monkeypatch.setattr(cli, "RTorrent", _FakeRT)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"hash": "NOPE", "kind": "movie"})))
    assert cli.main(["plan"]) == 1
    assert json.loads(capsys.readouterr().err)["error"] == "torrent not found"


def test_run_creates_job_and_launches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SB_CTRL_CONFIG", str(_write_cfg(tmp_path)))
    launched: list[str] = []

    def fake_launch(job_id: str) -> str:
        launched.append(job_id)
        return "systemd"

    monkeypatch.setattr(launcher, "launch", fake_launch)
    spec = {"name": "New", "kind": "movie", "dest_path": str(tmp_path / "movies" / "New")}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"job_spec": spec, "collision": "overwrite"})))
    assert cli.main(["run"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["launcher"] == "systemd"
    assert launched == [out["job_id"]]


def test_run_skips_on_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SB_CTRL_CONFIG", str(_write_cfg(tmp_path)))
    dest = tmp_path / "movies" / "Old"
    dest.mkdir(parents=True)
    spec = {"name": "Old", "dest_path": str(dest)}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"job_spec": spec, "collision": "skip"})))
    assert cli.main(["run"]) == 0
    assert json.loads(capsys.readouterr().out)["skipped"] is True


def test_run_job_dispatches_to_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SB_CTRL_CONFIG", str(_write_cfg(tmp_path)))
    called: list[Path] = []
    monkeypatch.setattr(worker, "run_job", lambda job_dir: called.append(job_dir))
    assert cli.main(["run-job", "J1"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert called[0].name == "J1"


def test_retry_resets_state_and_launches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SB_CTRL_CONFIG", str(_write_cfg(tmp_path)))
    job = create_job(f"{tmp_path}/staging", {"name": "X"}, job_id="J9")
    monkeypatch.setattr(launcher, "launch", lambda jid: "systemd")
    assert cli.main(["retry", "J9"]) == 0
    assert json.loads(capsys.readouterr().out)["job_id"] == "J9"
    assert read_state(job)["state"] == "queued"
