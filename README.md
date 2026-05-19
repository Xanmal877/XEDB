# Discord Bot with LLM Capabilities

XEDB (Xanrean Echo Discord Bot) is a multi-personality Discord bot powered by local LLMs via Ollama.

## Overview

Two personalities share one codebase:
- **Tama** — Music, Moderation, RPG cogs. Model: `Tamaneko`
- **Saki** — Moderation, Quiz cogs. Model: `Autumn`

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com) running locally with models named `Tamaneko` and `Autumn`
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

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Create your environment file:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and fill in your actual tokens and channel name.

4. **Run the bot:**
   ```bash
   # Run as Tama
   python main.py tama

   # Run as Saki
   python main.py saki
   ```

## Environment Variables

| Variable | Description |
|---|---|
| `TamaToken` | Discord bot token for the Tama personality |
| `SakiToken` | Discord bot token for the Saki personality |
| `ChatChannel` | Name of the Discord channel the bot listens and replies in |

## Cogs

| Cog | Description | Loaded By |
|---|---|---|
| **ModerationCog** | Standard Discord moderation | Both |
| **MusicCog** | Voice channel music playback via YouTube | Tama |
| **RPGCog** | RPG system | Tama |
| **QuizCog** | Trivia system | Saki (currently disabled) |

## Notes

- `cookies.txt` is generated at runtime by `yt-dlp` for YouTube access. It is ignored by git and should never be committed.
- Bot logs are written to `bot.log` and `bot-error.log` at runtime. These are also ignored by git.
