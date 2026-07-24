"""Unit tests for segment alignment (services/diff.py).

Runs under pytest, or standalone:

    .venv/bin/python tests/test_diff.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.diff import align_texts  # noqa: E402

# Long enough that one small edit stays above any plausible fuzzy threshold
# while a removed header (25+ chars) falls below it.
BASE = (
    "It is a truth universally acknowledged, that a single man in possession "
    "of a good fortune, must be in want of a wife. However little known the "
    "feelings or views of such a man may be on his first entering a "
    "neighbourhood, this truth is so well fixed in the minds of the "
    "surrounding families, that he is considered as the rightful property "
    "of some one or other of their daughters. "
) * 4


def _chunks(n):
    return [f"{BASE} Distinct trailing sentence number {i}." for i in range(n)]


def test_identical_lists_map_one_to_one():
    texts = _chunks(5)
    assert align_texts(texts, texts) == [0, 1, 2, 3, 4]


def test_whitespace_jitter_is_same():
    old = _chunks(3)
    new = [t.replace("  ", " ").replace(" ", "  ", 3) for t in old]
    assert align_texts(old, new) == [0, 1, 2]


def test_inserted_chunk_shifts_alignment():
    old = _chunks(4)
    new = old[:2] + ["A brand new chunk of totally different text."] + old[2:]
    assert align_texts(old, new) == [0, 1, None, 2, 3]


def test_deleted_chunk_is_retired():
    old = _chunks(4)
    new = old[:1] + old[2:]
    mapping = align_texts(old, new)
    assert mapping == [0, 2, 3]
    assert 1 not in mapping  # old chunk 1 unclaimed → retire


def test_removed_header_counts_as_changed():
    old = _chunks(3)
    new = list(old)
    # Simulate the fix we backfill for: a running header leaves chunk 1
    new[1] = old[1].replace("However little known", "")
    mapping = align_texts(old, new)
    assert mapping[0] == 0 and mapping[2] == 2
    assert mapping[1] is None  # must re-synthesize


def test_tiny_single_char_difference_is_same():
    old = _chunks(2)
    new = [old[0].replace("ﬁ", "fi") if "ﬁ" in old[0] else old[0] + ".", old[1]]
    mapping = align_texts(old, new)
    assert mapping == [0, 1]


def test_empty_lists():
    assert align_texts([], []) == []
    assert align_texts([], ["new text"]) == [None]
    assert align_texts(["old text"], []) == []


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if failures else 0)
