import { loginUrl } from "../api";
import s from "./Landing.module.css";

// Logged-out entry page. This is a VISUAL gate only — it hides the app shell
// from visitors who aren't signed in, but the backend API endpoints are still
// open to anyone who knows the URLs. If real privacy is ever needed, the fix is
// on the backend (require a session on /books etc.), not here.
//
// Visual language: the page is styled as an "incipit" — the decorated opening
// leaf of a codex. It borrows three quiet devices from illuminated manuscripts
// (a ruled gilt frame, an illuminated lapis initial, and a rubricated gloss)
// without tipping into literal medievalism. The framing line below is the one
// knob for positioning (private beta / demo / personal).
const TILES = [
  { title: "Upload a PDF", body: "Drop in any book or document." },
  { title: "Natural voice", body: "Turned into audio you'd actually listen to." },
  { title: "Listen anywhere", body: "Your library, on any device." },
];

export default function Landing({ denied, onDismissDenied }) {
  return (
    <div className={s.wrap}>
      <main className={s.leaf}>
        <div className={s.incipit}>
          {/* Wordmark: the a+e bond into a lowercase "æ" ligature, set as an
              illuminated (lapis) initial. aria-label keeps the name "Aedo". */}
          <h1 className={s.logo} aria-label="Aedo">
            <span aria-hidden="true">
              <span className={s.ae}>æ</span>do
            </span>
          </h1>
          <p className={s.pron} aria-hidden="true">AY-doh</p>
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

          {/* Hairline lozenge divider — a restrained marginal ornament. */}
          <div className={s.divider} aria-hidden="true">
            <span className={s.rule} />
            <span className={s.lozenge}>❧</span>
            <span className={s.rule} />
          </div>

          <ul className={s.tiles}>
            {TILES.map((t) => (
              <li key={t.title} className={s.tile}>
                <span className={s.tileTitle}>{t.title}</span>
                <span className={s.tileBody}>{t.body}</span>
              </li>
            ))}
          </ul>
        </div>
      </main>

      <footer className={s.colophon}>Aedo · {new Date().getFullYear()}</footer>
    </div>
  );
}
