import os
import time
import threading
from datetime import datetime
from uuid import UUID

import httpx


def deliver_message(
    user_id: UUID,
    channel: str,
    message: str,
    sender: str,
    schedule_time: datetime | None = None,
) -> None:
    """Deliver message directly to the agent service (local development mode).

    Uses a direct HTTP call to the agent endpoint. If schedule_time is provided,
    schedules delivery on a background thread after the appropriate delay.
    """
    agent_service_url = os.getenv("AGENT_ENDPOINT_URL", "http://localhost:8001")

    payload = {
        "user_id": str(user_id),
        "channel": channel,
        "message": message,
        "sender": sender,
    }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "everlight-agents/messaging-local",
    }

    if schedule_time:
        # Calculate delay and schedule for later
        now = datetime.now(tz=schedule_time.tzinfo) if schedule_time.tzinfo else datetime.now()
        delay_seconds = max(0, (schedule_time - now).total_seconds())
        print(f"   [LOCAL] Scheduling message for {schedule_time} (delay: {delay_seconds:.1f}s)")

        def delayed_send():
            time.sleep(delay_seconds)
            _make_direct_http_call(agent_service_url, payload, headers)

        thread = threading.Thread(target=delayed_send, daemon=True)
        thread.start()
        print(f"   [LOCAL] Message scheduled for delivery at {schedule_time}")
    else:
        # Send immediately
        _make_direct_http_call(agent_service_url, payload, headers)


def _make_direct_http_call(url: str, payload: dict, headers: dict) -> None:
    """Make direct HTTP call to the agent service."""
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(f"{url}/message", json=payload, headers=headers)
            if response.status_code == 200:
                print(f"   [LOCAL] Message delivered successfully to {url}/message")
            else:
                print(
                    f"   [LOCAL] Message delivery failed: {response.status_code} - {response.text}"
                )
    except Exception as e:
        print(f"   [LOCAL] Error delivering message: {e}")
