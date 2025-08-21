from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from uuid import UUID
from google.cloud import tasks_v2


def deliver_message(
    user_id: UUID,
    channel: str,
    message: str,
    sender: str,
    schedule_time: datetime | None = None,
    *,
    queue_name: str = "messages",
    client: "tasks_v2.CloudTasksClient" | None = None,
) -> None:
    """Enqueue a Cloud Task to deliver the message to the agent service."""
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-west1")
    agent_service_url = os.getenv("AGENT_ENDPOINT_URL", "http://localhost:8001")

    if not project_id:
        raise RuntimeError(
            "GOOGLE_CLOUD_PROJECT is not set; cloud transport cannot be used."
        )

    payload = {
        "user_id": str(user_id),
        "channel": channel,
        "message": message,
        "sender": sender,
    }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "everlight-agents/messaging",
    }

    client = client or tasks_v2.CloudTasksClient()
    parent = client.queue_path(project_id, location, queue_name)

    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{agent_service_url}/message",
            "headers": headers,
            "body": json.dumps(payload).encode(),
        }
    }

    if schedule_time:
        # Ensure schedule_time is timezone-aware UTC
        if schedule_time.tzinfo is None:
            schedule_time = schedule_time.replace(tzinfo=timezone.utc)
        else:
            schedule_time = schedule_time.astimezone(timezone.utc)
        from google.protobuf.timestamp_pb2 import (
            Timestamp,
        )  # local import to avoid import unless needed

        ts = Timestamp()
        ts.FromDatetime(schedule_time)
        task["schedule_time"] = ts

    resp = client.create_task(request={"parent": parent, "task": task})
    print(f"   [CLOUD] Successfully enqueued agent message task: {resp.name}")
