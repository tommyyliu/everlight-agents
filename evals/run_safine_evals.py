import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import click
import numpy as np
import testing.postgresql
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from sqlalchemy import create_engine, text, select, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool
from uuid import uuid4

# Ensure repo root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.models import (
    Base,
    User,
    Agent,
    AgentSubscription,
    Note,
    RawEntry,
    Slate,
    ChatMessage,
    Conversation,
)

BASE_DIR = Path(__file__).resolve().parent
# Load .env from repo root (if present)
load_dotenv(BASE_DIR.parent / ".env")
OUT_DIR = BASE_DIR / "out"


# --------------------------
# Helpers
# --------------------------


def ensure_out_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def read_text_file(path: str) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.read_text()


def load_scenarios() -> list[dict[str, Any]]:
    """Load scenarios from safine-specific file and from scenarios/*.json.

    Returns merged list where last scenario with same name wins.
    """
    scenarios: list[dict[str, Any]] = []

    # 1) safine_scenarios.json (optional)
    safine_path = BASE_DIR / "safine_scenarios.json"
    if safine_path.exists():
        try:
            data = json.loads(safine_path.read_text())
            if isinstance(data, list):
                scenarios.extend([s for s in data if isinstance(s, dict)])
            elif isinstance(data, dict):
                scenarios.append(data)
        except Exception:
            pass

    # 2) scenarios/safine/*.json
    scenarios_dir = BASE_DIR / "scenarios" / "safine"
    if scenarios_dir.exists():
        for p in sorted(scenarios_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text())
                if isinstance(data, list):
                    scenarios.extend([s for s in data if isinstance(s, dict)])
                elif isinstance(data, dict):
                    scenarios.append(data)
            except Exception:
                continue

    # 3) Deduplicate by name
    seen: dict[str, dict[str, Any]] = {}
    for sc in scenarios:
        name = sc.get("name") or f"scenario_{len(seen)+1}"
        seen[name] = sc

    # Optionally filter to Safine-only scenarios (have mode or prompt_name == 'safine')
    result = []
    for sc in seen.values():
        if sc.get("prompt_name") == "safine" or sc.get("mode") in (
            "incoming_message",
            "self_scheduled",
        ):
            result.append(sc)
    return result


def get_prompt_text(scenario: dict[str, Any]) -> tuple[str, str]:
    """Resolve prompt text by name/path, default to safine.md."""
    prompt_name = scenario.get("prompt_name")
    prompt_path = scenario.get("prompt_path")
    if prompt_name:
        path = OUT_DIR.parent / "prompts" / f"{prompt_name}.md"
        if path.exists():
            return prompt_name, path.read_text()
        fallback = Path("ai/default_prompts") / f"{prompt_name}.md"
        if fallback.exists():
            return prompt_name, fallback.read_text()
    if prompt_path:
        return Path(prompt_path).stem, read_text_file(prompt_path)
    # default prompt
    return "safine", read_text_file("ai/default_prompts/safine.md")


# --------------------------
# DB seeding
# --------------------------


def _zeros_vec(dim: int = 3072) -> np.ndarray:
    return np.zeros(dim, dtype=np.float16)


def create_user_and_agents(
    db: Session, safine_prompt: str, eforos_prompt: Optional[str] = None
) -> tuple[User, Agent, Agent]:
    """Create a user plus Safine and Eforos agents.

    Returns (user, safine, eforos).
    """
    user = User(
        id=uuid4(), email=f"eval+{uuid4()}@example.com", firebase_user_id=str(uuid4())
    )
    db.add(user)
    db.commit()

    common_tools = [
        "send_message_tool",
        "create_note",
        "update_note",
        "search_notes",
        "get_note_titles",
        "search_raw_entries",
        "get_recent_raw_entries",
        "schedule_message",
    ]

    safine_tools = common_tools + [
        "get_current_time",
        "get_hourly_weather",
        "read_slate",
        "update_slate",
    ]

    safine = Agent(
        user_id=user.id, name="Safine", prompt=safine_prompt, tools=safine_tools
    )
    db.add(safine)

    if eforos_prompt is None:
        try:
            eforos_prompt = read_text_file("ai/default_prompts/eforos.md")
        except Exception:
            eforos_prompt = "You are Eforos."

    eforos = Agent(
        user_id=user.id, name="Eforos", prompt=eforos_prompt, tools=common_tools
    )
    db.add(eforos)
    db.commit()

    # Private channels
    db.add_all(
        [
            AgentSubscription(agent_id=safine.id, channel="safine"),
            AgentSubscription(agent_id=eforos.id, channel="eforos"),
        ]
    )
    db.commit()

    # Create an initial Slate row for the user if needed (empty)
    if not db.query(Slate).filter(Slate.user_id == user.id).first():
        db.add(Slate(user_id=user.id, content=""))
        db.commit()

    return user, safine, eforos


def seed_from_scenario(
    db: Session, user: User, safine: Agent, eforos: Agent, scenario: dict[str, Any]
) -> None:
    """Seed notes, raw entries, and initial slate based on scenario."""
    # Notes
    for n in scenario.get("seed_notes", []) or []:
        owner_name = (n.get("owner") or "Eforos").strip()
        owner = eforos if owner_name.lower() == "eforos" else safine
        db.add(
            Note(
                user_id=user.id,
                owner=owner.id,
                title=n.get("title", "Untitled"),
                content=n.get("content", ""),
                embedding=_zeros_vec(),
            )
        )
    db.commit()

    # Raw entries
    for r in scenario.get("seed_raw_entries", []) or []:
        db.add(
            RawEntry(
                user_id=user.id,
                source=r.get("source", "unspecified"),
                content=r.get("content", {}),
                embedding=_zeros_vec(),
            )
        )
    db.commit()

    # Initial slate
    initial_slate = scenario.get("initial_slate")
    if initial_slate is not None:
        slate = db.query(Slate).filter(Slate.user_id == user.id).first()
        if slate:
            slate.content = initial_slate
        else:
            db.add(Slate(user_id=user.id, content=initial_slate))
        db.commit()


# --------------------------
# Prompt building
# --------------------------


def build_augmented_prompt(
    agent_prompt: str,
    user_email: str,
    scenario: dict[str, Any],
    message: Optional[str] = None,
) -> str:
    now = datetime.now().isoformat()
    header = (
        f"\nYour user is {user_email}. The current time is {now}.\n"
        f"You have tool-calling enabled. You can update the Living Slate with HTML and schedule future tasks.\n"
    )

    mode = scenario.get("mode", "incoming_message")

    if mode == "incoming_message":
        channel = scenario.get("channel", "safine")
        sender = scenario.get("sender", "Eforos")
        message_info = (
            f"\nMode: incoming_message\n"
            f"Channel: {channel}\n"
            f"Sender: {sender}\n"
            f"Incoming message: {message or scenario.get('message', '')}\n"
        )
        return f"{agent_prompt}\n{header}{message_info}"

    elif mode == "self_scheduled":
        at = scenario.get("run_context_time") or now
        directive = scenario.get("brief_directive", "Prepare a concise morning brief.")
        info = (
            f"\nMode: self_scheduled\n"
            f"It is {at}. You decided to prepare: {directive}\n"
            f"Use the notes and recent raw entries as needed. Keep it tactful and concise.\n"
        )
        return f"{agent_prompt}\n{header}{info}"

    else:
        # Fallback to simple
        return f"{agent_prompt}\n{header}\nIncoming message: {message or scenario.get('message', '')}\n"


# --------------------------
# Scenario execution
# --------------------------


async def run_scenario(db: Session, scenario: dict[str, Any]) -> dict[str, Any]:
    prompt_key, safine_prompt = get_prompt_text(scenario)

    # Create user and agents
    user, safine, eforos = create_user_and_agents(db, safine_prompt)

    # Seed environment
    seed_from_scenario(db, user, safine, eforos, scenario)

    # Create agent instance bound to this DB session
    model = scenario.get("model") or os.getenv("GENKIT_MODEL")
    from ai.agent import get_user_ai_base

    ai = get_user_ai_base(user.id, "Safine", model=model, db_session=db)

    # Setup output dir
    name = scenario.get("name") or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir = OUT_DIR / name / prompt_key
    run_dir.mkdir(parents=True, exist_ok=True)
    step_log_path = run_dir / "steps.ndjson"

    def _log_step(step: str, message: str):
        try:
            with step_log_path.open("a") as f:
                f.write(
                    json.dumps(
                        {
                            "timestamp": datetime.now().isoformat(),
                            "step": step,
                            "message": message,
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass

    augmented_prompt: Optional[str] = None

    messages_sequence = scenario.get("messages_sequence")
    if messages_sequence:
        for idx, msg in enumerate(messages_sequence):
            os.environ["EVAL_STEP_INDEX"] = str(idx)
            _log_step(str(idx), msg)
            ap = build_augmented_prompt(
                safine_prompt, user.email, scenario, message=msg
            )
            # backoff
            last_exc = None
            max_attempts = int(os.getenv("EVAL_MAX_ATTEMPTS", "3"))
            base_delay = float(os.getenv("EVAL_BASE_DELAY_SEC", "0.5"))
            for attempt in range(max_attempts):
                try:
                    if os.getenv("EVAL_DRY_RUN") == "1":
                        _log_step(str(idx), "DRY RUN: skipped model call")
                        last_exc = None
                        break
                    await ai.generate(prompt=ap, tools=safine.tools)
                    last_exc = None
                    break
                except Exception as e:
                    last_exc = e
                    _log_step(
                        str(idx),
                        f"ERROR attempt {attempt+1}/{max_attempts}: {type(e).__name__}: {e}",
                    )
                    await asyncio.sleep(base_delay * (2**attempt))
            if last_exc is not None:
                _log_step(str(idx), "FAILED after retries")
            await asyncio.sleep(
                float(os.getenv("EVAL_STEP_DELAY_SEC", str(base_delay)))
            )
    else:
        augmented_prompt = build_augmented_prompt(safine_prompt, user.email, scenario)
        _log_step("single", augmented_prompt)
        try:
            if os.getenv("EVAL_DRY_RUN") == "1":
                _log_step("single", "DRY RUN: skipped model call")
            else:
                await ai.generate(prompt=augmented_prompt, tools=safine.tools)
        except Exception as e:
            with (run_dir / "errors.ndjson").open("a") as ef:
                ef.write(
                    json.dumps(
                        {
                            "timestamp": datetime.now().isoformat(),
                            "step": os.getenv("EVAL_STEP_INDEX"),
                            "error": str(e),
                            "type": type(e).__name__,
                        }
                    )
                    + "\n"
                )

    # Collect outputs
    # Notes by Safine
    notes = (
        db.query(Note)
        .filter(Note.user_id == user.id, Note.owner == safine.id)
        .order_by(Note.created_at.asc())
        .all()
    )
    notes_dump = [
        {
            "id": str(n.id),
            "title": n.title,
            "content": n.content,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notes
    ]

    # Slate
    slate = db.execute(select(Slate).where(Slate.user_id == user.id)).scalars().first()
    slate_content = slate.content if slate else ""

    # Chat messages by Safine (optional; may be empty if chat tools not used)
    chat_msgs = (
        db.query(ChatMessage, Conversation)
        .join(Conversation, ChatMessage.conversation_id == Conversation.id)
        .filter(ChatMessage.sender_agent_id == safine.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    chat_dump = [
        {
            "at": m.created_at.isoformat() if m.created_at else None,
            "content": m.content,
            "conversation": c.name,
        }
        for (m, c) in chat_msgs
    ]

    return {
        "scenario": scenario,
        "prompt_used": safine_prompt,
        "augmented_prompt": augmented_prompt,
        "notes": notes_dump,
        "slate": slate_content,
        "chat_messages": chat_dump,
        "timestamp": datetime.now().isoformat(),
    }


def save_result(name: str, prompt_key: str, result: dict[str, Any]) -> None:
    run_dir = OUT_DIR / name / prompt_key
    run_dir.mkdir(parents=True, exist_ok=True)

    with (run_dir / "config.json").open("w") as f:
        json.dump(
            {"scenario": result["scenario"], "timestamp": result["timestamp"]},
            f,
            indent=2,
        )

    if result.get("augmented_prompt") is not None:
        with (run_dir / "prompt.txt").open("w") as f:
            f.write(result["augmented_prompt"])  # type: ignore[arg-type]

    with (run_dir / "notes.json").open("w") as f:
        json.dump(result["notes"], f, indent=2)

    # slate.html
    with (run_dir / "slate.html").open("w") as f:
        f.write(result.get("slate", ""))

    # chat messages
    with (run_dir / "chat_messages.json").open("w") as f:
        json.dump(result.get("chat_messages", []), f, indent=2)

    # Copy tool call log if present
    log_path = os.getenv("EVAL_TOOL_LOG_PATH")
    if log_path and Path(log_path).exists():
        src = Path(log_path)
        dst = run_dir / "tool_calls.ndjson"
        if src.resolve() != dst.resolve():
            dst.write_text(src.read_text())
        # Clean up tmp tool log if created with tmp prefix
        if src.name.startswith("tmp_rovodev_") and src.exists():
            try:
                src.unlink()
            except Exception:
                pass


# --------------------------
# CLI
# --------------------------


@click.group()
def cli() -> None:
    """Safine evals CLI"""
    pass


@cli.command(name="list")
def list_cmd() -> None:
    ensure_out_dir()
    scenarios = load_scenarios()
    click.echo("Available Safine scenarios:")
    for sc in scenarios:
        click.echo(f"- {sc.get('name')}")


@cli.command(name="run")
@click.option("--name", "selected_name", help="Run only this scenario by name.")
@click.option(
    "--model", default=None, help="Override model id (fallback to GENKIT_MODEL)."
)
@click.option(
    "--prompt",
    "prompt_name",
    default=None,
    help="Override prompt name (maps to evals/prompts/<name>.md or ai/default_prompts/<name>.md).",
)
@click.option(
    "--step-delay",
    type=float,
    default=None,
    help="Override per-step delay seconds (EVAL_STEP_DELAY_SEC).",
)
@click.option(
    "--max-attempts",
    type=int,
    default=None,
    help="Override max attempts per step (EVAL_MAX_ATTEMPTS).",
)
@click.option(
    "--base-delay",
    type=float,
    default=None,
    help="Override base delay for backoff (EVAL_BASE_DELAY_SEC).",
)
@click.option(
    "--timeout",
    "gen_timeout",
    type=float,
    default=None,
    help="Per-generate timeout seconds (EVAL_GENERATE_TIMEOUT_SEC).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Do not call the model; only write prompts/logs.",
)
def run_cmd(
    selected_name: Optional[str],
    model: Optional[str],
    prompt_name: Optional[str],
    step_delay: Optional[float],
    max_attempts: Optional[int],
    base_delay: Optional[float],
    gen_timeout: Optional[float],
    dry_run: bool,
) -> None:
    ensure_out_dir()

    # Env overrides
    if model:
        os.environ["GENKIT_MODEL"] = model
    if step_delay is not None:
        os.environ["EVAL_STEP_DELAY_SEC"] = str(step_delay)
    if max_attempts is not None:
        os.environ["EVAL_MAX_ATTEMPTS"] = str(max_attempts)
    if base_delay is not None:
        os.environ["EVAL_BASE_DELAY_SEC"] = str(base_delay)
    if gen_timeout is not None:
        os.environ["EVAL_GENERATE_TIMEOUT_SEC"] = str(gen_timeout)
    if dry_run:
        os.environ["EVAL_DRY_RUN"] = "1"

    scenarios = load_scenarios()

    if prompt_name:
        for sc in scenarios:
            sc["prompt_name"] = prompt_name

    if selected_name:
        scenarios = [s for s in scenarios if s.get("name") == selected_name]
        if not scenarios:
            click.echo(f"No scenario found with name '{selected_name}'.", err=True)
            raise SystemExit(1)

    # Ephemeral DB
    with testing.postgresql.Postgresql() as postgresql:
        url = postgresql.url()
        os.environ["TESTING"] = "1"
        os.environ["DATABASE_URL"] = url

        engine = create_engine(
            url.replace("postgresql://", "postgresql+psycopg://"),
            poolclass=NullPool,
            pool_reset_on_return=None,
        )
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.commit()

        @event.listens_for(engine, "connect")
        def connect(dbapi_connection, connection_record):
            register_vector(dbapi_connection)

        Base.metadata.create_all(engine)

        SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        db = SessionLocal()

        for scenario in scenarios:
            name = (
                scenario.get("name")
                or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            prompt_key, _ = get_prompt_text(scenario)

            # Configure tool call log path per scenario
            tool_log = OUT_DIR / name / prompt_key / "tool_calls.ndjson"
            os.environ["EVAL_TOOL_LOG_PATH"] = str(tool_log)
            (OUT_DIR / name / prompt_key).mkdir(parents=True, exist_ok=True)
            if tool_log.exists():
                tool_log.unlink()

            result = asyncio.run(run_scenario(db, scenario))
            save_result(name, prompt_key, result)


if __name__ == "__main__":
    cli()
