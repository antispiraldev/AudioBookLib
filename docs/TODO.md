# TODO

Working list of open items for Aedo. Checked and pruned when PRs merge and are
verified in prod, and after any other significant change or fix.

Convention: `- [ ]` open, `- [x]` done-but-not-yet-pruned (drop it next pass).
Keep entries short; the *why* belongs in the commit or in `PIPELINE.md`.

## Admin panel

All 6 roadmap PRs merged, deployed, and verified live at `#/admin` as of
2026-07-18 (see `PIPELINE.md` → Observability for what exists). One follow-up
the deploy surfaced:

- [x] The worker droplet had **no swap configured** — fixed 2026-07-19: 2 GB
      swap file added (fstab-persisted), visible in `/api/admin/resources`.

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

### Premium / multi-provider (in progress — the "highest quality, cost is fine" option)

`tts.synthesize_preset()` now dispatches by provider (openai / elevenlabs / gemini).
Two premium ElevenLabs narrator presets (`premium_man`/`premium_woman`, multilingual_v2)
are wired end to end and appear in the admin dropdown. `tts_ab.py --round4` blind-tests
the OpenAI default vs premium ElevenLabs + Gemini voices.

- [ ] Run round 4 (`python scripts/tts_ab.py --round4`) and pick the premium
      voice(s); the harness presets are a starting point, not a decision.
- [ ] Confirm the premium `voice_id`s against the account with
      `python scripts/tts_ab.py --el-list-voices` before trusting a win — the ids in
      `NARRATORS`/`PROVIDER_PRESETS` are documented defaults, not verified per-account.
- [ ] Set `ELEVENLABS_API_KEY` (and `GEMINI_API_KEY` for the A/B harness) in `.env`
      on the **worker** droplet before selecting a premium narrator in prod.
- [ ] **ElevenLabs caps *concurrent* requests per plan (often 5–15).** Synth runs at
      `SYNTH_CONCURRENCY` 16 — a premium book will 429. Gate premium synthesis to a
      lower concurrency (own queue) or a Scale-tier plan before shipping it widely.
- [ ] Gemini is A/B-only for now — it returns PCM, so wiring it into production would
      need a PCM→MP3 transcode step the pipeline doesn't have.

## Pipeline / content

- [x] Seed-batch retries all verified complete 2026-07-20 (books 16/17/19).
      Book 18 (popular_delusions) was unfixable — letter-spaced garbage text
      survived reprocess — and was deleted outright (user call, 2026-07-20).
- [ ] Book 22 (As We May Think) still sits in `review` awaiting text check.
- [ ] Part II batch (books 28–47, seeded 2026-07-20 from clean Gutenberg
      texts): user reviewing/approving; hide any with transcription issues.

## Worker throughput

Done in PR #24 (live 2026-07-19): ingest and synthesis split into separate
Celery queues so synthesis scales without touching the ingest OOM cap —
`worker-ingest` (`-Q ingest --concurrency=2`) + `worker-synth`
(`-Q synth,celery --concurrency=6`, measured ~3x throughput, ~755MB RSS).

- [x] Synth concurrency raised 6 → 8 → 16 (2026-07-20) to drain the approval
      backlog (~2.5k queued segments). Live rate-limit headers showed 10k RPM
      account limit vs ~32 RPM used at 8 slots, so OpenAI has huge headroom.
      Still watch worker RAM and 429s after changes.
- [x] Worker concurrency moved to `.env` (`SYNTH_CONCURRENCY`,
      `INGEST_CONCURRENCY`) so tuning no longer needs a PR + rebuild.
- [ ] Synth pool beyond ~16-20 slots: prefork costs ~110MB RAM per slot, so
      switch worker-synth to `--pool=threads` first (audit task thread-safety;
      OpenAI client is thread-safe, DB sessions are per-task).

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
