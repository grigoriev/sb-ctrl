from __future__ import annotations

import json
from pathlib import Path

import pytest

from sb_pull import cli
from sb_pull.rtorrent import Torrent

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
    monkeypatch.setenv("SB_PULL_CONFIG", str(cfg))
    assert cli.main(["status"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["jobs"] == [{"id": "001", "state": "active"}]


def test_config_get_redacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = tmp_path / "c.toml"
    cfg.write_text('[tmdb]\nkey = "k"\n')
    monkeypatch.setenv("SB_PULL_CONFIG", str(cfg))
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
