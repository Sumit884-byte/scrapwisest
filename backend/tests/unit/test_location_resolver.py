from app.services.location_resolver import normalize_location


def test_location_aliases_share_a_canonical_name():
    assert normalize_location("Income Colony") == "Income Colony"
    assert normalize_location("income colony ke qareeb, Multan") == "Income Colony"
    assert normalize_location("Bosan Rd") == "Bosan Road"


def test_unknown_location_is_retained_in_title_case():
    assert normalize_location("  new market  ") == "New Market"
