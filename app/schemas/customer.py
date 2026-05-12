"""Customer Pydantic schemas."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.customer import CustomerStatus


class CustomerBase(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    id_number: str = Field(..., min_length=1, max_length=64)
    phone: str | None = None
    email: EmailStr | None = None


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    status: CustomerStatus | None = None


class CustomerOut(CustomerBase):
    id: int
    status: CustomerStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
