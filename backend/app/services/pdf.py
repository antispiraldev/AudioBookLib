import re
import unicodedata
from collections import Counter
from typing import List

import fitz  # PyMuPDF

CHUNK_SIZE = 3500  # safe under OpenAI's 4096-char TTS limit

# A text-layer PDF yields ~1500-3000 chars/page; a scanned/image PDF yields
# almost none. Below this we assume no usable text layer (needs OCR).
MIN_CHARS_PER_PAGE = 200
# Whole-document floor: even a short essay extracts to more than this. Below it
# the text layer is effectively dead (also catches PDFs whose page count itself
# extracts wrong, e.g. a multi-page scan reported as one page).
MIN_TOTAL_CHARS = 1500


def looks_scanned(page_count: int, total_chars: int) -> bool:
    """True if extraction yielded too little text to be a real text layer."""
    if total_chars < MIN_TOTAL_CHARS:
        return True
    if page_count <= 0:
        return False
    return total_chars / page_count < MIN_CHARS_PER_PAGE


def _is_prose_line(line: str) -> bool:
    """A real body line: long, mixed-case, not page-number-heavy.

    Extraction emits one line per source line (not per paragraph), so we can't
    rely on sentence-ending punctuation. Instead: length + lowercase presence +
    sparse standalone numbers, and it must not end on a page number.
    """
    s = line.strip()
    if len(s) < 60 or not any(c.islower() for c in s):
        return False
    if s[-1].isdigit():
        return False
    return len(_STANDALONE_NUM_RE.findall(s)) <= 1


def _strip_front_matter(text: str) -> str:
    """Drop a leading table-of-contents / list-of-illustrations block.

    Conservative: only fires when a 'Contents' heading appears near the top and
    a run of real body prose is found after it; otherwise the text is untouched.
    """
    lines = text.split("\n")
    limit = max(1, len(lines) // 6)  # front matter lives in the first ~15%
    contents_idx = next(
        (i for i, ln in enumerate(lines[:limit]) if _CONTENTS_HEADING_RE.match(ln)),
        None,
    )
    if contents_idx is None:
        return text

    # Find where the body starts: the first of two consecutive prose lines.
    body_start = None
    run_start = None
    run = 0
    for i in range(contents_idx + 1, len(lines)):
        if _is_prose_line(lines[i]):
            if run == 0:
                run_start = i
            run += 1
            if run >= 2:
                body_start = run_start
                break
        else:
            run = 0
    if body_start is None:
        return text  # couldn't confidently locate the body — don't cut

    return "\n".join(lines[:contents_idx] + lines[body_start:])

# Bracketed numeric citation markers: [12], [12, 15], [12–14]
_CITATION_RE = re.compile(r"\[\d+(?:\s*[,–-]\s*\d+)*\]")
# URLs and bare DOIs, which TTS reads out character by character
_URL_RE = re.compile(r"https?://\S+|\bdoi:\s*\S+|\b10\.\d{4,}/\S+", re.IGNORECASE)
# Project Gutenberg wraps the actual text in standard START/END banners, with a
# metadata header before and the full legal license after — all of which would
# otherwise be read aloud.
_GUTENBERG_START = re.compile(
    r"\*\*\*\s*START\s+OF\s+TH(?:E|IS)\s+PROJECT\s+GUTENBERG.*?\*\*\*",
    re.IGNORECASE | re.DOTALL,
)
_GUTENBERG_END = re.compile(
    r"\*\*\*\s*END\s+OF\s+TH(?:E|IS)\s+PROJECT\s+GUTENBERG.*?\*\*\*",
    re.IGNORECASE | re.DOTALL,
)

# A line that is nothing but a references/bibliography heading
_REFS_HEADING_RE = re.compile(
    r"(?im)^\s*(references|bibliography|works cited)\.?\s*$"
)
# A "Contents" / "Table of Contents" heading line (heading formatting may have
# title-cased it and appended a period).
_CONTENTS_HEADING_RE = re.compile(r"(?i)^\s*(table\s+of\s+)?contents\.?\s*$")
# Standalone integers, used to spot page-number-dense table-of-contents lines.
_STANDALONE_NUM_RE = re.compile(r"\b\d{1,3}\b")
# Abbreviations that TTS mishandles → spoken-form expansions. Applied before
# sentence splitting so their internal periods don't create false boundaries.
_ABBREVIATIONS = [
    (re.compile(r"\be\.g\.", re.IGNORECASE), "for example"),
    (re.compile(r"\bi\.e\.", re.IGNORECASE), "that is"),
    (re.compile(r"\bet al\.", re.IGNORECASE), "and colleagues"),
    (re.compile(r"\bcf\.", re.IGNORECASE), "compare"),
    (re.compile(r"\bFig\.", re.IGNORECASE), "Figure"),
    (re.compile(r"\bvs\.", re.IGNORECASE), "versus"),
]

# Fraction of page height treated as header/footer zone
MARGIN_FRACTION = 0.08
# Block font size thresholds relative to body size
HEADING_RATIO = 1.2   # larger than body → heading
FOOTNOTE_RATIO = 0.85  # smaller than body in lower page → footnote


def extract_text_chunks(pdf_path: str) -> tuple[int, List[str]]:
    doc = fitz.open(pdf_path)
    page_count = len(doc)
    pages_text = [_extract_page(page) for page in doc]
    doc.close()
    full_text = "\n\n".join(t for t in pages_text if t)
    # Some PDFs yield NUL characters, which Postgres rejects in text columns
    full_text = full_text.replace("\x00", "")
    full_text = _normalize_text(full_text)
    return page_count, _split(full_text)


def _normalize_text(text: str) -> str:
    """Heuristic cleanup so the narration reads naturally and drops artifacts."""
    # Normalize ligatures (ﬁ/ﬂ), smart quotes, and exotic dashes to plain ASCII-ish
    text = unicodedata.normalize("NFKC", text)

    # Strip Project Gutenberg header (before START) and license (after END)
    start = _GUTENBERG_START.search(text)
    if start:
        text = text[start.end():]
    end = _GUTENBERG_END.search(text)
    if end:
        text = text[: end.start()]

    # Drop a leading table-of-contents / list-of-illustrations block
    text = _strip_front_matter(text)

    # Drop a trailing references/bibliography section, but only when it appears
    # in the last ~30% of the document so a mid-body mention isn't cut.
    for match in _REFS_HEADING_RE.finditer(text):
        if match.start() >= len(text) * 0.7:
            text = text[: match.start()]
            break

    text = _CITATION_RE.sub("", text)
    text = _URL_RE.sub("", text)
    for pattern, replacement in _ABBREVIATIONS:
        text = pattern.sub(replacement, text)

    return text


def _extract_page(page: fitz.Page) -> str:
    data = page.get_text("dict")
    page_h = data["height"]
    header_zone = page_h * MARGIN_FRACTION
    footer_zone = page_h * (1 - MARGIN_FRACTION)

    # Find the body font size: most common rounded size across all spans
    all_sizes = [
        round(span["size"])
        for block in data["blocks"] if block["type"] == 0
        for line in block["lines"]
        for span in line["spans"]
        if span["text"].strip()
    ]
    if not all_sizes:
        return ""
    body_size = Counter(all_sizes).most_common(1)[0][0]

    parts: List[str] = []

    for block in data["blocks"]:
        if block["type"] != 0:  # skip image blocks
            continue

        block_y_center = (block["bbox"][1] + block["bbox"][3]) / 2

        text, dominant_size = _block_content(block)
        if not text:
            continue

        # Drop running headers/footers: short text in top or bottom margin
        in_margin = block_y_center < header_zone or block_y_center > footer_zone
        if in_margin and len(text) < 80:
            continue

        # Drop page numbers and purely decorative lines
        if re.fullmatch(r"[\d\s\-–—|·•ivxlcdmIVXLCDM]+", text) and len(text) < 25:
            continue

        # Drop footnotes: smaller font in the lower portion of the page
        if dominant_size < body_size * FOOTNOTE_RATIO and block_y_center > page_h * 0.65:
            continue

        # Format headings for natural TTS reading
        if dominant_size > body_size * HEADING_RATIO:
            # Convert ALL CAPS headings to title case
            formatted = text.title() if text == text.upper() else text
            parts.append(f"\n{formatted}.\n")
        else:
            parts.append(text)

    return "\n".join(parts)


def _block_content(block) -> tuple[str, float]:
    """Return (cleaned text, dominant font size) for a block."""
    lines: List[str] = []
    sizes: List[float] = []
    pending_hyphen = False

    for line in block["lines"]:
        line_text = ""
        for span in line["spans"]:
            line_text += span["text"]
            if span["text"].strip():
                sizes.append(span["size"])
        line_text = line_text.strip()
        if not line_text:
            continue

        if pending_hyphen and lines:
            # Rejoin word broken across lines
            lines[-1] = lines[-1] + line_text
            pending_hyphen = False
        elif line_text.endswith("-"):
            lines.append(line_text[:-1])  # strip hyphen, next line continues
            pending_hyphen = True
        else:
            lines.append(line_text)

    text = " ".join(lines).strip()
    dominant = Counter(round(s) for s in sizes).most_common(1)[0][0] if sizes else 0
    return text, dominant


def _split(text: str) -> List[str]:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: List[str] = []
    current = ""
    for sentence in sentences:
        # A single sentence longer than the cap can't be packed — hard-split it
        # on whitespace so no chunk ever exceeds OpenAI's limit.
        for piece in _split_oversized(sentence):
            if current and len(current) + len(piece) + 1 > CHUNK_SIZE:
                chunks.append(current.strip())
                current = piece
            else:
                current = (current + " " + piece).lstrip()
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _split_oversized(sentence: str) -> List[str]:
    """Break a single over-cap sentence into <= CHUNK_SIZE whitespace pieces."""
    if len(sentence) <= CHUNK_SIZE:
        return [sentence]
    pieces: List[str] = []
    current = ""
    for word in sentence.split():
        if current and len(current) + len(word) + 1 > CHUNK_SIZE:
            pieces.append(current)
            current = word
        else:
            current = (current + " " + word).lstrip()
    if current:
        pieces.append(current)
    return pieces
