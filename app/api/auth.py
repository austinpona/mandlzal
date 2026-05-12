"""Auth endpoints: register, login, /me, list/promote users (admin)."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.config import settings
from app.core.audit import log_action
from app.core.rate_limit import limiter
from app.core.security import hash_password, verify_password, create_access_token
from app.database import get_db
from app.models.user import Role, User
from app.schemas.auth import RoleUpdate, Token, UserOut, UserRegister


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
# Lambda lets us re-read the limit on every request, so tests (and
# `RATE_LIMIT_REGISTER` env overrides at runtime) take effect without
# re-importing this module.
@limiter.limit(lambda: settings.RATE_LIMIT_REGISTER)
def register(request: Request, payload: UserRegister, db: Session = Depends(get_db)) -> User:
    """Self-service registration.

    Bootstrap rule: the very first user becomes **admin**. All subsequent
    self-registrations default to **viewer** (read-only) - an admin must
    promote them via `PATCH /auth/users/{id}/role`.
    """
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    is_first_user = db.query(User).count() == 0
    role = Role.admin if is_first_user else Role.viewer
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=role,
        is_admin=(role == Role.admin),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
@limiter.limit(lambda: settings.RATE_LIMIT_LOGIN)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    """OAuth2 password flow - accepts `username` (email) + `password` as form."""
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    token = create_access_token(user.id, extra={"email": user.email, "role": user.role.value})
    return Token(access_token=token)


@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)) -> User:
    return current


# ----- Admin user management -----


@router.get("/users", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[User]:
    return db.query(User).order_by(User.id.asc()).all()


@router.patch("/users/{user_id}/role", response_model=UserOut)
def set_user_role(
    user_id: int,
    payload: RoleUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_admin),
) -> User:
    """Promote / demote a user. Admins cannot demote *themselves* to avoid
    accidentally locking the system out of admin access."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current.id and payload.role != Role.admin:
        raise HTTPException(status_code=400, detail="Refusing to demote yourself")

    user.role = payload.role
    user.is_admin = (payload.role == Role.admin)
    log_action(
        db, actor=current.email, action="SET_USER_ROLE",
        entity_type="user", entity_id=user.id,
        details={"new_role": payload.role.value},
    )
    db.commit()
    db.refresh(user)
    return user
