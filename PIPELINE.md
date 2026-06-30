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
            Synth["synthesize_segment × N\n─────────────\nOpenAI tts-1-hd\nvoice: alloy\n→ MP3 saved to storage/audio/"]
        end

        Synth -->|"chord callback"| Finalize
        Finalize["finalize_book\n─────────────\nall ready → complete\nany error  → error"]
    end

    Finalize --> DB

    DB -->|"poll every 3s"| Frontend
    Frontend["React Frontend\n─────────────\nBook cards\nStatus + progress bar\nEdit modal + Suggest"]
    Frontend -->|"GET /api/audio/{id}\nHTTP 206 Partial Content\n(range requests)"| Player["Audio Player\n─────────────\nSegment pills\n±15s skip\nOverall progress"]
```

## Status flow

```
Book:    pending → processing → synthesizing → complete
                                             ↘ error

Segment: pending → processing → ready
                              ↘ error
```

## Services

| Service  | Role                        |
|----------|-----------------------------|
| FastAPI  | REST API, file storage      |
| Celery   | Background task execution   |
| Redis    | Broker + result backend     |
| SQLite   | Persistent state            |
| OpenAI   | TTS (`tts-1-hd`) + metadata suggestions (`gpt-4o-mini`) |
