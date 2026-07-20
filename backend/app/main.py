import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

load_dotenv()

from .database import init_db
from .routers import books, audio, auth, admin, ab_tests
from .services.monitor import setup_web_file_logging

# Module level, not lifespan: uvicorn logs lines (startup, first requests)
# before the lifespan hook runs, and this process IS the web droplet.
setup_web_file_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="AudioBookLib", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "dev-secret-change-me"),
    max_age=14 * 24 * 3600,
    same_site="lax",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(books.router, prefix="/api/books", tags=["books"])
app.include_router(audio.router, prefix="/api/audio", tags=["audio"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(ab_tests.router, prefix="/api/ab-tests", tags=["ab-tests"])
