import re
from collections import Counter
from typing import List

import fitz  # PyMuPDF

CHUNK_SIZE = 3500  # safe under OpenAI's 4096-char TTS limit

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
    return page_count, _split(full_text)


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
        if current and len(current) + len(sentence) + 1 > CHUNK_SIZE:
            chunks.append(current.strip())
            current = sentence
        else:
            current = (current + " " + sentence).lstrip()
    if current.strip():
        chunks.append(current.strip())
    return chunks
