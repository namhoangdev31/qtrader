import pytest
from unittest.mock import MagicMock
from qtrader.pipeline.deployment import BotDeployment

def test_deployment_initialization():
    deployer = BotDeployment(target_env="production")
    assert deployer.target_env == "production"

def test_deployment_package():
    deployer = BotDeployment(target_env="staging")
    strategy_config = {"name": "TestStrategy", "version": "1.0"}
    pkg_path = deployer.package_strategy(strategy_config)
    assert pkg_path is not None
    assert pkg_path.endswith(".zip") or pkg_path.endswith(".tar.gz")

def test_deployment_deploy():
    deployer = BotDeployment(target_env="production")
    mock_client = MagicMock()
    deployer.set_client(mock_client)
    
    status = deployer.deploy("/path/to/pkg.zip")
    assert status == "SUCCESS"
    mock_client.upload.assert_called_once()
