# sb-ctrl

[![CI](https://github.com/grigoriev/sb-ctrl/actions/workflows/ci.yml/badge.svg)](https://github.com/grigoriev/sb-ctrl/actions/workflows/ci.yml)
[![Publish image](https://github.com/grigoriev/sb-ctrl/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/grigoriev/sb-ctrl/actions/workflows/docker-publish.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/grigoriev/sb-ctrl/badge)](https://scorecard.dev/viewer/?uri=github.com/grigoriev/sb-ctrl)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/14805/badge)](https://www.bestpractices.dev/projects/14805)
[![Release](https://img.shields.io/github/v/release/grigoriev/sb-ctrl)](https://github.com/grigoriev/sb-ctrl/releases)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=grigoriev_sb-ctrl&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=grigoriev_sb-ctrl)
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

With neither `[api] token` nor a complete `[auth]` section, `sb-ctrl serve`
refuses to start and exits with an error. The app refuses to start under
uvicorn too, and rejects every request with 401. To run without
authentication on purpose, set `[api] allow_open = true`. The API is then open
to anyone who can reach the port, and the server logs a warning at startup.

```
GET  /me                  whether a login is needed, and who is logged in
POST /login, /logout      start and end a browser session
GET  /torrents            completed torrents (newest first), with what Plex holds
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

## Container image

Each GitHub release publishes `ghcr.io/grigoriev/sb-ctrl:<version>`.
[sb-stack](https://github.com/grigoriev/sb-stack) runs it.

### Verify

Images published after 0.7.1 carry a signed build provenance and an SPDX SBOM
attestation. Check that this repository's workflow built an image:

```sh
gh attestation verify oci://ghcr.io/grigoriev/sb-ctrl:<tag> --owner grigoriev
```

Add `--predicate-type https://spdx.dev/Document/v2.3` to check the SBOM.

GitHub releases after 0.7.1 carry both as assets: `sb-ctrl-<tag>.intoto.jsonl`
(the provenance bundle) and `sb-ctrl-<tag>.spdx.json` (the SBOM). To check against
the downloaded bundle, add `--bundle sb-ctrl-<tag>.intoto.jsonl`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Disclaimer

This software is provided "as is", without warranty of any kind, as the LICENSE states. Use
it at your own risk. Sergey Grigoriev is not liable for damage from its use, as far as the law
allows. It is published free of charge, outside of any commercial offering, with no
obligation to support it. Security reports are welcome, see [SECURITY.md](SECURITY.md).

## License

MIT License - see [LICENSE](LICENSE) for details.
