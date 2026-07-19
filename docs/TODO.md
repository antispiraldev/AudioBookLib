# TODO

Working list of open items for Aedo. Checked and pruned when PRs merge and are
verified in prod, and after any other significant change or fix.

Convention: `- [ ]` open, `- [x]` done-but-not-yet-pruned (drop it next pass).
Keep entries short; the *why* belongs in the commit or in `PIPELINE.md`.

## Admin panel

All 6 roadmap PRs merged, deployed, and verified live at `#/admin` as of
2026-07-18 (see `PIPELINE.md` → Observability for what exists). One follow-up
the deploy surfaced:

- [ ] The worker droplet has **no swap configured** (`swap_total: 0` in
      `/api/admin/resources`) — memory is its only OOM cushion. Consider
      adding swap there like the web droplet has.

## TTS / narration quality

Done in PR #18 (live 2026-07-19). The "too flat and impersonal" `onyx` default
was fixed as a prompt problem, not a provider one, and voice is now selectable.

- [x] Parameterize `voice` alongside the existing `tts_instructions` — `NARRATORS`
      preset registry + `tts.resolve()` in `backend/app/services/tts.py`
- [x] Write narrator-style instruction presets — default is onyx + `prosody_valence`
      (older narrator, valence-driven stress, lingering sentence-final decay)
- [x] Generate sample clips across voice × preset for blind comparison — harness at
      `backend/scripts/tts_ab.py`; three rounds settled it, no second provider needed
- [x] Offer voice/prompt options in the UI — admin narrator dropdown (Edit modal),
      `older_man`/onyx and `older_woman`/shimmer, fed by `GET /books/narrators`
- [ ] **Re-voice cache (deferred).** `POST /books/{id}/resynthesize` currently
      archives the old take under `audio-archive/{id}/{ts}/` and re-synthesizes
      from scratch (pays each time). Next step: tag each archived take by a render
      signature — hash of `(voice, instructions, ordered segment texts)` — and on
      re-synthesize, if a matching take exists, **restore it for free** instead of
      calling TTS. Makes A→B→A voice toggles cost nothing. Needs a `rendered`
      signature persisted per book (set on finalize) + a storage restore/copy
      helper. Signature must include the text hash so edits never restore stale
      audio. See `resynthesize_book` in `backend/app/routers/books.py`.

## Pipeline / content

- [ ] Retry the books left in `error` from the 2026-07-17 seeding run — they
      most likely died from the OOM, not from anything in their content, and
      ingest has its own droplet now. Query the DB for current `error`/`review`
      state first; don't trust this note for which books.

## Infra

- [ ] Cloudflare redirect rule voxshelf.io → aedo.io (old domain lapses
      ~Jan 2027)
- [ ] **User web-action:** add `~/.ssh/github_aedo.pub` at
      github.com/settings/keys, then revoke the old classic PAT at
      github.com/settings/tokens — the remote is already off it
- [ ] Optional: Cloudflare Origin Cert + Full (strict) on both zones — today
      SSL must stay Flexible because the droplet serves plain HTTP :80 only
- [ ] Optional: droplet hardening — fail2ban/UFW, non-root deploy user
- [ ] Optional: register aedo.app defensively

## Repo / process

- [ ] No CI: deploys are manual (`git pull && docker compose up -d --build` on
      the droplet). Worth automating at some point
