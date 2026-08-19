"""FastAPI REST layer over the domain modules (SPEC.md section 4).

The app is a thin adapter: the actual work lives in ``rtorrent``, ``planner``,
``jobs``, ``launcher``, and ``worker``. Clients (the Alfred workflow, a future
React UI) talk to this API; TLS is terminated by a reverse proxy in front.
"""

from __future__ import annotations

import dataclasses
import hmac
from pathlib import Path
from typing import Annotated, Any

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Response
from pydantic import BaseModel

from sb_ctrl import __version__, auth, launcher, planner, tmdb
from sb_ctrl.config import Config, load_config
from sb_ctrl.jobs import create_job, delete_job, jobs_dir, list_jobs, read_state, write_state
from sb_ctrl.rtorrent import RTorrent

_NOT_FOUND = "job not found"


def _find_job(cfg: Config, job_id: str) -> Path | None:
    """Find a job directory by matching an existing entry name, so a client-
    supplied id is never used to build a path (no traversal)."""
    root = jobs_dir(cfg.staging_root)
    if not root.is_dir():
        return None
    return next((e for e in root.iterdir() if e.name == job_id and e.is_dir()), None)


class LoginRequest(BaseModel):
    user: str
    password: str


class PlanRequest(BaseModel):
    hash: str
    kind: str
    name: str | None = None


class RunRequest(BaseModel):
    hash: str
    kind: str
    name: str | None = None
    collision: str = "overwrite"


def get_config() -> Config:
    return load_config()


def _client(cfg: Config) -> RTorrent:
    return RTorrent(cfg.rtorrent_url, cfg.rtorrent_user, cfg.rtorrent_pass, cfg.sftp_base)


ConfigDep = Annotated[Config, Depends(get_config)]


def login_configured(cfg: Config) -> bool:
    """True once a user, a password hash and a signing secret are all set."""
    return bool(cfg.auth_user and cfg.auth_password_hash and cfg.auth_secret)


def require_token(
    cfg: ConfigDep,
    authorization: Annotated[str | None, Header()] = None,
    sb_session: Annotated[str | None, Cookie()] = None,
) -> None:
    """Reject the request unless it proves who it is.

    Two ways in: the bearer token, which scripts and the Alfred workflow use,
    and the session cookie a browser gets from /login. When neither is
    configured (fresh install) the API is open, so setup works before then.
    """
    if cfg.api_token and authorization == f"Bearer {cfg.api_token}":
        return
    if login_configured(cfg) and sb_session and auth.session_user(cfg.auth_secret, sb_session):
        return
    if not cfg.api_token and not login_configured(cfg):
        return
    raise HTTPException(status_code=401, detail="unauthorized")


AuthDep = Depends(require_token)


def create_app() -> FastAPI:
    app = FastAPI(title="sb-ctrl", version=__version__)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__}

    @app.get("/me")
    def me(cfg: ConfigDep, sb_session: Annotated[str | None, Cookie()] = None) -> dict[str, Any]:
        """What the UI needs to decide between a login form and the app."""
        user = auth.session_user(cfg.auth_secret, sb_session) if login_configured(cfg) and sb_session else None
        return {"login_required": login_configured(cfg) and user is None, "user": user}

    @app.post("/login", responses={401: {"description": "bad credentials"}})
    def login(req: LoginRequest, response: Response, cfg: ConfigDep) -> dict[str, Any]:
        if not login_configured(cfg):
            raise HTTPException(status_code=400, detail="login not configured")
        ok = hmac.compare_digest(req.user, cfg.auth_user) and auth.verify_password(req.password, cfg.auth_password_hash)
        if not ok:
            raise HTTPException(status_code=401, detail="bad credentials")
        ttl = cfg.auth_ttl_hours * 3600
        response.set_cookie(
            auth.COOKIE_NAME,
            auth.issue_session(cfg.auth_secret, cfg.auth_user, ttl),
            max_age=ttl,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
        )
        return {"user": cfg.auth_user}

    @app.post("/logout")
    def logout(response: Response) -> dict[str, Any]:
        response.delete_cookie(auth.COOKIE_NAME, path="/")
        return {"ok": True}

    @app.get("/torrents", dependencies=[AuthDep])
    def torrents(cfg: ConfigDep) -> dict[str, Any]:
        return {"items": [dataclasses.asdict(t) for t in _client(cfg).list_completed()]}

    @app.get("/search", dependencies=[AuthDep])
    def search(name: str, cfg: ConfigDep) -> dict[str, Any]:
        result = tmdb.search_for(tmdb.TMDb(cfg.tmdb_key, cfg.tmdb_lang), name)
        return {
            "guess": result["guess"],
            "candidates": [{**dataclasses.asdict(c), "kind": c.kind} for c in result["candidates"]],
        }

    @app.post("/plan", dependencies=[AuthDep], responses={404: {"description": "torrent not found"}})
    def plan(req: PlanRequest, cfg: ConfigDep) -> dict[str, Any]:
        match = next((t for t in _client(cfg).list_completed() if t.hash == req.hash), None)
        if match is None:
            raise HTTPException(status_code=404, detail="torrent not found")
        return planner.plan(cfg, dataclasses.asdict(match), req.kind, req.name)

    @app.post("/jobs", dependencies=[AuthDep], responses={404: {"description": "torrent not found"}})
    def create(req: RunRequest, cfg: ConfigDep) -> dict[str, Any]:
        match = next((t for t in _client(cfg).list_completed() if t.hash == req.hash), None)
        if match is None:
            raise HTTPException(status_code=404, detail="torrent not found")
        result = planner.plan(cfg, dataclasses.asdict(match), req.kind, req.name)
        if result["collision"] and req.collision != "overwrite":
            return {"skipped": True, "dest_path": result["dest_path"]}
        job = create_job(cfg.staging_root, result["job_spec"])
        return {"job_id": job.name, "launcher": launcher.launch(job.name)}

    @app.get("/jobs", dependencies=[AuthDep])
    def jobs(cfg: ConfigDep) -> dict[str, Any]:
        return {"jobs": list_jobs(cfg.staging_root)}

    _job_errors: dict[int | str, dict[str, Any]] = {404: {"description": _NOT_FOUND}}

    @app.get("/jobs/{job_id}", dependencies=[AuthDep], responses=_job_errors)
    def job(job_id: str, cfg: ConfigDep) -> dict[str, Any]:
        job_dir = _find_job(cfg, job_id)
        if job_dir is None or not (job_dir / "state.json").is_file():
            raise HTTPException(status_code=404, detail=_NOT_FOUND)
        return read_state(job_dir)

    @app.post("/jobs/{job_id}/retry", dependencies=[AuthDep], responses=_job_errors)
    def retry(job_id: str, cfg: ConfigDep) -> dict[str, Any]:
        job_dir = _find_job(cfg, job_id)
        if job_dir is None:
            raise HTTPException(status_code=404, detail=_NOT_FOUND)
        write_state(job_dir, state="queued", error="", pct=0)
        return {"job_id": job_dir.name, "launcher": launcher.launch(job_dir.name)}

    @app.delete(
        "/jobs/{job_id}",
        dependencies=[AuthDep],
        responses={404: {"description": _NOT_FOUND}, 409: {"description": "job is running"}},
    )
    def remove(job_id: str, cfg: ConfigDep) -> dict[str, Any]:
        """Drop a finished or failed job from the list, staging leftovers too."""
        job_dir = _find_job(cfg, job_id)
        if job_dir is None:
            raise HTTPException(status_code=404, detail=_NOT_FOUND)
        state = read_state(job_dir).get("state") if (job_dir / "state.json").is_file() else None
        if state == "active":
            raise HTTPException(status_code=409, detail="job is running")
        delete_job(cfg.staging_root, job_dir)
        return {"deleted": job_id}

    @app.get("/config", dependencies=[AuthDep])
    def config(cfg: ConfigDep) -> dict[str, Any]:
        return cfg.as_dict()

    return app


app = create_app()
