from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Text, func, Boolean
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
from pgvector.sqlalchemy import Vector
import datetime
from app.db import Base

class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String(50), nullable=False)  # running, complete, failed
    started_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime, nullable=True)
    note = Column(Text, nullable=True)


class AdminRegion(Base):
    __tablename__ = "admin_regions"

    id = Column(Integer, primary_key=True, index=True)
    country_code = Column(String(10), nullable=False)
    name = Column(String(100), nullable=False)
    level = Column(String(50), nullable=False)  # state, district, subdistrict, ward
    parent_id = Column(Integer, ForeignKey("admin_regions.id"), nullable=True)
    # Source pack's own unit_id (e.g. IN-KA-CHITRADURGA-HIRIYUR). Lets
    # load_real_data.py match existing rows on re-import instead of
    # duplicating them; unset for hand-seeded demo regions.
    external_id = Column(String(100), unique=True, nullable=True, index=True)
    # Needed for per-capita scoring: raw report counts otherwise always favour
    # dense areas, which builds a system that funds places already served.
    population = Column(Integer, nullable=True)
    # pipe-separated alternate spellings/scripts, e.g. Bangalore|Bengaluru|ಬೆಂಗಳೂರು
    name_variants = Column(Text, nullable=True)
    # PostGIS geometry column for region boundaries (MultiPolygon or Polygon)
    geom = Column(Geometry(geometry_type="GEOMETRY", srid=4326), nullable=True)
    # Representative point for map plotting, especially when geom is unavailable
    centroid = Column(Geometry(geometry_type="POINT", srid=4326), nullable=True)

    parent = relationship("AdminRegion", remote_side=[id], backref="children")
    expenditures = relationship("Expenditure", back_populates="region")
    indicators = relationship("Indicator", back_populates="region")
    clusters = relationship("IssueCluster", back_populates="region")


class CitizenReport(Base):
    __tablename__ = "citizen_reports"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String(50), default="complete", nullable=False)
    tracking_id = Column(String(20), unique=True, index=True, nullable=True)
    channel = Column(String(50), default="web", nullable=False)
    raw_text = Column(Text, nullable=False)
    audio_url = Column(String(255), nullable=True)
    # HMAC of the channel user id + a server pepper. Never the raw id --
    # this lets scoring count distinct reporters (so flooding from one
    # identity cannot manufacture a hotspot) without ever being able to
    # name who reported. Nullable during migration from reports with no
    # channel identity attached yet.
    reporter_hash = Column(String(64), nullable=True, index=True)
    detected_language = Column(String(10), nullable=False)
    english_translation = Column(Text, nullable=True)
    sector = Column(String(50), nullable=False)  # water, roads, sanitation, etc.
    specific_issue = Column(String(255), nullable=True)
    urgency_score = Column(Float, default=1.0)  # 1 to 5
    sentiment = Column(String(50), nullable=True)
    pii_redacted_text = Column(Text, nullable=True)
    
    # Point geometry representing the location of the citizen report
    location = Column(Geometry(geometry_type="POINT", srid=4326), nullable=True)
    
    # Optional explicitly resolved region, preferred over spatial join
    region_id = Column(Integer, ForeignKey("admin_regions.id"), nullable=True)
    
    # pgvector embedding for semantic search/clustering (768 dimensions for text-embedding-004)
    embedding = Column(Vector(768), nullable=True)
    
    reported_at = Column(DateTime, default=func.now())
    cluster_id = Column(Integer, ForeignKey("issue_clusters.id"), nullable=True)

    cluster = relationship("IssueCluster", back_populates="reports")
    region = relationship("AdminRegion", foreign_keys=[region_id])

class PendingIntake(Base):
    __tablename__ = "pending_intake"

    channel_user_hash = Column(String(64), primary_key=True)
    channel = Column(String(50), nullable=False)
    partial_report = Column(JSON, nullable=False)
    awaiting = Column(String(50), nullable=False)  # currently always "location"
    expires_at = Column(DateTime, nullable=False)

class Expenditure(Base):
    __tablename__ = "expenditures"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    sector = Column(String(50), nullable=False)
    amount = Column(Float, nullable=False)
    allocated_year = Column(Integer, nullable=False)
    status = Column(String(50), nullable=False)  # sanctioned, completed, in_progress, stalled
    
    # Optional geographic location mapping
    location = Column(Geometry(geometry_type="POINT", srid=4326), nullable=True)
    # pgvector embedding for matching expenditures to citizen reports semantically
    embedding = Column(Vector(768), nullable=True)
    
    region_id = Column(Integer, ForeignKey("admin_regions.id"), nullable=False)
    
    region = relationship("AdminRegion", back_populates="expenditures")


class Indicator(Base):
    __tablename__ = "indicators"

    id = Column(Integer, primary_key=True, index=True)
    region_id = Column(Integer, ForeignKey("admin_regions.id"), nullable=False)
    indicator_key = Column(String(100), nullable=False)  # e.g., multidimensional_poverty_index, population_density
    numeric_value = Column(Float, nullable=False)
    source_year = Column(Integer, nullable=False)
    # Provenance. Nullable for hand-seeded demo indicators; every row imported
    # from a real government dataset carries both, because a figure that
    # cannot say where it came from should not be treated as evidence.
    source_name = Column(String(255), nullable=True)
    source_url = Column(String(500), nullable=True)

    region = relationship("AdminRegion", back_populates="indicators")


class IssueCluster(Base):
    __tablename__ = "issue_clusters"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    sector = Column(String(50), nullable=False)
    region_id = Column(Integer, ForeignKey("admin_regions.id"), nullable=False)
    centroid = Column(Geometry(geometry_type="POINT", srid=4326), nullable=True)
    is_approximate_location = Column(Boolean, default=False)
    report_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    run_id = Column(Integer, ForeignKey("analysis_runs.id"), nullable=True)

    region = relationship("AdminRegion", back_populates="clusters")
    reports = relationship("CitizenReport", back_populates="cluster")
    priorities = relationship("Priority", back_populates="cluster")


class Priority(Base):
    __tablename__ = "priorities"

    id = Column(Integer, primary_key=True, index=True)
    cluster_id = Column(Integer, ForeignKey("issue_clusters.id"), nullable=False)
    score = Column(Float, nullable=False)
    verdict = Column(String(50), nullable=False)  # UNSERVED_GAP, STALLED_ALLOCATION, UNDERFUNDED_CRITICAL, WELL_SERVED
    list = Column(String(10), nullable=True)  # fund or audit
    details = Column(JSON, nullable=True)  # breakdown of sub-scores
    created_at = Column(DateTime, default=func.now())
    run_id = Column(Integer, ForeignKey("analysis_runs.id"), nullable=True)

    cluster = relationship("IssueCluster", back_populates="priorities")
    evidence_bundle = relationship("EvidenceBundle", uselist=False, back_populates="priority")
    narrative_brief = relationship("NarrativeBrief", uselist=False, back_populates="priority")


class EvidenceBundle(Base):
    __tablename__ = "evidence_bundles"

    id = Column(Integer, primary_key=True, index=True)
    priority_id = Column(Integer, ForeignKey("priorities.id"), nullable=False)
    # Complete audit trail structured JSON
    data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=func.now())
    run_id = Column(Integer, ForeignKey("analysis_runs.id"), nullable=True)

    priority = relationship("Priority", back_populates="evidence_bundle")


class NarrativeBrief(Base):
    __tablename__ = "narrative_briefs"

    id = Column(Integer, primary_key=True, index=True)
    priority_id = Column(Integer, ForeignKey("priorities.id"), nullable=False)
    summary = Column(Text, nullable=False)
    why_prioritized = Column(Text, nullable=False)
    fiscal_gap_analysis = Column(Text, nullable=False)
    recommended_action = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now())
    run_id = Column(Integer, ForeignKey("analysis_runs.id"), nullable=True)

    priority = relationship("Priority", back_populates="narrative_brief")
