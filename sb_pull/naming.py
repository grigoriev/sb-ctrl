"""Filename helpers. TMDb-based naming arrives in a later phase; for now this is
the shared sanitizer and the kind-to-root mapping (SPEC.md sections 7 and 3).
"""

from __future__ import annotations

from sb_pull.config import Config

KINDS = ("movie", "cartoon", "series", "cartoon_series")

_STRIP = '?*"<>|'


def sanitize(name: str) -> str:
    """Make ``name`` safe for a filesystem path component (SPEC.md section 7)."""
    name = name.replace("/", "-").replace(":", " -")
    for ch in _STRIP:
        name = name.replace(ch, "")
    return name.strip()


def root_for_kind(cfg: Config, kind: str) -> str:
    roots = {
        "movie": cfg.root_movies,
        "cartoon": cfg.root_cartoons,
        "series": cfg.root_series,
        "cartoon_series": cfg.root_cartoon_series,
    }
    if kind not in roots:
        raise ValueError(f"unknown kind: {kind}")
    root = roots[kind]
    if not root:
        raise ValueError(f"no library root configured for kind: {kind}")
    return root
