from api import agent_endpoint

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Everlight Agents Service")

# Configure CORS for communication with main backend
origins = [
    "http://localhost",
    "http://localhost:8000",  # Main backend
    "http://localhost:5173",  # Frontend
    "https://b5d2af84.everlight-97q.pages.dev/",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent_endpoint.router)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "everlight-agents"}