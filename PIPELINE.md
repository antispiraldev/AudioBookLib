# AudioBookLib Pipeline

```mermaid
flowchart TD
    Upload["User: Upload PDF\n(title, author)"]
    API["FastAPI\nPOST /api/books/"]
    DB[("SQLite\nBook + Segments")]
    Queue["Redis\nTask Queue"]

    Upload -->|multipart/form-data| API
    API --> DB
    API -->|ingest_and_synthesize.delay| Queue

    Queue --> Ingest

    subgraph Worker ["Celery Worker (concurrency=5)"]
        Ingest["ingest_and_synthesize\n─────────────────\nPyMuPDF block/span analysis\n• detect body font size\n• skip headers / footers\n• skip page numbers\n• skip footnotes\n• rejoin hyphenated breaks\n• format headings for TTS\nChunk text ~3500 chars"]
        Ingest -->|"Celery group"| Synth

        subgraph Parallel ["Parallel segment tasks (up to 5)"]
            Synth["synthesize_segment × N\n─────────────\nOpenAI tts-1-hd\nvoice: alloy\n→ MP3 written to local temp\n→ uploaded to R2\n→ local temp deleted"]
        end

        Synth -->|"chord callback"| Finalize
        Finalize["finalize_book\n─────────────\nall ready → complete\nany error  → error"]
    end

    Finalize --> DB

    DB -->|"poll every 3s"| Frontend
    Frontend["React Frontend\n─────────────\nBook cards\nStatus + progress bar\nEdit modal + Suggest"]
    Frontend -->|"GET /api/audio/{id}\n→ 302 to signed R2 URL\n(1 hr expiry)"| R2
    R2["Cloudflare R2\n─────────────\nPrivate bucket\nSigned URLs\nNo egress fees"]
    R2 -->|"Audio stream\n(range requests)"| Player["Audio Player\n─────────────\nSegment pills\n±15s skip\nOverall progress"]
```

## Status flow

```
Book:    pending → processing → synthesizing → complete
                                             ↘ error

Segment: pending → processing → ready
                              ↘ error
```

## Services

| Service         | Role                                              |
|-----------------|---------------------------------------------------|
| FastAPI         | REST API, file storage                            |
| Celery          | Background task execution                         |
| Redis           | Broker + result backend                           |
| SQLite          | Persistent metadata                               |
| Cloudflare R2   | MP3 storage (private bucket, signed URLs)         |
| OpenAI tts-1-hd | Audio synthesis                                   |
| OpenAI gpt-4o-mini | Metadata suggestions                           |

## Hosting

| Component  | Provider        | Notes                              |
|------------|-----------------|------------------------------------|
| App server | DigitalOcean droplet | FastAPI + Celery + Redis + nginx (port 80) |
| Storage    | Cloudflare R2   | PDFs (local) + MP3s (R2)           |
| CDN / SSL  | Cloudflare      | DNS proxy, free SSL                |

## Fallback (local dev)

If `R2_ACCOUNT_ID` is not set, audio is served from the local filesystem
with range-request streaming. No code changes needed to switch modes.
