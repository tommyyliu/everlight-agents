import pytest
from uuid import uuid4

from db.models import (
    Agent,
    AgentSubscription,
    Conversation,
    ConversationMember,
)
from ai.tools.chat_seed import ensure_dm, ensure_self_dm
from ai.default_agents import create_default_agents_for_user


@pytest.mark.asyncio
async def test_ensure_self_and_dm_idempotent(db_session, test_user):
    # Create two agents for the user
    a = Agent(user_id=test_user.id, name="Eforos", prompt="", tools=[])
    b = Agent(user_id=test_user.id, name="Safine", prompt="", tools=[])
    db_session.add_all([a, b])
    db_session.commit()

    # Self-DM should be idempotent
    self1 = ensure_self_dm(db_session, test_user.id, b)
    self2 = ensure_self_dm(db_session, test_user.id, b)
    assert self1.id == self2.id
    assert self1.type == "self"
    members = (
        db_session.query(ConversationMember)
        .filter(ConversationMember.conversation_id == self1.id)
        .all()
    )
    assert {m.agent_id for m in members} == {b.id}

    # DM between a and b should be unique regardless of call order
    dm1 = ensure_dm(db_session, test_user.id, a, b)
    dm2 = ensure_dm(db_session, test_user.id, b, a)
    assert dm1.id == dm2.id
    assert dm1.type == "dm"
    members = (
        db_session.query(ConversationMember)
        .filter(ConversationMember.conversation_id == dm1.id)
        .all()
    )
    assert {m.agent_id for m in members} == {a.id, b.id}


@pytest.mark.asyncio
async def test_default_agents_seeding_creates_conversations_and_subscriptions(
    db_session,
):
    # Create a fresh user
    from db.models import User

    user = User(id=uuid4(), firebase_user_id="fb_seed", email="seed@example.com")
    db_session.add(user)
    db_session.commit()

    # Run default agent creation (Eforos + Safine)
    create_default_agents_for_user(db_session, user)

    # Load the agents
    agents = db_session.query(Agent).filter(Agent.user_id == user.id).all()
    names = {a.name for a in agents}
    assert names == {"Eforos", "Safine"}

    # Check subscriptions for private channels
    subs = db_session.query(AgentSubscription).all()
    sub_map = {(s.agent_id, s.channel) for s in subs}
    eforos = next(a for a in agents if a.name == "Eforos")
    safine = next(a for a in agents if a.name == "Safine")
    assert (eforos.id, "eforos") in sub_map
    assert (safine.id, "safine") in sub_map

    # Check that DM and self conversations exist
    convos = (
        db_session.query(Conversation).filter(Conversation.user_id == user.id).all()
    )
    # Should be 2 conversations: DM(Eforos,Safine) and Safine self-DM
    assert len(convos) == 2
    types = {c.type for c in convos}
    assert types == {"dm", "self"}

    # Validate members of DM include both agents; self-DM only Safine
    for c in convos:
        mems = (
            db_session.query(ConversationMember)
            .filter(ConversationMember.conversation_id == c.id)
            .all()
        )
        member_ids = {m.agent_id for m in mems}
        if c.type == "dm":
            assert member_ids == {eforos.id, safine.id}
        else:
            assert member_ids == {safine.id}
