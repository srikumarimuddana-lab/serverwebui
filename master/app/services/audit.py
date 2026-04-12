from sqlalchemy.ext.asyncio import AsyncSession
from master.app.models.audit import AuditLog


async def log_action(session: AsyncSession, user_id: int | None, agent_id: int | None, action: str, details: str | None = None):
    entry = AuditLog(user_id=user_id, agent_id=agent_id, action=action, details=details)
    session.add(entry)
    await session.commit()
