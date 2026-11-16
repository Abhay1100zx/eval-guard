"""Clerk session-token verification for the FastAPI backend.

Configure with ONE of:
  CLERK_PUBLISHABLE_KEY   (pk_test_... / pk_live_...)  -> issuer + JWKS URL are derived from it
  CLERK_ISSUER + CLERK_JWKS_URL                         -> explicit
Set EVALGUARD_AUTH_DISABLED=true to bypass (local dev / tests only). Unconfigured = fail closed (503).
"""
import base64
import os
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

import jwt
from fastapi import Depends, HTTPException, Request
from jwt import PyJWKClient


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def auth_disabled() -> bool:
    return _env("EVALGUARD_AUTH_DISABLED").lower() in ("1", "true", "yes")


def _issuer_and_jwks() -> Optional[Tuple[str, str]]:
    issuer, jwks = _env("CLERK_ISSUER"), _env("CLERK_JWKS_URL")
    if issuer and jwks:
        return issuer.rstrip("/"), jwks
    pk = _env("CLERK_PUBLISHABLE_KEY") or _env("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY")
    if pk.count("_") >= 2:
        encoded = pk.split("_", 2)[2]
        try:
            domain = base64.b64decode(encoded + "=" * (-len(encoded) % 4)).decode().rstrip("$")
        except Exception:
            return None
        if domain:
            return f"https://{domain}", f"https://{domain}/.well-known/jwks.json"
    return None


def _authorized_parties() -> set:
    raw = _env("CLERK_AUTHORIZED_PARTIES", "http://localhost:3000,http://127.0.0.1:3000")
    return {p.strip().rstrip("/") for p in raw.split(",") if p.strip()}


@lru_cache(maxsize=2)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, lifespan=3600)


def _signing_key(token: str):
    cfg = _issuer_and_jwks()
    return _jwks_client(cfg[1]).get_signing_key_from_jwt(token).key


def verify_token(token: str) -> Dict[str, Any]:
    cfg = _issuer_and_jwks()
    if not cfg:
        raise HTTPException(503, "Auth is not configured: set CLERK_PUBLISHABLE_KEY (or EVALGUARD_AUTH_DISABLED=true for local dev)")
    issuer, _ = cfg
    try:
        claims = jwt.decode(
            token, _signing_key(token), algorithms=["RS256"], issuer=issuer,
            options={"require": ["exp", "iat", "sub"], "verify_aud": False}, leeway=10,
        )
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"Invalid session token: {e}")
    azp = claims.get("azp")
    if azp and azp.rstrip("/") not in _authorized_parties():
        raise HTTPException(401, "Token was issued for an unauthorized origin")
    return claims


def require_user(request: Request) -> Dict[str, Any]:
    """FastAPI dependency: returns Clerk claims (sub = user id) or raises 401."""
    if auth_disabled():
        return {"sub": "dev-user", "dev": True}
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Missing bearer token")
    return verify_token(token)


CurrentUser = Depends(require_user)
