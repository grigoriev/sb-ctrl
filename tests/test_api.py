from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sb_ctrl import api, launcher, tmdb
from sb_ctrl.config import Config
from sb_ctrl.jobs import create_job
from sb_ctrl.rtorrent import Torrent
from sb_ctrl.tmdb import Candidate


class _FakeTMDb:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def search(self, query: str, media: str = "multi") -> list[Candidate]:
        return [Candidate(7, "movie", "T", "Orig", "2020", "o", False)]


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


def _client(cfg: Config) -> TestClient:
    app = api.create_app()
    app.dependency_overrides[api.get_config] = lambda: cfg
    return TestClient(app)


def test_health_needs_no_auth() -> None:
    resp = _client(Config(api_token="secret")).get("/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_token_is_required_when_configured() -> None:
    client = _client(Config(api_token="secret"))
    assert client.get("/config").status_code == 401
    assert client.get("/config", headers={"Authorization": "Bearer secret"}).status_code == 200


def test_open_when_no_token() -> None:
    assert _client(Config()).get("/config").status_code == 200


def test_torrents(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "RTorrent", _FakeRT)
    resp = _client(Config()).get("/torrents")
    assert resp.json()["items"][0]["name"] == "Movie"


def test_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tmdb, "TMDb", _FakeTMDb)
    resp = _client(Config()).get("/search", params={"name": "Some.Movie.2020.1080p"})
    body = resp.json()
    assert body["guess"]["media"] == "movie"
    assert body["candidates"][0]["kind"] == "movie"
    assert body["candidates"][0]["original_title"] == "Orig"


def test_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "RTorrent", _FakeRT)
    cfg = Config(root_movies=str(tmp_path / "movies"), staging_root=str(tmp_path / "staging"))
    resp = _client(cfg).post("/plan", json={"hash": "H1", "kind": "movie"})
    assert resp.status_code == 200
    assert resp.json()["job_spec"]["dest_path"].endswith("/movies/Movie/Movie.mkv")


def test_plan_unknown_hash_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "RTorrent", _FakeRT)
    resp = _client(Config()).post("/plan", json={"hash": "NOPE", "kind": "movie"})
    assert resp.status_code == 404


def test_create_job_and_launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "RTorrent", _FakeRT)
    launched: list[str] = []

    def fake_launch(job_id: str) -> str:
        launched.append(job_id)
        return "systemd"

    monkeypatch.setattr(launcher, "launch", fake_launch)
    cfg = Config(root_movies=str(tmp_path / "movies"), staging_root=str(tmp_path / "staging"))
    resp = _client(cfg).post("/jobs", json={"hash": "H1", "kind": "movie", "collision": "overwrite"})
    assert resp.status_code == 200
    assert launched == [resp.json()["job_id"]]


def test_create_job_skips_on_collision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "RTorrent", _FakeRT)
    dest = tmp_path / "movies" / "Movie" / "Movie.mkv"
    dest.parent.mkdir(parents=True)
    dest.write_text("x")
    cfg = Config(root_movies=str(tmp_path / "movies"), staging_root=str(tmp_path / "staging"))
    resp = _client(cfg).post("/jobs", json={"hash": "H1", "kind": "movie", "collision": "skip"})
    assert resp.json()["skipped"] is True


def test_jobs_list_and_get(tmp_path: Path) -> None:
    cfg = Config(staging_root=str(tmp_path / "staging"))
    create_job(cfg.staging_root, {"name": "X"}, job_id="J1")
    client = _client(cfg)
    assert client.get("/jobs").json()["jobs"][0]["id"] == "J1"
    assert client.get("/jobs/J1").json()["state"] == "queued"
    assert client.get("/jobs/NOPE").status_code == 404


def test_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher, "launch", lambda job_id: "systemd")
    cfg = Config(staging_root=str(tmp_path / "staging"))
    create_job(cfg.staging_root, {"name": "X"}, job_id="J2")
    client = _client(cfg)
    assert client.post("/jobs/J2/retry").json()["job_id"] == "J2"
    assert client.post("/jobs/NOPE/retry").status_code == 404


def test_config_redacts(tmp_path: Path) -> None:
    cfg = Config(api_token="secret", tmdb_key="k")
    resp = _client(cfg).get("/config", headers={"Authorization": "Bearer secret"})
    body = resp.json()
    assert body["api_token"] == "***"
    assert body["tmdb_key"] == "***"
