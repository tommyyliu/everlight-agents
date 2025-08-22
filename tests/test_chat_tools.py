import pytest
from uuid import uuid4
from unittest.mock import Mock, patch

from ai.tools.chat import (
    list_conversations,
    fetch_dm_history,
    fetch_self_dm_history,
    send_dm_to,
    send_self_dm,
    ListConversationsInput,
    FetchDmHistoryInput,
    FetchSelfHistoryInput,
    SendDmInput,
    SendSelfInput,
)
from ai.tools.core import AgentContext
from db.models import Agent, User


@pytest.mark.asyncio
async def test_list_conversations_and_fetch_history(
    db_session, mock_logfire, mock_log_tool_call
):
    # Create user and two agents
    user = User(id=uuid4(), firebase_user_id="fb", email="user@example.com")
    a = Agent(user_id=user.id, name="Eforos", prompt="", tools=[])
    b = Agent(user_id=user.id, name="Safine", prompt="", tools=[])
    db_session.add(user)
    db_session.commit()
    db_session.add_all([a, b])
    db_session.commit()

    # Seed using send tools (which call ensure_* internally)
    ctx_a = Mock()
    ctx_a.deps = AgentContext(user_id=user.id, agent_name="Eforos")

    # Capture user_id before patching session to avoid detachment issues
    uid = user.id
    with patch("ai.tools.chat.get_db_session") as gds, patch(
        "ai.tools.chat.notify_send_message"
    ) as notify_mock, patch("ai.comms.send_message.send_message") as comms_mock:
        gds.return_value.__next__ = Mock(return_value=db_session)
        await send_dm_to(
            ctx_a, SendDmInput(target_agent="Safine", content="Hello Safine")
        )
        await send_self_dm(ctx_a, SendSelfInput(content="My note"))
        # One of the patched call sites should be invoked
        assert (notify_mock.call_count + comms_mock.call_count) == 2

    # List conversations (should include DM and self)
    ctx_b = Mock()
    ctx_b.deps = AgentContext(user_id=uid, agent_name="Safine")
    with patch("ai.tools.chat.get_db_session") as gds:
        gds.return_value.__next__ = Mock(return_value=db_session)
        out = await list_conversations(ctx_b, ListConversationsInput())
    assert "Conversation:" in out and "Members:" in out and "Last message:" in out
    assert "Direct Message between Eforos and Safine" in out
    assert "Direct Message with Eforos (self)" in out

    # Fetch DM history from Safine side
    with patch("ai.tools.chat.get_db_session") as gds:
        gds.return_value.__next__ = Mock(return_value=db_session)
        hist = await fetch_dm_history(
            ctx_b, FetchDmHistoryInput(with_agent="Eforos", limit=10)
        )
    assert "Conversation:" in hist and "Messages:" in hist
    assert "Eforos: Hello Safine" in hist

    # Fetch self-DM history for Eforos
    with patch("ai.tools.chat.get_db_session") as gds:
        gds.return_value.__next__ = Mock(return_value=db_session)
        hist_self = await fetch_self_dm_history(ctx_a, FetchSelfHistoryInput(limit=10))
    assert "Conversation: Direct Message with Eforos (self)" in hist_self
    assert "Eforos: My note" in hist_self


@pytest.mark.asyncio
async def test_send_tools_schedule_respected(
    db_session, mock_logfire, mock_log_tool_call
):
    # Create user and agents
    user = User(id=uuid4(), firebase_user_id="fb2", email="user2@example.com")
    a = Agent(user_id=user.id, name="Eforos", prompt="", tools=[])
    b = Agent(user_id=user.id, name="Safine", prompt="", tools=[])
    db_session.add(user)
    db_session.commit()
    db_session.add_all([a, b])
    db_session.commit()

    ctx = Mock()
    ctx.deps = AgentContext(user_id=user.id, agent_name="Eforos")

    with patch("ai.tools.chat.get_db_session") as gds, patch(
        "ai.tools.chat.notify_send_message"
    ) as notify_mock, patch("ai.comms.send_message.send_message") as comms_mock:
        gds.return_value.__next__ = Mock(return_value=db_session)
        from datetime import datetime, timedelta

        run_at = datetime.now() + timedelta(minutes=5)
        await send_dm_to(
            ctx, SendDmInput(target_agent="Safine", content="later", run_at=run_at)
        )
        await send_self_dm(ctx, SendSelfInput(content="self later", run_at=run_at))

        # Ensure run_at propagated in one of the patched calls
        calls = notify_mock.call_args_list + comms_mock.call_args_list
        assert len(calls) == 2
        for c in calls:
            args = c[0]
            assert args[4] == run_at
