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

from app.services.pdf import extract_text_chunks, CHUNK_SIZE  # noqa: E402

SHORT = 120  # chars; below this a body segment is suspiciously stubby

_RESIDUAL_CITATION = re.compile(r"\[\d+(?:[\s,–-]+\d+)*\]")
_RESIDUAL_URL = re.compile(r"https?://|\bdoi:", re.IGNORECASE)
_CAPS_RUN = re.compile(r"\b[A-Z]{4,}(?:\s+[A-Z]{4,}){2,}")
_SPACED_LETTERS = re.compile(r"(?:\b[A-Za-z]\s){4,}")


def _non_text_ratio(s: str) -> float:
    if not s:
        return 1.0
    noise = sum(1 for c in s if not (c.isalnum() or c.isspace() or c in ".,;:'\"!?()—–-"))
    return noise / len(s)


def flags_for(text: str, is_last: bool) -> list[str]:
    flags = []
    n = len(text)
    if n > CHUNK_SIZE:
        flags.append(f"OVER-CAP({n})")
    if n < SHORT and not is_last:
        flags.append(f"STUBBY({n})")
    ratio = _non_text_ratio(text)
    if ratio > 0.12:
        flags.append(f"SYMBOL-HEAVY({ratio:.0%})")
    if _RESIDUAL_CITATION.search(text):
        flags.append("RESIDUAL-CITATION")
    if _RESIDUAL_URL.search(text):
        flags.append("RESIDUAL-URL")
    if _CAPS_RUN.search(text):
        flags.append("CAPS-RUN")
    if _SPACED_LETTERS.search(text):
        flags.append("OCR-SPACING")
    return flags


def preview(pdf_path: str, summary: bool, use_llm: bool) -> dict:
    page_count, chunks = extract_text_chunks(pdf_path)

    if use_llm:
        from app.services.clean import llm_clean
        chunks = [llm_clean(c) for c in chunks]

    lengths = [len(c) for c in chunks]
    n = len(chunks)
    flagged = []
    for i, c in enumerate(chunks):
        f = flags_for(c, is_last=(i == n - 1))
        if f:
            flagged.append((i, f, c))

    name = os.path.basename(pdf_path)
    print(f"\n=== {name} ===")
    print(f"pages: {page_count}   segments: {n}   "
          f"chars: total {sum(lengths):,}  "
          f"min {min(lengths) if lengths else 0}  "
          f"max {max(lengths) if lengths else 0}  "
          f"mean {sum(lengths)//n if n else 0}")
    print(f"flagged: {len(flagged)}/{n}")

    if not summary:
        out_dir = os.path.join(os.path.dirname(__file__), "preview_out")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, name.replace(".pdf", "") + ".txt")
        with open(out_path, "w") as fh:
            for i, c in enumerate(chunks):
                f = flags_for(c, is_last=(i == n - 1))
                tag = ("  ⚠ " + " ".join(f)) if f else ""
                fh.write(f"\n----- segment {i} ({len(c)} chars){tag} -----\n{c}\n")
        print(f"dumped -> {os.path.relpath(out_path)}")

        for i, f, c in flagged[:12]:
            print(f"\n  ⚠ seg {i}  {' '.join(f)}")
            print("    " + re.sub(r"\s+", " ", c[:180]))

    return {"name": name, "pages": page_count, "segments": n, "flagged": len(flagged)}


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
        print(f"{'book':<40} {'pages':>6} {'segs':>6} {'flagged':>8}")
        for r in rows:
            print(f"{r['name'][:40]:<40} {r['pages']:>6} {r['segments']:>6} {r['flagged']:>8}")


if __name__ == "__main__":
    main()
