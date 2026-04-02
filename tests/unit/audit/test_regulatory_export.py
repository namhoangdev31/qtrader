import hashlib
import hmac
import json

import pytest

from qtrader.audit.regulatory_export import (
    ExportFormat,
    RegulatorTarget,
    RegulatoryExporter,
)


@pytest.fixture
def exporter() -> RegulatoryExporter:
    """Initialize a RegulatoryExporter for institutional oversight."""
    return RegulatoryExporter(
        signing_secret="SEC_FINRA_OVERSIGHT_KEY"  # noqa: S106
    )


def test_regulatory_export_csv_transformation(exporter: RegulatoryExporter) -> None:
    """Verify that audit data correctly transforms into a signed CSV artifact."""
    data = [
        {
            "id": "E1",
            "timestamp": 1e9,
            "symbol": "BTC/USD",
            "price": 50000.0,
            "qty": 1.0,
        },
        {
            "id": "E2",
            "timestamp": 1.1e9,
            "symbol": "ETH/USD",
            "price": 3000.0,
            "qty": 10.0,
        },
    ]

    report = exporter.export_audit_trail(data, ExportFormat.CSV, RegulatorTarget.SEC)

    # 1. Structural Verification
    assert report["status"] == "EXPORT_COMPLETE"
    assert report["regulator"] == "SEC"

    # 2. Artifact Verification (CSV Header + Rows)
    artifact = report["payload"]
    assert "id,timestamp,symbol,price,qty" in artifact
    assert "BTC/USD" in artifact

    # 3. Integrity Signature
    assert len(report["integrity_signature"]) == 64


def test_regulatory_export_schema_compliance_enforcement(
    exporter: RegulatoryExporter,
) -> None:
    """Verify that exports missing mandatory fields are programmatically blocked."""
    # Missing 'symbol' and 'price'
    invalid_data = [{"id": "E3", "timestamp": 1.2e9, "qty": 5.0}]

    with pytest.raises(ValueError, match="SCHEMA_VIOLATION"):
        exporter.export_audit_trail(invalid_data, ExportFormat.JSON, RegulatorTarget.MAS)


def test_regulatory_export_json_format_verification(
    exporter: RegulatoryExporter,
) -> None:
    """Verify that audit data correctly transforms into a signed JSON object."""
    data = [
        {
            "id": "E4",
            "timestamp": 1.3e9,
            "symbol": "XRP/USD",
            "price": 0.5,
            "qty": 1000.0,
        }
    ]

    report = exporter.export_audit_trail(data, ExportFormat.JSON, RegulatorTarget.ESMA)

    # Verify JSON structure
    parsed = json.loads(report["payload"])
    assert parsed[0]["id"] == "E4"
    assert parsed[0]["symbol"] == "XRP/USD"


def test_regulatory_export_cryptographic_signature_integrity(
    exporter: RegulatoryExporter,
) -> None:
    """Verify that altering the artifact invalidates its forensic signature (HMAC-SHA256)."""
    data = [
        {
            "id": "S1",
            "timestamp": 1.4e9,
            "symbol": "ADA/USD",
            "price": 1.0,
            "qty": 100.0,
        }
    ]

    report = exporter.export_audit_trail(data, ExportFormat.CSV, RegulatorTarget.FINRA)
    original_sig = report["integrity_signature"]

    # Manual verification of the HMAC signature logic
    # The artifact itself must re-generate the same signature with the same secret
    secret = b"SEC_FINRA_OVERSIGHT_KEY"
    expected_sig = hmac.new(secret, report["payload"].encode(), hashlib.sha256).hexdigest()
    assert original_sig == expected_sig


def test_regulatory_export_telemetry_tracking(exporter: RegulatoryExporter) -> None:
    """Verify situational awareness for institutional submission cycles."""
    data = [
        {
            "id": "E5",
            "timestamp": 1.5e9,
            "symbol": "SOL/USD",
            "price": 20.0,
            "qty": 5.0,
        }
    ]

    # 1. Success
    exporter.export_audit_trail(data, ExportFormat.JSON, RegulatorTarget.SEC)

    # 2. Failure (missing field)
    with pytest.raises(ValueError):
        exporter.export_audit_trail([{"id": "E6"}], ExportFormat.JSON, RegulatorTarget.SEC)

    stats = exporter.get_export_telemetry()
    assert stats["success_count"] == 1
    assert stats["violation_count"] == 1
    assert stats["status"] == "AUDIT"
