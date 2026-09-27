"""
Every table in Sangam. These are the contracts between features: a feature
writes some tables and reads others, and never imports another feature's code.

No table or column encodes one country's vocabulary (no admin-level names,
no scheme names) — a new country adds rows, not columns.
"""

from datetime import date, datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

EMBEDDING_DIM = 768


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Reference data, loaded from a country pack ───────────────────────────────


class Region(Base):
    """One administrative unit, in a tree. What each level is called comes from pack.yaml."""

    __tablename__ = "regions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # the pack's unit_id
    country_code: Mapped[str] = mapped_column(String(2), index=True)
    level: Mapped[int] = mapped_column(Integer)  # 0 = country; meaning of deeper levels is in pack.yaml
    name: Mapped[str] = mapped_column(String(200))
    name_variants: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("regions.id"), index=True)
    external_code: Mapped[str | None] = mapped_column(String(32))
    population: Mapped[int | None] = mapped_column(Integer)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    source_name: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)


class Indicator(Base):
    """One statistic for one place in one period. Tall, so new statistics are rows."""

    __tablename__ = "indicators"
    __table_args__ = (UniqueConstraint("region_id", "key", "period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[str] = mapped_column(ForeignKey("regions.id"), index=True)
    key: Mapped[str] = mapped_column(String(100), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(50))
    period: Mapped[str] = mapped_column(String(20))
    source_name: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)


class Project(Base):
    """Public money committed to a place and sector. The other half of the join."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    region_id: Mapped[str] = mapped_column(ForeignKey("regions.id"), index=True)
    sector: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(Text)
    amount: Mapped[float | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(20))  # planned|sanctioned|in_progress|completed|stalled
    sanctioned_date: Mapped[date | None] = mapped_column(Date)
    completion_date: Mapped[date | None] = mapped_column(Date)
    source_name: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)


# ── Citizen intake ────────────────────────────────────────────────────────────


class Report(Base):
    """One citizen request. Only redacted text is ever stored."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    tracking_id: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    country_code: Mapped[str] = mapped_column(String(2), index=True)
    channel: Mapped[str] = mapped_column(String(20))  # telegram|whatsapp|web|seed
    reporter_hash: Mapped[str] = mapped_column(String(64), index=True)  # HMAC; raw ID never stored
    # received → understood → located  (or needs_location / needs_confirmation / unlocated)
    status: Mapped[str] = mapped_column(String(24), default="received", index=True)
    language: Mapped[str | None] = mapped_column(String(10))
    text_original: Mapped[str | None] = mapped_column(Text)
    text_en: Mapped[str | None] = mapped_column(Text)
    sector: Mapped[str | None] = mapped_column(String(50), index=True)
    urgency: Mapped[int | None] = mapped_column(Integer)
    location_text: Mapped[str | None] = mapped_column(Text)
    region_id: Mapped[str | None] = mapped_column(ForeignKey("regions.id"), index=True)
    location_method: Mapped[str | None] = mapped_column(String(10))  # gps|text|picker
    location_confidence: Mapped[float | None] = mapped_column(Float)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    # NULL means "not computed yet" — never a placeholder of zeros.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    has_media: Mapped[bool] = mapped_column(Boolean, default=False)
    flagged_coordinated: Mapped[bool] = mapped_column(Boolean, default=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReportMedia(Base):
    """Raw voice/photo, kept only until understood and at most media_retention_days."""

    __tablename__ = "report_media"

    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), primary_key=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Contact(Base):
    """
    The encrypted chat ID for one report, kept only so the citizen can be told when
    it is prioritised. Deleted after that message, or at expires_at.
    """

    __tablename__ = "contacts"

    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), primary_key=True)
    channel: Mapped[str] = mapped_column(String(20))
    address_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Conversation(Base):
    """The single pending follow-up question for one reporter (location or confirmation)."""

    __tablename__ = "conversations"

    reporter_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"))
    awaiting: Mapped[str] = mapped_column(String(20))  # location|confirm
    candidate_region_id: Mapped[str | None] = mapped_column(ForeignKey("regions.id"))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# ── Analysis output (one set per versioned run) ──────────────────────────────


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    country_code: Mapped[str] = mapped_column(String(2), index=True)
    status: Mapped[str] = mapped_column(String(12), default="running")  # running|complete|failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)


class Cluster(Base):
    """Demand for one need in one place, as of one run."""

    __tablename__ = "clusters"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    region_id: Mapped[str] = mapped_column(ForeignKey("regions.id"))
    sector: Mapped[str] = mapped_column(String(50))
    report_count: Mapped[int] = mapped_column(Integer)
    distinct_reporters: Mapped[int] = mapped_column(Integer)
    per_1000: Mapped[float | None] = mapped_column(Float)
    baseline_ratio: Mapped[float | None] = mapped_column(Float)
    avg_urgency: Mapped[float | None] = mapped_column(Float)
    is_emerging: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Priority(Base):
    """A ranked recommendation: verdict, score, the arithmetic behind it, and its evidence."""

    __tablename__ = "priorities"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("clusters.id", ondelete="CASCADE"))
    region_id: Mapped[str] = mapped_column(ForeignKey("regions.id"))
    sector: Mapped[str] = mapped_column(String(50))
    rank: Mapped[int] = mapped_column(Integer)
    verdict: Mapped[str] = mapped_column(String(30), index=True)
    score: Mapped[float] = mapped_column(Float)
    components: Mapped[dict] = mapped_column(JSONB)  # each term, its weight, its contribution
    evidence: Mapped[list] = mapped_column(JSONB)  # [{id, label, value, unit, source_name, source_url}]
    estimated_cost: Mapped[float | None] = mapped_column(Float)
    beneficiaries: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(Text)
    summary_source: Mapped[str] = mapped_column(String(10))  # model|template
    displayable: Mapped[bool] = mapped_column(Boolean)  # False below the privacy floor
