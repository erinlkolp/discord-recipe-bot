import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session


def create_db_engine():
    url = (
        f"mysql+pymysql://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}"
        f"@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}"
    )
    return create_engine(url, pool_pre_ping=True)


def get_session_factory(engine):
    return sessionmaker(engine)


def upsert_guild(session: Session, guild_id: str, guild_name: str) -> None:
    """Ensure a guild row exists; safe to call on every command invocation."""
    from recipebot.db.models import Guild
    session.merge(Guild(guild_id=str(guild_id), name=guild_name))


def current_week_start():
    """Return the Monday of the current ISO calendar week."""
    from datetime import date, timedelta
    today = date.today()
    return today - timedelta(days=today.weekday())
