"""Tests for the shared JSON persistence helpers in Cogs/util.py."""

import json

from Cogs.util import load_json, save_json


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "nested" / "dir" / "data.json"
    save_json(path, {"a": 1, "b": [2, 3]})
    assert path.exists()
    assert load_json(path) == {"a": 1, "b": [2, 3]}


def test_load_missing_returns_empty(tmp_path):
    assert load_json(tmp_path / "missing.json") == {}


def test_load_corrupt_backs_up_and_returns_empty(tmp_path):
    path = tmp_path / "data.json"
    path.write_text("{not valid json")
    data = load_json(path)
    assert data == {}
    backup = path.with_suffix(".json.bak")
    assert backup.exists()
    # The corrupt original is moved aside so the cog can start fresh without
    # losing the corrupt payload.
    assert backup.read_text() == "{not valid json"
    assert not path.exists()


def test_load_non_object_returns_empty(tmp_path):
    path = tmp_path / "data.json"
    path.write_text("[1, 2, 3]")
    assert load_json(path) == {}


def test_save_is_valid_json(tmp_path):
    path = tmp_path / "data.json"
    save_json(path, {"x": "y"})
    assert json.loads(path.read_text()) == {"x": "y"}
    # temp file is cleaned up
    assert not list(tmp_path.glob("*.tmp"))
