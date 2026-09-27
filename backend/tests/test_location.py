from app.features.intake.location import Gazetteer, normalise
from app.models import Region


def gazetteer():
    return Gazetteer([
        Region(id="TL", level=0, name="Testland", name_variants=[]),
        Region(id="N", level=2, name="Northfield", name_variants=["Nordstadt"], lat=12.0, lon=77.0),
        Region(id="S", level=2, name="Southmere", name_variants=[], lat=11.0, lon=77.0),
        Region(id="N-R", level=3, name="Riverton", name_variants=[], parent_id="N", lat=12.05, lon=77.05),
        Region(id="N-H", level=3, name="Hillview", name_variants=[], parent_id="N"),
    ])


def test_exact_name_and_variant_match_fully():
    g = gazetteer()
    assert (g.resolve(["Northfield"]).region_id, g.resolve(["Northfield"]).score) == ("N", 100.0)
    assert g.resolve(["nordstadt"]).region_id == "N"


def test_place_is_found_inside_a_longer_description():
    assert gazetteer().resolve(["near the bus stand, Riverton village"]).region_id == "N-R"


def test_misspelling_scores_between_confirm_and_accept():
    match = gazetteer().resolve(["Riverdon"])
    assert match.region_id == "N-R" and 75 <= match.score < 100


def test_country_level_is_never_matched():
    assert gazetteer().resolve(["Testland"]).region_id != "TL"


def test_generic_words_come_from_the_pack():
    assert normalise("Southmere village") == "southmere"
    g = Gazetteer([Region(id="S", level=2, name="Southmere", name_variants=[])], generic_words=["county"])
    assert g.resolve(["Southmere County"]).score == 100.0


def test_gps_prefers_a_nearby_block_then_falls_back_to_district():
    g = gazetteer()
    assert g.nearest(12.04, 77.04).region_id == "N-R"
    assert g.nearest(11.0, 77.0).region_id == "S"  # nearest block is > 30 km away
