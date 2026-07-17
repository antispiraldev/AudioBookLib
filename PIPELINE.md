# AudioBookLib Pipeline

```mermaid
flowchart TD
    Upload["User: Upload PDF\n(title, author)"]
    API["FastAPI\nPOST /api/books/"]
    DB[("PostgreSQL\nBook + Segments")]
    Queue["Redis\nTask Queue"]

    Upload -->|multipart/form-data| API
    API --> DB
    API -->|ingest_book.delay| Queue

    Queue --> Ingest

    subgraph Worker ["Celery Worker (concurrency=5)"]
        Ingest["ingest_book\n─────────────────\nPyMuPDF block/span analysis\n• detect body font size\n• skip headers / footers\n• skip page numbers\n• skip footnotes\n• rejoin hyphenated breaks\n• format headings for TTS\nHeuristic cleanup\n• NFKC / ligatures\n• strip Project Gutenberg header/license\n• strip leading table-of-contents block\n• strip [n] citations, URLs/DOIs\n• drop trailing references section\n• expand e.g./i.e./et al.\ndetect scanned PDFs (chars/page) → needs OCR\nChapter detection (regex + roman validation\n+ body-gap/dedup/longest-run filters)\nChunk ~1800 chars, chapter-aware\n(never crosses a chapter boundary;\nchapter_title on first segment)\ngpt-4o-mini polish (verbatim, parallel)\n→ status: review (pause)"]

        Review["Admin review\n─────────────\nGET /books/{id}/segments\nedit segments if needed\nPOST /books/{id}/synthesize"]
        Ingest -->|"status: review"| Review
        Review -->|"approve → Celery group"| Synth

        subgraph Parallel ["Parallel segment tasks (up to 5)"]
            Synth["synthesize_segment × N\n─────────────\nOpenAI gpt-4o-mini-tts\nvoice: onyx\nper-book instructions\n→ MP3 written to local temp\n→ uploaded to R2\n→ local temp deleted"]
        end

        Synth -->|"chord callback"| Finalize
        Finalize["finalize_book\n─────────────\nall ready → complete\nany error  → error"]
    end

    Finalize --> DB

    DB -->|"poll every 3s"| Frontend
    Frontend["React Frontend\n─────────────\nBook cards\nStatus + progress bar\nReview modal + Approve\nEdit modal (+ narration\ninstructions) + Suggest\nReprocess (re-run ingest,\n± replace PDF)"]
    Frontend -->|"POST /books/{id}/reprocess\nclear segments + audio,\n± upload new PDF → R2"| Queue
    Frontend -->|"GET /api/audio/{id}\n→ 302 to signed R2 URL\n(1 hr expiry)"| R2
    R2["Cloudflare R2\n─────────────\nPrivate bucket\nSigned URLs\nNo egress fees"]
    R2 -->|"Audio stream\n(range requests)"| Player["Audio Player\n─────────────\nSegment pills\nChapter dropdown + jump\n±15s skip\nOverall progress"]
```

## Status flow

```
Book:    pending → processing → review → synthesizing → complete
                                      (admin approves)  ↘ error

Segment: pending → processing → ready
                              ↘ error
```

## Services

| Service         | Role                                              |
|-----------------|---------------------------------------------------|
| FastAPI         | REST API, file storage                            |
| Celery          | Background task execution                         |
| Redis           | Broker + result backend                           |
| PostgreSQL      | Persistent metadata (Alembic migrations)          |
| Cloudflare R2   | MP3 storage (private bucket, signed URLs)         |
| OpenAI gpt-4o-mini-tts | Audio synthesis (per-book narration instructions) |
| OpenAI gpt-4o-mini | Metadata suggestions + text cleanup polish     |
| Google OAuth (Authlib) | Sign-in; admin role gates uploads/edits/synthesis |

## Hosting

| Component  | Provider        | Notes                              |
|------------|-----------------|------------------------------------|
| App server | DigitalOcean droplet | FastAPI + Celery + Redis + nginx (port 80) |
| Storage    | Cloudflare R2   | PDFs + MP3s                        |
| CDN / SSL  | Cloudflare      | DNS proxy, free SSL                |

## Fallback (local dev)

If `R2_ACCOUNT_ID` is not set, audio and PDFs are stored on the local
filesystem, with range-request streaming for audio. If `DATABASE_URL` is
not set, SQLite is used instead of PostgreSQL. No code changes needed to
switch modes.
