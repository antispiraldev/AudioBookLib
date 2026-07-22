import base64
import json
import os
import urllib.error
import urllib.request
import wave
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
# key -> preset. The admin picks one per book; a non-empty Book.tts_instructions
# overrides the prompt (providers that don't take a prompt ignore it, see below).
# Add a preset by adding an entry here — the API and the admin UI read this
# registry, so nothing else needs to change.
#
# Every preset carries a "provider" (default "openai" when omitted) and "label"
# + "voice" (a display string the admin dropdown shows). The remaining keys are
# provider-specific and consumed by synthesize_preset():
#   openai     -> voice (an API voice id), instructions (natural-language prompt)
#   elevenlabs -> voice_id, model_id, voice_settings   (no NL prompt; see note)
#   gemini     -> voice_name, model, instructions (style prompt)   [A/B only, WAV]
#
# The premium ElevenLabs presets are the "highest quality, cost is fine" option
# for select books. They need ELEVENLABS_API_KEY in the environment. multilingual_v2
# is ElevenLabs' own long-form-narration recommendation and, unlike v3, is
# deterministic enough to stay consistent across a book synthesized segment by
# segment. The specific voice_ids and voice_settings below are a starting point to
# be *finalized by the coming A/B round* — confirm the ids against the account with
# `python scripts/tts_ab.py --el-list-voices`.
NARRATORS: dict[str, dict] = {
    "older_man": {
        "provider": "openai",
        "label": "Older man (default)",
        "voice": "onyx",
        "instructions": _instructions("man"),
    },
    "older_woman": {
        "provider": "openai",
        "label": "Older woman",
        "voice": "shimmer",
        "instructions": _instructions("woman"),
    },
    "premium_man": {
        "provider": "elevenlabs",
        "label": "Premium male — ElevenLabs (highest quality)",
        "voice": "George",  # display only; the real selector is voice_id
        "voice_id": "JBFqnCBsd6RMkjVDRZzb",  # premade "George"; verify per account
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.8,
            "style": 0.0,
            "use_speaker_boost": True,
            "speed": 1.0,
        },
    },
    "premium_woman": {
        "provider": "elevenlabs",
        "label": "Premium female — ElevenLabs (highest quality)",
        "voice": "Charlotte",  # display only
        "voice_id": "XB0fDUnXU5powFXDhCwa",  # premade "Charlotte"; verify per account
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.8,
            "style": 0.0,
            "use_speaker_boost": True,
            "speed": 1.0,
        },
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


def preset(narrator: str | None) -> dict:
    """The narrator preset for a key, falling back to the default for an unknown
    or missing key. Never raises, so callers can pass a stored value directly.

    This is the *shared* registry entry — read-only. Use `resolve()` when you
    need a mutable copy with the provider defaulted and overrides applied.
    """
    return NARRATORS.get(narrator or DEFAULT_NARRATOR, NARRATORS[DEFAULT_NARRATOR])


def resolve(narrator: str | None = None, instructions: str | None = None) -> dict:
    """Map a per-book narrator key + optional free-text override to a resolved preset.

    An unknown or missing key falls back to the default preset. A non-empty
    `instructions` override replaces the preset's prompt (providers that don't take
    a natural-language prompt — currently ElevenLabs — ignore it). The returned dict
    is a copy safe to mutate and always carries a "provider".
    """
    p = dict(preset(narrator))
    p.setdefault("provider", "openai")
    if instructions:
        p["instructions"] = instructions
    return p


# --- Provider back ends ----------------------------------------------------
# Each writes a single utterance to output_path. urllib (stdlib) is used instead
# of the vendor SDKs so the memory-tight worker gains no new dependencies and the
# OpenAI path is untouched. Outbound HTTPS reaches both APIs fine over the worker's
# NAT route through the web droplet.


def _synthesize_openai(text: str, output_path: str, *, voice: str, instructions: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with _get_client().audio.speech.with_streaming_response.create(
        model=MODEL,
        voice=voice,
        input=text,
        instructions=instructions,
    ) as response:
        response.stream_to_file(output_path)


ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"


def _http_post(url: str, headers: dict, body: bytes, timeout: int = 300) -> bytes:
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:  # surface the provider's error text
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"{url.split('?')[0]} -> HTTP {exc.code}: {detail}") from exc


def _synthesize_elevenlabs(
    text: str,
    output_path: str,
    *,
    voice_id: str,
    model_id: str,
    voice_settings: dict,
    output_format: str = "mp3_44100_128",
) -> None:
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set")
    url = f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}?output_format={output_format}"
    body = json.dumps(
        {"text": text, "model_id": model_id, "voice_settings": voice_settings}
    ).encode("utf-8")
    audio = _http_post(
        url,
        {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        body,
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_bytes(audio)


GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_SAMPLE_RATE = 24000  # Gemini TTS returns 16-bit mono PCM at 24 kHz


def _synthesize_gemini(
    text: str,
    output_path: str,
    *,
    voice_name: str,
    model: str = "gemini-2.5-pro-preview-tts",
    instructions: str | None = None,
) -> None:
    """Render one utterance with Gemini TTS. Writes a WAV (the API returns raw PCM).

    A/B-only: the production pipeline stores .mp3, so wiring Gemini into a book would
    need a PCM->mp3 transcode step. Style is steered by prepending a natural-language
    instruction to the text, per Google's docs.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY (or GOOGLE_API_KEY) is not set")
    prompt = f"{instructions.rstrip('.:')}: {text}" if instructions else text
    url = f"{GEMINI_BASE}/models/{model}:generateContent"
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_name}}
                },
            },
        }
    ).encode("utf-8")
    raw = _http_post(
        url, {"x-goog-api-key": api_key, "Content-Type": "application/json"}, body
    )
    payload = json.loads(raw)
    try:
        parts = payload["candidates"][0]["content"]["parts"]
        b64 = next(p["inlineData"]["data"] for p in parts if "inlineData" in p)
    except (KeyError, IndexError, StopIteration) as exc:
        raise RuntimeError(f"Gemini returned no audio: {json.dumps(payload)[:500]}") from exc
    pcm = base64.b64decode(b64)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(output_path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(GEMINI_SAMPLE_RATE)
        wav.writeframes(pcm)


def synthesize_preset(text: str, output_path: str, preset: dict) -> None:
    """Dispatch one utterance to the preset's provider back end."""
    provider = preset.get("provider", "openai")
    if provider == "openai":
        _synthesize_openai(
            text,
            output_path,
            voice=preset.get("voice") or VOICE,
            instructions=preset.get("instructions") or DEFAULT_INSTRUCTIONS,
        )
    elif provider == "elevenlabs":
        _synthesize_elevenlabs(
            text,
            output_path,
            voice_id=preset["voice_id"],
            model_id=preset.get("model_id", "eleven_multilingual_v2"),
            voice_settings=preset.get("voice_settings", {}),
            output_format=preset.get("output_format", "mp3_44100_128"),
        )
    elif provider == "gemini":
        _synthesize_gemini(
            text,
            output_path,
            voice_name=preset["voice_name"],
            model=preset.get("model", "gemini-2.5-pro-preview-tts"),
            instructions=preset.get("instructions") or None,
        )
    else:
        raise ValueError(f"unknown TTS provider: {provider!r}")


def synthesize(
    text: str,
    output_path: str,
    instructions: str | None = None,
    voice: str | None = None,
) -> None:
    """Back-compat OpenAI entry point for callers that pass voice/instructions directly."""
    _synthesize_openai(
        text,
        output_path,
        voice=voice or VOICE,
        instructions=instructions or DEFAULT_INSTRUCTIONS,
    )
