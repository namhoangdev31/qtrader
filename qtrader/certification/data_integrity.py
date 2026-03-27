from __future__ import annotations

import hashlib
import logging
import time
from enum import Enum, auto
from typing import Any

import polars as pl

_LOG = logging.getLogger("qtrader.certification.data_integrity")


class IntegrityResult(Enum):
    """
    Industrial Data Veracity Outcomes.
    Determines if the dataset is structurally compliant for ingestion.
    """

    PASS = auto()
    FAIL = auto()


class DataIntegrityValidator:
    """
    Principal Data Integrity Validator.

    Objective: Certify the structural veracity and causal ordering of market data.
    Model: Vectorized Anomalies Scan with SHA-256 Cryptographic Fingerprinting.
    """

    def __init__(self) -> None:
        """
        Initialize the institutional data veracity controller.
        """
        self._stats = {
            "scanned_records": 0,
            "anomaly_count": 0,
            "last_duplicate_rate": 0.0,
        }

    def validate_dataset(
        self, dataset: pl.DataFrame, expected_hash: str | None = None
    ) -> dict[str, Any]:
        """
        Execute vectorized structural veracity scan for ingestion readiness.

        Forensic Logic:
        1. Temporal Audit: Enforces strictly increasing timestamps (Causality).
        2. Duplicate Analysis: Detects bit-perfect row identicality.
        3. Corruption Check: Gating for Price > 0 and Qty >= 0 (Sanity).
        4. Hash Fingerprinting: Validates data lineage via SHA-256.
        """
        start_time = time.time()
        record_count = len(dataset)
        self._stats["scanned_records"] += record_count

        if record_count == 0:
            return {
                "status": "DATA_CHECK_EMPTY",
                "result": IntegrityResult.PASS.name,
                "checks": {"record_count": 0},
            }

        is_ordered = bool(dataset["timestamp"].is_sorted())
        if is_ordered and record_count > 1:
            timestamp_unique_count = dataset["timestamp"].n_unique()
            is_ordered = timestamp_unique_count == record_count

        duplicate_mask = dataset.is_duplicated()
        duplicate_count = int(duplicate_mask.sum())
        self._stats["last_duplicate_rate"] = (
            duplicate_count / record_count if record_count > 0 else 0.0
        )

        corruption_filter = (pl.col("price") <= 0) | (pl.col("qty") < 0)
        corrupted_record_count = int(dataset.filter(corruption_filter).height)

        hash_buffer = str(dataset.to_dicts()).encode("utf-8")
        current_hash = hashlib.sha256(hash_buffer).hexdigest()

        hash_verified = True
        if expected_hash and current_hash != expected_hash:
            hash_verified = False
            _LOG.error(
                f"[DATA_CHECK] HASH_MISMATCH | Current: {current_hash} | Expected: {expected_hash}"
            )

        overall_integrity = (
            is_ordered
            and (duplicate_count == 0)
            and (corrupted_record_count == 0)
            and hash_verified
        )

        result = IntegrityResult.PASS if overall_integrity else IntegrityResult.FAIL

        if result == IntegrityResult.FAIL:
            self._stats["anomaly_count"] += 1
            _LOG.warning(
                f"[DATA_CHECK] INTEGRITY_BREACH | Ordered: {is_ordered} | "
                f"Dupes: {duplicate_count} | Corrupted: {corrupted_record_count}"
            )

        artifact = {
            "status": "DATA_CHECK_COMPLETE",
            "result": result.name,
            "checks": {
                "monotonic_ordering": is_ordered,
                "duplicate_count": duplicate_count,
                "corruption_count": corrupted_record_count,
                "integrity_hash": current_hash,
                "lineage_verified": hash_verified if expected_hash else "N/A",
            },
            "certification": {
                "anomalous_record_count": duplicate_count + corrupted_record_count,
                "timestamp": time.time(),
                "scan_latency_ms": round((time.time() - start_time) * 1000, 4),
            },
        }

        return artifact

    def get_integrity_telemetry(self) -> dict[str, Any]:
        """
        situational awareness for institutional dataset health.
        """
        return {
            "status": "DATA_HEALTH",
            "total_records_analyzed": self._stats["scanned_records"],
            "anomalous_dataset_count": self._stats["anomaly_count"],
            "last_duplicate_rate": self._stats["last_duplicate_rate"],
        }
