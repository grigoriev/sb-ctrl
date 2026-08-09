"""FastAPI REST layer over the domain modules (SPEC.md section 4).

The app is a thin adapter: the actual work lives in ``rtorrent``, ``planner``,
``jobs``, ``launcher``, and ``worker``. Clients (the Alfred workflow, a future
React UI) talk to this API; TLS is terminated by a reverse proxy in front.
"""

from __future__ import annotations

import dataclasses
import os
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from sb_ctrl import __version__, launcher, planner
from sb_ctrl.config import Config, load_config
from sb_ctrl.jobs import create_job, jobs_dir, list_jobs, read_state, write_state
from sb_ctrl.rtorrent import RTorrent


class PlanRequest(BaseModel):
    hash: str
    kind: str
    name: str | None = None


class RunRequest(BaseModel):
    job_spec: dict[str, Any]
    collision: str = "overwrite"


def get_config() -> Config:
    return load_config()


def _client(cfg: Config) -> RTorrent:
    return RTorrent(cfg.rtorrent_url, cfg.rtorrent_user, cfg.rtorrent_pass, cfg.sftp_base)


ConfigDep = Annotated[Config, Depends(get_config)]


def require_token(cfg: ConfigDep, authorization: Annotated[str | None, Header()] = None) -> None:
    """Reject the request unless it carries the configured bearer token.

    When no token is configured (fresh install) the API is open, so setup works
    before a token is set.
    """
    if not cfg.api_token:
        return
    if authorization != f"Bearer {cfg.api_token}":
        raise HTTPException(status_code=401, detail="unauthorized")


AuthDep = Depends(require_token)


def create_app() -> FastAPI:
    app = FastAPI(title="sb-ctrl", version=__version__)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__}

    @app.get("/torrents", dependencies=[AuthDep])
    def torrents(cfg: ConfigDep) -> dict[str, Any]:
        return {"items": [dataclasses.asdict(t) for t in _client(cfg).list_completed()]}

    @app.post("/plan", dependencies=[AuthDep])
    def plan(req: PlanRequest, cfg: ConfigDep) -> dict[str, Any]:
        match = next((t for t in _client(cfg).list_completed() if t.hash == req.hash), None)
        if match is None:
            raise HTTPException(status_code=404, detail="torrent not found")
        return planner.plan(cfg, dataclasses.asdict(match), req.kind, req.name)

    @app.post("/jobs", dependencies=[AuthDep])
    def create(req: RunRequest, cfg: ConfigDep) -> dict[str, Any]:
        spec = req.job_spec
        if os.path.exists(spec["dest_path"]) and req.collision != "overwrite":
            return {"skipped": True, "dest_path": spec["dest_path"]}
        job = create_job(cfg.staging_root, spec)
        return {"job_id": job.name, "launcher": launcher.launch(job.name)}

    @app.get("/jobs", dependencies=[AuthDep])
    def jobs(cfg: ConfigDep) -> dict[str, Any]:
        return {"jobs": list_jobs(cfg.staging_root)}

    @app.get("/jobs/{job_id}", dependencies=[AuthDep])
    def job(job_id: str, cfg: ConfigDep) -> dict[str, Any]:
        job_dir = jobs_dir(cfg.staging_root) / job_id
        if not (job_dir / "state.json").is_file():
            raise HTTPException(status_code=404, detail="job not found")
        return read_state(job_dir)

    @app.post("/jobs/{job_id}/retry", dependencies=[AuthDep])
    def retry(job_id: str, cfg: ConfigDep) -> dict[str, Any]:
        job_dir = jobs_dir(cfg.staging_root) / job_id
        if not job_dir.is_dir():
            raise HTTPException(status_code=404, detail="job not found")
        write_state(job_dir, state="queued", error="", pct=0)
        return {"job_id": job_id, "launcher": launcher.launch(job_id)}

    @app.get("/config", dependencies=[AuthDep])
    def config(cfg: ConfigDep) -> dict[str, Any]:
        return cfg.as_dict()

    return app


app = create_app()
