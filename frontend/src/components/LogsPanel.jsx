import { useEffect, useRef, useState } from "react";
import { fetchAdminLogs } from "../api";
import s from "./LogsPanel.module.css";

const SOURCES = [
  { key: "web", label: "Web" },
  { key: "worker", label: "Worker" },
];

export default function LogsPanel() {
  const [source, setSource] = useState("web");
  const [lines, setLines] = useState(null);
  const [error, setError] = useState(null);
  const boxRef = useRef(null);
  const pinnedRef = useRef(true); // stick to the newest lines unless the user scrolls up

  useEffect(() => {
    let dead = false;
    setLines(null);
    pinnedRef.current = true;

    const load = async () => {
      try {
        const data = await fetchAdminLogs({ source, limit: 300 });
        if (dead) return;
        setLines(data.lines);
        setError(null);
      } catch (e) {
        if (!dead) setError(e.message);
      }
    };
    load();
    const id = setInterval(load, 10000);
    return () => {
      dead = true;
      clearInterval(id);
    };
  }, [source]);

  useEffect(() => {
    const box = boxRef.current;
    if (box && pinnedRef.current) box.scrollTop = box.scrollHeight;
  }, [lines]);

  const onScroll = () => {
    const box = boxRef.current;
    if (!box) return;
    pinnedRef.current =
      box.scrollHeight - box.scrollTop - box.clientHeight < 40;
  };

  return (
    <div className={s.section}>
      <div className={s.head}>
        <h3 className={s.title}>Logs</h3>
        <div className={s.tabs}>
          {SOURCES.map(({ key, label }) => (
            <button
              key={key}
              className={`${s.tab} ${source === key ? s.tabActive : ""}`}
              onClick={() => setSource(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      {error && <div className={s.error}>Couldn't load logs: {error}</div>}
      <pre ref={boxRef} onScroll={onScroll} className={s.box}>
        {lines === null
          ? "Loading…"
          : lines.length === 0
            ? "No log lines yet."
            : lines.join("\n")}
      </pre>
    </div>
  );
}
