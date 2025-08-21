"""
Communication tools for AI agents - messaging and scheduling.
"""

from datetime import datetime
import os
from typing import Optional

import logfire
from pydantic_ai import RunContext
from pydantic import BaseModel

from ai.comms.send_message import send_message
from . import AgentContext, log_tool_call


class SendMessageInput(BaseModel):
    channel: str
    message: str


class ScheduleMessageInput(BaseModel):
    channel: str
    message: str
    run_at: datetime


async def send_message_tool(ctx: RunContext[AgentContext], input_data: SendMessageInput) -> str:
    """Send a message to a channel."""
    with logfire.span("send_message_tool", channel=input_data.channel):
        log_tool_call(ctx, "send_message_tool", input_data.model_dump())
        
        if os.getenv("TESTING"):
            return "Message recorded (test mode; not sent to external queue)."
        
        send_message(
            ctx.deps.user_id, 
            input_data.channel, 
            input_data.message, 
            ctx.deps.agent_name, 
            None
        )
        
        local_mode = os.getenv("LOCAL_DEVELOPMENT", "false").lower() == "true"
        if local_mode:
            return f"Message sent directly to {input_data.channel} (local development mode)."
        else:
            return f"Message queued for delivery to {input_data.channel} via Cloud Tasks."


async def schedule_message(ctx: RunContext[AgentContext], input_data: ScheduleMessageInput) -> str:
    """Schedule a message to be sent at a specific time."""
    with logfire.span("schedule_message", channel=input_data.channel, run_at=input_data.run_at.isoformat()):
        log_tool_call(ctx, "schedule_message", input_data.model_dump())
        
        if os.getenv("TESTING"):
            return f"Scheduled message recorded (test mode; delivery at {input_data.run_at})."
        
        result = send_message(
            ctx.deps.user_id,
            input_data.channel,
            input_data.message,
            ctx.deps.agent_name,
            input_data.run_at
        )
        
        local_mode = os.getenv("LOCAL_DEVELOPMENT", "false").lower() == "true"
        
        logfire.info("Message scheduled", channel=input_data.channel, run_at=input_data.run_at.isoformat())
        
        if local_mode:
            delay_seconds = max(0, (input_data.run_at - datetime.now()).total_seconds())
            return f"Message scheduled for {input_data.channel} at {input_data.run_at} (local mode: {delay_seconds:.1f}s delay)."
        else:
            return f"Message scheduled for {input_data.channel} at {input_data.run_at} via Cloud Tasks."