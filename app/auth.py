from __future__ import annotations

import os

from fastapi import Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from . import db


APP_ENV = (os.getenv("APP_ENV", "development") or "development").strip().lower().split()[0]
IS_PRODUCTION = APP_ENV in {"prod", "production"}
SECRET_KEY = (os.getenv("SECRET_KEY") or "").strip()
if IS_PRODUCTION and not SECRET_KEY:
    raise RuntimeError("SECRET_KEY must be set when APP_ENV=production.")
SECRET_KEY = SECRET_KEY or "dev-only-change-this-secret-key"
COOKIE_NAME = "streza_admin"
MAX_AGE_SECONDS = 60 * 60 * 8
CSRF_MAX_AGE_SECONDS = MAX_AGE_SECONDS
COOKIE_SECURE = (os.getenv("COOKIE_SECURE", "true" if IS_PRODUCTION else "false") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
serializer = URLSafeTimedSerializer(SECRET_KEY, salt="streza-admin-session")
csrf_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="streza-admin-csrf")


def verify_credentials(username: str, password: str) -> bool:
    return db.verify_admin(username.strip(), password)


def create_token(username: str) -> str:
    return serializer.dumps({"username": username})


def read_token(token: str | None) -> str | None:
    if not token:
        return None
    try:
        data = serializer.loads(token, max_age=MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    username = data.get("username")
    return username if isinstance(username, str) else None


def create_csrf_token(username: str) -> str:
    return csrf_serializer.dumps({"username": username})


def verify_csrf_token(username: str, token: str | None) -> bool:
    if not token:
        return False
    try:
        data = csrf_serializer.loads(token, max_age=CSRF_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return False
    return data.get("username") == username


def current_admin(request: Request) -> str | None:
    return read_token(request.cookies.get(COOKIE_NAME))


def login_response(response: Response, username: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        create_token(username),
        max_age=MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )


def logout_response(response: Response) -> None:
    response.delete_cookie(
        COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )
