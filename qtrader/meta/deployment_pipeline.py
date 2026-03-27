from __future__ import annotations

import logging
from typing import Any

_LOG = logging.getLogger("qtrader.meta.deployment_pipeline")


class DeploymentPipeline:
    """
    Principal Deployment Controller.

    Ensures that no strategy attains 'LIVE' status unless it has successfully
    navigated the full meta-governance chain:
    APPROVED -> CAPITAL_ALLOCATED -> SHADOW_PASS -> LIVE.
    """

    def __init__(self) -> None:
        """
        Initialize the deployment telemetry.
        """
        self._stats = {"deployed": 0, "rejected": 0}

    def request_deployment(
        self, strategy_id: str, is_approved: bool, allocation: float, shadow_pass: bool
    ) -> dict[str, Any]:
        """
        Evaluate the promotion request for the candidate alpha signal.

        Args:
            strategy_id: Unique identifier for the strategy.
            is_approved: Formal sign-off from the StrategyApprovalSystem.
            allocation: Capital weight from the CapitalAllocator.
            shadow_pass: Pass/Fail result from the ShadowEnforcer.

        Returns:
            dict containing deployment_status (LIVE/REJECTED) and audit reasons.
        """
        rejections: list[str] = []

        # 1. Gate 1: Institutional Approval
        if not is_approved:
            rejections.append("NOT_APPROVED_BY_COMMITTEE")

        # 2. Gate 2: Positive Risk Allocation
        if allocation <= 0:
            rejections.append("ZERO_CAPITAL_ALLOCATION")

        # 3. Gate 3: Live Verification Pass
        if not shadow_pass:
            rejections.append("SHADOW_MODE_VALIDATION_FAILURE")

        # Terminal Decision Logic
        if rejections:
            self._stats["rejected"] += 1
            _LOG.warning(f"REJECTED | {strategy_id} | Reasons: {', '.join(rejections)}")
            return {
                "status": "DEPLOYMENT",
                "result": "REJECTED",
                "reasons": rejections,
            }

        self._stats["deployed"] += 1
        _LOG.info(f"LIVE | {strategy_id} | Deployment authorized for production.")
        return {
            "status": "DEPLOYMENT",
            "result": "LIVE",
            "allocation": round(allocation, 4),
        }

    def get_deployment_report(self) -> dict[str, Any]:
        """
        Generate high-level deployment success telemetry.
        """
        total = self._stats["deployed"] + self._stats["rejected"]
        return {
            "status": "REPORT",
            "deployment_success_rate": (
                round(self._stats["deployed"] / total, 4) if total > 0 else 0.0
            ),
            "deployed_count": self._stats["deployed"],
            "rejected_count": self._stats["rejected"],
        }
