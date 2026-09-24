"""Tests for personality trigger matching."""

from main import mentioned_personality


def test_tama_word():
    assert mentioned_personality("hey tama") == "tama"
    assert mentioned_personality("TAMANEKO are you there") == "tama"


def test_saki_word():
    assert mentioned_personality("saki, ping") == "saki"
    assert mentioned_personality("hello autumn") == "saki"


def test_no_substring_false_positive():
    assert mentioned_personality("tamarind smoothie") is None
    assert mentioned_personality("sake is rice wine") is None


def test_no_match():
    assert mentioned_personality("hello there") is None
