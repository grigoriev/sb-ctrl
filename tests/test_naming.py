from __future__ import annotations

import pytest

from sb_ctrl.config import Config
from sb_ctrl.naming import root_for_kind, sanitize


def test_sanitize_only_takes_out_the_separator() -> None:
    assert sanitize("A/B") == "A-B"
    assert sanitize("  spaced  ") == "spaced"


def test_sanitize_keeps_the_punctuation_of_a_title() -> None:
    assert sanitize("Demon Slayer: Kimetsu no Yaiba") == "Demon Slayer: Kimetsu no Yaiba"
    assert sanitize("Who Framed Roger Rabbit?") == "Who Framed Roger Rabbit?"
    assert sanitize("WALL·E") == "WALL·E"


def test_sanitize_leaves_no_name_a_folder_cannot_end_with() -> None:
    assert sanitize("Trailing dot.") == "Trailing dot"
    assert sanitize("Two  spaces") == "Two spaces"


def test_root_for_kind_returns_configured_root() -> None:
    cfg = Config(root_series="/data/series")
    assert root_for_kind(cfg, "series") == "/data/series"


def test_root_for_kind_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="unknown kind"):
        root_for_kind(Config(), "bogus")


def test_root_for_kind_rejects_unconfigured_root() -> None:
    with pytest.raises(ValueError, match="no library root"):
        root_for_kind(Config(), "movie")
