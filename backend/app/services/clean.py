import logging

from openai import OpenAI

log = logging.getLogger(__name__)

_client = None

# How far the cleaned length may drift from the input before we assume the model
# paraphrased, truncated, or ran away — in which case we keep the heuristic text.
_MAX_LENGTH_DRIFT = 0.35

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
        _client = OpenAI()
    return _client


def llm_clean(text: str) -> str:
    """Polish one chunk of extracted text for narration.

    Falls back to the input text if the model call fails or the result drifts
    too far in length (a proxy for hallucination / truncation / runaway).
    """
    if not text.strip():
        return text

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
        return text

    if not cleaned:
        log.warning("llm_clean returned empty output; keeping heuristic text")
        return text

    drift = abs(len(cleaned) - len(text)) / max(len(text), 1)
    if drift > _MAX_LENGTH_DRIFT:
        log.warning(
            "llm_clean length drift %.0f%% exceeds %.0f%%; keeping heuristic text",
            drift * 100,
            _MAX_LENGTH_DRIFT * 100,
        )
        return text

    return cleaned
