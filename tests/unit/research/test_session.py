import pytest
from unittest.mock import MagicMock
from qtrader.research.session import ResearchSession

def test_research_session_init():
    session = ResearchSession(name="test_session")
    assert session.name == "test_session"
    assert session.is_active is False

def test_research_session_start_stop():
    session = ResearchSession(name="temp")
    session.start()
    assert session.is_active is True
    assert session.start_time is not None
    
    session.stop()
    assert session.is_active is False
    assert session.end_time is not None
    assert session.duration > 0

def test_research_session_add_artifact():
    session = ResearchSession(name="artifact_test")
    session.start()
    
    session.add_artifact("model", "/path/to/model")
    artifacts = session.get_artifacts()
    assert "model" in artifacts
    assert artifacts["model"] == "/path/to/model"
    
    session.stop()
