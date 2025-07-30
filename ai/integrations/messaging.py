#!/usr/bin/env python3
"""
Messaging utilities for sending notifications via Google Cloud Tasks.
"""

import os
import json
from uuid import UUID
from google.cloud import tasks_v2
from datetime import datetime


def send_agent_message_notification(user_id: UUID, channel: str, message: str, sender: str, schedule_time: datetime = None):
    """
    Enqueue a task to send a message notification to the agent service.
    
    Args:
        user_id: The user's UUID
        channel: The channel to send the message to
        message: The message content
        sender: The sender identifier
        schedule_time: Optional datetime to schedule the message for future delivery
    """
    # Get Google Cloud Tasks configuration
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-west1")
    queue_name = "messages"
    agent_service_url = os.getenv("AGENT_ENDPOINT_URL", "http://localhost:8001")
    agent_service_token = os.getenv("AGENT_SERVICE_TOKEN")

    # Prepare the task payload for the agent service
    task_payload = {
        "user_id": str(user_id),
        "channel": channel,
        "message": message,
        "sender": sender
    }

    # Prepare headers for the eventual HTTP request
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "everlight-agents/messaging"
    }

    if agent_service_token:
        headers["Authorization"] = f"Bearer {agent_service_token}"

    # Create Cloud Tasks client
    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(project_id, location, queue_name)

    # Create the task
    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{agent_service_url}/message",
            "headers": headers,
            "body": json.dumps(task_payload).encode()
        }
    }

    # Add schedule_time if provided
    if schedule_time:
        from google.protobuf.timestamp_pb2 import Timestamp
        timestamp = Timestamp()
        timestamp.FromDatetime(schedule_time)
        task["schedule_time"] = timestamp

    # Enqueue the task
    response = client.create_task(request={"parent": parent, "task": task})
    print(f"   Successfully enqueued agent message task: {response.name}")
