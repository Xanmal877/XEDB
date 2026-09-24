# Cog audit — cleanup done, features to add

## Cleanup applied (verified: 68 tests, ruff clean)

**Dead weight removed**
- `_get_voice_client` was `async` but contained no `await` — 11 call sites were awaiting a coroutine for a dict lookup. Now sync.
- `_process_search_results` / `_process_direct_url` same problem — `async` with no await, awaited at 2 sites. Now sync.
- `Music.active_views` — a hand-rolled view registry duplicating discord.py's own `ViewStore`. 6 lines of bookkeeping, gone.
- `Quiz.get_random_question` double-checked emptiness after already filtering empty categories.
- Quiz `enable_category` had a redundant `if "enabled_categories" not in self.data` guard that the constructor already guarantees.
- `Moderation.OWNER_ID` frozen at import (see bug below).

**Duplication collapsed**
- 4 copies of the same `aiohttp.ClientSession → raise_for_status → .json()` block in QuizCog → one `_opentdb_get`.
- `get_session_token` / `reset_session_token` were the same function twice → one `_token_command`.
- 2 copies of the "is this skill defined" scan → `rpg_logic.is_known_skill`.
- RPG item data existed twice: `ITEM_EFFECTS` (type/value) and `_default_shop_items` (type/value/price/stock) — every item declared in both. Now three tables keyed by name, one source.
- 18-monster seed list was inlined in `__init__` → module-level `DEFAULT_MONSTERS`.
- Stats embed existed twice, and the two copies had **drifted** — the menu version showed Stamina/Mana, `/stats` did not. Unified in `build_stats_embed`.
- 20-line manual `+=` string building in `list_categories` → joins.
- Duplicate-question check was O(used) per question → set lookups.

**Bugs found by this pass**
1. `Moderation.OWNER_ID = config.BOT_OWNER_ID` ran at import, before anything guaranteed `config.load()` — owner-only commands could silently deny the owner.
2. `QuizView.handle_response` had a check-then-set race: two fast clicks could both pass the "already answered" test and double-count points.

## Feature candidates (ranked)

### Worth doing
1. **`/disable_category`** — you can enable a quiz category but never turn one off; the only escape is hand-editing `quiz-data.json`. Asymmetric command set.
2. **RPG `/sell`** — `/use rare_artifact` is the only way to convert an item to gold, and it *consumes* it. Duplicate loot is a dead end.
3. **Music `/seek <seconds>`** — needs an ffmpeg `-ss` offset; ffmpeg already in the pipeline, no new dependency.
4. **Music `/playlist <name>`** — queue save/load. Queue is per-guild in-memory, so every bot restart loses it.
5. **`/rpg_leaderboard`** — RPG has per-player level/gold but only quiz has a leaderboard.

### Cheap + high value
6. **`/help` with a single source of truth** — `modhelp` is hand-written prose that can drift from the real command set. Generate it from `client.tree` so it cannot lie.
7. **Quiz `/points_reset`** — a new season has no reset path.

### Maybe not
8. Music `/lyrics` — new dependency, third-party API, questionable payoff.
9. RPG `/trade` — needs two-user interaction state; real complexity for a small server.

## Deliberately not touched
- **Game balance** (damage, XP curve, monster stats, quiz points). That's design, your call.
- **Command names / permission model.** Public contracts.
- **Voice backend.** `davey` missing is a library issue, not code.
- **QuizCog is still 650 lines.** OpenTDB access, quiz state, and 9 slash commands in one file. Splitting further means moving slash commands out of `*Cog.py`, which breaks the convention the other three follow — flagging, not doing.

## Found while verifying shutdown (fixed)

- **`davey` was never declared.** discord.py 2.7 made voice opt-in; `requirements.txt`
  listed bare `discord.py`, so every clone installed without voice support. The bot
  booted fine and only logged one WARNING, then `/play_music` would raise
  `RuntimeError('davey library needed in order to use voice')`. Fixed by declaring
  `discord.py[voice]` and having `_ensure_deps()` check `davey` explicitly.
- **`PyNaCl` version violated discord.py's pin.** `discord.py[voice]` requires
  `PyNaCl>=1.5.0,<1.6`; the venv had 1.6.2 installed. Corrected to 1.5.0.
  `tests/test_voice_deps.py` now pins both.

## Shutdown bug (fixed)

`main.py` called `await client.start(token)` bare — discord.py's `start()` never
returns and never calls `close()`, so killing the process left the gateway socket
open and Discord kept showing the bot online. Verified by running the old form and
sending SIGINT: `close()` was called 0 times.

The first fix attempt (`try/except KeyboardInterrupt`) was insufficient: **systemd
sends SIGTERM, which kills Python outright with no exception.** `main.py` now
installs in-process handlers for both SIGINT and SIGTERM via
`loop.add_signal_handler` and unwinds through `close()` either way. Live-verified:
SIGINT and SIGTERM each exit in ~2ms with zero leftover sockets.

`kill -9` remains unrecoverable by design — no handler can run.
