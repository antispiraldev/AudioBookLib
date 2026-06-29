import { useState } from "react";
import { updateBook } from "../api";

export default function EditModal({ book, onClose, onSaved }) {
  const [form, setForm] = useState({
    title: book.title ?? "",
    author: book.author ?? "",
    genre: book.genre ?? "",
    year: book.year ?? "",
    notes: book.notes ?? "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.title.trim()) return;
    setLoading(true);
    setError("");
    try {
      const payload = {
        title: form.title.trim(),
        author: form.author.trim() || null,
        genre: form.genre.trim() || null,
        year: form.year ? parseInt(form.year, 10) : null,
        notes: form.notes.trim() || null,
      };
      const updated = await updateBook(book.id, payload);
      onSaved(updated);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={styles.overlay} onClick={onClose}>
      <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h2 style={styles.heading}>Edit Book</h2>
        <form onSubmit={handleSubmit} style={styles.form}>
          <label style={styles.label}>Title</label>
          <input
            style={styles.input}
            value={form.title}
            onChange={(e) => set("title", e.target.value)}
            required
          />

          <label style={styles.label}>Author</label>
          <input
            style={styles.input}
            placeholder="Optional"
            value={form.author}
            onChange={(e) => set("author", e.target.value)}
          />

          <div style={styles.row}>
            <div style={{ flex: 2 }}>
              <label style={styles.label}>Genre</label>
              <input
                style={styles.input}
                placeholder="e.g. Non-fiction"
                value={form.genre}
                list="genre-suggestions"
                onChange={(e) => set("genre", e.target.value)}
              />
              <datalist id="genre-suggestions">
                {["Fiction", "Non-fiction", "History", "Philosophy", "Science",
                  "Biography", "Politics", "Technology", "Economics"].map((g) => (
                  <option key={g} value={g} />
                ))}
              </datalist>
            </div>
            <div style={{ flex: 1 }}>
              <label style={styles.label}>Year</label>
              <input
                style={styles.input}
                type="number"
                placeholder="e.g. 1969"
                min="1000"
                max="2099"
                value={form.year}
                onChange={(e) => set("year", e.target.value)}
              />
            </div>
          </div>

          <label style={styles.label}>Notes</label>
          <textarea
            style={{ ...styles.input, ...styles.textarea }}
            placeholder="Your notes (optional)"
            value={form.notes}
            onChange={(e) => set("notes", e.target.value)}
          />

          {error && <p style={{ color: "var(--danger)", fontSize: 13 }}>{error}</p>}

          <div style={styles.actions}>
            <button type="button" style={styles.cancelBtn} onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              style={{ ...styles.submitBtn, opacity: loading ? 0.6 : 1 }}
              disabled={loading || !form.title.trim()}
            >
              {loading ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
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
    padding: 28,
    width: 440,
    maxWidth: "90vw",
  },
  heading: {
    fontSize: 18,
    fontWeight: 600,
    marginBottom: 20,
  },
  form: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  label: {
    fontSize: 11,
    color: "var(--text-muted)",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    marginBottom: 2,
    display: "block",
  },
  input: {
    width: "100%",
    background: "var(--surface2)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "9px 12px",
    color: "var(--text)",
    fontSize: 14,
    outline: "none",
  },
  textarea: {
    resize: "vertical",
    minHeight: 80,
    fontFamily: "inherit",
  },
  row: {
    display: "flex",
    gap: 10,
  },
  actions: {
    display: "flex",
    gap: 8,
    justifyContent: "flex-end",
    marginTop: 8,
  },
  cancelBtn: {
    background: "transparent",
    border: "1px solid var(--border)",
    color: "var(--text-muted)",
    borderRadius: 6,
    padding: "8px 16px",
    fontSize: 14,
  },
  submitBtn: {
    background: "var(--accent)",
    color: "#fff",
    borderRadius: 6,
    padding: "8px 18px",
    fontSize: 14,
    fontWeight: 500,
    transition: "opacity 0.2s",
  },
};
