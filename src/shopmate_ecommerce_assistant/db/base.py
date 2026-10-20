"""SQLAlchemy declarative base for Alembic metadata."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all future ORM models."""
