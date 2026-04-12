from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from master.app.core.database import get_session
from master.app.core.auth import require_role, hash_password
from master.app.models.user import User

router = APIRouter()

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "viewer"

class UpdateRoleRequest(BaseModel):
    role: str

@router.get("/users")
async def list_users(
    user=Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(User))
    users = result.scalars().all()
    return [{"id": u.id, "username": u.username, "role": u.role} for u in users]

@router.post("/users", status_code=201)
async def create_user(
    body: CreateUserRequest,
    user=Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    if body.role not in ("admin", "operator", "viewer"):
        raise HTTPException(status_code=400, detail="Invalid role")
    existing = await session.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already exists")
    new_user = User(username=body.username, password_hash=hash_password(body.password), role=body.role)
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)
    return {"id": new_user.id, "username": new_user.username, "role": new_user.role}

@router.put("/users/{user_id}/role")
async def update_role(
    user_id: int,
    body: UpdateRoleRequest,
    user=Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    if body.role not in ("admin", "operator", "viewer"):
        raise HTTPException(status_code=400, detail="Invalid role")
    result = await session.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    target.role = body.role
    await session.commit()
    return {"id": target.id, "username": target.username, "role": target.role}
