from __future__ import annotations

from pathlib import Path

from sb_ctrl.episodes import episode_targets, parse_episode, season_of


def test_parse_episode_formats() -> None:
    assert parse_episode("Show.S01E02.mkv") == (1, 2)
    assert parse_episode("show s1e5") == (1, 5)
    assert parse_episode("Show.S01.E02.mkv") == (1, 2)
    assert parse_episode("Show S01 E02.mkv") == (1, 2)
    assert parse_episode("Show-S01-E02.mkv") == (1, 2)
    assert parse_episode("Show.S01.Extras.mkv") is None
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


def test_season_from_the_folder_and_number_from_the_file(tmp_path: Path) -> None:
    """A pack that numbers by folder, as an anime release usually does."""
    pack = tmp_path / "Demon Slayer"
    (pack / "S01 - Unwavering Resolve").mkdir(parents=True)
    (pack / "S01 - Unwavering Resolve" / "01 - Cruelty.mp4").write_text("v")
    (pack / "S01 - Unwavering Resolve" / "02 - Trainer Sakonji Urokodaki.mp4").write_text("v")
    (pack / "S03 - Swordsmith Village").mkdir()
    (pack / "S03 - Swordsmith Village" / "03 - A Sword from Over 300 Years Ago.mp4").write_text("v")

    targets = {src.name: dest for src, dest in episode_targets(pack, "/lib/Show")}
    assert targets["01 - Cruelty.mp4"] == "/lib/Show/Season 01/S01E01.mp4"
    assert targets["02 - Trainer Sakonji Urokodaki.mp4"] == "/lib/Show/Season 01/S01E02.mp4"
    # the 300 in the title used to read as season 3, episode 0
    assert targets["03 - A Sword from Over 300 Years Ago.mp4"] == "/lib/Show/Season 03/S03E03.mp4"


def test_a_season_in_two_parts_is_one_run_of_episodes(tmp_path: Path) -> None:
    pack = tmp_path / "pack"
    for folder, count in (("S02.1 - Mugen Train", 2), ("S02.2 - Entertainment District", 3)):
        (pack / folder).mkdir(parents=True)
        for n in range(1, count + 1):
            (pack / folder / f"{n:02d} - Episode.mp4").write_text("v")

    targets = sorted(dest for _, dest in episode_targets(pack, "/lib/Show"))
    assert targets == [f"/lib/Show/Season 02/S02E{n:02d}.mp4" for n in range(1, 6)]


def test_two_files_of_one_episode_leave_the_second_alone(tmp_path: Path) -> None:
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "Show.S01E01.mkv").write_text("v")
    (pack / "Show.S01E01.repack.mkv").write_text("v")
    targets = episode_targets(pack, "/lib/Show")
    assert len(targets) == 1


def test_season_of_reads_the_forms_a_pack_uses() -> None:
    assert season_of("S01 - Unwavering Resolve") == (1, 1)
    assert season_of("S02.2 - Entertainment District") == (2, 2)
    assert season_of("Season 3") == (3, 1)
    assert season_of("Сезон 4") == (4, 1)
    assert season_of("Shorts") is None
    assert season_of("Swordsmith Village") is None
