import pytest

from qtrader.meta.deployment_pipeline import DeploymentPipeline


@pytest.fixture
def pipeline() -> DeploymentPipeline:
    """Initialize DeploymentPipeline for transition testing."""
    return DeploymentPipeline()


def test_deployment_happy_path(pipeline: DeploymentPipeline) -> None:
    """Verify that a strategy passing all gates is deployed LIVE."""
    # 1. APPROVED, 2. ALLOCATION_WEIGHT=0.05, 3. SHADOW_PASS=True
    result = pipeline.request_deployment(
        strategy_id="S1", is_approved=True, allocation=0.05, shadow_pass=True
    )
    assert result["result"] == "LIVE"
    assert result["allocation"] == 0.05


def test_deployment_gate_failures(pipeline: DeploymentPipeline) -> None:
    """Verify that failing any single gate results in REJECTED."""
    # Failure 1: Not Approved
    res1 = pipeline.request_deployment("S_UNA", False, 0.02, True)
    assert res1["result"] == "REJECTED"
    assert "NOT_APPROVED_BY_COMMITTEE" in res1["reasons"]

    # Failure 2: Zero Allocation
    res2 = pipeline.request_deployment("S_ZERO", True, 0.0, True)
    assert res2["result"] == "REJECTED"
    assert "ZERO_CAPITAL_ALLOCATION" in res2["reasons"]

    # Failure 3: Shadow Failure
    res3 = pipeline.request_deployment("S_SHAD", True, 0.03, False)
    assert res3["result"] == "REJECTED"
    assert "SHADOW_MODE_VALIDATION_FAILURE" in res3["reasons"]


def test_deployment_multi_gate_rejection(pipeline: DeploymentPipeline) -> None:
    """Verify that all relevant rejection reasons are captured."""
    # Failed both Approval and Shadow
    result = pipeline.request_deployment("S_BOMB", False, 0.05, False)
    assert "NOT_APPROVED_BY_COMMITTEE" in result["reasons"]
    assert "SHADOW_MODE_VALIDATION_FAILURE" in result["reasons"]


def test_deployment_governance_report(pipeline: DeploymentPipeline) -> None:
    """Verify the validity of the deployment success reporting."""
    # 1 Live, 3 rejected
    pipeline.request_deployment("S1", True, 0.05, True)  # PASS
    pipeline.request_deployment("S2", False, 0.05, True)  # FAIL
    pipeline.request_deployment("S3", True, 0.00, True)  # FAIL
    pipeline.request_deployment("S4", True, 0.01, False)  # FAIL

    report = pipeline.get_deployment_report()
    assert report["deployment_success_rate"] == 0.25
    assert report["deployed_count"] == 1
    assert report["rejected_count"] == 3
