"""
AI tools organized by category with shared components.
"""

# 1. Standard library imports
import json
import os
from datetime import datetime
from typing import Any
from uuid import UUID

# 2. Third-party imports
from pydantic import BaseModel, ConfigDict
from pydantic_ai import RunContext

# 3. Local application imports (your tools)
from .communication import schedule_message, send_message_tool
from .data import get_recent_raw_entries, search_raw_entries
from .notes import create_note, get_note_titles, search_notes, update_note
from .slate import read_slate, update_slate
from .utilities import get_current_time, get_hourly_weather


# 4. Module-level definitions
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
        # It's generally better to catch specific exceptions,
        # but for a simple logger that shouldn't crash the app, this is okay.
        pass


# 5. Public API definition for the package
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
