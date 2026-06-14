import uuid
from datetime import UTC, datetime
from typing import ClassVar

from sqlalchemy import JSON, DateTime, ForeignKey, String, TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class TZDateTime(TypeDecorator):
    """DateTime that always comes back UTC-aware (sqlite parity with postgres)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict] = {dict: JSON, datetime: TZDateTime()}


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)


class Avatar(Base):
    __tablename__ = "avatars"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="recording")
    assets: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Video(Base):
    __tablename__ = "videos"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    avatar_id: Mapped[str] = mapped_column(ForeignKey("avatars.id"), index=True)
    status_fast: Mapped[str] = mapped_column(String(16), default="queued")
    script: Mapped[dict | None] = mapped_column(JSON, default=None)
    assets: Mapped[dict] = mapped_column(JSON, default=dict)
    rating: Mapped[str | None] = mapped_column(String(8), default=None)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Plan(Base):
    """A Video Agent artifact: the researched, scripted, directed plan a user
    reviews and edits before submitting it for generation.

    `brief` holds the request inputs (prompt, chosen avatar/voice, duration,
    orientation, language). `plan` holds the emitted artifact JSON (title, style,
    research, script scenes with direction + transitions, audio, resources).
    `video_id` links the Video produced once the plan is generated.
    """

    __tablename__ = "plans"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    avatar_id: Mapped[str | None] = mapped_column(
        ForeignKey("avatars.id"), index=True, default=None
    )
    # researching -> scripting -> directing -> ready -> generating -> generated | failed
    status: Mapped[str] = mapped_column(String(16), default="researching")
    brief: Mapped[dict] = mapped_column(JSON, default=dict)
    plan: Mapped[dict | None] = mapped_column(JSON, default=None)
    # Finalized artifact manifest for the session: durable S3 keys for every asset
    # (plan snapshot + media/overlays/audio/footage) plus counts/metadata.
    bundle: Mapped[dict | None] = mapped_column(JSON, default=None)
    video_id: Mapped[str | None] = mapped_column(ForeignKey("videos.id"), default=None)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Voice(Base):
    """A reusable voice: cloned from an avatar's footage or from a freshly
    recorded/uploaded sample. Several provider/model `candidates` are generated
    for the user to A/B, then one is `selected` (its external id + provider).

    A selected voice can be attached to an avatar (the avatar's `voice_id` asset)
    or used on its own as a picker source for the Video Agent.
    """

    __tablename__ = "voices"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    # The avatar this voice was derived from / attached to (footage clones, or an
    # explicit attach). Null for standalone voices not tied to any avatar.
    avatar_id: Mapped[str | None] = mapped_column(
        ForeignKey("avatars.id"), index=True, default=None
    )
    label: Mapped[str] = mapped_column(String(120), default="Minha voz")
    # cloning -> ready -> failed
    status: Mapped[str] = mapped_column(String(16), default="cloning")
    # "footage" | "recorded" | "uploaded"
    source: Mapped[str] = mapped_column(String(16), default="recorded")
    # The chosen candidate after selection (external provider id + which provider).
    provider: Mapped[str | None] = mapped_column(String(32), default=None)
    external_id: Mapped[str | None] = mapped_column(String(64), default=None)
    # [{provider, label, model, external_id, preview_key, status}] — the A/B options.
    candidates: Mapped[dict | None] = mapped_column(JSON, default=None)
    # {sample: "voices/{id}/sample.wav", ...}
    assets: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    lane: Mapped[str] = mapped_column(String(16), default="interactive")
    status: Mapped[str] = mapped_column(String(16), default="queued")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    timings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=_now)
