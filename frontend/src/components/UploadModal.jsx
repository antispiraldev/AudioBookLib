import { useState, useRef } from "react";
import { uploadBook } from "../api";
import s from "./Modal.module.css";

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
    <div className={s.overlay} onClick={onClose}>
      <div className={s.modal} onClick={(e) => e.stopPropagation()}>
        <h2 className={s.heading}>Add Book</h2>
        <form onSubmit={handleSubmit} className={s.form}>
          <div
            className={`${s.dropzone} ${file ? s.dropzoneActive : ""}`}
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
              <span className={s.fileName}>{file.name}</span>
            ) : (
              <span className={s.placeholder}>Click to select a PDF</span>
            )}
          </div>

          <input
            className={s.input}
            placeholder="Title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
          />
          <input
            className={s.input}
            placeholder="Author (optional)"
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
          />

          {error && <p className={s.errorText}>{error}</p>}

          <div className={s.actions}>
            <button type="button" className={s.cancelBtn} onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              className={s.submitBtn}
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
