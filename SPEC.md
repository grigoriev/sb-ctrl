# sb-ctrl — Specification (Draft v1)

Server-side **brain + agent** for the seedbox → Plex pipeline. Runs on Ubuntu
`beaver.h.g7v.io`, written in **Python 3**. Holds all configuration and secrets,
and exposes a **JSON CLI** that the Mac front-end (`alfred-seedbox-workflow`)
invokes over SSH. The Mac holds no secrets and no logic.

Status: plan only, no implementation. Decisions are locked from the interview;
`[TBD]` marks values to fill before building.

---

## 1. Role in the system

| System | Role | Access |
|---|---|---|
| Clients (`alfred-seedbox-workflow`, a future React UI) | Thin UIs over the REST API | HTTPS + bearer token |
| **Ubuntu `beaver.h.g7v.io`** — **sb-ctrl** | Backend service + agent: rTorrent, TMDb, naming, transfer, jobs | REST over HTTPS, LAN/VPN-only, always up |
| whatbox (seedbox) | rTorrent + source files | XML-RPC `https://sb.mim.box.ca/xmlrpc` (Basic auth); SFTP `sftp://sb.g7v.io` (key). Downloads under `files/`. Same host, two DNS names. |

**Data flow:** whatbox → (lftp SFTP pull, **on Ubuntu**) → Ubuntu staging → Plex
library. Clients are never in the data path — they only call the API.

Consequence: everything (even listing) needs the client to reach beaver (LAN/VPN).
Accepted — acting requires it anyway, and keeping all creds on the server is the
point.

---

## 2. Language & layout

- **Python 3** (3.12 and 3.14), **FastAPI** + **uvicorn**. The domain modules
  (`rtorrent`, `planner`, `jobs`, `lftp`, `launcher`, `worker`) use the standard
  library; `api.py` is a thin FastAPI adapter over them.
- Package `sb_ctrl`, console entry point `sb-ctrl` (`serve`, `run-job`, and
  admin subcommands). `pytest` + FastAPI `TestClient`.
- Deployed on beaver (venv) behind a reverse proxy; see Deployment.
- Config file: `~/.config/sb-ctrl/config.toml` (chmod 600). No secrets on any
  client.

---

## 3. Configuration (server-side, `config.toml`)

| Key | Meaning | Default |
|---|---|---|
| `rtorrent.url` | XML-RPC endpoint | `https://sb.mim.box.ca/xmlrpc` |
| `rtorrent.user` / `rtorrent.pass` | Basic auth | `[TBD]` |
| `sftp.host` | SFTP host for lftp | `sb.g7v.io` |
| `sftp.base` | remote base dir mapped from rTorrent paths | `files` |
| `tmdb.key` | TMDb API key | `[TBD]` |
| `tmdb.lang` | search/UI language hint (naming still uses original_title) | `en-US` |
| `roots.movies` / `.cartoons` / `.series` / `.cartoon_series` | 4 library roots | `[TBD]` |
| `perms.owner` / `.group` | target ownership | `[TBD]` |
| `perms.dir_mode` / `.file_mode` | target modes | `[TBD]` (suggest 775 / 664) |
| `layout.movie` | `folder` (per-title dir) or `flat` | `folder` |
| `lftp.limit_rate` | bandwidth cap | none |
| `lftp.parallel` | segmented/parallel transfer | modest |
| `staging_root` | staging dir, **same filesystem as the libraries** | `[TBD]` |
| `api.host` / `api.port` | uvicorn bind | `127.0.0.1` / `8765` |
| `api.token` | bearer token for the REST API | `[TBD]` |

`GET /config` returns this (secrets redacted); `sb-ctrl config get` prints it.

---

## 4. REST API (FastAPI)

Clients (the Alfred workflow, a future React UI) talk to a **FastAPI** service.
Pydantic models formalize the contract and produce an OpenAPI schema at `/docs`.
A bearer token (`Authorization: Bearer <token>`) guards every route except
`/health`; when no token is configured the API is open, so first-time setup
works. TLS is terminated by a reverse proxy (see Deployment).

| Method + path | Body / params | Result |
|---|---|---|
| `GET /health` | — | `{ok, version}` (no auth) |
| `GET /torrents` | — | `{items:[{hash,name,size,is_multi,base_rel,finished,...}]}` completed, newest first |
| `GET /torrents/{hash}/files` | — | `{files:[{index,path,size,done}]}` *(later phase)* |
| `GET /search` | `kind`, `name` | `{guess_kind, candidates:[...]}` *(TMDb phase)* |
| `POST /plan` | `{hash, kind, name?}` | `{job_spec, dest_path, collision}` (preview, no side effects) |
| `POST /jobs` | `{job_spec, collision: overwrite\|skip\|cancel}` | `{job_id, launcher}` — creates and launches the job |
| `GET /jobs` | — | `{jobs:[{id,name,state,pct,rate,eta,error?}]}` |
| `GET /jobs/{id}` | — | the job's state |
| `POST /jobs/{id}/retry` | — | `{job_id}` |
| `GET /config` | — | effective config (secrets redacted) |
| `PUT /config` | — | update config *(later phase)* |

A thin CLI remains for the service entrypoint and the worker:
`sb-ctrl serve` (run the API under uvicorn), `sb-ctrl run-job <id>` (invoked by
`systemd-run`). `list` / `status` / `plan` / `run` / `retry` also exist on the
CLI for admin and debugging.

## 4a. Deployment

- `sb-ctrl serve` runs uvicorn on `api.host:api.port` (default `127.0.0.1:8765`),
  managed by a **systemd** service.
- A **Caddy** reverse proxy terminates TLS with a **Let's Encrypt** certificate
  and forwards to uvicorn. Because the host is VPN-only (port 80 not public),
  Caddy obtains the cert via the **DNS-01** challenge using the `g7v.io` DNS
  provider's API (provider `[TBD]`).
- Transfers run as separate `systemd-run --user` units, so they survive a
  service restart; the API tracks them through the job state files.

---

## 5. rTorrent integration

- `d.multicall2` (XML-RPC POST, Basic auth) for the list; fields `d.hash`,
  `d.name`, `d.size_bytes`, `d.complete`, `d.base_path`, `d.is_multi_file`.
- Filter `complete == 1`. Sort newest first.
- **Path mapping:** `d.base_path` (absolute on whatbox, e.g.
  `/home/<user>/files/<Title>`) → strip the home prefix → `files/<Title>` (this is
  `base_rel`) → lftp `cd files; mirror <Title>` (folder) / `get <Title>` (file).
- File subset: `f.multicall` on the hash for per-file path/size/completed.

---

## 6. TMDb integration

- **Guess** title + year from the torrent name (strip release tags; year regex).
- **Category guess (overridable):** `SxxEyy`/season structure → TV, else Movie;
  TMDb genre **Animation (16)** → Cartoons / Cartoon-series, else Movies / Series.
- **Search** (movie or tv) → candidates; the Mac shows them and the user confirms.
  Fallback: manual title + year (no TMDb id).
- **Naming source:** always `original_title` (Russian films keep Russian). Year
  from `release_date` / `first_air_date`.
- **TV episode mapping:** parse `S01E02` / `s01e02` / `1x02` / joined `0102`/`101`
  from source filenames. Unmatched → flagged for manual entry or skip. Exotic
  patterns added later.

---

## 7. Naming & layout (final targets)

**Movie / Cartoon** (`layout.movie = folder`):
```
<root>/Original Name (Year)/Original Name (Year).ext
<root>/Original Name (Year)/Original Name (Year).ru.srt
```
`flat` drops the per-title folder. One version per title (no quality tags); a
second version triggers a collision prompt.

**Series / Cartoon-series** (minimal filenames):
```
<root>/Show Name (Year)/Season 01/S01E02.ext
<root>/Show Name (Year)/Season 01/S01E02.ru.srt
```
Show folder = `original_title (Year)`; season = `Season NN` (zero-padded); file =
`SNNEMM.ext`.

**Sanitization:** `/`→`-`, `:`→` -`, strip `? * " < > |`; keep the source extension.

**Kept vs skipped:** transfer **video + subtitles** only (subtitle renamed to the
video basename, preserving a `.ru`/`.en`-style language suffix if present). Skip
samples, extras/featurettes, `.nfo`, `.txt`, images.

---

## 8. Job model & worker

- Job dir `<staging_root>/.jobs/<id>/` → `state.json` (state, pct, rate, eta,
  error), `spec.json`, `log`.
- `run` launches the worker via **`systemd-run --user`** (transient unit; linger
  enabled so it survives SSH/Mac disconnect). `nohup` fallback. The worker is
  `sb-ctrl run-job <id>`.
- Worker steps:
  1. lftp pull into `<staging_root>/<id>/` — `mirror -c` (folder) / `get -c`
     (file), resume, optional `net:limit-rate` and parallel segments.
  2. **Progress:** `du(staging)/size` → `pct`; rate/ETA from the delta; written to
     `state.json` periodically.
  3. **Organize:** rename to final names; subtitles alongside; skip junk.
  4. `chown owner:group`, `chmod dir_mode/file_mode` (SSH user can chown — no sudo).
  5. **Atomic `mv`** into the library root (same filesystem). Collisions were
     resolved at `run` time.
  6. `state = done` (or `failed`). **No Plex trigger** (Plex auto-scans). **No
     whatbox change** (keeps seeding, stays in the list).
- **Concurrency:** multiple jobs may run in parallel; one job = one torrent.
- **Retry:** manual only (`retry <id>`); `-c` resumes.

---

## 9. Error handling

- rTorrent / TMDb HTTP errors → `{"error"}`, non-zero exit; the Mac shows it.
- No TMDb match → the Mac offers manual title+year (plan accepts a manual name).
- lftp failure → job `failed`; wait for `retry`.

## 10. Security

- All secrets in `config.toml` (chmod 600) on beaver. The Mac never sees them.
- SSH/SFTP via keys; the worker runs as the SSH user (chown allowed, no sudo).
- Creds passed to curl/lftp via config/`--netrc`/stdin, never argv.

## 11. Open items `[TBD]`

- 4 library roots; `staging_root` (same FS as libraries).
- `perms.owner:group` + modes.
- `tmdb.key`; `rtorrent.user/pass`; exact whatbox home prefix for path mapping.
- Confirm `systemd --user` + linger on beaver.

## 12. Build phasing

- **P0** config + `list` (rTorrent) + path mapping + `status` skeleton. ✅
- **P1** `plan`/`run`/`run-job`: whole-title transfer + job state + `systemd-run`. ✅
- **P2** TMDb search + movie naming (rename to `Name (Year).ext`). ✅
- **P3** series season layout + `SxxEyy` + subtitles. ✅
- **REST** FastAPI adapter + bearer auth + deploy guide. ✅
- **P4** file-subset selection, batch queue, add magnet/.torrent. Later.

---

Clients consume the REST API in §4: the Alfred workflow
(**`alfred-seedbox-workflow/SPEC.md`**) and the React UI
(**`sb-ctrl-ui`**). The OpenAPI schema at `/docs` types both.
