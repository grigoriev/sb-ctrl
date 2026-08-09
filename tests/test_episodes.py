from __future__ import annotations

from pathlib import Path

from sb_ctrl.episodes import episode_targets, parse_episode


def test_parse_episode_formats() -> None:
    assert parse_episode("Show.S01E02.mkv") == (1, 2)
    assert parse_episode("show s1e5") == (1, 5)
    assert parse_episode("Show 3x08.mkv") == (3, 8)
    assert parse_episode("Show 102.mkv") == (1, 2)
    assert parse_episode("Show.mkv") is None


def test_episode_targets_places_videos_and_subs(tmp_path: Path) -> None:
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "Show.S01E01.mkv").write_text("v")
    (pack / "Show.S01E01.ru.srt").write_text("s")
    (pack / "Show.S01E02.mkv").write_text("v")
    (pack / "sample.mkv").write_text("junk")
    (pack / "readme.nfo").write_text("junk")

    targets = {src.name: dest for src, dest in episode_targets(pack, "/lib/Show (2020)")}
    assert targets["Show.S01E01.mkv"] == "/lib/Show (2020)/Season 01/S01E01.mkv"
    assert targets["Show.S01E01.ru.srt"] == "/lib/Show (2020)/Season 01/S01E01.ru.srt"
    assert targets["Show.S01E02.mkv"] == "/lib/Show (2020)/Season 01/S01E02.mkv"
    assert "sample.mkv" not in targets
    assert "readme.nfo" not in targets


def test_episode_targets_honors_configured_patterns(tmp_path: Path) -> None:
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "Show.S01E01.webm").write_text("v")
    (pack / "Show.S01E02.mkv").write_text("v")
    (pack / "Show.S01E03.PROOF.webm").write_text("junk")

    targets = {
        src.name: dest
        for src, dest in episode_targets(pack, "/lib/Show", video_ext=["webm"], sub_ext=[], skip_patterns=["proof"])
    }
    assert targets["Show.S01E01.webm"] == "/lib/Show/Season 01/S01E01.webm"
    assert "Show.S01E02.mkv" not in targets  # mkv is not in the configured video_ext
    assert "Show.S01E03.PROOF.webm" not in targets  # matches a skip pattern


def test_episode_targets_custom_subtitle_ext(tmp_path: Path) -> None:
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "Show.S01E01.en.vtt").write_text("s")

    targets = {src.name: dest for src, dest in episode_targets(pack, "/lib/Show", video_ext=[], sub_ext=["vtt"])}
    assert targets["Show.S01E01.en.vtt"] == "/lib/Show/Season 01/S01E01.en.vtt"
