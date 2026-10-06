"""Request and response bodies for auth and /me."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignupIn(BaseModel):
    email: EmailStr
    # Letters, digits and "_": safe in URLs and mentions.
    username: str = Field(pattern=r"^[A-Za-z0-9_]{3,32}$")
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=256)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


class TokenOut(BaseModel):
    """The refresh token is not here: it goes in an httpOnly cookie."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    username: str
    display_name: str
    email_verified: bool
    created_at: datetime


class MeOut(UserOut):
    is_admin: bool


class MeUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
