from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os

os.makedirs("storage", exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///storage/audiobooklib.db")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db():
    """Bring the schema to the latest Alembic revision.

    Databases created before Alembic was introduced have tables but no
    alembic_version — stamp those as current before upgrading.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if "books" in tables and "alembic_version" not in tables:
        command.stamp(cfg, "head")
    command.upgrade(cfg, "head")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
