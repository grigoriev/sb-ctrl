from __future__ import annotations

from typing import Any

from sb_ctrl.tmdb import Candidate, TMDb, guess, readable, search_for


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
                "poster_path": "/abc.jpg",
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
    assert cands[0].poster == "https://image.tmdb.org/t/p/w154/abc.jpg"
    assert cands[1].poster == ""
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

    def search(self, query: str, media: str = "multi", lang: str = "", year: str = "") -> list[Candidate]:
        self.calls.append((query, media))
        if media != self.hit:
            return []
        return [Candidate(7, "movie", "T", "Orig", "2020", "o", False)]

    def name_titles(self, candidates: list[Candidate], query: str, media: str) -> list[Candidate]:
        return candidates


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


def _by_language(ru: dict[str, Any], en: dict[str, Any]) -> Any:
    """A fetch that answers differently per requested language."""

    def fetch(path: str, params: dict[str, str]) -> dict[str, Any]:
        return en if params.get("language") == "en-US" else ru

    return fetch


def test_fill_overviews_borrows_the_english_text() -> None:
    ru = {"results": [{"id": 5, "title": "Тихий", "overview": ""}, {"id": 6, "title": "Шумный", "overview": "есть"}]}
    en = {"results": [{"id": 5, "title": "Quiet", "overview": "a quiet film"}]}
    client = TMDb("k", lang="ru-RU", fetch=_by_language(ru, en))
    filled = client.fill_overviews(client.search("x"), "x", "movie")
    assert [c.overview for c in filled] == ["a quiet film", "есть"]


def test_fill_overviews_leaves_an_english_client_alone() -> None:
    ru = {"results": [{"id": 5, "title": "Quiet", "overview": ""}]}
    client = TMDb("k", fetch=_by_language(ru, {"results": []}))
    assert client.fill_overviews(client.search("x"), "x", "movie")[0].overview == ""


def test_fill_overviews_keeps_an_empty_overview_with_no_english_match() -> None:
    ru = {"results": [{"id": 5, "title": "Тихий", "overview": ""}]}
    client = TMDb("k", lang="ru-RU", fetch=_by_language(ru, {"results": []}))
    assert client.fill_overviews(client.search("x"), "x", "movie")[0].overview == ""


def test_search_for_fills_a_missing_overview() -> None:
    ru = {"results": [{"id": 5, "title": "Тихий", "overview": ""}]}
    en = {"results": [{"id": 5, "title": "Quiet", "overview": "a quiet film"}]}
    client = TMDb("k", lang="ru-RU", fetch=_by_language(ru, en))
    result = search_for(client, "Some.Movie.2024.1080p")
    assert result["candidates"][0].overview == "a quiet film"


def test_guess_keeps_a_future_number_in_the_title() -> None:
    g = guess("Blade.Runner.2049.2160p.BluRay")
    assert g["query"] == "Blade Runner 2049"
    assert g["year"] == ""


def test_guess_prefers_a_year_that_leaves_a_title() -> None:
    assert guess("2012.2009.BDRip") == {"media": "movie", "query": "2012", "year": "2009"}
    assert guess("1917.2019.1080p") == {"media": "movie", "query": "1917", "year": "2019"}


def test_search_sends_the_year_the_endpoint_expects() -> None:
    seen: list[dict[str, str]] = []

    def fetch(path: str, params: dict[str, str]) -> dict[str, Any]:
        seen.append({"path": path, **params})
        return {"results": []}

    client = TMDb("k", fetch=fetch)
    client.search("x", "movie", year="1999")
    client.search("x", "tv", year="1999")
    client.search("x", "multi", year="1999")
    assert seen[0]["year"] == "1999"
    assert seen[1]["first_air_date_year"] == "1999"
    assert "year" not in seen[2] and "first_air_date_year" not in seen[2]


def test_search_for_drops_the_year_before_the_media_type() -> None:
    calls: list[dict[str, str]] = []

    def fetch(path: str, params: dict[str, str]) -> dict[str, Any]:
        calls.append({"path": path, **params})
        if path == "/search/multi":
            return {"results": [{"id": 1, "title": "T", "overview": "o"}]}
        return {"results": []}

    client = TMDb("k", fetch=fetch)
    result = search_for(client, "Some.Movie.2024.1080p")
    assert [(c["path"], c.get("year", "")) for c in calls] == [
        ("/search/movie", "2024"),
        ("/search/movie", ""),
        ("/search/multi", ""),
    ]
    assert len(result["candidates"]) == 1


def test_readable_accepts_the_scripts_the_library_uses() -> None:
    assert readable("Intouchables")
    assert readable("Даун Хаус")
    assert readable("Amélie 2001!")
    assert not readable("劇場版「鬼滅の刃」")
    assert not readable("기생충")


def test_name_titles_keeps_a_title_the_library_can_carry() -> None:
    ru = {"results": [{"id": 5, "title": "Довод", "original_title": "Tenet", "overview": "x"}]}
    client = TMDb("k", lang="ru-RU", fetch=_by_language(ru, {"results": []}))
    named = client.name_titles(client.search("x"), "x", "movie")
    assert [c.name for c in named] == ["Tenet"]


def test_name_titles_borrows_the_english_name_for_another_script() -> None:
    ru = {"results": [{"id": 5, "title": "Паразиты", "original_title": "기생충", "overview": "x"}]}
    en = {"results": [{"id": 5, "title": "Parasite", "original_title": "기생충", "overview": "x"}]}
    client = TMDb("k", lang="ru-RU", fetch=_by_language(ru, en))
    named = client.name_titles(client.search("x"), "x", "movie")
    assert [c.name for c in named] == ["Parasite"]


def test_name_titles_falls_back_to_the_translated_name() -> None:
    ru = {"results": [{"id": 5, "title": "Паразиты", "original_title": "기생충", "overview": "x"}]}
    client = TMDb("k", lang="ru-RU", fetch=_by_language(ru, {"results": []}))
    named = client.name_titles(client.search("x"), "x", "movie")
    assert [c.name for c in named] == ["Паразиты"]


def test_name_titles_asks_english_only_when_a_title_needs_it() -> None:
    asked: list[str] = []

    def fetch(path: str, params: dict[str, str]) -> Any:
        asked.append(params.get("language", ""))
        return {"results": [{"id": 5, "title": "Tenet", "original_title": "Tenet", "overview": "x"}]}

    client = TMDb("k", lang="ru-RU", fetch=fetch)
    client.name_titles(client.search("x"), "x", "movie")
    assert asked == [""]
