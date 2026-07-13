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
        Ingest["ingest_book\n─────────────────\nPyMuPDF block/span analysis\n• detect body font size\n• skip headers / footers\n• skip page numbers\n• skip footnotes\n• rejoin hyphenated breaks\n• format headings for TTS\nHeuristic cleanup\n• NFKC / ligatures\n• strip Project Gutenberg header/license\n• strip leading table of contents / front matter\n• strip [n] citations, URLs/DOIs\n• drop trailing references section\n• expand e.g./i.e./et al.\nScanned-PDF check\n• too little text for the page count\n  (<200 ch/page or <1500 total)\n  → log warning (likely needs OCR)\nChunk text ~3500 chars (hard-split oversized)\ngpt-4o-mini polish (verbatim)\n→ status: review (pause)"]

        Review["Admin review\n─────────────\nGET /books/{id}/segments\n⚠ warn if PDF looks scanned\n  (no usable text layer)\nedit segments if needed\nPOST /books/{id}/synthesize"]
        Ingest -->|"status: review"| Review
        Review -->|"approve → Celery group"| Synth

        subgraph Parallel ["Parallel segment tasks (up to 5)"]
            Synth["synthesize_segment × N\n─────────────\nOpenAI gpt-4o-mini-tts\nvoice: alloy\nper-book instructions\n→ MP3 written to local temp\n→ uploaded to R2\n→ local temp deleted"]
        end

        Synth -->|"chord callback"| Finalize
        Finalize["finalize_book\n─────────────\nall ready → complete\nany error  → error"]
    end

    Finalize --> DB

    DB -->|"poll every 3s"| Frontend
    Frontend["React Frontend\n─────────────\nBook cards\nStatus + progress bar\nReview modal + Approve\n(scanned-PDF warning banner)\nEdit modal (+ narration\ninstructions) + Suggest"]
    Frontend -->|"GET /api/audio/{id}\n→ 302 to signed R2 URL\n(1 hr expiry)"| R2
    R2["Cloudflare R2\n─────────────\nPrivate bucket\nSigned URLs\nNo egress fees"]
    R2 -->|"Audio stream\n(range requests)"| Player["Audio Player\n─────────────\nSegment pills\n±15s skip\nOverall progress"]
```

## Status flow

```
Book:    pending → processing → review → synthesizing → complete
                                      (admin approves)  ↘ error

Segment: pending → processing → ready
                              ↘ error
```

## Scanned / image PDFs

PDFs without a real text layer (scans, photographed pages) extract to almost
nothing, which would otherwise synthesize to near-silence. Ingestion measures
the extracted text against the page count (`looks_scanned`): below ~200
chars/page, or under 1500 chars total, the book is treated as likely scanned.
It still lands in **review** rather than failing — the worker logs a warning and
the review modal shows a banner (mirroring the same threshold) telling the admin
the PDF probably needs OCR and should not be approved.

The `scripts/preview_extract.py` diagnostic reports chars/page and the same
`SCANNED — needs OCR` note, alongside per-segment quality flags
(`GIBBERISH`, `SYMBOL-HEAVY`, `OCR-SPACING`, `GUTENBERG-RESIDUE`, residual
citations/URLs) for spot-checking extraction before synthesis.

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
