"""
Test configuration and fixtures for AI agent tools using real PostgreSQL database.
"""

import os
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import numpy as np
import pytest
import testing.postgresql

# Suppress logfire warnings during testing
os.environ["LOGFIRE_IGNORE_NO_CONFIG"] = "1"

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from pgvector.psycopg import register_vector
from sqlalchemy import event

from ai.tools import AgentContext
from db.models import Base, User, Agent, Slate, Note, RawEntry


# Use a different database for each test worker if running in parallel
@pytest.fixture(scope="session")
def postgresql_proc():
    """Create a PostgreSQL process for testing"""
    with testing.postgresql.Postgresql() as postgresql:
        yield postgresql


@pytest.fixture(scope="session")
def database_url(postgresql_proc):
    """Get database URL for the test PostgreSQL instance"""
    # Use psycopg (v3) instead of psycopg2
    url = postgresql_proc.url()
    return url.replace("postgresql://", "postgresql+psycopg://")


@pytest.fixture(scope="session")
def engine(database_url):
    """Create SQLAlchemy engine for testing"""
    engine = create_engine(database_url, echo=False)

    # Install pgvector extension first
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    # Register pgvector on connection after extension is installed
    @event.listens_for(engine, "connect")
    def connect(dbapi_connection, connection_record):
        register_vector(dbapi_connection)

    # Create all tables
    Base.metadata.create_all(engine)

    yield engine

    # Cleanup
    Base.metadata.drop_all(engine)


@pytest.fixture
def db_session(engine):
    """Create a database session for testing"""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    # Start a transaction
    connection = engine.connect()
    transaction = connection.begin()

    # Bind session to the transaction
    session.bind = connection

    yield session

    # Rollback transaction and close
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def sample_user_id():
    """Sample user ID for testing"""
    return UUID("123e4567-e89b-12d3-a456-426614174000")


@pytest.fixture
def sample_agent_name():
    """Sample agent name for testing"""
    return "test_agent"


@pytest.fixture
def test_user(db_session, sample_user_id):
    """Create a test user in the database"""
    user = User(
        id=sample_user_id, firebase_user_id="test_firebase_id", email="test@example.com"
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_agent(db_session, test_user, sample_agent_name):
    """Create a test agent in the database"""
    agent = Agent(
        user_id=test_user.id,
        name=sample_agent_name,
        prompt="Test agent prompt for testing purposes",
        tools=["test_tool", "another_tool"],
    )
    db_session.add(agent)
    db_session.commit()
    return agent


@pytest.fixture
def agent_context(sample_user_id, sample_agent_name):
    """Create a test agent context"""
    return AgentContext(user_id=sample_user_id, agent_name=sample_agent_name)


@pytest.fixture
def run_context(agent_context):
    """Create RunContext with agent dependencies"""
    context = Mock()
    context.deps = agent_context
    return context


@pytest.fixture
def mock_get_db_session(db_session):
    """Mock get_db_session to return our test database session"""
    with patch("ai.tools.slate.get_db_session") as mock_func:
        mock_func.return_value.__next__ = Mock(return_value=db_session)
        yield mock_func


@pytest.fixture
def mock_get_db_session_notes(db_session):
    """Mock get_db_session for notes tools"""
    with patch("ai.tools.notes.get_db_session") as mock_func:
        mock_func.return_value.__next__ = Mock(return_value=db_session)
        yield mock_func


@pytest.fixture
def mock_get_db_session_data(db_session):
    """Mock get_db_session for data tools"""
    with patch("ai.tools.data.get_db_session") as mock_func:
        mock_func.return_value.__next__ = Mock(return_value=db_session)
        yield mock_func


@pytest.fixture
def mock_logfire():
    """Mock logfire for testing - simplified approach"""
    mock = Mock()

    # Create a context manager mock for span
    span_mock = Mock()
    span_mock.__enter__ = Mock(return_value=span_mock)
    span_mock.__exit__ = Mock(return_value=None)
    mock.span.return_value = span_mock
    mock.info = Mock()
    mock.error = Mock()

    # Patch all the modules that import logfire
    patches = [
        patch("ai.tools.slate.logfire", mock),
        patch("ai.tools.notes.logfire", mock),
        patch("ai.tools.data.logfire", mock),
        patch("ai.tools.utilities.logfire", mock),
    ]

    for p in patches:
        p.start()

    yield mock

    for p in patches:
        p.stop()


@pytest.fixture
def mock_log_tool_call():
    """Mock the log_tool_call function"""
    mock = Mock()

    patches = [
        patch("ai.tools.slate.log_tool_call", mock),
        patch("ai.tools.notes.log_tool_call", mock),
        patch("ai.tools.data.log_tool_call", mock),
        patch("ai.tools.utilities.log_tool_call", mock),
    ]

    for p in patches:
        p.start()

    yield mock

    for p in patches:
        p.stop()


@pytest.fixture
def mock_embed_document():
    """Mock embedding document function"""
    with patch("ai.tools.notes.embed_document") as mock:
        # Return a realistic embedding vector (3072 dimensions for HALFVEC)
        mock.return_value = np.random.rand(3072).astype(np.float16)
        yield mock


@pytest.fixture
def mock_embed_query():
    """Mock embedding query function"""
    with patch("ai.tools.data.embed_query") as data_mock, patch(
        "ai.tools.notes.embed_query"
    ) as notes_mock:
        data_mock.return_value = np.random.rand(3072).astype(np.float16)
        notes_mock.return_value = np.random.rand(3072).astype(np.float16)

        # Return an object that tracks both mocks
        class CombinedMock:
            def __init__(self, data_mock, notes_mock):
                self.data_mock = data_mock
                self.notes_mock = notes_mock

            def assert_called_once_with(self, *args, **kwargs):
                # Try data mock first, then notes mock
                try:
                    self.data_mock.assert_called_once_with(*args, **kwargs)
                except AssertionError:
                    self.notes_mock.assert_called_once_with(*args, **kwargs)

        yield CombinedMock(data_mock, notes_mock)


@pytest.fixture
def test_slate(db_session, test_user):
    """Create a test slate in the database"""
    slate = Slate(
        user_id=test_user.id, content="Test slate content for testing purposes"
    )
    db_session.add(slate)
    db_session.commit()
    return slate


@pytest.fixture
def test_note(db_session, test_user, test_agent):
    """Create a test note in the database"""
    embedding = np.random.rand(3072).astype(np.float16)
    note = Note(
        user_id=test_user.id,
        owner=test_agent.id,
        title="Test Note",
        content="Test note content for testing purposes",
        embedding=embedding,
    )
    db_session.add(note)
    db_session.commit()
    return note


@pytest.fixture
def test_raw_entry(db_session, test_user):
    """Create a test raw entry in the database"""
    embedding = np.random.rand(3072).astype(np.float16)
    raw_entry = RawEntry(
        user_id=test_user.id,
        source="test_source",
        content={
            "text": "Test raw entry content that is quite long and will be truncated in the formatted output when displayed to users"
        },
        embedding=embedding,
    )
    db_session.add(raw_entry)
    db_session.commit()
    return raw_entry


@pytest.fixture
def mock_run_context():
    """Mock run context for utilities tests that don't need database"""
    context = Mock()
    context.deps = Mock()
    context.deps.user_id = uuid4()
    context.deps.agent_name = "test_agent"
    return context
