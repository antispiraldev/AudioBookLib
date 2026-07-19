import { loginUrl } from "../api";
import s from "./Landing.module.css";

// Logged-out entry page. This is a VISUAL gate only — it hides the app shell
// from visitors who aren't signed in, but the backend API endpoints are still
// open to anyone who knows the URLs. If real privacy is ever needed, the fix is
// on the backend (require a session on /books etc.), not here.
//
// Visual language: a manuscript leaf, laid out asymmetrically like a real codex
// page — a decorated left margin (the vine rail) beside a left-aligned text
// block, opened by an illuminated initial. The æ sits inside a lapis square and
// "do" flows out of it as a drop-cap. Cues are suggestive, not literal
// medievalism. Vellum ground is procedurally weathered (grain + crinkle) in
// Landing.module.css. Framing line is the positioning knob.
const TILES = [
  { label: "Upload", body: "Drop in any book or document." },
  { label: "Natural voice", body: "Turned into audio you'd actually listen to." },
  { label: "Anywhere", body: "Your library, on any device." },
];

export default function Landing({ denied, onDismissDenied }) {
  return (
    <div className={s.wrap}>
      <main className={s.leaf}>
        <div className={s.page}>
          <div className={s.rail} aria-hidden="true" />

          <div className={s.block}>
            {/* Illuminated initial: the æ inside a lapis square, "do" flowing
                out of it as a drop-cap. aria-label keeps the name "Aedo". */}
            <h1 className={s.title} aria-label="Aedo">
              <span className={s.box} aria-hidden="true">
                <span className={s.ae}>æ</span>
              </span>
              <span className={s.do} aria-hidden="true">do</span>
            </h1>
            <p className={s.pron} aria-hidden="true">AY-doh</p>

            <div className={s.rule} aria-hidden="true" />

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
