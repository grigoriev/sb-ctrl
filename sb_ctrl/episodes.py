"""Lay a season pack out into ``Show/Season NN/SNNEMM.ext`` (SPEC.md section 7).

Video files are matched to a season and episode by their name; subtitles keep a
language suffix if they carry one; samples and other junk are skipped.
"""

from __future__ import annotations

import re
from pathlib import Path

VIDEO_EXT = {".mkv", ".mp4", ".avi", ".m4v", ".mov", ".ts"}
SUB_EXT = {".srt", ".ass", ".sub"}

_EPISODE = re.compile(r"[Ss](\d{1,2})[Ee](\d{1,2})|(\d{1,2})x(\d{1,2})|\b(\d)(\d\d)\b")
_SUB_LANG = re.compile(r"\.([A-Za-z]{2,3})\.(?:srt|ass|sub)$", re.IGNORECASE)


def parse_episode(name: str) -> tuple[int, int] | None:
    """Return (season, episode) from a filename, or None."""
    match = _EPISODE.search(name)
    if match is None:
        return None
    for season_group, episode_group in ((1, 2), (3, 4), (5, 6)):
        if match.group(season_group):
            return int(match.group(season_group)), int(match.group(episode_group))
    return None


def _sub_lang(name: str) -> str:
    match = _SUB_LANG.search(name)
    return f".{match.group(1).lower()}" if match else ""


def episode_targets(staging_dir: Path, show_dir: str) -> list[tuple[Path, str]]:
    """Map each usable file under ``staging_dir`` to its final path under ``show_dir``."""
    targets: list[tuple[Path, str]] = []
    for path in sorted(staging_dir.rglob("*")):
        if not path.is_file() or "sample" in path.name.lower():
            continue
        episode = parse_episode(path.name)
        if episode is None:
            continue
        season, number = episode
        stem = f"S{season:02d}E{number:02d}"
        suffix = path.suffix.lower()
        if suffix in VIDEO_EXT:
            filename = f"{stem}{suffix}"
        elif suffix in SUB_EXT:
            filename = f"{stem}{_sub_lang(path.name)}{suffix}"
        else:
            continue
        targets.append((path, f"{show_dir}/Season {season:02d}/{filename}"))
    return targets
