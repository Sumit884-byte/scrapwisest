from app.agent.nemotron import nearest_region, normalize_region, public_regions, resolve_region


def test_nearest_europe_and_us():
    assert nearest_region(59.33, 18.07) == "eu-north1"
    assert nearest_region(41.88, -87.63) == "us-central1"
    assert nearest_region(28.61, 77.21) == "eu-north1"


def test_normalize_and_resolve():
    assert normalize_region("EU-NORTH1") == "eu-north1"
    assert normalize_region("nowhere") is None
    assert resolve_region(None) == "us-central1"
    assert resolve_region("eu-north1") == "eu-north1"


def test_public_regions_match_catalog():
    ids = {r["id"] for r in public_regions()}
    assert ids == {"eu-north1", "us-central1"}
