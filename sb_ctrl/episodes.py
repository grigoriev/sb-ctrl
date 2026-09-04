"""Lay a season pack out into ``Show/Season NN/SNNEMM.ext`` (SPEC.md section 7).

A file says which episode it is in one of three ways, and they are read in
this order: a marked number in its own name (``S01E02``, ``1x02``); a season
from the folder it sits in plus a number the name starts with; or, for an old
release, three joined digits. Subtitles keep a language suffix if they carry
one; samples and other junk are skipped. The recognized extensions and the
skip patterns come from the config.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from sb_ctrl.config import DEFAULT_SKIP_PATTERNS, DEFAULT_SUB_EXT, DEFAULT_VIDEO_EXT

# S01E02, S01.E02, 1x02
_MARKED = re.compile(r"[Ss](\d{1,2})[\s._-]*[Ee](\d{1,3})|\b(\d{1,2})x(\d{1,2})\b")
# 102 for season 1, episode 2: an old convention, and the weakest reading
_JOINED = re.compile(r"\b(\d)(\d\d)\b")
# "S01 - Unwavering Resolve", "Season 2", "Сезон 2", and "S02.1" for a part
_SEASON_FOLDER = re.compile(r"^(?:[Ss]|[Ss]eason\s*|[Сс]езон\s*)(\d{1,2})(?:\.(\d+))?(?!\d)")
# "01 - Cruelty.mp4", "12. Title.mkv"
_LEADING_NUMBER = re.compile(r"^(\d{1,3})(?!\d)")


@dataclass(frozen=True)
class _Found:
    season: int
    part: int
    number: int
    path: Path


def _marked(name: str) -> tuple[int, int] | None:
    match = _MARKED.search(name)
    if match is None:
        return None
    groups = (1, 2) if match.group(1) else (3, 4)
    return int(match.group(groups[0])), int(match.group(groups[1]))


def _joined(name: str) -> tuple[int, int] | None:
    match = _JOINED.search(name)
    return (int(match.group(1)), int(match.group(2))) if match else None


def parse_episode(name: str) -> tuple[int, int] | None:
    """Return (season, episode) from a filename, or None."""
    return _marked(name) or _joined(name)


def season_of(folder: str) -> tuple[int, int] | None:
    """The season a folder names, and which part of it, or None.

    A season split into arcs arrives as ``S02.1`` and ``S02.2``; both are
    season two, and the part says which comes first.
    """
    match = _SEASON_FOLDER.match(folder)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2) or 1)


def ext_set(items: Iterable[str]) -> set[str]:
    """The extensions as a set, each lowercase and with its dot."""
    return {e if e.startswith(".") else f".{e}" for e in (str(i).lower().strip() for i in items)}


def _sub_lang(name: str, sub_ext: Iterable[str]) -> str:
    exts = "|".join(re.escape(e.lstrip(".")) for e in sub_ext)
    match = re.search(rf"\.([A-Za-z]{{2,3}})\.(?:{exts})$", name, re.IGNORECASE)
    return f".{match.group(1).lower()}" if match else ""


def _place(path: Path, folders: tuple[str, ...]) -> _Found | None:
    """Which episode this file is, from its name and the folders above it."""
    season_part = next((s for s in (season_of(f) for f in reversed(folders)) if s), None)
    marked = _marked(path.name)
    if marked:
        return _Found(marked[0], season_part[1] if season_part else 1, marked[1], path)
    leading = _LEADING_NUMBER.match(path.name)
    if season_part and leading:
        return _Found(season_part[0], season_part[1], int(leading.group(1)), path)
    joined = _joined(path.name)
    return _Found(joined[0], 1, joined[1], path) if joined else None


def _renumber(found: list[_Found]) -> list[_Found]:
    """Number a season that arrived in parts as one run of episodes.

    ``S02.1`` holds seven episodes and ``S02.2`` starts again at one. They are
    one season of eighteen, so the second part continues where the first ends.
    """
    seasons = {f.season for f in found if len({g.part for g in found if g.season == f.season}) > 1}
    out = [f for f in found if f.season not in seasons]
    for season in seasons:
        run = sorted((f for f in found if f.season == season), key=lambda f: (f.part, f.number))
        out.extend(_Found(season, 1, number, f.path) for number, f in enumerate(run, 1))
    return out


def episode_targets(
    staging_dir: Path,
    show_dir: str,
    *,
    video_ext: Iterable[str] = DEFAULT_VIDEO_EXT,
    sub_ext: Iterable[str] = DEFAULT_SUB_EXT,
    skip_patterns: Iterable[str] = DEFAULT_SKIP_PATTERNS,
) -> list[tuple[Path, str]]:
    """Map each usable file under ``staging_dir`` to its final path under ``show_dir``."""
    videos = ext_set(video_ext)
    subs = ext_set(sub_ext)
    skips = [p.lower() for p in skip_patterns]
    found: list[_Found] = []
    for path in sorted(staging_dir.rglob("*")):
        lowered = path.name.lower()
        if not path.is_file() or any(pattern in lowered for pattern in skips):
            continue
        if path.suffix.lower() not in videos | subs:
            continue
        place = _place(path, path.relative_to(staging_dir).parts[:-1])
        if place is not None:
            found.append(place)

    targets: list[tuple[Path, str]] = []
    taken: set[str] = set()
    for place in _renumber(found):
        stem = f"S{place.season:02d}E{place.number:02d}"
        suffix = place.path.suffix.lower()
        # a subtitle keeps the language it names, so two of them can live side by side
        language = "" if suffix in videos else _sub_lang(place.path.name, subs)
        filename = f"{stem}{language}{suffix}"
        target = f"{show_dir}/Season {place.season:02d}/{filename}"
        # two files that read as one episode: the second is left where it is,
        # rather than written over the first
        if target in taken:
            continue
        taken.add(target)
        targets.append((place.path, target))
    return sorted(targets, key=lambda pair: pair[1])
