"""
Tests for data search tools using real PostgreSQL database.
"""

import pytest
import numpy as np
from uuid import uuid4

from ai.tools.data import (
    search_raw_entries, get_recent_raw_entries,
    RawEntrySearchInput
)
from db.models import RawEntry


@pytest.mark.asyncio
class TestSearchRawEntries:
    """Tests for search_raw_entries tool"""

    async def test_search_raw_entries_finds_relevant_entries(
        self, 
        run_context, 
        mock_get_db_session_data, 
        mock_logfire, 
        mock_log_tool_call,
        mock_embed_query,
        db_session,
        test_raw_entry
    ):
        """Test raw entry search finds relevant entries"""
        # Setup
        input_data = RawEntrySearchInput(query="test search query", limit=10)
        
        # Execute
        result = await search_raw_entries(run_context, input_data)
        
        # Assert
        assert str(test_raw_entry.id) in result
        assert test_raw_entry.source in result
        assert str(test_raw_entry.created_at) in result
        
        # Verify content is displayed (should be truncated for long content)
        content_str = str(test_raw_entry.content)
        if len(content_str) > 300:
            expected_content = content_str[:300] + "..."
        else:
            expected_content = content_str
        assert expected_content in result
        
        # Verify embedding query was called
        mock_embed_query.assert_called_once_with(input_data.query)
        mock_logfire.info.assert_called_with("Raw entries found", count=1)

    async def test_search_raw_entries_with_source_filter(
        self, 
        run_context, 
        mock_get_db_session_data, 
        mock_logfire, 
        mock_log_tool_call,
        mock_embed_query,
        db_session,
        test_user
    ):
        """Test raw entry search with source filter"""
        # Setup - create entries with different sources
        entry1 = RawEntry(
            user_id=test_user.id,
            source="source_a",
            content={"text": "Content from source A"},
            embedding=np.random.rand(3072).astype(np.float16)
        )
        entry2 = RawEntry(
            user_id=test_user.id,
            source="source_b", 
            content={"text": "Content from source B"},
            embedding=np.random.rand(3072).astype(np.float16)
        )
        db_session.add(entry1)
        db_session.add(entry2)
        db_session.commit()
        
        input_data = RawEntrySearchInput(query="content", limit=10, source_filter="source_a")
        
        # Execute
        result = await search_raw_entries(run_context, input_data)
        
        # Assert - should only find entry from source_a
        assert "source_a" in result
        assert "source_b" not in result

    async def test_search_raw_entries_limit_works(
        self, 
        run_context, 
        mock_get_db_session_data, 
        mock_logfire, 
        mock_log_tool_call,
        mock_embed_query,
        db_session,
        test_user
    ):
        """Test that search limit is properly applied"""
        # Setup - create multiple raw entries
        entries = []
        for i in range(15):
            entry = RawEntry(
                user_id=test_user.id,
                source=f"source_{i}",
                content={"text": f"Content for entry {i}"},
                embedding=np.random.rand(3072).astype(np.float16)
            )
            entries.append(entry)
            db_session.add(entry)
        db_session.commit()
        
        input_data = RawEntrySearchInput(query="content", limit=5)
        
        # Execute
        result = await search_raw_entries(run_context, input_data)
        
        # Assert - should only return 5 entries despite having 15
        entry_sections = result.split("---")
        # Filter out empty sections
        actual_entries = [section for section in entry_sections if section.strip()]
        assert len(actual_entries) <= 5

    async def test_search_raw_entries_no_results(
        self, 
        run_context, 
        mock_get_db_session_data, 
        mock_logfire, 
        mock_log_tool_call,
        mock_embed_query,
        db_session,
        test_user  # User exists but no raw entries
    ):
        """Test search when no raw entries exist"""
        # Setup
        input_data = RawEntrySearchInput(query="nonexistent content", limit=10)
        
        # Execute
        result = await search_raw_entries(run_context, input_data)
        
        # Assert
        assert result == "No relevant raw entries found."
        mock_logfire.info.assert_called_with("No raw entries found for search")

    async def test_search_raw_entries_content_truncation(
        self, 
        run_context, 
        mock_get_db_session_data, 
        mock_logfire, 
        mock_log_tool_call,
        mock_embed_query,
        db_session,
        test_user
    ):
        """Test that very long content is properly truncated"""
        # Setup - create entry with very long content
        long_content = {"text": "A" * 500}  # Much longer than 300 chars
        long_entry = RawEntry(
            user_id=test_user.id,
            source="test_source",
            content=long_content,
            embedding=np.random.rand(3072).astype(np.float16)
        )
        db_session.add(long_entry)
        db_session.commit()
        
        input_data = RawEntrySearchInput(query="content", limit=10)
        
        # Execute
        result = await search_raw_entries(run_context, input_data)
        
        # Assert - content should be truncated
        # The content is JSON, so it will look like str({"text": "AAAA..."})
        assert "..." in result  # Should show truncation
        full_content_str = str(long_content)
        assert full_content_str not in result  # Full content should not be present

    async def test_search_raw_entries_user_isolation(
        self, 
        run_context, 
        mock_get_db_session_data, 
        mock_logfire, 
        mock_log_tool_call,
        mock_embed_query,
        db_session,
        test_user
    ):
        """Test that users only see their own raw entries"""
        # Setup - create another user and their entry
        from db.models import User
        other_user = User(
            id=uuid4(),
            firebase_user_id="other_firebase_id",
            email="other@example.com"
        )
        db_session.add(other_user)
        db_session.flush()  # Get the ID assigned
        
        other_entry = RawEntry(
            user_id=other_user.id,
            source="other_source", 
            content={"text": "Other user's content"},
            embedding=np.random.rand(3072).astype(np.float16)
        )
        db_session.add(other_entry)
        db_session.commit()
        
        input_data = RawEntrySearchInput(query="content", limit=10)
        
        # Execute
        result = await search_raw_entries(run_context, input_data)
        
        # Assert - should not find other user's entry
        assert "Other user's content" not in result


@pytest.mark.asyncio
class TestGetRecentRawEntries:
    """Tests for get_recent_raw_entries tool"""

    async def test_get_recent_raw_entries_returns_entries(
        self, 
        run_context, 
        mock_get_db_session_data, 
        mock_logfire, 
        mock_log_tool_call,
        db_session,
        test_raw_entry
    ):
        """Test getting recent raw entries returns existing entries"""
        # Execute
        result = await get_recent_raw_entries(run_context, 20)
        
        # Assert
        assert test_raw_entry.source in result
        assert str(test_raw_entry.created_at) in result
        
        # Content should be truncated if over 200 chars for recent entries
        content_str = str(test_raw_entry.content)
        if len(content_str) > 200:
            expected_content = content_str[:200] + "..."
        else:
            expected_content = content_str
        assert expected_content in result
        
        mock_logfire.info.assert_called_with("Recent raw entries retrieved", count=1)

    async def test_get_recent_raw_entries_chronological_order(
        self, 
        run_context, 
        mock_get_db_session_data, 
        mock_logfire, 
        mock_log_tool_call,
        db_session,
        test_user
    ):
        """Test that recent entries are returned in reverse chronological order"""
        # Setup - create multiple entries with explicit timestamps
        from datetime import datetime, timedelta
        
        older_time = datetime.now() - timedelta(hours=1)
        older_entry = RawEntry(
            user_id=test_user.id,
            source="older_source",
            content={"text": "Older content"},
            embedding=np.random.rand(3072).astype(np.float16),
            created_at=older_time
        )
        db_session.add(older_entry)
        db_session.commit()
        
        newer_time = datetime.now()
        newer_entry = RawEntry(
            user_id=test_user.id,
            source="newer_source",
            content={"text": "Newer content"},
            embedding=np.random.rand(3072).astype(np.float16),
            created_at=newer_time
        )
        db_session.add(newer_entry)
        db_session.commit()
        
        # Execute
        result = await get_recent_raw_entries(run_context, 20)
        
        # Assert - newer entry should appear first
        newer_pos = result.find("newer_source")
        older_pos = result.find("older_source")
        assert newer_pos < older_pos  # Newer should come first in string

    async def test_get_recent_raw_entries_default_limit(
        self, 
        run_context, 
        mock_get_db_session_data, 
        mock_logfire, 
        mock_log_tool_call,
        db_session,
        test_user
    ):
        """Test getting recent raw entries with default limit"""
        # Execute (using default limit)
        await get_recent_raw_entries(run_context)
        
        # Assert logging shows default limit
        mock_logfire.span.assert_called_once_with("get_recent_raw_entries", limit=20)

    async def test_get_recent_raw_entries_custom_limit(
        self, 
        run_context, 
        mock_get_db_session_data, 
        mock_logfire, 
        mock_log_tool_call,
        db_session,
        test_user
    ):
        """Test getting recent raw entries with custom limit"""
        # Setup - create multiple entries
        entries = []
        for i in range(25):
            entry = RawEntry(
                user_id=test_user.id,
                source=f"source_{i}",
                content={"text": f"Content {i}"},
                embedding=np.random.rand(3072).astype(np.float16)
            )
            entries.append(entry)
            db_session.add(entry)
        db_session.commit()
        
        custom_limit = 10
        
        # Execute
        result = await get_recent_raw_entries(run_context, custom_limit)
        
        # Assert - should only return 10 entries despite having 25
        entry_sections = result.split("---")
        actual_entries = [section for section in entry_sections if section.strip()]
        assert len(actual_entries) <= custom_limit
        
        mock_logfire.span.assert_called_once_with("get_recent_raw_entries", limit=custom_limit)

    async def test_get_recent_raw_entries_no_results(
        self, 
        run_context, 
        mock_get_db_session_data, 
        mock_logfire, 
        mock_log_tool_call,
        db_session,
        test_user  # User exists but no raw entries
    ):
        """Test getting recent raw entries when none exist"""
        # Execute
        result = await get_recent_raw_entries(run_context, 20)
        
        # Assert
        assert result == "No recent raw entries found."
        mock_logfire.info.assert_called_with("No recent raw entries found")

    async def test_get_recent_raw_entries_content_truncation(
        self, 
        run_context, 
        mock_get_db_session_data, 
        mock_logfire, 
        mock_log_tool_call,
        db_session,
        test_user
    ):
        """Test that long content is properly truncated for recent entries"""
        # Setup - create entry with long content
        long_content = {"text": "B" * 300}  # Content longer than 200 chars
        long_entry = RawEntry(
            user_id=test_user.id,
            source="test_source",
            content=long_content,
            embedding=np.random.rand(3072).astype(np.float16)
        )
        db_session.add(long_entry)
        db_session.commit()
        
        # Execute
        result = await get_recent_raw_entries(run_context, 20)
        
        # Assert - content should be truncated to 200 chars for recent entries
        assert "..." in result
        full_content_str = str(long_content)
        assert full_content_str not in result

    async def test_get_recent_raw_entries_user_isolation(
        self, 
        run_context, 
        mock_get_db_session_data, 
        mock_logfire, 
        mock_log_tool_call,
        db_session,
        test_user
    ):
        """Test that users only see their own recent entries"""
        # Setup - create another user and their entry
        from db.models import User
        other_user = User(
            id=uuid4(),
            firebase_user_id="other_firebase_id_2",
            email="other2@example.com"
        )
        db_session.add(other_user)
        db_session.flush()
        
        other_entry = RawEntry(
            user_id=other_user.id,
            source="other_source",
            content={"text": "Other user's content"},
            embedding=np.random.rand(3072).astype(np.float16)
        )
        db_session.add(other_entry)
        db_session.commit()
        
        # Execute
        result = await get_recent_raw_entries(run_context, 20)
        
        # Assert - should not find other user's entry
        assert "Other user's content" not in result


class TestRawEntrySearchInput:
    """Tests for RawEntrySearchInput model validation"""

    def test_raw_entry_search_input_defaults(self):
        """Test RawEntrySearchInput default values"""
        input_with_defaults = RawEntrySearchInput(query="test query")
        assert input_with_defaults.query == "test query"
        assert input_with_defaults.limit == 10
        assert input_with_defaults.source_filter is None

    def test_raw_entry_search_input_custom_values(self):
        """Test RawEntrySearchInput with custom values"""
        custom_input = RawEntrySearchInput(
            query="custom query", 
            limit=25, 
            source_filter="custom_source"
        )
        assert custom_input.query == "custom query"
        assert custom_input.limit == 25
        assert custom_input.source_filter == "custom_source"

    def test_raw_entry_search_input_optional_source_filter(self):
        """Test that source_filter is optional"""
        input_no_filter = RawEntrySearchInput(query="test", limit=5)
        assert input_no_filter.source_filter is None
        
        input_with_filter = RawEntrySearchInput(query="test", limit=5, source_filter="test_source")
        assert input_with_filter.source_filter == "test_source"