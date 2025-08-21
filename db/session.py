import os

from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool.impl import NullPool

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError(
        "The DATABASE_URL environment variable is not set. "
        "Please ensure it is defined in a .env file in the project root."
    )


def get_db_session():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError(
            "The DATABASE_URL environment variable is not set. "
            "Please ensure it is defined in a .env file in the project root."
        )

    if os.getenv("TESTING"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://")

    engine = create_engine(
        db_url, connect_args={"prepare_threshold": None}, poolclass=NullPool
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    @event.listens_for(engine, "connect")
    def connect(dbapi_connection, connection_record):
        register_vector(dbapi_connection)

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
