# XEDB — Xanrean Echo Discord Bot

A unified Discord bot with multi-personality AI, voice music playback, an RPG system, and scheduled daily trivia. Powered by Ollama (Gemma 4) and discord.py.

## Architecture

One bot process. One Discord token. One `personality.yaml`. Clone the instance (not the code) for Tama vs Saki — each is a long-running systemd service.

Talk to the instance by any of its trigger names and it replies as that character.

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com) running locally **or** an [Ollama Cloud](https://ollama.com/cloud) API key
- [ffmpeg](https://ffmpeg.org) installed and on PATH (required for MusicCog voice playback)
- A Discord bot token (create at https://discord.com/developers/applications)

## Quick Start

```bash
git clone https://git.worldofxanrea.com/PurpleXanmal/XEDB.git
cd XEDB
python main.py
```

On first run the bot will:
1. Auto-install missing Python packages (discord.py, python-dotenv, ollama, yt-dlp, pytz, PyYAML)
2. Prompt you for your Discord bot token and channel name
3. Write those to `.env` in the instance home
4. Pull the *local* personality model from Ollama if it is not already available
5. Warn you if Ollama or ffmpeg are missing and offer to open their download pages

## Environment Variables

Create `.env` manually or let the first-run wizard handle it:

| Variable | Required | Description |
|---|---|---|
| `BotToken` | Yes | Discord bot token |
| `ChatChannel` | No | Channel name the bot listens in (default: `general`) |
| `DefaultPersonality` | No | Unused unless you override the yaml `id` (leave unset) |
| `BotOwnerId` | No | Discord user ID allowed to use owner-restricted commands (falls back to guild owner/admin) |
| `CommandPrefix` | No | Legacy text-command prefix (default: `!`) |
| `ReplyChance` | No | 1-in-N chance to reply in other channels when not named (default: `6`) |
| `ActivityHours` | No | Hours between Discord activity rotations (default: `12`) |
| `OllamaHost` | No | Local Ollama HTTP endpoint (default: `http://localhost:11434`) |
| `OllamaApiKey` | Yes for cloud | Ollama Cloud API key (also `OLLAMA_API_KEY`). Required for `endpoint: cloud` |
| `OllamaCloudHost` | No | Ollama Cloud API host (default: `https://ollama.com`) |
| `OpenAIApiKey` | No | OpenAI API key for `codex` / `luna` fallbacks |
| `CodexModel` | No | OpenAI model for the `codex` fallback (default: `gpt-5.3-codex`) |
| `LunaApiKey` | No | Optional separate key for Luna; otherwise `OpenAIApiKey` |
| `LunaModel` | No | OpenAI volume model (default: `gpt-5.6-luna`) |
| `SongsDir` | No | Local music directory for `/play_music` (default: `Songs`) |
| `AloneDisconnectSeconds` | No | Leave voice after this many seconds alone (default: `60`) |
| `QuizTimezone` | No | IANA timezone for the daily quiz (default: `US/Arizona`) |
| `SteamGamesDir` | No | Extra folder of game names for presence (Windows Steam `common/` is used if unset and present) |

## Personalities (`personality.yaml`)

`.env` is secrets and runtime knobs. The character and which cogs run live in `personality.yaml` in the instance home (`XEDB_HOME`, or the repo root):

```yaml
id: tama
names:
  - tama
  - tamaneko
model: gemma4:31b
endpoint: cloud
system: |
  You are Tama.
fallbacks: [codex, luna]
cogs:
  ModerationCog: true
  MusicCog: true
  RPGCog: false
  QuizCog: false
```

Omitted cogs stay **on**. Names also accept `music`, `rpg`, `quiz`, `moderation`.

Default path for Pi clones: **Ollama Cloud `gemma4:31b`**. If that call fails (quota, outage), the bot tries **codex** then **luna**:

| Fallback | What it actually is | Keys |
|---|---|---|
| `codex` | OpenAI **API** (`CodexModel`, default `gpt-5.3-codex`) | `OpenAIApiKey` |
| `luna` | OpenAI cheap volume model (`LunaModel`, default `gpt-5.6-luna`) | `LunaApiKey` or `OpenAIApiKey` |

The ChatGPT **Codex subscription / Codex app cannot be called from this bot**. If you only have the sub and no API key, skip `codex` and leave `luna` (or drop both and stay on Ollama Cloud).

`endpoint` is explicit. Direct cloud uses `gemma4:31b` + `OllamaApiKey`. A `:cloud` tag on a **local** daemon is still `endpoint: local`.

Clone Saki as a second instance with its own yaml, token, and cog flags — do not cram two Discord bots into one process.

## Running as daemons (Pi)

One code checkout, one venv, N instance directories. The Pi should use `endpoint: cloud` or `OllamaHost` pointing at a machine that actually has a GPU — a Pi will not run Gemma locally in any useful way.

```bash
# once
sudo mkdir -p /home/xanmal/xedb/app /home/xanmal/xedb/instances
sudo rsync -a ./ /home/xanmal/xedb/app/
cd /home/xanmal/xedb/app
python -m venv venv
./venv/bin/pip install -r requirements.txt

# per bot
INSTANCE=tama
mkdir -p /home/xanmal/xedb/instances/$INSTANCE
cp personality.yaml /home/xanmal/xedb/instances/$INSTANCE/
cp .env.example /home/xanmal/xedb/instances/$INSTANCE/.env
# edit .env (BotToken, OllamaApiKey / OllamaHost) and personality.yaml (id, cogs)

sudo cp deploy/xedb@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now xedb@$INSTANCE
```

Launch another clone:

```bash
cp -a /home/xanmal/xedb/instances/tama /home/xanmal/xedb/instances/saki
# new token + yaml, then:
sudo systemctl enable --now xedb@saki
```

Foreground equivalent: `python main.py --home /home/xanmal/xedb/instances/tama`

Logs: `journalctl -u xedb@tama -f` and `$XEDB_HOME/bot.log`.

### Stopping a bot

Use systemd, not `kill`:

```bash
sudo systemctl stop xedb@tama     # clean shutdown, sends SIGTERM
sudo systemctl restart xedb@tama
```

`main.py` traps both SIGINT (Ctrl+C) and SIGTERM (what systemd sends) and closes
the gateway connection properly — it sends a close frame and shuts the HTTP
session down before exiting. If you instead `kill -9` the process, nothing can
run: the socket dies without a close frame, so Discord's gateway is never told
the bot left and can keep showing it as online until the session times out.

`xedb@.service` sets `Restart=always`, so it comes back ~5s after any exit.
That is intended for a long-running daemon. To take one down for good, `stop`
it — stopping does not trigger a restart.

## Cogs

### ModerationCog
Slash commands for server management. Restricted to allowed users and standard Discord permissions.

| Command | Permission | Description |
|---|---|---|
| `/ping` | Anyone | Bot latency in ms |
| `/cogs` | Anyone | List loaded cogs |
| `/modhelp` | Anyone | List moderation commands |
| `/purge <count>` | Manage Messages | Bulk delete messages |
| `/kick <member> [reason]` | Kick Members | Kick a user |
| `/ban <member> [reason]` | Ban Members | Ban a user |
| `/unban <user_id> [reason]` | Ban Members | Unban a user by ID |
| `/timeout <member> <minutes> [reason]` | Moderate Members | Temporarily timeout a user |
| `/untimeout <member> [reason]` | Moderate Members | Remove a user's timeout |
| `/speak <message> [channel]` | Manage Messages | Send a message as the bot |
| `/reload_cogs` | Allowed users | Hot-reload all loaded cogs |

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
- Rejects URLs that point to private/reserved addresses

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
- **Skills** — Power Strike, Mana Shield, Fireball, and Dodge. Each costs stamina or mana.
- **Shop** — buy potions, weapons, armor, and rare artifacts. Stock restocks periodically.
- **Level up** — XP gain scales with monster difficulty. Stats increase automatically on level-up.
- **Regen** — stamina and mana regenerate by 10 per minute while the cog is loaded; defeated players slowly recover health.
- **Balance** — encountered monsters are scaled to your level; battles have a 10-second cooldown.

**Files**: player data is saved to `DataFiles/rpgFiles/players.json` (runtime, git-ignored).

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
- **6:00 PM** (Arizona time): Correct answer revealed in-channel
- Points are awarded immediately when a user answers correctly
- Automatically fetches new questions from OpenTDB when running low

**Files**: quiz state, questions, used questions, and points are saved under `DataFiles/` (runtime, git-ignored).

## Data Files (Persistent)

These JSON files are created at runtime and persist between restarts. They are **git-ignored** and must never be committed:

```
DataFiles/
  quiz-data.json        # Quiz schedule, channel, session token, points
  questions.json        # Active question pool per category
  used-questions.json   # Already-used questions (rotated back in by /reset_questions)
  points.json           # Legacy/legacy score file (deprecated)
  rpgFiles/
    players.json        # All RPG character data
    monsters.json       # Monster definitions (seeded with defaults)
    shop-items.json     # Shop inventory and stock
```

`DataFiles/GameList.json` is the one tracked data file — it lists games used for the bot's rotating activity status.

## Runtime Files (Git Ignored)

These are generated at runtime and should never be committed:

| File | Source |
|---|---|
| `Songs/` | Local music downloads and uploads |
| `bot.log` | Normal bot logging |
| `bot-error.log` | Error logging |
| `cookies.txt` | yt-dlp YouTube session cookies (used automatically if present) |
| `logs/` | Reserved for chat log storage |

## Logging

Logs are written to `bot.log` (info and above) and `bot-error.log` (errors only), plus the console. Configuration lives in `main.py` (`_setup_logging`).

## Development

Install dev dependencies and run tests:

```bash
pip install -r requirements-dev.txt
pytest
ruff check Cogs/ main.py bot.py cog_manager.py safety_checks.py config.py llm_setup.py tests/
```

## Notes

- The legacy `python main.py tama` argument no longer exists; personality is automatic based on trigger words.
- If Ollama is not running, the bot prints a warning and continues. AI responses will fail until Ollama starts.
- If ffmpeg is missing, MusicCog commands that need voice playback will fail gracefully with a user-visible message.
- The bot uses `discord.Intents.all()`. Make sure your bot's gateway intents are enabled in the Discord developer portal.
