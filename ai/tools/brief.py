"""
Brief management tools for AI agents - reading and creating user briefs.
"""

import logfire
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel
from pydantic_ai import RunContext
from sqlalchemy import select

from ai.tools.core import AgentContext, log_tool_call
from db.models import Brief
from db.session import get_db_session


class ListBriefsInput(BaseModel):
    target_date: Optional[date] = None  # Defaults to today
    include_dismissed: bool = False  # Show dismissed briefs?


class CreateBriefInput(BaseModel):
    title: str
    content: str  # Markdown format
    display_at: datetime  # When the brief should be shown
    utc_date: Optional[date] = None  # Auto-derive from display_at if not provided


async def list_user_briefs(
        ctx: RunContext[AgentContext], input_data: ListBriefsInput
) -> str:
    """Lists existing briefs for the user to review before creating new ones."""
    with logfire.span("list_user_briefs", user_id=str(ctx.deps.user_id)):
        log_tool_call(ctx, "list_user_briefs", input_data.model_dump())

        db = next(get_db_session())

        # Use today if no target_date provided
        target_date = input_data.target_date or date.today()

        # Build query
        query = select(Brief).where(
            Brief.user_id == ctx.deps.user_id,
            Brief.utc_date == target_date
        )

        # Filter out dismissed briefs unless requested
        if not input_data.include_dismissed:
            query = query.where(Brief.dismissed_at.is_(None))

        # Order by display time
        query = query.order_by(Brief.display_at.asc())

        briefs = db.execute(query).scalars().all()

        if not briefs:
            logfire.info("No briefs found", date=str(target_date))
            return f"No briefs found for {target_date}."

        # Format response for agent
        response_lines = [f"Existing briefs for {target_date}:"]
        for brief in briefs:
            status = " (dismissed)" if brief.dismissed_at else ""
            display_time = brief.display_at.strftime("%H:%M")

            # Truncate content for overview
            content_preview = brief.content[:100] + "..." if len(brief.content) > 100 else brief.content

            response_lines.append(
                f"- {display_time}: '{brief.title}'{status}\n  Content: {content_preview}"
            )

        logfire.info("Listed briefs", count=len(briefs), date=str(target_date))
        return "\n".join(response_lines)


async def create_brief(
        ctx: RunContext[AgentContext], input_data: CreateBriefInput
) -> str:
    """Creates a new brief for the user."""
    with logfire.span("create_brief", user_id=str(ctx.deps.user_id)):
        log_tool_call(ctx, "create_brief", input_data.model_dump())

        db = next(get_db_session())

        # Auto-derive utc_date from display_at if not provided
        utc_date = input_data.utc_date or input_data.display_at.date()

        # Create new brief
        brief = Brief(
            user_id=ctx.deps.user_id,
            utc_date=utc_date,
            title=input_data.title,
            content=input_data.content,
            display_at=input_data.display_at
        )

        db.add(brief)
        db.commit()
        db.refresh(brief)

        logfire.info(
            "Brief created successfully",
            brief_id=str(brief.id),
            title=brief.title,
            date=str(utc_date),
            display_at=str(input_data.display_at)
        )

        return f"Brief '{input_data.title}' created successfully for {utc_date} at {input_data.display_at.strftime('%H:%M')}."
