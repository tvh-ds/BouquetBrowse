import hmac
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache

import httpx
import jwt
from fastapi import Depends, HTTPException, Request
from jwt import PyJWKClient
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db, utcnow
from .models import AppUser


@dataclass
class User:
    id: str
    role: str


def require_proxy(request: Request):
    expected = get_settings().internal_api_token
    if not hmac.compare_digest(request.headers.get("x-bouquet-proxy", ""), expected):
        raise HTTPException(401, detail={"code": "proxy_required", "message": "Use the authenticated website."})


@lru_cache
def jwks_client():
    return PyJWKClient(f"{get_settings().supabase_url}/auth/v1/.well-known/jwks.json", cache_keys=True)


def demo_token(role: str):
    return jwt.encode(
        {
            "sub": f"demo-{role}",
            "role": role,
            "iss": "bouquetbrowse-demo",
            "aud": "bouquetbrowse",
            "iat": utcnow(),
            "exp": utcnow() + timedelta(hours=8),
        },
        get_settings().demo_secret,
        algorithm="HS256",
    )


def require_user(request: Request, db: Session = Depends(get_db)):
    require_proxy(request)
    token = request.headers.get("authorization", "").removeprefix("Bearer ")
    try:
        settings = get_settings()
        if settings.app_mode == "demo":
            claims = jwt.decode(
                token, settings.demo_secret, algorithms=["HS256"], audience="bouquetbrowse", issuer="bouquetbrowse-demo"
            )
            role = claims.get("role")
            if role not in {"tester", "reviewer", "admin"}:
                raise jwt.InvalidTokenError("Unknown role")
            return User(claims["sub"], role)
        key = jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            issuer=f"{settings.supabase_url}/auth/v1",
        )
        member = db.get(AppUser, claims["sub"])
        if not member or member.disabled:
            raise HTTPException(
                403, detail={"code": "invite_required", "message": "An active research-pilot membership is required."}
            )
        return User(member.id, member.role)
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(401, detail={"code": "session_expired", "message": "Sign in to continue."}) from exc


def require_reviewer(user: User = Depends(require_user)):
    if user.role not in {"reviewer", "admin"}:
        raise HTTPException(
            403,
            detail={"code": "reviewer_required", "message": "A reviewer or administrator must perform this action."},
        )
    return user


def require_admin(user: User = Depends(require_user)):
    if user.role != "admin":
        raise HTTPException(
            403, detail={"code": "admin_required", "message": "Only administrators can perform this action."}
        )
    return user


def supabase_password(email: str, password: str):
    s = get_settings()
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        response = client.post(
            f"{s.supabase_url}/auth/v1/token?grant_type=password",
            headers={"apikey": s.supabase_publishable_key},
            json={"email": email, "password": password},
        )
    if response.status_code != 200:
        raise HTTPException(
            401, detail={"code": "invalid_credentials", "message": "Unable to sign in with those credentials."}
        )
    body = response.json()
    return {
        "access_token": body["access_token"],
        "refresh_token": body["refresh_token"],
        "expires_in": body["expires_in"],
    }
