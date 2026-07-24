import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple

from openai import OpenAI

log = logging.getLogger(__name__)

_client = None

# Chunks are cleaned in parallel — the calls are network-bound, so threads (not
# more Celery workers) are the cheap win. Tunable if OpenAI starts rate-limiting.
CLEAN_CONCURRENCY = int(os.getenv("CLEAN_CONCURRENCY", "8"))

# How far the cleaned length may drift from the input before we assume the model
# paraphrased, truncated, or ran away — in which case we keep the heuristic text.
_MAX_LENGTH_DRIFT = 0.35

# A book's opening chunks are where title pages, TOCs, and library stamps live —
# the RIGHT cleaning there often deletes over half the chunk, which the normal
# drift guard would reject (keeping precisely the debris we most want gone, in
# the segment every listener hears first). Give the first few chunks extra
# shrink room; growth stays capped at _MAX_LENGTH_DRIFT everywhere.
_OPENING_CHUNKS = 2
_OPENING_MAX_SHRINK = 0.75

_SYSTEM_PROMPT = (
    "You clean OCR/PDF-extracted book text for audiobook narration. "
    "Remove residual page artifacts, footnote debris, stray citation, figure, "
    "and table fragments, running headers, and anything that is not part of the "
    "prose meant to be read aloud. Do not paraphrase, summarize, translate, or "
    "add words — return the narration prose verbatim except for removed artifacts. "
    "Return only the cleaned text, with no preamble or commentary."
)


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        # Retry transient 429/5xx with backoff before we give up and fall back
        # to heuristic text — cleaning chunks concurrently invites rate limits,
        # and a silent fallback would quietly cost us the polish.
        _client = OpenAI(max_retries=5)
    return _client


def llm_clean(text: str) -> str:
    """Polish one chunk of extracted text for narration.

    Falls back to the input text if the model call fails or the result drifts
    too far in length (a proxy for hallucination / truncation / runaway).
    """
    return _clean_one(text)[0]


def clean_many(texts: List[str], max_workers: int = 0) -> Tuple[List[str], int]:
    """Clean chunks in parallel. Returns (cleaned_texts, fallback_count).

    Order is preserved (callers index segments by position, so this matters).
    Nothing raises: _clean_one absorbs failures into the fallback count.
    """
    if not texts:
        return [], 0
    workers = max_workers or CLEAN_CONCURRENCY
    shrinks = [
        _OPENING_MAX_SHRINK if i < _OPENING_CHUNKS else _MAX_LENGTH_DRIFT
        for i in range(len(texts))
    ]
    with ThreadPoolExecutor(max_workers=min(workers, len(texts))) as pool:
        results = list(pool.map(_clean_one, texts, shrinks))
    return [t for t, _ in results], sum(1 for _, used in results if not used)


def _clean_one(text: str, max_shrink: float = _MAX_LENGTH_DRIFT) -> Tuple[str, bool]:
    """Return (text, used_llm). used_llm is False whenever we fell back."""
    if not text.strip():
        return text, True

    try:
        response = _get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0,
        )
        cleaned = (response.choices[0].message.content or "").strip()
    except Exception:
        log.exception("llm_clean call failed; keeping heuristic text")
        return text, False

    if not cleaned:
        log.warning("llm_clean returned empty output; keeping heuristic text")
        return text, False

    delta = (len(cleaned) - len(text)) / max(len(text), 1)
    limit = _MAX_LENGTH_DRIFT if delta > 0 else max_shrink
    if abs(delta) > limit:
        log.warning(
            "llm_clean length drift %.0f%% exceeds %.0f%%; keeping heuristic text",
            abs(delta) * 100,
            limit * 100,
        )
        return text, False

    return cleaned, True
