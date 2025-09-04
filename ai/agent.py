"""
AI agent factory and management with database-driven tool configuration.
Uses pydantic-ai and logfire for observability.
"""

from typing import Dict, List, Callable, Optional
import os
import logfire
from pydantic_ai import Agent
from uuid import UUID

from ai.tools import (
    AgentContext,
    send_message_tool,
    get_current_time,
    get_hourly_weather,
    list_user_briefs,
    create_brief,
    create_note,
    update_note,
    search_notes,
    get_note_titles,
    search_raw_entries,
    get_recent_raw_entries,
    schedule_message,
)
from db.models import Agent as DBAgent
from db.session import get_db_session


class ToolRegistry:
    """Registry for managing available tools"""

    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._register_all_tools()

    def _register_all_tools(self):
        """Register all available tools"""
        self._tools.update(
            {
                "send_message_tool": send_message_tool,
                "get_current_time": get_current_time,
                "get_hourly_weather": get_hourly_weather,
                "list_user_briefs": list_user_briefs,
                "create_brief": create_brief,
                "create_note": create_note,
                "update_note": update_note,
                "search_notes": search_notes,
                "get_note_titles": get_note_titles,
                "search_raw_entries": search_raw_entries,
                "get_recent_raw_entries": get_recent_raw_entries,
                "schedule_message": schedule_message,
            }
        )

    def get_tools_by_names(self, tool_names: List[str]) -> Dict[str, Callable]:
        """Get tools by their names"""
        return {name: func for name, func in self._tools.items() if name in tool_names}

    def get_all_tools(self) -> Dict[str, Callable]:
        """Get all registered tools"""
        return self._tools.copy()

    def is_tool_available(self, tool_name: str) -> bool:
        """Check if a tool is registered"""
        return tool_name in self._tools


class AgentFactory:
    """Factory for creating agents with database-defined tools"""

    def __init__(self):
        self.tool_registry = ToolRegistry()

    def create_agent_from_db(
        self, user_id: UUID, agent_name: str, model: Optional[str] = None
    ) -> Agent[AgentContext, str]:
        """Create an agent using database configuration"""

        db = next(get_db_session())

        # Get agent configuration from database
        agent_config = (
            db.query(DBAgent)
            .filter(DBAgent.user_id == user_id, DBAgent.name == agent_name)
            .first()
        )

        if not agent_config:
            raise ValueError(f"Agent '{agent_name}' not found for user {user_id}")

        selected_model = model or "gemini-2.0-flash-exp"

        # Skip logfire configuration in testing/eval environments
        if not os.getenv("TESTING") and not os.getenv("LOGFIRE_IGNORE_NO_CONFIG"):
            logfire.configure()

        agent = Agent(
            model=selected_model,
            deps_type=AgentContext,
            system_prompt=agent_config.prompt,
        )

        # Add tools based on database configuration
        available_tools = self.tool_registry.get_tools_by_names(agent_config.tools)

        for tool_name, tool_func in available_tools.items():
            agent.tool(tool_func)

        # Log any missing tools
        missing_tools = set(agent_config.tools) - set(available_tools.keys())
        if missing_tools:
            logfire.warning(
                "Some tools not found in registry",
                missing_tools=list(missing_tools),
                agent_name=agent_name,
            )

        logfire.info(
            "Agent created from database",
            agent_name=agent_name,
            available_tools=list(available_tools.keys()),
            prompt_length=len(agent_config.prompt),
        )

        return agent


# Global factory instance
agent_factory = AgentFactory()


def create_agent_from_db(
    user_id: UUID, agent_name: str, model: Optional[str] = None
) -> Agent[AgentContext, str]:
    """Create an agent using database configuration"""
    return agent_factory.create_agent_from_db(user_id, agent_name, model)


async def run_agent_from_db(
    user_id: UUID, agent_name: str, prompt: str, model: Optional[str] = None
) -> str:
    """Run an agent using database configuration"""
    agent = create_agent_from_db(user_id, agent_name, model)

    context = AgentContext(user_id=user_id, agent_name=agent_name)

    with logfire.span("db_agent_run", user_id=str(user_id), agent_name=agent_name):
        result = await agent.run(prompt, deps=context)
        logfire.info(
            "Database agent run completed",
            response_length=len(result.data),
            agent_name=agent_name,
        )
        return result.data


def get_available_tools() -> List[str]:
    """Get list of all available tool names"""
    return list(agent_factory.tool_registry.get_all_tools().keys())


def get_agent_config(user_id: UUID, agent_name: str) -> Optional[DBAgent]:
    """Get agent configuration from database"""
    db = next(get_db_session())
    return (
        db.query(DBAgent)
        .filter(DBAgent.user_id == user_id, DBAgent.name == agent_name)
        .first()
    )


def get_user_ai_base(
    user_id: UUID, agent_name: str, model: Optional[str] = None, db_session=None
):
    """Create an agent that matches genkit's API interface"""

    if db_session:
        # Create agent with provided db session for evals
        tool_registry = ToolRegistry()

        # Get agent configuration from database using provided session
        agent_config = (
            db_session.query(DBAgent)
            .filter(DBAgent.user_id == user_id, DBAgent.name == agent_name)
            .first()
        )

        if not agent_config:
            raise ValueError(f"Agent '{agent_name}' not found for user {user_id}")

        selected_model = model or "gemini-2.0-flash-exp"

        # Skip logfire configuration in testing/eval environments
        if not os.getenv("TESTING") and not os.getenv("LOGFIRE_IGNORE_NO_CONFIG"):
            logfire.configure()

        agent = Agent(
            model=selected_model,
            deps_type=AgentContext,
            system_prompt=agent_config.prompt,
        )

        # Add tools based on database configuration
        available_tools = tool_registry.get_tools_by_names(agent_config.tools)

        for tool_name, tool_func in available_tools.items():
            agent.tool(tool_func)

        # Add generate method directly to agent to match genkit API
        async def generate(prompt: str, tools: List[str] = None):
            """Generate response using the agent"""
            context = AgentContext(
                user_id=user_id, agent_name=agent_name, db_session=db_session
            )

            result = await agent.run(prompt, deps=context)
            return str(result)

        agent.generate = generate
        return agent
    else:
        # Use standard agent creation
        agent = create_agent_from_db(user_id, agent_name, model)

        # Add generate method to match genkit API
        async def generate(prompt: str, tools: List[str] = None):
            """Generate response using the agent"""
            context = AgentContext(user_id=user_id, agent_name=agent_name)

            with logfire.span(
                "agent_generate", user_id=str(user_id), agent_name=agent_name
            ):
                result = await agent.run(prompt, deps=context)
                logfire.info(
                    "Agent generation completed", response_length=len(str(result))
                )
                return str(result)

        agent.generate = generate
        return agent
