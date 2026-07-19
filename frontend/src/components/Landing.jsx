import { loginUrl } from "../api";
import s from "./Landing.module.css";

// Logged-out entry page. This is a VISUAL gate only — it hides the app shell
// from visitors who aren't signed in, but the backend API endpoints are still
// open to anyone who knows the URLs. If real privacy is ever needed, the fix is
// on the backend (require a session on /books etc.), not here.
//
// The framing line below is the one knob for positioning: swap it to reframe
// Aedo as a private beta / portfolio demo / etc. without touching anything else.
const TILES = [
  { title: "Upload a PDF", body: "Drop in any book or document." },
  { title: "Natural voice", body: "Turned into audio you'd actually listen to." },
  { title: "Listen anywhere", body: "Your library, on any device." },
];

export default function Landing({ denied, onDismissDenied }) {
  return (
    <div className={s.wrap}>
      <main className={s.hero}>
        <h1 className={s.logo}>Aedo</h1>
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
            <li key={t.title} className={s.tile}>
              <span className={s.tileTitle}>{t.title}</span>
              <span className={s.tileBody}>{t.body}</span>
            </li>
          ))}
        </ul>
      </main>

      <footer className={s.footer}>© Aedo · {new Date().getFullYear()}</footer>
    </div>
  );
}
