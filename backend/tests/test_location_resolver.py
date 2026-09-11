import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.location_resolver import resolve_location, resolve_gps_location
from app.models.models import AdminRegion

@pytest.fixture
def mock_db_session():
    mock_session = AsyncMock()
    
    # Setup some mock regions
    bengaluru = AdminRegion(
        id=1,
        country_code="IN",
        level="district",
        name="Bengaluru",
        name_variants="Bangalore|Bengaluru Urban"
    )
    kalaburagi = AdminRegion(
        id=2,
        country_code="IN",
        level="district",
        name="Kalaburagi",
        name_variants="Gulbarga"
    )
    mysuru = AdminRegion(
        id=3,
        country_code="IN",
        level="district",
        name="Mysuru",
        name_variants="Mysore"
    )
    
    # Configure execute to return the list of regions
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [bengaluru, kalaburagi, mysuru]
    mock_session.execute.return_value = mock_result
    
    return mock_session

@pytest.mark.asyncio
async def test_resolve_exact_match(mock_db_session):
    # Exact match (case-insensitive)
    region = await resolve_location("MYSURU", "IN", mock_db_session)
    assert region is not None
    assert region.name == "Mysuru"

@pytest.mark.asyncio
async def test_resolve_alternate_spelling_bangalore(mock_db_session):
    # Alternate spelling in name_variants
    region = await resolve_location("Bangalore", "IN", mock_db_session)
    assert region is not None
    assert region.name == "Bengaluru"

@pytest.mark.asyncio
async def test_resolve_pre_2014_name_gulbarga(mock_db_session):
    # Pre-2014 district name
    region = await resolve_location("Gulbarga", "IN", mock_db_session)
    assert region is not None
    assert region.name == "Kalaburagi"

@pytest.mark.asyncio
async def test_resolve_unresolvable_string(mock_db_session):
    # Genuinely unresolvable string
    region = await resolve_location("Atlantis", "IN", mock_db_session)
    assert region is None

@pytest.mark.asyncio
async def test_resolve_empty_string(mock_db_session):
    # Empty string should return None and not query the DB
    region = await resolve_location("", "IN", mock_db_session)
    assert region is None
    mock_db_session.execute.assert_not_called()


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
