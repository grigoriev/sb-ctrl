"""TMDb client and title guessing (SPEC.md section 6).

Guesses a search query + media type from a torrent name, searches TMDb, and
classifies a chosen result into one of the four kinds. Naming always uses the
original title; a client picks the match and passes it to ``plan``.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

TMDB_BASE = "https://api.themoviedb.org/3"
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

    @property
    def kind(self) -> str:
        if self.media == "tv":
            return "cartoon_series" if self.is_animation else "series"
        return "cartoon" if self.is_animation else "movie"


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
    year_match = _YEAR.search(cleaned)
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
        query = urllib.parse.urlencode({**params, "api_key": self._key, "language": self._lang})
        with urllib.request.urlopen(f"{TMDB_BASE}{path}?{query}", timeout=8) as response:  # noqa: S310
            data: dict[str, Any] = json.loads(response.read())
        return data

    def search(self, query: str, media: str = "multi") -> list[Candidate]:
        data = self._fetch(f"/search/{media}", {"query": query})
        results = data.get("results", [])
        return [self._candidate(r) for r in results if _usable(r)]

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
    """Guess from a torrent name and search; retry across media types when empty.

    The guessed media type is only a guess, so an empty typed search falls back
    to ``multi`` before the caller reports no matches.
    """
    hint = guess(name)
    query = hint["query"] or name
    candidates = client.search(query, hint["media"])
    if not candidates:
        candidates = client.search(query, "multi")
    return {"guess": hint, "candidates": candidates}
