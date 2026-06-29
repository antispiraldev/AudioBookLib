import { useEffect, useRef, useState } from "react";
import { audioUrl } from "../api";

const SKIP = 15;

export default function AudioPlayer({ book, onClose }) {
  const audioRef = useRef(null);
  const pillsRef = useRef(null);
  const [segIdx, setSegIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);

  const readySegs = book.segments.filter((s) => s.status === "ready");
  const seg = readySegs[segIdx];

  useEffect(() => {
    setSegIdx(0);
    setPlaying(true);
  }, [book.id]);

  useEffect(() => {
    if (!seg || !audioRef.current) return;
    audioRef.current.src = audioUrl(seg.id);
    if (playing) audioRef.current.play().catch(() => {});
    // Scroll active pill into view
    const pill = pillsRef.current?.querySelector(`[data-idx="${segIdx}"]`);
    pill?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
  }, [seg?.id]);

  useEffect(() => {
    if (!audioRef.current) return;
    if (playing) audioRef.current.play().catch(() => {});
    else audioRef.current.pause();
  }, [playing]);

  function onEnded() {
    if (segIdx < readySegs.length - 1) {
      setSegIdx((i) => i + 1);
    } else {
      setPlaying(false);
    }
  }

  function onTimeUpdate() {
    const el = audioRef.current;
    if (el && el.duration) setProgress(el.currentTime / el.duration);
  }

  function seekBar(e) {
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    if (audioRef.current?.duration) {
      audioRef.current.currentTime = ratio * audioRef.current.duration;
    }
  }

  function skipBack() {
    const el = audioRef.current;
    if (!el) return;
    el.currentTime = Math.max(0, el.currentTime - SKIP);
  }

  function skipForward() {
    const el = audioRef.current;
    if (!el || !isFinite(el.duration)) return;
    const newTime = el.currentTime + SKIP;
    if (newTime >= el.duration) {
      if (segIdx < readySegs.length - 1) setSegIdx((i) => i + 1);
    } else {
      el.currentTime = newTime;
    }
  }

  const overallProgress = readySegs.length > 0
    ? (segIdx + progress) / readySegs.length
    : 0;

  return (
    <div style={styles.bar}>
      <audio
        ref={audioRef}
        onEnded={onEnded}
        onTimeUpdate={onTimeUpdate}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
      />

      {/* Segment pills */}
      <div ref={pillsRef} style={styles.pills}>
        {readySegs.map((s, i) => (
          <button
            key={s.id}
            data-idx={i}
            style={{
              ...styles.pill,
              background: i === segIdx ? "var(--accent)" : "var(--surface2)",
              color: i === segIdx ? "#fff" : "var(--text-muted)",
              border: i === segIdx ? "1px solid var(--accent)" : "1px solid var(--border)",
            }}
            onClick={() => setSegIdx(i)}
          >
            {i + 1}
          </button>
        ))}
      </div>

      {/* Info */}
      <div style={styles.info}>
        <p style={styles.title}>{book.title}</p>
        <p style={styles.sub}>
          {book.author ? `${book.author} · ` : ""}
          {segIdx + 1} / {readySegs.length}
        </p>
      </div>

      {/* Controls */}
      <div style={styles.controls}>
        <button style={styles.btn} onClick={skipBack} title="-15s">−15s</button>
        <button
          style={styles.btn}
          onClick={() => setSegIdx((i) => Math.max(0, i - 1))}
          disabled={segIdx === 0}
          title="Previous segment"
        >
          ◀◀
        </button>
        <button
          style={{ ...styles.btn, ...styles.playPause }}
          onClick={() => setPlaying((p) => !p)}
        >
          {playing ? "⏸" : "▶"}
        </button>
        <button
          style={styles.btn}
          onClick={() => setSegIdx((i) => Math.min(readySegs.length - 1, i + 1))}
          disabled={segIdx >= readySegs.length - 1}
          title="Next segment"
        >
          ▶▶
        </button>
        <button style={styles.btn} onClick={skipForward} title="+15s">+15s</button>
      </div>

      {/* Progress */}
      <div style={styles.progressWrapper}>
        <div style={styles.progressTrack} onClick={seekBar} title="Seek">
          <div style={{ ...styles.progressFill, width: `${progress * 100}%` }} />
        </div>
        <div style={styles.progressTrack} title="Overall progress">
          <div style={{ ...styles.overallFill, width: `${overallProgress * 100}%` }} />
        </div>
      </div>

      <button style={styles.closeBtn} onClick={onClose}>✕</button>
    </div>
  );
}

const styles = {
  bar: {
    position: "fixed",
    bottom: 0,
    left: 0,
    right: 0,
    background: "var(--surface)",
    borderTop: "1px solid var(--border)",
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "10px 20px",
    zIndex: 50,
  },
  pills: {
    display: "flex",
    gap: 4,
    overflowX: "auto",
    maxWidth: 200,
    scrollbarWidth: "none",
    flexShrink: 0,
    padding: "2px 0",
  },
  pill: {
    flexShrink: 0,
    width: 28,
    height: 24,
    borderRadius: 4,
    fontSize: 11,
    fontWeight: 500,
    cursor: "pointer",
    transition: "background 0.15s, color 0.15s",
    lineHeight: 1,
  },
  info: {
    minWidth: 0,
    flex: "0 0 160px",
  },
  title: {
    fontSize: 13,
    fontWeight: 600,
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  sub: {
    fontSize: 11,
    color: "var(--text-muted)",
    marginTop: 2,
  },
  controls: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    flexShrink: 0,
  },
  btn: {
    background: "transparent",
    color: "var(--text)",
    fontSize: 12,
    padding: "6px 9px",
    borderRadius: 5,
    border: "1px solid var(--border)",
    lineHeight: 1,
    whiteSpace: "nowrap",
  },
  playPause: {
    fontSize: 16,
    width: 40,
    height: 40,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 0,
  },
  progressWrapper: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 5,
    minWidth: 0,
  },
  progressTrack: {
    height: 4,
    background: "var(--border)",
    borderRadius: 2,
    overflow: "hidden",
    cursor: "pointer",
  },
  progressFill: {
    height: "100%",
    background: "var(--accent)",
    transition: "width 0.1s linear",
  },
  overallFill: {
    height: "100%",
    background: "var(--surface2)",
    transition: "width 0.3s ease",
  },
  closeBtn: {
    background: "transparent",
    color: "var(--text-muted)",
    fontSize: 16,
    padding: "4px 8px",
    borderRadius: 4,
    border: "none",
    flexShrink: 0,
  },
};
