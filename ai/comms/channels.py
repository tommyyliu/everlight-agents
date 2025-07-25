import httpx
import asyncio
from uuid import UUID

from db.models import Message
from db.session import get_db_session


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
                
            # Make a request to the agent endpoint (self-reference for internal processing)
            response = await client.post(
                "http://localhost:8001/agent/message",
                json=payload
            )
            
            return response.json()
        except Exception as e:
            print(f"Error notifying ai endpoint: {e}")
            return None

def send_message(user_id: UUID, channel: str, message: str, sender: str):
    """
    Send a message to a channel.
    This function persists the message to the database and notifies the ai endpoint.
    """
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

    return db_message