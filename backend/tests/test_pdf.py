"""Unit tests for the extraction/cleaning/chunking pipeline (services/pdf.py).

Runs under pytest, or standalone (no deps beyond the app's own):

    .venv/bin/python tests/test_pdf.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.pdf import (  # noqa: E402
    CHUNK_SIZE,
    Chunk,
    _chapter_number,
    _clean_title,
    _find_boundaries,
    _is_prose_line,
    _normalize_text,
    _pack_region,
    _segment_chapters,
    _smart_titlecase,
    _split,
    _strip_front_matter,
    looks_scanned,
)

PROSE = (
    "This is a long line of genuine narrative prose used to simulate the "
    "body text of a real book chapter in these tests."
)


# ---------------------------------------------------------------- numbers

def test_chapter_number_arabic_and_roman():
    assert _chapter_number("7") == 7
    assert _chapter_number("IV") == 4
    assert _chapter_number("xii") == 12
    assert _chapter_number("MCMXCIV") == 1994


def test_chapter_number_rejects_non_canonical_and_words():
    # round-trip validation rejects OCR debris and roman-lettered words
    for bad in ("IIII", "VV", "did", "civil", "mill", "IC", ""):
        assert _chapter_number(bad) is None, bad


# ---------------------------------------------------------------- titles

def test_smart_titlecase_keeps_roman_numerals():
    assert _smart_titlecase("CHAPTER II") == "Chapter II"
    out = _smart_titlecase("CHAPTER XIV: OF CIVIL WAR")
    assert "XIV" in out and "Civil" in out


def test_clean_title_strips_period_and_restores_romans():
    assert _clean_title("Chapter Ii.  Concerning   Things.") == (
        "Chapter II. Concerning Things"
    )


# ------------------------------------------------------------ boundaries

def test_running_headers_deduped():
    lines = (
        ["Chapter I. Start"] + [PROSE] * 10
        + ["Chapter I. Start"]  # running header echo
        + [PROSE] * 10
        + ["Chapter II. Next"] + [PROSE] * 10
    )
    boundaries, noise = _find_boundaries(lines)
    assert [t for _, t in boundaries] == ["Chapter I. Start", "Chapter II. Next"]
    assert 11 in noise  # the echo


def test_adjacent_toc_block_filtered_by_body_gap():
    lines = (
        ["Chapter I", "Chapter II", "Chapter III"]  # TOC survivors, no prose between
        + ["Chapter I. Real"] + [PROSE] * 10
        + ["Chapter II. Also Real"] + [PROSE] * 10
    )
    boundaries, _ = _find_boundaries(lines)
    assert [t for _, t in boundaries] == ["Chapter I. Real", "Chapter II. Also Real"]


def test_consecutive_duplicate_titles_keep_last():
    lines = (
        ["Chapter V: Multi Part I", "Chapter V: Multi Part II", "Chapter V: Multi"]
        + [PROSE] * 10
    )
    boundaries, _ = _find_boundaries(lines)
    assert len(boundaries) == 1
    assert boundaries[0][1] == "Chapter V: Multi"


def test_out_of_order_straggler_rejected():
    lines = (
        ["Chapter III. Three"] + [PROSE] * 10
        + ["Chapter I. Straggler"] + [PROSE] * 10
        + ["Chapter IV. Four"] + [PROSE] * 10
    )
    boundaries, _ = _find_boundaries(lines)
    assert [t for _, t in boundaries] == ["Chapter III. Three", "Chapter IV. Four"]


def test_heading_split_across_two_lines_rejoined():
    # Block extraction sometimes yields "FEDERALIST" / "No. 6. Title" on
    # separate lines; the candidate collector rejoins them.
    lines = (
        ["FEDERALIST", "No. 6. Concerning Dangers"] + [PROSE] * 10
        + ["FEDERALIST", "No. 7. More Dangers"] + [PROSE] * 10
    )
    boundaries, _ = _find_boundaries(lines)
    titles = [t for _, t in boundaries]
    assert titles == [
        "FEDERALIST No. 6. Concerning Dangers",
        "FEDERALIST No. 7. More Dangers",
    ], titles


def test_high_toc_straggler_does_not_poison_real_run():
    # Regression (meditations): a garbled TOC survivor ("Book XL") sitting
    # before the real Book I..V run must lose to the run, not suppress it.
    lines = ["Book XL"] + [PROSE] * 10
    for n in ("I", "II", "III", "IV", "V"):
        lines += [f"Book {n}. Real"] + [PROSE] * 10
    boundaries, _ = _find_boundaries(lines)
    titles = [t for _, t in boundaries]
    assert titles == [f"Book {n}. Real" for n in ("I", "II", "III", "IV", "V")], titles


# --------------------------------------------------------------- regions

def test_preface_region_untitled_and_heading_still_narrated():
    doc = "\n".join(
        ["A preface line of real prose long enough to count as narration."] * 3
        + ["Chapter I. Begin"] + [PROSE] * 10
    )
    regions = _segment_chapters(doc)
    assert regions[0][0] is None
    assert regions[1][0] == "Chapter I. Begin"
    assert regions[1][1].startswith("Chapter I. Begin")  # heading line kept


def test_no_chapters_single_region():
    doc = (PROSE + " ") * 50
    regions = _segment_chapters(doc)
    assert len(regions) == 1 and regions[0][0] is None


# --------------------------------------------------------------- packing

def test_chunks_respect_cap_and_first_only_titled():
    regions = [("Chapter I. Big", (PROSE + " ") * 60), (None, PROSE)]
    chunks = _split(regions)
    assert all(len(c.text) <= CHUNK_SIZE for c in chunks)
    titled = [c for c in chunks if c.chapter_title]
    assert len(titled) == 1 and titled[0] is chunks[0]


def test_oversized_single_sentence_hard_split():
    pieces = _pack_region("word " * 2000)  # no sentence boundaries
    assert len(pieces) >= 2
    assert all(len(p) <= CHUNK_SIZE for p in pieces)


def test_no_chunk_spans_regions():
    regions = [("Chapter I", "Short chapter one."), ("Chapter II", "Short chapter two.")]
    chunks = _split(regions)
    assert [c.text for c in chunks] == ["Short chapter one.", "Short chapter two."]
    assert [c.chapter_title for c in chunks] == ["Chapter I", "Chapter II"]


# ------------------------------------------------------------- normalize

def test_normalize_strips_citations_urls_ligatures():
    t = _normalize_text("The ﬁre [12] burns https://x.io brightly e.g. now.")
    assert "fire" in t and "[12]" not in t and "https" not in t
    assert "for example" in t


def test_gutenberg_banners_stripped():
    doc = (
        "Header junk\n***  START  OF  THE  PROJECT  GUTENBERG  EBOOK  X ***\n"
        "Real body prose that should survive intact here.\n"
        "***  END  OF  THE  PROJECT  GUTENBERG  EBOOK  X ***\nLicense junk"
    )
    out = _normalize_text(doc)
    assert "Real body prose" in out
    assert "gutenberg" not in out.lower() and "License junk" not in out


# ---------------------------------------------------------------- scanned

def test_looks_scanned():
    assert looks_scanned(1, 644) is True          # tiny total (modest_proposal)
    assert looks_scanned(144, 272364) is False    # real text layer
    assert looks_scanned(500, 40000) is True      # low chars/page


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
