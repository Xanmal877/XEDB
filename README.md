# Discord Bot with LLM Capabilities

XEDB (Xanrean Echo Discord Bot) is a multi-personality Discord bot powered by a local LLM via Ollama.

## Overview

One bot, multiple personalities. Address it as **Tama** or **Saki** and it responds in character.

- **Tama** — Triggered by saying "tama" or "tamaneko"
- **Saki** — Triggered by saying "saki" or "autumn"

The default AI model is **Gemma 4** via Ollama. The bot auto-detects which personality you are addressing and switches context automatically.

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com) running locally
- [ffmpeg](https://ffmpeg.org) installed on your system (required for MusicCog voice playback)
- SDL2 libraries (required for Game Boy Color emulator cog on some systems)
- A Discord bot token (create at https://discord.com/developers/applications)

## Setup

1. **Clone and create virtual environment:**
   ```bash
   git clone https://git.worldofxanrea.com/PurpleXanmal/XEDB.git
   cd XEDB
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   ```

2. **Run the bot:**
   ```bash
   python main.py
   ```

   On first run, the bot will:
   - Auto-install any missing Python packages
   - Prompt you for your Discord bot token and channel name
   - Pull the **gemma4** model from Ollama if it is not already local
   - Warn you if ffmpeg is missing and offer to open the download page

3. **Or configure manually:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and fill in `BotToken`.

## Environment Variables

| Variable | Description |
|---|---|
| `BotToken` | Discord bot token |
| `ChatChannel` | Name of the Discord channel the bot listens and replies in |
| `DefaultPersonality` | Which personality starts active: `tama` or `saki` |

## Cogs

| Cog | Description |
|---|---|
| **ModerationCog** | Standard Discord moderation |
| **MusicCog** | Voice channel music playback via YouTube |
| **RPGCog** | RPG system |
| **QuizCog** | Trivia system (currently disabled) |

## Notes

- `cookies.txt` is generated at runtime by `yt-dlp` for YouTube access. It is ignored by git and should never be committed.
- Bot logs are written to `bot.log` and `bot-error.log` at runtime. These are also ignored by git.
- The `Songs/` directory is auto-created for local music playback and is also ignored by git.
