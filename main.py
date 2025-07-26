from datetime import datetime
from typing import List, Dict, Any, Annotated

from fastapi import FastAPI, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette import status

from ai.agent import get_user_ai_base
from db.models import Agent, AgentSubscription, User
from db.session import get_db_session

app = FastAPI(title="Everlight Agents Service")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class MessageNotification(BaseModel):
    channel: str
    message: str
    sender: str
    user_id: str


class AgentResponse(BaseModel):
    agent_name: str
    response: str
    actions: List[Dict[str, Any]] = []


async def process_agent_message(
        message_notification: MessageNotification,
        user: User,
        agent: Agent):
    """
    Process a message for a specific ai.
    This function creates a prompt for the ai and augments it with message information.
    TODO: Consider moving this to its own file.
    """
    # Todo change datetime to use user's timezone.
    user_info = f"""
    Your user is {user.email}. The current time is {datetime.now()}.
    Currently, we're just testing the code to give you tool calling functionality.
    Try to just do everything that you think you need to do. Then, just log it all into a note, so that we can inspect
    how you're doing.
    """
    message_info = f"""
    On channel {message_notification.channel},
    An ai or process has sent a message: {message_notification.message}.
    The sender is {message_notification.sender}.
    """
    agent_prompt = agent.prompt.format(
        # Place any information in here that can be used to augment the ai's understanding of the situation.
    )

    augmented_prompt = f"""
    {agent_prompt}
    {user_info}
    {message_info}
    """

    await get_user_ai_base(user.id, agent.name).generate(
        prompt=augmented_prompt,
        tools=agent.tools,
    )


@app.post("/message", status_code=status.HTTP_202_ACCEPTED)
async def new_message(
        message_notification: MessageNotification,
        background_tasks: BackgroundTasks,
        db: Annotated[Session, Depends(get_db_session)]):
    """
    Handle a new message notification.
    This endpoint fetches agents subscribed to the specified channel and processes the message.
    """
    # Fetch agents that are subscribed to this channel
    agent_query = select(Agent).join(AgentSubscription).filter(AgentSubscription.channel == message_notification.channel)
    agents = db.execute(agent_query).scalars().all()
    user = db.execute(select(User).filter(User.id == message_notification.user_id)).scalar_one()

    if not agents:
        print("No agents found.")
        return []

    print(f"Found {len(agents)} agents.")
    print(f"Message: {message_notification.message}")
    # Process the message for each ai
    for agent in agents:
        if agent.name == message_notification.sender:
            continue
        print(f"{agent.name} informed of message.")
        # Add the task to background processing
        background_tasks.add_task(
            process_agent_message,
            message_notification,
            user,
            agent
        )

    return {"message": f"Message accepted. Processing for {len(agents)} ai(s) has been initiated."}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "everlight-agents"}