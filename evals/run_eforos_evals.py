import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import testing.postgresql
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import Session, sessionmaker

from db.models import User, Agent, AgentSubscription, Note, Base

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "out"


def ensure_out_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_scenarios() -> list[dict[str, Any]]:
    scenarios_path = BASE_DIR / "eforos_scenarios.json"
    with scenarios_path.open("r") as f:
        return json.load(f)


def read_text_file(path: str) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.read_text()


def create_user_and_agent(db: Session, prompt: str) -> tuple[User, Agent]:
    user = User(id=uuid4(), email=f"eval+{uuid4()}@example.com", firebase_user_id=str(uuid4()))
    db.add(user)
    db.commit()

    common_tools = [
        "send_message_tool",
        "create_note",
        "search_notes",
        "get_note_titles",
        "search_raw_entries",
        "get_recent_raw_entries",
        "schedule_message",
    ]

    agent = Agent(
        user_id=user.id,
        name="Eforos",
        prompt=prompt,
        tools=common_tools,
    )
    db.add(agent)
    db.commit()

    sub = AgentSubscription(agent_id=agent.id, channel="raw_data_entries")
    db.add(sub)
    db.commit()

    return user, agent


def build_augmented_prompt(agent_prompt: str, user_email: str, channel: str, message: str) -> str:
    user_info = (
        f"\n    Your user is {user_email}. The current time is {datetime.now()}.\n"
        f"    Currently, we're just testing the code to give you tool calling functionality.\n"
        f"    Try to just do everything that you think you need to do. Then, just log it all into a note, so that we can inspect\n"
        f"    how you're doing.\n"
    )
    message_info = (
        f"\n    On channel {channel},\n"
        f"    An ai or process has sent a message: {message}.\n"
        f"    The sender is eval_runner.\n"
    )
    return f"\n    {agent_prompt}\n    {user_info}\n    {message_info}\n    "


async def run_scenario(db: Session, scenario: dict[str, Any]) -> dict[str, Any]:
    prompt_path = scenario.get("prompt_path")
    prompt_text = read_text_file(prompt_path) if prompt_path else "You are Eforos."

    user, agent = create_user_and_agent(db, prompt_text)

    model = scenario.get("model") or os.getenv("GENKIT_MODEL")
    from ai.agent import get_user_ai_base
    ai = get_user_ai_base(user.id, agent.name, model=model)

    messages_sequence = scenario.get("messages_sequence")
    if messages_sequence:
        for idx, msg in enumerate(messages_sequence):
            os.environ["EVAL_STEP_INDEX"] = str(idx)
            augmented_prompt = build_augmented_prompt(
                agent_prompt=agent.prompt,
                user_email=user.email,
                channel=scenario.get("channel", "raw_data_entries"),
                message=msg,
            )
            try:
                await ai.generate(prompt=augmented_prompt, tools=agent.tools)
            except Exception:
                pass
    else:
        augmented_prompt = build_augmented_prompt(
            agent_prompt=agent.prompt,
            user_email=user.email,
            channel=scenario.get("channel", "raw_data_entries"),
            message=scenario.get("message", ""),
        )
        try:
            await ai.generate(prompt=augmented_prompt, tools=agent.tools)
        except Exception:
            pass

    notes = db.query(Note).filter(Note.user_id == user.id, Note.owner == agent.id).order_by(Note.created_at.asc()).all()
    notes_dump = [
        {
            "id": str(n.id),
            "title": n.title,
            "content": n.content,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notes
    ]

    return {
        "scenario": scenario,
        "prompt_used": prompt_text,
        "augmented_prompt": augmented_prompt if not messages_sequence else None,
        "notes": notes_dump,
        "timestamp": datetime.now().isoformat(),
    }


def save_result(name: str, result: dict[str, Any]) -> None:
    run_dir = OUT_DIR / name
    run_dir.mkdir(parents=True, exist_ok=True)

    with (run_dir / "config.json").open("w") as f:
        json.dump({"scenario": result["scenario"], "timestamp": result["timestamp"]}, f, indent=2)

    with (run_dir / "prompt.txt").open("w") as f:
        f.write(result["augmented_prompt"])

    with (run_dir / "notes.json").open("w") as f:
        json.dump(result["notes"], f, indent=2)

    # Copy tool call log if present
    log_path = os.getenv("EVAL_TOOL_LOG_PATH")
    if log_path and Path(log_path).exists():
        with open(log_path, "r") as lf, (run_dir / "tool_calls.ndjson").open("w") as out:
            out.write(lf.read())


def main() -> None:
    ensure_out_dir()
    scenarios = load_scenarios()

    with testing.postgresql.Postgresql() as postgresql:
        url = postgresql.url()
        os.environ["TESTING"] = "1"
        os.environ["DATABASE_URL"] = url

        engine = create_engine(url.replace("postgresql://", "postgresql+psycopg://"))
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.commit()

        @event.listens_for(engine, "connect")
        def connect(dbapi_connection, connection_record):
            register_vector(dbapi_connection)

        Base.metadata.create_all(engine)

        SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        db = SessionLocal()
        try:
            for scenario in scenarios:
                name = scenario.get("name") or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                # Set per-run tool log file
                tool_log = OUT_DIR / name / "tool_calls.ndjson"
                os.environ["EVAL_TOOL_LOG_PATH"] = str(tool_log)
                # Ensure parent dir exists for the log
                (OUT_DIR / name).mkdir(parents=True, exist_ok=True)
                # Clear any existing log file
                if tool_log.exists():
                    tool_log.unlink()

                result = asyncio.run(run_scenario(db, scenario))
                save_result(name, result)
        finally:
            db.close()


if __name__ == "__main__":
    main()
