from datetime import datetime
from functools import cache
from uuid import UUID

from genkit.ai import Genkit
from genkit.plugins.google_genai import GoogleAI
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select

from ai.comms.channels import send_message
from db.models import Agent, Slate, Note, RawEntry
from db.session import get_db_session
from db.embedding import embed_document, embed_query


class SendMessageInput(BaseModel):
    channel: str
    message: str

class WriteNotesInput(BaseModel):
    notes: str

class UpdateSlateInput(BaseModel):
    """Input model for the update_slate tool."""
    content: str

class CreateNoteInput(BaseModel):
    """Input model for creating a summary."""
    title: str
    content: str

class NoteSearchInput(BaseModel):
    """Input model for searching summaries."""
    query: str
    limit: int = 5

class RawEntrySearchInput(BaseModel):
    """Input model for searching raw entries."""
    query: str
    limit: int = 10
    source_filter: Optional[str] = None

class ScheduleMessageInput(BaseModel):
    channel: str
    message: str
    run_at: datetime

@cache
def get_user_ai_base(user_id: UUID, agent_name: str):
    ai = Genkit(
        plugins=[GoogleAI()],
        model='googleai/gemini-2.5-flash',
    )
    @ai.tool()
    def send_message_tool(send_message_input: SendMessageInput) -> str:
        """
        Send a message to a channel.
        """
        send_message(user_id, send_message_input.channel, send_message_input.message, agent_name, None)
        return "Message sent."


    @ai.tool()
    def read_slate() -> str:
        """Reads the current content of the user's Living Slate."""
        db = next(get_db_session())
        # Assuming one slate per user, get the most recently updated one.
        stmt = select(Slate).where(Slate.user_id == user_id).order_by(Slate.updated_at.desc())
        slate = db.execute(stmt).scalar_one_or_none()
        if slate:
            return slate.content
        else:
            return "The slate is currently empty."

    @ai.tool()
    def update_slate(update_slate_input: UpdateSlateInput) -> str:
        """Updates the user's Living Slate with new, structured content."""
        db = next(get_db_session())
        # Find the user's slate or create a new one.
        stmt = select(Slate).where(Slate.user_id == user_id)
        slate = db.execute(stmt).scalar_one_or_none()
        if slate:
            slate.content = update_slate_input.content
        else:
            slate = Slate(user_id=user_id, content=update_slate_input.content)
            db.add(slate)
        db.commit()
        return "Slate updated successfully."

    @ai.tool()
    def get_current_time() -> str:
        # IMPROVEMENT: Return a standardized string format for the AI.
        # TODO: Think about getting latest user timezone.
        return datetime.now().isoformat()

    @ai.tool()
    def get_hourly_weather() -> str:
        # TODO: Get user location and get weather for that location.
        # Can use weatherkit once I get on that Apple developer program.
        return "Sunny and 72 degrees. This is just example weather data by the way. Actual weather API integration will come in the future."

    @ai.tool()
    def create_note(create_note_input: CreateNoteInput) -> str:
        """
        Create and store a structured summary with semantic embedding.
        Use this to store organized, processed information that can be retrieved later.
        """
        db = next(get_db_session())
        
        # Get the agent ID for this agent
        agent = db.query(Agent).filter(Agent.user_id == user_id, Agent.name == agent_name).first()
        if not agent:
            return f"Error: Agent {agent_name} not found for user"
        
        # Generate embedding for the summary content
        embedding = embed_document(create_note_input.content)

        # Create the note
        note = Note(
            user_id=user_id,
            owner=agent.id,  # Use the actual agent ID as owner
            title=create_note_input.title,
            content=create_note_input.content,
            embedding=embedding
        )
        
        db.add(note)
        db.commit()
        return f"Note created successfully with ID: {note.id}"

    @ai.tool()
    def search_notes(note_search_input: NoteSearchInput) -> str:
        """
        Search existing summaries using semantic similarity.
        Returns the most relevant summaries based on the query.
        """
        db = next(get_db_session())
        
        # Generate embedding for the search query
        query_vector = embed_query(note_search_input.query)

        stmt = select(Note).where(Note.user_id == user_id).order_by(
            Note.embedding.l2_distance(query_vector)
        ).limit(note_search_input.limit)
        results = db.execute(stmt).scalars().all()
        
        if not results:
            return "No summaries found."
        
        formatted_results = []
        for note in results:
            formatted_results.append(f"ID: {note.id}\nContent: {note.content}\nCreated: {note.created_at}\n---")
        
        return "\n".join(formatted_results)

    @ai.tool()
    def get_note_titles() -> str:
        """
        Retrieve all notes for organizational overview.
        Use this to understand the current knowledge structure.
        """
        db = next(get_db_session())
        notes = db.query(Note).filter(Note.user_id == user_id).order_by(Note.created_at.desc()).all()
        
        if not notes:
            return "No notes found."
        
        formatted_notes = []
        for note in notes:
            formatted_notes.append(f"ID: {note.id}\nCreated: {note.created_at}\nTitle: {note.title}\n---")
        
        return "\n".join(formatted_notes)

    @ai.tool()
    def search_raw_entries(raw_entry_search_input: RawEntrySearchInput) -> str:
        """
        Search past raw entries using semantic similarity.
        Use this to find relevant historical data that might provide context for current processing.
        """
        db = next(get_db_session())
        
        # Generate embedding for the search query
        query_vector = embed_query(raw_entry_search_input.query)

        # Build query with optional source filter
        stmt = select(RawEntry).where(RawEntry.user_id == user_id)
        
        if raw_entry_search_input.source_filter:
            stmt = stmt.where(RawEntry.source == raw_entry_search_input.source_filter)
        
        stmt = stmt.order_by(
            RawEntry.embedding.l2_distance(query_vector)
        ).limit(raw_entry_search_input.limit)
        
        results = db.execute(stmt).scalars().all()
        
        if not results:
            return "No relevant raw entries found."
        
        formatted_results = []
        for entry in results:
            # Extract meaningful content for display
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

    @ai.tool()
    def get_recent_raw_entries(limit: int = 20) -> str:
        """
        Get recent raw entries for context.
        Use this to understand recent user activity and data patterns.
        """
        db = next(get_db_session())
        
        stmt = select(RawEntry).where(RawEntry.user_id == user_id).order_by(
            RawEntry.created_at.desc()
        ).limit(limit)
        
        results = db.execute(stmt).scalars().all()
        
        if not results:
            return "No recent raw entries found."
        
        formatted_results = []
        for entry in results:
            # Extract meaningful content for display
            content_preview = str(entry.content)
            if len(content_preview) > 200:
                content_preview = content_preview[:200] + "..."
            
            formatted_results.append(
                f"Source: {entry.source} | Created: {entry.created_at}\n"
                f"Content: {content_preview}\n"
                f"---"
            )
        
        return "\n".join(formatted_results)

    # Scheduling tools
    @ai.tool()
    async def schedule_message(schedule_message_input: ScheduleMessageInput) -> str:
        """
        Schedule a message to be sent at a specific time using Google Cloud Tasks.
        Use this to schedule future communications with other agents or channels.
        """
        return send_message(
            user_id,
            schedule_message_input.channel,
            schedule_message_input.message,
            agent_name,
            schedule_message_input.run_at
        )

    return ai