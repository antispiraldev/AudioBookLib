import { loginUrl } from "../api";
import s from "./Landing.module.css";

// Logged-out entry page. This is a VISUAL gate only — it hides the app shell
// from visitors who aren't signed in, but the backend API endpoints are still
// open to anyone who knows the URLs. If real privacy is ever needed, the fix is
// on the backend (require a session on /books etc.), not here.
//
// Visual language: a manuscript leaf, laid out asymmetrically like a real codex
// page — a decorated left margin (the vine rail) beside a left-aligned text
// block, opened by an illuminated initial. The æ is drawn as an inline SVG so it
// fills the lapis panel precisely (and doubles as a reusable mark); "do" flows
// out of it. Vellum is procedurally weathered in Landing.module.css. Framing
// line is the positioning knob.
const TILES = [
  { label: "Upload", body: "Drop in any book or document." },
  { label: "Natural voice", body: "Turned into audio you'd actually listen to." },
  { label: "Anywhere", body: "Your library, on any device." },
];

// The illuminated initial: a lapis panel, gilt double keyline, gilt corner
// flourishes, and the æ scaled to fill it.
function Initial() {
  return (
    <svg className={s.mark} viewBox="0 0 100 100" aria-hidden="true">
      <rect x="0.75" y="0.75" width="98.5" height="98.5" fill="#274b8e" stroke="#a97c22" strokeWidth="1.5" />
      <rect x="5" y="5" width="90" height="90" fill="none" stroke="#a97c22" strokeOpacity="0.5" strokeWidth="0.75" />
      <g fill="none" stroke="#d8b458" strokeOpacity="0.7" strokeWidth="1">
        <path d="M9 19 A 10 10 0 0 1 19 9" />
        <path d="M81 9 A 10 10 0 0 1 91 19" />
        <path d="M91 81 A 10 10 0 0 1 81 91" />
        <path d="M19 91 A 10 10 0 0 1 9 81" />
      </g>
      <text
        x="50" y="78" textAnchor="middle"
        fontFamily="Fraunces, Georgia, serif" fontWeight="600" fontSize="104"
        textLength="94" lengthAdjust="spacingAndGlyphs" fill="#e9dcae"
      >
        æ
      </text>
    </svg>
  );
}

export default function Landing({ denied, onDismissDenied }) {
  return (
    <div className={s.wrap}>
      <main className={s.leaf}>
        <div className={s.page}>
          <div className={s.rail} aria-hidden="true" />

          <div className={s.block}>
            <h1 className={s.title} aria-label="Aedo">
              <Initial />
              <span className={s.do} aria-hidden="true">do</span>
            </h1>
            <p className={s.pron} aria-hidden="true">AY-doh</p>

            <div className={s.divider} aria-hidden="true">
              <span className={s.diamond} />
              <span className={s.dline} />
            </div>

            <p className={s.tagline}>Turn any book into a listen.</p>

            <a className={s.cta} href={loginUrl()}>
              <span className={s.g} aria-hidden="true">G</span>
              Continue with Google
            </a>
            <p className={s.framing}>A personal project — sign in to take a look.</p>

            {denied && (
              <div className={s.denied} role="alert">
                You're not on the invite list yet.
                <button className={s.deniedClose} onClick={onDismissDenied} aria-label="Dismiss">
                  ✕
                </button>
              </div>
            )}

            <ul className={s.tiles}>
              {TILES.map((t) => (
                <li key={t.label} className={s.tile}>
                  <span className={s.tileLabel}>{t.label}</span>
                  <span className={s.tileBody}>{t.body}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </main>

      <footer className={s.colophon}>Aedo · {new Date().getFullYear()}</footer>
    </div>
  );
}
