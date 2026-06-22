import { useState, useRef } from "react";
import { uploadBook } from "../api";

export default function UploadModal({ onClose, onUploaded }) {
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef();

  async function handleSubmit(e) {
    e.preventDefault();
    if (!file || !title.trim()) return;
    setLoading(true);
    setError("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("title", title.trim());
      if (author.trim()) fd.append("author", author.trim());
      const book = await uploadBook(fd);
      onUploaded(book);
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
        <h2 style={styles.heading}>Add Book</h2>
        <form onSubmit={handleSubmit} style={styles.form}>
          <div
            style={{
              ...styles.dropzone,
              borderColor: file ? "var(--accent)" : "var(--border)",
            }}
            onClick={() => inputRef.current.click()}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".pdf"
              style={{ display: "none" }}
              onChange={(e) => {
                const f = e.target.files[0];
                if (f) {
                  setFile(f);
                  if (!title) setTitle(f.name.replace(/\.pdf$/i, ""));
                }
              }}
            />
            {file ? (
              <span style={{ color: "var(--accent)" }}>{file.name}</span>
            ) : (
              <span style={{ color: "var(--text-muted)" }}>Click to select a PDF</span>
            )}
          </div>

          <input
            style={styles.input}
            placeholder="Title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
          />
          <input
            style={styles.input}
            placeholder="Author (optional)"
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
          />

          {error && <p style={{ color: "var(--danger)", fontSize: 13 }}>{error}</p>}

          <div style={styles.actions}>
            <button type="button" style={styles.cancelBtn} onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              style={{ ...styles.submitBtn, opacity: loading ? 0.6 : 1 }}
              disabled={loading || !file || !title.trim()}
            >
              {loading ? "Uploading…" : "Upload & Generate"}
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
    width: 420,
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
    gap: 12,
  },
  dropzone: {
    border: "2px dashed",
    borderRadius: "var(--radius)",
    padding: "20px 16px",
    textAlign: "center",
    cursor: "pointer",
    fontSize: 14,
    transition: "border-color 0.2s",
  },
  input: {
    background: "var(--surface2)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "10px 12px",
    color: "var(--text)",
    fontSize: 14,
    outline: "none",
  },
  actions: {
    display: "flex",
    gap: 8,
    justifyContent: "flex-end",
    marginTop: 4,
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
