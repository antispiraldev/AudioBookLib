import { useEffect, useState } from "react";
import { fetchBookSegments, updateSegment, synthesizeBook } from "../api";

export default function ReviewModal({ book, onClose, onApproved }) {
  const [segments, setSegments] = useState(null);
  const [drafts, setDrafts] = useState({});
  const [savingOrder, setSavingOrder] = useState(null);
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    fetchBookSegments(book.id)
      .then((segs) => {
        if (!alive) return;
        setSegments(segs);
        setDrafts(Object.fromEntries(segs.map((s) => [s.order, s.text])));
      })
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [book.id]);

  function setDraft(order, text) {
    setDrafts((d) => ({ ...d, [order]: text }));
  }

  async function handleSaveSegment(seg) {
    setSavingOrder(seg.order);
    setError("");
    try {
      const updated = await updateSegment(book.id, seg.order, drafts[seg.order]);
      setSegments((segs) =>
        segs.map((s) => (s.order === seg.order ? updated : s))
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setSavingOrder(null);
    }
  }

  async function handleApprove() {
    setApproving(true);
    setError("");
    try {
      const updated = await synthesizeBook(book.id);
      onApproved(updated);
      onClose();
    } catch (e) {
      setError(e.message);
      setApproving(false);
    }
  }

  const total = segments?.length ?? 0;
  const chars = segments?.reduce((n, s) => n + s.text.length, 0) ?? 0;
  // Mirror backend MIN_CHARS_PER_PAGE: too little text means no text layer.
  const pages = book.page_count ?? 0;
  const likelyScanned = segments && pages > 0 && chars / pages < 200;

  return (
    <div style={styles.overlay} onClick={onClose}>
      <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div style={styles.headingRow}>
          <div>
            <h2 style={styles.heading}>Review “{book.title}”</h2>
            {segments && (
              <p style={styles.sub}>
                {total} segment{total === 1 ? "" : "s"} · {chars.toLocaleString()} chars
              </p>
            )}
          </div>
          <button type="button" style={styles.closeBtn} onClick={onClose}>✕</button>
        </div>

        <p style={styles.hint}>
          Read through the cleaned text and fix any artifacts before generating
          audio. Editing a segment re-queues just that segment.
        </p>

        {likelyScanned && (
          <p style={styles.warn}>
            ⚠ Likely a scanned PDF — only {chars.toLocaleString()} characters
            across {pages} pages. This book probably has no text layer and needs
            OCR; synthesizing now would produce near-silence. Don't approve.
          </p>
        )}

        <div style={styles.list}>
          {error && <p style={styles.error}>{error}</p>}
          {!segments && !error && <p style={styles.muted}>Loading…</p>}
          {segments?.map((seg) => {
            const dirty = drafts[seg.order] !== seg.text;
            return (
              <div key={seg.order}>
                {seg.chapter_title && (
                  <p style={styles.chapterMark}>{seg.chapter_title}</p>
                )}
              <div style={styles.segment}>
                <div style={styles.segHead}>
                  <span style={styles.segNum}>#{seg.order + 1}</span>
                  <span style={styles.segStatus}>{seg.status}</span>
                </div>
                <textarea
                  style={styles.segText}
                  value={drafts[seg.order] ?? ""}
                  onChange={(e) => setDraft(seg.order, e.target.value)}
                />
                {dirty && (
                  <button
                    type="button"
                    style={styles.saveBtn}
                    disabled={savingOrder === seg.order}
                    onClick={() => handleSaveSegment(seg)}
                  >
                    {savingOrder === seg.order ? "Saving…" : "Save segment"}
                  </button>
                )}
              </div>
              </div>
            );
          })}
        </div>

        <div style={styles.actions}>
          <button type="button" style={styles.cancelBtn} onClick={onClose}>
            Close
          </button>
          <button
            type="button"
            style={{ ...styles.approveBtn, opacity: approving || !total ? 0.6 : 1 }}
            disabled={approving || !total}
            onClick={handleApprove}
          >
            {approving ? "Starting…" : "Approve & Synthesize"}
          </button>
        </div>
      </div>
    </div>
  );
}

const styles = {
  overlay: {
    position: "fixed",
    inset: 0,
    background: "rgba(0,0,0,0.7)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 100,
  },
  modal: {
    background: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius)",
    padding: 24,
    width: 640,
    maxWidth: "92vw",
    maxHeight: "88vh",
    display: "flex",
    flexDirection: "column",
  },
  headingRow: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 12,
  },
  heading: { fontSize: 18, fontWeight: 600 },
  sub: { fontSize: 12, color: "var(--text-muted)", marginTop: 2 },
  closeBtn: {
    background: "transparent",
    border: "none",
    color: "var(--text-muted)",
    fontSize: 15,
    cursor: "pointer",
  },
  hint: {
    fontSize: 12,
    color: "var(--text-muted)",
    margin: "10px 0 12px",
    lineHeight: 1.5,
  },
  list: {
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
    gap: 12,
    paddingRight: 4,
    flex: 1,
  },
  muted: { fontSize: 13, color: "var(--text-muted)" },
  error: { fontSize: 13, color: "var(--danger)" },
  warn: {
    fontSize: 12.5,
    lineHeight: 1.5,
    color: "var(--text)",
    background: "var(--surface2)",
    border: "1px solid var(--danger)",
    borderRadius: 8,
    padding: "10px 12px",
    margin: "0 0 12px",
  },
  segment: {
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: 10,
    background: "var(--surface2)",
  },
  chapterMark: {
    fontSize: 11,
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    color: "var(--accent)",
    margin: "6px 0 6px 2px",
  },
  segHead: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 6,
  },
  segNum: { fontSize: 11, fontWeight: 600, color: "var(--text-muted)" },
  segStatus: {
    fontSize: 10,
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    color: "var(--text-muted)",
  },
  segText: {
    width: "100%",
    minHeight: 96,
    resize: "vertical",
    background: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "8px 10px",
    color: "var(--text)",
    fontSize: 13,
    lineHeight: 1.5,
    fontFamily: "inherit",
    outline: "none",
  },
  saveBtn: {
    marginTop: 6,
    background: "transparent",
    border: "1px solid var(--border)",
    color: "var(--accent)",
    borderRadius: 5,
    padding: "5px 10px",
    fontSize: 12,
    cursor: "pointer",
  },
  actions: {
    display: "flex",
    gap: 8,
    justifyContent: "flex-end",
    marginTop: 16,
    paddingTop: 14,
    borderTop: "1px solid var(--border)",
  },
  cancelBtn: {
    background: "transparent",
    border: "1px solid var(--border)",
    color: "var(--text-muted)",
    borderRadius: 6,
    padding: "8px 16px",
    fontSize: 14,
  },
  approveBtn: {
    background: "var(--accent)",
    color: "#fff",
    borderRadius: 6,
    padding: "8px 18px",
    fontSize: 14,
    fontWeight: 500,
    transition: "opacity 0.2s",
  },
};
