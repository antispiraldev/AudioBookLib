import os

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from ..database import get_db
from ..models import User
from ..schemas import UserOut

router = APIRouter()

oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


def _base_url() -> str:
    return os.getenv("PUBLIC_BASE_URL", "http://localhost").rstrip("/")


def _allowed(email: str) -> bool:
    """ALLOWED_EMAILS limits sign-in to listed accounts; empty = open."""
    raw = os.getenv("ALLOWED_EMAILS", "").strip()
    if not raw:
        return True
    allowed = {e.strip().lower() for e in raw.split(",") if e.strip()}
    admin = os.getenv("ADMIN_EMAIL", "").strip().lower()
    if admin:
        allowed.add(admin)
    return email.lower() in allowed


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    return db.get(User, user_id)


def require_admin(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise HTTPException(401, "Sign in required")
    if user.role != "admin":
        raise HTTPException(403, "Admin access required")
    return user


def require_ab_access(user: User | None = Depends(get_current_user)) -> User:
    """Gate for the A/B tests section. Admins always pass; other signed-in users
    need the explicit `ab_test_access` grant."""
    if user is None:
        raise HTTPException(401, "Sign in required")
    if user.role != "admin" and not user.ab_test_access:
        raise HTTPException(403, "No access to A/B tests")
    return user


@router.get("/login")
async def login(request: Request):
    if not os.getenv("GOOGLE_CLIENT_ID"):
        raise HTTPException(503, "Google sign-in is not configured")
    redirect_uri = f"{_base_url()}/api/auth/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def callback(request: Request, db: Session = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError:
        return RedirectResponse("/")
    info = token.get("userinfo")
    if not info or not info.get("sub"):
        return RedirectResponse("/")

    if not _allowed(info.get("email", "")):
        return RedirectResponse("/?login=denied")

    user = db.query(User).filter(User.google_id == info["sub"]).first()
    if not user:
        user = User(
            google_id=info["sub"],
            email=info.get("email", ""),
            display_name=info.get("name"),
        )
        db.add(user)

    admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    if admin_email and user.email.lower() == admin_email:
        user.role = "admin"

    db.commit()
    db.refresh(user)

    request.session["user_id"] = user.id
    return RedirectResponse("/")


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me", response_model=UserOut | None)
def me(user: User | None = Depends(get_current_user)):
    return user
