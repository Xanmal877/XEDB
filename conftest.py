"""Pytest configuration root. Ensures the repository root is importable."""

from pathlib import Path

import pytest

from llm_setup import load_personalities

PERSONALITY_YAML = Path(__file__).resolve().parent / "personality.yaml"


@pytest.fixture(autouse=True)
def _default_personalities():
    load_personalities(PERSONALITY_YAML)
    yield
