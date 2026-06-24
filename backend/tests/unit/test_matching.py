from __future__ import annotations

import pytest

from app.ml.matching import find_exact_duplicates, fuzzy_match, name_similarity, normalize_name


@pytest.mark.unit
def test_normalize_drops_suffix_and_punctuation():
    assert normalize_name("AtlasClient 0001, Ltd.") == "atlasclient 0001"
    assert normalize_name("Foo  GmbH") == "foo"


@pytest.mark.unit
def test_similar_names_score_high():
    assert name_similarity("AtlasClient 0001 Ltd", "AtlasClient 0001 Inc") > 0.9
    assert name_similarity("Acme Corp", "Globex Co") < 0.5


@pytest.mark.unit
def test_find_exact_duplicates():
    dups = find_exact_duplicates([("p1", "k"), ("p2", "k"), ("p3", "other")])
    assert len(dups) == 1
    assert dups[0].ids == ["p1", "p2"]


@pytest.mark.unit
def test_fuzzy_match_threshold():
    candidates = [("c1", "AtlasClient 0001 Ltd"), ("c2", "Totally Different SAS")]
    matches = fuzzy_match("AtlasClient 0001 Inc", candidates, threshold=0.8)
    assert matches and matches[0][0] == "c1"
