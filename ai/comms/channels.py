from uuid import UUID

from db.models import Message
from db.session import get_db_session
from ai.integrations.messaging import send_agent_message_notification


def send_message(user_id: UUID, channel: str, message: str, sender: str, schedule_time):
    """
    Send a message to a channel.
    This function persists the message to the database and enqueues a task to notify agents.
    """
    # Persist the message to the database
    db = next(get_db_session())
    try:
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
        
        # Enqueue task to notify agents via Cloud Tasks
        send_agent_message_notification(user_id, channel, message, sender, schedule_time)
        
        return {"status": "message_sent"}
    except Exception as e:
        db.rollback()
        print(f"Error sending message: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()
