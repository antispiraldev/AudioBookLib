from pathlib import Path
from openai import OpenAI

VOICE = "alloy"
_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def synthesize(text: str, output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    response = _get_client().audio.speech.create(
        model="tts-1-hd",
        voice=VOICE,
        input=text,
    )
    response.stream_to_file(output_path)
