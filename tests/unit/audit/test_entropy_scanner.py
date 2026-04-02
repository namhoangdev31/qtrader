import os

import pytest

from qtrader.audit.entropy_scanner import EntropyScanner

MOCK_FILE_CONTENT = """
import random
import numpy as np
import torch

def uncontrolled_random():
    return random.random()  # Uncontrolled

def controlled_random():
    random.seed(42)
    return random.random()  # Controlled via file-level seed

def numpy_uncontrolled():
    return np.random.rand(5)  # Uncontrolled

def torch_controlled():
    return torch.rand(5, generator=torch.Generator().manual_seed(42))  # Should detect as entropy but maybe controlled if manually checked

def set_iter():
    for x in set([1, 2, 3]):  # Hidden entropy
        print(x)

class Model:
    def __init__(self, random_state=42):
        self.rs = random_state

    def predict(self):
        return random.random() # Uncontrolled unless we trace the class init (simplified for now)
"""

@pytest.fixture
def mock_repo(tmp_path):
    repo = tmp_path / "qtrader"
    repo.mkdir()
    (repo / "alpha").mkdir()
    
    dirty_file = repo / "alpha" / "dirty.py"
    dirty_file.write_text(MOCK_FILE_CONTENT)
    
    return str(tmp_path)

def test_entropy_scanner_detection(mock_repo):
    scanner = EntropyScanner(mock_repo)
    scanner.scan_directory(mock_repo)
    
    # Total sources: random.random (x2), np.random.rand, torch.rand, set_iter
    # Excluding seeds which are markers
    assert len(scanner.sources) >= 5
    
    categories = [s.category for s in scanner.sources]
    assert "STOCHASTIC_CALL" in categories
    assert "HIDDEN_ENTROPY" in categories
    
    # Check severity for alpha module
    for s in scanner.sources:
        if "alpha" in s.file_path:
            assert s.severity == "HIGH"

def test_entropy_scanner_reporting(mock_repo, tmp_path):
    scanner = EntropyScanner(mock_repo)
    scanner.scan_directory(mock_repo)
    
    output_dir = tmp_path / "audit"
    scanner.export(str(output_dir))
    
    assert (output_dir / "entropy_report.json").exists()
    assert (output_dir / "entropy_locations.csv").exists()
