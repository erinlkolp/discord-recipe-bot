import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from recipebot.db.models import Base


@pytest.fixture
def engine():
    e = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(e)
    yield e
    Base.metadata.drop_all(e)


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture
def mock_interaction():
    interaction = MagicMock()
    interaction.guild_id = 123456789
    interaction.guild.name = "Test Guild"
    interaction.guild.id = 123456789
    interaction.user.id = 987654321
    interaction.response.send_message = AsyncMock()
    interaction.response.send_modal = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


def make_session_factory(session):
    """Return a callable that acts as a context manager yielding the given session.
    Use this in bot fixtures so `with self.bot.session_factory() as s:` works in tests."""
    from contextlib import contextmanager

    @contextmanager
    def factory():
        yield session

    return factory
