"""Tests for personality trigger matching."""

from pathlib import Path

from llm_setup import load_personalities, mentioned_personality


def test_tama_word():
    assert mentioned_personality("hey tama") == "tama"
    assert mentioned_personality("TAMANEKO are you there") == "tama"


def test_saki_word(tmp_path):
    path = tmp_path / "personality.yaml"
    path.write_text("id: saki\nnames: [saki, autumn]\nmodel: gemma4\nendpoint: local\n")
    load_personalities(path)
    assert mentioned_personality("saki, ping") == "saki"
    assert mentioned_personality("hello autumn") == "saki"
    assert mentioned_personality("sake is rice wine") is None


def test_no_substring_false_positive():
    assert mentioned_personality("tamarind smoothie") is None


def test_no_match():
    assert mentioned_personality("hello there") is None


def test_example_file_is_valid():
    load_personalities(Path(__file__).resolve().parent.parent / "personality.yaml")
    assert mentioned_personality("tama") == "tama"
