"""
Note management tools for AI agents - creating, updating, and searching notes.
"""

from typing import Optional

import logfire
from pydantic_ai import RunContext
from pydantic import BaseModel
from sqlalchemy import select

from db.models import Agent as DBAgent, Note
from db.session import get_db_session
from db.embedding import embed_document, embed_query
from . import AgentContext, log_tool_call


class CreateNoteInput(BaseModel):
    title: str
    content: str


class UpdateNoteInput(BaseModel):
    note_id: str
    content: str
    title: Optional[str] = None


class NoteSearchInput(BaseModel):
    query: str
    limit: int = 5


async def create_note(
    ctx: RunContext[AgentContext], input_data: CreateNoteInput
) -> str:
    """Create and store a structured summary with semantic embedding."""
    with logfire.span(
        "create_note", title=input_data.title, user_id=str(ctx.deps.user_id)
    ):
        log_tool_call(ctx, "create_note", input_data.model_dump())

        db = next(get_db_session())

        agent_record = (
            db.query(DBAgent)
            .filter(
                DBAgent.user_id == ctx.deps.user_id, DBAgent.name == ctx.deps.agent_name
            )
            .first()
        )

        if not agent_record:
            error_msg = f"Error: Agent {ctx.deps.agent_name} not found for user"
            logfire.error("Agent not found", agent_name=ctx.deps.agent_name)
            return error_msg

        # Generate embedding for the summary content
        embedding = embed_document(input_data.content)

        # Create the note
        note = Note(
            user_id=ctx.deps.user_id,
            owner=agent_record.id,
            title=input_data.title,
            content=input_data.content,
            embedding=embedding,
        )

        db.add(note)
        db.commit()

        logfire.info(
            "Note created successfully", note_id=str(note.id), title=input_data.title
        )
        return f"Note created successfully with ID: {note.id}"


async def update_note(
    ctx: RunContext[AgentContext], input_data: UpdateNoteInput
) -> str:
    """Update an existing note's content and optionally title."""
    with logfire.span(
        "update_note", note_id=input_data.note_id, user_id=str(ctx.deps.user_id)
    ):
        log_tool_call(ctx, "update_note", input_data.model_dump())

        db = next(get_db_session())

        try:
            from uuid import UUID as _UUID

            note_uuid = _UUID(str(input_data.note_id))
        except Exception:
            error_msg = f"Error: note_id '{input_data.note_id}' is not a valid UUID"
            logfire.error("Invalid note UUID", note_id=input_data.note_id)
            return error_msg

        note = (
            db.query(Note)
            .filter(Note.user_id == ctx.deps.user_id, Note.id == note_uuid)
            .first()
        )

        if not note:
            error_msg = f"Error: Note {input_data.note_id} not found for user"
            logfire.error("Note not found", note_id=input_data.note_id)
            return error_msg

        note.content = input_data.content
        if input_data.title is not None:
            note.title = input_data.title

        # Regenerate embedding for updated content
        note.embedding = embed_document(input_data.content)

        db.commit()

        logfire.info("Note updated successfully", note_id=str(note.id))
        return f"Note {note.id} updated successfully."


async def search_notes(
    ctx: RunContext[AgentContext], input_data: NoteSearchInput
) -> str:
    """Search existing summaries using semantic similarity."""
    with logfire.span("search_notes", query=input_data.query, limit=input_data.limit):
        log_tool_call(ctx, "search_notes", input_data.model_dump())

        db = next(get_db_session())
        query_vector = embed_query(input_data.query)

        stmt = (
            select(Note)
            .where(Note.user_id == ctx.deps.user_id)
            .order_by(Note.embedding.l2_distance(query_vector))
            .limit(input_data.limit)
        )

        results = db.execute(stmt).scalars().all()

        if not results:
            logfire.info("No notes found for search")
            return "No summaries found."

        logfire.info("Notes found", count=len(results))
        formatted_results = []
        for note in results:
            formatted_results.append(
                f"ID: {note.id}\nContent: {note.content}\nCreated: {note.created_at}\n---"
            )

        return "\n".join(formatted_results)


async def get_note_titles(ctx: RunContext[AgentContext]) -> str:
    """Retrieve all notes for organizational overview."""
    with logfire.span("get_note_titles", user_id=str(ctx.deps.user_id)):
        log_tool_call(ctx, "get_note_titles", {})

        db = next(get_db_session())
        notes = (
            db.query(Note)
            .filter(Note.user_id == ctx.deps.user_id)
            .order_by(Note.created_at.desc())
            .all()
        )

        if not notes:
            logfire.info("No notes found")
            return "No notes found."

        logfire.info("Notes retrieved", count=len(notes))
        formatted_notes = []
        for note in notes:
            formatted_notes.append(
                f"ID: {note.id}\nCreated: {note.created_at}\nTitle: {note.title}\n---"
            )

        return "\n".join(formatted_notes)
