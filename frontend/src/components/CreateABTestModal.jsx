import { useState } from "react";
import { createABTest } from "../api";
import s from "./Modal.module.css";

// A clip picker for one side of the test — a label plus an audio file.
function ClipField({ side, label, file, onLabel, onFile }) {
  return (
    <div className={s.row}>
      <div className={s.col1}>
        <label className={s.label}>Clip {side} label</label>
        <input
          className={s.input}
          placeholder={side === "A" ? "e.g. onyx" : "e.g. alloy"}
          value={label}
          onChange={(e) => onLabel(e.target.value)}
          required
        />
      </div>
      <div className={s.col1}>
        <label className={s.label}>Clip {side} audio</label>
        <input
          className={s.input}
          type="file"
          accept="audio/*,.mp3"
          onChange={(e) => onFile(e.target.files[0] || null)}
          required
        />
      </div>
    </div>
  );
}

export default function CreateABTestModal({ onClose, onCreated }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [labelA, setLabelA] = useState("");
  const [labelB, setLabelB] = useState("");
  const [fileA, setFileA] = useState(null);
  const [fileB, setFileB] = useState(null);
  const [published, setPublished] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const ready =
    title.trim() && labelA.trim() && labelB.trim() && fileA && fileB;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!ready) return;
    setLoading(true);
    setError("");
    try {
      const fd = new FormData();
      fd.append("title", title.trim());
      if (description.trim()) fd.append("description", description.trim());
      fd.append("label_a", labelA.trim());
      fd.append("label_b", labelB.trim());
      fd.append("file_a", fileA);
      fd.append("file_b", fileB);
      fd.append("published", published ? "true" : "false");
      const test = await createABTest(fd);
      onCreated(test);
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
        <h2 className={s.heading}>New A/B test</h2>
        <form onSubmit={handleSubmit} className={s.form}>
          <div>
            <label className={s.label}>Title</label>
            <input
              className={s.input}
              placeholder="e.g. The Prince — opening passage"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
            />
          </div>
          <div>
            <label className={s.label}>Description (optional)</label>
            <textarea
              className={`${s.input} ${s.textarea}`}
              placeholder="What are we comparing?"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <ClipField
            side="A"
            label={labelA}
            file={fileA}
            onLabel={setLabelA}
            onFile={setFileA}
          />
          <ClipField
            side="B"
            label={labelB}
            file={fileB}
            onLabel={setLabelB}
            onFile={setFileB}
          />

          <label className={s.label} style={{ display: "flex", gap: 8, textTransform: "none", letterSpacing: 0, fontSize: 13, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={published}
              onChange={(e) => setPublished(e.target.checked)}
            />
            Publish immediately (visible to people with access)
          </label>

          {error && <p className={s.errorText}>{error}</p>}

          <div className={s.actions}>
            <button type="button" className={s.cancelBtn} onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              className={s.submitBtn}
              disabled={loading || !ready}
            >
              {loading ? "Creating…" : "Create test"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
