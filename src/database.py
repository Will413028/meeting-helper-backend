from sqlalchemy import create_engine
from sqlalchemy.orm import (
    declarative_base,
    sessionmaker,
    Session,
)


from typing import Iterator
import os

from src.config import settings

Base = declarative_base()

DATABASE_URL = f"sqlite:///{os.path.join(settings.OUTPUT_DIR, 'meeting_helper.db')}"

# engine = create_engine(DATABASE_URL,connect_args={"check_same_thread": False}, echo=True)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
