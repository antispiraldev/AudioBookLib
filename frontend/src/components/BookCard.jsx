import { useState } from "react";
import { deleteBook, retryBook } from "../api";
import EditModal from "./EditModal";

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
  synthesizing: "Generating audio…",
  complete: "Ready",
  error: "Error",
};

export default function BookCard({ book, isPlaying, onPlay, onDeleted, onUpdated }) {
  const [showEdit, setShowEdit] = useState(false);
  const [retryError, setRetryError] = useState("");

  const readySegments = book.segments.filter((s) => s.status === "ready").length;
  const failedSegments = book.segments.filter((s) => s.status === "error").length;
  const total = book.segments.length;
  const progress = total > 0 ? readySegments / total : 0;
  const canPlay = book.status === "complete" || (book.status === "synthesizing" && readySegments > 0);
  const isStuck = book.status === "synthesizing" && failedSegments > 0;

  async function handleDelete() {
    if (!confirm(`Delete "${book.title}"?`)) return;
    await deleteBook(book.id);
    onDeleted(book.id);
  }

  async function handleRetry() {
    setRetryError("");
    try {
      const updated = await retryBook(book.id);
      onUpdated(updated);
    } catch (e) {
      setRetryError(e.message);
    }
  }

  return (
    <>
      <div style={{ ...styles.card, outline: isPlaying ? `2px solid ${color(book.id)}` : "none" }}>
        <div style={{ ...styles.cover, background: color(book.id) }}>
          {isPlaying && <span style={styles.playingDot}>▶</span>}
        </div>

        <div style={styles.body}>
          <p style={styles.title} title={book.title}>{book.title}</p>

          <p style={styles.author}>
            {[book.author, book.year].filter(Boolean).join(" · ") || <span style={{ color: "var(--border)" }}>—</span>}
          </p>

          {book.genre && (
            <span style={styles.genre}>{book.genre}</span>
          )}

          {book.notes && (
            <p style={styles.notes} title={book.notes}>{book.notes}</p>
          )}

          <div style={styles.statusRow}>
            <span style={{ ...styles.badge, color: book.status === "error" ? "var(--danger)" : "var(--text-muted)" }}>
              {STATUS_LABEL[book.status] || book.status}
            </span>
            {book.status === "synthesizing" && total > 0 && (
              <span style={styles.count}>{readySegments}/{total}</span>
            )}
            {book.status === "error" && total > 0 && (
              <span style={{ ...styles.count, color: "var(--danger)" }}>
                {failedSegments}/{total} failed
              </span>
            )}
          </div>

          {book.status === "synthesizing" && total > 0 && (
            <div style={styles.progressTrack}>
              <div style={{ ...styles.progressBar, width: `${progress * 100}%` }} />
            </div>
          )}

          {retryError && <p style={styles.errorMsg}>{retryError}</p>}

          <div style={styles.actions}>
            {canPlay && (
              <button style={styles.playBtn} onClick={() => onPlay(book)}>
                {isPlaying ? "Playing" : "Play"}
              </button>
            )}
            {book.status === "error" && (
              <button style={styles.retryBtn} onClick={handleRetry}>Retry</button>
            )}
            {isStuck && (
              <button style={styles.retryBtn} onClick={handleRetry}>Refresh</button>
            )}
            <button style={styles.iconBtn} onClick={() => setShowEdit(true)} title="Edit">✏</button>
            <button style={styles.deleteBtn} onClick={handleDelete} title="Delete">✕</button>
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
    </>
  );
}

const styles = {
  card: {
    background: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius)",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    transition: "outline 0.15s",
  },
  cover: {
    height: 140,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  playingDot: {
    fontSize: 28,
    color: "rgba(255,255,255,0.9)",
  },
  body: {
    padding: "14px 16px",
    display: "flex",
    flexDirection: "column",
    gap: 3,
    flex: 1,
  },
  title: {
    fontWeight: 600,
    fontSize: 14,
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  author: {
    fontSize: 12,
    color: "var(--text-muted)",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  genre: {
    display: "inline-block",
    fontSize: 10,
    fontWeight: 500,
    background: "var(--surface2)",
    border: "1px solid var(--border)",
    color: "var(--text-muted)",
    borderRadius: 4,
    padding: "2px 6px",
    alignSelf: "flex-start",
    marginTop: 1,
  },
  notes: {
    fontSize: 11,
    color: "var(--text-muted)",
    fontStyle: "italic",
    marginTop: 1,
    lineHeight: 1.4,
  },
  statusRow: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    marginTop: 4,
  },
  badge: {
    fontSize: 11,
  },
  count: {
    fontSize: 11,
    color: "var(--text-muted)",
  },
  progressTrack: {
    height: 3,
    background: "var(--border)",
    borderRadius: 2,
    overflow: "hidden",
    marginTop: 2,
  },
  progressBar: {
    height: "100%",
    background: "var(--accent)",
    transition: "width 0.5s ease",
  },
  errorMsg: {
    fontSize: 11,
    color: "var(--danger)",
    marginTop: 2,
    wordBreak: "break-word",
  },
  actions: {
    display: "flex",
    gap: 5,
    marginTop: 8,
    alignItems: "center",
  },
  playBtn: {
    background: "var(--accent)",
    color: "#fff",
    borderRadius: 5,
    padding: "5px 12px",
    fontSize: 12,
    fontWeight: 500,
  },
  retryBtn: {
    background: "transparent",
    border: "1px solid var(--border)",
    color: "var(--text-muted)",
    borderRadius: 5,
    padding: "5px 10px",
    fontSize: 12,
  },
  iconBtn: {
    marginLeft: "auto",
    background: "transparent",
    color: "var(--text-muted)",
    fontSize: 13,
    padding: "4px 6px",
    borderRadius: 4,
    border: "none",
  },
  deleteBtn: {
    background: "transparent",
    color: "var(--text-muted)",
    fontSize: 13,
    padding: "4px 6px",
    borderRadius: 4,
    border: "none",
  },
};
