import s from "./ResourcesPanel.module.css";

const HOST_LABELS = { web: "Web droplet", worker: "Worker droplet" };

function barClass(pct) {
  if (pct >= 80) return s.barRed;
  if (pct >= 60) return s.barAmber;
  return s.barGreen;
}

function Meter({ label, pct, usedMb, totalMb }) {
  return (
    <div className={s.meter}>
      <div className={s.meterHead}>
        <span>{label}</span>
        <span className={s.meterVal}>
          {usedMb} / {totalMb} MB ({pct}%)
        </span>
      </div>
      <div className={s.track}>
        <div
          className={`${s.bar} ${barClass(pct)}`}
          style={{ width: `${Math.min(100, pct)}%` }}
        />
      </div>
    </div>
  );
}

function HostCard({ h }) {
  return (
    <div className={s.card}>
      <div className={s.cardHead}>
        <span className={s.name}>{HOST_LABELS[h.host] ?? h.host}</span>
        <span className={`${s.sev} ${s[`sev_${h.severity}`] || ""}`}>
          {h.severity}
        </span>
      </div>
      {!h.online ? (
        <div className={s.offline}>{h.reasons?.join("; ") || "offline"}</div>
      ) : (
        <div className={s.cardBody}>
          <Meter
            label="Memory"
            pct={h.mem_pct}
            usedMb={h.mem_used_mb}
            totalMb={h.mem_total_mb}
          />
          <Meter
            label="Swap"
            pct={h.swap_pct}
            usedMb={h.swap_used_mb}
            totalMb={h.swap_total_mb}
          />
          <div className={s.loadRow}>
            <span>Load {h.load.join(" / ")}</span>
            <span className={s.muted}>
              {h.cpus} cpu{h.cpus === 1 ? "" : "s"}
              {h.host !== "web" && h.age_s != null && ` · ${h.age_s}s ago`}
            </span>
          </div>
          {h.reasons?.length > 0 && (
            <div className={s.reasons}>{h.reasons.join("; ")}</div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ResourcesPanel({ resources }) {
  if (!resources) return null;
  return (
    <div className={s.section}>
      <h3 className={s.title}>Host resources</h3>
      <div className={s.cards}>
        {resources.hosts.map((h) => (
          <HostCard key={h.host} h={h} />
        ))}
      </div>
    </div>
  );
}
