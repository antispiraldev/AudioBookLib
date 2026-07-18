import { useState } from "react";
import s from "./EventsPanel.module.css";

function fmtTime(iso) {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// One event row — click to expand the traceback when present.
function EventRow({ ev }) {
  const [open, setOpen] = useState(false);
  const hasTrace = Boolean(ev.traceback);
  return (
    <div className={s.item}>
      <div
        className={`${s.line} ${hasTrace ? s.clickable : ""}`}
        onClick={hasTrace ? () => setOpen((o) => !o) : undefined}
      >
        <span className={`${s.level} ${s[`lvl_${ev.level}`] || ""}`}>
          {ev.level}
        </span>
        <span className={s.task}>{ev.task}</span>
        {ev.book_title && <span className={s.book}>{ev.book_title}</span>}
        <span className={s.msg}>{ev.message}</span>
        <span className={s.time}>{fmtTime(ev.created_at)}</span>
        {hasTrace && <span className={s.chev}>{open ? "▲" : "▼"}</span>}
      </div>
      {open && hasTrace && <pre className={s.trace}>{ev.traceback}</pre>}
    </div>
  );
}

export default function EventsPanel({ events }) {
  const [onlyErrors, setOnlyErrors] = useState(false);
  const shown = onlyErrors
    ? events.filter((e) => e.level === "error")
    : events;

  return (
    <div className={s.section}>
      <div className={s.head}>
        <h3 className={s.title}>Pipeline events</h3>
        <label className={s.toggle}>
          <input
            type="checkbox"
            checked={onlyErrors}
            onChange={(e) => setOnlyErrors(e.target.checked)}
          />
          Errors only
        </label>
      </div>
      {shown.length === 0 ? (
        <div className={s.empty}>No events. Nothing has gone wrong.</div>
      ) : (
        <div className={s.list}>
          {shown.map((ev) => (
            <EventRow key={ev.id} ev={ev} />
          ))}
        </div>
      )}
    </div>
  );
}
