"""
Chat tools for agents: list conversations, fetch histories, and send messages.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import logfire
from pydantic import BaseModel
from pydantic_ai import RunContext
from sqlalchemy import select

from ai.tools.core import AgentContext, log_tool_call
from ai.tools.chat_seed import ensure_dm, ensure_self_dm
from db.models import (
    Agent as DBAgent,
    Conversation,
    ConversationMember,
    ChatMessage,
)
from db.session import get_db_session


class ListConversationsInput(BaseModel):
    kind: Optional[str] = None  # "dm" | "self" | None


async def list_conversations(
    ctx: RunContext[AgentContext], input_data: ListConversationsInput
) -> str:
    """List conversations for the user, showing headers first."""
    with logfire.span("list_conversations", kind=input_data.kind or "all"):
        log_tool_call(ctx, "list_conversations", input_data.model_dump())

        db = next(get_db_session())
        try:
            q = select(Conversation).where(Conversation.user_id == ctx.deps.user_id)
            if input_data.kind:
                q = q.where(Conversation.type == input_data.kind)
            conversations = db.execute(q).scalars().all()

            if not conversations:
                return "No conversations found."

            lines: list[str] = []
            for c in conversations:
                # Members
                member_join = (
                    db.query(ConversationMember, DBAgent)
                    .join(DBAgent, ConversationMember.agent_id == DBAgent.id)
                    .filter(ConversationMember.conversation_id == c.id)
                    .all()
                )
                members = ", ".join(a.name for _, a in member_join)

                # Last message time
                last_msg = (
                    db.execute(
                        select(ChatMessage)
                        .where(ChatMessage.conversation_id == c.id)
                        .order_by(ChatMessage.created_at.desc())
                        .limit(1)
                    )
                    .scalars()
                    .first()
                )
                last_at = (
                    last_msg.created_at.isoformat() if last_msg else "no messages yet"
                )

                lines.append(f"Conversation: {c.name} (id: {c.id})")
                lines.append(f"Members: {members}")
                lines.append(f"Last message: {last_at}")
                lines.append("---")

            return "\n".join(lines)
        finally:
            db.close()


class FetchDmHistoryInput(BaseModel):
    with_agent: str
    limit: int = 50
    before: Optional[datetime] = None
    after: Optional[datetime] = None


async def fetch_dm_history(
    ctx: RunContext[AgentContext], input_data: FetchDmHistoryInput
) -> str:
    """Fetch DM history with another agent. Headers first, then messages."""
    with logfire.span(
        "fetch_dm_history", with_agent=input_data.with_agent, limit=input_data.limit
    ):
        log_tool_call(ctx, "fetch_dm_history", input_data.model_dump())

        db = next(get_db_session())
        try:
            me = (
                db.query(DBAgent)
                .filter(
                    DBAgent.user_id == ctx.deps.user_id,
                    DBAgent.name == ctx.deps.agent_name,
                )
                .first()
            )
            other = (
                db.query(DBAgent)
                .filter(
                    DBAgent.user_id == ctx.deps.user_id,
                    DBAgent.name == input_data.with_agent,
                )
                .first()
            )
            if not me or not other:
                return "Error: one or both agents not found."

            convo = ensure_dm(db, ctx.deps.user_id, me, other)

            # Header
            members = (
                db.query(ConversationMember, DBAgent)
                .join(DBAgent, ConversationMember.agent_id == DBAgent.id)
                .filter(ConversationMember.conversation_id == convo.id)
                .all()
            )
            member_names = ", ".join(a.name for _, a in members)
            lines = [
                f"Conversation: {convo.name} (id: {convo.id})",
                f"Members: {member_names}",
                "---",
                "Messages:",
            ]

            # Messages
            q = select(ChatMessage).where(ChatMessage.conversation_id == convo.id)
            if input_data.before:
                q = q.where(ChatMessage.created_at < input_data.before)
            if input_data.after:
                q = q.where(ChatMessage.created_at > input_data.after)
            q = q.order_by(ChatMessage.created_at.asc()).limit(input_data.limit)
            msgs = db.execute(q).scalars().all()

            # Map sender ids to names
            agent_map = {a.id: a.name for _, a in members}

            for m in msgs:
                lines.append(
                    f"[{m.created_at.isoformat()}] {agent_map.get(m.sender_agent_id, 'unknown')}: {m.content}"
                )

            return "\n".join(lines)
        finally:
            db.close()


class FetchSelfHistoryInput(BaseModel):
    limit: int = 50
    before: Optional[datetime] = None
    after: Optional[datetime] = None


async def fetch_self_dm_history(
    ctx: RunContext[AgentContext], input_data: FetchSelfHistoryInput
) -> str:
    """Fetch self-DM history. Headers first, then messages."""
    with logfire.span("fetch_self_dm_history", limit=input_data.limit):
        log_tool_call(ctx, "fetch_self_dm_history", input_data.model_dump())

        db = next(get_db_session())
        try:
            me = (
                db.query(DBAgent)
                .filter(
                    DBAgent.user_id == ctx.deps.user_id,
                    DBAgent.name == ctx.deps.agent_name,
                )
                .first()
            )
            if not me:
                return "Error: agent not found."

            convo = ensure_self_dm(db, ctx.deps.user_id, me)

            members = (
                db.query(ConversationMember, DBAgent)
                .join(DBAgent, ConversationMember.agent_id == DBAgent.id)
                .filter(ConversationMember.conversation_id == convo.id)
                .all()
            )
            member_names = ", ".join(a.name for _, a in members)
            lines = [
                f"Conversation: {convo.name} (id: {convo.id})",
                f"Members: {member_names}",
                "---",
                "Messages:",
            ]

            q = select(ChatMessage).where(ChatMessage.conversation_id == convo.id)
            if input_data.before:
                q = q.where(ChatMessage.created_at < input_data.before)
            if input_data.after:
                q = q.where(ChatMessage.created_at > input_data.after)
            q = q.order_by(ChatMessage.created_at.asc()).limit(input_data.limit)
            msgs = db.execute(q).scalars().all()

            for m in msgs:
                lines.append(f"[{m.created_at.isoformat()}] {me.name}: {m.content}")

            return "\n".join(lines)
        finally:
            db.close()


class SendDmInput(BaseModel):
    target_agent: str
    content: str
    run_at: Optional[datetime] = None


async def send_dm_to(ctx: RunContext[AgentContext], input_data: SendDmInput) -> str:
    """Send a DM to another agent. Persist chat message then notify via send_message."""
    with logfire.span("send_dm_to", target=input_data.target_agent):
        log_tool_call(ctx, "send_dm_to", input_data.model_dump())

        db = next(get_db_session())
        try:
            me = (
                db.query(DBAgent)
                .filter(
                    DBAgent.user_id == ctx.deps.user_id,
                    DBAgent.name == ctx.deps.agent_name,
                )
                .first()
            )
            other = (
                db.query(DBAgent)
                .filter(
                    DBAgent.user_id == ctx.deps.user_id,
                    DBAgent.name == input_data.target_agent,
                )
                .first()
            )
            if not me or not other:
                return "Error: one or both agents not found."

            convo = ensure_dm(db, ctx.deps.user_id, me, other)

            msg = ChatMessage(
                conversation_id=convo.id,
                sender_agent_id=me.id,
                content=input_data.content,
                content_type="text",
            )
            db.add(msg)
            db.commit()

            # Notify target via private channel
            from ai.comms.send_message import send_message as _notify

            _notify(
                ctx.deps.user_id,
                other.name.lower(),
                input_data.content,
                me.name,
                input_data.run_at,
            )

            return f"Sent to {convo.name} (conversation_id={convo.id})."
        finally:
            db.close()


class SendSelfInput(BaseModel):
    content: str
    run_at: Optional[datetime] = None


async def send_self_dm(ctx: RunContext[AgentContext], input_data: SendSelfInput) -> str:
    """Send a self-DM. Persist chat message then notify via send_message."""
    with logfire.span("send_self_dm"):
        log_tool_call(ctx, "send_self_dm", input_data.model_dump())

        db = next(get_db_session())
        try:
            me = (
                db.query(DBAgent)
                .filter(
                    DBAgent.user_id == ctx.deps.user_id,
                    DBAgent.name == ctx.deps.agent_name,
                )
                .first()
            )
            if not me:
                return "Error: agent not found."

            convo = ensure_self_dm(db, ctx.deps.user_id, me)

            msg = ChatMessage(
                conversation_id=convo.id,
                sender_agent_id=me.id,
                content=input_data.content,
                content_type="text",
            )
            db.add(msg)
            db.commit()

            # Notify self via private channel
            from ai.comms.send_message import send_message as _notify

            _notify(
                ctx.deps.user_id,
                me.name.lower(),
                input_data.content,
                me.name,
                input_data.run_at,
            )

            return f"Sent to {convo.name} (conversation_id={convo.id})."
        finally:
            db.close()
