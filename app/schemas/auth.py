from pydantic import BaseModel, EmailStr


class SignupIn(BaseModel):
    email: EmailStr
    password: str
    nickname: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
