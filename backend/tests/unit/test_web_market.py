from app.services.web_market import is_blocked_host, reliable_web_context


def test_blocks_facebook():
    assert is_blocked_host("https://www.facebook.com/groups/scrap/posts/1")
    assert not is_blocked_host("https://www.dawn.com/news/scrap-rates")


def test_drops_social_and_foreign_currency():
    raw = {
        "answer": "Rates look stable worldwide.",
        "results": [
            {
                "title": "Today Karachi PET scrap scrap rate?",
                "content": "Comment your rate",
                "url": "https://www.facebook.com/groups/pet/posts/99",
            },
            {
                "title": "Delhi PET INR 45/kg",
                "content": "India scrap PET INR 45 per kg",
                "url": "https://example.in/delhi-pet",
            },
        ],
    }
    clean = reliable_web_context(
        raw, currency="PKR", country="Pakistan", city="Karachi", material="plastic_pet"
    )
    assert clean["sources"] == []
    assert clean["context"] is None


def test_keeps_same_market_in_band_listing():
    raw = {
        "answer": "",
        "results": [
            {
                "title": "Karachi scrap yard list",
                "content": "PET bottles in Pakistan trade near PKR 135/kg this week.",
                "url": "https://www.dawn.com/news/karachi-scrap",
            }
        ],
    }
    clean = reliable_web_context(
        raw, currency="PKR", country="Pakistan", city="Karachi", material="plastic_pet"
    )
    assert clean["sources"] == ["https://www.dawn.com/news/karachi-scrap"]
    assert clean["prices"] == [135.0]
    assert "135" in (clean["context"] or "")
    assert "not a logged sale" in (clean["context"] or "")


def test_keeps_rs_per_kg_when_request_is_pakistan():
    raw = {
        "results": [
            {
                "title": "Karachi PET yard",
                "content": "PET bottles 135 Rs/kg this week.",
                "url": "https://www.dawn.com/news/karachi-pet",
            }
        ]
    }
    clean = reliable_web_context(
        raw, currency="PKR", country="Pakistan", city="Karachi", material="plastic_pet"
    )
    assert clean["prices"] == [135.0]
    assert clean["sources"] == ["https://www.dawn.com/news/karachi-pet"]


def test_keeps_usd_per_kg_listing():
    raw = {
        "results": [
            {
                "title": "Chicago PET scrap",
                "content": "PET flake USD 1.20 per kg at local yards.",
                "url": "https://recycle.example/chicago-pet",
            }
        ]
    }
    clean = reliable_web_context(
        raw,
        currency="USD",
        country="United States",
        city="Chicago",
        material="plastic_pet",
    )
    assert clean["prices"] == [1.2]
    assert "1.20" in (clean["context"] or "")


def test_usd_listing_does_not_price_pkr_request():
    raw = {
        "results": [
            {
                "title": "US PET",
                "content": "PET USD 1.20/kg",
                "url": "https://recycle.example/us-pet",
            }
        ]
    }
    clean = reliable_web_context(
        raw, currency="PKR", country="Pakistan", city="Karachi", material="plastic_pet"
    )
    assert clean["prices"] == []


def test_rejects_out_of_band_pkr():
    raw = {
        "results": [
            {
                "title": "Karachi PET",
                "content": "Pakistan PET PKR 900/kg",
                "url": "https://news.example/karachi",
            }
        ]
    }
    clean = reliable_web_context(
        raw, currency="PKR", country="Pakistan", city="Karachi", material="plastic_pet"
    )
    assert clean["prices"] == []
    assert clean["sources"] == []
