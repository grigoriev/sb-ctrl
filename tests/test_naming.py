from __future__ import annotations

import pytest

from sb_pull.config import Config
from sb_pull.naming import root_for_kind, sanitize


def test_sanitize_replaces_and_strips() -> None:
    assert sanitize("A/B: C?*") == "A-B - C"
    assert sanitize("  spaced  ") == "spaced"
    assert sanitize('bad<>|"name') == "badname"


def test_root_for_kind_returns_configured_root() -> None:
    cfg = Config(root_series="/data/series")
    assert root_for_kind(cfg, "series") == "/data/series"


def test_root_for_kind_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="unknown kind"):
        root_for_kind(Config(), "bogus")


def test_root_for_kind_rejects_unconfigured_root() -> None:
    with pytest.raises(ValueError, match="no library root"):
        root_for_kind(Config(), "movie")
