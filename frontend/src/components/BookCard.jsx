import { useEffect, useState } from "react";
import { deleteBook, retryBook, updateBook } from "../api";
import { loadProgress } from "../lib/playback";
import EditModal from "./EditModal";
import ReviewModal from "./ReviewModal";
import ReprocessModal from "./ReprocessModal";
import s from "./BookCard.module.css";

const PALETTE = [
  "#7c6af7", "#5b8af5", "#4caf82", "#e07c5b",
  "#b55be0", "#e0b05b", "#5bb8e0", "#e05b84",
];

function color(id) {
  return PALETTE[id % PALETTE.length];
}

const STATUS_LABEL = {
  pending: "Queued",
  processing: "Extracting text…",
  review: "Ready to review",
  synthesizing: "Generating audio…",
  complete: "Ready",
  error: "Error",
};

const PlayIc = () => (<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>);
const PauseIc = () => (<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h4v14H6zm8 0h4v14h-4z" /></svg>);

export default function BookCard({ book, isAdmin, isActive, playing, onPlay, onDeleted, onUpdated }) {
  const [showEdit, setShowEdit] = useState(false);
  const [showReview, setShowReview] = useState(false);
  const [showReprocess, setShowReprocess] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [retryError, setRetryError] = useState("");
  // True while an approve/retry request is in flight, so the button can't be
  // fired twice before the status flips to "synthesizing".
  const [submitting, setSubmitting] = useState(false);
  // Set when the user fires a reprocess, so we can label the working state
  // "Reprocessing…" rather than the generic "Queued"/"Extracting text…".
  const [reprocessing, setReprocessing] = useState(false);

  const readySegments = book.segments.filter((seg) => seg.status === "ready").length;
  const failedSegments = book.segments.filter((seg) => seg.status === "error").length;
  const total = book.segments.length;
  const progress = total > 0 ? readySegments / total : 0;
  const canPlay = book.status === "complete" || (book.status === "synthesizing" && readySegments > 0);
  const isStuck = book.status === "synthesizing" && failedSegments > 0;
  // "Working" = extracting/cleaning text with nothing to count yet (fresh
  // ingest or a reprocess). Drives the animated indicator and blocks re-firing.
  const isWorking = book.status === "pending" || book.status === "processing";
  const busy = isWorking || book.status === "synthesizing";
  const statusText = reprocessing && isWorking
    ? "Reprocessing…"
    : STATUS_LABEL[book.status] || book.status;
  const initial = (book.title || "?").trim().charAt(0).toUpperCase();

  // Saved listening progress (read at render; refreshes when the player closes
  // and App re-renders). Only show a meaningful, in-progress fraction.
  const listenFrac = canPlay ? loadProgress(book.id)?.fraction ?? 0 : 0;
  const started = listenFrac > 0.01 && listenFrac < 0.995;
  // Tapping the card plays it; tapping the active card toggles play/pause.
  const actionLabel = isActive ? (playing ? "Pause" : "Play") : started ? "Resume" : "Play";

  // Once the book leaves the working states (reaches review/complete/error),
  // drop the local "Reprocessing…" label.
  useEffect(() => {
    if (!isWorking) setReprocessing(false);
  }, [isWorking]);

  // Close the overflow menu on Escape.
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e) => e.key === "Escape" && setMenuOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  async function handleDelete() {
    setMenuOpen(false);
    if (!confirm(`Delete "${book.title}"?`)) return;
    await deleteBook(book.id);
    onDeleted(book.id);
  }

  async function handleRetry() {
    if (submitting) return;
    setRetryError("");
    setSubmitting(true);
    try {
      const updated = await retryBook(book.id);
      onUpdated(updated);
    } catch (e) {
      setRetryError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleToggleHidden() {
    setMenuOpen(false);
    setRetryError("");
    try {
      const updated = await updateBook(book.id, { hidden: !book.hidden });
      onUpdated(updated);
    } catch (e) {
      setRetryError(e.message);
    }
  }

  return (
    <>
      <div
        className={s.card}
        style={{
          outline: isActive ? `2px solid ${color(book.id)}` : "none",
          opacity: book.hidden ? 0.55 : 1,
        }}
      >
        <button
          type="button"
          className={s.cover}
          style={{ background: color(book.id) }}
          disabled={!canPlay}
          onClick={() => onPlay(book)}
          aria-label={
            isActive ? (playing ? `Pause ${book.title}` : `Play ${book.title}`)
            : canPlay ? `Play ${book.title}` : book.title
          }
        >
          {book.hidden && <span className={s.hiddenTag}>Hidden</span>}
          {isActive ? (
            <span className={s.coverIcon}>{playing ? <PauseIc /> : <PlayIc />}</span>
          ) : (
            <>
              {initial}
              {canPlay && <span className={s.coverHover}><PlayIc /></span>}
            </>
          )}
        </button>

        <div className={s.body}>
          <p className={s.title} title={book.title}>{book.title}</p>

          <p className={s.author}>
            {[book.author, book.year].filter(Boolean).join(" · ") || <span className={s.dash}>—</span>}
          </p>

          {book.genre && <span className={s.genre}>{book.genre}</span>}

          {book.notes && <p className={s.notes} title={book.notes}>{book.notes}</p>}

          <div className={s.statusRow}>
            {isWorking && <span className={s.spinner} aria-hidden="true" />}
            <span className={`${s.badge} ${book.status === "error" ? s.badgeError : ""} ${isWorking ? s.badgeWorking : ""}`}>
              {statusText}
            </span>
            {book.status === "synthesizing" && total > 0 && (
              <span className={s.count}>{readySegments}/{total}</span>
            )}
            {book.status === "error" && total > 0 && (
              <span className={`${s.count} ${s.countError}`}>{failedSegments}/{total} failed</span>
            )}
          </div>

          {isWorking && (
            <div className={s.progressTrack}>
              <div className={s.progressIndeterminate} />
            </div>
          )}

          {book.status === "synthesizing" && total > 0 && (
            <div className={s.progressTrack}>
              <div className={s.progressBar} style={{ width: `${progress * 100}%` }} />
            </div>
          )}

          {/* Listening progress (resume) */}
          {started && !isActive && (
            <div className={s.listenRow}>
              <div className={s.listenTrack}>
                <div className={s.listenBar} style={{ width: `${listenFrac * 100}%` }} />
              </div>
              <span className={s.listenPct}>{Math.round(listenFrac * 100)}%</span>
            </div>
          )}

          {retryError && <p className={s.errorMsg}>{retryError}</p>}

          <div className={s.actions}>
            {canPlay && (
              <button className={s.playBtn} onClick={() => onPlay(book)}>
                {actionLabel}
              </button>
            )}
            {isAdmin && book.status === "review" && (
              <>
                <button className={s.retryBtn} onClick={() => setShowReview(true)} disabled={submitting}>
                  Review
                </button>
                <button className={s.playBtn} onClick={handleRetry} disabled={submitting}>
                  {submitting ? "Starting…" : "Approve"}
                </button>
              </>
            )}
            {isAdmin && book.status === "error" && (
              <button className={s.retryBtn} onClick={handleRetry} disabled={submitting}>
                {submitting ? "Starting…" : "Retry"}
              </button>
            )}
            {isAdmin && isStuck && (
              <button className={s.retryBtn} onClick={handleRetry} disabled={submitting}>
                {submitting ? "Starting…" : "Refresh"}
              </button>
            )}

            {isAdmin && (
              <div className={s.menuWrap}>
                <button
                  className={s.menuBtn}
                  data-open={menuOpen}
                  aria-label="More actions"
                  aria-haspopup="menu"
                  aria-expanded={menuOpen}
                  onClick={() => setMenuOpen((o) => !o)}
                >
                  ⋯
                </button>
                {menuOpen && (
                  <>
                    <div className={s.backdrop} onClick={() => setMenuOpen(false)} />
                    <div className={s.menu} role="menu">
                      <button className={s.menuItem} role="menuitem" onClick={handleToggleHidden}>
                        <span className={s.menuIcon}>{book.hidden ? "◉" : "◌"}</span>
                        {book.hidden ? "Show" : "Hide"}
                      </button>
                      <button className={s.menuItem} role="menuitem" onClick={() => { setMenuOpen(false); setShowEdit(true); }}>
                        <span className={s.menuIcon}>✎</span>
                        Edit
                      </button>
                      <button
                        className={s.menuItem}
                        role="menuitem"
                        disabled={busy}
                        onClick={() => { setMenuOpen(false); setShowReprocess(true); }}
                      >
                        <span className={s.menuIcon}>↻</span>
                        {reprocessing && isWorking ? "Reprocessing…" : "Reprocess"}
                      </button>
                      <button className={`${s.menuItem} ${s.menuItemDanger}`} role="menuitem" onClick={handleDelete}>
                        <span className={s.menuIcon}>🗑</span>
                        Delete
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {showEdit && (
        <EditModal
          book={book}
          onClose={() => setShowEdit(false)}
          onSaved={onUpdated}
        />
      )}

      {showReview && (
        <ReviewModal
          book={book}
          onClose={() => setShowReview(false)}
          onApproved={onUpdated}
        />
      )}

      {showReprocess && (
        <ReprocessModal
          book={book}
          onClose={() => setShowReprocess(false)}
          onReprocessed={(updated) => { setReprocessing(true); onUpdated(updated); }}
        />
      )}
    </>
  );
}
