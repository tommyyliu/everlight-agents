# Local Development Mode

This project supports a local development mode that bypasses Google Cloud Tasks for easier local testing and development.

## Environment Variable

Set the `LOCAL_DEVELOPMENT` environment variable to enable local mode:

```bash
export LOCAL_DEVELOPMENT=true
```

Or in your `.env` file:
```env
LOCAL_DEVELOPMENT=true
```

## How It Works

### Production Mode (LOCAL_DEVELOPMENT=false or unset)
- Messages are queued via Google Cloud Tasks
- Requires Google Cloud project configuration
- Provides reliable, scalable message delivery
- Messages are retried on failure

### Local Development Mode (LOCAL_DEVELOPMENT=true)
- **Immediate messages**: Sent directly via HTTP to the agent service
- **Scheduled messages**: Use threading with `time.sleep()` to delay delivery
- No Google Cloud dependencies required
- Faster feedback during development

## Message Types

### Immediate Messages
```python
# In local mode: HTTP POST sent immediately
send_message(
    user_id=user_id,
    channel="notifications",
    message="Hello!",
    sender="my-agent"
)
```

### Scheduled Messages
```python
from datetime import datetime, timedelta

# In local mode: Thread sleeps then sends HTTP POST
future_time = datetime.now() + timedelta(minutes=5)
send_message(
    user_id=user_id,
    channel="reminders", 
    message="Don't forget!",
    sender="my-agent",
    schedule_time=future_time
)
```

## Configuration

Make sure your `.env` file has the agent service URL:

```env
LOCAL_DEVELOPMENT=true
AGENT_ENDPOINT_URL=http://localhost:8001
```

## Agent Tool Feedback

The communication tools provide different feedback based on the mode:

**Local Mode:**
- `"Message sent directly to notifications (local development mode)."`
- `"Message scheduled for reminders at 2025-01-01 12:00:00 (local mode: 300.0s delay)."`

**Production Mode:**
- `"Message queued for delivery to notifications via Cloud Tasks."`
- `"Message scheduled for reminders at 2025-01-01 12:00:00 via Cloud Tasks."`

## Benefits for Development

1. **No Cloud Setup Required**: Test messaging without Google Cloud configuration
2. **Immediate Feedback**: See HTTP requests in logs immediately
3. **Debugging**: Easier to debug message delivery issues
4. **Testing**: Scheduled messages work with real delays during testing

## Limitations

- No automatic retries on failure
- Threading-based scheduling is not as robust as Cloud Tasks
- Messages are lost if the process terminates
- No distributed queuing capabilities

## Switching to Production

When deploying to production, simply set:
```env
LOCAL_DEVELOPMENT=false
```

And ensure your Google Cloud Tasks configuration is complete.