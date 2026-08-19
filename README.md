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
route except `/health`, `/me` and `/login` needs proof of identity, and there are
two kinds. Scripts send `Authorization: Bearer <token>` from `[api] token`. A
browser posts to `/login` and gets a signed session cookie, from `[auth]`.

Set up the login once:

```sh
sb-ctrl hash-password        # prompts, prints a password_hash and a secret
```

Put both in `[auth]` together with the user name. Without that section a browser
has no way in, and only the bearer token opens the API.

```
GET  /me                  whether a login is needed, and who is logged in
POST /login, /logout      start and end a browser session
GET  /torrents            completed torrents (newest first)
POST /plan                preview a transfer for a torrent + kind
POST /jobs                create and launch a transfer
GET  /jobs, /jobs/{id}    job state / progress
DELETE /jobs/{id}         drop a finished or failed job, staging leftovers too
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

Python 3.14+. FastAPI + uvicorn.

## Status

Beta. Implemented: config, rTorrent listing, the transfer engine
(plan/run/worker), the REST API, TMDb search + movie naming, series season
layout, and the deploy guide (systemd + Caddy). Clients: the
[alfred-seedbox-workflow](https://github.com/grigoriev/alfred-seedbox-workflow)
and [sb-ctrl-ui](https://github.com/grigoriev/sb-ctrl-ui). Still to fill in: the
`[TBD]` config values (SPEC.md section 11). Later: file-subset selection and
adding magnets.
