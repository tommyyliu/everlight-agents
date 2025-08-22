import pytest
from sqlalchemy import select

from db.models import Conversation, ConversationMember, ChatMessage, Agent
from ai.tools.chat_naming import generate_dm_name, generate_self_dm_name


@pytest.mark.asyncio
async def test_generate_names():
    assert (
        generate_dm_name("Safine", "Eforos")
        == "Direct Message between Eforos and Safine"
    )
    assert generate_dm_name("A", "B") == "Direct Message between A and B"
    assert generate_self_dm_name("Safine") == "Direct Message with Safine (self)"


def _ensure_dm(db, user_id, a: Agent, b: Agent):
    # store ordered pair
    a_id, b_id = (a.id, b.id) if str(a.id) < str(b.id) else (b.id, a.id)
    name = generate_dm_name(a.name, b.name)
    convo = (
        db.query(Conversation)
        .filter(
            Conversation.user_id == user_id,
            Conversation.dm_a_id == a_id,
            Conversation.dm_b_id == b_id,
        )
        .first()
    )
    if not convo:
        convo = Conversation(
            user_id=user_id, type="dm", name=name, dm_a_id=a_id, dm_b_id=b_id
        )
        db.add(convo)
        db.commit()
        db.add_all(
            [
                ConversationMember(
                    conversation_id=convo.id, agent_id=a.id, role="member"
                ),
                ConversationMember(
                    conversation_id=convo.id, agent_id=b.id, role="member"
                ),
            ]
        )
        db.commit()
    return convo


def _ensure_self(db, user_id, a: Agent):
    convo = (
        db.query(Conversation)
        .filter(
            Conversation.user_id == user_id,
            Conversation.self_agent_id == a.id,
        )
        .first()
    )
    if not convo:
        convo = Conversation(
            user_id=user_id,
            type="self",
            name=generate_self_dm_name(a.name),
            self_agent_id=a.id,
        )
        db.add(convo)
        db.commit()
        db.add(
            ConversationMember(conversation_id=convo.id, agent_id=a.id, role="owner")
        )
        db.commit()
    return convo


@pytest.mark.asyncio
async def test_conversation_uniqueness_and_members(db_session, test_user):
    # Create two agents
    a = Agent(user_id=test_user.id, name="Eforos", prompt="", tools=[])
    b = Agent(user_id=test_user.id, name="Safine", prompt="", tools=[])
    db_session.add_all([a, b])
    db_session.commit()

    # Ensure DM conversation is created once regardless of order
    convo1 = _ensure_dm(db_session, test_user.id, a, b)
    convo2 = _ensure_dm(db_session, test_user.id, b, a)
    assert convo1.id == convo2.id
    assert convo1.name == "Direct Message between Eforos and Safine"

    # Ensure members are both present
    members = (
        db_session.query(ConversationMember)
        .filter(ConversationMember.conversation_id == convo1.id)
        .all()
    )
    assert set(m.agent_id for m in members) == {a.id, b.id}

    # Ensure self conversation uniqueness
    self1 = _ensure_self(db_session, test_user.id, b)
    self2 = _ensure_self(db_session, test_user.id, b)
    assert self1.id == self2.id
    assert self1.name == "Direct Message with Safine (self)"


@pytest.mark.asyncio
async def test_chat_message_persistence(db_session, test_user):
    # Agents
    a = Agent(user_id=test_user.id, name="Eforos", prompt="", tools=[])
    b = Agent(user_id=test_user.id, name="Safine", prompt="", tools=[])
    db_session.add_all([a, b])
    db_session.commit()

    convo = _ensure_dm(db_session, test_user.id, a, b)

    # Create message
    msg = ChatMessage(conversation_id=convo.id, sender_agent_id=a.id, content="Hello")
    db_session.add(msg)
    db_session.commit()

    # Verify ordering by created_at works
    msgs = (
        db_session.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == convo.id)
            .order_by(ChatMessage.created_at.asc())
        )
        .scalars()
        .all()
    )
    assert len(msgs) == 1
    assert msgs[0].content == "Hello"
