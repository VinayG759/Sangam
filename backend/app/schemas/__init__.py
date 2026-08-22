"""
Pydantic schemas for Sangam API request/response validation.

Organized by domain:
- Overview schemas
- Priority schemas
- Citizen report schemas
- Simulation schemas
- Pack/config schemas
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ─── Overview ───────────────────────────────────────────────────────────────────

class OverviewResponse(BaseModel):
    total_citizen_reports: int = 0
    total_sanctioned_expenditure: float = 0.0
    unserved_gaps_count: int = 0
    stalled_projects_count: int = 0
    stalled_capital_amount: float = 0.0
    sectors_breakdown: Dict[str, int] = Field(default_factory=dict)


# ─── Priority ──────────────────────────────────────────────────────────────────

class PriorityScoreBreakdown(BaseModel):
    demand_density: float
    vulnerability: float
    expenditure_gap: float
    urgency: float

class PriorityWeights(BaseModel):
    demand_density: float
    vulnerability_index: float
    expenditure_gap: float
    urgency: float

class PriorityScoreResult(BaseModel):
    score: float
    verdict: str
    breakdown: PriorityScoreBreakdown
    weights_applied: PriorityWeights

class PriorityListItem(BaseModel):
    id: int
    cluster_id: int
    title: str
    sector: str
    score: float
    verdict: str
    report_count: int
    region_name: str
    details: Optional[Dict[str, Any]] = None

class NarrativeBriefResponse(BaseModel):
    summary: str
    why_prioritized: str
    fiscal_gap_analysis: str
    recommended_action: str

class PriorityDetailResponse(BaseModel):
    id: int
    score: float
    verdict: str
    evidence_bundle: Dict[str, Any] = Field(default_factory=dict)
    narrative_brief: NarrativeBriefResponse


# ─── Citizen Reports ────────────────────────────────────────────────────────────

class CitizenInflowRequest(BaseModel):
    """Request schema for ingesting a new citizen report."""
    text: str = Field(..., min_length=1, max_length=5000, description="Raw citizen report text in any supported language")
    latitude: Optional[float] = Field(None, ge=-90, le=90, description="Latitude of the report location")
    longitude: Optional[float] = Field(None, ge=-180, le=180, description="Longitude of the report location")

class CitizenReportAnalysisResponse(BaseModel):
    """Response from Gemini analysis of a citizen report."""
    original_language: str
    english_translation: str
    sector: str
    specific_issue: str
    urgency_score: float = Field(ge=1.0, le=5.0)
    sentiment: str
    extracted_location_entities: List[str] = Field(default_factory=list)
    pii_redacted_text: str

class CitizenIngestResponse(BaseModel):
    status: str
    report_id: int
    analysis_extracted: CitizenReportAnalysisResponse


# ─── Simulation ─────────────────────────────────────────────────────────────────

class SimulationRequest(BaseModel):
    """Request schema for budget simulation."""
    available_budget: float = Field(..., gt=0, description="Total budget pool to allocate (in local currency)")
    strategy: str = Field("equity", pattern="^(equity|reach|default)$", description="Allocation strategy: 'equity', 'reach', or 'default'")

class SimulationAllocationItem(BaseModel):
    cluster_id: int
    title: str
    sector: str
    allocated_amount: float
    pct_funded: float
    status: str

class SimulationResponse(BaseModel):
    strategy: str
    simulated_budget: float
    total_spent: float
    remaining_budget: float
    gaps_fully_resolved: int
    citizen_needs_addressed: int
    allocations: List[SimulationAllocationItem]


# ─── Verification ──────────────────────────────────────────────────────────────

class VerificationResult(BaseModel):
    verified: bool
    unverified_count: int
    unverified_numbers: List[float]
    extracted_numbers: List[float]
    bundle_values: List[float]


# ─── Pack Config ────────────────────────────────────────────────────────────────

class LanguageInfo(BaseModel):
    code: str
    name: str
    is_default: bool = False

class SectorInfo(BaseModel):
    key: str
    name: str

class WeightsInfo(BaseModel):
    demand_density: float
    vulnerability_index: float
    expenditure_gap: float
    urgency: float

class PackInfoResponse(BaseModel):
    country_code: str
    region_name: str
    languages: List[LanguageInfo]
    sectors: List[SectorInfo]
    weights: WeightsInfo


# ─── Common ─────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    app: str
    active_pack: str

class ErrorResponse(BaseModel):
    detail: str

class SuccessResponse(BaseModel):
    status: str
    message: str
