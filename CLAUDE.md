# Aedo (repo folder: AudioBookLib)

Personal audiobook library — converts PDFs to audio via OpenAI TTS. Live at
https://aedo.io, private beta behind Google SSO.

Stack: FastAPI + SQLAlchemy + Postgres (Alembic), Celery + Redis, React/Vite,
Cloudflare R2 for MP3s, DigitalOcean droplets behind Cloudflare.

See `PIPELINE.md` for the processing flow and `docs/TODO.md` for open work.
Keep both current — `PIPELINE.md` on any meaningful pipeline change, `docs/TODO.md`
when a PR merges and is verified. Same commit as the change.

## Commands

Local, all-in-one (the `worker` profile is off by default because production
runs the worker on its own droplet):

    docker compose --profile worker up -d --build

Frontend dev server: `cd frontend && npm run dev` (build: `npm run build`).

Backend tests are dependency-free and run standalone or under pytest — pytest is
not in `requirements.txt`, so standalone is the reliable path:

    cd backend && python tests/test_pdf.py

## Deploy — manual, no CI

Web droplet:

    cd /opt/voxshelf/AudioBookLib && git pull && docker compose up -d --build

Worker droplet: same pull, then
`docker compose -f docker-compose.worker.yml up -d --build`.

Droplet commands go through `deploy/run_remote.sh '<cmd>'` (web) and
`deploy/run_remote_worker.sh '<cmd>'` (worker, reached via the web droplet as an
SSH ProxyJump bastion). Both are **untracked, local-only** — a fresh clone won't
have them. They append every command verbatim to `deploy/remote_history.log`, so
never put a secret on a droplet command line; read it from `.env` on the box
instead. Frontend-only changes need just `docker compose up -d --build frontend`.

Migrations apply themselves: `init_db()` runs `alembic upgrade head` in the
FastAPI lifespan hook, so a backend restart migrates the DB. Take a `pg_dump`
before deploying a migration.

## Constraints — these bite

- **Cloudflare SSL must stay Flexible** on both zones. The droplet serves plain
  HTTP :80 only; "Full" returns 521.
- **Worker concurrency stays at 2.** `ingest_book` is memory-heavy — PyMuPDF
  balloons a 25MB PDF to hundreds of MB, and >2 parallel ingests OOM'd the box
  and 504'd the site. Raise only alongside more RAM.
- **The worker droplet has no public IP.** It reaches Postgres and Redis over
  the VPC at `10.120.0.2` and the internet via NAT through the web droplet.
  Anything it needs to report must travel through shared Redis or Postgres —
  never direct HTTP.
- **`POSTGRES_PASSWORD` and `REDIS_PASSWORD` are mandatory** — compose uses
  `${VAR:?}` with no default, so it refuses to start rather than fall back. That
  is deliberate: a defaulted password (`voxshelf`) was once live in production
  and published in this public repo. Both are set in `.env` on each droplet and
  must match across the two. Redis runs with `--requirepass`; it still binds to
  `DB_BIND_IP` (loopback locally, the VPC IP in production) and should never be
  bound to a public interface.
- **`voxshelf` is load-bearing** in the Postgres user/db name and the
  `/opt/voxshelf/AudioBookLib` droplet path. The app renamed to Aedo; these
  didn't, because renaming the DB would orphan the volume.
- Backend `.env` changes need a backend restart to take effect.

## Conventions

- Work on a branch, open a PR — `master` is what production deploys.
- **Avoid stacked PRs.** A chain of PRs based on each other once merged into
  their intermediate branches instead of `master` and was orphaned on branch
  delete. If you do stack them, verify `origin/master` actually advanced after
  each merge before deleting anything — `state:MERGED` alone doesn't prove it.
- No `Co-Authored-By` lines in commits.
- Frontend styling is CSS Modules (`*.module.css` per component). Routing is a
  hash route, not react-router.
