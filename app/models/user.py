"""Application user for JWT-protected endpoints.

Each user has a role (RBAC):
  - admin  - everything, including delete & user management
  - agent  - create/update customers, policies, payments, members
  - viewer - read-only

`is_admin` is kept as a derived convenience flag (= role == admin) for
back-compat with older clients reading the field directly.
"""
import enum
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum

from app.database import Base


class Role(str, enum.Enum):
    admin = "admin"
    agent = "agent"
    viewer = "viewer"


# Role hierarchy: index implies level of privilege (higher = more powerful).
_ROLE_ORDER = {Role.viewer: 0, Role.agent: 1, Role.admin: 2}


def role_at_least(actual: Role, required: Role) -> bool:
    return _ROLE_ORDER[actual] >= _ROLE_ORDER[required]


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    # Kept for back-compat; mirrors `role == admin`. Set automatically.
    is_admin = Column(Boolean, default=False, nullable=False)
    role = Column(Enum(Role), default=Role.viewer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
