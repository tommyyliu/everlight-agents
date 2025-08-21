"""
Tests for note management tools using real PostgreSQL database.
"""

import pytest
from uuid import uuid4
import numpy as np

from ai.tools.notes import (
    create_note, update_note, search_notes, get_note_titles,
    CreateNoteInput, UpdateNoteInput, NoteSearchInput
)
from db.models import Note


@pytest.mark.asyncio
class TestCreateNote:
    """Tests for create_note tool"""

    async def test_create_note_success(
        self, 
        run_context, 
        mock_get_db_session_notes, 
        mock_logfire, 
        mock_log_tool_call,
        mock_embed_document,
        db_session,
        test_agent
    ):
        """Test successful note creation in database"""
        # Setup
        input_data = CreateNoteInput(title="Test Note Title", content="Test note content for creation")
        
        # Execute
        result = await create_note(run_context, input_data)
        
        # Assert response
        assert "Note created successfully with ID:" in result
        
        # Verify note was actually created in database
        created_notes = db_session.query(Note).filter(
            Note.user_id == test_agent.user_id,
            Note.title == input_data.title
        ).all()
        
        assert len(created_notes) == 1
        created_note = created_notes[0]
        assert created_note.content == input_data.content
        assert created_note.title == input_data.title
        assert created_note.owner == test_agent.id
        assert created_note.embedding is not None
        # Verify embedding was created (it's a HalfVector from pgvector)
        assert str(type(created_note.embedding)) == "<class 'pgvector.halfvec.HalfVector'>"

    async def test_create_note_agent_not_found(
        self, 
        run_context, 
        mock_get_db_session_notes, 
        mock_logfire, 
        mock_log_tool_call,
        test_user  # User exists but agent doesn't match
    ):
        """Test note creation when agent is not found"""
        # Setup - create context with non-existent agent name
        bad_context = run_context
        bad_context.deps.agent_name = "nonexistent_agent"
        
        input_data = CreateNoteInput(title="Test Note", content="Test content")
        
        # Execute
        result = await create_note(bad_context, input_data)
        
        # Assert
        expected_error = f"Error: Agent nonexistent_agent not found for user"
        assert result == expected_error
        mock_logfire.error.assert_called_once_with("Agent not found", agent_name="nonexistent_agent")

    async def test_create_note_with_embedding(
        self, 
        run_context, 
        mock_get_db_session_notes, 
        mock_logfire, 
        mock_log_tool_call,
        mock_embed_document,
        db_session,
        test_agent
    ):
        """Test that note creation includes proper embedding"""
        # Setup
        input_data = CreateNoteInput(title="Embedding Test", content="Content to embed")
        
        # Execute
        result = await create_note(run_context, input_data)
        
        # Assert
        assert "Note created successfully with ID:" in result
        
        # Verify embedding was called with correct content
        mock_embed_document.assert_called_once_with(input_data.content)
        
        # Verify embedding was stored in database
        created_note = db_session.query(Note).filter(
            Note.title == input_data.title
        ).first()
        assert created_note.embedding is not None


@pytest.mark.asyncio
class TestUpdateNote:
    """Tests for update_note tool"""

    async def test_update_note_content_and_title(
        self, 
        run_context, 
        mock_get_db_session_notes, 
        mock_logfire, 
        mock_log_tool_call,
        mock_embed_document,
        db_session,
        test_note
    ):
        """Test updating both content and title of existing note"""
        # Setup
        original_content = test_note.content
        original_title = test_note.title
        note_id = str(test_note.id)
        
        input_data = UpdateNoteInput(
            note_id=note_id, 
            content="Updated content from test", 
            title="Updated Title"
        )
        
        # Execute
        result = await update_note(run_context, input_data)
        
        # Assert
        assert result == f"Note {test_note.id} updated successfully."
        
        # Verify database was actually updated
        db_session.refresh(test_note)
        assert test_note.content == "Updated content from test"
        assert test_note.title == "Updated Title"
        assert test_note.content != original_content
        assert test_note.title != original_title
        
        # Verify embedding was regenerated
        mock_embed_document.assert_called_with("Updated content from test")

    async def test_update_note_content_only(
        self, 
        run_context, 
        mock_get_db_session_notes, 
        mock_logfire, 
        mock_log_tool_call,
        mock_embed_document,
        db_session,
        test_note
    ):
        """Test updating only content, leaving title unchanged"""
        # Setup
        original_title = test_note.title
        note_id = str(test_note.id)
        
        input_data = UpdateNoteInput(note_id=note_id, content="Only content updated")
        
        # Execute
        result = await update_note(run_context, input_data)
        
        # Assert
        assert result == f"Note {test_note.id} updated successfully."
        
        # Verify content changed but title didn't
        db_session.refresh(test_note)
        assert test_note.content == "Only content updated"
        assert test_note.title == original_title

    async def test_update_note_invalid_uuid(
        self, 
        run_context, 
        mock_get_db_session_notes, 
        mock_logfire, 
        mock_log_tool_call
    ):
        """Test update with invalid UUID format"""
        # Setup
        input_data = UpdateNoteInput(note_id="not-a-valid-uuid", content="Updated content")
        
        # Execute
        result = await update_note(run_context, input_data)
        
        # Assert
        assert result == "Error: note_id 'not-a-valid-uuid' is not a valid UUID"
        mock_logfire.error.assert_called_once_with("Invalid note UUID", note_id="not-a-valid-uuid")

    async def test_update_note_not_found(
        self, 
        run_context, 
        mock_get_db_session_notes, 
        mock_logfire, 
        mock_log_tool_call,
        db_session,
        test_user
    ):
        """Test update when note doesn't exist"""
        # Setup
        nonexistent_id = str(uuid4())
        input_data = UpdateNoteInput(note_id=nonexistent_id, content="Updated content")
        
        # Execute
        result = await update_note(run_context, input_data)
        
        # Assert
        assert result == f"Error: Note {nonexistent_id} not found for user"
        mock_logfire.error.assert_called_once_with("Note not found", note_id=nonexistent_id)

    async def test_update_note_wrong_user(
        self, 
        run_context, 
        mock_get_db_session_notes, 
        mock_logfire, 
        mock_log_tool_call,
        db_session,
        test_agent
    ):
        """Test that users can't update notes belonging to other users"""
        # Setup - create another user and their note
        from db.models import User
        other_user = User(
            id=uuid4(),
            firebase_user_id="other_firebase_id_notes",
            email="other_notes@example.com"
        )
        db_session.add(other_user)
        db_session.flush()
        
        other_note = Note(
            user_id=other_user.id,
            owner=test_agent.id,
            title="Other user's note",
            content="Content belonging to other user",
            embedding=np.random.rand(3072).astype(np.float16)
        )
        db_session.add(other_note)
        db_session.commit()
        
        input_data = UpdateNoteInput(note_id=str(other_note.id), content="Trying to update")
        
        # Execute
        result = await update_note(run_context, input_data)
        
        # Assert - should not find note because user_id doesn't match
        assert f"Error: Note {other_note.id} not found for user" in result


@pytest.mark.asyncio
class TestSearchNotes:
    """Tests for search_notes tool"""

    async def test_search_notes_finds_relevant_notes(
        self, 
        run_context, 
        mock_get_db_session_notes, 
        mock_logfire, 
        mock_log_tool_call,
        mock_embed_query,
        db_session,
        test_note
    ):
        """Test note search finds relevant notes"""
        # Setup
        input_data = NoteSearchInput(query="test search query", limit=5)
        
        # Execute
        result = await search_notes(run_context, input_data)
        
        # Assert
        assert str(test_note.id) in result
        assert test_note.content in result
        assert str(test_note.created_at) in result
        
        # Verify embedding query was called
        mock_embed_query.assert_called_once_with(input_data.query)
        mock_logfire.info.assert_called_with("Notes found", count=1)

    async def test_search_notes_limit_works(
        self, 
        run_context, 
        mock_get_db_session_notes, 
        mock_logfire, 
        mock_log_tool_call,
        mock_embed_query,
        db_session,
        test_user,
        test_agent
    ):
        """Test that search limit is properly applied"""
        # Setup - create multiple notes
        notes = []
        for i in range(10):
            note = Note(
                user_id=test_user.id,
                owner=test_agent.id,
                title=f"Note {i}",
                content=f"Content for note {i}",
                embedding=np.random.rand(3072).astype(np.float16)
            )
            notes.append(note)
            db_session.add(note)
        db_session.commit()
        
        input_data = NoteSearchInput(query="note", limit=3)
        
        # Execute
        result = await search_notes(run_context, input_data)
        
        # Assert - should only return 3 notes despite having 10
        note_sections = result.split("---")
        # Filter out empty sections
        actual_notes = [section for section in note_sections if section.strip()]
        assert len(actual_notes) <= 3

    async def test_search_notes_no_results(
        self, 
        run_context, 
        mock_get_db_session_notes, 
        mock_logfire, 
        mock_log_tool_call,
        mock_embed_query,
        db_session,
        test_user  # User exists but no notes
    ):
        """Test search when no notes exist"""
        # Setup
        input_data = NoteSearchInput(query="nonexistent content", limit=5)
        
        # Execute
        result = await search_notes(run_context, input_data)
        
        # Assert
        assert result == "No summaries found."
        mock_logfire.info.assert_called_with("No notes found for search")


@pytest.mark.asyncio
class TestGetNoteTitles:
    """Tests for get_note_titles tool"""

    async def test_get_note_titles_returns_all_notes(
        self, 
        run_context, 
        mock_get_db_session_notes, 
        mock_logfire, 
        mock_log_tool_call,
        db_session,
        test_note
    ):
        """Test getting all note titles for user"""
        # Execute
        result = await get_note_titles(run_context)
        
        # Assert
        assert str(test_note.id) in result
        assert test_note.title in result
        assert str(test_note.created_at) in result
        mock_logfire.info.assert_called_with("Notes retrieved", count=1)

    async def test_get_note_titles_ordered_by_creation(
        self, 
        run_context, 
        mock_get_db_session_notes, 
        mock_logfire, 
        mock_log_tool_call,
        db_session,
        test_user,
        test_agent
    ):
        """Test that notes are returned in reverse chronological order"""
        # Setup - create multiple notes with explicit timestamps
        from datetime import datetime, timedelta
        
        older_time = datetime.now() - timedelta(hours=1)
        older_note = Note(
            user_id=test_user.id,
            owner=test_agent.id,
            title="Older Note",
            content="Older content",
            embedding=np.random.rand(3072).astype(np.float16),
            created_at=older_time
        )
        db_session.add(older_note)
        db_session.commit()
        
        newer_time = datetime.now()
        newer_note = Note(
            user_id=test_user.id,
            owner=test_agent.id,
            title="Newer Note", 
            content="Newer content",
            embedding=np.random.rand(3072).astype(np.float16),
            created_at=newer_time
        )
        db_session.add(newer_note)
        db_session.commit()
        
        # Execute
        result = await get_note_titles(run_context)
        
        # Assert - newer note should appear first
        newer_pos = result.find("Newer Note")
        older_pos = result.find("Older Note")
        assert newer_pos < older_pos  # Newer should come first in string

    async def test_get_note_titles_no_notes(
        self, 
        run_context, 
        mock_get_db_session_notes, 
        mock_logfire, 
        mock_log_tool_call,
        db_session,
        test_user  # User exists but no notes
    ):
        """Test getting note titles when user has no notes"""
        # Execute
        result = await get_note_titles(run_context)
        
        # Assert
        assert result == "No notes found."
        mock_logfire.info.assert_called_with("No notes found")


class TestNoteInputModels:
    """Tests for note input model validation"""

    def test_create_note_input_validation(self):
        """Test CreateNoteInput validation"""
        valid_input = CreateNoteInput(title="Valid Title", content="Valid content")
        assert valid_input.title == "Valid Title"
        assert valid_input.content == "Valid content"

    def test_update_note_input_with_title(self):
        """Test UpdateNoteInput with title update"""
        input_with_title = UpdateNoteInput(
            note_id=str(uuid4()), 
            content="Updated content", 
            title="Updated Title"
        )
        assert input_with_title.title == "Updated Title"
        assert input_with_title.content == "Updated content"

    def test_update_note_input_without_title(self):
        """Test UpdateNoteInput without title (content only)"""
        input_without_title = UpdateNoteInput(
            note_id=str(uuid4()), 
            content="Updated content only"
        )
        assert input_without_title.title is None
        assert input_without_title.content == "Updated content only"

    def test_note_search_input_defaults(self):
        """Test NoteSearchInput default values"""
        default_input = NoteSearchInput(query="test query")
        assert default_input.query == "test query"
        assert default_input.limit == 5

    def test_note_search_input_custom_limit(self):
        """Test NoteSearchInput with custom limit"""
        custom_input = NoteSearchInput(query="test query", limit=15)
        assert custom_input.limit == 15