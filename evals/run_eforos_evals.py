import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
import click
from uuid import uuid4

import testing.postgresql
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.models import User, Agent, AgentSubscription, Note, Base

BASE_DIR = Path(__file__).resolve().parent
# Load .env from everlight-agents root to pick up API keys
load_dotenv(BASE_DIR.parent / ".env")
OUT_DIR = BASE_DIR / "out"


def ensure_out_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_scenarios() -> list[dict[str, Any]]:
    """Load scenarios from the legacy JSON file and from scenarios/*.json files.

    Returns a flat list of scenario dicts. Each JSON file can be either a dict (single scenario)
    or a list of dicts (multiple scenarios). Later entries with the same name override earlier ones.
    """
    scenarios: list[dict[str, Any]] = []

    # 1) Load the legacy consolidated file if present
    scenarios_path = BASE_DIR / "eforos_scenarios.json"
    if scenarios_path.exists():
        try:
            data = json.loads(scenarios_path.read_text())
            if isinstance(data, list):
                scenarios.extend([s for s in data if isinstance(s, dict)])
            elif isinstance(data, dict):
                scenarios.append(data)
        except Exception:
            # Best-effort: ignore malformed file
            pass

    # 2) Load individual scenario JSONs from scenarios/
    scenarios_dir = BASE_DIR / "scenarios"
    if scenarios_dir.exists():
        for p in sorted(scenarios_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text())
                if isinstance(data, list):
                    scenarios.extend([s for s in data if isinstance(s, dict)])
                elif isinstance(data, dict):
                    scenarios.append(data)
            except Exception:
                # Skip malformed files but continue
                continue

    # 3) De-duplicate by name, last one wins
    seen: dict[str, dict[str, Any]] = {}
    for sc in scenarios:
        name = sc.get("name") or f"scenario_{len(seen)+1}"
        seen[name] = sc

    return list(seen.values())


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
        "update_note",
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
        f"\nYour user is {user_email}. The current time is {datetime.now().isoformat()}.\n"
        f"You have tool-calling enabled. Do what you need to, then persist a clear note we can audit.\n"
    )
    message_info = (
        f"\nChannel: {channel}\n"
        f"Incoming message: {message}\n"
        f"Sender: eval_runner\n"
    )
    return f"{agent_prompt}\n{user_info}{message_info}"



async def run_scenario(db: Session, scenario: dict[str, Any]) -> dict[str, Any]:
    # Load prompt by name/path/default
    prompt_key, prompt_text = get_prompt_text(scenario)

    user, agent = create_user_and_agent(db, prompt_text)

    model = scenario.get("model") or os.getenv("GENKIT_MODEL")
    from ai.agent import get_user_ai_base
    ai = get_user_ai_base(user.id, agent.name, model=model, db_session=db)

    # Prepare a simple per-step message log in the output directory to verify processing coverage
    name = scenario.get("name") or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    # Run dir includes prompt key
    run_dir = OUT_DIR / name / prompt_key
    run_dir.mkdir(parents=True, exist_ok=True)
    step_log_path = run_dir / "steps.ndjson"
    def _log_step(step: str, message: str):
        try:
            with step_log_path.open("a") as f:
                f.write(json.dumps({
                    "timestamp": datetime.now().isoformat(),
                    "step": step,
                    "message": message,
                }) + "\n")
        except Exception:
            pass

    messages_sequence = scenario.get("messages_sequence")
    if messages_sequence:
        for idx, msg in enumerate(messages_sequence):
            os.environ["EVAL_STEP_INDEX"] = str(idx)
            _log_step(str(idx), msg)
            augmented_prompt = build_augmented_prompt(
                agent_prompt=agent.prompt,
                user_email=user.email,
                channel=scenario.get("channel", "raw_data_entries"),
                message=msg,
            )
            # Retry with simple exponential backoff to handle transient Genkit/HTTP errors or rate limits
            last_exc = None
            max_attempts = int(os.getenv("EVAL_MAX_ATTEMPTS", "3"))
            base_delay = float(os.getenv("EVAL_BASE_DELAY_SEC", "0.5"))
            for attempt in range(max_attempts):
                try:
                   if os.getenv("EVAL_DRY_RUN") == "1":
                       _log_step(str(idx), "DRY RUN: skipped model call")
                       last_exc = None
                       break
                   await ai.generate(prompt=augmented_prompt, tools=agent.tools)
                   last_exc = None
                   break
                except Exception as e:
                    last_exc = e
                    _log_step(str(idx), f"ERROR attempt {attempt+1}/{max_attempts}: {type(e).__name__}: {e}")
                    import traceback as _tb
                    cause = getattr(e, "__cause__", None)
                    context = getattr(e, "__context__", None)
                    with (run_dir / "errors.ndjson").open("a") as ef:
                        ef.write(json.dumps({
                            "timestamp": datetime.now().isoformat(),
                            "step": str(idx),
                            "attempt": attempt+1,
                            "error": str(e),
                            "type": type(e).__name__,
                            "cause": repr(cause) if cause else None,
                            "context": repr(context) if context else None,
                            "model": model,
                            "traceback": _tb.format_exc(),
                        }) + "\n")
                    # Backoff before retrying
                    await asyncio.sleep(base_delay * (2 ** attempt))
            if last_exc is not None:
                # Give up on this step after retries
                _log_step(str(idx), "FAILED after retries")
            # Optional pacing to reduce chance of rate limiting
            await asyncio.sleep(float(os.getenv("EVAL_STEP_DELAY_SEC", str(base_delay))))
    else:
        augmented_prompt = build_augmented_prompt(
            agent_prompt=agent.prompt,
            user_email=user.email,
            channel=scenario.get("channel", "raw_data_entries"),
            message=scenario.get("message", ""),
        )
        _log_step("single", augmented_prompt)
        try:
            if os.getenv("EVAL_DRY_RUN") == "1":
                _log_step("single", "DRY RUN: skipped model call")
            else:
                await ai.generate(prompt=augmented_prompt, tools=agent.tools)
        except Exception as e:
            # Log exception details by step
            err = {
                "timestamp": datetime.now().isoformat(),
                "step": os.getenv("EVAL_STEP_INDEX"),
                "error": str(e),
                "type": type(e).__name__,
            }
            with (run_dir / "errors.ndjson").open("a") as ef:
                ef.write(json.dumps(err) + "\n")


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


def get_prompt_text(scenario: dict[str, Any]) -> tuple[str, str]:
    # priority: scenario.prompt_name -> scenario.prompt_path -> default
    prompt_name = scenario.get("prompt_name")
    prompt_path = scenario.get("prompt_path")
    if prompt_name:
        # map to evals/prompts/<prompt_name>.md
        path = OUT_DIR.parent / "prompts" / f"{prompt_name}.md"
        if path.exists():
            return prompt_name, path.read_text()
        else:
            # fallback to ai/default_prompts
            fallback = Path("ai/default_prompts") / f"{prompt_name}.md"
            if fallback.exists():
                return prompt_name, fallback.read_text()
    if prompt_path:
        return Path(prompt_path).stem, read_text_file(prompt_path)
    # default minimal prompt
    return "initial_test_eforos", read_text_file("evals/prompts/initial_test_eforos.md")


def save_result(name: str, prompt_key: str, result: dict[str, Any]) -> None:
    # Organize as out/<scenario_name>/<prompt_key>/
    run_dir = OUT_DIR / name / prompt_key
    run_dir.mkdir(parents=True, exist_ok=True)

    with (run_dir / "config.json").open("w") as f:
        json.dump({"scenario": result["scenario"], "timestamp": result["timestamp"]}, f, indent=2)

    # Save prompt only for single-message scenarios
    if result.get("augmented_prompt") is not None:
        with (run_dir / "prompt.txt").open("w") as f:
            f.write(result["augmented_prompt"])

    with (run_dir / "notes.json").open("w") as f:
        json.dump(result["notes"], f, indent=2)

    # Copy tool call log if present
    log_path = os.getenv("EVAL_TOOL_LOG_PATH")
    if log_path and Path(log_path).exists():
        src = Path(log_path)
        dst = run_dir / "tool_calls.ndjson"
        if src.resolve() != dst.resolve():
            dst.write_text(src.read_text())
        else:
            # already at destination, do nothing
            pass
        # Clean up tmp tool log if it has our tmp prefix
        if src.name.startswith("tmp_rovodev_") and src.exists():
            try:
                src.unlink()
            except Exception:
                pass


@click.group()
def cli() -> None:
    """Eforos evals CLI"""
    pass


@cli.command(name="list")
def list_cmd() -> None:
    """List available scenarios."""
    ensure_out_dir()
    scenarios = load_scenarios()
    click.echo("Available scenarios:")
    for sc in scenarios:
        click.echo(f"- {sc.get('name')}")


@cli.command(name="run")
@click.option("--name", "selected_name", help="Run only this scenario by name.")
@click.option("--model", default=None, help="Override model id for the run (fallback to GENKIT_MODEL).")
@click.option("--prompt", "prompt_name", default=None, help="Override prompt name (maps to evals/prompts/<name>.md or ai/default_prompts/<name>.md).")
@click.option("--step-delay", type=float, default=None, help="Override per-step delay seconds (EVAL_STEP_DELAY_SEC).")
@click.option("--max-attempts", type=int, default=None, help="Override max attempts per step (EVAL_MAX_ATTEMPTS).")
@click.option("--base-delay", type=float, default=None, help="Override base delay for backoff (EVAL_BASE_DELAY_SEC).")
@click.option("--timeout", "gen_timeout", type=float, default=None, help="Per-generate timeout seconds (EVAL_GENERATE_TIMEOUT_SEC).")
@click.option("--dry-run", is_flag=True, default=False, help="Do not call the model; only write prompts/logs.")
def run_cmd(selected_name: str | None, model: str | None, prompt_name: str | None, step_delay: float | None, max_attempts: int | None, base_delay: float | None, gen_timeout: float | None, dry_run: bool) -> None:
    """Run scenarios. By default, runs all discovered scenarios."""
    ensure_out_dir()

    # Environment overrides for runtime behavior
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

    # Optional prompt override: apply to each scenario
    if prompt_name:
        for sc in scenarios:
            sc["prompt_name"] = prompt_name

    # Filter by name if provided (fallback to env var EVAL_SCENARIO for backward compatibility)
    selected_name = selected_name or os.getenv("EVAL_SCENARIO")
    if selected_name:
        scenarios = [s for s in scenarios if s.get("name") == selected_name]
        if not scenarios:
            click.echo(f"No scenario found with name '{selected_name}'.", err=True)
            raise SystemExit(1)

    with testing.postgresql.Postgresql() as postgresql:
        url = postgresql.url()
        os.environ["TESTING"] = "1"
        os.environ["DATABASE_URL"] = url

        # Use NullPool to avoid pool cleanup rollback calls during ephemeral DB shutdown
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
            name = scenario.get("name") or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            # Set per-run tool log file under <scenario>/<prompt>
            prompt_key, _ = get_prompt_text(scenario)
            tool_log = OUT_DIR / name / prompt_key / "tool_calls.ndjson"
            os.environ["EVAL_TOOL_LOG_PATH"] = str(tool_log)
            # Ensure parent dirs exist for the log
            (OUT_DIR / name / prompt_key).mkdir(parents=True, exist_ok=True)
            # Clear any existing log file
            if tool_log.exists():
                tool_log.unlink()

            result = asyncio.run(run_scenario(db, scenario))
            save_result(name, prompt_key, result)


if __name__ == "__main__":
    cli()
