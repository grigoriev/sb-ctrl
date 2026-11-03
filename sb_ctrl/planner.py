"""Turn a chosen torrent + kind into a transfer job spec (SPEC.md sections 7-8).

The name is the TMDb match the client picked. A single-file movie is renamed to
``Name (Year).ext``; a series folder is laid out by ``episodes`` in the worker.
"""

from __future__ import annotations

import os
import stat
from typing import Any

from sb_ctrl.config import Config
from sb_ctrl.naming import root_for_kind, sanitize

NO_PATH = "the seedbox reports no path for this torrent"


class NoPathError(ValueError):
    """The torrent has no path on the seedbox, so lftp would have nothing to pull."""


def plan(cfg: Config, torrent: dict[str, Any], kind: str, name: str | None = None) -> dict[str, Any]:
    """Build the job spec for ``torrent`` under ``kind``.

    Returns ``{job_spec, dest_path, collision}``; ``collision`` is true when the
    destination already exists, to be resolved by the caller before ``run``.
    ``existing_size`` is added when a file is in the way, so the caller can tell
    the same release from another one. Raises ``NoPathError`` for a torrent
    without a path.
    """
    display = name or str(torrent["name"])
    safe = sanitize(display)
    root = root_for_kind(cfg, kind)
    is_multi = bool(torrent["is_multi"])
    base_rel = str(torrent["base_rel"])
    if not base_rel:
        raise NoPathError(NO_PATH)
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
        # a single-file episode keeps its name; only a series folder is laid out
        staging_item = basename
        dest_path = f"{root}/{safe}/{basename}"

    # a series folder is laid out into Season NN/SNNEMM.ext; everything else moves whole
    mode = "episodes" if is_multi and not is_film else "move"

    spec: dict[str, Any] = {
        "kind": kind,
        "name": safe,
        "mode": mode,
        "source": {
            "hash": str(torrent.get("hash", "")),
            "host": cfg.sftp_host,
            "user": cfg.sftp_user,
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
        "files": {
            "video_ext": cfg.video_ext,
            "sub_ext": cfg.sub_ext,
            "skip_patterns": cfg.skip_patterns,
        },
        "staging_root": cfg.staging_root,
        "plex": {"url": cfg.plex_url, "token": cfg.plex_token},
    }
    # One look at the destination: a worker can replace the file between two.
    try:
        found: os.stat_result | None = os.stat(_inside(root, dest_path))
    except FileNotFoundError:
        found = None
    result: dict[str, Any] = {"job_spec": spec, "dest_path": dest_path, "collision": found is not None}
    if found is not None and stat.S_ISREG(found.st_mode):
        result["existing_size"] = found.st_size
    return result


def _inside(root: str, path: str) -> str:
    """Return ``path`` normalized, or fail when it is not below ``root``.

    ``sanitize`` removes the separator, so a name cannot climb out. A name that
    sanitizes to nothing would still point at the root itself.
    """
    normalized = os.path.normpath(path)
    if not normalized.startswith(os.path.normpath(root) + os.sep):
        raise ValueError(f"destination is not inside the library root: {path}")
    return normalized
