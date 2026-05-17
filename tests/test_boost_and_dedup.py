"""Tests for graph-boost (no-saturation) and md/graph dedup logic."""

from __future__ import annotations

import pytest

from app.rag.retriever import (
    DEDUP_TOKEN_OVERLAP_THRESHOLD,
    GRAPH_BOOST,
    boost_score,
    _jaccard,
    _tokens,
)


def test_boost_score_preserves_ordering() -> None:
    """The whole point of the new boost: preserves ranking among boosted items."""
    a = boost_score(0.95, 0.25)
    b = boost_score(0.60, 0.25)
    c = boost_score(0.30, 0.25)
    assert a > b > c, f"Ranking not preserved: a={a}, b={b}, c={c}"
    # And no saturation
    assert a < 1.0 - 1e-6


def test_boost_score_strict_increase() -> None:
    base = 0.7
    assert boost_score(base, 0.0) == pytest.approx(base)
    assert boost_score(base, 0.25) > base
    # Boost amount stays in (0, 1-base]
    assert boost_score(base, 0.5) - base <= (1.0 - base) + 1e-9


def test_boost_score_clamps_extremes() -> None:
    # Negative or >1 inputs are clamped to [0, 1]
    assert 0.0 <= boost_score(-0.5, 0.25) < 1.0
    assert boost_score(2.0, 0.25) == pytest.approx(1.0)


def test_boost_constant_in_use_is_sane() -> None:
    assert 0.0 < GRAPH_BOOST < 0.6


def test_tokens_basic() -> None:
    s = _tokens("Облигация — долговая ценная бумага: купон 10% годовых.")
    assert "облигация" in s
    assert "долговая" in s
    assert "купон" in s
    assert "10" not in s  # too short (3 minimum)


def test_jaccard_identity() -> None:
    a = {"x", "y", "z"}
    assert _jaccard(a, a) == 1.0
    assert _jaccard(a, set()) == 0.0
    assert _jaccard(a, {"x"}) == pytest.approx(1 / 3)


def test_dedup_threshold_constant_is_sane() -> None:
    assert 0.4 < DEDUP_TOKEN_OVERLAP_THRESHOLD < 0.95
