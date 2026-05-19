# XEDB — Xanrean Echo Discord Bot

A unified Discord bot with multi-personality AI, voice music playback, an RPG system, and scheduled daily trivia. Powered by Ollama (Gemma 4) and discord.py.

## Architecture

One bot. One token. Two personalities. Talk to it as **Tama** or **Saki** and it switches context automatically based on trigger words in your message.

| Personality | Trigger words |
|---|---|
| **Tama** | `tama`, `tamaneko` |
| **Saki** | `saki`, `autumn` |

All cogs load for the unified bot. No more juggling two separate bot applications.

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com) running locally
- [ffmpeg](https://ffmpeg.org) installed and on PATH (required for MusicCog voice playback)
- A Discord bot token (create at https://discord.com/developers/applications)

## Quick Start

```bash
git clone https://git.worldofxanrea.com/PurpleXanmal/XEDB.git
cd XEDB
python main.py
```

On first run the bot will:
1. Auto-install missing Python packages (discord.py, python-dotenv, ollama, yt-dlp, pytz)
2. Prompt you for your Discord bot token, channel name, and default personality
3. Write these to `.env`
4. Pull `gemma4` from Ollama if it is not already local
5. Warn you if Ollama or ffmpeg are missing and offer to open their download pages
## Environment Variables

Create `.env` manually or let the first-run wizard handle it:

| Variable | Required | Description |
|---|---|---|
| `BotToken` | Yes | Discord bot token |
| `ChatChannel` | No | Channel name the bot listens in (default: `general`) |
| `DefaultPersonality` | No | `tama` or `saki` (default: `tama`) |

## Cogs

### ModerationCog
Slash commands for server management. Restricted to allowed users and standard Discord permissions.

| Command | Permission | Description |
|---|---|---|
| `/ping` | Anyone | Bot latency in ms |
| `/purge <count>` | Manage Messages | Bulk delete messages |
| `/kick <member>` | Kick Members | Kick a user |
| `/ban <member>` | Ban Members | Ban a user |
| `/unban <user_id>` | Ban Members | Unban a user by ID |
| `/speak <message> [channel]` | Manage Messages | Send a message as the bot |
| `/reload_cogs` | Allowed users | Hot-reload MusicCog and QuizCog |

### MusicCog
Voice channel music playback via YouTube (yt-dlp) or local files from the `Songs/` directory.

| Command | Description |
|---|---|
| `/play_music <query>` | Play from URL, YouTube search, or local file |
| `/nowplaying` | Show current track info |
| `/queue` | Show tracks in queue |
| `/skip` | Skip current track |
| `/stop` | Stop and disconnect |
| `/volume <0-100>` | Set playback volume |
| `/pause` | Pause playback |
| `/resume` | Resume playback |
| `/loop <off/track/queue>` | Set repeat mode |
| `/shuffle` | Randomize queue order |
| `/remove <position>` | Remove track at position |

**Features**
- YouTube search results appear as interactive buttons
- Auto-disconnects after 60 seconds if left alone in a voice channel
- Reconnect + retry logic with failure-rate limiting
- Per-guild queue, volume, and repeat mode state

### RPGCog
Discord-native turn-based RPG. Each user has persistent stats, inventory, and exploration history.

| Command | Description |
|---|---|
| `/register` | Create your character |
| `/playrpg` | Open the adventure menu (Explore / Battle / Shop / Inventory / Stats) |
| `/stats` | View your character stats |
| `/use <item>` | Use an item from inventory |

**Systems**
- **Explore** — find gold, items, monsters, or nothing. 5-second cooldown.
- **Battle** — attack, use skills, or flee. Skills unlock at levels 2 and 4.
- **Shop** — buy potions, weapons, armor, and rare artifacts.
- **Level up** — XP gain scales with monster difficulty. Stats increase automatically.
- **Regen** — stamina and mana regenerate by 10 per minute while the cog is loaded.

**Files**: player data is saved to `DataFiles/rpgFiles/players.json`.

### QuizCog
Scheduled daily trivia from [OpenTDB](https://opentdb.com). Runs automatically. No user setup required beyond the channel.

| Command | Permission | Description |
|---|---|---|
| `/set_quiz_channel <channel>` | Admin | Channel for daily quizzes |
| `/set_quiz_time <start> <reveal>` | Admin | Quiz and reveal times in `HH:MM` (Arizona time) |
| `/start_quiz` | Admin | Force-start today's quiz |
| `/list_categories` | Anyone | Show enabled trivia categories |
| `/enable_category <name>` | Admin | Enable a category |
| `/quiz_status` | Anyone | Leaderboard and current question status |
| `/points` | Anyone | Check your quiz score |
| `/reset_questions` | Admin | Move all used questions back to the active pool |
| `/force_reset_quiz` | Admin | Emergency reset if the quiz state locks up |

**Schedule**
- **6:00 AM** (Arizona time): Quiz posts in the configured channel
- **6:00 PM** (Arizona time): Correct answer revealed, points awarded
- Automatically fetches new questions from OpenTDB when running low

**Files**: quiz state, questions, used questions, and points are saved under `DataFiles/`.

## Data Files (Persistent)

These JSON files are created at runtime and persist between restarts:

```
DataFiles/
  quiz-data.json        # Quiz schedule, channel, session token, points
  questions.json        # Active question pool per category
  used-questions.json   # Already-used questions (rotated back in by /reset_questions)
  rpgFiles/
    players.json        # All RPG character data
    monsters.json       # Monster definitions
    shop-items.json     # Shop inventory and stock
```

## Runtime Files (Git Ignored)

These are generated at runtime and should never be committed:

| File | Source |
|---|---|
| `Songs/` | Local music downloads and uploads |
| `bot.log` | Normal bot logging |
| `bot-error.log` | Error logging |
| `cookies.txt` | yt-dlp YouTube session cookies |

## Notes

- The legacy `python main.py tama` argument still works but is ignored. Personality is automatic.
- If Ollama is not running, the bot prints a warning and continues. AI responses will fail until Ollama starts.
- If ffmpeg is missing, MusicCog commands that need voice playback will fail gracefully with a user-visible message.
- The bot uses ` discord.Intents.all()`. Make sure your bot's gateway intents are enabled in the Discord developer portal.
