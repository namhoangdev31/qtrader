from unittest.mock import MagicMock

import pytest

from qtrader.pipeline.deployment import DeploymentBridge
from qtrader.pipeline.research import ResearchResult


def test_deployment_initialization():
    deployer = DeploymentBridge(config_path="configs/test_bot.yaml")
    assert deployer.config_path.name == "test_bot.yaml"

def test_deployment_fail_unapproved():
    deployer = DeploymentBridge()
    result = MagicMock(spec=ResearchResult)
    result.approved_for_deployment = False
    
    with pytest.raises(ValueError, match="Cannot deploy unapproved research result"):
        deployer.deploy(result)
