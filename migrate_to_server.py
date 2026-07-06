"""
Migrates local books to the remote server.

- Uploads local MP3s to R2 with IDs offset by SERVER_ID_OFFSET
- Writes a SQL file (migration.sql) to apply to the server DB

Run from the repo root:
    python migrate_to_server.py

Then copy migration.sql to the server and apply:
    scp migration.sql root@<droplet-ip>:/opt/voxshelf/AudioBookLib/
    # on server:
    docker compose exec -T backend sqlite3 storage/audiobooklib.db < migration.sql
"""

import os
import sqlite3
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "backend/storage/audiobooklib.db"
SERVER_ID_OFFSET = 2  # server already has books with IDs 1 and 2

account_id = os.environ["R2_ACCOUNT_ID"]
access_key = os.environ["R2_ACCESS_KEY_ID"]
secret_key = os.environ["R2_SECRET_ACCESS_KEY"]
bucket = os.environ.get("R2_BUCKET_NAME", "audiobooklib")

s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
)


def _q(val):
    if val is None:
        return "NULL"
    return "'" + str(val).replace("'", "''") + "'"


def r2_key_exists(key):
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError:
        return False


conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT * FROM books ORDER BY id")
books = cur.fetchall()

sql_lines = []
uploaded = 0
skipped = 0
missing = 0

for book in books:
    old_id = book["id"]
    new_id = old_id + SERVER_ID_OFFSET

    # Upload segments for this book
    cur.execute("SELECT * FROM segments WHERE book_id = ? ORDER BY \"order\"", (old_id,))
    segments = cur.fetchall()

    seg_inserts = []
    for seg in segments:
        local_path = seg["audio_path"]
        new_key = f"audio/{new_id}/{seg['order']:04d}.mp3"

        if local_path and ("storage/audio" in local_path):
            full_path = os.path.join("backend", local_path) if not local_path.startswith("backend/") else local_path
            if os.path.exists(full_path):
                if r2_key_exists(new_key):
                    print(f"  skip (exists): {new_key}")
                    skipped += 1
                else:
                    print(f"  upload: {full_path} → {new_key}")
                    s3.upload_file(full_path, bucket, new_key)
                    uploaded += 1
                audio_path_value = new_key
            else:
                print(f"  missing local file: {local_path}")
                missing += 1
                audio_path_value = None
        else:
            # Already an R2 key or None
            audio_path_value = seg["audio_path"]

        seg_inserts.append(
            f"INSERT INTO segments (id, book_id, \"order\", text, audio_path, status, duration) VALUES "
            f"({seg['id'] + SERVER_ID_OFFSET * 1000}, {new_id}, {seg['order']}, "
            f"{_q(seg['text'])}, {_q(audio_path_value)}, {_q(seg['status'])}, "
            f"{seg['duration'] if seg['duration'] is not None else 'NULL'});"
        )

    sql_lines.append(
        f"INSERT INTO books (id, title, author, filename, pdf_path, status, page_count, genre, year, notes, created_at) VALUES "
        f"({new_id}, {_q(book['title'])}, {_q(book['author'])}, {_q(book['filename'])}, "
        f"{_q(book['pdf_path'])}, {_q(book['status'])}, "
        f"{book['page_count'] if book['page_count'] is not None else 'NULL'}, "
        f"{_q(book['genre'])}, "
        f"{book['year'] if book['year'] is not None else 'NULL'}, "
        f"{_q(book['notes'])}, {_q(book['created_at'])});"
    )
    sql_lines.extend(seg_inserts)

conn.close()

with open("migration.sql", "w") as f:
    f.write("BEGIN;\n")
    f.write("\n".join(sql_lines))
    f.write("\nCOMMIT;\n")

print(f"\nDone. Uploaded: {uploaded}, Skipped (already in R2): {skipped}, Missing: {missing}")
print("migration.sql written — copy it to the server and apply with:")
print("  scp migration.sql root@<droplet-ip>:/opt/voxshelf/AudioBookLib/")
print("  # on server:")
print('  docker compose exec -T backend sqlite3 storage/audiobooklib.db < migration.sql')
