"""Auth-related request/response models."""
from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.user import Role


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str | None = None
    is_admin: bool
    role: Role

    model_config = ConfigDict(from_attributes=True)


class RoleUpdate(BaseModel):
    role: Role
