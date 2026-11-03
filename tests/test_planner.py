from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from sb_ctrl.config import Config
from sb_ctrl.planner import NoPathError, plan


def _cfg(tmp_path: Path, movie_layout: str = "folder") -> Config:
    return Config(
        root_movies=str(tmp_path / "movies"),
        root_series=str(tmp_path / "series"),
        owner="plex",
        group="plex",
        movie_layout=movie_layout,
        staging_root=str(tmp_path / "staging"),
    )


def _torrent(name: str, base_rel: str, is_multi: bool) -> dict[str, object]:
    return {"hash": "H", "name": name, "size": 100, "is_multi": is_multi, "base_rel": base_rel}


def test_multi_folder_lands_as_title_folder(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    result = plan(cfg, _torrent("The Show S01", "files/The Show S01", True), "series")
    spec = result["job_spec"]
    assert spec["staging_item"] == "The Show S01"
    assert spec["dest_path"] == f"{tmp_path}/series/The Show S01"
    assert result["collision"] is False


def test_single_movie_folder_layout(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, "folder")
    result = plan(cfg, _torrent("Film 2024", "files/Film.2024.mkv", False), "movie")
    spec = result["job_spec"]
    assert spec["staging_item"] == "Film.2024.mkv"
    assert spec["dest_path"] == f"{tmp_path}/movies/Film 2024/Film 2024.mkv"


def test_single_movie_flat_layout(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, "flat")
    result = plan(cfg, _torrent("Film 2024", "files/Film.2024.mkv", False), "movie")
    assert result["job_spec"]["dest_path"] == f"{tmp_path}/movies/Film 2024.mkv"


def test_single_episode_keeps_its_name(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    result = plan(cfg, _torrent("Show", "files/Show.S01E02.mkv", False), "series")
    assert result["job_spec"]["dest_path"] == f"{tmp_path}/series/Show/Show.S01E02.mkv"


def test_name_override_and_collision(tmp_path: Path) -> None:
    (tmp_path / "series" / "Chosen").mkdir(parents=True)
    cfg = _cfg(tmp_path)
    result = plan(cfg, _torrent("raw name", "files/raw name", True), "series", name="Chosen")
    assert result["job_spec"]["name"] == "Chosen"
    assert result["collision"] is True


def test_a_file_in_the_way_reports_its_size(tmp_path: Path) -> None:
    dest = tmp_path / "movies" / "Film 2024" / "Film 2024.mkv"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"x" * 42)
    result = plan(_cfg(tmp_path, "folder"), _torrent("Film 2024", "files/Film.2024.mkv", False), "movie")
    assert result["collision"] is True
    assert result["existing_size"] == 42


def test_a_free_destination_reports_no_size(tmp_path: Path) -> None:
    result = plan(_cfg(tmp_path, "folder"), _torrent("Film 2024", "files/Film.2024.mkv", False), "movie")
    assert "existing_size" not in result


def test_a_folder_in_the_way_reports_no_size(tmp_path: Path) -> None:
    # A folder takes some files of a pack and skips others, so its size says nothing.
    (tmp_path / "series" / "Chosen").mkdir(parents=True)
    result = plan(_cfg(tmp_path), _torrent("raw name", "files/raw name", True), "series", name="Chosen")
    assert result["collision"] is True
    assert "existing_size" not in result


def test_a_torrent_without_a_path_is_refused(tmp_path: Path) -> None:
    with pytest.raises(NoPathError, match="the seedbox reports no path for this torrent"):
        plan(_cfg(tmp_path), _torrent("Film 2024", "", False), "movie")


def test_a_file_that_goes_during_the_preview_reports_no_size(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A worker removes the old file right before it moves the new one in.
    dest = tmp_path / "movies" / "Film 2024" / "Film 2024.mkv"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"x")
    real_stat = os.stat

    def gone(path: str, *args: Any, **kwargs: Any) -> os.stat_result:
        if str(path) == str(dest):
            raise FileNotFoundError(path)
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", gone)
    result = plan(_cfg(tmp_path, "folder"), _torrent("Film 2024", "files/Film.2024.mkv", False), "movie")
    assert "existing_size" not in result


def test_name_that_sanitizes_to_nothing_is_rejected(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    with pytest.raises(ValueError, match="not inside the library root"):
        plan(cfg, _torrent("raw name", "files/raw name", True), "series", name="..")


def test_episode_basename_cannot_leave_the_root(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    with pytest.raises(ValueError, match="not inside the library root"):
        plan(cfg, _torrent("Show", "files/..", False), "series")
