"""
Core components and context shared across all agent tools.
"""

import json
import os
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic_ai import RunContext


class AgentContext(BaseModel):
    """Context passed to all agent tools."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    user_id: UUID
    agent_name: str
    db_session: Any = None


def log_tool_call(ctx: RunContext[AgentContext], name: str, args: dict):
    """Log tool calls for evaluation purposes."""
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
        # For a simple logger that shouldn't crash the app,
        # catching a broad exception is acceptable.
        pass
