"""
Tests for slate management tools using real PostgreSQL database.
"""

import pytest
from sqlalchemy import select

from ai.tools.slate import read_slate, update_slate, UpdateSlateInput
from db.models import Slate


@pytest.mark.asyncio
class TestReadSlate:
    """Tests for read_slate tool"""

    async def test_read_slate_with_existing_content(
        self, 
        run_context, 
        mock_get_db_session, 
        mock_logfire, 
        mock_log_tool_call,
        test_slate
    ):
        """Test reading slate when content exists in database"""
        # Execute
        result = await read_slate(run_context)
        
        # Assert
        assert result == test_slate.content
        mock_logfire.span.assert_called_once_with("read_slate", user_id=str(run_context.deps.user_id))
        mock_log_tool_call.assert_called_once_with(run_context, "read_slate", {})
        mock_logfire.info.assert_called_once_with("Slate content retrieved", content_length=len(test_slate.content))

    async def test_read_slate_no_slate_exists(
        self, 
        run_context, 
        mock_get_db_session, 
        mock_logfire, 
        mock_log_tool_call,
        test_user  # User exists but no slate
    ):
        """Test reading slate when no slate exists for user"""
        # Execute
        result = await read_slate(run_context)
        
        # Assert
        assert result == "The slate is currently empty."
        mock_logfire.info.assert_called_once_with("Slate is empty")

    async def test_read_slate_multiple_slates_returns_most_recent(
        self, 
        run_context, 
        mock_get_db_session, 
        mock_logfire, 
        mock_log_tool_call,
        db_session,
        test_user
    ):
        """Test that read_slate returns the most recently updated slate"""
        # Create multiple slates with explicit timestamps
        from datetime import datetime, timedelta
        
        older_time = datetime.now() - timedelta(hours=1)
        older_slate = Slate(
            user_id=test_user.id, 
            content="Older content",
            updated_at=older_time
        )
        db_session.add(older_slate)
        db_session.commit()
        
        newer_time = datetime.now()
        newer_slate = Slate(
            user_id=test_user.id, 
            content="Newer content",
            updated_at=newer_time
        )
        db_session.add(newer_slate)
        db_session.commit()
        
        # Execute
        result = await read_slate(run_context)
        
        # Assert - should return the newer slate content
        assert result == "Newer content"


@pytest.mark.asyncio
class TestUpdateSlate:
    """Tests for update_slate tool"""

    async def test_update_existing_slate(
        self, 
        run_context, 
        mock_get_db_session, 
        mock_logfire, 
        mock_log_tool_call,
        db_session,
        test_slate
    ):
        """Test updating an existing slate in database"""
        # Setup
        new_content = "Updated slate content from test"
        input_data = UpdateSlateInput(content=new_content)
        original_id = test_slate.id
        
        # Execute
        result = await update_slate(run_context, input_data)
        
        # Assert
        assert result == "Slate updated successfully."
        
        # Verify database was actually updated
        db_session.refresh(test_slate)
        assert test_slate.content == new_content
        assert test_slate.id == original_id  # Same slate, not a new one
        
        mock_logfire.info.assert_called_with("Slate updated", slate_id=str(test_slate.id))

    async def test_create_new_slate_when_none_exists(
        self, 
        run_context, 
        mock_get_db_session, 
        mock_logfire, 
        mock_log_tool_call,
        db_session,
        test_user  # User exists but no slate
    ):
        """Test creating a new slate when none exists for the user"""
        # Setup
        new_content = "Brand new slate content"
        input_data = UpdateSlateInput(content=new_content)
        
        # Verify no slate exists initially
        existing_slates = db_session.query(Slate).filter(Slate.user_id == test_user.id).all()
        assert len(existing_slates) == 0
        
        # Execute
        result = await update_slate(run_context, input_data)
        
        # Assert
        assert result == "Slate updated successfully."
        
        # Verify new slate was created in database
        new_slates = db_session.query(Slate).filter(Slate.user_id == test_user.id).all()
        assert len(new_slates) == 1
        assert new_slates[0].content == new_content
        assert new_slates[0].user_id == test_user.id
        
        mock_logfire.info.assert_called_with("New slate created")

    async def test_update_slate_replaces_existing_content(
        self, 
        run_context, 
        mock_get_db_session, 
        mock_logfire, 
        mock_log_tool_call,
        db_session,
        test_slate
    ):
        """Test that updating completely replaces slate content"""
        # Setup
        original_content = test_slate.content
        new_content = "Completely different content"
        input_data = UpdateSlateInput(content=new_content)
        
        # Execute
        result = await update_slate(run_context, input_data)
        
        # Assert
        assert result == "Slate updated successfully."
        
        # Verify content was completely replaced, not appended
        db_session.refresh(test_slate)
        assert test_slate.content == new_content
        assert original_content not in test_slate.content

    async def test_update_slate_with_empty_content(
        self, 
        run_context, 
        mock_get_db_session, 
        mock_logfire, 
        mock_log_tool_call,
        db_session,
        test_slate
    ):
        """Test updating slate with empty content"""
        # Setup
        input_data = UpdateSlateInput(content="")
        
        # Execute
        result = await update_slate(run_context, input_data)
        
        # Assert
        assert result == "Slate updated successfully."
        
        # Verify empty content was saved
        db_session.refresh(test_slate)
        assert test_slate.content == ""

    async def test_update_slate_logging(
        self, 
        run_context, 
        mock_get_db_session, 
        mock_logfire, 
        mock_log_tool_call,
        test_slate
    ):
        """Test that update_slate logs correctly"""
        # Setup
        input_data = UpdateSlateInput(content="test content for logging")
        
        # Execute
        await update_slate(run_context, input_data)
        
        # Assert logging
        mock_logfire.span.assert_called_once_with("update_slate", user_id=str(run_context.deps.user_id))
        mock_log_tool_call.assert_called_once_with(run_context, "update_slate", input_data.model_dump())


class TestUpdateSlateInputValidation:
    """Tests for UpdateSlateInput model validation"""

    def test_update_slate_input_valid_content(self):
        """Test UpdateSlateInput with valid content"""
        valid_input = UpdateSlateInput(content="Valid slate content")
        assert valid_input.content == "Valid slate content"

    def test_update_slate_input_empty_content(self):
        """Test UpdateSlateInput with empty content (should be allowed)"""
        empty_input = UpdateSlateInput(content="")
        assert empty_input.content == ""

    def test_update_slate_input_long_content(self):
        """Test UpdateSlateInput with very long content"""
        long_content = "A" * 10000  # Very long content
        long_input = UpdateSlateInput(content=long_content)
        assert long_input.content == long_content