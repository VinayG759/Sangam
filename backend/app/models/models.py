from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Text, func
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
from pgvector.sqlalchemy import Vector
import datetime
from app.db import Base

class AdminRegion(Base):
    __tablename__ = "admin_regions"

    id = Column(Integer, primary_key=True, index=True)
    country_code = Column(String(10), nullable=False)
    name = Column(String(100), nullable=False)
    level = Column(String(50), nullable=False)  # state, district, subdistrict, ward
    parent_id = Column(Integer, ForeignKey("admin_regions.id"), nullable=True)
    # PostGIS geometry column for region boundaries (MultiPolygon or Polygon)
    geom = Column(Geometry(geometry_type="GEOMETRY", srid=4326), nullable=True)

    parent = relationship("AdminRegion", remote_side=[id], backref="children")
    expenditures = relationship("Expenditure", back_populates="region")
    indicators = relationship("Indicator", back_populates="region")
    clusters = relationship("IssueCluster", back_populates="region")


class CitizenReport(Base):
    __tablename__ = "citizen_reports"

    id = Column(Integer, primary_key=True, index=True)
    raw_text = Column(Text, nullable=False)
    audio_url = Column(String(255), nullable=True)
    detected_language = Column(String(10), nullable=False)
    english_translation = Column(Text, nullable=True)
    sector = Column(String(50), nullable=False)  # water, roads, sanitation, etc.
    specific_issue = Column(String(255), nullable=True)
    urgency_score = Column(Float, default=1.0)  # 1 to 5
    sentiment = Column(String(50), nullable=True)
    pii_redacted_text = Column(Text, nullable=True)
    
    # Point geometry representing the location of the citizen report
    location = Column(Geometry(geometry_type="POINT", srid=4326), nullable=True)
    
    # pgvector embedding for semantic search/clustering (768 dimensions for text-embedding-004)
    embedding = Column(Vector(768), nullable=True)
    
    reported_at = Column(DateTime, default=func.now())
    cluster_id = Column(Integer, ForeignKey("issue_clusters.id"), nullable=True)

    cluster = relationship("IssueCluster", back_populates="reports")


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

    region = relationship("AdminRegion", back_populates="indicators")


class IssueCluster(Base):
    __tablename__ = "issue_clusters"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    sector = Column(String(50), nullable=False)
    region_id = Column(Integer, ForeignKey("admin_regions.id"), nullable=False)
    centroid = Column(Geometry(geometry_type="POINT", srid=4326), nullable=True)
    report_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())

    region = relationship("AdminRegion", back_populates="clusters")
    reports = relationship("CitizenReport", back_populates="cluster")
    priorities = relationship("Priority", back_populates="cluster")


class Priority(Base):
    __tablename__ = "priorities"

    id = Column(Integer, primary_key=True, index=True)
    cluster_id = Column(Integer, ForeignKey("issue_clusters.id"), nullable=False)
    score = Column(Float, nullable=False)
    verdict = Column(String(50), nullable=False)  # UNSERVED_GAP, STALLED_ALLOCATION, UNDERFUNDED_CRITICAL, WELL_SERVED
    details = Column(JSON, nullable=True)  # breakdown of sub-scores
    created_at = Column(DateTime, default=func.now())

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

    priority = relationship("Priority", back_populates="narrative_brief")
