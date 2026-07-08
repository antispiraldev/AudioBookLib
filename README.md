# VoxShelf

A personal audiobook library that converts PDFs into high-quality text-to-speech audio.

Upload a PDF, and VoxShelf parses it with structure-aware extraction, synthesizes it in parallel segments using OpenAI TTS, and streams it back with a chapter-aware audio player.

Live at [voxshelf.io](https://voxshelf.io)

## Features

- PDF upload with automatic text extraction (PyMuPDF block/span analysis)
- Parallel TTS synthesis via OpenAI `tts-1-hd` (alloy voice)
- Editable book metadata with AI-powered suggestions (GPT-4o-mini)
- Segment-based audio player with ±15s skip and overall progress
- Cloudflare R2 storage for MP3s with signed URL delivery
- Retry/refresh for stuck synthesis jobs

## Stack

| Layer    | Technology                          |
|----------|-------------------------------------|
| Backend  | FastAPI + SQLAlchemy + PostgreSQL (Alembic) |
| Tasks    | Celery + Redis                      |
| Frontend | React + Vite                        |
| TTS      | OpenAI tts-1-hd                     |
| Storage  | Cloudflare R2 (S3-compatible)       |
| Hosting  | DigitalOcean + Cloudflare CDN/SSL   |

See [PIPELINE.md](PIPELINE.md) for a full pipeline diagram.

## Running locally

```bash
cp .env.example .env   # fill in OPENAI_API_KEY at minimum
docker compose up --build
```

Open `http://localhost` — the API is at `http://localhost/api/`.

R2 storage is optional. If `R2_ACCOUNT_ID` is not set, audio is served from the local filesystem.

## Environment variables

| Variable              | Required | Description                        |
|-----------------------|----------|------------------------------------|
| `OPENAI_API_KEY`      | Yes      | OpenAI API key                     |
| `POSTGRES_PASSWORD`   | Yes*     | Postgres password (*in Docker; bare local dev falls back to SQLite) |
| `R2_ACCOUNT_ID`       | No       | Cloudflare account ID              |
| `R2_ACCESS_KEY_ID`    | No       | R2 S3-compatible access key        |
| `R2_SECRET_ACCESS_KEY`| No       | R2 S3-compatible secret key        |
| `R2_BUCKET_NAME`      | No       | R2 bucket name (default: `audiobooklib`) |
| `GOOGLE_CLIENT_ID`    | No       | Google OAuth client (omit to disable sign-in) |
| `GOOGLE_CLIENT_SECRET`| No       | Google OAuth client secret         |
| `SESSION_SECRET`      | With auth| Cookie signing key (`openssl rand -hex 32`) |
| `ADMIN_EMAIL`         | With auth| This Google account becomes admin on sign-in |
| `PUBLIC_BASE_URL`     | With auth| Origin used for the OAuth redirect (e.g. `https://voxshelf.io`) |
