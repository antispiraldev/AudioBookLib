import { loginUrl } from "../api";
import initialSvg from "../assets/initial.svg?raw";
import s from "./Landing.module.css";

// Logged-out entry page. This is a VISUAL gate only — it hides the app shell
// from visitors who aren't signed in, but the backend API endpoints are still
// open to anyone who knows the URLs. If real privacy is ever needed, the fix is
// on the backend (require a session on /books etc.), not here.
//
// Visual language: an illuminated manuscript leaf (International Gothic / Book of
// Hours). A fixed 760x1000 codex page, scaled to fit on small screens, with an
// ornate floral border, a gold bar margin, an illuminated initial (the æ; the
// SVG is inlined via ?raw so its <text> uses the Fraunces webfont), and the
// wordmark's "do" plus the tile versals in blackletter. Framing line is the
// positioning knob.
const TILES = [
  { v: "U", label: "Upload", body: "Drop in any book or document." },
  { v: "N", label: "Natural voice", body: "Turned into audio you'd actually listen to." },
  { v: "A", label: "Anywhere", body: "Your library, on any device." },
];

export default function Landing({ denied, onDismissDenied }) {
  return (
    <div className={s.wrap}>
      <div className={s.leaf}>
        <div className={s.frame} aria-hidden="true" />
        <div className={s.goldbar} aria-hidden="true" />

        <div className={s.content}>
          <h1 className={s.title} aria-label="Aedo">
            <span className={s.mark} aria-hidden="true" dangerouslySetInnerHTML={{ __html: initialSvg }} />
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
                <span className={s.versal} aria-hidden="true">{t.v}</span>
                <div>
                  <div className={s.tl}>{t.label}</div>
                  <div className={s.tb}>{t.body}</div>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className={s.colophon}>Aedo · {new Date().getFullYear()}</div>
      </div>
    </div>
  );
}
