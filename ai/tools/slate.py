"""
Slate management tools for AI agents - reading and updating the user's Living Slate.
"""

import logfire
from pydantic_ai import RunContext
from pydantic import BaseModel
from sqlalchemy import select

from db.models import Slate
from db.session import get_db_session
from . import AgentContext, log_tool_call


class UpdateSlateInput(BaseModel):
    content: str


async def read_slate(ctx: RunContext[AgentContext]) -> str:
    """Reads the current content of the user's Living Slate."""
    with logfire.span("read_slate", user_id=str(ctx.deps.user_id)):
        log_tool_call(ctx, "read_slate", {})
        
        db = next(get_db_session())
        stmt = select(Slate).where(Slate.user_id == ctx.deps.user_id).order_by(Slate.updated_at.desc())
        slate = db.execute(stmt).scalars().first()
        
        if slate:
            logfire.info("Slate content retrieved", content_length=len(slate.content))
            return slate.content
        else:
            logfire.info("Slate is empty")
            return "The slate is currently empty."


async def update_slate(ctx: RunContext[AgentContext], input_data: UpdateSlateInput) -> str:
    """Updates the user's Living Slate with new, structured content."""
    with logfire.span("update_slate", user_id=str(ctx.deps.user_id)):
        log_tool_call(ctx, "update_slate", input_data.model_dump())
        
        db = next(get_db_session())
        stmt = select(Slate).where(Slate.user_id == ctx.deps.user_id)
        slate = db.execute(stmt).scalar_one_or_none()
        
        if slate:
            slate.content = input_data.content
            logfire.info("Slate updated", slate_id=str(slate.id))
        else:
            slate = Slate(user_id=ctx.deps.user_id, content=input_data.content)
            db.add(slate)
            logfire.info("New slate created")
        
        db.commit()
        return "Slate updated successfully."