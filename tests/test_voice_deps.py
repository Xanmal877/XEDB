"""Voice dependencies must stay declared.

discord.py 2.7 made voice opt-in: `discord.py[voice]` pulls PyNaCl **and**
davey. If either is missing, the client still starts and logs a single WARNING
at import time, then every voice call fails at runtime with
RuntimeError('davey library needed in order to use voice').

That failure mode is easy to ship by accident: the bot boots fine, `/play_music`
just never works. These tests fail loudly instead.
"""

import importlib.util

import pytest


def test_davey_is_installed():
    assert importlib.util.find_spec("davey") is not None, (
        "davey is missing — MusicCog voice commands will raise at runtime. "
        "Install it with: pip install 'discord.py[voice]'"
    )


def test_pynacl_is_installed():
    assert importlib.util.find_spec("nacl") is not None, (
        "PyNaCl is missing — voice will not work. Install it with: pip install 'discord.py[voice]'"
    )


def test_discord_reports_voice_as_available():
    import discord.voice_client as voice_client
    from discord.voice_state import has_dave

    assert has_dave, "discord.py reports davey as unavailable"
    assert voice_client.has_nacl, "discord.py reports PyNaCl as unavailable"


def test_requirements_declares_the_voice_extra():
    """The declared dep must be the extra, not bare discord.py."""
    from pathlib import Path

    reqs = (Path(__file__).resolve().parent.parent / "requirements.txt").read_text()
    lines = [ln.strip() for ln in reqs.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert any(ln.startswith("discord.py[voice]") for ln in lines), (
        "requirements.txt must request discord.py[voice]; bare discord.py omits davey"
    )


def test_pynacl_satisfies_discord_pin():
    """discord.py[voice] pins PyNaCl <1.6; a newer version breaks voice crypto."""
    if importlib.util.find_spec("nacl") is None:
        pytest.skip("PyNaCl not installed")

    from importlib.metadata import version

    installed = version("PyNaCl")
    major, minor = (int(part) for part in installed.split(".")[:2])
    assert (major, minor) >= (1, 5), f"PyNaCl {installed} is older than the required 1.5.0"
    assert (major, minor) < (1, 6), f"PyNaCl {installed} violates discord.py's <1.6 pin; voice may break"
