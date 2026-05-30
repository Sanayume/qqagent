"""JWT helpers for the admin console."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from src.admin.security import get_admin_security_warnings
from src.utils.logger import log

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24


def _get_secret_key() -> str:
    from src.utils.config_loader import get_config_loader

    return get_config_loader().config.admin.get(
        "secret_key", "change-me-to-a-random-string"
    )


class TokenData(BaseModel):
    username: str
    exp: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


security = HTTPBearer(auto_error=False)


def create_access_token(username: str, expires_delta: Optional[timedelta] = None) -> str:
    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    expire = datetime.utcnow() + expires_delta
    payload = {
        "sub": username,
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    from src.utils.config_loader import get_config_loader

    for warning in get_admin_security_warnings(get_config_loader().config.admin):
        log.warning(f"Admin security warning: {warning}")
    return jwt.encode(payload, _get_secret_key(), algorithm=ALGORITHM)


def verify_token(token: str) -> Optional[TokenData]:
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])
        username = payload.get("sub")
        exp_raw = payload.get("exp")
        if not username or exp_raw is None:
            return None
        return TokenData(username=username, exp=datetime.fromtimestamp(exp_raw))
    except JWTError:
        return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = verify_token(credentials.credentials)
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token_data.username


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[str]:
    if credentials is None:
        return None

    token_data = verify_token(credentials.credentials)
    if token_data is None:
        return None

    return token_data.username


def extract_websocket_token(websocket: WebSocket) -> str | None:
    auth_header = websocket.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return token

    token = websocket.query_params.get("token")
    return token.strip() if token else None


async def authenticate_websocket(websocket: WebSocket) -> str | None:
    token = extract_websocket_token(websocket)
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return None

    token_data = verify_token(token)
    if token_data is None:
        await websocket.close(code=1008, reason="Invalid token")
        return None

    return token_data.username
