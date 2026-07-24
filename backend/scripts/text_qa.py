"""Artifact-prevalence report over stored segment text.

Counts segments matching known PDF-extraction artifact classes, per book and
in total — run it before and after a heuristics change (or a diff-backfill)
to see what actually improved:

    docker compose exec -T backend python scripts/text_qa.py            # totals
    docker compose exec -T backend python scripts/text_qa.py --per-book
    docker compose exec -T backend python scripts/text_qa.py --book 38

Patterns deliberately exclude classes that proved to be false-positive-heavy
on this corpus (single-letter words = possessive 's / math variables).
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal  # noqa: E402
from app.models import Book, Segment  # noqa: E402

PATTERNS = [
    ("header+pagenum leak", re.compile(r"[A-Z]{4,}[A-Z ]* {1,3}\d{1,4}\b|\b\d{1,4} {1,3}[A-Z]{4,}")),
    ("ligature leftovers", re.compile(r"[ﬀ-ﬆ]")),
    ("bracket markup", re.compile(r"\[(?:Illustration|Footnote|Greek|Sidenote|Transcriber)", re.I)),
    ("gutenberg residue", re.compile(r"gutenberg", re.I)),
    ("url", re.compile(r"https?://|www\.", re.I)),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.\w")),
    ("citation [n]", re.compile(r"\[\d")),
    ("hyphen-space break", re.compile(r"[a-z]- {1,3}\n?[a-z]")),
    ("underscore emphasis", re.compile(r"(?<![\w])_[^_\n]{1,200}_(?![\w])")),
    ("e.g./i.e. residual", re.compile(r"\b(e\.g\.|i\.e\.)", re.I)),
    ("multi-space", re.compile(r"   ")),
    ("word-per-line salad", re.compile(r"(?:\n[\w'-]{1,12}){6,}\n")),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", type=int, help="restrict to one book id")
    ap.add_argument("--per-book", action="store_true", help="break out per book")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        q = db.query(Segment.book_id, Segment.text)
        if args.book:
            q = q.filter(Segment.book_id == args.book)
        rows = q.all()
        titles = dict(db.query(Book.id, Book.title).all())
    finally:
        db.close()

    total = {label: 0 for label, _ in PATTERNS}
    per_book: dict = {}
    for book_id, text in rows:
        for label, rx in PATTERNS:
            if rx.search(text):
                total[label] += 1
                per_book.setdefault(book_id, {label: 0 for label, _ in PATTERNS})
                per_book[book_id][label] += 1

    n = len(rows)
    print(f"{n} segments scanned\n")
    print(f"{'artifact':<24}{'segments':>9}{'pct':>7}")
    for label, count in sorted(total.items(), key=lambda kv: -kv[1]):
        print(f"{label:<24}{count:>9}{100 * count / max(n, 1):>6.1f}%")

    if args.per_book:
        print()
        for book_id in sorted(per_book):
            counts = {k: v for k, v in per_book[book_id].items() if v}
            title = (titles.get(book_id) or "?")[:34]
            print(f"book {book_id:>3}  {title:<36} " +
                  ", ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])))


if __name__ == "__main__":
    main()
