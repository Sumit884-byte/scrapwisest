from __future__ import annotations

from datetime import datetime, timezone
from app.schemas.report import MaterialType, PriceReport
from app.services.anomaly_detector import _features, anomaly_detector_service


def _sample_report(price_per_kg: float) -> PriceReport:
    return PriceReport(
        material_type=MaterialType.PLASTIC_PET,
        quantity_kg=10.0,
        price_paid_pkr=price_per_kg * 10.0,
        price_paid_pkr_per_kg=price_per_kg,
        location="Income Colony",
        timestamp=datetime.now(timezone.utc),
    )


def test_features_calculation():
    feat = _features(100.0, 10.0, 100.0)
    assert len(feat) == 2
    assert feat[0] == 1.0  # price_ratio
    assert feat[1] > 0  # np.log1p(10.0)


def test_deterministic_insufficient_history():
    report = _sample_report(100.0)
    # With fewer than 3 history reports, accepted by default
    verdict = anomaly_detector_service.deterministic_check(report, [100.0, 105.0])
    assert verdict.is_anomalous is False
    assert "not enough regional history" in verdict.reason


def test_deterministic_normal_price():
    report = _sample_report(100.0)
    # Median is 100.0, price is 100.0 -> normal
    verdict = anomaly_detector_service.deterministic_check(report, [95.0, 100.0, 105.0])
    assert verdict.is_anomalous is False
    assert "within normal range" in verdict.reason


def test_deterministic_too_low():
    report = _sample_report(40.0)  # Under 0.5 * 100.0
    verdict = anomaly_detector_service.deterministic_check(report, [95.0, 100.0, 105.0])
    assert verdict.is_anomalous is True
    assert "under half" in verdict.reason


def test_deterministic_too_high():
    report = _sample_report(250.0)  # Over 2.0 * 100.0
    verdict = anomaly_detector_service.deterministic_check(report, [95.0, 100.0, 105.0])
    assert verdict.is_anomalous is True
    assert "over double" in verdict.reason
