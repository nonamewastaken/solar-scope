from pathlib import Path

import pytest

from solarscope import config

FIXTURES = Path(__file__).parent / "fixtures"
RAW = FIXTURES / "raw"


@pytest.fixture
def cfg():
    return config.load_config(None, RAW / "site.json")
