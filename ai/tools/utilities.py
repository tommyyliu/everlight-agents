"""
Utility tools for AI agents - time, weather, and other general utilities.
"""

from datetime import datetime

import logfire
from pydantic_ai import RunContext

from . import AgentContext, log_tool_call


async def get_current_time(ctx: RunContext[AgentContext]) -> str:
    """Get the current time."""
    try:
        with logfire.span("get_current_time"):
            try:
                log_tool_call(ctx, "get_current_time", {})
            except Exception:
                pass  # Continue even if logging fails
            current_time = datetime.now().isoformat()
            logfire.info("Current time retrieved", time=current_time)
            return current_time
    except Exception:
        # Fallback if logfire fails - still return time
        return datetime.now().isoformat()


async def get_hourly_weather(ctx: RunContext[AgentContext]) -> str:
    """Get weather information."""
    try:
        with logfire.span("get_hourly_weather"):
            try:
                log_tool_call(ctx, "get_hourly_weather", {})
            except Exception:
                pass  # Continue even if logging fails
            return "Sunny and 72 degrees. This is just example weather data by the way. Actual weather API integration will come in the future."
    except Exception:
        # Fallback if logfire fails - still return weather
        return "Sunny and 72 degrees. This is just example weather data by the way. Actual weather API integration will come in the future."
