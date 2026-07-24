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
- [ ] Multi-voice narrations + listener toggle (branch `worktree-voice-narration-toggle`,
      not yet merged): a book can be rendered in several narrator presets
      (`segment_audio` table, `POST/DELETE /books/{id}/narrations`), and the player
      has a voice switch that keeps position and remembers the choice per book.
      Admin generates extra voices from the Edit modal. Verify in prod after deploy;
      the alt-render progress isn't shown on book cards, only in the Edit modal.

### Premium / multi-provider — ElevenLabs is now the default provider

`tts.synthesize_preset()` dispatches by provider (openai / elevenlabs / gemini).
`DEFAULT_NARRATOR` is **`storyteller`**, an ElevenLabs *designed* voice (generated
from a written description via Voice Design — not cloned from anyone), with
`elegiac` and `scholar` offered alongside it and the premade `premium_man`/
`premium_woman` presets kept. The OpenAI presets (`older_man`/`older_woman`) remain
selectable and are still the cheap path.

- [x] Run round 4 and pick the voice(s) — round 4 chose ElevenLabs over OpenAI;
      a 21-voice account survey then a Voice Design round produced the three
      designed narrators now shipping.
- [x] Confirm `voice_id`s against the account — all confirmed via
      `GET /v1/voices/{id}`. Note `/v1/voices` lists only the *saved* library, so a
      premade voice missing from it is not broken; check the id endpoint instead.
- [x] `ELEVENLABS_API_KEY` set in `.env` on the **worker** droplet (2026-07-22, hash-verified
      against local; `.env.bak.pre-el` left as backup) and loaded into the running
      containers 2026-07-23 — `env_file` is read at container *creation*, so
      `docker compose restart` will not pick it up; use `up -d --force-recreate`.
- [x] 429 handling: `_http_post` retries 429/5xx with exponential backoff and honours
      `Retry-After`, so exceeding the concurrency cap costs latency rather than
      failing a segment. Complements the `synth_el` queue rather than replacing it.
- [ ] `GEMINI_API_KEY` is still unset everywhere except locally — only the A/B harness
      needs it, so round 4 currently skips the four Gemini presets.
- [ ] **`worker-el` must be deployed before the next book, now that the default
      narrator is an ElevenLabs voice.** The `synth_el` queue is inert until
      `worker-el` runs — tasks sit pending rather than failing — and with
      `storyteller` as default that is *every* book, not just premium ones.
- [ ] **`EL_CONCURRENCY` (default 3) is now the throughput ceiling for almost all
      synthesis**, since the default narrator routes to `synth_el` while the
      16-slot `synth` queue sits idle. The queue was sized when ElevenLabs was the
      exception; raise it to the plan's actual concurrent limit, or accept that
      books render several times slower than they did on OpenAI.
- [ ] **Cost: ElevenLabs is character-metered and is now on the default path.** A
      ~6-hour book is roughly 300k characters, so every book costs materially more
      than the OpenAI path did (~$5–6/book). Watch the first few books and set a
      `character_limit` on the API key; switch `DEFAULT_NARRATOR` back to
      `older_man` if the spend is wrong.
- [ ] Gemini is A/B-only for now — it returns PCM, so wiring it into production would
      need a PCM→MP3 transcode step the pipeline doesn't have.

## Pipeline / content

- [x] Seed-batch retries all verified complete 2026-07-20 (books 16/17/19).
      Book 18 (popular_delusions) was unfixable — letter-spaced garbage text
      survived reprocess — and was deleted outright (user call, 2026-07-20).
- [ ] Book 22 (As We May Think) still sits in `review` awaiting text check.
- [ ] Part II batch (books 28–47, seeded 2026-07-20 from clean Gutenberg
      texts): user reviewing/approving; hide any with transcription issues.

### Text-quality survey + diff backfill (2026-07-24)

Corpus survey found two ingest cohorts split at 2026-07-13 (when the cleaning
heuristics + LLM polish landed): pre-heuristics "legacy" books carry raw
extraction (ligatures, Gutenberg banners, ~3300-char segments), and even
modern books leak running headers ("BEYOND GOOD AND EVIL 127" mid-sentence),
transcriber markup, and back-of-book indexes. Heuristics hardened (see
`PIPELINE.md`) and a diff-based backfill added (`POST /books/{id}/refresh`)
that re-synthesizes only changed segments.

- [x] Hidden garbled-source books 5 (Language of Flowers), 12 (Meditations),
      14 (Beyond Good and Evil), 19 (Origin of Species) — OCR-salad sources
      that heuristics can't fix (2026-07-23, prod `hidden=true`).
- [x] All 45 existing books pinned `tts_narrator='older_man'` (prod,
      2026-07-24): their audio is onyx, and a NULL narrator now resolves to
      the ElevenLabs `storyteller` default — an unpinned refresh would have
      switched voice mid-book and hit the character-metered EL path.
- [ ] Replace hidden books' PDFs with clean sources (Gutenberg text-based
      PDFs) and reprocess; book 10 (Self-Reliance, Roycroft edition) is
      borderline word-salad too — candidate for source replacement.
- [ ] Admin UI button for `POST /books/{id}/refresh` (backend-only for now;
      backfills run via curl/celery from the droplet).
- [ ] Alternate-narration takes of *changed* segments are dropped by refresh
      (primary re-renders; alternates fall back until re-requested via
      `POST /books/{id}/narrations`).
- [ ] `backend/scripts/text_qa.py` — artifact-prevalence report; run before/
      after heuristics changes or backfills.

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
