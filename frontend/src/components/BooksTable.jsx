import { useMemo, useState } from "react";
import s from "./BooksTable.module.css";

// Status → badge tone. Anything unlisted renders neutral.
const STATUS_TONE = {
  pending: "neutral",
  processing: "working",
  review: "review",
  synthesizing: "working",
  complete: "good",
  error: "error",
};

function fmtDate(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

const COLUMNS = [
  { key: "title", label: "Title" },
  { key: "status", label: "Status" },
  { key: "genre", label: "Genre" },
  { key: "owner_email", label: "Owner" },
  { key: "progress", label: "Segments" },
  { key: "page_count", label: "Pages" },
  { key: "created_at", label: "Added" },
];

// Sort accessors — "progress" sorts by completion fraction.
function sortValue(book, key) {
  if (key === "progress") {
    return book.segments_total ? book.segments_ready / book.segments_total : -1;
  }
  const v = book[key];
  if (typeof v === "string") return v.toLowerCase();
  return v ?? -Infinity;
}

export default function BooksTable({ books }) {
  const [sort, setSort] = useState({ key: "created_at", dir: "desc" });

  const sorted = useMemo(() => {
    const copy = [...books];
    copy.sort((a, b) => {
      const av = sortValue(a, sort.key);
      const bv = sortValue(b, sort.key);
      if (av < bv) return sort.dir === "asc" ? -1 : 1;
      if (av > bv) return sort.dir === "asc" ? 1 : -1;
      return 0;
    });
    return copy;
  }, [books, sort]);

  function toggleSort(key) {
    setSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === "asc" ? "desc" : "asc" }
        : { key, dir: key === "created_at" ? "desc" : "asc" }
    );
  }

  if (books.length === 0) {
    return <div className={s.empty}>No books yet.</div>;
  }

  return (
    <div className={s.wrap}>
      <table className={s.table}>
        <thead>
          <tr>
            {COLUMNS.map(({ key, label }) => (
              <th
                key={key}
                className={s.th}
                onClick={() => toggleSort(key)}
                aria-sort={
                  sort.key === key
                    ? sort.dir === "asc"
                      ? "ascending"
                      : "descending"
                    : "none"
                }
              >
                {label}
                {sort.key === key && (
                  <span className={s.caret}>{sort.dir === "asc" ? "▲" : "▼"}</span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((b) => {
            const tone = STATUS_TONE[b.status] || "neutral";
            return (
              <tr key={b.id} className={s.row}>
                <td className={s.title}>
                  <span className={s.titleText}>{b.title}</span>
                  {b.author && <span className={s.author}>{b.author}</span>}
                  {b.hidden && <span className={s.hidden}>hidden</span>}
                </td>
                <td>
                  <span className={`${s.badge} ${s[`tone_${tone}`]}`}>
                    {b.status}
                  </span>
                </td>
                <td className={s.muted}>{b.genre || "—"}</td>
                <td className={s.muted}>{b.owner_email || "—"}</td>
                <td>
                  {b.segments_total ? (
                    <span className={b.segments_error ? s.progErr : s.muted}>
                      {b.segments_ready}/{b.segments_total}
                      {b.segments_error ? ` · ${b.segments_error} err` : ""}
                    </span>
                  ) : (
                    <span className={s.muted}>—</span>
                  )}
                </td>
                <td className={s.muted}>{b.page_count ?? "—"}</td>
                <td className={s.muted}>{fmtDate(b.created_at)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
