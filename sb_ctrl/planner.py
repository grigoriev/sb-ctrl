"""Turn a chosen torrent + kind into a transfer job spec (SPEC.md sections 7-8).

Phase P1 transfers the whole title without renaming its contents; TMDb-based
renaming enriches this in a later phase.
"""

from __future__ import annotations

import os
from typing import Any

from sb_ctrl.config import Config
from sb_ctrl.naming import root_for_kind, sanitize


def plan(cfg: Config, torrent: dict[str, Any], kind: str, name: str | None = None) -> dict[str, Any]:
    """Build the job spec for ``torrent`` under ``kind``.

    Returns ``{job_spec, dest_path, collision}``; ``collision`` is true when the
    destination already exists, to be resolved by the caller before ``run``.
    """
    display = name or str(torrent["name"])
    safe = sanitize(display)
    root = root_for_kind(cfg, kind)
    is_multi = bool(torrent["is_multi"])
    base_rel = str(torrent["base_rel"])
    basename = base_rel.rstrip("/").rsplit("/", 1)[-1]
    is_film = kind in ("movie", "cartoon")

    if is_multi:
        staging_item = safe
        dest_path = f"{root}/{safe}"
    elif is_film:
        # a single-file movie is renamed to the canonical "Name (Year).ext"
        staging_item = basename
        ext = os.path.splitext(basename)[1]
        final = f"{safe}{ext}"
        dest_path = f"{root}/{final}" if cfg.movie_layout == "flat" else f"{root}/{safe}/{final}"
    else:
        # a single-file episode keeps its name until the series-naming phase
        staging_item = basename
        dest_path = f"{root}/{safe}/{basename}"

    # a series folder is laid out into Season NN/SNNEMM.ext; everything else moves whole
    mode = "episodes" if is_multi and not is_film else "move"

    spec: dict[str, Any] = {
        "kind": kind,
        "name": safe,
        "mode": mode,
        "source": {
            "host": cfg.sftp_host,
            "base_rel": base_rel,
            "is_multi": is_multi,
            "size": int(torrent["size"]),
        },
        "staging_item": staging_item,
        "dest_path": dest_path,
        "perms": {
            "owner": cfg.owner,
            "group": cfg.group,
            "dir_mode": cfg.dir_mode,
            "file_mode": cfg.file_mode,
        },
        "lftp": {"limit_rate": cfg.lftp_limit_rate, "parallel": cfg.lftp_parallel},
        "staging_root": cfg.staging_root,
    }
    return {"job_spec": spec, "dest_path": dest_path, "collision": os.path.exists(dest_path)}
