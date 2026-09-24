"""Runtime dependency checks: Ollama, ffmpeg, and the configured model."""

import subprocess
import sys

import config


def check_ollama():
    """Check if Ollama is running locally."""
    import urllib.request

    host = config.OLLAMA_HOST
    if not host.startswith(("http://", "https://")):
        return False
    try:
        urllib.request.urlopen(host, timeout=2)  # noqa: S310
        return True
    except Exception:
        return False


def check_ffmpeg():
    """Check if ffmpeg is installed on the system."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def offer_open(url: str, name: str):
    """Ask user if they want to open a download page."""
    if not sys.stdin.isatty():
        return
    try:
        response = input(f"Open {name} download page in browser? [y/N]: ").strip().lower()
        if response in ("y", "yes"):
            import webbrowser

            webbrowser.open(url)
            print(f"[Bootstrap] Opened {url}")
    except (EOFError, KeyboardInterrupt):
        pass


def health_checks():
    from llm_setup import needs_local_runtime

    if needs_local_runtime() and not check_ollama():
        print(f"\n⚠️  Ollama is not running on {config.OLLAMA_HOST}")
        print("   The bot needs Ollama for local AI responses.")
        offer_open("https://ollama.com/download", "Ollama")
        print("   Start Ollama and try again.\n")

    if not check_ffmpeg():
        print("\n⚠️  ffmpeg is not installed or not in PATH")
        print("   The MusicCog needs ffmpeg for voice channel audio playback.")
        offer_open("https://ffmpeg.org/download.html", "ffmpeg")
        print("   Install ffmpeg and try again.\n")
