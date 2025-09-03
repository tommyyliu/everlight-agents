"""
AI tools organized by category with shared components.
"""

from .communication import send_message_tool, schedule_message
from .core import AgentContext, log_tool_call
from .notes import create_note, update_note, search_notes, get_note_titles
from .data import search_raw_entries, get_recent_raw_entries
from .utilities import get_current_time, get_hourly_weather
from .chat import (
    list_conversations,
    fetch_dm_history,
    fetch_self_dm_history,
    send_dm_to,
    send_self_dm,
)

# 5. Public API definition for the package
__all__ = [
    # Shared components
    "AgentContext",
    "log_tool_call",
    # Communication tools
    "send_message_tool",
    "schedule_message",
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
    # Chat tools
    "list_conversations",
    "fetch_dm_history",
    "fetch_self_dm_history",
    "send_dm_to",
    "send_self_dm",
]
