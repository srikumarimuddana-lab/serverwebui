import secrets
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from master.app.core.database import get_session
from master.app.core.auth import require_role, get_current_user
from master.app.models.agent import Agent, RegistrationToken
from master.app.models.user import User

router = APIRouter(prefix="/agents")

class RegisterRequest(BaseModel):
    token: str
    hostname: str
    ip_address: str
    port: int = 8420

@router.get("")
async def list_agents(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Agent))
    agents = result.scalars().all()
    return [
        {"id": a.id, "hostname": a.hostname, "ip_address": a.ip_address,
         "port": a.port, "status": a.status, "last_seen": str(a.last_seen) if a.last_seen else None}
        for a in agents
    ]

@router.post("/token", status_code=201)
async def generate_token(
    user=Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    token = secrets.token_urlsafe(32)
    reg_token = RegistrationToken(token=token)
    session.add(reg_token)
    await session.commit()
    return {"token": token}

@router.post("/register", status_code=201)
async def register_agent(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(RegistrationToken).where(
            RegistrationToken.token == body.token,
            RegistrationToken.used == False,
        )
    )
    reg_token = result.scalar_one_or_none()
    if not reg_token:
        raise HTTPException(status_code=401, detail="Invalid or used registration token")

    reg_token.used = True
    agent = Agent(hostname=body.hostname, ip_address=body.ip_address, port=body.port, status="active")
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return {"id": agent.id, "hostname": agent.hostname, "status": agent.status}

@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: int,
    user=Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await session.delete(agent)
    await session.commit()
    return {"deleted": agent_id}
