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

## Pipeline / content

- [x] Retry the seed-batch `error` books — done 2026-07-19: books 16/17/19
      synthesized clean on retry (old errors were transient). Book 18
      (popular_delusions) was NOT transient: per-character PDF extraction had
      letter-spaced its text ("I n t e r…"), blowing the TTS 2000-token limit.
      Reprocessed with the current extractor.
- [ ] Book 18 lands back in `review` after its reprocess — **eyeball the text
      for the letter-spacing pathology before approving**. If it's still
      garbage, the PDF needs OCR or a replacement copy.
- [ ] Books 22, 26, 27 sit in `review` awaiting text check + approve.

## Worker throughput

Done in PR #24 (live 2026-07-19): ingest and synthesis split into separate
Celery queues so synthesis scales without touching the ingest OOM cap —
`worker-ingest` (`-Q ingest --concurrency=2`) + `worker-synth`
(`-Q synth,celery --concurrency=6`, measured ~3x throughput, ~755MB RSS).

- [ ] Synth concurrency could go higher (RAM headroom exists) — raise only
      while watching worker RAM and OpenAI 429s.

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
