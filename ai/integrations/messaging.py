#!/usr/bin/env python3
"""
Messaging utilities for sending notifications via Google Cloud Tasks.
"""

import os
import json
from uuid import UUID
from google.cloud import tasks_v2


async def send_agent_message_notification(user_id: UUID, channel: str, message: str, sender: str):
    """
    Enqueue a task to send a message notification to the agent service.
    
    Args:
        user_id: The user's UUID
        channel: The channel to send the message to
        message: The message content
        sender: The sender identifier
    """
    try:
        # Get Google Cloud Tasks configuration
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-west1")
        queue_name = "messages"
        agent_service_url = os.getenv("AGENT_ENDPOINT_URL", "http://localhost:8001")
        agent_service_token = os.getenv("AGENT_SERVICE_TOKEN")
        
        if not project_id:
            print("   GOOGLE_CLOUD_PROJECT not configured - falling back to direct HTTP")
            # Fallback to direct HTTP call if Cloud Tasks not configured
            return await _send_direct_http_notification(user_id, channel, message, sender)
            
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
        
        # Enqueue the task
        response = client.create_task(request={"parent": parent, "task": task})
        print(f"   Successfully enqueued agent message task: {response.name}")
        
    except Exception as e:
        print(f"   Error enqueuing agent message task: {e}")
        # Fallback to direct HTTP call
        return await _send_direct_http_notification(user_id, channel, message, sender)


async def _send_direct_http_notification(user_id: UUID, channel: str, message: str, sender: str):
    """
    Fallback method to send notification directly via HTTP when Cloud Tasks is not available.
    """
    import httpx
    
    try:
        async with httpx.AsyncClient() as client:
            payload = {
                "user_id": str(user_id),
                "channel": channel,
                "message": message,
                "sender": sender
            }
                
            # Get agent endpoint URL from environment, with fallback to localhost
            agent_endpoint_url = os.getenv("AGENT_ENDPOINT_URL", "http://localhost:8001")
            
            # Make a request to the agent endpoint
            response = await client.post(
                f"{agent_endpoint_url}/message",
                json=payload
            )
            
            print(f"   Direct HTTP notification sent: {response.status_code}")
            return response.json()
    except Exception as e:
        print(f"   Error sending direct HTTP notification: {e}")
        return None