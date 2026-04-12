from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from master.app.core.database import get_session
from master.app.core.auth import (
    verify_password, create_access_token, create_refresh_token,
    decode_token, get_current_user,
)
from master.app.models.user import User

router = APIRouter(prefix="/auth")

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenResponse(
        access_token=create_access_token(user.id, user.username, user.role),
        refresh_token=create_refresh_token(user.id),
    )

@router.post("/refresh")
async def refresh(user: User = Depends(get_current_user)):
    return {
        "access_token": create_access_token(user.id, user.username, user.role),
        "token_type": "bearer",
    }
