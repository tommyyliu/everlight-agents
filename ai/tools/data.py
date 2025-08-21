"""
Data search tools for AI agents - searching and retrieving raw entries.
"""

from typing import Optional

import logfire
from pydantic_ai import RunContext
from pydantic import BaseModel
from sqlalchemy import select

from db.models import RawEntry
from db.session import get_db_session
from db.embedding import embed_query
from . import AgentContext, log_tool_call


class RawEntrySearchInput(BaseModel):
    query: str
    limit: int = 10
    source_filter: Optional[str] = None


async def search_raw_entries(ctx: RunContext[AgentContext], input_data: RawEntrySearchInput) -> str:
    """Search past raw entries using semantic similarity."""
    with logfire.span("search_raw_entries", query=input_data.query, limit=input_data.limit):
        log_tool_call(ctx, "search_raw_entries", input_data.model_dump())
        
        db = next(get_db_session())
        query_vector = embed_query(input_data.query)

        stmt = select(RawEntry).where(RawEntry.user_id == ctx.deps.user_id)
        
        if input_data.source_filter:
            stmt = stmt.where(RawEntry.source == input_data.source_filter)
        
        stmt = stmt.order_by(
            RawEntry.embedding.l2_distance(query_vector)
        ).limit(input_data.limit)
        
        results = db.execute(stmt).scalars().all()
        
        if not results:
            logfire.info("No raw entries found for search")
            return "No relevant raw entries found."
        
        logfire.info("Raw entries found", count=len(results))
        formatted_results = []
        for entry in results:
            content_preview = str(entry.content)
            if len(content_preview) > 300:
                content_preview = content_preview[:300] + "..."
            
            formatted_results.append(
                f"ID: {entry.id}\n"
                f"Source: {entry.source}\n"
                f"Created: {entry.created_at}\n"
                f"Content: {content_preview}\n"
                f"---"
            )
        
        return "\n".join(formatted_results)


async def get_recent_raw_entries(ctx: RunContext[AgentContext], limit: int = 20) -> str:
    """Get recent raw entries for context."""
    with logfire.span("get_recent_raw_entries", limit=limit):
        log_tool_call(ctx, "get_recent_raw_entries", {"limit": limit})
        
        db = next(get_db_session())
        stmt = select(RawEntry).where(RawEntry.user_id == ctx.deps.user_id).order_by(
            RawEntry.created_at.desc()
        ).limit(limit)
        
        results = db.execute(stmt).scalars().all()
        
        if not results:
            logfire.info("No recent raw entries found")
            return "No recent raw entries found."
        
        logfire.info("Recent raw entries retrieved", count=len(results))
        formatted_results = []
        for entry in results:
            content_preview = str(entry.content)
            if len(content_preview) > 200:
                content_preview = content_preview[:200] + "..."
            
            formatted_results.append(
                f"Source: {entry.source} | Created: {entry.created_at}\n"
                f"Content: {content_preview}\n"
                f"---"
            )
        
        return "\n".join(formatted_results)