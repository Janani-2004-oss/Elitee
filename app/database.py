"""
SQLAlchemy async models and engine setup.
"""
import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text, ForeignKey
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import settings


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class RequestLog(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True)
    status_code = Column(Integer, nullable=False)
    latency_ms = Column(Float, nullable=False)
    payment_status = Column(String(50))
    inventory_latency = Column(Float)
    external_api_latency = Column(Float)
    root_cause = Column(String(100))
    error_type = Column(String(100))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# Async engine & session factory
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create tables and seed seed users."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed a handful of users for realistic logs
    seed_users = [
        {"email": "alice@example.com", "name": "Alice Nguyen"},
        {"email": "bob@example.com",   "name": "Bob Hernandez"},
        {"email": "carol@example.com", "name": "Carol Smith"},
        {"email": "dave@example.com",  "name": "Dave Okafor"},
        {"email": "eve@example.com",   "name": "Eve Park"},
    ]
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        for u in seed_users:
            existing = await session.execute(
                select(User).where(User.email == u["email"])
            )
            if existing.scalar_one_or_none() is None:
                session.add(User(**u))
        await session.commit()
