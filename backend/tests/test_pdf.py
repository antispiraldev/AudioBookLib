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
    _strip_running_headers,
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


# ------------------------------------------------------- running headers

def test_running_header_with_page_numbers_stripped():
    # Title + varying page number at the top of most pages — the book 14
    # pattern ("BEYOND GOOD AND EVIL 127" landing mid-sentence).
    pages = [
        f"BEYOND GOOD AND EVIL {100 + i}\n{PROSE}\n{PROSE}\n{PROSE}"
        for i in range(10)
    ]
    out = _strip_running_headers(pages)
    assert all("BEYOND GOOD" not in p for p in out)
    assert all(PROSE in p for p in out)


def test_alternating_verso_recto_headers_stripped():
    pages = []
    for i in range(12):
        head = "ORIGIN OF SPECIES" if i % 2 else "THEORY OF NATURAL SELECTION"
        pages.append(f"{i + 40} {head}\n{PROSE}\n{PROSE}")
    out = _strip_running_headers(pages)
    joined = "\n".join(out)
    assert "ORIGIN OF SPECIES" not in joined
    assert "NATURAL SELECTION" not in joined


def test_chapter_headings_never_stripped_as_headers():
    # Digit-stripped chapter lines all normalize to "chapter" — they must be
    # exempt or every chapter heading would vanish.
    pages = [f"Chapter {i + 1}.\n{PROSE}\n{PROSE}" for i in range(10)]
    out = _strip_running_headers(pages)
    assert all("Chapter" in p for p in out)


def test_mid_page_refrain_not_treated_as_header():
    # A poem's short repeated refrain repeats mid-page, not in the top/bottom
    # zone — it must survive (Kalevala regression guard).
    refrain = "Spake the ancient Wainamoinen"
    pages = [
        f"{PROSE}\n{PROSE}\n{refrain}\n{PROSE}\n{PROSE}\n{PROSE}"
        for _ in range(20)
    ]
    out = _strip_running_headers(pages)
    assert all(refrain in p for p in out)


def test_header_stripped_everywhere_once_qualified():
    # Once a key qualifies via the page-edge zone, mid-page occurrences
    # (blocks merged out of order) are dropped too.
    pages = [f"THE PROSE EDDA\n{PROSE}\n{PROSE}" for _ in range(9)]
    pages.append(f"{PROSE}\nTHE PROSE EDDA\n{PROSE}\n{PROSE}")
    out = _strip_running_headers(pages)
    assert all("PROSE EDDA" not in p for p in out)


# ------------------------------------------------------- markup stripping

def test_bracket_markup_stripped_including_nested():
    t = _normalize_text(
        "Prose before. [Illustration: GUNNAR REFUSES TO LEAVE HOME] "
        "More prose. [Footnote 61: See note [Greek: logos] on chapter 28.] "
        "[Sidenote: A.D. 758.] End prose."
    )
    assert "Illustration" not in t and "Footnote" not in t
    assert "Greek" not in t and "Sidenote" not in t
    assert "Prose before." in t and "More prose." in t and "End prose." in t


def test_emphasis_markers_unwrapped():
    t = _normalize_text("He read _Punch_ and the =Thesaurus= that day.")
    assert "_" not in t and "=" not in t
    assert "Punch" in t and "Thesaurus" in t


def test_equations_survive_equals_stripping():
    t = _normalize_text("Where E = mc squared holds, and a = b = c follows.")
    assert "E = mc" in t and "a = b = c" in t


def test_ascii_box_lines_stripped():
    t = _normalize_text(
        "+-------------------------+\n"
        "|Transcriber's Note: junk |\n"
        "+-------------------------+\n"
        + PROSE
    )
    assert "+---" not in t and "|" not in t and PROSE in t


def test_emails_and_arxiv_ids_stripped():
    t = _normalize_text(
        "Ashish Vaswani avaswani@google.com wrote arXiv:1402.0993v1 today."
    )
    assert "@" not in t and "arXiv" not in t
    assert "Ashish Vaswani" in t


def test_index_heading_truncates_tail():
    body = (PROSE + "\n") * 30
    doc = body + "INDEX\nAbacus, i. 414\nBadashan, ii. 3-4\n"
    t = _normalize_text(doc)
    assert "Abacus" not in t and "Badashan" not in t
    # …but only in the tail: a mention early in a long doc survives
    doc2 = "Index\n" + (PROSE + "\n") * 40
    assert "Index" in _normalize_text(doc2)


def test_pg_license_without_end_banner_truncated():
    body = (PROSE + "\n") * 30
    doc = body + "START: FULL LICENSE\nThe Full Project Gutenberg License\n"
    t = _normalize_text(doc)
    assert "FULL LICENSE" not in t and PROSE in t


def test_produced_by_credit_stripped():
    doc = "Produced by An Anonymous Volunteer, and David Widger\n" + (PROSE + "\n") * 20
    t = _normalize_text(doc)
    assert "Widger" not in t and PROSE in t


# -------------------------------------------------------- ebook TOC strip

def test_ebook_toc_run_stripped_without_contents_heading():
    lines = (
        ["DUNE MESSIAH", "FRANK HERBERT", "Cover", "Title"]
        + [f"Chapter {i}" for i in range(1, 25)]
        + ["Epilogue", "Appendix I", "Also by Frank Herbert"]
        + [PROSE] * 40  # enough body for the run to sit in the first ~15%
    )
    out = _strip_front_matter("\n".join(lines))
    assert "Chapter 5" not in out and "Also by" not in out
    assert PROSE in out
    assert "DUNE MESSIAH" in out  # title lines before the run survive


def test_scattered_toc_like_lines_do_not_trigger():
    # Fewer than five consecutive navigation lines is not a TOC
    doc = "\n".join(["Cover", PROSE, "Chapter 1", PROSE, "Epilogue", PROSE * 2])
    assert _strip_front_matter(doc) == doc


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
