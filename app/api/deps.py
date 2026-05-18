"""Shared FastAPI dependencies (auth + RBAC + DB)."""
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.database import get_db
from app.models.user import Role, User, role_at_least


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
# `auto_error=False` lets us look at the header without 401'ing when it's
# missing. Used by endpoints that work for both anonymous and logged-in
# callers (e.g. the public funeral-cover signup, which records the agent
# in the audit log when they're signed in).
oauth2_optional = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """Resolve the authenticated `User` from a bearer JWT."""
    creds_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("type") == "device":
            raise creds_exc
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise creds_exc
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise creds_exc
    return user


def require_role(minimum: Role) -> Callable[[User], User]:
    """FastAPI dependency factory: enforce that the current user's role
    is at least `minimum` in the role hierarchy (viewer < agent < admin).
    """
    def _dep(user: User = Depends(get_current_user)) -> User:
        if not role_at_least(user.role, minimum):
            raise HTTPException(status_code=403, detail=f"Requires role {minimum.value} or higher")
        return user
    _dep.__name__ = f"require_{minimum.value}"
    return _dep


def get_current_user_optional(
    token: str | None = Depends(oauth2_optional),
    db: Session = Depends(get_db),
) -> User | None:
    """Return the authenticated user, or None if the request is anonymous.

    Unlike `get_current_user`, an invalid or missing token returns None
    instead of raising. Use this on endpoints that work without auth but
    want to know the caller when it's available (e.g. for audit logs).
    """
    if not token:
        return None
    try:
        payload = decode_token(token)
        if payload.get("type") == "device":
            return None
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        return None
    user = db.get(User, user_id)
    return user if user and user.is_active else None


# Convenience aliases for the three common write/read tiers.
require_admin = require_role(Role.admin)
require_writer = require_role(Role.agent)   # agents and admins can write
require_viewer = require_role(Role.viewer)  # any authenticated user
