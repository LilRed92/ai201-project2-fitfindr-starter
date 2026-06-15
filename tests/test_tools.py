"""
Tests for the three FitFindr tools, run in isolation before any agent wiring.

The styling tools (suggest_outfit, create_fit_card) make real Groq API calls,
so these tests need GROQ_API_KEY set in .env and a network connection.
"""

import os
import sys

# Make the project root importable so `tools` and `utils` resolve when pytest
# runs from the tests/ directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


def _a_listing():
    """Grab a real listing to feed into the styling tools."""
    results = search_listings("vintage graphic tee", size="M", max_price=30.0)
    return results[0]


# ── search_listings ──────────────────────────────────────────────────

def test_search_reasonable_query_returns_results():
    results = search_listings("vintage graphic tee", size="M", max_price=30.0)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_impossible_query_returns_empty():
    results = search_listings("designer ballgown", size="XXS", max_price=5.0)
    assert results == []


def test_search_max_price_filter():
    results = search_listings("vintage", size=None, max_price=25.0)
    assert len(results) > 0
    assert all(item["price"] <= 25.0 for item in results)


def test_search_none_filters_ok():
    results = search_listings("vintage", size=None, max_price=None)
    assert isinstance(results, list)
    assert len(results) > 0


# ── suggest_outfit ───────────────────────────────────────────────────

def test_suggest_with_example_wardrobe_returns_string():
    out = suggest_outfit(_a_listing(), get_example_wardrobe())
    assert isinstance(out, str)
    assert len(out.strip()) > 0


def test_suggest_with_empty_wardrobe_returns_message():
    out = suggest_outfit(_a_listing(), get_empty_wardrobe())
    assert isinstance(out, str)
    assert len(out.strip()) > 0


def test_suggest_references_the_item():
    item = _a_listing()
    out = suggest_outfit(item, get_example_wardrobe()).lower()
    tokens = item["title"].lower().split()
    tokens += [t.lower() for t in item["style_tags"]]
    tokens += [c.lower() for c in item["colors"]]
    assert any(tok in out for tok in tokens)


# ── create_fit_card ──────────────────────────────────────────────────

_OUTFIT = "the tee with baggy dark-wash jeans and chunky white sneakers"


def test_fit_card_valid_returns_string():
    card = create_fit_card(_OUTFIT, _a_listing())
    assert isinstance(card, str)
    assert len(card.strip()) > 0


def test_fit_card_empty_outfit_returns_message():
    card = create_fit_card("", _a_listing())
    assert isinstance(card, str)
    assert len(card.strip()) > 0


def test_fit_card_varies():
    item = _a_listing()
    a = create_fit_card(_OUTFIT, item)
    b = create_fit_card(_OUTFIT, item)
    assert a != b
