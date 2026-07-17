import { useState } from "react";
import { reprocessBook } from "../api";
import s from "./Modal.module.css";

export default function ReprocessModal({ book, onClose, onReprocessed }) {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    setLoading(true);
    setError("");
    try {
      const updated = await reprocessBook(book.id, file);
      onReprocessed(updated);
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
        <div className={s.headingRow}>
          <h2 className={s.heading}>Reprocess Book</h2>
        </div>

        <div className={s.form}>
          <p className={s.label}>
            Re-extracts and re-cleans “{book.title}” with the current pipeline,
            then returns it to review. Existing audio will be cleared and must be
            regenerated on approval.
          </p>

          <div>
            <label className={s.label}>Replace PDF (optional)</label>
            <input
              className={s.input}
              type="file"
              accept="application/pdf"
              onChange={(e) => setFile(e.target.files[0] || null)}
            />
            <p className={s.label} style={{ opacity: 0.7 }}>
              Only needed if the original PDF is no longer on the server.
            </p>
          </div>

          {error && <p className={s.errorText}>{error}</p>}

          <div className={s.actions}>
            <button type="button" className={s.cancelBtn} onClick={onClose}>
              Cancel
            </button>
            <button
              type="button"
              className={s.submitBtn}
              disabled={loading}
              onClick={submit}
            >
              {loading ? "Reprocessing…" : "Reprocess"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
