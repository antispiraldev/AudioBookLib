import { useEffect, useRef, useState } from "react";
import {
  updateBook,
  suggestBook,
  fetchNarrators,
  fetchBook,
  generateNarration,
  deleteNarration,
} from "../api";
import s from "./Modal.module.css";

function narrationLabel(n) {
  if (n.ready) return "Ready";
  if (n.segments_total > 0) return `Generating ${n.segments_ready}/${n.segments_total}`;
  return "Generating…";
}

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
  const [narrations, setNarrations] = useState(book.narrations ?? []);
  const [busyVoice, setBusyVoice] = useState(null);
  const [loading, setLoading] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchNarrators()
      .then((d) => setNarrators(d.presets))
      .catch(() => setNarrators([]));
  }, []);

  // A complete book can carry extra narrations. Only their existence enables
  // the listener toggle, and only a complete book has base audio to render from.
  const canNarrate = book.status === "complete";
  const primaryKey = narrations.find((n) => n.primary)?.narrator;
  const existingKeys = new Set(narrations.map((n) => n.narrator));
  const addable = narrators.filter(
    (n) => n.key !== primaryKey && !existingKeys.has(n.key)
  );
  const generating = narrations.some((n) => !n.primary && !n.ready);

  // While an alternate is still rendering, poll the book so its progress and
  // eventual readiness show up — generation doesn't flip book.status, so the
  // app-level poll won't cover this.
  const onSavedRef = useRef(onSaved);
  onSavedRef.current = onSaved;
  useEffect(() => {
    if (!generating) return;
    const id = setInterval(async () => {
      try {
        const fresh = await fetchBook(book.id);
        setNarrations(fresh.narrations ?? []);
        onSavedRef.current?.(fresh);
      } catch {
        // transient — keep polling
      }
    }, 4000);
    return () => clearInterval(id);
  }, [generating, book.id]);

  async function handleGenerate(key) {
    setBusyVoice(key);
    setError("");
    try {
      const updated = await generateNarration(book.id, key);
      setNarrations(updated.narrations ?? []);
      onSaved?.(updated);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyVoice(null);
    }
  }

  async function handleRemoveNarration(key) {
    setBusyVoice(key);
    setError("");
    try {
      const updated = await deleteNarration(book.id, key);
      setNarrations(updated.narrations ?? []);
      onSaved?.(updated);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyVoice(null);
    }
  }

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

          {canNarrate && (
            <div>
              <label className={s.label}>Alternate narrations</label>
              <div className={s.narrList}>
                {narrations.map((n) => (
                  <div key={n.narrator} className={s.narrRow}>
                    <span className={s.narrName}>
                      {n.label}
                      {n.primary ? " · primary" : ""}
                    </span>
                    {!n.primary && (
                      <span className={s.narrStatus} data-ready={n.ready}>
                        {narrationLabel(n)}
                      </span>
                    )}
                    {!n.primary && (
                      <button
                        type="button"
                        className={s.narrAction}
                        disabled={busyVoice === n.narrator}
                        onClick={() => handleRemoveNarration(n.narrator)}
                      >
                        {busyVoice === n.narrator ? "…" : "Remove"}
                      </button>
                    )}
                  </div>
                ))}
                {addable.map((n) => (
                  <div key={n.key} className={s.narrRow}>
                    <span className={s.narrName}>{n.label}</span>
                    <button
                      type="button"
                      className={s.narrAction}
                      disabled={busyVoice === n.key}
                      onClick={() => handleGenerate(n.key)}
                    >
                      {busyVoice === n.key ? "Starting…" : "Generate"}
                    </button>
                  </div>
                ))}
              </div>
              <p className={s.narrHint}>
                Render the book in another voice so listeners can switch between
                narrations in the player. Uses TTS credits.
              </p>
            </div>
          )}

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
