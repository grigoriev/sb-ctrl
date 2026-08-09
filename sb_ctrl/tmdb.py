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

FetchFn = Callable[[str, dict[str, str]], dict[str, Any]]


@dataclass(frozen=True)
class Candidate:
    tmdb_id: int
    media: str
    title: str
    original_title: str
    year: str
    overview: str
    is_animation: bool

    @property
    def kind(self) -> str:
        if self.media == "tv":
            return "cartoon_series" if self.is_animation else "series"
        return "cartoon" if self.is_animation else "movie"


def guess(name: str) -> dict[str, str]:
    """Guess the media type, a clean search query, and the year from a torrent name."""
    media = "tv" if _EPISODE.search(name) else "movie"
    cleaned = name.replace(".", " ").replace("_", " ")
    cleaned = _EPISODE.split(cleaned)[0]
    year_match = _YEAR.search(cleaned)
    year = year_match.group(0) if year_match else ""
    if year_match:
        cleaned = cleaned[: year_match.start()]
    cleaned = re.sub(r"[\[\](){}]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
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
        )


def _usable(r: dict[str, Any]) -> bool:
    if r.get("media_type") in ("person",):
        return False
    return bool(r.get("id") and (r.get("title") or r.get("name")))
