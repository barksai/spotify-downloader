"""
Spotify MP3 Downloader - Authentification du serveur Web
Protection par mot de passe (variable d'environnement APP_PASSWORD) avec cookie de session
HttpOnly / SameSite=Strict, ou en-tête "Authorization: Bearer <APP_PASSWORD>" pour les scripts.
"""
import hashlib
import hmac
import os
import secrets
from typing import Optional

from fastapi import Request

SESSION_COOKIE = "sd_session"
SESSION_MAX_AGE = 30 * 24 * 3600  # 30 jours


def get_app_password() -> str:
    return os.getenv("APP_PASSWORD", "")


def auth_enabled() -> bool:
    return bool(get_app_password())


def session_token(password: Optional[str] = None) -> str:
    """Jeton de session dérivé du mot de passe : changer APP_PASSWORD invalide toutes les sessions."""
    pwd = get_app_password() if password is None else password
    return hmac.new(pwd.encode("utf-8"), b"spotify-downloader-session", hashlib.sha256).hexdigest()


def check_password(candidate: str) -> bool:
    expected = get_app_password()
    if not expected:
        return True
    return secrets.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


def is_authenticated(request: Request) -> bool:
    if not auth_enabled():
        return True

    cookie = request.cookies.get(SESSION_COOKIE, "")
    if cookie and secrets.compare_digest(cookie, session_token()):
        return True

    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return check_password(auth_header[7:].strip())

    return False
