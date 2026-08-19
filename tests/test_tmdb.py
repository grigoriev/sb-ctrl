from __future__ import annotations

from typing import Any

from sb_ctrl.tmdb import Candidate, TMDb, guess, search_for


def test_guess_movie() -> None:
    g = guess("Some.Movie.2024.1080p.BluRay.x264")
    assert g["media"] == "movie"
    assert g["year"] == "2024"
    assert g["query"] == "Some Movie"


def test_guess_tv() -> None:
    g = guess("Some.Show.S02E05.1080p")
    assert g["media"] == "tv"
    assert g["query"] == "Some Show"
    assert g["year"] == ""


def test_guess_tv_x_notation() -> None:
    assert guess("Another Show 3x08 HDTV")["media"] == "tv"


def test_guess_season_without_episode() -> None:
    g = guess("1670.S01.WEB-DL.1080p")
    assert g["media"] == "tv"
    assert g["query"] == "1670"
    assert g["year"] == ""


def test_guess_drops_container_and_tags() -> None:
    g = guess("Soulm8te.1080p.mkv")
    assert g["media"] == "movie"
    assert g["query"] == "Soulm8te"


def test_guess_cuts_at_first_release_tag() -> None:
    assert guess("Some Movie WEBRip x265 DTS-HD-GROUP")["query"] == "Some Movie"
    assert guess("Some_Movie_REMUX_2160p")["query"] == "Some Movie"


def test_candidate_kind() -> None:
    assert Candidate(1, "movie", "T", "T", "2020", "", False).kind == "movie"
    assert Candidate(1, "movie", "T", "T", "2020", "", True).kind == "cartoon"
    assert Candidate(1, "tv", "T", "T", "2020", "", False).kind == "series"
    assert Candidate(1, "tv", "T", "T", "2020", "", True).kind == "cartoon_series"


def test_search_parses_and_filters() -> None:
    results: dict[str, Any] = {
        "results": [
            {
                "id": 1,
                "media_type": "movie",
                "title": "Guardians",
                "original_title": "Guardians orig",
                "release_date": "2014-08-01",
                "genre_ids": [28, 16],
                "overview": "o",
            },
            {"id": 2, "media_type": "person", "name": "Someone"},
            {
                "id": 3,
                "media_type": "tv",
                "name": "Show",
                "original_name": "Show orig",
                "first_air_date": "2020-01-01",
                "genre_ids": [18],
            },
        ]
    }
    client = TMDb("k", fetch=lambda path, params: results)
    cands = client.search("x")
    assert [c.tmdb_id for c in cands] == [1, 3]
    assert cands[0].year == "2014"
    assert cands[0].original_title == "Guardians orig"
    assert cands[0].is_animation is True
    assert cands[0].kind == "cartoon"
    assert cands[1].media == "tv"
    assert cands[1].kind == "series"


def test_search_infers_media_from_dates() -> None:
    results: dict[str, Any] = {"results": [{"id": 5, "name": "X", "first_air_date": "2019-01-01"}]}
    client = TMDb("k", fetch=lambda path, params: results)
    assert client.search("x")[0].media == "tv"


class _Recorder:
    """Stands in for TMDb; answers only the media type it was primed with."""

    def __init__(self, hit: str) -> None:
        self.hit = hit
        self.calls: list[tuple[str, str]] = []

    def search(self, query: str, media: str = "multi") -> list[Candidate]:
        self.calls.append((query, media))
        if media != self.hit:
            return []
        return [Candidate(7, "movie", "T", "Orig", "2020", "o", False)]


def test_search_for_uses_the_guessed_media() -> None:
    client = _Recorder("movie")
    result = search_for(client, "Some.Movie.2020.1080p")  # type: ignore[arg-type]
    assert client.calls == [("Some Movie", "movie")]
    assert result["guess"]["year"] == "2020"
    assert len(result["candidates"]) == 1


def test_search_for_falls_back_to_multi() -> None:
    client = _Recorder("multi")
    result = search_for(client, "Soulm8te.1080p.mkv")  # type: ignore[arg-type]
    assert client.calls == [("Soulm8te", "movie"), ("Soulm8te", "multi")]
    assert len(result["candidates"]) == 1


def test_search_for_falls_back_to_the_raw_name() -> None:
    client = _Recorder("movie")
    search_for(client, "1080p")  # type: ignore[arg-type]
    assert client.calls[0] == ("1080p", "movie")
