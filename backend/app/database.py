from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os

os.makedirs("storage", exist_ok=True)

engine = create_engine(
    "sqlite:///storage/audiobooklib.db",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db():
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate():
    import sqlite3
    conn = sqlite3.connect("storage/audiobooklib.db")
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(books)")
    existing = {row[1] for row in cur.fetchall()}
    for col, typedef in [("genre", "TEXT"), ("year", "INTEGER"), ("notes", "TEXT")]:
        if col not in existing:
            cur.execute(f"ALTER TABLE books ADD COLUMN {col} {typedef}")
    conn.commit()
    conn.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
