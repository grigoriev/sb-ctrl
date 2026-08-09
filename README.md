# sb-ctrl

![CI](https://github.com/grigoriev/sb-ctrl/actions/workflows/ci.yml/badge.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Quality Gate](https://sonarcloud.io/api/project_badges/measure?project=grigoriev_sb-ctrl&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=grigoriev_sb-ctrl)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=grigoriev_sb-ctrl&metric=coverage)](https://sonarcloud.io/summary/new_code?id=grigoriev_sb-ctrl)

Backend service and agent for the seedbox to Plex pipeline. Runs on the Plex
host, exposes a **REST API** (FastAPI), lists completed torrents on the rTorrent
seedbox, and pulls a chosen title with `lftp`, sets permissions, and moves it
into the right Plex library (TMDb-based renaming lands in a later phase). Clients
are the [alfred-seedbox-workflow](https://github.com/grigoriev/alfred-seedbox-workflow)
and, later, a React UI.

The full design is in [SPEC.md](SPEC.md).

## REST API

`sb-ctrl serve` runs the API (uvicorn); `/docs` serves the OpenAPI schema. Every
route except `/health` needs `Authorization: Bearer <token>`.

```
GET  /torrents            completed torrents (newest first)
POST /plan                preview a transfer for a torrent + kind
POST /jobs                create and launch a transfer
GET  /jobs, /jobs/{id}    job state / progress
POST /jobs/{id}/retry     re-run a failed job
GET  /config              effective config (secrets redacted)
```

A thin CLI remains for the worker (`sb-ctrl run-job <id>`, invoked by
`systemd-run`) and admin (`list`, `status`, `config get`).

## Configuration

`~/.config/sb-ctrl/config.toml` (chmod 600). See SPEC.md section 3 for every
key. Nothing is stored on any client; all secrets live here.

## Development

```sh
uv sync --all-extras
uv run ruff check . && uv run ruff format --check .
uv run mypy sb_ctrl tests
uv run pytest --cov --cov-report=term-missing
```

Python 3.12+. FastAPI + uvicorn.

## Status

Alpha. Config, rTorrent listing, the transfer engine (plan/run/worker), and the
REST API are implemented; TMDb + naming and the deploy (systemd + Caddy) land in
later phases per SPEC.md.
