import re
import unicodedata
from collections import Counter
from typing import List, NamedTuple, Optional, Tuple

import fitz  # PyMuPDF

# ~1800 chars ≈ 1.5 min of audio. gpt-4o-mini-tts drifts (pauses, even voice
# changes) past ~3 min, so we stay well under; also well under the 4096 cap.
CHUNK_SIZE = 1800


class Chunk(NamedTuple):
    """One TTS-ready piece of text. chapter_title is set only on the first
    chunk of a detected chapter; None elsewhere (and everywhere for books
    with no detectable chapters)."""
    chapter_title: Optional[str]
    text: str

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


_ROMAN_PAIRS = [
    (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
    (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
]
_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def _int_to_roman(n: int) -> str:
    out = []
    for value, symbol in _ROMAN_PAIRS:
        while n >= value:
            out.append(symbol)
            n -= value
    return "".join(out)


def _chapter_number(s: str) -> Optional[int]:
    """Parse an arabic or roman chapter number.

    Roman parsing is round-trip validated (int_to_roman(v) == s), which
    rejects OCR debris and English words that happen to use roman letters
    ("did", "civil", "mill") — the linchpin of noise-free chapter detection.
    """
    s = s.strip()
    if s.isdigit():
        return int(s)
    low = s.lower()
    if not low or any(c not in _ROMAN_VALUES for c in low):
        return None
    total, prev = 0, 0
    for c in reversed(low):
        v = _ROMAN_VALUES[c]
        if v < prev:
            total -= v
        else:
            total += v
            prev = v
    if total > 0 and _int_to_roman(total) == low:
        return total
    return None


def _smart_titlecase(text: str) -> str:
    """str.title() that keeps roman numerals uppercase: CHAPTER II → Chapter II,
    not Chapter Ii — while leaving real words (Civil, Did) alone."""
    def fix(word: str) -> str:
        core = word.strip(".,:;()[]*")
        if core and not core.isdigit() and _chapter_number(core) is not None:
            return word.replace(core, core.upper(), 1)
        return word
    return " ".join(fix(w) for w in text.title().split())


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
# Chapter/section heading at the start of a line. Text-pattern based on
# purpose: font-size heading detection is unusable for chapters (poor scans
# yield hundreds of garbage "headings"), while this pattern produced zero
# false positives on OCR noise across the test corpus.
_CHAPTER_RE = re.compile(
    r"^\s*(?:"
    r"(?P<type>chapter|book|part|section|letter|essay|canto)\s+(?P<num>\d+|[ivxlcdm]+)\b"
    r"|(?P<ftype>federalist)\s+no\.?\s*(?P<fnum>\d+)\b"
    r")",
    re.IGNORECASE,
)
# A line that is nothing but a heading keyword — block extraction sometimes
# splits "FEDERALIST" / "No. 6. …" onto separate lines; we rejoin for matching.
_LONE_KEYWORD_RE = re.compile(
    r"(?i)^\s*(chapter|book|part|section|letter|essay|canto|federalist)\s*[.:]?\s*$"
)
# Minimum prose between two chapter candidates for the first to be a real
# boundary. TOC entries and repeated/multi-line titles sit adjacent with ~no
# prose between them; real chapters have pages of it.
MIN_CHAPTER_CHARS = 600
# A "Contents" / "Table of Contents" heading line (heading formatting may have
# title-cased it and appended a period).
# Tolerate trailing punctuation: OCR + heading formatting yield "Contents,."
_CONTENTS_HEADING_RE = re.compile(r"(?i)^\s*(table\s+of\s+)?contents\s*[.,:;]*\s*$")
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


def _clean_title(raw: str) -> str:
    """Normalize a heading line into a stored chapter title."""
    t = re.sub(r"\s+", " ", raw).strip().rstrip(".")
    if len(t) > 96:  # navigation label, not prose — keep it scannable
        t = t[:96].rsplit(" ", 1)[0] + "…"
    # Defensively restore roman numerals mangled by earlier title-casing
    # ("Chapter Ii" from an old extraction → "Chapter II").
    def fix(word: str) -> str:
        core = word.strip(".,:;()[]*")
        if core and not core.isdigit() and _chapter_number(core) is not None:
            return word.replace(core, core.upper(), 1)
        return word
    return " ".join(fix(w) for w in t.split())


def _find_boundaries(lines: List[str]) -> Tuple[List[Tuple[int, str]], set]:
    """Classify chapter-heading candidates into real boundaries vs noise.

    Returns (boundaries, noise_line_indices) where boundaries is
    [(line_idx, title)] in document order. Three layered filters turn the raw
    regex matches (which over-count ~1.7x from running headers and surviving
    TOC lines) into real chapter starts:

      (A) body-gap: a real chapter has substantial prose before the next
          candidate; TOC runs and repeated/multi-line titles sit adjacent.
      (B) key-dedup: first occurrence of (type, number) wins; repeats are
          running headers echoing the current chapter atop each page.
      (C) longest increasing run: within a type, keep the longest strictly
          increasing sequence of numbers in document order. A stray survivor
          (e.g. a garbled TOC line "Book XL" sitting before the real Book I)
          loses to the long real run instead of poisoning it — which a naive
          "numbers must only increase" filter did on real scans.

    Known limitation: books that restart numbering per part merge the second
    run — acceptable for v1.
    """
    def counts_toward_gap(line: str) -> bool:
        # Lighter than _is_prose_line (which is tuned for TOC detection and
        # rejects paragraphs containing a couple of numbers): body prose is
        # long, mixed-case, and doesn't end in a page number.
        s = line.strip()
        return len(s) >= 60 and any(c.islower() for c in s) and not s[-1].isdigit()

    candidates = []
    for i, line in enumerate(lines):
        raw = line.strip()
        m = _CHAPTER_RE.match(raw)
        if not m and _LONE_KEYWORD_RE.match(raw):
            # Heading split across two lines by block extraction — rejoin with
            # the next non-empty line and retry.
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                raw = f"{raw} {lines[j].strip()}"
                m = _CHAPTER_RE.match(raw)
        if not m:
            continue
        if m.group("type"):
            typ = m.group("type").lower()
            num = _chapter_number(m.group("num"))
        else:
            typ = m.group("ftype").lower()
            num = int(m.group("fnum"))
        if num is None:
            continue
        candidates.append((i, typ, num, raw))

    noise: set = set()
    seen_keys: set = set()
    survivors: List[Tuple[int, str, int, str]] = []

    for c_idx, (line_idx, typ, num, raw) in enumerate(candidates):
        next_line = (
            candidates[c_idx + 1][0] if c_idx + 1 < len(candidates) else len(lines)
        )
        body_gap = sum(
            len(ln) for ln in lines[line_idx + 1 : next_line] if counts_toward_gap(ln)
        )
        key = (typ, num)
        if body_gap < MIN_CHAPTER_CHARS or key in seen_keys:
            noise.add(line_idx)
            continue
        seen_keys.add(key)
        survivors.append((line_idx, typ, num, raw))

    # (C) keep only the longest strictly-increasing run per heading type
    keep: set = set()
    for typ in {s[1] for s in survivors}:
        positions = [i for i, s in enumerate(survivors) if s[1] == typ]
        for k in _lis_indices([survivors[i][2] for i in positions]):
            keep.add(positions[k])

    boundaries: List[Tuple[int, str]] = []
    for i, (line_idx, typ, num, raw) in enumerate(survivors):
        if i in keep:
            boundaries.append((line_idx, _clean_title(raw)))
        else:
            noise.add(line_idx)

    return boundaries, noise


def _lis_indices(nums: List[int]) -> set:
    """Indices of a longest strictly-increasing subsequence (O(n²), n is small)."""
    n = len(nums)
    if not n:
        return set()
    length = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if nums[j] < nums[i] and length[j] + 1 > length[i]:
                length[i] = length[j] + 1
                prev[i] = j
    end = max(range(n), key=lambda i: (length[i], -i))
    out = set()
    while end != -1:
        out.add(end)
        end = prev[end]
    return out


def _segment_chapters(text: str) -> List[Tuple[Optional[str], str]]:
    """Split normalized text into (chapter_title, body) regions.

    Region 0 (anything before the first heading — preface, front matter) has
    title None. Each heading line stays as the first line of its region so it
    is still narrated. Noise lines (running headers, TOC echoes) are dropped
    from the narration text entirely.
    """
    lines = text.split("\n")
    boundaries, noise = _find_boundaries(lines)
    if not boundaries:
        return [(None, text)]

    title_at = dict(boundaries)
    regions: List[Tuple[Optional[str], str]] = []
    cur_title: Optional[str] = None
    cur_lines: List[str] = []
    for i, line in enumerate(lines):
        if i in title_at:
            body = "\n".join(cur_lines).strip()
            if body:
                regions.append((cur_title, body))
            cur_title = title_at[i]
            cur_lines = [line]
        elif i in noise:
            continue
        else:
            cur_lines.append(line)
    body = "\n".join(cur_lines).strip()
    if body:
        regions.append((cur_title, body))
    return regions


def extract_text_chunks(pdf_path: str) -> tuple[int, List[Chunk]]:
    doc = fitz.open(pdf_path)
    page_count = len(doc)
    pages_text = [_extract_page(page) for page in doc]
    doc.close()
    full_text = "\n\n".join(t for t in pages_text if t)
    # Some PDFs yield NUL characters, which Postgres rejects in text columns
    full_text = full_text.replace("\x00", "")
    full_text = _normalize_text(full_text)
    return page_count, _split(_segment_chapters(full_text))


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

        # Drop viewer-style page counters ("90 of 239", "Page 4 of 12")
        if re.fullmatch(r"(?i)(page\s+)?\d+\s+of\s+\d+\.?", text):
            continue

        # Drop footnotes: smaller font in the lower portion of the page
        if dominant_size < body_size * FOOTNOTE_RATIO and block_y_center > page_h * 0.65:
            continue

        # Format headings for natural TTS reading
        if dominant_size > body_size * HEADING_RATIO:
            # Convert ALL CAPS headings to title case (roman numerals kept)
            formatted = _smart_titlecase(text) if text == text.upper() else text
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


def _split(regions: List[Tuple[Optional[str], str]]) -> List[Chunk]:
    """Pack each chapter region independently so no chunk ever spans a
    chapter boundary; only a region's first chunk carries its title."""
    chunks: List[Chunk] = []
    for title, body in regions:
        for i, piece in enumerate(_pack_region(body)):
            chunks.append(Chunk(chapter_title=title if i == 0 else None, text=piece))
    return chunks


def _pack_region(text: str) -> List[str]:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    sentences = re.split(r"(?<=[.!?])\s+", text)
    pieces: List[str] = []
    current = ""
    for sentence in sentences:
        # A single sentence longer than the cap can't be packed — hard-split it
        # on whitespace so no chunk ever exceeds OpenAI's limit.
        for piece in _split_oversized(sentence):
            if current and len(current) + len(piece) + 1 > CHUNK_SIZE:
                pieces.append(current.strip())
                current = piece
            else:
                current = (current + " " + piece).lstrip()
    if current.strip():
        pieces.append(current.strip())
    return pieces


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
