# GPS Location Capture & Confidence-Gated Confirmation (F12/F13) Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking. Work through tasks in order — each depends on the previous one's interfaces.

**Goal:** Close the real "Yelahanka" → "Alanka" bug found in live testing (a voice note's location got mis-transcribed by Gemini, `resolve_location` correctly found nothing close enough to auto-accept, and the citizen was silently left with no location — no chance to confirm or correct it). Two independent fixes: (F12) let a citizen share their device's GPS location natively instead of typing a place name at all, and (F13) when a typed place name matches only weakly, ask one yes/no confirmation instead of silently accepting a bad guess or silently giving up.

**Architecture:** `location_resolver.py` gets a richer `resolve_location_with_confidence()` that returns *how sure* a match is (`"exact"` / `"low"` / `"none"`), not just whether one exists — the existing `resolve_location()` becomes a thin wrapper that keeps its old behavior exactly (only `"exact"` counts). A new `resolve_gps_location()` resolves a raw lat/lon point to the nearest administrative region by centroid distance. `ingestion_service.py` uses the confidence to decide whether to auto-accept, ask for confirmation (a new `PendingIntake.awaiting = "location_confirmation"` state), or fall back to the existing "please name a location" flow. Both channel adapters (`telegram_adapter.py`, `whatsapp_adapter.py`) get near-identical additions — this project already keeps those two files as parallel, independently-readable copies rather than sharing logic through an abstraction, so this plan follows that existing convention rather than introducing a new one.

**Tech Stack:** Python 3.11, SQLAlchemy `AsyncSession`, PostGIS (`ST_Distance`, `ST_MakePoint`), `rapidfuzz`, pytest + pytest-asyncio.

**Spec:** Sangam System Design Document §17 "Location resolution, hardened" (F12, F13) (`https://claude.ai/code/artifact/ab991d55-d4c5-4c17-86e5-53449719f3db`), and §16's "Risk 2, revisited" note describing the real bug this closes.

## Global Constraints

- $0 running cost: no new dependency, no new external service.
- Stage explicit file paths when committing (`git add <path>`), never `git add -A`.
- No `Co-Authored-By` trailer on commits.
- `location_resolver.py` and the two channel adapters run on `AsyncSession` (`await` everywhere) — this is different from `clustering_engine.py`, which is sync. Do not mix the two styles.
- `AdminRegion.geom` (real boundary polygons) is **not populated** for Karnataka data yet — only `AdminRegion.centroid` (a point) is reliably present. Any new spatial query must use `centroid`, not `geom`.
- Full backend suite (`pytest backend/tests/`) must stay green throughout, not just the tests this plan adds.
- This project has no database migration tooling (`Base.metadata.create_all` only creates missing tables, never alters existing ones). `PendingIntake.awaiting` is already a free-text `String` column and `PendingIntake.partial_report` is already a JSON column — this plan adds a new string value (`"location_confirmation"`) and a new JSON key (`candidate_region_id`) to existing, already-flexible columns. **No schema change, no migration, is needed or permitted for this plan.**

---

### Task 1: `location_resolver.py` — confidence-aware and GPS resolution

**Files:**
- Modify: `backend/app/services/location_resolver.py`
- Test: `backend/tests/test_location_resolver.py`

**Interfaces:**
- Produces: `async def resolve_location_with_confidence(location_text_latin: str, country_code: str, db: AsyncSession) -> tuple[AdminRegion | None, str]` — confidence is one of `"exact"`, `"low"`, `"none"`. Produces `async def resolve_gps_location(latitude: float, longitude: float, country_code: str, db: AsyncSession) -> AdminRegion | None`. The existing `async def resolve_location(...) -> AdminRegion | None` keeps its exact current signature and behavior (delegates internally to the new function, accepting only `"exact"`).
- Consumes: nothing new — same `AdminRegion` model, same `db` session pattern already used in this file.

- [ ] **Step 1: Write the failing tests**

Open `backend/tests/test_location_resolver.py`. Change the import line at the top from:

```python
from app.services.location_resolver import resolve_location
```

to:

```python
from app.services.location_resolver import resolve_location, resolve_location_with_confidence, resolve_gps_location
```

Keep every existing test in this file unchanged — they must all still pass after this task, proving `resolve_location`'s old behavior survives the refactor. Add these new tests at the end of the file:

```python
@pytest.mark.asyncio
async def test_resolve_with_confidence_high_score_returns_exact(mock_db_session, monkeypatch):
    # Isolate the threshold branching from rapidfuzz's actual scoring
    # behavior for any specific string pair -- mock the matcher directly.
    def fake_extract_one(query, choices, scorer):
        return (choices[0], 90, 0)  # above the 85 auto-accept threshold
    monkeypatch.setattr("app.services.location_resolver.process.extractOne", fake_extract_one)

    region, confidence = await resolve_location_with_confidence("close enough", "IN", mock_db_session)
    assert confidence == "exact"
    assert region is not None


@pytest.mark.asyncio
async def test_resolve_with_confidence_mid_score_returns_low(mock_db_session, monkeypatch):
    def fake_extract_one(query, choices, scorer):
        return (choices[0], 70, 0)  # in the [65, 85) "low" band
    monkeypatch.setattr("app.services.location_resolver.process.extractOne", fake_extract_one)

    region, confidence = await resolve_location_with_confidence("sort of close", "IN", mock_db_session)
    assert confidence == "low"
    assert region is not None


@pytest.mark.asyncio
async def test_resolve_with_confidence_below_floor_returns_none(mock_db_session, monkeypatch):
    def fake_extract_one(query, choices, scorer):
        return (choices[0], 50, 0)  # below the 65 floor
    monkeypatch.setattr("app.services.location_resolver.process.extractOne", fake_extract_one)

    region, confidence = await resolve_location_with_confidence("nonsense", "IN", mock_db_session)
    assert confidence == "none"
    assert region is None


@pytest.mark.asyncio
async def test_resolve_with_confidence_empty_string_returns_none_without_query(mock_db_session):
    region, confidence = await resolve_location_with_confidence("", "IN", mock_db_session)
    assert region is None
    assert confidence == "none"
    mock_db_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_location_still_only_accepts_exact_confidence(mock_db_session, monkeypatch):
    # resolve_location must behave exactly as before this change: a "low"
    # confidence match is NOT good enough for its existing callers, which
    # haven't been upgraded to use the confidence-aware function.
    def fake_extract_one(query, choices, scorer):
        return (choices[0], 70, 0)
    monkeypatch.setattr("app.services.location_resolver.process.extractOne", fake_extract_one)

    region = await resolve_location("something", "IN", mock_db_session)
    assert region is None


@pytest.mark.asyncio
async def test_resolve_gps_location_returns_nearest_region():
    mock_session = AsyncMock()
    nearest = AdminRegion(id=5, country_code="IN", level="ward", name="Test Ward")

    nearest_id_result = MagicMock()
    nearest_id_result.first.return_value = (5,)
    region_result = MagicMock()
    region_result.scalar_one_or_none.return_value = nearest
    mock_session.execute.side_effect = [nearest_id_result, region_result]

    region = await resolve_gps_location(12.9716, 77.5946, "IN", mock_session)
    assert region is not None
    assert region.id == 5


@pytest.mark.asyncio
async def test_resolve_gps_location_returns_none_when_no_centroids_exist():
    mock_session = AsyncMock()
    empty_result = MagicMock()
    empty_result.first.return_value = None
    mock_session.execute.return_value = empty_result

    region = await resolve_gps_location(0.0, 0.0, "IN", mock_session)
    assert region is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_location_resolver.py -v`
Expected: FAIL with `ImportError` (the two new functions don't exist yet).

- [ ] **Step 3: Implement**

Replace the full contents of `backend/app/services/location_resolver.py` with:

```python
import logging
from rapidfuzz import process, fuzz
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.models.models import AdminRegion

logger = logging.getLogger(__name__)

# Below this score, a fuzzy match is not even worth suggesting.
FUZZY_SUGGEST_THRESHOLD = 65
# At or above this score, a fuzzy match is safe to accept automatically.
# Unchanged from the original single-threshold design.
FUZZY_AUTO_ACCEPT_THRESHOLD = 85


async def resolve_location_with_confidence(
    location_text_latin: str, country_code: str, db: AsyncSession
) -> tuple[AdminRegion | None, str]:
    """
    Like resolve_location, but distinguishes a confident match from a weak
    one instead of collapsing both non-matches into a single None.

    Returns (region, confidence) where confidence is one of:
      - "exact": an exact name/variant match, or a fuzzy score >= 85 --
        safe to accept automatically. Same bar the original single-
        threshold resolve_location always used.
      - "low": a fuzzy score in [65, 85) -- plausible, but not safe to
        accept silently. The caller should ask the citizen to confirm
        rather than either accepting it outright or discarding the report
        (F13, closing the real "Yelahanka" -> "Alanka" mis-transcription
        bug found in live testing -- resolve_location alone had nothing to
        do with a match this weak except discard it).
      - "none": nothing cleared even the low bar. region is None.
    """
    if not location_text_latin:
        return None, "none"

    stmt = select(AdminRegion).where(AdminRegion.country_code == country_code)
    result = await db.execute(stmt)
    regions = result.scalars().all()

    if not regions:
        return None, "none"

    query = location_text_latin.strip().lower()

    # Exact match first (name or variant).
    for region in regions:
        if region.name.strip().lower() == query:
            return region, "exact"
        if region.name_variants:
            variants = [v.strip().lower() for v in region.name_variants.split('|')]
            if query in variants:
                return region, "exact"

    # Fuzzy match. Both sides lowercased before scoring -- see the original
    # comment history in this file for why (WRatio is not case-insensitive
    # on its own).
    choices = []
    region_map = {}
    for region in regions:
        names_to_match = [region.name]
        if region.name_variants:
            names_to_match.extend(region.name_variants.split('|'))
        for name in names_to_match:
            clean_name = name.strip()
            if clean_name:
                lowered = clean_name.lower()
                choices.append(lowered)
                region_map[lowered] = region

    if not choices:
        return None, "none"

    match = process.extractOne(query, choices, scorer=fuzz.WRatio)
    if not match:
        return None, "none"

    best_str, score, _index = match
    if score >= FUZZY_AUTO_ACCEPT_THRESHOLD:
        return region_map[best_str], "exact"
    if score >= FUZZY_SUGGEST_THRESHOLD:
        return region_map[best_str], "low"
    return None, "none"


async def resolve_location(location_text_latin: str, country_code: str, db: AsyncSession) -> AdminRegion | None:
    """
    Thin wrapper kept for existing callers that only want an auto-acceptable
    match. Behavior is unchanged from before resolve_location_with_confidence
    existed: only "exact" confidence returns a region.
    """
    region, confidence = await resolve_location_with_confidence(location_text_latin, country_code, db)
    return region if confidence == "exact" else None


async def resolve_gps_location(
    latitude: float, longitude: float, country_code: str, db: AsyncSession
) -> AdminRegion | None:
    """
    Resolves a raw GPS point to the nearest administrative region with a
    known centroid -- used when a citizen shares their device location
    natively (F12) instead of typing a place name, bypassing transcription
    and spelling entirely. Real region boundary polygons (AdminRegion.geom)
    are not populated for Karnataka data yet, so this matches on centroid
    distance rather than point-in-polygon containment.
    """
    stmt = text("""
        SELECT id FROM admin_regions
        WHERE country_code = :country_code AND centroid IS NOT NULL
        ORDER BY ST_Distance(centroid, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)) ASC
        LIMIT 1;
    """)
    result = await db.execute(stmt, {"country_code": country_code, "lon": longitude, "lat": latitude})
    row = result.first()
    if not row:
        return None

    region_result = await db.execute(select(AdminRegion).where(AdminRegion.id == row[0]))
    return region_result.scalar_one_or_none()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_location_resolver.py -v`
Expected: all tests pass — the 5 pre-existing tests (proving `resolve_location`'s behavior didn't change) plus the 7 new ones.

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && python -m pytest tests/ -v`
Expected: everything passes. `clustering_engine.py` has its own inline, independent copy of fuzzy-matching logic for pending-report retries (not touched by this task) — confirm nothing there broke, since it imports from this module only indirectly (it does not call `resolve_location`, it duplicates the logic locally, so it should be unaffected, but verify the full suite anyway).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/location_resolver.py backend/tests/test_location_resolver.py
git commit -m "feat: add confidence-aware and GPS-based location resolution"
```

---

### Task 2: `ingestion_service.py` — wire confidence into intake

**Files:**
- Modify: `backend/app/services/ingestion_service.py`
- Test: `backend/tests/test_ingestion_service.py`

**Interfaces:**
- Consumes: `resolve_location_with_confidence` from Task 1.
- Produces: `ingest_citizen_message(...)`'s return dict gains two new keys: `"needs_location_confirmation": bool` and `"location_confirmation_candidate_name": str | None`. A new `PendingIntake.awaiting` value, `"location_confirmation"`, appears alongside the existing `"location"` value; its `partial_report` JSON gains a `"candidate_region_id"` key. Both new adapters tasks (3 and 4) read these.

- [ ] **Step 1: Write the failing test**

Open `backend/tests/test_ingestion_service.py`. Find the existing test `test_needs_location_followup_upserts_pending_intake`. It currently monkeypatches `resolve_location`:

```python
    monkeypatch.setattr(ingestion_module, "resolve_location", AsyncMock(return_value=None))
```

Change that line to monkeypatch the new function instead, returning the new tuple shape (no match at all, same case this test was already covering):

```python
    monkeypatch.setattr(ingestion_module, "resolve_location_with_confidence", AsyncMock(return_value=(None, "none")))
```

Leave the rest of that test unchanged — it should still pass as-is once `ingestion_service.py` is updated in Step 3.

Then add this new test, in the same style, right after `test_needs_location_followup_upserts_pending_intake`:

```python
@pytest.mark.asyncio
async def test_low_confidence_location_creates_confirmation_pending_intake(monkeypatch):
    # A "low"-confidence match must NOT auto-accept and must NOT fall
    # through to the generic "please name a location" prompt -- it needs
    # its own one-question confirmation (F13), closing the real
    # "Yelahanka" -> "Alanka" bug where a weak match was silently dropped.
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.execute.return_value.scalar_one_or_none.return_value = None

    class MockGeminiService:
        def analyze_citizen_report(self, text_content, audio_bytes, mime_type):
            return {
                "original_language": "en",
                "english_translation": text_content,
                "sector": "roads",
                "specific_issue": "pothole",
                "urgency_score": 3.0,
                "sentiment": "negative",
                "location_text_latin": "Alanka",
                "pii_redacted_text": text_content,
            }

        def get_embedding(self, text):
            return [0.1] * 768

    import app.services.ingestion_service as ingestion_module
    monkeypatch.setattr(ingestion_module, "gemini_service", MockGeminiService())

    fake_candidate_region = MagicMock(id=42, name="Yelahanka")
    monkeypatch.setattr(
        ingestion_module,
        "resolve_location_with_confidence",
        AsyncMock(return_value=(fake_candidate_region, "low")),
    )

    result = await ingest_citizen_message(
        db=mock_session,
        text="Potholes near Alanka",
        channel="telegram",
        channel_user_id="user_123",
    )

    assert result["needs_location_confirmation"] is True
    assert result["needs_location_followup"] is False
    assert result["location_confirmation_candidate_name"] == "Yelahanka"

    upsert_call = None
    for call in mock_session.execute.call_args_list:
        stmt = call[0][0]
        if "pending_intake" in str(stmt).lower():
            upsert_call = stmt
            break

    assert upsert_call is not None, "expected a statement touching pending_intake"
    compiled = str(upsert_call.compile(dialect=__import__("sqlalchemy.dialects.postgresql", fromlist=["dialect"]).dialect()))
    assert "ON CONFLICT" in compiled.upper()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_ingestion_service.py -v`
Expected: FAIL — `ingestion_service.py` still imports and calls `resolve_location`, not `resolve_location_with_confidence`, so the new monkeypatch target doesn't exist on the module and/or the result dict lacks the new keys.

- [ ] **Step 3: Implement**

In `backend/app/services/ingestion_service.py`, change the import line:

```python
from app.services.location_resolver import resolve_location
```

to:

```python
from app.services.location_resolver import resolve_location_with_confidence
```

Find this block (inside the `else:` branch that runs when `gemini_failed` is `False`):

```python
            # Resolve location
            region = await resolve_location(
                analysis.get("location_text_latin", ""),
                pack_loader.load_active_pack().country_code,
                db
            )
            
            region_id = region.id if region else None
            needs_location_followup = False
            
            if not region_id and not location_wkt and reporter_hash:
                needs_location_followup = True
```

Replace it with:

```python
            # Resolve location, now confidence-aware (F13): a weak match
            # gets one confirmation question instead of being silently
            # accepted or silently dropped.
            region, location_confidence = await resolve_location_with_confidence(
                analysis.get("location_text_latin", ""),
                pack_loader.load_active_pack().country_code,
                db
            )

            region_id = region.id if location_confidence == "exact" else None
            needs_location_followup = False
            needs_location_confirmation = False
            location_confirmation_candidate_id = None
            location_confirmation_candidate_name = None

            if not region_id and not location_wkt and reporter_hash:
                if location_confidence == "low" and region is not None:
                    needs_location_confirmation = True
                    location_confirmation_candidate_id = region.id
                    location_confirmation_candidate_name = region.name
                else:
                    needs_location_followup = True
```

Find this line (in the `if gemini_failed:` branch, which sets defaults for the failure path):

```python
            needs_location_followup = False
```

Replace it with (adding the two new variables to the failure-path defaults):

```python
            needs_location_followup = False
            needs_location_confirmation = False
            location_confirmation_candidate_id = None
            location_confirmation_candidate_name = None
```

Find the PendingIntake upsert block:

```python
        if needs_location_followup:
            # channel_user_hash is PendingIntake's primary key -- one
            # pending conversation per user at a time. A plain insert
            # crashes with a UniqueViolationError if this same user still
            # has an earlier, unanswered location question outstanding
            # (reproduced live: a voice note that itself needed a location
            # follow-up collided with one from a still-unresolved text
            # report). Upsert instead: the newest report needing a
            # location supersedes an older, presumably-forgotten one --
            # only one pending question can be tracked per user regardless,
            # so the most recent context is the more useful one to keep.
            upsert_stmt = pg_insert(PendingIntake).values(
                channel_user_hash=reporter_hash,
                channel=channel,
                partial_report={"report_id": report.id, "analysis": analysis},
                awaiting="location",
                expires_at=datetime.utcnow() + timedelta(hours=1)
            ).on_conflict_do_update(
                index_elements=[PendingIntake.channel_user_hash],
                set_={
                    "channel": channel,
                    "partial_report": {"report_id": report.id, "analysis": analysis},
                    "awaiting": "location",
                    "expires_at": datetime.utcnow() + timedelta(hours=1)
                }
            )
            await db.execute(upsert_stmt)
            await db.flush()
```

Replace it with:

```python
        if needs_location_followup or needs_location_confirmation:
            # channel_user_hash is PendingIntake's primary key -- one
            # pending conversation per user at a time. A plain insert
            # crashes with a UniqueViolationError if this same user still
            # has an earlier, unanswered location question outstanding.
            # Upsert instead: the newest report needing a location
            # supersedes an older, presumably-forgotten one.
            awaiting = "location_confirmation" if needs_location_confirmation else "location"
            partial_report = {"report_id": report.id, "analysis": analysis}
            if needs_location_confirmation:
                partial_report["candidate_region_id"] = location_confirmation_candidate_id

            upsert_stmt = pg_insert(PendingIntake).values(
                channel_user_hash=reporter_hash,
                channel=channel,
                partial_report=partial_report,
                awaiting=awaiting,
                expires_at=datetime.utcnow() + timedelta(hours=1)
            ).on_conflict_do_update(
                index_elements=[PendingIntake.channel_user_hash],
                set_={
                    "channel": channel,
                    "partial_report": partial_report,
                    "awaiting": awaiting,
                    "expires_at": datetime.utcnow() + timedelta(hours=1)
                }
            )
            await db.execute(upsert_stmt)
            await db.flush()
```

Finally, find the return statement:

```python
        return {
            "status": "success",
            "report_id": report.id,
            "tracking_id": tracking_id,
            "analysis_extracted": analysis if not gemini_failed else None,
            "needs_location_followup": needs_location_followup
        }
```

Replace it with:

```python
        return {
            "status": "success",
            "report_id": report.id,
            "tracking_id": tracking_id,
            "analysis_extracted": analysis if not gemini_failed else None,
            "needs_location_followup": needs_location_followup,
            "needs_location_confirmation": needs_location_confirmation,
            "location_confirmation_candidate_name": location_confirmation_candidate_name,
        }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_ingestion_service.py -v`
Expected: all tests pass, including the updated `test_needs_location_followup_upserts_pending_intake` and the new confirmation test.

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && python -m pytest tests/ -v`
Expected: everything passes.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/ingestion_service.py backend/tests/test_ingestion_service.py
git commit -m "feat: ask for confirmation on low-confidence location matches instead of silently dropping them"
```

---

### Task 3: `telegram_adapter.py` — GPS sharing and confirmation replies

**Files:**
- Modify: `backend/app/services/telegram_adapter.py`
- Test: `backend/tests/test_telegram_adapter.py`

**Interfaces:**
- Consumes: `resolve_gps_location`, `resolve_location` from Task 1; the new `needs_location_confirmation`/`location_confirmation_candidate_name` result keys from Task 2.
- Produces: no new interface for other tasks — this is a leaf.

- [ ] **Step 1: Write the failing tests**

Open `backend/tests/test_telegram_adapter.py`. Add this import near the top, alongside the existing `from app.services.telegram_adapter import handle_telegram_update`:

```python
from app.models.models import PendingIntake, CitizenReport
```

(Skip this line if the file already imports `PendingIntake, CitizenReport` from an earlier test — check first; several existing tests in this file already construct `PendingIntake` objects, so this import likely already exists at the top of the file. Only add it if it's missing.)

Add these tests at the end of the file:

```python
@pytest.mark.asyncio
async def test_telegram_location_message_resolves_pending_intake(monkeypatch):
    # A citizen replying to a location prompt by sharing their GPS location
    # (instead of typing a place name) should resolve immediately via
    # nearest-region lookup -- no transcription, no spelling involved.
    import app.services.telegram_adapter as telegram_module

    pending = PendingIntake(
        channel_user_hash="irrelevant",
        awaiting="location",
        partial_report={"report_id": 42},
        expires_at=telegram_module.datetime(2999, 1, 1),
    )
    resolved_report = MagicMock(spec=CitizenReport)
    resolved_report.tracking_id = "SNG-GPS1"

    mock_session = AsyncMock()
    mock_session.delete = AsyncMock()
    pending_lookup = MagicMock()
    pending_lookup.scalar_one_or_none.return_value = pending
    report_lookup = MagicMock()
    report_lookup.scalar_one_or_none.return_value = resolved_report
    mock_session.execute.side_effect = [pending_lookup, report_lookup]

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_bot_token")

    fake_region = MagicMock(id=7)
    mock_resolve_gps = AsyncMock(return_value=fake_region)
    monkeypatch.setattr(telegram_module, "resolve_gps_location", mock_resolve_gps)

    mock_send = AsyncMock()
    monkeypatch.setattr(telegram_module, "_send_telegram_message", mock_send)

    update_payload = {
        "message": {
            "chat": {"id": 123456},
            "location": {"latitude": 13.1007, "longitude": 77.5963},
        }
    }

    await handle_telegram_update(update_payload, mock_session)

    mock_resolve_gps.assert_called_once()
    mock_send.assert_called_once()
    assert "SNG-GPS1" in mock_send.call_args[0][1]


@pytest.mark.asyncio
async def test_telegram_location_message_with_no_pending_intake_asks_for_description(monkeypatch):
    import app.services.telegram_adapter as telegram_module

    mock_session = AsyncMock()
    pending_lookup = MagicMock()
    pending_lookup.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = pending_lookup

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_bot_token")
    mock_send = AsyncMock()
    monkeypatch.setattr(telegram_module, "_send_telegram_message", mock_send)

    update_payload = {
        "message": {
            "chat": {"id": 123456},
            "location": {"latitude": 13.1007, "longitude": 77.5963},
        }
    }

    await handle_telegram_update(update_payload, mock_session)

    mock_send.assert_called_once()
    assert "describe" in mock_send.call_args[0][1].lower()


@pytest.mark.asyncio
async def test_telegram_confirmation_reply_yes_commits_candidate_region(monkeypatch):
    import app.services.telegram_adapter as telegram_module

    pending = PendingIntake(
        channel_user_hash="irrelevant",
        awaiting="location_confirmation",
        partial_report={"report_id": 42, "candidate_region_id": 7},
        expires_at=telegram_module.datetime(2999, 1, 1),
    )
    resolved_report = MagicMock(spec=CitizenReport)
    resolved_report.tracking_id = "SNG-CONF1"

    mock_session = AsyncMock()
    mock_session.delete = AsyncMock()
    pending_lookup = MagicMock()
    pending_lookup.scalar_one_or_none.return_value = pending
    report_lookup = MagicMock()
    report_lookup.scalar_one_or_none.return_value = resolved_report
    mock_session.execute.side_effect = [pending_lookup, report_lookup]

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_bot_token")
    mock_send = AsyncMock()
    monkeypatch.setattr(telegram_module, "_send_telegram_message", mock_send)

    update_payload = {"message": {"chat": {"id": 123456}, "text": "yes"}}

    await handle_telegram_update(update_payload, mock_session)

    mock_send.assert_called_once()
    assert "SNG-CONF1" in mock_send.call_args[0][1]


@pytest.mark.asyncio
async def test_telegram_confirmation_reply_no_falls_through_to_new_report(monkeypatch):
    # A reply that isn't an affirmative word and doesn't resolve to any
    # location on retry must not be discarded -- same one-question rule
    # (F3) as the plain "location" pending state already follows.
    import app.services.telegram_adapter as telegram_module

    pending = PendingIntake(
        channel_user_hash="irrelevant",
        awaiting="location_confirmation",
        partial_report={"report_id": 42, "candidate_region_id": 7},
        expires_at=telegram_module.datetime(2999, 1, 1),
    )
    old_report = MagicMock(spec=CitizenReport)
    old_report.tracking_id = "SNG-OLD9"

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.delete = AsyncMock()
    pending_lookup = MagicMock()
    pending_lookup.scalar_one_or_none.return_value = pending
    old_report_lookup = MagicMock()
    old_report_lookup.scalar_one_or_none.return_value = old_report
    mock_session.execute.side_effect = [pending_lookup, old_report_lookup]

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_bot_token")
    monkeypatch.setattr(telegram_module, "resolve_location", AsyncMock(return_value=None))

    mock_ingest = AsyncMock(return_value={"tracking_id": "SNG-NEW9"})
    monkeypatch.setattr(telegram_module, "ingest_citizen_message", mock_ingest)
    mock_send = AsyncMock()
    monkeypatch.setattr(telegram_module, "_send_telegram_message", mock_send)

    update_payload = {"message": {"chat": {"id": 123456}, "text": "who is narendra modi"}}

    await handle_telegram_update(update_payload, mock_session)

    mock_ingest.assert_called_once()
    assert mock_send.call_count == 2
    assert "SNG-OLD9" in mock_send.call_args_list[0][0][1]
    assert "SNG-NEW9" in mock_send.call_args_list[1][0][1]


@pytest.mark.asyncio
async def test_ingest_reply_asks_for_confirmation_when_flagged(monkeypatch):
    import app.services.telegram_adapter as telegram_module

    mock_session = AsyncMock()
    pending_lookup = MagicMock()
    pending_lookup.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = pending_lookup

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_bot_token")
    mock_ingest = AsyncMock(return_value={
        "tracking_id": "SNG-LOW1",
        "needs_location_followup": False,
        "needs_location_confirmation": True,
        "location_confirmation_candidate_name": "Yelahanka",
    })
    monkeypatch.setattr(telegram_module, "ingest_citizen_message", mock_ingest)
    mock_send = AsyncMock()
    monkeypatch.setattr(telegram_module, "_send_telegram_message", mock_send)

    update_payload = {"message": {"chat": {"id": 123456}, "text": "potholes near alanka"}}

    await handle_telegram_update(update_payload, mock_session)

    mock_send.assert_called_once()
    reply = mock_send.call_args[0][1]
    assert "Yelahanka" in reply
    assert "YES" in reply
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_telegram_adapter.py -v`
Expected: FAIL — `resolve_gps_location` isn't imported/used yet, `location` messages aren't handled, `awaiting == "location_confirmation"` isn't handled, and the confirmation reply text doesn't exist.

- [ ] **Step 3: Implement**

In `backend/app/services/telegram_adapter.py`, change the import line:

```python
from app.services.location_resolver import resolve_location
```

to:

```python
from app.services.location_resolver import resolve_location, resolve_gps_location
```

Find this line:

```python
    text = message.get("text")
    voice = message.get("voice")
    photo = message.get("photo")
```

Replace it with:

```python
    text = message.get("text")
    voice = message.get("voice")
    photo = message.get("photo")
    location = message.get("location")
```

Find this block (right after the pending-intake lookup, before the existing `if pending and pending.awaiting == "location":` line):

```python
    db_result = await db.execute(stmt)
    pending = db_result.scalar_one_or_none()
    
    if pending and pending.awaiting == "location":
```

Replace it with (inserting the new GPS-handling block between the lookup and the existing text-based block):

```python
    db_result = await db.execute(stmt)
    pending = db_result.scalar_one_or_none()

    # Native GPS location (F12) takes priority over any pending text-based
    # location flow -- it's authoritative where a typed guess is not, and
    # applies whether the citizen was asked to name a place or to confirm
    # a weak guess.
    if location and pending and pending.awaiting in ("location", "location_confirmation"):
        try:
            lat = location.get("latitude")
            lon = location.get("longitude")
            report_id = pending.partial_report.get("report_id")
            await db.delete(pending)

            region = (
                await resolve_gps_location(lat, lon, pack_loader.load_active_pack().country_code, db)
                if lat is not None and lon is not None else None
            )

            if region and report_id:
                await db.execute(
                    update(CitizenReport).where(CitizenReport.id == report_id).values(region_id=region.id)
                )
                await db.commit()
                r_res = await db.execute(select(CitizenReport).where(CitizenReport.id == report_id))
                r = r_res.scalar_one_or_none()
                tracking_id = r.tracking_id if r else "Unknown"
                await _send_telegram_message(chat_id, f"Location updated successfully. Thank you. Tracking ID: {tracking_id}", bot_token)
            elif report_id:
                await db.commit()
                r_res = await db.execute(select(CitizenReport).where(CitizenReport.id == report_id))
                r = r_res.scalar_one_or_none()
                tracking_id = r.tracking_id if r else "Unknown"
                await _send_telegram_message(
                    chat_id,
                    f"We couldn't match that location to a known area for your report (Tracking ID: {tracking_id}) -- it's saved without one.",
                    bot_token
                )
            return
        except Exception as e:
            logger.error(f"Error resolving GPS location for pending intake: {e}")
            await db.rollback()
            await _send_telegram_message(chat_id, "Sorry, there was an error processing your location. Please try again later.", bot_token)
            return

    if location and not pending:
        await _send_telegram_message(
            chat_id,
            "Thanks for sharing your location. Please also send a text message, voice note, or photo describing the infrastructure issue.",
            bot_token
        )
        return

    AFFIRMATIVE_WORDS = {"yes", "y", "yeah", "yep", "yup", "correct", "confirm", "ok", "okay", "ha", "haan", "ho"}

    if pending and pending.awaiting == "location_confirmation":
        try:
            report_id = pending.partial_report.get("report_id")
            candidate_region_id = pending.partial_report.get("candidate_region_id")
            await db.delete(pending)

            normalized_reply = (text or "").strip().lower()
            confirmed = normalized_reply in AFFIRMATIVE_WORDS

            if confirmed and candidate_region_id and report_id:
                await db.execute(
                    update(CitizenReport).where(CitizenReport.id == report_id).values(region_id=candidate_region_id)
                )
                await db.commit()
                r_res = await db.execute(select(CitizenReport).where(CitizenReport.id == report_id))
                r = r_res.scalar_one_or_none()
                tracking_id = r.tracking_id if r else "Unknown"
                await _send_telegram_message(chat_id, f"Got it, thank you. Tracking ID: {tracking_id}", bot_token)
                return
            elif report_id:
                # Not a confirmation -- try it as a fresh location guess,
                # auto-accept only (no second confirmation round, keeping
                # F3's one-question rule).
                fresh_region = await resolve_location(
                    text, pack_loader.load_active_pack().country_code, db
                ) if text else None
                await db.commit()
                r_res = await db.execute(select(CitizenReport).where(CitizenReport.id == report_id))
                r = r_res.scalar_one_or_none()
                tracking_id = r.tracking_id if r else "Unknown"

                if fresh_region:
                    await db.execute(
                        update(CitizenReport).where(CitizenReport.id == report_id).values(region_id=fresh_region.id)
                    )
                    await db.commit()
                    await _send_telegram_message(chat_id, f"Location updated successfully. Thank you. Tracking ID: {tracking_id}", bot_token)
                    return
                else:
                    await _send_telegram_message(
                        chat_id,
                        f"No problem -- your report (Tracking ID: {tracking_id}) is saved without a confirmed location. "
                        "Treating this message as a new report...",
                        bot_token
                    )
        except Exception as e:
            logger.error(f"Error resolving pending location confirmation: {e}")
            await db.rollback()
            await _send_telegram_message(chat_id, "Sorry, there was an error processing your report. Please try again later.", bot_token)
            return

    if pending and pending.awaiting == "location":
```

(That last line, `if pending and pending.awaiting == "location":`, is the original line the block above it was replacing the start of — it must still be there afterward, unchanged, along with everything that already follows it. You are inserting new blocks BEFORE it, not replacing the existing "location" handling logic itself.)

Find the final reply-building block:

```python
        tracking_id = result["tracking_id"]
        if result.get("needs_location_followup"):
            reply_text = f"Thank you. We received your report (Tracking ID: {tracking_id}), but we couldn't detect a specific location. Could you please reply with the name of the ward, block, or district this relates to?"
        else:
            reply_text = f"Thank you. Your report has been securely received.\n\nTracking ID: {tracking_id}\n\nYou can use this tracking ID to check the status of your report."
            
        await _send_telegram_message(chat_id, reply_text, bot_token)
```

Replace it with:

```python
        tracking_id = result["tracking_id"]
        if result.get("needs_location_confirmation"):
            candidate_name = result.get("location_confirmation_candidate_name") or "that location"
            reply_text = (
                f"Thank you. We received your report (Tracking ID: {tracking_id}). "
                f"Did you mean {candidate_name}? Reply YES to confirm, or send the correct ward/area name."
            )
        elif result.get("needs_location_followup"):
            reply_text = f"Thank you. We received your report (Tracking ID: {tracking_id}), but we couldn't detect a specific location. Could you please reply with the name of the ward, block, or district this relates to?"
        else:
            reply_text = f"Thank you. Your report has been securely received.\n\nTracking ID: {tracking_id}\n\nYou can use this tracking ID to check the status of your report."
            
        await _send_telegram_message(chat_id, reply_text, bot_token)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_telegram_adapter.py -v`
Expected: all tests pass, including every pre-existing test in this file (the `/start` command test, the photo test, the pending-location tests already there).

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && python -m pytest tests/ -v`
Expected: everything passes.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/telegram_adapter.py backend/tests/test_telegram_adapter.py
git commit -m "feat: handle native GPS location sharing and location-confirmation replies on Telegram"
```

---

### Task 4: `whatsapp_adapter.py` — mirror Task 3 for WhatsApp

**Files:**
- Modify: `backend/app/services/whatsapp_adapter.py`
- Test: `backend/tests/test_whatsapp_adapter.py`

**Interfaces:**
- Consumes: the same functions Task 3 consumes.
- Produces: nothing new — a leaf, parallel to Task 3.

Meta's WhatsApp Cloud API sends a location message as `message["type"] == "location"` with `message["location"] = {"latitude": ..., "longitude": ..., "name": ..., "address": ...}` — the same field names Telegram uses for latitude/longitude, so the resolution logic is identical; only the message-type detection and the reply-sending function name differ from Telegram.

- [ ] **Step 1: Write the failing tests**

Open `backend/tests/test_whatsapp_adapter.py`. Add these tests at the end of the file, following whatever import/fixture pattern the existing tests in this file already use (check the top of the file for how `PendingIntake`, `CitizenReport`, and `handle_whatsapp_update` are imported, and match it):

```python
@pytest.mark.asyncio
async def test_whatsapp_location_message_resolves_pending_intake(monkeypatch):
    import app.services.whatsapp_adapter as whatsapp_module

    pending = PendingIntake(
        channel_user_hash="irrelevant",
        awaiting="location",
        partial_report={"report_id": 42},
        expires_at=whatsapp_module.datetime(2999, 1, 1),
    )
    resolved_report = MagicMock(spec=CitizenReport)
    resolved_report.tracking_id = "SNG-WGPS1"

    mock_session = AsyncMock()
    mock_session.delete = AsyncMock()
    pending_lookup = MagicMock()
    pending_lookup.scalar_one_or_none.return_value = pending
    report_lookup = MagicMock()
    report_lookup.scalar_one_or_none.return_value = resolved_report
    mock_session.execute.side_effect = [pending_lookup, report_lookup]

    mock_resolve_gps = AsyncMock(return_value=MagicMock(id=7))
    monkeypatch.setattr(whatsapp_module, "resolve_gps_location", mock_resolve_gps)
    mock_send = AsyncMock()
    monkeypatch.setattr(whatsapp_module, "_send_whatsapp_message", mock_send)

    payload = {
        "entry": [{"changes": [{"value": {"messages": [{
            "from": "15551234567",
            "type": "location",
            "location": {"latitude": 13.1007, "longitude": 77.5963},
        }]}}]}]
    }

    await handle_whatsapp_update(payload, mock_session)

    mock_resolve_gps.assert_called_once()
    mock_send.assert_called_once()
    assert "SNG-WGPS1" in mock_send.call_args[0][1]


@pytest.mark.asyncio
async def test_whatsapp_confirmation_reply_yes_commits_candidate_region(monkeypatch):
    import app.services.whatsapp_adapter as whatsapp_module

    pending = PendingIntake(
        channel_user_hash="irrelevant",
        awaiting="location_confirmation",
        partial_report={"report_id": 42, "candidate_region_id": 7},
        expires_at=whatsapp_module.datetime(2999, 1, 1),
    )
    resolved_report = MagicMock(spec=CitizenReport)
    resolved_report.tracking_id = "SNG-WCONF1"

    mock_session = AsyncMock()
    mock_session.delete = AsyncMock()
    pending_lookup = MagicMock()
    pending_lookup.scalar_one_or_none.return_value = pending
    report_lookup = MagicMock()
    report_lookup.scalar_one_or_none.return_value = resolved_report
    mock_session.execute.side_effect = [pending_lookup, report_lookup]

    mock_send = AsyncMock()
    monkeypatch.setattr(whatsapp_module, "_send_whatsapp_message", mock_send)

    payload = {
        "entry": [{"changes": [{"value": {"messages": [{
            "from": "15551234567",
            "type": "text",
            "text": {"body": "yes"},
        }]}}]}]
    }

    await handle_whatsapp_update(payload, mock_session)

    mock_send.assert_called_once()
    assert "SNG-WCONF1" in mock_send.call_args[0][1]


@pytest.mark.asyncio
async def test_whatsapp_ingest_reply_asks_for_confirmation_when_flagged(monkeypatch):
    import app.services.whatsapp_adapter as whatsapp_module

    mock_session = AsyncMock()
    pending_lookup = MagicMock()
    pending_lookup.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = pending_lookup

    mock_ingest = AsyncMock(return_value={
        "tracking_id": "SNG-WLOW1",
        "needs_location_followup": False,
        "needs_location_confirmation": True,
        "location_confirmation_candidate_name": "Yelahanka",
    })
    monkeypatch.setattr(whatsapp_module, "ingest_citizen_message", mock_ingest)
    mock_send = AsyncMock()
    monkeypatch.setattr(whatsapp_module, "_send_whatsapp_message", mock_send)

    payload = {
        "entry": [{"changes": [{"value": {"messages": [{
            "from": "15551234567",
            "type": "text",
            "text": {"body": "potholes near alanka"},
        }]}}]}]
    }

    await handle_whatsapp_update(payload, mock_session)

    mock_send.assert_called_once()
    reply = mock_send.call_args[0][1]
    assert "Yelahanka" in reply
    assert "YES" in reply
```

If `PendingIntake`, `CitizenReport`, `MagicMock`, `AsyncMock` aren't already imported at the top of `test_whatsapp_adapter.py`, add whatever imports are missing, matching the exact import style already used elsewhere in that file.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_whatsapp_adapter.py -v`
Expected: FAIL, for the same reasons as Task 3's Step 2.

- [ ] **Step 3: Implement**

Apply the exact same set of changes described in Task 3's Step 3 to `backend/app/services/whatsapp_adapter.py`, adjusted only for this file's existing naming:

1. Change the import line `from app.services.location_resolver import resolve_location` to `from app.services.location_resolver import resolve_location, resolve_gps_location`.
2. After `text = message.get("text", {}).get("body") if msg_type == "text" else None`, add: `location = message.get("location") if msg_type == "location" else None`.
3. Insert the same GPS-handling block, no-pending-fallback block, and `AFFIRMATIVE_WORDS`/`location_confirmation` handling block as Task 3, positioned identically (after the pending-intake lookup, before the existing `if pending and pending.awaiting == "location":` block) — substituting `_send_whatsapp_message(from_number, ..., access_token, phone_number_id)` everywhere Task 3 used `_send_telegram_message(chat_id, ..., bot_token)`, matching this file's existing call signature for that function (check the existing `_send_whatsapp_message` calls already in this file for the exact parameter order).
4. Apply the same reply-building change (the `needs_location_confirmation` branch added before the existing `needs_location_followup` branch) to this file's final reply-building block, keeping this file's existing `from_number`/`access_token`/`phone_number_id` parameters in the `_send_whatsapp_message` calls.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_whatsapp_adapter.py -v`
Expected: all tests pass, including every pre-existing test in this file.

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && python -m pytest tests/ -v`
Expected: everything passes — this is the last task in the plan, so this is the final green run.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/whatsapp_adapter.py backend/tests/test_whatsapp_adapter.py
git commit -m "feat: handle native GPS location sharing and location-confirmation replies on WhatsApp"
```
