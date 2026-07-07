"""One-time copy of books + segments from the legacy SQLite file into Postgres.

Run inside the backend container after `docker compose up -d`:

    docker compose exec backend python scripts/migrate_sqlite_to_postgres.py

Refuses to run if Postgres already has books, so it can't double-import.
"""

import os
import sqlite3
import sys

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine, init_db  # noqa: E402

SQLITE_PATH = "storage/audiobooklib.db"

BOOK_COLS = [
    "id", "title", "author", "filename", "pdf_path", "status",
    "page_count", "genre", "year", "notes", "created_at",
]
SEGMENT_COLS = ["id", "book_id", "order", "text", "audio_path", "status", "duration"]


def main() -> None:
    if engine.dialect.name != "postgresql":
        sys.exit("DATABASE_URL is not Postgres — nothing to migrate into.")
    if not os.path.exists(SQLITE_PATH):
        sys.exit(f"SQLite file not found at {SQLITE_PATH}")

    init_db()

    src = sqlite3.connect(SQLITE_PATH)
    src.row_factory = sqlite3.Row

    with engine.begin() as dst:
        if dst.execute(text("SELECT COUNT(*) FROM books")).scalar():
            sys.exit("Postgres already has books — aborting to avoid duplicates.")

        books = src.execute("SELECT * FROM books").fetchall()
        for row in books:
            dst.execute(
                text(
                    "INSERT INTO books (id, title, author, filename, pdf_path, status, "
                    "page_count, genre, year, notes, created_at) "
                    "VALUES (:id, :title, :author, :filename, :pdf_path, :status, "
                    ":page_count, :genre, :year, :notes, :created_at)"
                ),
                {col: row[col] for col in BOOK_COLS},
            )

        segments = src.execute("SELECT * FROM segments").fetchall()
        for row in segments:
            dst.execute(
                text(
                    'INSERT INTO segments (id, book_id, "order", text, audio_path, '
                    "status, duration) "
                    'VALUES (:id, :book_id, :order, :text, :audio_path, :status, :duration)'
                ),
                {col: row[col] for col in SEGMENT_COLS},
            )

        for table in ("books", "segments"):
            dst.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
                )
            )

    src.close()
    print(f"Migrated {len(books)} books and {len(segments)} segments to Postgres.")


if __name__ == "__main__":
    main()
