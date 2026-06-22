import re
import fitz  # PyMuPDF
from typing import List

CHUNK_SIZE = 3500  # safe under OpenAI's 4096-char TTS limit


def extract_text_chunks(pdf_path: str) -> tuple[int, List[str]]:
    doc = fitz.open(pdf_path)
    page_count = len(doc)
    full_text = "\n".join(page.get_text() for page in doc)
    doc.close()
    return page_count, _split(full_text)


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
