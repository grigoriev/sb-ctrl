# sb-ctrl

![CI](https://github.com/grigoriev/sb-ctrl/actions/workflows/ci.yml/badge.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Quality Gate](https://sonarcloud.io/api/project_badges/measure?project=grigoriev_sb-ctrl&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=grigoriev_sb-ctrl)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=grigoriev_sb-ctrl&metric=coverage)](https://sonarcloud.io/summary/new_code?id=grigoriev_sb-ctrl)

Server-side brain and agent for the seedbox to Plex pipeline. Runs on the Plex
host, lists completed torrents on the rTorrent seedbox, and (in later phases)
pulls a chosen title with `lftp`, renames it via TMDb, sets permissions, and
moves it into the right Plex library. Driven over SSH by
[alfred-seedbox-workflow](https://github.com/grigoriev/alfred-seedbox-workflow).

The full design is in [SPEC.md](SPEC.md).

## CLI

Every command prints one JSON object to stdout; errors print `{"error": ...}` to
stderr and exit non-zero.

```sh
sb-ctrl list          # completed torrents on the seedbox (newest first)
sb-ctrl status        # transfer jobs
sb-ctrl config get    # effective configuration (secrets redacted)
```

## Configuration

`~/.config/sb-ctrl/config.toml` (chmod 600). See SPEC.md section 3 for every
key. Nothing is stored on the Mac; all secrets live here.

## Development

```sh
uv sync --all-extras
uv run ruff check . && uv run ruff format --check .
uv run mypy sb_ctrl tests
uv run pytest --cov --cov-report=term-missing
```

Python 3.11+. No runtime dependencies (standard library only).

## Status

Alpha. Phase P0 (config, rTorrent listing, status skeleton) is implemented; the
transfer worker, TMDb, and naming land in later phases per SPEC.md section 12.
