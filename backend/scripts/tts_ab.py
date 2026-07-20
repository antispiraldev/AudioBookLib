"""Render one passage across a voice x instruction-preset grid for blind A/B listening.

Standalone, like the other scripts here — no pytest, no app imports beyond the
TTS service. Reads OPENAI_API_KEY from the environment (or ../.env).

    cd backend && python scripts/tts_ab.py
    cd backend && python scripts/tts_ab.py --voices onyx,marin --presets current,character
    open scripts/ab_out/index.html

Round 4 pits the OpenAI production default against premium ElevenLabs and Gemini
presets (see PROVIDER_PRESETS). It needs ELEVENLABS_API_KEY and GEMINI_API_KEY in
the environment (or ../.env), and costs real money — a few cents per clip, not per
grid — so it is opt-in:

    cd backend && python scripts/tts_ab.py --round4
    cd backend && python scripts/tts_ab.py --el-list-voices   # real voice_ids for your account

Clips land in scripts/ab_out*/ as <name>.mp3 (or .wav for Gemini, which returns
PCM) plus an index.html that plays them blind (labels hidden until Reveal).
"""

import argparse
import json
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.tts import (  # noqa: E402
    DEFAULT_INSTRUCTIONS,
    NARRATORS,
    synthesize_preset,
)

OUT_DIR = Path(__file__).resolve().parent / "ab_out"

# Machiavelli's 13 Dec 1513 letter to Vettori (public domain). Chosen because it
# mixes plain exposition, a long quotation, and a line of verse — flat narration
# has nowhere to hide.
PASSAGE = (
    "The evening being come, I return home and go to my study; at the entrance "
    "I pull off my peasant-clothes, covered with dust and dirt, and put on my "
    "noble court dress, and thus becomingly re-clothed I pass into the ancient "
    "courts of the men of old, where, being lovingly received by them, I am fed "
    "with that food which is mine alone; where I do not hesitate to speak with "
    "them, and to ask for the reason of their actions, and they in their "
    "benignity answer me; and for four hours I feel no weariness, I forget every "
    "trouble, poverty does not dismay, death does not terrify me; I am possessed "
    "entirely by those great men."
)

# onyx is the current production default and acts as the control. marin and cedar
# are the newest OpenAI voices; ash and ballad are the more characterful of the
# older set.
VOICES = ["onyx", "ash", "ballad", "marin", "cedar"]

PRESETS = {
    # Control: verbatim from tts.py, so the grid always contains today's output.
    "current": DEFAULT_INSTRUCTIONS,
    "character": (
        "Read as an engaged storyteller who is genuinely interested in what he is "
        "saying. Vary your pitch and pace with the meaning of the sentence: lean "
        "into the vivid images, let the long clauses build, and slow down for the "
        "closing line. Warm and human, never breathless or theatrical. "
        "Do not editorialize or change the words."
    ),
    "intimate": (
        "Read as if speaking quietly to one person in the same room, close to the "
        "microphone. Unhurried and conversational, with natural breaths and small "
        "pauses at the commas. Confiding rather than performed. "
        "Do not editorialize or change the words."
    ),
    "classic": (
        "Read as a distinguished literary narrator in the classic BBC tradition. "
        "Measured, articulate, and authoritative, with crisp consonants and "
        "deliberate phrasing that respects the punctuation. Dignified but not cold. "
        "Do not editorialize or change the words."
    ),
    # --- Round 2 -------------------------------------------------------------
    # Round 1 picked ash/intimate, ash/classic, onyx/classic: deep voices, restrained
    # delivery. None of the round-1 presets described the *speaker* — only pacing and
    # manner. These add age and vocal fry, and isolate each factor against `intimate`
    # so we can tell which one is actually doing the work.
    "aged_fry": (
        "Read as an older narrator, a man in his sixties or seventies with a low, "
        "lived-in voice and a slight vocal fry — a soft gravelly creak that settles "
        "in at the ends of phrases and on the quieter words. Unhurried and "
        "conversational, close to the microphone, speaking to one person. The voice "
        "carries age and experience without sounding frail or tired. "
        "Do not editorialize or change the words."
    ),
    "aged_warm": (
        "Read as an older narrator, a man in his sixties or seventies with a low, "
        "warm, lived-in voice. Unhurried and conversational, close to the "
        "microphone, speaking to one person. The voice carries age and experience, "
        "smooth and resonant rather than rough. "
        "Do not editorialize or change the words."
    ),
    "fry_only": (
        "Read as if speaking quietly to one person in the same room, close to the "
        "microphone. Unhurried and conversational, with natural breaths and small "
        "pauses at the commas. Let a slight vocal fry into your voice — a soft "
        "gravelly creak at the ends of phrases and on the quieter words. Confiding "
        "rather than performed. Do not editorialize or change the words."
    ),
    "unpolished": (
        "Read as an older man reading aloud to a friend, not as a professional "
        "narrator. Low and gravelly, with a slight vocal fry. Let it be imperfect: "
        "audible breaths, the occasional micro-pause where someone would naturally "
        "gather a thought, phrases that run a little long and then settle. Some "
        "sentences land softer than others. Human rather than polished. "
        "Do not editorialize or change the words."
    ),
    # Identical to aged_fry minus the trailing constraint, to test whether that
    # clause is itself suppressing expression.
    "aged_fry_free": (
        "Read as an older narrator, a man in his sixties or seventies with a low, "
        "lived-in voice and a slight vocal fry — a soft gravelly creak that settles "
        "in at the ends of phrases and on the quieter words. Unhurried and "
        "conversational, close to the microphone, speaking to one person. The voice "
        "carries age and experience without sounding frail or tired."
    ),
}

ROUND2_VOICES = ["ash", "onyx"]
ROUND2_PRESETS = ["intimate", "aged_fry", "aged_warm", "fry_only", "unpolished", "aged_fry_free"]

# --- Round 3 ---------------------------------------------------------------
# Round 2 picked onyx/aged_fry_free, then onyx/aged_warm. Two findings drive
# round 3: onyx beat ash once the prompt described age (so the production default
# voice is fine), and dropping "do not editorialize" is what unlocked the
# emotional content — aged_fry, the same prompt *with* the clause, ranked lower.
#
# The clause conflated lexical fidelity with prosodic freedom. These presets split
# them: say exactly these words, but vary how. They also name the trait the listener
# singled out in D — letting the final phoneme of a sentence linger rather than clip.

# Guarantees the words without touching delivery. Insurance against paraphrase now
# that the blunt clause is gone.
_FIDELITY = (
    "Read the text exactly as written — every word, in order, with nothing added, "
    "dropped, or reworded. How you say it is entirely yours to shape."
)

_AGED_BASE = (
    "Read as an older narrator, a man in his sixties or seventies with a low, "
    "lived-in voice and a slight vocal fry — a soft gravelly creak that settles "
    "in at the ends of phrases and on the quieter words. Unhurried and "
    "conversational, close to the microphone, speaking to one person. The voice "
    "carries age and experience without sounding frail or tired."
)

_LINGER = (
    "Let the last word of a sentence linger and decay rather than clipping it off, "
    "and leave a beat of silence after it before moving on."
)

PRESETS.update(
    {
        # Stress follows meaning: the emphasis lands on whichever word carries the
        # emotional weight, so it moves sentence to sentence instead of falling on a
        # fixed metrical beat.
        "prosody_valence": (
            f"{_AGED_BASE} As you read, find the word in each sentence that carries "
            "its feeling and let the stress land there, so the emphasis moves from "
            "sentence to sentence rather than falling into a fixed rhythm. Where the "
            "text turns warm or reverent, soften and slow; where it turns plain or "
            "factual, level out. Let the pitch rise slightly through a clause that is "
            f"building and fall as it resolves. {_LINGER} {_FIDELITY}"
        ),
        # Same idea stated as mechanics rather than emotion — tests whether the model
        # responds better to "vary pitch/tempo/volume" than to "follow the feeling."
        "prosody_contour": (
            f"{_AGED_BASE} Vary your prosody continuously: change pitch, tempo, and "
            "volume from phrase to phrase so no two sentences share the same shape. "
            "Take subordinate and parenthetical clauses faster and quieter, then "
            "return to full weight on the main clause. Pause longer at a semicolon "
            f"than at a comma, and longer still at a full stop. {_LINGER} {_FIDELITY}"
        ),
        # Both of the above at once, pushed harder — the ceiling test.
        "prosody_max": (
            f"{_AGED_BASE} Give this real prosodic range. Let the stress land on the "
            "word carrying the feeling, and let it move as the meaning moves. Vary "
            "pitch, tempo, and volume from phrase to phrase; take the subordinate "
            "clauses lighter and quicker, lean into the vivid images, and let a long "
            "sentence build and then settle. Some lines should land noticeably softer "
            f"than others. {_LINGER} Never sing-song or theatrical. {_FIDELITY}"
        ),
        # D's exact prompt plus only the lingering-decay line, to check whether that
        # single trait is what the listener actually responded to.
        "linger_only": f"{_AGED_BASE} {_LINGER} {_FIDELITY}",
        # D verbatim, no fidelity clause at all — carried forward as the control.
        "d_control": _AGED_BASE,
        # prosody_valence with the blunt original clause restored, to confirm the
        # reworded fidelity line is what preserves expression.
        "prosody_valence_blunt": (
            f"{_AGED_BASE} As you read, find the word in each sentence that carries "
            "its feeling and let the stress land there, so the emphasis moves from "
            "sentence to sentence rather than falling into a fixed rhythm. Where the "
            "text turns warm or reverent, soften and slow; where it turns plain or "
            "factual, level out. Let the pitch rise slightly through a clause that is "
            f"building and fall as it resolves. {_LINGER} "
            "Do not editorialize or change the words."
        ),
    }
)

ROUND3_VOICES = ["onyx"]
ROUND3_PRESETS = [
    "d_control",
    "linger_only",
    "prosody_valence",
    "prosody_contour",
    "prosody_max",
    "prosody_valence_blunt",
]

# --- Round 4: cross-provider premium grid ----------------------------------
# The first three rounds tuned OpenAI voice x prompt. Round 4 asks a different
# question: is a premium provider worth it for select books, cost aside? Each
# entry is a self-contained preset (same schema app/services/tts.py consumes), so
# whatever wins can be pasted straight into NARRATORS. The OpenAI production default
# rides along as the control.
#
# ElevenLabs steers by voice + settings, not by a natural-language prompt: the
# "pre chosen parameters" are the model_id and voice_settings below (stability trades
# consistency vs expressiveness; multilingual_v2 = the reliable long-form pick, v3 =
# more expressive but less deterministic across a book). Gemini steers by a prompt
# prefix like OpenAI and returns PCM, so its clips are .wav.
#
# Voice ids/names are a documented starting point — confirm ElevenLabs ids for your
# account with `--el-list-voices` before trusting a win.
_EL_AUDIOBOOK = {
    "stability": 0.5,
    "similarity_boost": 0.8,
    "style": 0.0,
    "use_speaker_boost": True,
    "speed": 1.0,
}
_GEMINI_STYLE = (
    "Read the following as a warm, unhurried older audiobook narrator, close to the "
    "microphone, letting the stress follow the meaning of each sentence and the final "
    "words linger"
)
_GEMINI_MODEL = "gemini-2.5-pro-preview-tts"

PROVIDER_PRESETS: dict[str, dict] = {
    # Control: today's production narrator, so the blind grid always contains the
    # bar the premium options have to clear.
    "openai_default": {"label": "OpenAI onyx (production default)", **NARRATORS["older_man"]},
    # --- ElevenLabs, multilingual_v2 (long-form workhorse) ---
    "el_george_v2": {
        "label": "ElevenLabs George / multilingual_v2",
        "provider": "elevenlabs",
        "voice_id": "JBFqnCBsd6RMkjVDRZzb",
        "model_id": "eleven_multilingual_v2",
        "voice_settings": _EL_AUDIOBOOK,
    },
    "el_charlotte_v2": {
        "label": "ElevenLabs Charlotte / multilingual_v2",
        "provider": "elevenlabs",
        "voice_id": "XB0fDUnXU5powFXDhCwa",
        "model_id": "eleven_multilingual_v2",
        "voice_settings": _EL_AUDIOBOOK,
    },
    "el_adam_v2": {
        "label": "ElevenLabs Adam (deep) / multilingual_v2",
        "provider": "elevenlabs",
        "voice_id": "pNInz6obpgDQGcFmaJgB",
        "model_id": "eleven_multilingual_v2",
        "voice_settings": _EL_AUDIOBOOK,
    },
    # --- ElevenLabs v3 (expressive; test consistency vs the v2 take) ---
    "el_george_v3": {
        "label": "ElevenLabs George / v3 (expressive)",
        "provider": "elevenlabs",
        "voice_id": "JBFqnCBsd6RMkjVDRZzb",
        "model_id": "eleven_v3",
        "voice_settings": _EL_AUDIOBOOK,
    },
    # --- Gemini 2.5 Pro (prompt-steered; returns .wav) ---
    "gem_charon": {
        "label": "Gemini Charon / 2.5-pro",
        "provider": "gemini",
        "voice_name": "Charon",
        "model": _GEMINI_MODEL,
        "instructions": _GEMINI_STYLE,
    },
    "gem_enceladus": {
        "label": "Gemini Enceladus / 2.5-pro",
        "provider": "gemini",
        "voice_name": "Enceladus",
        "model": _GEMINI_MODEL,
        "instructions": _GEMINI_STYLE,
    },
    "gem_sulafat": {
        "label": "Gemini Sulafat / 2.5-pro",
        "provider": "gemini",
        "voice_name": "Sulafat",
        "model": _GEMINI_MODEL,
        "instructions": _GEMINI_STYLE,
    },
    "gem_kore": {
        "label": "Gemini Kore / 2.5-pro",
        "provider": "gemini",
        "voice_name": "Kore",
        "model": _GEMINI_MODEL,
        "instructions": _GEMINI_STYLE,
    },
}


def _openai_spec(voice: str, preset: str) -> tuple[str, str, dict]:
    """Build a (name, label, preset) spec for one cell of the OpenAI voice x prompt grid."""
    return (
        f"{voice}__{preset}",
        f"{voice} / {preset}",
        {"provider": "openai", "voice": voice, "instructions": PRESETS[preset]},
    )


def render(name: str, label: str, preset: dict, text: str, take: int = 1) -> tuple:
    """Synthesize one clip. Returns (name, label, take, filename, error)."""
    ext = "wav" if preset.get("provider") == "gemini" else "mp3"
    suffix = "" if take == 1 else f"__take{take}"
    filename = f"{name}{suffix}.{ext}"
    try:
        synthesize_preset(text, str(OUT_DIR / filename), preset)
    except Exception as exc:  # noqa: BLE001 - report per-clip, keep the grid going
        return name, label, take, None, str(exc)
    return name, label, take, filename, None


def list_elevenlabs_voices() -> int:
    """Print the account's real ElevenLabs voice ids so PROVIDER_PRESETS can be trusted."""
    import urllib.request

    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        print("ELEVENLABS_API_KEY not set and not found in .env", file=sys.stderr)
        return 1
    req = urllib.request.Request(
        "https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": key}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        voices = json.loads(resp.read()).get("voices", [])
    for v in voices:
        print(f"{v.get('voice_id'):24}  {v.get('name')}  ({v.get('category')})")
    print(f"\n{len(voices)} voices", file=sys.stderr)
    return 0


def load_env() -> None:
    """Load API keys from ../.env / ../../.env for any provider not already in the env."""
    wanted = ("OPENAI_API_KEY", "ELEVENLABS_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")
    if all(os.environ.get(k) for k in wanted):
        return
    for candidate in (
        Path(__file__).resolve().parent.parent / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env",
    ):
        if not candidate.exists():
            continue
        for line in candidate.read_text().splitlines():
            line = line.strip()
            key = line.split("=", 1)[0]
            if key in wanted and "=" in line and not os.environ.get(key):
                os.environ[key] = line.split("=", 1)[1].strip().strip("\"'")


def write_index(items: list[dict]) -> Path:
    """Blind player: clips are shuffled and anonymized until you hit Reveal.

    Each item is {"label": ..., "file": ...}.
    """
    items = list(items)
    random.shuffle(items)
    html = _INDEX_TEMPLATE.replace("__ITEMS__", json.dumps(items, indent=2)).replace(
        "__PASSAGE__", PASSAGE
    )
    path = OUT_DIR / "index.html"
    path.write_text(html)
    return path


_INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Aedo TTS A/B</title>
<style>
  :root { color-scheme: light dark; }
  body { font: 16px/1.5 system-ui, sans-serif; max-width: 46rem; margin: 3rem auto; padding: 0 1rem; }
  blockquote { border-left: 3px solid currentColor; opacity: .7; margin: 0 0 2rem; padding-left: 1rem; font-size: .9rem; }
  .row { display: flex; align-items: center; gap: 1rem; padding: .6rem 0; border-bottom: 1px solid rgba(128,128,128,.3); }
  .tag { font-variant-numeric: tabular-nums; font-weight: 600; width: 2.5rem; }
  .label { font-size: .85rem; opacity: .65; min-width: 12rem; }
  audio { flex: 1; min-width: 0; }
  button { font: inherit; padding: .5rem 1rem; margin-bottom: 1.5rem; cursor: pointer; }
</style>
</head>
<body>
<h1>Aedo TTS A/B</h1>
<blockquote>__PASSAGE__</blockquote>
<button id="reveal">Reveal labels</button>
<div id="rows"></div>
<script>
const items = __ITEMS__;
const rows = document.getElementById("rows");
items.forEach((it, i) => {
  const row = document.createElement("div");
  row.className = "row";
  row.innerHTML =
    '<span class="tag">' + String.fromCharCode(65 + i) + '</span>' +
    '<audio controls preload="none" src="' + it.file + '"></audio>' +
    '<span class="label" hidden>' + it.label + '</span>';
  rows.appendChild(row);
});
document.getElementById("reveal").onclick = () => {
  document.querySelectorAll(".label").forEach(el => el.hidden = !el.hidden);
};
</script>
</body>
</html>
"""


_KEY_FOR_PROVIDER = {
    "openai": ("OPENAI_API_KEY",),
    "elevenlabs": ("ELEVENLABS_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voices", default=",".join(VOICES))
    parser.add_argument("--presets", default=",".join(PRESETS))
    parser.add_argument("--text-file", help="passage to read instead of the built-in one")
    parser.add_argument("--out", default="ab_out", help="output dir under scripts/")
    parser.add_argument(
        "--round2",
        action="store_true",
        help="round-2 grid: round-1 winners x the age/fry presets, into ab_out2/",
    )
    parser.add_argument(
        "--round3",
        action="store_true",
        help="round-3 grid: onyx x the prosody presets, 2 takes each, into ab_out3/",
    )
    parser.add_argument(
        "--round4",
        action="store_true",
        help="round-4 grid: OpenAI default vs premium ElevenLabs/Gemini presets, into ab_out4/",
    )
    parser.add_argument(
        "--el-list-voices",
        action="store_true",
        help="print your ElevenLabs account voice ids and exit",
    )
    parser.add_argument(
        "--takes", type=int, default=1, help="renders per cell, to judge consistency"
    )
    args = parser.parse_args()

    load_env()

    if args.el_list_voices:
        return list_elevenlabs_voices()

    # Build the grid as a list of (name, label, preset) specs.
    if args.round4:
        if args.out == "ab_out":
            args.out = "ab_out4"
        specs = [(name, p["label"], p) for name, p in PROVIDER_PRESETS.items()]
    else:
        if args.round2:
            args.voices = ",".join(ROUND2_VOICES)
            args.presets = ",".join(ROUND2_PRESETS)
            if args.out == "ab_out":
                args.out = "ab_out2"
        if args.round3:
            args.voices = ",".join(ROUND3_VOICES)
            args.presets = ",".join(ROUND3_PRESETS)
            if args.takes == 1:
                args.takes = 2
            if args.out == "ab_out":
                args.out = "ab_out3"
        voices = [v.strip() for v in args.voices.split(",") if v.strip()]
        presets = [p.strip() for p in args.presets.split(",") if p.strip()]
        unknown = [p for p in presets if p not in PRESETS]
        if unknown:
            print(f"unknown preset(s): {', '.join(unknown)}", file=sys.stderr)
            return 1
        specs = [_openai_spec(v, p) for v in voices for p in presets]

    globals()["OUT_DIR"] = Path(__file__).resolve().parent / args.out

    # A provider whose key is missing would fail every one of its clips — warn once
    # up front rather than per clip. OpenAI missing is fatal (it is always the control).
    providers = {p.get("provider", "openai") for _, _, p in specs}
    for provider in sorted(providers):
        keys = _KEY_FOR_PROVIDER.get(provider, ())
        if keys and not any(os.environ.get(k) for k in keys):
            msg = f"{' / '.join(keys)} not set — {provider} clips will fail"
            if provider == "openai":
                print(msg, file=sys.stderr)
                return 1
            print(f"WARNING: {msg}", file=sys.stderr)

    text = Path(args.text_file).read_text().strip() if args.text_file else PASSAGE
    globals()["PASSAGE"] = text

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cells = [
        (name, label, preset, take)
        for (name, label, preset) in specs
        for take in range(1, args.takes + 1)
    ]
    print(f"rendering {len(cells)} clips into {OUT_DIR}/ ...")

    items = []
    failures = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = pool.map(lambda c: render(c[0], c[1], c[2], text, c[3]), cells)
        for name, label, take, filename, err in results:
            tag = "" if take == 1 else f" take {take}"
            if err:
                failures += 1
                print(f"  FAIL {name}{tag}: {err}")
            else:
                print(f"  ok   {name}{tag}")
                items.append({"label": label + (f" (take {take})" if take > 1 else ""), "file": filename})

    if items:
        print(f"\nopen {write_index(items)}")
    if failures:
        print(f"{failures} of {len(cells)} clips failed", file=sys.stderr)
    return 1 if failures and not items else 0


if __name__ == "__main__":
    raise SystemExit(main())
