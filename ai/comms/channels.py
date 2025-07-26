import httpx
import asyncio
import os
from uuid import UUID

from db.models import Message
from db.session import get_db_session


# Removed direct database imports - now uses API service for persistence


async def notify_agent_endpoint(user_id: UUID, channel: str, message: str, sender: str):
    """
    Notify the ai endpoint about a new message.
    This function makes an HTTP request to the ai endpoint.
    """
    async with httpx.AsyncClient() as client:
        try:
            payload = {
                "user_id": str(user_id),
                "channel": channel,
                "message": message,
                "sender": sender
            }
                
            # Get agent endpoint URL from environment, with fallback to localhost
            agent_endpoint_url = os.getenv("AGENT_ENDPOINT_URL", "http://localhost:8001")
            
            # Make a request to the agent endpoint (self-reference for internal processing)
            response = await client.post(
                f"{agent_endpoint_url}/message",
                json=payload
            )
            
            return response.json()
        except Exception as e:
            print(f"Error notifying ai endpoint: {e}")
            print(f"Payload: {payload}")
            print(f"Agent Endpoint URL: {agent_endpoint_url}")
            print(f"Response: {response}")
            print(f"{e.__traceback__}")
            return None

def send_message(user_id: UUID, channel: str, message: str, sender: str):
    """
    Send a message to a channel.
    This function persists the message via the API service and notifies the agent endpoint.
    """
    # Create tasks for both API persistence and agent notification
    db = next(get_db_session())
    db_message = Message(
        user_id=user_id,
        sender=sender,
        payload={
            "channel": channel,
            "message": message
        }
    )
    db.add(db_message)
    db.commit()

    asyncio.create_task(notify_agent_endpoint(user_id, channel, message, sender))
    return {"status": "message_sent"}
