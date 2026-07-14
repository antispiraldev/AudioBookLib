import { useEffect, useRef, useState } from "react";
import { audioUrl } from "../api";
import { loadProgress, saveProgress, loadSpeed, saveSpeed } from "../lib/playback";
import s from "./AudioPlayer.module.css";

const SKIP = 15;
const SPEEDS = [1, 1.25, 1.5, 1.75, 2, 0.75];
const SLEEP_OPTIONS = [
  { value: null, label: "Off" },
  { value: 15, label: "15 minutes" },
  { value: 30, label: "30 minutes" },
  { value: 45, label: "45 minutes" },
  { value: 60, label: "1 hour" },
  { value: "chapter", label: "End of chapter" },
];

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

// Where to resume a book: saved chapter + offset, else the start.
function initialResume(book) {
  const ready = book.segments.filter((x) => x.status === "ready");
  const p = loadProgress(book.id);
  if (p && p.segIdx >= 0 && p.segIdx < ready.length) {
    return { idx: p.segIdx, t: p.t || 0 };
  }
  return { idx: 0, t: 0 };
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
const Moon = () => (<svg {...ic} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></svg>);
// Circular arrow with the skip seconds baked into the SVG as <text>, so the
// "15" stays centered on every browser. (A separate absolutely-positioned
// label drifted off-centre on iOS Safari.) The arrow is mirrored for forward.
const SkipIcon = ({ dir }) => (
  <svg {...ic} fill="none" aria-hidden="true">
    <g
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      transform={dir === "fwd" ? "matrix(-1,0,0,1,24,0)" : undefined}
    >
      <path d="M11 4a8 8 0 1 1-7.5 5.3" />
      <path d="M3 4v5h5" />
    </g>
    <text x="12" y="15" textAnchor="middle" fontSize="8" fontWeight="700" fill="currentColor">15</text>
  </svg>
);

export default function AudioPlayer({ book, onClose }) {
  const audioRef = useRef(null);

  // Resume position for the initial book (chapter + offset).
  const resumeRef = useRef(null);
  if (resumeRef.current === null) resumeRef.current = initialResume(book);

  const [segIdx, setSegIdx] = useState(resumeRef.current.idx);
  const [playing, setPlaying] = useState(true);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const [rate, setRate] = useState(() => loadSpeed());
  const [expanded, setExpanded] = useState(false);
  const [showChapters, setShowChapters] = useState(false);
  const [sleep, setSleep] = useState(null); // null | minutes | "chapter"
  const [sleepEndsAt, setSleepEndsAt] = useState(0);
  const [sleepRemain, setSleepRemain] = useState(0);
  const [showSleep, setShowSleep] = useState(false);

  // Seconds to seek to once the next chapter's metadata loads (for resume).
  const savedSeekRef = useRef(resumeRef.current.t);

  const readySegs = book.segments.filter((seg) => seg.status === "ready");
  const seg = readySegs[segIdx];
  const hasPrev = segIdx > 0;
  const hasNext = segIdx < readySegs.length - 1;
  const color = coverColor(book.id);
  const initial = (book.title || "?").trim().charAt(0).toUpperCase();

  // Switching to a different book -> resume that book (mount is handled by the
  // lazy initial state above, so skip the first run).
  const firstRunRef = useRef(true);
  useEffect(() => {
    if (firstRunRef.current) { firstRunRef.current = false; return; }
    const r = initialResume(book);
    savedSeekRef.current = r.t;
    setSegIdx(r.idx);
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
    // If a saved position is pending, defer play to onLoadedMetadata so we
    // seek first and avoid a blip of audio from 0:00.
    if (playing && savedSeekRef.current <= 0) el.play().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seg?.id]);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    if (playing) el.play().catch(() => {});
    else el.pause();
  }, [playing]);

  // Apply + persist playback speed.
  useEffect(() => {
    if (audioRef.current) audioRef.current.playbackRate = rate;
    saveSpeed(rate);
  }, [rate]);

  // ---- Progress persistence (resume where you left off) ----
  const lastSaveRef = useRef(0);
  const persistRef = useRef(() => {});
  persistRef.current = () => {
    const el = audioRef.current;
    if (!el || readySegs.length === 0) return;
    const intra = el.duration ? el.currentTime / el.duration : 0;
    const fraction = (segIdx + intra) / readySegs.length;
    saveProgress(book.id, { segIdx, t: el.currentTime, fraction });
  };
  useEffect(() => () => persistRef.current(), []); // save on close/unmount

  // ---- Sleep timer countdown ----
  useEffect(() => {
    if (typeof sleep !== "number") { setSleepRemain(0); return; }
    const tick = () => {
      const rem = Math.max(0, sleepEndsAt - Date.now());
      setSleepRemain(rem);
      if (rem <= 0) {
        setPlaying(false);
        setSleep(null);
        setSleepEndsAt(0);
      }
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [sleep, sleepEndsAt]);

  // ---- Keyboard shortcuts (desktop) ----
  // keyRef is populated after the handlers are defined (below); the listener
  // reads it lazily at key-press time, so it always calls the latest handlers.
  const keyRef = useRef({});
  useEffect(() => {
    function onKey(e) {
      const t = e.target;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = keyRef.current;
      switch (e.key) {
        case " ": case "k": e.preventDefault(); k.togglePlay(); break;
        case "ArrowLeft": e.preventDefault(); e.shiftKey ? k.goPrev() : k.skipBack(); break;
        case "ArrowRight": e.preventDefault(); e.shiftKey ? k.goNext() : k.skipForward(); break;
        default: break;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
    // Sleep timer set to "end of chapter": stop here instead of advancing.
    if (sleep === "chapter") {
      setPlaying(false);
      setSleep(null);
      return;
    }
    // iOS Safari fires a `pause` event when playback reaches the end, which
    // flips `playing` to false. Re-assert the intent to keep playing so the
    // load-next-chapter effect auto-plays instead of stalling paused.
    if (hasNext) {
      setPlaying(true);
      setSegIdx((i) => i + 1);
    } else {
      setPlaying(false);
    }
  }

  function onTimeUpdate() {
    const el = audioRef.current;
    if (!el) return;
    setCurrent(el.currentTime);
    const now = Date.now();
    if (now - lastSaveRef.current > 4000) {
      lastSaveRef.current = now;
      persistRef.current();
    }
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

  function chooseSleep(option) {
    setShowSleep(false);
    if (option == null) { setSleep(null); setSleepEndsAt(0); return; }
    if (option === "chapter") { setSleep("chapter"); setSleepEndsAt(0); return; }
    setSleep(option);
    setSleepEndsAt(Date.now() + option * 60000);
  }

  function togglePlay() { setPlaying((p) => !p); }
  const goPrev = () => hasPrev && setSegIdx((i) => i - 1);
  const goNext = () => hasNext && setSegIdx((i) => i + 1);
  const pickChapter = (i) => { setSegIdx(i); setPlaying(true); setShowChapters(false); };

  // Latest handlers for the keyboard listener (see effect above).
  keyRef.current = { togglePlay, skipBack, skipForward, goPrev, goNext };

  const fill = duration > 0 ? (current / duration) * 100 : 0;
  const overall = readySegs.length > 0
    ? ((segIdx + (duration > 0 ? current / duration : 0)) / readySegs.length) * 100
    : 0;
  const subText = `${book.author ? `${book.author} · ` : ""}Chapter ${segIdx + 1} of ${readySegs.length}`;
  const speedLabel = `${rate}×`;
  const sleepChipLabel = sleep == null
    ? null
    : sleep === "chapter" ? "Ch" : fmt(Math.ceil(sleepRemain / 1000));

  function onLoadedMetadata(e) {
    const el = e.target;
    setDuration(el.duration || 0);
    const seekTo = savedSeekRef.current;
    if (seekTo > 0) {
      // Resume: apply the saved offset if it's in range, then start playing
      // (the load effect deferred play so we could seek first).
      savedSeekRef.current = 0;
      if (seekTo < el.duration) {
        el.currentTime = seekTo;
        setCurrent(seekTo);
      }
      if (playing) el.play().catch(() => {});
    }
  }

  // Render helpers (plain functions, not components) so React doesn't remount
  // them each render — important so dragging the seek slider keeps focus.
  const transport = () => (
    <div className={s.transport}>
      <button className={s.iconBtn} onClick={skipBack} title="Back 15s" aria-label="Back 15 seconds">
        <SkipIcon dir="back" />
      </button>
      <button className={s.iconBtn} onClick={goPrev} disabled={!hasPrev} title="Previous chapter" aria-label="Previous chapter"><Prev /></button>
      <button className={s.playBtn} onClick={togglePlay} aria-label={playing ? "Pause" : "Play"}>
        {playing ? <Pause /> : <Play />}
      </button>
      <button className={s.iconBtn} onClick={goNext} disabled={!hasNext} title="Next chapter" aria-label="Next chapter"><Next /></button>
      <button className={s.iconBtn} onClick={skipForward} title="Forward 15s" aria-label="Forward 15 seconds">
        <SkipIcon dir="fwd" />
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

  const sleepBtn = () => (
    <button
      className={s.chip}
      data-active={sleep != null}
      onClick={() => setShowSleep((v) => !v)}
      title="Sleep timer"
      aria-label="Sleep timer"
    >
      <Moon />{sleepChipLabel && <span>{sleepChipLabel}</span>}
    </button>
  );

  return (
    <>
      <audio
        ref={audioRef}
        onEnded={onEnded}
        onTimeUpdate={onTimeUpdate}
        onLoadedMetadata={onLoadedMetadata}
        onPlay={() => setPlaying(true)}
        onPause={() => { setPlaying(false); persistRef.current(); }}
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
            {sleepBtn()}
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

      {/* Sleep-timer menu (works over the bar and the mobile sheet) */}
      {showSleep && (
        <>
          <div className={s.menuBackdrop} onClick={() => setShowSleep(false)} />
          <div className={s.sleepMenu} role="menu">
            <div className={s.sleepMenuTitle}>Sleep timer</div>
            {SLEEP_OPTIONS.map((o) => (
              <button
                key={String(o.value)}
                className={s.sleepItem}
                data-active={sleep === o.value}
                role="menuitem"
                onClick={() => chooseSleep(o.value)}
              >
                {o.label}
              </button>
            ))}
          </div>
        </>
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
            <div className={s.sheetFooterBtns}>
              <button className={s.chip} onClick={cycleSpeed}>{speedLabel}</button>
              {sleepBtn()}
            </div>
            <span className={s.sub}>Chapter {segIdx + 1} of {readySegs.length}</span>
          </div>

          <div className={s.sheetChapters}>{chapters()}</div>
        </div>
      )}
    </>
  );
}
