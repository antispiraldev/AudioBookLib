import { useEffect, useState } from "react";
import { updateBook, suggestBook, fetchNarrators } from "../api";
import s from "./Modal.module.css";

export default function EditModal({ book, onClose, onSaved }) {
  const [form, setForm] = useState({
    title: book.title ?? "",
    author: book.author ?? "",
    genre: book.genre ?? "",
    year: book.year ?? "",
    notes: book.notes ?? "",
    tts_narrator: book.tts_narrator ?? "",
    tts_instructions: book.tts_instructions ?? "",
  });
  const [narrators, setNarrators] = useState([]);
  const [loading, setLoading] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchNarrators()
      .then((d) => setNarrators(d.presets))
      .catch(() => setNarrators([]));
  }, []);

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function handleSuggest() {
    setSuggesting(true);
    setError("");
    try {
      const suggestion = await suggestBook(book.id);
      setForm((f) => ({
        title: suggestion.title ?? f.title,
        author: suggestion.author ?? f.author,
        genre: suggestion.genre ?? f.genre,
        year: suggestion.year != null ? String(suggestion.year) : f.year,
        notes: suggestion.notes ?? f.notes,
        tts_narrator: f.tts_narrator,
        tts_instructions: f.tts_instructions,
      }));
    } catch (err) {
      setError(err.message);
    } finally {
      setSuggesting(false);
    }
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
        tts_narrator: form.tts_narrator || null,
        tts_instructions: form.tts_instructions.trim() || null,
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
    <div className={s.overlay} onClick={onClose}>
      <div className={s.modal} onClick={(e) => e.stopPropagation()}>
        <div className={s.headingRow}>
          <h2 className={s.heading}>Edit Book</h2>
          <button
            type="button"
            className={s.suggestBtn}
            disabled={suggesting}
            onClick={handleSuggest}
          >
            {suggesting ? "Suggesting…" : "✦ Suggest"}
          </button>
        </div>
        <form onSubmit={handleSubmit} className={s.form}>
          <div>
            <label className={s.label}>Title</label>
            <input
              className={s.input}
              value={form.title}
              onChange={(e) => set("title", e.target.value)}
              required
            />
          </div>

          <div>
            <label className={s.label}>Author</label>
            <input
              className={s.input}
              placeholder="Optional"
              value={form.author}
              onChange={(e) => set("author", e.target.value)}
            />
          </div>

          <div className={s.row}>
            <div className={s.col2}>
              <label className={s.label}>Genre</label>
              <input
                className={s.input}
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
            <div className={s.col1}>
              <label className={s.label}>Year</label>
              <input
                className={s.input}
                type="number"
                placeholder="e.g. 1969"
                min="1000"
                max="2099"
                value={form.year}
                onChange={(e) => set("year", e.target.value)}
              />
            </div>
          </div>

          <div>
            <label className={s.label}>Notes</label>
            <textarea
              className={`${s.input} ${s.textarea}`}
              placeholder="Your notes (optional)"
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
            />
          </div>

          <div>
            <label className={s.label}>Narrator voice</label>
            <select
              className={s.input}
              value={form.tts_narrator}
              onChange={(e) => set("tts_narrator", e.target.value)}
            >
              <option value="">Default</option>
              {narrators.map((n) => (
                <option key={n.key} value={n.key}>
                  {n.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className={s.label}>Custom narration instructions</label>
            <textarea
              className={`${s.input} ${s.textarea}`}
              placeholder="Advanced: overrides the narrator style above with your own wording. Leave blank to use the selected voice."
              value={form.tts_instructions}
              onChange={(e) => set("tts_instructions", e.target.value)}
            />
          </div>

          {error && <p className={s.errorText}>{error}</p>}

          <div className={s.actions}>
            <button type="button" className={s.cancelBtn} onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              className={s.submitBtn}
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
