import json
import fitz
from openai import OpenAI

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def suggest_metadata(pdf_path: str, title: str, text_excerpt: str) -> dict:
    pdf_meta = _read_pdf_meta(pdf_path)

    prompt = (
        "You are a library cataloger. Given the document title, an optional author hint, "
        "and an excerpt from the document, return a JSON object with exactly these keys:\n"
        '  "author": full author name as a string, or null\n'
        '  "genre": one of the standard genres (e.g. "History", "Philosophy", "Science", '
        '"Fiction", "Biography", "Politics", "Technology", "Economics", "Non-fiction"), or null\n'
        '  "year": publication year as an integer (not the PDF creation date), or null\n'
        '  "notes": one sentence describing what this document is about, or null\n\n'
        f"Title: {title}\n"
        f"Author hint from PDF metadata: {pdf_meta.get('author') or 'none'}\n"
        f"Document excerpt:\n{text_excerpt[:600]}\n\n"
        "Return only the JSON object."
    )

    response = _get_client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
    )

    raw = response.choices[0].message.content
    data = json.loads(raw)

    # Normalise — only return keys we care about, coerce types
    return {
        "author": _str_or_none(data.get("author")),
        "genre": _str_or_none(data.get("genre")),
        "year": _int_or_none(data.get("year")),
        "notes": _str_or_none(data.get("notes")),
    }


def _read_pdf_meta(pdf_path: str) -> dict:
    try:
        doc = fitz.open(pdf_path)
        meta = doc.metadata or {}
        doc.close()
        return meta
    except Exception:
        return {}


def _str_or_none(val) -> str | None:
    if not val or not str(val).strip():
        return None
    return str(val).strip()


def _int_or_none(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None
