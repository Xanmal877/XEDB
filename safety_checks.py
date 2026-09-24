"""Runtime dependency checks: Ollama, ffmpeg, and the configured model."""

import subprocess
import sys

import ollama

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
    if not check_ollama():
        print(f"\n⚠️  Ollama is not running on {config.OLLAMA_HOST}")
        print("   The bot needs Ollama for AI responses.")
        offer_open("https://ollama.com/download", "Ollama")
        print("   Start Ollama and try again.\n")

    if not check_ffmpeg():
        print("\n⚠️  ffmpeg is not installed or not in PATH")
        print("   The MusicCog needs ffmpeg for voice channel audio playback.")
        offer_open("https://ffmpeg.org/download.html", "ffmpeg")
        print("   Install ffmpeg and try again.\n")


def ensure_ollama_model(model_name: str):
    """Warn (and optionally pull) if the Ollama model is not local."""
    try:
        response = ollama.list()
        models = []
        if hasattr(response, "models"):
            models = [getattr(m, "model", str(m)) for m in response.models]
        elif isinstance(response, dict):
            models = [m.get("model", m.get("name", "")) for m in response.get("models", [])]

        if any(model_name == m or model_name in m for m in models):
            print(f"[Bootstrap] Ollama model '{model_name}' is available")
            return

        if not sys.stdin.isatty():
            print(f"[Bootstrap] Warning: Ollama model '{model_name}' is not local.")
            print(f"   Pull it manually: ollama pull {model_name}")
            return

        print(f"[Bootstrap] Pulling Ollama model '{model_name}' (this may take a few minutes)...")
        ollama.pull(model_name)
        print(f"[Bootstrap] Model '{model_name}' ready")
    except Exception as e:
        print(f"[Bootstrap] Warning: could not pull '{model_name}': {e}")
        print(f"   Make sure Ollama is running and try manually: ollama pull {model_name}")
