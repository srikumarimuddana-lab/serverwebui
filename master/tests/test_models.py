import pytest
from master.app.models.user import User
from master.app.models.agent import Agent, RegistrationToken
from master.app.models.audit import AuditLog


@pytest.mark.asyncio
async def test_create_user(db_session):
    user = User(username="admin", password_hash="hashed", role="admin")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    assert user.id is not None
    assert user.username == "admin"
    assert user.role == "admin"


@pytest.mark.asyncio
async def test_create_agent(db_session):
    agent = Agent(hostname="server1", ip_address="192.168.1.10", port=8420)
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)
    assert agent.id is not None
    assert agent.status == "pending"


@pytest.mark.asyncio
async def test_create_audit_log(db_session):
    log = AuditLog(user_id=1, agent_id=1, action="terminal.open", details="Opened terminal session")
    db_session.add(log)
    await db_session.commit()
    await db_session.refresh(log)
    assert log.id is not None
