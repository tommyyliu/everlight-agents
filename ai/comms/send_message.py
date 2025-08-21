from __future__ import annotations

import os
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from db.models import Message
from db.session import get_db_session

Transport = Literal["auto", "local", "cloud"]


def send_message(
    user_id: UUID,
    channel: str,
    message: str,
    sender: str,
    schedule_time: Optional[datetime] = None,
    *,
    transport: Transport = "auto",
) -> dict:
    """
    Persist a message and deliver it to the agent service using the selected transport.
    """

    # Persist the message to the database
    db = next(get_db_session())
    try:
        db_message = Message(
            user_id=user_id,
            sender=sender,
            payload={
                "channel": channel,
                "message": message,
            },
        )
        db.add(db_message)
        db.commit()
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": f"DB error: {e}"}
    finally:
        db.close()

    selected = _select_transport(transport)

    try:
        if selected == "local":
            from .send_message_local import deliver_message as deliver_local
            deliver_local(user_id, channel, message, sender, schedule_time)
        else:
            from .send_message_cloud import deliver_message as deliver_cloud
            deliver_cloud(user_id, channel, message, sender, schedule_time)
        return {"status": "message_sent"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _select_transport(transport: Transport) -> Literal["local", "cloud"]:
    if transport in ("local", "cloud"):
        return transport
    local_mode = os.getenv("LOCAL_DEVELOPMENT", "false").lower() == "true"
    return "local" if local_mode else "cloud"
