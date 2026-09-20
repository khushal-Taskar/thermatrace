import hashlib
import hmac
import secrets
from datetime import timedelta, timezone
from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from ..database import SessionLocal
from ..models import User, AuthSession, utcnow


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 310_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    salt, expected = stored.split("$")
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 310_000).hex()
    return hmac.compare_digest(actual, expected)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db, user):
    token = secrets.token_urlsafe(48)
    db.add(AuthSession(token_hash=token_hash(token), user_id=user.id, expires_at=utcnow() + timedelta(hours=8)))
    db.commit()
    return token


def get_user(token: str | None):
    if not token:
        return None
    with SessionLocal() as db:
        session = db.get(AuthSession, token_hash(token))
        if not session or session.expires_at.replace(tzinfo=timezone.utc) < utcnow():
            return None
        user=db.get(User, session.user_id)
        return user if user and user.active else None


def require_user(pharma_session: str | None = Cookie(default=None)):
    user = get_user(pharma_session)
    if not user:
        raise HTTPException(401, "Please sign in to continue")
    return user


def require_roles(*roles):
    def dependency(user=Depends(require_user)):
        if user.role not in roles:
            raise HTTPException(403, "Your account does not have permission for this action")
        return user
    return dependency
