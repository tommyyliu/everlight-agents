# Everlight Agents Service

An independent AI agent service for the Everlight platform.

## Python and virtual environment (.venv)

To avoid confusion with system Python and ensure consistent dependencies, use a project-local virtual environment in .venv.

- Recommended Python: 3.13 (matches pyproject.toml). If 3.13 isn't available, use the closest available 3.x version, but prefer 3.13 for parity.

Create and activate .venv:
- macOS/Linux (using uv):
  - uv venv -p python3.13
  - source .venv/bin/activate
- macOS/Linux (standard venv):
  - python3 -m venv .venv
  - source .venv/bin/activate
- Windows (PowerShell):
  - py -3.13 -m venv .venv
  - .venv\Scripts\Activate.ps1

Once activated, your shell should show (.venv) as a prefix and python -V should reflect the venv Python.

## Overview

This service handles AI agent functionality including:
- Agent message processing
- Tool execution
- Agent subscriptions and channels
- Communication between agents

This service works in conjunction with the everlight-api service which handles CRUD operations and integrations.

## Setup

1. Create and activate the .venv (see section above).

2. Install dependencies:
```bash
uv pip install -r requirements.txt
# or, with pip:
pip install .
```

3. (Optional) Install test extras for running eval scenarios locally:
```bash
pip install .[test]
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your actual values
```

5. Run the service:
```bash
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

### Running Eforos eval scenarios

- List scenarios:
```bash
python evals/run_eforos_evals.py --list
```

- Run a single named scenario:
```bash
python evals/run_eforos_evals.py evolving_context_multi_step
# or via env var:
EVAL_SCENARIO=evolving_context_multi_step python evals/run_eforos_evals.py
```

Outputs are written under evals/out/<scenario_name> including config.json, prompts (when applicable), notes.json, and tool_calls.ndjson.

## API Endpoints

- `POST /message` - Process agent messages
- `GET /health` - Health check

## Architecture

The service is designed to be independent but communicates with the everlight-api service for CRUD operations and shares the same database for agent-specific data.