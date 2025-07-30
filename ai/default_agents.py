from pathlib import Path
from sqlalchemy.orm import Session

from db.models import User, Agent, AgentSubscription

# Define a base path to locate the document files robustly
# This assumes the script is run from the project root or that the path is adjusted accordingly.
DOCS_PATH = Path(__file__).parent / "default_prompts"

def _read_prompt_file(agent_name: str) -> str:
    """Helper function to read the prompt content for a given agent."""
    file_path = DOCS_PATH / "agents" / f"{agent_name.lower()}.md"
    if not file_path.exists():
        # Fallback to a default prompt if the file is missing
        return f"You are the agent known as {agent_name}."
    return file_path.read_text()

def create_default_agents_for_user(db: Session, user: User):
    """
    Creates and configures the default agents (Eforos and Safine) for a new user.

    This function is designed to be called once upon user creation. It performs the
    following actions in a single database transaction:
    1. Creates the 'Eforos' agent with its specific prompt and tools.
    2. Creates the 'Safine' agent with her specific prompt and tools.
    3. Subscribes Eforos to the 'journal_entry_created' channel.
    4. Subscribes Safine to the 'eforos_insight_ready' channel.

    Args:
        db: The SQLAlchemy database session.
        user: The newly created User object.
    """
    print(f"Creating default agents for user {user.email} ({user.id})")

    common_tools = [
        "send_message_tool", 
        "create_note", 
        "search_notes", 
        "get_note_titles", 
        "search_raw_entries", 
        "get_recent_raw_entries",
        "schedule_message"
    ]

    # 1. Define and create Eforos, the Information Guardian
    eforos_agent = Agent(
        user_id=user.id,
        name="Eforos",
        prompt=_read_prompt_file("eforos"),
        # Eforos needs to process info, manage summaries, and talk to Safine
        tools=common_tools
    )

    # 2. Define and create Safine, the Focus Curator
    safine_agent = Agent(
        user_id=user.id,
        name="Safine",
        prompt=_read_prompt_file("safine"),
        # Safine needs to manage her own state and get context
        tools=common_tools + ["get_current_time", "get_hourly_weather", "read_slate", "update_slate"]
    )

    # Add the agents to the session
    db.add(eforos_agent)
    db.add(safine_agent)

    # We must flush the session to get the generated agent IDs
    # This sends the INSERT statements to the DB without committing the transaction.
    db.flush()

    # 3. Subscribe Eforos to be notified when a new journal entry is created
    eforos_subscription = AgentSubscription(
        agent_id=eforos_agent.id,
        channel="raw_data_entries"
    )

    # 4. Subscribe Safine to be notified when Eforos has a new insight
    safine_subscription = AgentSubscription(
        agent_id=safine_agent.id,
        channel="safine"
    )

    db.add(eforos_subscription)
    db.add(safine_subscription)

    # The final commit saves all agents and subscriptions atomically
    db.commit()
    print(f"Successfully created and subscribed default agents for user {user.email}.")


if __name__ == "__main__":
    from db.session import SessionLocal
    with SessionLocal() as db:
        # Select user b2bf2caf-f9af-411a-bef6-d9b8383a06e0
        user = db.query(User).filter(User.id == "b2bf2caf-f9af-411a-bef6-d9b8383a06e0").first()
        if user:
            create_default_agents_for_user(db, user)
        else:
            print("User not found.")
