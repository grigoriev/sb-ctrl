"""Lay a season pack out into ``Show/Season NN/SNNEMM.ext`` (SPEC.md section 7).

Video files are matched to a season and episode by their name; subtitles keep a
language suffix if they carry one; samples and other junk are skipped. The
recognized extensions and the skip patterns come from the config.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from sb_ctrl.config import DEFAULT_SKIP_PATTERNS, DEFAULT_SUB_EXT, DEFAULT_VIDEO_EXT

_EPISODE = re.compile(r"[Ss](\d{1,2})[\s._-]*[Ee](\d{1,2})|(\d{1,2})x(\d{1,2})|\b(\d)(\d\d)\b")


def parse_episode(name: str) -> tuple[int, int] | None:
    """Return (season, episode) from a filename, or None."""
    match = _EPISODE.search(name)
    if match is None:
        return None
    for season_group, episode_group in ((1, 2), (3, 4), (5, 6)):
        if match.group(season_group):
            return int(match.group(season_group)), int(match.group(episode_group))
    return None


def _ext_set(items: Iterable[str]) -> set[str]:
    return {e if e.startswith(".") else f".{e}" for e in (str(i).lower().strip() for i in items)}


def _sub_lang(name: str, sub_ext: Iterable[str]) -> str:
    exts = "|".join(re.escape(e.lstrip(".")) for e in sub_ext)
    match = re.search(rf"\.([A-Za-z]{{2,3}})\.(?:{exts})$", name, re.IGNORECASE)
    return f".{match.group(1).lower()}" if match else ""


def episode_targets(
    staging_dir: Path,
    show_dir: str,
    *,
    video_ext: Iterable[str] = DEFAULT_VIDEO_EXT,
    sub_ext: Iterable[str] = DEFAULT_SUB_EXT,
    skip_patterns: Iterable[str] = DEFAULT_SKIP_PATTERNS,
) -> list[tuple[Path, str]]:
    """Map each usable file under ``staging_dir`` to its final path under ``show_dir``."""
    videos = _ext_set(video_ext)
    subs = _ext_set(sub_ext)
    skips = [p.lower() for p in skip_patterns]
    targets: list[tuple[Path, str]] = []
    for path in sorted(staging_dir.rglob("*")):
        lowered = path.name.lower()
        if not path.is_file() or any(pattern in lowered for pattern in skips):
            continue
        episode = parse_episode(path.name)
        if episode is None:
            continue
        season, number = episode
        stem = f"S{season:02d}E{number:02d}"
        suffix = path.suffix.lower()
        if suffix in videos:
            filename = f"{stem}{suffix}"
        elif suffix in subs:
            filename = f"{stem}{_sub_lang(path.name, subs)}{suffix}"
        else:
            continue
        targets.append((path, f"{show_dir}/Season {season:02d}/{filename}"))
    return targets
