from __future__ import annotations

from pathlib import Path

import pytest

from sb_ctrl.config import Config, from_dict, load_config

SAMPLE = """
staging_root = "/data/.staging"

[rtorrent]
url = "https://example/xmlrpc"
user = "u"
pass = "secret"

[sftp]
host = "sftp.example"
base = "downloads"

[tmdb]
key = "abc123"

[roots]
movies = "/data/movies"
cartoons = "/data/cartoons"
series = "/data/series"
cartoon_series = "/data/cartoon-series"

[perms]
owner = "plex"
group = "plex"
dir_mode = 775
file_mode = 664

[layout]
movie = "flat"

[lftp]
limit_rate = "2M"
parallel = 4
"""


def test_defaults_when_no_file(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "missing.toml")
    assert cfg == Config()
    assert cfg.movie_layout == "folder"
    assert cfg.sftp_base == "files"


def test_load_from_toml(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(SAMPLE)
    cfg = load_config(path)
    assert cfg.rtorrent_url == "https://example/xmlrpc"
    assert cfg.rtorrent_user == "u"
    assert cfg.sftp_base == "downloads"
    assert cfg.tmdb_key == "abc123"
    assert cfg.root_series == "/data/series"
    assert cfg.dir_mode == "775"
    assert cfg.file_mode == "664"
    assert cfg.movie_layout == "flat"
    assert cfg.lftp_limit_rate == "2M"
    assert cfg.lftp_parallel == 4
    assert cfg.staging_root == "/data/.staging"


def test_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "c.toml"
    path.write_text('[tmdb]\nkey = "envkey"\n')
    monkeypatch.setenv("SB_CTRL_CONFIG", str(path))
    assert load_config().tmdb_key == "envkey"


def test_as_dict_redacts_secrets() -> None:
    cfg = from_dict({"rtorrent": {"pass": "p"}, "tmdb": {"key": "k"}})
    data = cfg.as_dict()
    assert data["rtorrent_pass"] == "***"
    assert data["tmdb_key"] == "***"


def test_as_dict_keeps_empty_secrets() -> None:
    data = Config().as_dict()
    assert data["rtorrent_pass"] == ""
    assert data["tmdb_key"] == ""


def test_files_defaults() -> None:
    cfg = Config()
    assert ".mkv" in cfg.video_ext
    assert ".srt" in cfg.sub_ext
    assert cfg.skip_patterns == ["sample"]


def test_files_section_normalizes() -> None:
    cfg = from_dict(
        {"files": {"video_ext": ["MKV", ".WebM"], "sub_ext": ["SRT"], "skip_patterns": ["Sample", "PROOF"]}}
    )
    assert cfg.video_ext == [".mkv", ".webm"]
    assert cfg.sub_ext == [".srt"]
    assert cfg.skip_patterns == ["sample", "proof"]
