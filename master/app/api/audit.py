from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from master.app.core.database import get_session
from master.app.core.auth import require_role
from master.app.models.audit import AuditLog

router = APIRouter()

@router.get("/audit")
async def get_audit_logs(
    user=Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
):
    result = await session.execute(
        select(AuditLog).order_by(desc(AuditLog.timestamp)).offset(offset).limit(limit)
    )
    logs = result.scalars().all()
    return [
        {"id": l.id, "user_id": l.user_id, "agent_id": l.agent_id,
         "action": l.action, "details": l.details, "timestamp": str(l.timestamp)}
        for l in logs
    ]
