from __future__ import annotations
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from config import settings
from database.models import Base, NotificationConfig

os.makedirs(os.path.dirname(settings.db_path), exist_ok=True)

engine = create_async_engine(
    settings.db_url,
    connect_args={"check_same_thread": False},
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def init_db() -> None:
    """Create all tables and seed defaults."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed notification config row (singleton, id=1)
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(select(NotificationConfig).where(NotificationConfig.id == 1))
        if not result.scalar_one_or_none():
            session.add(NotificationConfig(
                id=1,
                enabled=True,
                pushover_user_key=settings.pushover_user_key or None,
                pushover_api_token=settings.pushover_api_token or None,
                cooldown_hours=settings.notify_cooldown_hours,
            ))
            await session.commit()


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
