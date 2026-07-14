from pathlib import Path
from openai import OpenAI

MODEL = "gpt-4o-mini-tts"
VOICE = "onyx"
DEFAULT_INSTRUCTIONS = (
    "Read as a warm, measured audiobook narrator. Neutral, natural pacing. "
    "Do not editorialize or change the words."
)
_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def synthesize(text: str, output_path: str, instructions: str | None = None) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    response = _get_client().audio.speech.create(
        model=MODEL,
        voice=VOICE,
        input=text,
        instructions=instructions or DEFAULT_INSTRUCTIONS,
    )
    response.stream_to_file(output_path)
