from pathlib import Path
from openai import OpenAI

client = OpenAI()
VOICE = "alloy"


def synthesize(text: str, output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    response = client.audio.speech.create(
        model="tts-1-hd",
        voice=VOICE,
        input=text,
    )
    response.stream_to_file(output_path)
