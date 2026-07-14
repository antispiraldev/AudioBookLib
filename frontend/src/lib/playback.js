// Small localStorage-backed persistence for the audio player:
// per-book listening position + a global preferred playback speed.

const PROGRESS_PREFIX = "aedo:progress:";
const SPEED_KEY = "aedo:speed";

// Progress record shape: { segIdx, t, fraction, updated }
//  - segIdx:   chapter index the listener was on
//  - t:        seconds into that chapter
//  - fraction: overall 0..1 through the book (cached so cards can show it
//              without knowing every chapter's duration)

export function loadProgress(bookId) {
  try {
    const raw = localStorage.getItem(PROGRESS_PREFIX + bookId);
    if (!raw) return null;
    const p = JSON.parse(raw);
    return typeof p?.segIdx === "number" ? p : null;
  } catch {
    return null;
  }
}

export function saveProgress(bookId, data) {
  try {
    localStorage.setItem(
      PROGRESS_PREFIX + bookId,
      JSON.stringify({ ...data, updated: Date.now() })
    );
  } catch {
    // storage full / unavailable (private mode) — non-fatal
  }
}

export function loadSpeed() {
  try {
    const v = parseFloat(localStorage.getItem(SPEED_KEY));
    return Number.isFinite(v) && v > 0 ? v : 1;
  } catch {
    return 1;
  }
}

export function saveSpeed(rate) {
  try {
    localStorage.setItem(SPEED_KEY, String(rate));
  } catch {
    // non-fatal
  }
}
