from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sqlalchemy.orm import (
    declarative_base,
)


import os

from src.config import settings

Base = declarative_base()

DATABASE_URL = (
    f"sqlite+aiosqlite:///{os.path.join(settings.OUTPUT_DIR, 'meeting_helper.db')}"
)

engine = create_async_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
    echo=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autoflush=False,
    future=True,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
