import s from "./WorkersPanel.module.css";

function fmtDuration(sec) {
  if (sec == null) return "—";
  const n = Math.round(sec);
  if (n < 60) return `${n}s`;
  if (n < 3600) return `${Math.floor(n / 60)}m ${n % 60}s`;
  const h = Math.floor(n / 3600);
  if (h < 48) return `${h}h ${Math.floor((n % 3600) / 60)}m`;
  return `${Math.floor(h / 24)}d ${h % 24}h`;
}

// "celery@aedo-worker-2" → "aedo-worker-2"
function shortName(name) {
  return name.includes("@") ? name.split("@")[1] : name;
}

// "app.tasks.ingest_book" → "ingest_book"
function shortTask(task) {
  return task ? task.split(".").pop() : "?";
}

export default function WorkersPanel({ workers }) {
  if (!workers) return null;
  const { broker_reachable, queue_depth, workers: list } = workers;

  return (
    <div className={s.section}>
      <div className={s.head}>
        <h3 className={s.title}>Workers & queue</h3>
        <span className={s.queue}>
          Queue:{" "}
          <strong className={queue_depth > 0 ? s.queueBusy : ""}>
            {queue_depth ?? "—"}
          </strong>{" "}
          waiting
        </span>
      </div>

      {!broker_reachable && (
        <div className={s.warn}>
          Broker unreachable — no queue or worker data.
        </div>
      )}

      {broker_reachable && list.length === 0 && (
        <div className={s.warn}>
          No workers responding. Uploads will queue but nothing is processing.
        </div>
      )}

      <div className={s.cards}>
        {list.map((w) => (
          <div key={w.name} className={s.card}>
            <div className={s.cardHead}>
              <span className={s.dot} />
              <span className={s.name}>{shortName(w.name)}</span>
              <span className={s.meta}>
                {w.concurrency != null && `${w.concurrency} slots`}
                {w.uptime_s != null && ` · up ${fmtDuration(w.uptime_s)}`}
              </span>
            </div>
            <div className={s.cardBody}>
              {w.active.length === 0 ? (
                <span className={s.idle}>idle</span>
              ) : (
                w.active.map((t, i) => (
                  <div key={i} className={s.task}>
                    <span className={s.taskName}>{shortTask(t.task)}</span>
                    {Array.isArray(t.args) && t.args.length > 0 && (
                      <span className={s.taskArgs}>
                        ({t.args.join(", ")})
                      </span>
                    )}
                    <span className={s.taskTime}>
                      {fmtDuration(t.runtime_s)}
                    </span>
                  </div>
                ))
              )}
              <div className={s.counts}>
                {w.reserved > 0 && <span>{w.reserved} reserved</span>}
                <span>{w.processed} done since start</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
