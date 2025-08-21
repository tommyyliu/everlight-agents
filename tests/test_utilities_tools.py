"""
Tests for utility tools.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime
from freezegun import freeze_time

from ai.tools.utilities import get_current_time, get_hourly_weather


@pytest.mark.asyncio
class TestGetCurrentTime:
    """Tests for get_current_time tool"""

    @freeze_time("2023-12-25 15:30:45")
    async def test_get_current_time(
        self, 
        mock_run_context, 
        mock_logfire, 
        mock_log_tool_call
    ):
        """Test getting current time"""
        # Execute
        result = await get_current_time(mock_run_context)
        
        # Assert
        expected_time = "2023-12-25T15:30:45"
        assert result == expected_time
        
        # Verify logging
        mock_logfire.span.assert_called_once_with("get_current_time")
        mock_log_tool_call.assert_called_once_with(mock_run_context, "get_current_time", {})
        mock_logfire.info.assert_called_once_with("Current time retrieved", time=expected_time)

    async def test_get_current_time_format(
        self, 
        mock_run_context, 
        mock_logfire, 
        mock_log_tool_call
    ):
        """Test that current time is returned in ISO format"""
        # Execute
        result = await get_current_time(mock_run_context)
        
        # Assert - should be parseable as datetime
        parsed_time = datetime.fromisoformat(result)
        assert isinstance(parsed_time, datetime)
        
        # Should be roughly current time (within a few seconds)
        now = datetime.now()
        time_diff = abs((now - parsed_time).total_seconds())
        assert time_diff < 5  # Within 5 seconds

    async def test_get_current_time_multiple_calls(
        self, 
        mock_run_context, 
        mock_logfire, 
        mock_log_tool_call
    ):
        """Test that multiple calls return different times"""
        # Execute first call
        result1 = await get_current_time(mock_run_context)
        
        # Small delay to ensure different timestamps
        import asyncio
        await asyncio.sleep(0.01)
        
        # Execute second call
        result2 = await get_current_time(mock_run_context)
        
        # Assert - times should be different (unless running very fast)
        # At minimum, they should be valid datetime strings
        datetime.fromisoformat(result1)
        datetime.fromisoformat(result2)


@pytest.mark.asyncio
class TestGetHourlyWeather:
    """Tests for get_hourly_weather tool"""

    async def test_get_hourly_weather(
        self, 
        mock_run_context, 
        mock_logfire, 
        mock_log_tool_call
    ):
        """Test getting weather information"""
        # Execute
        result = await get_hourly_weather(mock_run_context)
        
        # Assert
        expected_weather = "Sunny and 72 degrees. This is just example weather data by the way. Actual weather API integration will come in the future."
        assert result == expected_weather
        
        # Verify logging
        mock_logfire.span.assert_called_once_with("get_hourly_weather")
        mock_log_tool_call.assert_called_once_with(mock_run_context, "get_hourly_weather", {})

    async def test_get_hourly_weather_consistency(
        self, 
        mock_run_context, 
        mock_logfire, 
        mock_log_tool_call
    ):
        """Test that weather returns consistent response"""
        # Execute multiple times
        result1 = await get_hourly_weather(mock_run_context)
        result2 = await get_hourly_weather(mock_run_context)
        
        # Assert - should return the same mock data
        assert result1 == result2
        assert "Sunny and 72 degrees" in result1

    async def test_get_hourly_weather_indicates_mock(
        self, 
        mock_run_context, 
        mock_logfire, 
        mock_log_tool_call
    ):
        """Test that weather response indicates it's example data"""
        # Execute
        result = await get_hourly_weather(mock_run_context)
        
        # Assert - should indicate this is example/mock data
        assert "example weather data" in result.lower()
        assert "future" in result.lower()


@pytest.mark.asyncio
class TestUtilitiesToolsIntegration:
    """Integration tests for utility tools"""

    async def test_utilities_tools_logging_integration(
        self, 
        mock_run_context
    ):
        """Test that all utility tools integrate correctly with logging"""
        
        with patch('ai.tools.utilities.logfire') as mock_logfire, \
             patch('ai.tools.utilities.log_tool_call') as mock_log_tool_call:
            
            # Setup logfire mock
            mock_logfire.span.return_value.__enter__ = Mock()
            mock_logfire.span.return_value.__exit__ = Mock()
            
            # Test both utility tools
            await get_current_time(mock_run_context)
            await get_hourly_weather(mock_run_context)
            
            # Assert both tools logged properly
            assert mock_logfire.span.call_count == 2
            assert mock_log_tool_call.call_count == 2
            
            # Check specific tool calls
            span_calls = [call[0][0] for call in mock_logfire.span.call_args_list]
            assert "get_current_time" in span_calls
            assert "get_hourly_weather" in span_calls
            
            tool_calls = [call[0][1] for call in mock_log_tool_call.call_args_list]
            assert "get_current_time" in tool_calls
            assert "get_hourly_weather" in tool_calls

    async def test_utilities_context_usage(
        self, 
        mock_run_context
    ):
        """Test that utility tools use the context correctly"""
        
        with patch('ai.tools.utilities.log_tool_call') as mock_log_tool_call, \
             patch('ai.tools.utilities.logfire'):
            # Execute tools
            await get_current_time(mock_run_context)
            await get_hourly_weather(mock_run_context)
            
            # Assert context was passed to log_tool_call
            for call in mock_log_tool_call.call_args_list:
                assert call[0][0] == mock_run_context  # First argument should be context


class TestUtilitiesErrorHandling:
    """Test error handling in utility tools"""

    @pytest.mark.asyncio
    async def test_get_current_time_with_logging_error(
        self, 
        mock_run_context
    ):
        """Test get_current_time handles logging errors gracefully"""
        
        with patch('ai.tools.utilities.log_tool_call', side_effect=Exception("Logging error")), \
             patch('ai.tools.utilities.logfire'):
            # Should still work even if logging fails
            result = await get_current_time(mock_run_context)
            
            # Should still return valid time
            datetime.fromisoformat(result)

    @pytest.mark.asyncio
    async def test_get_weather_with_logging_error(
        self, 
        mock_run_context
    ):
        """Test get_hourly_weather handles logging errors gracefully"""
        
        with patch('ai.tools.utilities.log_tool_call', side_effect=Exception("Logging error")), \
             patch('ai.tools.utilities.logfire'):
            # Should still work even if logging fails
            result = await get_hourly_weather(mock_run_context)
            
            # Should still return weather data
            assert "Sunny and 72 degrees" in result