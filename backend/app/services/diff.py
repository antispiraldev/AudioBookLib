"""Segment-level text alignment for diff-based backfill.

When a book is re-extracted with newer cleaning heuristics, most of its text
is usually unchanged — re-synthesizing every segment would re-pay TTS for
audio we already own. align_texts() maps each newly extracted chunk to the
existing segment whose text (and therefore audio) it can reuse, so only the
chunks that actually changed get re-synthesized.
"""
import difflib
from typing import List, Optional

# Two texts at least this similar are "the same" for audio-reuse purposes.
# Deliberately strict: a removed running header ("BEYOND GOOD AND EVIL 127")
# in an 1800-char chunk only drops the ratio to ~0.993, and those segments are
# exactly the ones a backfill must re-synthesize. 0.998 (~4 chars per 1800)
# tolerates whitespace jitter and single-character normalization (ligatures)
# while treating every audible edit as changed.
FUZZY_THRESHOLD = 0.998


def _norm(text: str) -> str:
    return " ".join(text.split())


def align_texts(
    old: List[str], new: List[str], fuzzy: float = FUZZY_THRESHOLD
) -> List[Optional[int]]:
    """For each new chunk index, the old segment index whose audio it can
    reuse, or None if it must be (re-)synthesized.

    Alignment is a sequence diff over whitespace-normalized texts: exact
    matches carry over directly; within replaced runs, positionally paired
    texts still carry over when they are nearly identical (>= fuzzy ratio).
    Each old index is used at most once, so callers can delete every old
    segment that no new chunk claims.
    """
    old_n = [_norm(t) for t in old]
    new_n = [_norm(t) for t in new]
    result: List[Optional[int]] = [None] * len(new)

    sm = difflib.SequenceMatcher(a=old_n, b=new_n, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(j2 - j1):
                result[j1 + k] = i1 + k
        elif tag == "replace":
            # Positionally paired near-identical texts (polish jitter, tiny
            # artifact removals below the audible threshold) keep their audio.
            for oi, nj in zip(range(i1, i2), range(j1, j2)):
                ratio = difflib.SequenceMatcher(
                    None, old_n[oi], new_n[nj], autojunk=False
                ).ratio()
                if ratio >= fuzzy:
                    result[nj] = oi
    return result
