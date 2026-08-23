# Graph Report - .  (2026-08-22)

## Corpus Check
- 79 files · ~61,586 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 635 nodes · 825 edges · 48 communities (28 shown, 20 thin omitted)
- Extraction: 82% EXTRACTED · 18% INFERRED · 0% AMBIGUOUS · INFERRED: 150 edges (avg confidence: 0.63)
- Token cost: 321,616 input · 0 output

## Community Hubs (Navigation)
- DB Models & Session
- Scoring Engine & Pack Config
- Gemini AI Service
- Country Pack Loader (Backend)
- App Config & Entry Point
- Evidence Verifier
- Frontend App Shell
- Frontend Dependencies
- Budget Simulation Engine
- Orphaned Engine Pack Loader
- API Response Schemas
- Frontend TS Config (App)
- Docs & Pack-Format Fork
- Frontend TS Config (Node)
- Frontend API Client
- Expenditures API Routes
- Test Fixtures
- Sector Chart Component
- Priority List Component
- Pack API Route
- Header Component
- Core Design Docs
- Scoring Weights Rationale
- Frontend TS Root Config
- Route Registration
- Docker Entrypoint Script
- Privacy Floor Rationale
- Docker Compose Config
- "The Join" Core Claim
- Admin Units Data Spec
- Data Task Brief
- Media Retention Decision
- 3-Call AI Pipeline Concept
- Frontend HTML Entry
- Favicon Brand Mark
- Icon Sprite Asset
- Frontend Template Notes
- Hero Banner Image
- React Logo (Default)
- Vite Logo (Default)
- Keepalive Workflow
- India Data Sources Tracker

## God Nodes (most connected - your core abstractions)
1. `compilerOptions` - 20 edges
2. `PackLoader` - 18 edges
3. `CountryPack` - 15 edges
4. `TestExtractBundleValues` - 15 edges
5. `compilerOptions` - 15 edges
6. `WeightsConfig` - 14 edges
7. `GeminiService` - 13 edges
8. `AdminRegion` - 12 edges
9. `TestVerdictClassification` - 12 edges
10. `TestInputClamping` - 12 edges

## Surprising Connections (you probably didn't know these)
- `Engine Python Dependencies` --semantically_similar_to--> `Backend Python Dependencies`  [AMBIGUOUS] [semantically similar]
  engine/requirements.txt → backend/requirements.txt
- `sanctioned_projects.csv Spec` --conceptually_related_to--> `India-Karnataka Country Pack Config`  [AMBIGUOUS]
  docs/DATA-SOURCES.md → packs/india_karnataka/pack.yaml
- `CI GitHub Actions Workflow` --references--> `India-Karnataka Country Pack Config`  [EXTRACTED]
  .github/workflows/ci.yml → packs/india_karnataka/pack.yaml
- `Sangam Deployment Guide` --references--> `India-Karnataka Country Pack Config`  [EXTRACTED]
  DEPLOY.md → packs/india_karnataka/pack.yaml
- `Docker Compose Backend Service` --shares_data_with--> `Backend Python Dependencies`  [INFERRED]
  docker-compose.yml → backend/requirements.txt

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Country Pack Schema Fork (india / india_karnataka / default)** — concept_pack_format_fork, packs_india_pack_indiapack, packs_india_karnataka_pack_karnatakapack, packs_default_pack_defaultpack [INFERRED 0.85]
- **Runtime Evidence That india_karnataka Is the Active Pack** — docker_compose_backend_service, github_workflows_ci_ci_workflow, deploy_deployment_guide, docs_implementation_plan_phase1_foundation, packs_india_karnataka_pack_karnatakapack [EXTRACTED 1.00]
- **India Pack Config Citing Decision Log Entries** — packs_india_pack_weights, packs_india_pack_privacy, packs_india_pack_indiapack, docs_decisions_scoring_posture_balanced, docs_decisions_aggregation_floor, docs_decisions_stalled_allocations_two_lists [EXTRACTED 1.00]

## Communities (48 total, 20 thin omitted)

### Community 0 - "DB Models & Session"
Cohesion: 0.07
Nodes (52): get_db(), AsyncSession, AdminRegion, CitizenReport, EvidenceBundle, Expenditure, Indicator, IssueCluster (+44 more)

### Community 1 - "Scoring Engine & Pack Config"
Cohesion: 0.05
Nodes (30): LanguageConfig, BaseModel, SectorConfig, Any, Deterministic scoring engine.      PriorityScore = w_demand × DemandDensity +, Calculate a deterministic priority score and verdict.          Args:, ScoringEngine, _make_mock_pack() (+22 more)

### Community 2 - "Gemini AI Service"
Cohesion: 0.06
Nodes (31): CitizenReportAnalysis, GeminiService, PolicyBrief, Any, BaseModel, Call 3: Generate a grounded policy brief narrative based strictly on evidence bu, Call 1: Analyze citizen voice/text report, translate to English, categorise, and, Generate semantic vector embedding for similarity mapping. (+23 more)

### Community 3 - "Country Pack Loader (Backend)"
Cohesion: 0.07
Nodes (29): CountryPack, PackLoader, Clear the cached pack (useful for testing or hot-reload)., Return the list of valid sector keys from the active pack., Return the list of supported language codes from the active pack., Priority scoring weights. These should sum to 1.0 for a properly     normalized, Warn if weights don't sum to ~1.0 (they still work, just un-normalized)., A country/region configuration pack that defines:     - Supported languages (+21 more)

### Community 4 - "App Config & Entry Point"
Cohesion: 0.04
Nodes (18): Settings, client(), mock_db_session(), Integration tests for all Sangam API routes.  Uses FastAPI's TestClient with m, Simulation with negative budget should return 500 (ValueError from engine)., Simulation with valid input (but no priorities in DB) should return 200., Create a TestClient with mocked database dependency., Override the get_db dependency with a mock AsyncSession.     All database queri (+10 more)

### Community 5 - "Evidence Verifier"
Cohesion: 0.07
Nodes (14): Any, Does `num` legitimately represent `bundle_val`?          This method is the wh, Compare extracted text numbers against evidence values.          Args:, Regex to find all numeric expressions: currency, percentage, counts, decimals., Recursively extract all numeric values from the Evidence Bundle.         Handle, Programmatic Number Verifier (Non-LLM).     Extracts all numerical values from, VerificationEngine, Unit tests for VerificationEngine.  Tests cover: - Number extraction from tex (+6 more)

### Community 6 - "Frontend App Shell"
Cohesion: 0.06
Nodes (29): plugins, rules, react/only-export-components, react/rules-of-hooks, $schema, Tab, BudgetSimulator(), croreLabel() (+21 more)

### Community 7 - "Frontend Dependencies"
Cohesion: 0.05
Nodes (37): dependencies, leaflet, lucide-react, react, react-dom, recharts, @types/leaflet, devDependencies (+29 more)

### Community 8 - "Budget Simulation Engine"
Cohesion: 0.06
Nodes (18): Any, Run budget allocation simulation.          Args:             available_budget, Simulates allocation of a fixed public capital pool across priorities     using, SimulationEngine, Unit tests for SimulationEngine.  Tests cover: - Equity strategy sorting and, Items where estimated_cost <= allocated_budget should be skipped., Input validation tests., Basic allocation behavior tests. (+10 more)

### Community 9 - "Orphaned Engine Pack Loader"
Cohesion: 0.10
Nodes (25): AdminUnit, coverage_report(), Indicator, _int_or_none(), load(), Pack, PackError, Any (+17 more)

### Community 10 - "API Response Schemas"
Cohesion: 0.13
Nodes (26): CitizenInflowRequest, CitizenIngestResponse, CitizenReportAnalysisResponse, ErrorResponse, HealthResponse, LanguageInfo, NarrativeBriefResponse, OverviewResponse (+18 more)

### Community 11 - "Frontend TS Config (App)"
Cohesion: 0.08
Nodes (26): compilerOptions, allowArbitraryExtensions, allowImportingTsExtensions, erasableSyntaxOnly, ignoreDeprecations, jsx, lib, module (+18 more)

### Community 12 - "Docs & Pack-Format Fork"
Cohesion: 0.10
Nodes (22): Backend Python Dependencies, Country Pack Format Fork (india vs india_karnataka), Sangam Deployment Guide, Docker Compose Backend Service, Docker Compose Postgres/PostGIS/pgvector Service, Load-Bearing Decisions (5 principles), indicators.csv Spec (tall schema, indicator_key list), sanctioned_projects.csv Spec (+14 more)

### Community 13 - "Frontend TS Config (Node)"
Cohesion: 0.10
Nodes (19): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, lib, module, moduleDetection, noEmit, noFallthroughCasesInSwitch (+11 more)

### Community 14 - "Frontend API Client"
Cohesion: 0.14
Nodes (11): api, Cluster, NarrativeBrief, OverviewData, PackInfo, Priority, PriorityDetail, Report (+3 more)

### Community 15 - "Expenditures API Routes"
Cohesion: 0.28
Nodes (8): expenditures_summary(), get_expenditure_detail(), list_expenditures(), AsyncSession, Expenditures API routes.  Provides endpoints for: - Listing expenditure recor, Get a single expenditure record's full detail., List expenditure records with optional filters and pagination., Aggregate expenditure statistics grouped by sector.     Shows total amount, cou

### Community 16 - "Test Fixtures"
Cohesion: 0.25
Nodes (7): Shared pytest fixtures and configuration for Sangam backend tests.  Uses a tem, Create a temporary pack directory with a valid pack.yaml.     Returns the path, Return a realistic evidence bundle for testing the verifier and Gemini service., Return a list of priority dicts for simulation testing., sample_evidence_bundle(), sample_pack_dir(), sample_priorities()

### Community 17 - "Sector Chart Component"
Cohesion: 0.29
Nodes (4): COLORS_HEX, SECTOR_LABELS, SectorChartProps, TooltipProps

### Community 18 - "Priority List Component"
Cohesion: 0.33
Nodes (3): PriorityListProps, SECTOR_ICONS, VERDICT_META

### Community 19 - "Pack API Route"
Cohesion: 0.50
Nodes (3): get_active_pack(), Pack configuration API routes.  Provides endpoints for: - Getting the active, Returns the active country pack configuration.     Includes supported languages

### Community 21 - "Core Design Docs"
Cohesion: 0.67
Nodes (3): Sangam System Design Doc, Decision Log, Implementation Plan Doc

### Community 22 - "Scoring Weights Rationale"
Cohesion: 0.67
Nodes (3): Decision #8 — Scoring Posture: Balanced Weights, 8 Core Data Model Tables, India Pack Scoring Weights (demand/deficit/reach/coverage)

## Ambiguous Edges - Review These
- `Backend Python Dependencies` → `Engine Python Dependencies`  [AMBIGUOUS]
  engine/requirements.txt · relation: semantically_similar_to
- `sanctioned_projects.csv Spec` → `India-Karnataka Country Pack Config`  [AMBIGUOUS]
  docs/DATA-SOURCES.md · relation: conceptually_related_to

## Knowledge Gaps
- **112 isolated node(s):** `docker-entrypoint.sh script`, `$schema`, `typescript`, `oxc`, `react/rules-of-hooks` (+107 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **20 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Backend Python Dependencies` and `Engine Python Dependencies`?**
  _Edge tagged AMBIGUOUS (relation: semantically_similar_to) - confidence is low._
- **What is the exact relationship between `sanctioned_projects.csv Spec` and `India-Karnataka Country Pack Config`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `PackError` connect `Orphaned Engine Pack Loader` to `Gemini AI Service`?**
  _High betweenness centrality (0.041) - this node is a cross-community bridge._
- **Are the 12 inferred relationships involving `PackLoader` (e.g. with `.__new__()` and `pack_loader_instance()`) actually correct?**
  _`PackLoader` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 11 inferred relationships involving `CountryPack` (e.g. with `TestFallbackBehavior` and `TestHelperMethods`) actually correct?**
  _`CountryPack` has 11 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Centralized route registration for the Sangam API.  All route modules are impo`, `Issue Clusters API routes.  Provides endpoints for: - Listing clusters with s`, `List issue clusters. Each cluster represents a geographic concentration     of` to the rest of the system?**
  _245 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `DB Models & Session` be split into smaller, more focused modules?**
  _Cohesion score 0.06597222222222222 - nodes in this community are weakly interconnected._