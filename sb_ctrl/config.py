"""Server-side configuration for sb-ctrl, loaded from a TOML file.

All logic and secrets live on the server; the Mac front-end holds none. See
SPEC.md section 3 for the field reference.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "sb-ctrl" / "config.toml"

DEFAULT_VIDEO_EXT = [".mkv", ".mp4", ".avi", ".m4v", ".mov", ".ts"]
DEFAULT_SUB_EXT = [".srt", ".ass", ".sub"]
DEFAULT_SKIP_PATTERNS = ["sample"]


def _norm_ext(items: Any) -> list[str]:
    """Lowercase each extension and ensure a leading dot."""
    out = []
    for raw in items:
        ext = str(raw).lower().strip()
        out.append(ext if ext.startswith(".") else f".{ext}")
    return out


def _norm_patterns(items: Any) -> list[str]:
    return [str(p).lower() for p in items]


@dataclass(frozen=True)
class Config:
    """Resolved configuration with sensible defaults; empty strings are unset."""

    rtorrent_url: str = "https://sb.mim.box.ca/xmlrpc"
    rtorrent_user: str = ""
    rtorrent_pass: str = ""
    sftp_host: str = "sb.g7v.io"
    sftp_base: str = "files"
    tmdb_key: str = ""
    tmdb_lang: str = "en-US"
    root_movies: str = ""
    root_cartoons: str = ""
    root_series: str = ""
    root_cartoon_series: str = ""
    owner: str = ""
    group: str = ""
    dir_mode: str = "775"
    file_mode: str = "664"
    movie_layout: str = "folder"
    video_ext: list[str] = field(default_factory=lambda: list(DEFAULT_VIDEO_EXT))
    sub_ext: list[str] = field(default_factory=lambda: list(DEFAULT_SUB_EXT))
    skip_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_SKIP_PATTERNS))
    lftp_limit_rate: str = ""
    lftp_parallel: int = 1
    staging_root: str = ""
    api_host: str = "127.0.0.1"
    api_port: int = 8765
    api_token: str = ""
    auth_user: str = ""
    auth_password_hash: str = ""
    auth_secret: str = ""
    auth_ttl_hours: int = 720

    def as_dict(self) -> dict[str, Any]:
        """Return the config as a plain dict, with secrets redacted."""
        data = asdict(self)
        for secret in ("rtorrent_pass", "tmdb_key", "api_token", "auth_password_hash", "auth_secret"):
            if data[secret]:
                data[secret] = "***"
        return data


def from_dict(data: dict[str, Any]) -> Config:
    """Build a Config from a parsed TOML mapping (nested sections)."""
    base = Config()
    rt = data.get("rtorrent", {})
    sftp = data.get("sftp", {})
    tmdb = data.get("tmdb", {})
    roots = data.get("roots", {})
    perms = data.get("perms", {})
    layout = data.get("layout", {})
    files = data.get("files", {})
    lftp = data.get("lftp", {})
    api = data.get("api", {})
    auth = data.get("auth", {})
    return Config(
        rtorrent_url=rt.get("url", base.rtorrent_url),
        rtorrent_user=rt.get("user", base.rtorrent_user),
        rtorrent_pass=rt.get("pass", base.rtorrent_pass),
        sftp_host=sftp.get("host", base.sftp_host),
        sftp_base=sftp.get("base", base.sftp_base),
        tmdb_key=tmdb.get("key", base.tmdb_key),
        tmdb_lang=tmdb.get("lang", base.tmdb_lang),
        root_movies=roots.get("movies", base.root_movies),
        root_cartoons=roots.get("cartoons", base.root_cartoons),
        root_series=roots.get("series", base.root_series),
        root_cartoon_series=roots.get("cartoon_series", base.root_cartoon_series),
        owner=perms.get("owner", base.owner),
        group=perms.get("group", base.group),
        dir_mode=str(perms.get("dir_mode", base.dir_mode)),
        file_mode=str(perms.get("file_mode", base.file_mode)),
        movie_layout=layout.get("movie", base.movie_layout),
        video_ext=_norm_ext(files.get("video_ext", base.video_ext)),
        sub_ext=_norm_ext(files.get("sub_ext", base.sub_ext)),
        skip_patterns=_norm_patterns(files.get("skip_patterns", base.skip_patterns)),
        lftp_limit_rate=lftp.get("limit_rate", base.lftp_limit_rate),
        lftp_parallel=int(lftp.get("parallel", base.lftp_parallel)),
        staging_root=data.get("staging_root", base.staging_root),
        api_host=api.get("host", base.api_host),
        api_port=int(api.get("port", base.api_port)),
        api_token=api.get("token", base.api_token),
        auth_user=auth.get("user", base.auth_user),
        auth_password_hash=auth.get("password_hash", base.auth_password_hash),
        auth_secret=auth.get("secret", base.auth_secret),
        auth_ttl_hours=int(auth.get("ttl_hours", base.auth_ttl_hours)),
    )


def load_config(path: Path | None = None) -> Config:
    """Load the config from ``path`` (or $SB_CTRL_CONFIG, or the default).

    A missing file yields all defaults, so the CLI still runs before setup.
    """
    if path is None:
        env = os.environ.get("SB_CTRL_CONFIG")
        path = Path(env) if env else DEFAULT_CONFIG_PATH
    if not path.exists():
        return Config()
    return from_dict(tomllib.loads(path.read_text()))
