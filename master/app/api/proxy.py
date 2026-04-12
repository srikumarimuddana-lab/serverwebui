from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from master.app.core.database import get_session
from master.app.core.auth import get_current_user
from master.app.models.agent import Agent
from master.app.models.user import User

router = APIRouter(prefix="/agents/{agent_id}")


async def _get_agent(agent_id: int, session: AsyncSession) -> Agent:
    result = await session.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.get("/files/{path:path}")
async def proxy_files_get(agent_id: int, path: str, request: Request,
                          user: User = Depends(get_current_user),
                          session: AsyncSession = Depends(get_session)):
    agent = await _get_agent(agent_id, session)
    proxy = request.app.state.agent_proxy
    result = await proxy.forward_get(agent.ip_address, agent.port, f"/files/{path}", dict(request.query_params))
    return result["body"]


@router.post("/files/{path:path}")
async def proxy_files_post(agent_id: int, path: str, request: Request,
                           user: User = Depends(get_current_user),
                           session: AsyncSession = Depends(get_session)):
    agent = await _get_agent(agent_id, session)
    proxy = request.app.state.agent_proxy
    result = await proxy.forward_post(agent.ip_address, agent.port, f"/files/{path}")
    return result["body"]


@router.delete("/files/{path:path}")
async def proxy_files_delete(agent_id: int, path: str, request: Request,
                             user: User = Depends(get_current_user),
                             session: AsyncSession = Depends(get_session)):
    agent = await _get_agent(agent_id, session)
    proxy = request.app.state.agent_proxy
    result = await proxy.forward_delete(agent.ip_address, agent.port, f"/files/{path}")
    return result["body"]


@router.get("/stats")
async def proxy_stats(agent_id: int, request: Request,
                      user: User = Depends(get_current_user),
                      session: AsyncSession = Depends(get_session)):
    agent = await _get_agent(agent_id, session)
    proxy = request.app.state.agent_proxy
    result = await proxy.forward_get(agent.ip_address, agent.port, "/stats")
    return result["body"]


@router.get("/services")
async def proxy_services(agent_id: int, request: Request,
                         user: User = Depends(get_current_user),
                         session: AsyncSession = Depends(get_session)):
    agent = await _get_agent(agent_id, session)
    proxy = request.app.state.agent_proxy
    result = await proxy.forward_get(agent.ip_address, agent.port, "/services")
    return result["body"]


@router.post("/services/{name}/{action}")
async def proxy_service_action(agent_id: int, name: str, action: str, request: Request,
                               user: User = Depends(get_current_user),
                               session: AsyncSession = Depends(get_session)):
    agent = await _get_agent(agent_id, session)
    proxy = request.app.state.agent_proxy
    result = await proxy.forward_post(agent.ip_address, agent.port, f"/services/{name}/{action}")
    return result["body"]


@router.get("/logs/{path:path}")
async def proxy_logs(agent_id: int, path: str, request: Request,
                     user: User = Depends(get_current_user),
                     session: AsyncSession = Depends(get_session)):
    agent = await _get_agent(agent_id, session)
    proxy = request.app.state.agent_proxy
    result = await proxy.forward_get(agent.ip_address, agent.port, f"/logs/{path}", dict(request.query_params))
    return result["body"]
