import { useEffect, useState, useCallback } from "react";
import { fetchAdminSummary, fetchAdminBooks } from "../api";
import BooksTable from "./BooksTable";
import s from "./AdminPanel.module.css";

// Order + display labels for the status strip. Kept in sync with the backend's
// BOOK_STATUSES. "error" is styled as a warning tile so it stands out.
const STATUS_META = [
  { key: "pending", label: "Pending" },
  { key: "processing", label: "Processing" },
  { key: "review", label: "In review" },
  { key: "synthesizing", label: "Synthesizing" },
  { key: "complete", label: "Complete" },
  { key: "error", label: "Errored" },
];

export default function AdminPanel() {
  const [summary, setSummary] = useState(null);
  const [books, setBooks] = useState([]);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      const [sum, bks] = await Promise.all([
        fetchAdminSummary(),
        fetchAdminBooks(),
      ]);
      setSummary(sum);
      setBooks(bks);
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    load();
    // Refresh a little slower than the library's 3s poll — this is a monitor,
    // not an interaction surface.
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  const counts = summary?.by_status ?? {};

  return (
    <div className={s.panel}>
      <div className={s.head}>
        <h2 className={s.title}>Pipeline</h2>
        {summary && (
          <span className={s.total}>{summary.total} books total</span>
        )}
      </div>

      {error && <div className={s.error}>Couldn't load summary: {error}</div>}

      <div className={s.tiles}>
        {STATUS_META.map(({ key, label }) => {
          const n = counts[key] ?? 0;
          const highlight = key === "error" && n > 0;
          return (
            <div
              key={key}
              className={`${s.tile} ${highlight ? s.tileError : ""}`}
            >
              <div className={s.count}>{summary ? n : "—"}</div>
              <div className={s.label}>{label}</div>
            </div>
          );
        })}
      </div>

      <div className={s.section}>
        <h3 className={s.sectionTitle}>Books</h3>
        <BooksTable books={books} />
      </div>
    </div>
  );
}
