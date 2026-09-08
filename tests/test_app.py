"""Tests for src/app.py.

Run them with: pytest
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.app import greeting


def test_greeting_uses_the_name():
    assert greeting("Ada") == "Hello, Ada!"


def test_greeting_handles_an_empty_name():
    assert greeting("") == "Hello there!"
