"""
AI tools organized by category with shared components.
"""

from datetime import datetime
from uuid import UUID
import os
import json
from typing import Any

from pydantic_ai import RunContext
from pydantic import BaseModel, ConfigDict


class AgentContext(BaseModel):
    """Context passed to all agent tools"""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    user_id: UUID
    agent_name: str
    db_session: Any = None


def log_tool_call(ctx: RunContext[AgentContext], name: str, args: dict):
    """Log tool calls for evaluation purposes"""
    path = os.getenv("EVAL_TOOL_LOG_PATH")
    if not path:
        return
    
    try:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "user_id": str(ctx.deps.user_id),
            "agent_name": ctx.deps.agent_name,
            "tool": name,
            "args": args,
            "step": os.getenv("EVAL_STEP_INDEX"),
        }
        with open(path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


# Import all tools from category modules
from .communication import send_message_tool, schedule_message
from .slate import read_slate, update_slate
from .notes import create_note, update_note, search_notes, get_note_titles
from .data import search_raw_entries, get_recent_raw_entries
from .utilities import get_current_time, get_hourly_weather

# Export all tools for easy importing
__all__ = [
    # Shared components
    "AgentContext",
    "log_tool_call",
    
    # Communication tools
    "send_message_tool",
    "schedule_message",
    
    # Slate tools
    "read_slate",
    "update_slate",
    
    # Note tools
    "create_note",
    "update_note", 
    "search_notes",
    "get_note_titles",
    
    # Data tools
    "search_raw_entries",
    "get_recent_raw_entries",
    
    # Utility tools
    "get_current_time",
    "get_hourly_weather",
]