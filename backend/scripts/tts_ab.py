"""Render one passage across a voice x instruction-preset grid for blind A/B listening.

Standalone, like the other scripts here — no pytest, no app imports beyond the
TTS service. Reads OPENAI_API_KEY from the environment (or ../.env).

    cd backend && python scripts/tts_ab.py
    cd backend && python scripts/tts_ab.py --voices onyx,marin --presets current,character
    open scripts/ab_out/index.html

Clips land in scripts/ab_out/ as <voice>__<preset>.mp3 plus an index.html that
plays them blind (labels hidden until you click Reveal). Cost is a few cents per
full grid at gpt-4o-mini-tts rates.
"""

import argparse
import json
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.tts import DEFAULT_INSTRUCTIONS, synthesize  # noqa: E402

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


def render(voice: str, preset: str, text: str) -> tuple[str, str, str | None]:
    """Synthesize one cell of the grid. Returns (voice, preset, error)."""
    path = OUT_DIR / f"{voice}__{preset}.mp3"
    try:
        # tts.synthesize() hardcodes VOICE, so patch it for the duration of the
        # call. Fine here because this script is single-purpose and the pool below
        # is the only caller — do not copy this pattern into the pipeline.
        import app.services.tts as tts_mod

        original = tts_mod.VOICE
        tts_mod.VOICE = voice
        try:
            synthesize(text, str(path), instructions=PRESETS[preset])
        finally:
            tts_mod.VOICE = original
    except Exception as exc:  # noqa: BLE001 - report per-cell, keep the grid going
        return voice, preset, str(exc)
    return voice, preset, None


def load_env() -> None:
    if os.environ.get("OPENAI_API_KEY"):
        return
    for candidate in (
        Path(__file__).resolve().parent.parent / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env",
    ):
        if not candidate.exists():
            continue
        for line in candidate.read_text().splitlines():
            line = line.strip()
            if line.startswith("OPENAI_API_KEY="):
                os.environ["OPENAI_API_KEY"] = line.split("=", 1)[1].strip().strip("\"'")
                return


def write_index(cells: list[tuple[str, str]]) -> Path:
    """Blind player: clips are shuffled and anonymized until you hit Reveal."""
    items = [{"voice": v, "preset": p, "file": f"{v}__{p}.mp3"} for v, p in cells]
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
<h1>Voice &times; prompt A/B</h1>
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
    '<span class="label" hidden>' + it.voice + ' / ' + it.preset + '</span>';
  rows.appendChild(row);
});
document.getElementById("reveal").onclick = () => {
  document.querySelectorAll(".label").forEach(el => el.hidden = !el.hidden);
};
</script>
</body>
</html>
"""


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
    args = parser.parse_args()

    if args.round2:
        args.voices = ",".join(ROUND2_VOICES)
        args.presets = ",".join(ROUND2_PRESETS)
        if args.out == "ab_out":
            args.out = "ab_out2"
    globals()["OUT_DIR"] = Path(__file__).resolve().parent / args.out

    load_env()
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY not set and not found in .env", file=sys.stderr)
        return 1

    voices = [v.strip() for v in args.voices.split(",") if v.strip()]
    presets = [p.strip() for p in args.presets.split(",") if p.strip()]
    unknown = [p for p in presets if p not in PRESETS]
    if unknown:
        print(f"unknown preset(s): {', '.join(unknown)}", file=sys.stderr)
        return 1

    text = Path(args.text_file).read_text().strip() if args.text_file else PASSAGE
    globals()["PASSAGE"] = text

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cells = [(v, p) for v in voices for p in presets]
    print(f"rendering {len(cells)} clips into {OUT_DIR}/ ...")

    failed = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for voice, preset, err in pool.map(lambda c: render(c[0], c[1], text), cells):
            if err:
                failed.append((voice, preset, err))
                print(f"  FAIL {voice}/{preset}: {err}")
            else:
                print(f"  ok   {voice}/{preset}")

    ok = [c for c in cells if c not in [(v, p) for v, p, _ in failed]]
    if ok:
        print(f"\nopen {write_index(ok)}")
    if failed:
        print(f"{len(failed)} of {len(cells)} clips failed", file=sys.stderr)
    return 1 if failed and not ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
