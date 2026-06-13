import uuid
from datetime import UTC, datetime
from typing import ClassVar

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict] = {dict: JSON}


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class Avatar(Base):
    __tablename__ = "avatars"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="recording")
    assets: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Video(Base):
    __tablename__ = "videos"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    avatar_id: Mapped[str] = mapped_column(ForeignKey("avatars.id"), index=True)
    status_fast: Mapped[str] = mapped_column(String(16), default="queued")
    script: Mapped[dict | None] = mapped_column(JSON, default=None)
    assets: Mapped[dict] = mapped_column(JSON, default=dict)
    rating: Mapped[str | None] = mapped_column(String(8), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    lane: Mapped[str] = mapped_column(String(16), default="interactive")
    status: Mapped[str] = mapped_column(String(16), default="queued")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    timings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
