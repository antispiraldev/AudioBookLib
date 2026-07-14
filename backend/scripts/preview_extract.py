"""Local preprocessing harness — inspect extraction/cleaning quality for FREE.

Runs the real pdf.py pipeline (heuristic cleaning; NO OpenAI by default) on a
PDF and reports segment stats + auto-flagged suspicious segments, and dumps the
cleaned segments to a text file so you can read them before spending TTS credits.

    cd backend
    .venv/bin/python scripts/preview_extract.py storage/pdfs/engelbart_augmenting.pdf
    .venv/bin/python scripts/preview_extract.py storage/pdfs/*.pdf --summary
    .venv/bin/python scripts/preview_extract.py storage/pdfs/the_prince.pdf --llm  # costs cents

Flags a segment as SUSPICIOUS when it looks like an artifact slipped through:
stubby, over the TTS cap, symbol/digit-heavy, residual [n] citations or URLs,
OCR letter-spacing, or long ALL-CAPS runs.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.pdf import extract_text_chunks, looks_scanned, CHUNK_SIZE  # noqa: E402

SHORT = 120  # chars; below this a body segment is suspiciously stubby

_RESIDUAL_CITATION = re.compile(r"\[\d+(?:[\s,–-]+\d+)*\]")
_RESIDUAL_URL = re.compile(r"https?://|\bdoi:", re.IGNORECASE)
_SPACED_LETTERS = re.compile(r"(?:\b[A-Za-z]\s){4,}")
_GUTENBERG_RESIDUE = re.compile(r"project gutenberg", re.IGNORECASE)


def _non_text_ratio(s: str) -> float:
    if not s:
        return 1.0
    noise = sum(1 for c in s if not (c.isalnum() or c.isspace() or c in ".,;:'\"!?()—–-"))
    return noise / len(s)


def _short_token_ratio(s: str) -> float:
    """Fraction of 1-2 char alpha tokens — high means OCR letter-spacing/garble."""
    toks = [t for t in s.split() if any(c.isalpha() for c in t)]
    if not toks:
        return 0.0
    return sum(1 for t in toks if len(t) <= 2) / len(toks)


def flags_for(text: str, is_last: bool) -> list[str]:
    # Note: CAPS-RUN was dropped — it fired on names/emphasis (PUBLIUS, QUEEN
    # ANNE) that modern TTS reads fine, drowning out real artifacts.
    flags = []
    n = len(text)
    if n > CHUNK_SIZE:
        flags.append(f"OVER-CAP({n})")
    if n < SHORT and not is_last:
        flags.append(f"STUBBY({n})")
    ratio = _non_text_ratio(text)
    if ratio > 0.12:
        flags.append(f"SYMBOL-HEAVY({ratio:.0%})")
    stok = _short_token_ratio(text)
    if stok > 0.30:
        flags.append(f"GIBBERISH({stok:.0%})")
    if _RESIDUAL_CITATION.search(text):
        flags.append("RESIDUAL-CITATION")
    if _RESIDUAL_URL.search(text):
        flags.append("RESIDUAL-URL")
    if _GUTENBERG_RESIDUE.search(text):
        flags.append("GUTENBERG-RESIDUE")
    if _SPACED_LETTERS.search(text):
        flags.append("OCR-SPACING")
    return flags


def preview(pdf_path: str, summary: bool, use_llm: bool) -> dict:
    page_count, chunks = extract_text_chunks(pdf_path)

    if use_llm:
        from app.services.clean import llm_clean
        chunks = [c._replace(text=llm_clean(c.text)) for c in chunks]

    lengths = [len(c.text) for c in chunks]
    n = len(chunks)
    chapters = [c.chapter_title for c in chunks if c.chapter_title]
    flagged = []
    for i, c in enumerate(chunks):
        f = flags_for(c.text, is_last=(i == n - 1))
        if f:
            flagged.append((i, f, c.text))

    name = os.path.basename(pdf_path)
    total_chars = sum(lengths)
    per_page = total_chars // page_count if page_count else total_chars
    scanned = looks_scanned(page_count, total_chars)
    print(f"\n=== {name} ===")
    print(f"pages: {page_count}   segments: {n}   chapters: {len(chapters)}   "
          f"chars: total {total_chars:,}  "
          f"min {min(lengths) if lengths else 0}  "
          f"max {max(lengths) if lengths else 0}  "
          f"mean {sum(lengths)//n if n else 0}   "
          f"chars/page {per_page}")
    if scanned:
        print("  ⚠⚠ LIKELY SCANNED — no usable text layer, needs OCR")
    print(f"flagged: {len(flagged)}/{n}")
    if chapters and not summary:
        print("chapters:")
        for t in chapters[:40]:
            print(f"   {t[:70]}")
        if len(chapters) > 40:
            print(f"   ... and {len(chapters) - 40} more")

    if not summary:
        out_dir = os.path.join(os.path.dirname(__file__), "preview_out")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, name.replace(".pdf", "") + ".txt")
        with open(out_path, "w") as fh:
            for i, c in enumerate(chunks):
                f = flags_for(c.text, is_last=(i == n - 1))
                tag = ("  ⚠ " + " ".join(f)) if f else ""
                if c.chapter_title:
                    fh.write(f"\n========== {c.chapter_title} ==========\n")
                fh.write(f"\n----- segment {i} ({len(c.text)} chars){tag} -----\n{c.text}\n")
        print(f"dumped -> {os.path.relpath(out_path)}")

        for i, f, ctext in flagged[:12]:
            print(f"\n  ⚠ seg {i}  {' '.join(f)}")
            print("    " + re.sub(r"\s+", " ", ctext[:180]))

    return {"name": name, "pages": page_count, "segments": n, "chapters": len(chapters),
            "flagged": len(flagged), "per_page": per_page, "scanned": scanned}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--summary", action="store_true", help="one line per PDF, no dump")
    ap.add_argument("--llm", action="store_true", help="also run the gpt-4o-mini polish (costs cents)")
    args = ap.parse_args()

    rows = []
    for p in args.pdfs:
        try:
            rows.append(preview(p, args.summary, args.llm))
        except Exception as e:
            print(f"\n=== {os.path.basename(p)} ===\n  ERROR: {e}")

    if len(rows) > 1:
        print("\n\n=== SUMMARY ===")
        print(f"{'book':<40} {'pages':>6} {'segs':>6} {'chaps':>6} {'flagged':>8} {'ch/pg':>7}  note")
        for r in rows:
            note = "SCANNED — needs OCR" if r.get("scanned") else ""
            print(f"{r['name'][:40]:<40} {r['pages']:>6} {r['segments']:>6} "
                  f"{r.get('chapters', 0):>6} {r['flagged']:>8} {r.get('per_page', 0):>7}  {note}")


if __name__ == "__main__":
    main()
