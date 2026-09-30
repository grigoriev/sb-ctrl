# CLAUDE.md

This file guides Claude Code when it works on or reviews this repository.

## Project Overview

sb-ctrl is the backend service and transfer agent of the seedbox to Plex pipeline. It runs on the
Plex host and exposes a REST API (FastAPI). It lists completed torrents on the rTorrent seedbox,
pulls a chosen title with `lftp`, sets permissions, and moves it into the right Plex library.
Clients are `alfred-seedbox-workflow` and `sb-ctrl-ui`. `sb-stack` runs the published image.

The design is in `SPEC.md`. The systemd deployment is in `DEPLOY.md`.

## Tech Stack

- **Python**: 3.14+, package manager uv, build backend hatchling
- **Runtime**: FastAPI + uvicorn. Domain modules use the standard library only
- **Lint and format**: ruff (line length 120)
- **Type check**: mypy, strict mode, on `sb_ctrl` and `tests`
- **Tests**: pytest, pytest-cov (branch coverage, `fail_under = 90`), FastAPI `TestClient`
- **Image**: `python:3.14-slim` pinned by digest, with `lftp` and `openssh-client`

## Common Commands

```sh
uv sync --all-extras                           # install the dependencies
uv run ruff check .                            # lint
uv run ruff format --check .                   # format check
uv run mypy sb_ctrl tests                      # type check
uv run pytest --cov --cov-report=term-missing  # tests with coverage
docker build -t sb-ctrl:test .                 # build the image
tests/smoke-image.sh sb-ctrl:test              # start the image and check the API
```

On an ARM machine, build the image with `--platform linux/amd64`.

## Architecture

Package `sb_ctrl/`, console entry point `sb-ctrl` (`sb_ctrl.cli:main`):

- `api.py`: thin FastAPI adapter over the domain modules. Routes and auth checks live here
- `auth.py`: scrypt password hash and a signed, stateless session cookie
- `config.py`: loads `config.toml` into dataclasses, redacts secrets for `GET /config`
- `rtorrent.py`: read-only XML-RPC client, maps seedbox paths to SFTP paths
- `tmdb.py`: TMDb search and title guessing. `naming.py`: sanitizer and kind-to-root map
- `planner.py`: turns a torrent and a kind into a job spec. No side effects
- `episodes.py`: lays a season pack out as `Show/Season NN/SNNEMM.ext`
- `jobs.py`: job state under `<staging_root>/.jobs/<id>/` (`spec.json`, `state.json`)
- `launcher.py`: starts the worker through `systemd-run --user`, or as a detached child in a container
- `lftp.py`: builds the `lftp` command. `worker.py`: pull, chown/chmod, atomic move, state
- `plex.py`: what the library holds, and a scan after delivery

Tests mirror the modules in `tests/test_<module>.py`. `tests/smoke-image.sh` checks a built image.
`config.example.toml` documents every config key.

## Code Style

- Strict mypy typing. Every function has annotations
- Start each module with `from __future__ import annotations`
- Import abstract types from `collections.abc`
- Keep domain modules free of FastAPI and third-party HTTP libraries. Use `urllib` and `xmlrpc`
- Inject side effects (process runner, chown, clock) so tests run without a seedbox or root
- Each module docstring names the SPEC.md section it implements
- Every CLI subcommand prints one JSON object to stdout, errors as `{"error": ...}` on stderr

## Review Focus

Flag these in a pull request:

- A route without the bearer token or session check. Only `/health`, `/me` and `/login` are open
- A change that lets the server start without auth when `[api] allow_open` is not set
- Secret comparison without `hmac.compare_digest`, or a secret in a log line or error message
- A new config secret that `GET /config` does not redact
- Credentials on a command line. SPEC.md section 10 requires config, `--netrc` or stdin, never argv
- Shell commands built by string concatenation. `lftp.py` quotes with `shlex`
- A move into the library that is not atomic, or staging off the library filesystem
- A breaking change to the REST response shape or the CLI JSON contract. Two clients depend on them
- New runtime dependencies. The runtime set is FastAPI and uvicorn only
- An unpinned base image or tool image in the `Dockerfile`, or a change to the root user without reason
- Missing tests for new behavior, or coverage below 90%
- No `## [Unreleased]` entry in `CHANGELOG.md`, or README not updated for a behavior change
- Workflow changes without SHA-pinned actions, `persist-credentials: false`, or `timeout-minutes`

## CI/CD and Release

- `ci.yml`: ShellCheck, Hadolint, actionlint, zizmor, `trivy config`, ruff, mypy, pytest, SonarCloud,
  package build, image build with Trivy scan and smoke test. A fixable CRITICAL finding fails
- `bump-version.yml`: manual, writes the version to `pyproject.toml`, `sb_ctrl/__init__.py` and
  `uv.lock`, cuts the changelog section, tags `vX.Y.Z`
- `docker-publish.yml`: on `v*` tags, pushes the tested image to `ghcr.io/grigoriev/sb-ctrl` by
  digest, attests provenance and SBOM, creates the immutable GitHub release
- Renovate updates dependencies and `uv.lock`

Commit, branch and pull request rules are in `CONTRIBUTING.md`.
