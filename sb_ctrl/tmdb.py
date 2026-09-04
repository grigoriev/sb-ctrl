"""TMDb client and title guessing (SPEC.md section 6).

Guesses a search query + media type from a torrent name, searches TMDb, and
classifies a chosen result into one of the four kinds. Naming always uses the
original title; a client picks the match and passes it to ``plan``.
"""

from __future__ import annotations

import datetime
import json
import re
import unicodedata
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

TMDB_BASE = "https://api.themoviedb.org/3"
FALLBACK_LANG = "en-US"
# how each search endpoint names the year; /search/multi takes none
_YEAR_PARAM = {"movie": "year", "tv": "first_air_date_year"}
ANIMATION_GENRE = 16

_YEAR = re.compile(r"(19|20)\d{2}")
_EPISODE = re.compile(r"[Ss]\d{1,2}[Ee]\d{1,2}|\b\d{1,2}x\d{1,2}\b")
_SEASON = re.compile(r"\bs\d{1,2}(?:-s?\d{1,2})?\b|\bseason\s*\d{1,2}\b", re.I)
_CONTAINER = re.compile(r"\.(?:mkv|mp4|avi|m4v|mov|ts|wmv|flv)$", re.I)

# release tags; everything from the first one is noise, not part of the title
_TAG = re.compile(
    r"\b(?:"
    r"\d{3,4}[pi]|4k|uhd|hdr10?|sdr"
    r"|web[- ]?dl|web[- ]?rip|bd[- ]?rip|br[- ]?rip|blu[- ]?ray|bd[- ]?remux|remux"
    r"|dvd[- ]?rip|hd[- ]?tv|hd[- ]?rip|cam[- ]?rip|tv[- ]?rip|sat[- ]?rip|vhs[- ]?rip"
    r"|[xh][- ]?26[45]|hevc|avc|xvid|divx|\d{1,2}bit"
    r"|dts(?:[- ]?hd)?|e?ac3|dd[p+]?\s?\d(?:\s\d)?|aac|flac|atmos|true[- ]?hd|opus"
    r"|proper|repack|extended|unrated|remastered|dubbed|subbed"
    r")\b",
    re.I,
)

FetchFn = Callable[[str, dict[str, str]], dict[str, Any]]


POSTER_BASE = "https://image.tmdb.org/t/p/w154"


def readable(text: str) -> bool:
    """Whether a title is written in a script this library is written in.

    The library is named in Latin and Cyrillic. A title in Japanese or Hindi
    is correct but unreadable here, and a folder nobody can type is worse
    than one named after the same film in English.
    """
    return all(not ch.isalpha() or unicodedata.name(ch, "").startswith(("LATIN", "CYRILLIC")) for ch in text)


@dataclass(frozen=True)
class Candidate:
    tmdb_id: int
    media: str
    title: str
    original_title: str
    year: str
    overview: str
    is_animation: bool
    poster: str = ""
    # what the library should call it; see ``name_titles``
    name: str = ""

    @property
    def kind(self) -> str:
        if self.media == "tv":
            return "cartoon_series" if self.is_animation else "series"
        return "cartoon" if self.is_animation else "movie"


def _plausible_year(text: str) -> re.Match[str] | None:
    """The first four digit run a release could actually be dated by.

    A title carries numbers too: "Blade Runner 2049" is not from 2049. Anything
    past next year is part of the name, not the year of release, and a year
    that would leave no title at all is the name itself.
    """
    limit = datetime.date.today().year + 1
    matches = [m for m in _YEAR.finditer(text) if int(m.group(0)) <= limit]
    # a title can be a year ("2012"), so prefer a match that leaves a name behind
    return next((m for m in matches if text[: m.start()].strip(" -")), matches[0] if matches else None)


def _cut_at(text: str, pattern: re.Pattern[str]) -> str:
    """Drop everything from the first match of ``pattern``."""
    match = pattern.search(text)
    return text[: match.start()] if match else text


def guess(name: str) -> dict[str, str]:
    """Guess the media type, a clean search query, and the year from a torrent name.

    A season marker without an episode (``S01``) still means TV, and the query
    keeps only what precedes the first episode, season, year or release tag.
    """
    stripped = _CONTAINER.sub("", name)
    media = "tv" if _EPISODE.search(stripped) or _SEASON.search(stripped) else "movie"
    cleaned = stripped.replace(".", " ").replace("_", " ")
    cleaned = _cut_at(cleaned, _EPISODE)
    cleaned = _cut_at(cleaned, _SEASON)
    year_match = _plausible_year(cleaned)
    year = year_match.group(0) if year_match else ""
    if year_match:
        cleaned = cleaned[: year_match.start()]
    cleaned = _cut_at(cleaned, _TAG)
    cleaned = re.sub(r"[\[\](){}]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
    return {"media": media, "query": cleaned, "year": year}


class TMDb:
    def __init__(self, key: str, lang: str = "en-US", fetch: FetchFn | None = None) -> None:
        self._key = key
        self._lang = lang
        self._fetch: FetchFn = fetch or self._http_get

    def _http_get(self, path: str, params: dict[str, str]) -> dict[str, Any]:  # pragma: no cover - network
        # language first, so a caller can ask for another one
        query = urllib.parse.urlencode({"language": self._lang, **params, "api_key": self._key})
        with urllib.request.urlopen(f"{TMDB_BASE}{path}?{query}", timeout=8) as response:  # noqa: S310
            data: dict[str, Any] = json.loads(response.read())
        return data

    def search(self, query: str, media: str = "multi", lang: str = "", year: str = "") -> list[Candidate]:
        params = {"query": query}
        if lang:
            params["language"] = lang
        year_param = _YEAR_PARAM.get(media)
        if year and year_param:
            params[year_param] = year
        data = self._fetch(f"/search/{media}", params)
        results = data.get("results", [])
        return [self._candidate(r) for r in results if _usable(r)]

    def name_titles(self, candidates: list[Candidate], query: str, media: str) -> list[Candidate]:
        """Give each candidate the name the library should use.

        The original title comes first, because that is what the library is
        named by. When it is written in another script, the English catalogue
        names the same film in a way this library can carry. One extra
        request, and only when a title needs it.
        """
        named = [replace(c, name=c.original_title) for c in candidates if readable(c.original_title)]
        foreign = [c for c in candidates if not readable(c.original_title)]
        if not foreign:
            return named if len(named) == len(candidates) else candidates
        english = {c.tmdb_id: c.title for c in self.search(query, media, lang=FALLBACK_LANG)}
        by_id = {c.tmdb_id: replace(c, name=english.get(c.tmdb_id) or c.title or c.original_title) for c in foreign}
        by_id.update({c.tmdb_id: c for c in named})
        return [by_id[c.tmdb_id] for c in candidates]

    def fill_overviews(self, candidates: list[Candidate], query: str, media: str) -> list[Candidate]:
        """Fill an empty overview from the English catalogue.

        TMDb has no translated overview for every title, and a card with no
        text is worse than one in English. Costs one extra request, and only
        when something is actually missing.
        """
        if self._lang == FALLBACK_LANG:
            return candidates
        english = {c.tmdb_id: c.overview for c in self.search(query, media, lang=FALLBACK_LANG)}
        return [c if c.overview else replace(c, overview=english.get(c.tmdb_id, "")) for c in candidates]

    def _candidate(self, r: dict[str, Any]) -> Candidate:
        media = r.get("media_type") or ("tv" if "first_air_date" in r else "movie")
        title = r.get("title") or r.get("name") or ""
        original = r.get("original_title") or r.get("original_name") or title
        date = r.get("release_date") or r.get("first_air_date") or ""
        genres = r.get("genre_ids") or []
        return Candidate(
            tmdb_id=int(r["id"]),
            media=str(media),
            title=str(title),
            original_title=str(original),
            year=str(date)[:4],
            overview=str(r.get("overview", "")),
            is_animation=ANIMATION_GENRE in genres,
            poster=_poster(r.get("poster_path")),
        )


def _poster(path: Any) -> str:
    """The full poster URL, or an empty string when the title has no image."""
    return f"{POSTER_BASE}{path}" if path else ""


def _usable(r: dict[str, Any]) -> bool:
    if r.get("media_type") in ("person",):
        return False
    return bool(r.get("id") and (r.get("title") or r.get("name")))


def search_for(client: TMDb, name: str) -> dict[str, Any]:
    """Guess from a torrent name and search, then patch the gaps.

    The year narrows the search when the name carries one. Both it and the
    guessed media type are only guesses, so an empty result drops the year
    first, then the media type, before the caller reports no matches. A
    missing overview falls back to English.
    """
    hint = guess(name)
    query = hint["query"] or name
    media = hint["media"]
    candidates = client.search(query, media, year=hint["year"])
    if not candidates and hint["year"]:
        candidates = client.search(query, media)
    if not candidates:
        media = "multi"
        candidates = client.search(query, media)
    if any(not c.overview for c in candidates):
        candidates = client.fill_overviews(candidates, query, media)
    candidates = client.name_titles(candidates, query, media)
    return {"guess": hint, "candidates": candidates}
