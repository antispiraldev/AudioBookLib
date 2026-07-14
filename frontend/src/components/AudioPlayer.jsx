import { useEffect, useRef, useState } from "react";
import { audioUrl } from "../api";
import s from "./AudioPlayer.module.css";

const SKIP = 15;
const SPEEDS = [1, 1.25, 1.5, 1.75, 2, 0.75];

// Same palette as BookCard so the player cover matches the library card.
const PALETTE = [
  "#7c6af7", "#5b8af5", "#4caf82", "#e07c5b",
  "#b55be0", "#e0b05b", "#5bb8e0", "#e05b84",
];
const coverColor = (id) => PALETTE[id % PALETTE.length];

function fmt(t) {
  if (!isFinite(t) || t < 0) return "0:00";
  const m = Math.floor(t / 60);
  const sec = Math.floor(t % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

/* ---- Inline icons (self-contained, no external assets) ---- */
const ic = { width: 22, height: 22, viewBox: "0 0 24 24", fill: "currentColor" };
const Play = () => (<svg {...ic}><path d="M8 5v14l11-7z" /></svg>);
const Pause = () => (<svg {...ic}><path d="M6 5h4v14H6zm8 0h4v14h-4z" /></svg>);
const Prev = () => (<svg {...ic}><path d="M6 6h2v12H6zm3.5 6L18 6v12z" /></svg>);
const Next = () => (<svg {...ic}><path d="M16 6h2v12h-2zM6 6l8.5 6L6 18z" /></svg>);
const ChevronUp = (props) => (<svg {...ic} {...props}><path d="M12 8l-6 6 1.4 1.4L12 10.8l4.6 4.6L18 14z" /></svg>);
const Close = () => (<svg {...ic}><path d="M18.3 5.7 12 12l6.3 6.3-1.4 1.4L10.6 13.4 4.3 19.7 2.9 18.3 9.2 12 2.9 5.7 4.3 4.3l6.3 6.3 6.3-6.3z" /></svg>);
const List = () => (<svg {...ic} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" /></svg>);
// Circular arrow used for skip-back / skip-forward, mirrored for direction.
const Rewind = () => (<svg {...ic} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4a8 8 0 1 1-7.5 5.3" /><path d="M3 4v5h5" /></svg>);
const Forward = () => (<svg {...ic} style={{ transform: "scaleX(-1)" }} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4a8 8 0 1 1-7.5 5.3" /><path d="M3 4v5h5" /></svg>);

export default function AudioPlayer({ book, onClose }) {
  const audioRef = useRef(null);
  const [segIdx, setSegIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const [rate, setRate] = useState(1);
  const [expanded, setExpanded] = useState(false);
  const [showChapters, setShowChapters] = useState(false);

  const readySegs = book.segments.filter((seg) => seg.status === "ready");
  const seg = readySegs[segIdx];
  const hasPrev = segIdx > 0;
  const hasNext = segIdx < readySegs.length - 1;
  const color = coverColor(book.id);
  const initial = (book.title || "?").trim().charAt(0).toUpperCase();

  // New book -> start from its first chapter.
  useEffect(() => {
    setSegIdx(0);
    setPlaying(true);
  }, [book.id]);

  // Load the current chapter's audio when the chapter changes.
  useEffect(() => {
    const el = audioRef.current;
    if (!seg || !el) return;
    el.src = audioUrl(seg.id);
    el.playbackRate = rate;
    setCurrent(0);
    setDuration(0);
    if (playing) el.play().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seg?.id]);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    if (playing) el.play().catch(() => {});
    else el.pause();
  }, [playing]);

  useEffect(() => {
    if (audioRef.current) audioRef.current.playbackRate = rate;
  }, [rate]);

  // Lock-screen / bluetooth controls.
  useEffect(() => {
    if (!("mediaSession" in navigator)) return;
    navigator.mediaSession.metadata = new window.MediaMetadata({
      title: book.title || "Untitled",
      artist: book.author || "",
      album: `Chapter ${segIdx + 1} of ${readySegs.length}`,
    });
    const set = (action, handler) => {
      try { navigator.mediaSession.setActionHandler(action, handler); } catch {}
    };
    set("play", () => setPlaying(true));
    set("pause", () => setPlaying(false));
    set("previoustrack", hasPrev ? () => setSegIdx((i) => i - 1) : null);
    set("nexttrack", hasNext ? () => setSegIdx((i) => i + 1) : null);
    set("seekbackward", skipBack);
    set("seekforward", skipForward);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [book.id, segIdx, readySegs.length, hasPrev, hasNext]);

  function onEnded() {
    if (hasNext) setSegIdx((i) => i + 1);
    else setPlaying(false);
  }

  function onTimeUpdate() {
    const el = audioRef.current;
    if (el) setCurrent(el.currentTime);
  }

  function onSeek(e) {
    const el = audioRef.current;
    const v = Number(e.target.value);
    setCurrent(v);
    if (el && isFinite(el.duration)) el.currentTime = v;
  }

  function skipBack() {
    const el = audioRef.current;
    if (el) el.currentTime = Math.max(0, el.currentTime - SKIP);
  }

  function skipForward() {
    const el = audioRef.current;
    if (!el || !isFinite(el.duration)) return;
    if (el.currentTime + SKIP >= el.duration) {
      if (hasNext) setSegIdx((i) => i + 1);
      else el.currentTime = el.duration;
    } else {
      el.currentTime += SKIP;
    }
  }

  function cycleSpeed() {
    setRate((r) => {
      const i = SPEEDS.indexOf(r);
      return SPEEDS[(i + 1) % SPEEDS.length];
    });
  }

  const togglePlay = () => setPlaying((p) => !p);
  const goPrev = () => hasPrev && setSegIdx((i) => i - 1);
  const goNext = () => hasNext && setSegIdx((i) => i + 1);
  const pickChapter = (i) => { setSegIdx(i); setPlaying(true); setShowChapters(false); };

  const fill = duration > 0 ? (current / duration) * 100 : 0;
  const overall = readySegs.length > 0
    ? ((segIdx + (duration > 0 ? current / duration : 0)) / readySegs.length) * 100
    : 0;
  const subText = `${book.author ? `${book.author} · ` : ""}Chapter ${segIdx + 1} of ${readySegs.length}`;
  const speedLabel = `${rate}×`;

  // Render helpers (plain functions, not components) so React doesn't remount
  // them each render — important so dragging the seek slider keeps focus.
  const transport = () => (
    <div className={s.transport}>
      <button className={`${s.iconBtn} ${s.skip}`} onClick={skipBack} title="Back 15s" aria-label="Back 15 seconds">
        <Rewind /><span className={s.skipNum}>15</span>
      </button>
      <button className={s.iconBtn} onClick={goPrev} disabled={!hasPrev} title="Previous chapter" aria-label="Previous chapter"><Prev /></button>
      <button className={s.playBtn} onClick={togglePlay} aria-label={playing ? "Pause" : "Play"}>
        {playing ? <Pause /> : <Play />}
      </button>
      <button className={s.iconBtn} onClick={goNext} disabled={!hasNext} title="Next chapter" aria-label="Next chapter"><Next /></button>
      <button className={`${s.iconBtn} ${s.skip}`} onClick={skipForward} title="Forward 15s" aria-label="Forward 15 seconds">
        <Forward /><span className={s.skipNum}>15</span>
      </button>
    </div>
  );

  const seek = () => (
    <div className={s.seekRow}>
      <span className={s.time}>{fmt(current)}</span>
      <input
        type="range"
        className={`${s.slider} ${s.filled}`}
        style={{ "--fill": fill }}
        min={0}
        max={duration || 0}
        step={0.1}
        value={Math.min(current, duration || 0)}
        onChange={onSeek}
        aria-label="Seek"
      />
      <span className={`${s.time} ${s.timeEnd}`}>{fmt(duration)}</span>
    </div>
  );

  const chapters = () =>
    readySegs.map((_, i) => (
      <button key={i} className={s.chapterItem} data-active={i === segIdx} onClick={() => pickChapter(i)}>
        <span className={s.chapterNum}>{i + 1}</span>
        Chapter {i + 1}
      </button>
    ));

  return (
    <>
      <audio
        ref={audioRef}
        onEnded={onEnded}
        onTimeUpdate={onTimeUpdate}
        onLoadedMetadata={(e) => setDuration(e.target.duration || 0)}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
      />

      <div className={s.bar}>
        <button
          className={s.cover}
          style={{ background: color }}
          onClick={() => setExpanded(true)}
          aria-label="Open now playing"
        >
          {initial}
        </button>

        <div className={s.meta}>
          <span className={s.title}>{book.title}</span>
          <span className={s.sub}>{subText}</span>
        </div>

        {/* Desktop cluster */}
        <div className={s.barMain}>
          {transport()}
          {seek()}
          <div className={s.extras}>
            <button className={s.chip} onClick={cycleSpeed} title="Playback speed">{speedLabel}</button>
            <button className={s.chip} data-active={showChapters} onClick={() => setShowChapters((v) => !v)} title="Chapters">
              <List /> Chapters
            </button>
            <button className={s.iconBtn} onClick={onClose} aria-label="Close player"><Close /></button>
          </div>
        </div>

        {/* Mobile mini controls */}
        <div className={s.miniControls}>
          <button className={s.playBtn} onClick={togglePlay} aria-label={playing ? "Pause" : "Play"}>
            {playing ? <Pause /> : <Play />}
          </button>
          <button className={s.iconBtn} onClick={() => setExpanded(true)} aria-label="Expand"><ChevronUp /></button>
        </div>
      </div>

      {/* Desktop chapters popover */}
      {showChapters && (
        <div className={s.popover}>{chapters()}</div>
      )}

      {/* Mobile full-screen Now Playing sheet */}
      {expanded && (
        <div className={s.sheet}>
          <div className={s.sheetHeader}>
            <button className={s.iconBtn} onClick={() => setExpanded(false)} aria-label="Minimize"><ChevronUp style={{ transform: "rotate(180deg)" }} /></button>
            <span>Now Playing</span>
            <button className={s.iconBtn} onClick={onClose} aria-label="Close player"><Close /></button>
          </div>

          <div className={s.sheetCover} style={{ background: color }}>{initial}</div>

          <div className={s.sheetMeta}>
            <div className={s.sheetTitle}>{book.title}</div>
            <div className={s.sheetSub}>{book.author || ""}</div>
          </div>

          <div className={s.sheetSeek}>
            {seek()}
            <div className={s.overall}><div className={s.overallFill} style={{ width: `${overall}%` }} /></div>
          </div>

          <div className={s.sheetControls}>{transport()}</div>

          <div className={s.sheetFooter}>
            <button className={s.chip} onClick={cycleSpeed}>{speedLabel} speed</button>
            <span className={s.sub}>Chapter {segIdx + 1} of {readySegs.length}</span>
          </div>

          <div className={s.sheetChapters}>{chapters()}</div>
        </div>
      )}
    </>
  );
}
