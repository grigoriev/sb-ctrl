# sb-pull — Specification (Draft v1)

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
| Mac + Alfred (`alfred-seedbox-workflow`) | Thin UI; runs `ssh beaver sb-pull <cmd> --json` | — |
| **Ubuntu `beaver.h.g7v.io`** — **sb-pull** | Brain + agent: rTorrent, TMDb, naming, transfer, jobs | SSH key-based, LAN/VPN-only, always up |
| whatbox (seedbox) | rTorrent + source files | XML-RPC `https://sb.mim.box.ca/xmlrpc` (Basic auth); SFTP `sftp://sb.g7v.io` (key). Downloads under `files/`. Same host, two DNS names. |

**Data flow:** whatbox → (lftp SFTP pull, **on Ubuntu**) → Ubuntu staging → Plex
library. The Mac is never in the data path — it only triggers `sb-pull` over SSH.

Consequence: everything (even listing) needs the Mac to reach beaver (LAN/VPN).
Accepted — acting requires it anyway, and keeping all creds on the server is the
point.

---

## 2. Language & layout

- **Python 3** (present on Ubuntu). Prefer stdlib; `urllib`/`http.client` for
  HTTP so there are no hard third-party deps (a `requests` extra is optional).
- Package `sb_pull`, console entry point `sb-pull`. `pytest` for tests.
- Deployed on beaver (pipx or a venv); invoked as `sb-pull <subcommand> --json`.
- Config file: `~/.config/sb-pull/config.toml` (chmod 600). No secrets on the
  command line or in the Alfred workflow.

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

`sb-pull config` reads/edits this (so the Mac can open settings over SSH).

---

## 4. CLI contract (invoked over SSH, JSON in/out)

All commands accept `--json` and print a single JSON object to stdout; errors go
to stderr with a non-zero exit and `{"error": "..."}`. This contract is the API
the Alfred workflow depends on — keep it stable.

| Command | Input | Output |
|---|---|---|
| `list` | — | `{items:[{hash,name,size,is_multi,added,base_rel}]}` completed only, newest first |
| `files <hash>` | hash | `{files:[{index,path,size,done}]}` |
| `search` | `--kind auto|movie|cartoon|series|cartoon_series --name <torrent name>` | `{guess_kind, candidates:[{tmdb_id,media,title,original_title,year,overview}]}` |
| `plan` | `{hash, files?, kind, tmdb_id}` | `{job_spec, targets:[{src_rel,dest_abs}], collisions:[dest_abs], perms}` (preview, no side effects) |
| `run` | `{job_spec, collision: overwrite|skip|cancel}` | `{job_id}` — creates the job, launches the worker |
| `status` | `[--job <id>]` | `{jobs:[{id,name,state,pct,rate,eta,error?}]}` |
| `retry` | `<id>` | `{job_id}` |
| `run-job` | `<id>` | internal worker (invoked by systemd-run), not called by the Mac |
| `config` | `get|edit` | reads/edits `config.toml` |

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
  `sb-pull run-job <id>`.
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

- **P0** config + `list` (rTorrent) + path mapping + `status` skeleton.
- **P1** `plan`/`run`/`run-job`: whole-title transfer (no rename) + job state.
- **P2** TMDb + movie naming + folder + perms + atomic mv.
- **P3** TV mapping + season layout + subtitles.
- **P4** file-subset selection, `retry`, polish.
- **Later** add magnet/.torrent; batch queue.

---

The Mac front-end and its wizard UX are specified in
**`alfred-seedbox-workflow/SPEC.md`**, which consumes the CLI contract in §4.
