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

A listener found the default `onyx` narration "too flat and impersonal."
`gpt-4o-mini-tts` is steerable and `Book.tts_instructions` is already per-book,
but `VOICE = "onyx"` is hardcoded in `backend/app/services/tts.py` — that
asymmetry is the gap.

- [ ] Parameterize `voice` alongside the existing `tts_instructions`
- [ ] Write 3–4 narrator-style instruction presets
- [ ] Generate sample clips of one paragraph across voice × preset for blind
      comparison — costs pennies, and answers whether a second provider
      (ElevenLabs et al.) is worth abstracting behind `synthesize()` at all
- [ ] Offer a few voice/prompt options in the UI rather than one default

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
