from pathlib import Path
from openai import OpenAI

MODEL = "gpt-4o-mini-tts"

# --- Prompt fragments ------------------------------------------------------
# The default narration prompt was chosen by blind A/B (see backend/scripts/
# tts_ab.py): onyx voice, "prosody_valence" preset. It is assembled from shared
# fragments so every narrator preset stays consistent — only the voice and the
# gendered noun differ. Lexical fidelity is stated separately from delivery so the
# model reads the exact words while still varying prosody.

_VALENCE = (
    "As you read, find the word in each sentence that carries its feeling and let "
    "the stress land there, so the emphasis moves from sentence to sentence rather "
    "than falling into a fixed rhythm. Where the text turns warm or reverent, "
    "soften and slow; where it turns plain or factual, level out. Let the pitch "
    "rise slightly through a clause that is building and fall as it resolves."
)
_LINGER = (
    "Let the last word of a sentence linger and decay rather than clipping it off, "
    "and leave a beat of silence after it before moving on."
)
_FIDELITY = (
    "Read the text exactly as written — every word, in order, with nothing added, "
    "dropped, or reworded. How you say it is entirely yours to shape."
)


def _aged(noun: str) -> str:
    return (
        f"Read as an older narrator, a {noun} in their sixties or seventies with a "
        "low, lived-in voice and a slight vocal fry — a soft gravelly creak that "
        "settles in at the ends of phrases and on the quieter words. Unhurried and "
        "conversational, close to the microphone, speaking to one person. The voice "
        "carries age and experience without sounding frail or tired."
    )


def _instructions(noun: str) -> str:
    return " ".join([_aged(noun), _VALENCE, _LINGER, _FIDELITY])


# --- Narrator presets ------------------------------------------------------
# key -> {label, voice, instructions}. The admin picks one per book; a non-empty
# Book.tts_instructions overrides the prompt (but not the voice). Add a preset by
# adding an entry here — the API and the admin UI read this registry, so nothing
# else needs to change.
NARRATORS: dict[str, dict[str, str]] = {
    "older_man": {
        "label": "Older man (default)",
        "voice": "onyx",
        "instructions": _instructions("man"),
    },
    "older_woman": {
        "label": "Older woman",
        "voice": "shimmer",
        "instructions": _instructions("woman"),
    },
}
DEFAULT_NARRATOR = "older_man"

# Backward-compatible module constants for callers that pass no preset.
VOICE = NARRATORS[DEFAULT_NARRATOR]["voice"]
DEFAULT_INSTRUCTIONS = NARRATORS[DEFAULT_NARRATOR]["instructions"]

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def resolve(narrator: str | None = None, instructions: str | None = None) -> tuple[str, str]:
    """Map a per-book narrator key + optional free-text override to (voice, instructions).

    An unknown or missing key falls back to the default preset. A non-empty
    `instructions` override replaces the preset's prompt but keeps its voice.
    """
    preset = NARRATORS.get(narrator or DEFAULT_NARRATOR, NARRATORS[DEFAULT_NARRATOR])
    return preset["voice"], (instructions or preset["instructions"])


def synthesize(
    text: str,
    output_path: str,
    instructions: str | None = None,
    voice: str | None = None,
) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with _get_client().audio.speech.with_streaming_response.create(
        model=MODEL,
        voice=voice or VOICE,
        input=text,
        instructions=instructions or DEFAULT_INSTRUCTIONS,
    ) as response:
        response.stream_to_file(output_path)
