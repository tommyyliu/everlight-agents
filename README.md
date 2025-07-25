# Everlight Agents Service

An independent AI agent service for the Everlight platform.

## Overview

This service handles all AI agent functionality including:
- Agent message processing
- Tool execution
- Agent subscriptions and channels
- Communication between agents

## Setup

1. Install dependencies:
```bash
uv pip install -r requirements.txt
```

2. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your actual values
```

3. Run the service:
```bash
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

## API Endpoints

- `POST /agent/message` - Process agent messages
- `GET /health` - Health check

## Architecture

The service is designed to be independent but communicates with the main Everlight backend through HTTP APIs and shares the same database.