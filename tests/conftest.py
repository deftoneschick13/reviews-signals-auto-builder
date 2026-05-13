"""Shared pytest fixtures."""

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def peec_response_json():
    with open(FIXTURES_DIR / "sample_peec_response.json") as f:
        return json.load(f)
