from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_sessionmaker


async def db_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session
