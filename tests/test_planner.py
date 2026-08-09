from __future__ import annotations

from pathlib import Path

from sb_ctrl.config import Config
from sb_ctrl.planner import plan


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
    assert spec["dest_path"] == f"{tmp_path}/movies/Film 2024/Film.2024.mkv"


def test_single_movie_flat_layout(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, "flat")
    result = plan(cfg, _torrent("Film 2024", "files/Film.2024.mkv", False), "movie")
    assert result["job_spec"]["dest_path"] == f"{tmp_path}/movies/Film.2024.mkv"


def test_name_override_and_collision(tmp_path: Path) -> None:
    (tmp_path / "series" / "Chosen").mkdir(parents=True)
    cfg = _cfg(tmp_path)
    result = plan(cfg, _torrent("raw name", "files/raw name", True), "series", name="Chosen")
    assert result["job_spec"]["name"] == "Chosen"
    assert result["collision"] is True
