from __future__ import annotations

from uuid import UUID
from sqlalchemy.orm import Session

from db.models import Agent, Conversation, ConversationMember
from ai.tools.chat_naming import generate_dm_name, generate_self_dm_name


def ensure_self_dm(db: Session, user_id: UUID, agent: Agent) -> Conversation:
    convo = (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id, Conversation.self_agent_id == agent.id)
        .first()
    )
    if convo:
        return convo

    convo = Conversation(
        user_id=user_id,
        type="self",
        name=generate_self_dm_name(agent.name),
        self_agent_id=agent.id,
        created_by_agent_id=agent.id,
    )
    db.add(convo)
    db.flush()
    db.add(
        ConversationMember(conversation_id=convo.id, agent_id=agent.id, role="owner")
    )
    db.commit()
    return convo


def ensure_dm(db: Session, user_id: UUID, a: Agent, b: Agent) -> Conversation:
    if a.id == b.id:
        return ensure_self_dm(db, user_id, a)

    # Order by id string for deterministic pair ordering
    a_id, b_id = (a.id, b.id) if str(a.id) < str(b.id) else (b.id, a.id)

    convo = (
        db.query(Conversation)
        .filter(
            Conversation.user_id == user_id,
            Conversation.dm_a_id == a_id,
            Conversation.dm_b_id == b_id,
        )
        .first()
    )
    if convo:
        return convo

    name = generate_dm_name(a.name, b.name)
    convo = Conversation(
        user_id=user_id,
        type="dm",
        name=name,
        dm_a_id=a_id,
        dm_b_id=b_id,
        created_by_agent_id=a.id,
    )
    db.add(convo)
    db.flush()
    db.add_all(
        [
            ConversationMember(conversation_id=convo.id, agent_id=a.id, role="member"),
            ConversationMember(conversation_id=convo.id, agent_id=b.id, role="member"),
        ]
    )
    db.commit()
    return convo
