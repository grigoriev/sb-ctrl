from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sb_ctrl import api, launcher, tmdb
from sb_ctrl.config import Config
from sb_ctrl.jobs import create_job, jobs_dir, write_state
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


# --- login ---------------------------------------------------------------

PASSWORD = "correct horse"


def _login_cfg(**extra: object) -> Config:
    from sb_ctrl import auth

    return Config(
        auth_user="sergey",
        auth_password_hash=auth.hash_password(PASSWORD),
        auth_secret="signing-key",
        **extra,  # type: ignore[arg-type]
    )


def _tls_client(cfg: Config) -> TestClient:
    """The session cookie is Secure, so a client must speak https to keep it."""
    app = api.create_app()
    app.dependency_overrides[api.get_config] = lambda: cfg
    return TestClient(app, base_url="https://testserver")


def test_login_sets_a_session_and_opens_the_api() -> None:
    client = _tls_client(_login_cfg())
    assert client.get("/config").status_code == 401

    resp = client.post("/login", json={"user": "sergey", "password": PASSWORD})
    assert resp.status_code == 200
    assert resp.json()["user"] == "sergey"

    cookie = client.cookies.get("sb_session")
    assert cookie
    assert client.get("/config").status_code == 200


def test_login_rejects_a_wrong_password() -> None:
    client = _tls_client(_login_cfg())
    resp = client.post("/login", json={"user": "sergey", "password": "nope"})
    assert resp.status_code == 401
    assert client.cookies.get("sb_session") is None


def test_login_rejects_a_wrong_user() -> None:
    client = _tls_client(_login_cfg())
    assert client.post("/login", json={"user": "someone", "password": PASSWORD}).status_code == 401


def test_login_without_configuration_is_refused() -> None:
    client = _client(Config())
    resp = client.post("/login", json={"user": "sergey", "password": PASSWORD})
    assert resp.status_code == 400


def test_logout_clears_the_session() -> None:
    client = _tls_client(_login_cfg())
    client.post("/login", json={"user": "sergey", "password": PASSWORD})
    assert client.get("/config").status_code == 200
    client.post("/logout")
    assert client.get("/config").status_code == 401


def test_a_forged_cookie_is_refused() -> None:
    client = _tls_client(_login_cfg())
    client.cookies.set("sb_session", "c2VyZ2V5.9999999999.deadbeef")
    assert client.get("/config").status_code == 401


def test_the_bearer_token_still_works_beside_a_login() -> None:
    client = _tls_client(_login_cfg(api_token="secret"))
    assert client.get("/config", headers={"Authorization": "Bearer secret"}).status_code == 200


def test_me_reports_whether_a_login_is_needed() -> None:
    client = _tls_client(_login_cfg())
    body = client.get("/me").json()
    assert body == {"login_required": True, "user": None}

    client.post("/login", json={"user": "sergey", "password": PASSWORD})
    assert client.get("/me").json() == {"login_required": False, "user": "sergey"}


def test_me_on_an_open_install() -> None:
    assert _client(Config()).get("/me").json() == {"login_required": False, "user": None}


def test_config_redacts_the_login_secrets() -> None:
    client = _tls_client(_login_cfg())
    client.post("/login", json={"user": "sergey", "password": PASSWORD})
    body = client.get("/config").json()
    assert body["auth_password_hash"] == "***"
    assert body["auth_secret"] == "***"


# --- deleting a job ------------------------------------------------------


def test_delete_removes_the_job_and_its_staging(tmp_path: Path) -> None:
    cfg = Config(staging_root=str(tmp_path))
    job = create_job(str(tmp_path), {"name": "x"})
    write_state(job, state="failed", error="boom")
    staging = tmp_path / ".staging" / job.name
    staging.mkdir(parents=True)
    (staging / "half.mkv").write_bytes(b"x" * 5)

    resp = _client(cfg).delete(f"/jobs/{job.name}")

    assert resp.status_code == 200
    assert resp.json() == {"deleted": job.name}
    assert not job.exists()
    assert not staging.exists()


def test_delete_refuses_a_running_job(tmp_path: Path) -> None:
    cfg = Config(staging_root=str(tmp_path))
    job = create_job(str(tmp_path), {"name": "x"})
    write_state(job, state="active", pct=42)

    resp = _client(cfg).delete(f"/jobs/{job.name}")

    assert resp.status_code == 409
    assert job.exists()


def test_delete_reports_an_unknown_job(tmp_path: Path) -> None:
    cfg = Config(staging_root=str(tmp_path))
    jobs_dir(str(tmp_path)).mkdir(parents=True)
    assert _client(cfg).delete("/jobs/nope").status_code == 404


def test_delete_a_job_that_never_wrote_a_state(tmp_path: Path) -> None:
    cfg = Config(staging_root=str(tmp_path))
    job = create_job(str(tmp_path), {"name": "x"})
    (job / "state.json").unlink(missing_ok=True)
    assert _client(cfg).delete(f"/jobs/{job.name}").status_code == 200


def test_job_log_is_served(tmp_path: Path) -> None:
    cfg = Config(staging_root=str(tmp_path))
    job = create_job(cfg.staging_root, {"name": "X"}, job_id="J30")
    (job / "job.log").write_text("lftp said this\n")
    resp = _client(cfg).get("/jobs/J30/log")
    assert resp.status_code == 200
    assert resp.json()["log"] == "lftp said this"


def test_job_log_of_an_unknown_job_is_404(tmp_path: Path) -> None:
    resp = _client(Config(staging_root=str(tmp_path))).get("/jobs/nope/log")
    assert resp.status_code == 404


def test_a_job_with_no_state_is_404(tmp_path: Path) -> None:
    cfg = Config(staging_root=str(tmp_path))
    job = create_job(cfg.staging_root, {"name": "X"}, job_id="J31")
    (job / "state.json").unlink()
    assert _client(cfg).get("/jobs/J31").status_code == 404


def test_listing_jobs_marks_a_dead_worker(tmp_path: Path) -> None:
    cfg = Config(staging_root=str(tmp_path))
    job = create_job(cfg.staging_root, {"name": "X"}, job_id="J32")
    write_state(job, state="active", pct=10, pid=999_999)
    body = _client(cfg).get("/jobs").json()
    assert body["jobs"][0]["state"] == "stalled"


def test_torrents_report_a_delivered_title(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "RTorrent", _FakeRT)
    cfg = Config(staging_root=str(tmp_path))
    dest = tmp_path / "movies" / "Movie"
    dest.mkdir(parents=True)
    job = create_job(cfg.staging_root, {"name": "Movie", "source": {"hash": "H1"}}, job_id="J40")
    write_state(job, state="done", pct=100, dest=str(dest))
    item = _client(cfg).get("/torrents").json()["items"][0]
    assert item["delivered"] is True
    assert item["job"] == {"id": "J40", "state": "done", "pct": 100}


def test_torrents_report_a_transfer_in_flight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "RTorrent", _FakeRT)
    cfg = Config(staging_root=str(tmp_path))
    job = create_job(cfg.staging_root, {"name": "Movie", "source": {"hash": "H1"}}, job_id="J41")
    write_state(job, state="active", pct=35, pid=os.getpid())
    item = _client(cfg).get("/torrents").json()["items"][0]
    assert item["job"]["pct"] == 35
    assert item["delivered"] is False


def test_torrents_match_an_older_job_by_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "RTorrent", _FakeRT)
    cfg = Config(staging_root=str(tmp_path))
    job = create_job(cfg.staging_root, {"name": "Movie", "source": {"base_rel": "files/Movie.mkv"}}, job_id="J42")
    write_state(job, state="done", pct=100, dest=str(tmp_path / "gone"))
    item = _client(cfg).get("/torrents").json()["items"][0]
    assert item["job"]["id"] == "J42"
    # the library no longer holds it, so it is not delivered
    assert item["delivered"] is False


def test_torrents_stay_bare_without_a_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "RTorrent", _FakeRT)
    item = _client(Config(staging_root=str(tmp_path))).get("/torrents").json()["items"][0]
    assert "job" not in item
    assert "delivered" not in item
