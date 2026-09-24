"""Load and unload the bot's cogs."""

import contextlib
import logging

from discord.ext import commands

from llm_setup import COG_MODULES, ENABLED_EXTENSIONS

logger = logging.getLogger(__name__)

ALL_COGS = list(COG_MODULES.values())


class CogManager:
    def __init__(self, client, extensions: list[str] | None = None):
        self.client = client
        self.extensions = list(extensions) if extensions is not None else list(ENABLED_EXTENSIONS)

    async def load_cogs(self):
        await self.remove_cogs()

        loaded = []
        for cog in self.extensions:
            try:
                await self.client.load_extension(cog)
                loaded.append(cog.split(".")[-1])
            except Exception as e:
                logger.warning("Failed to load %s: %s", cog, e)

        logger.info("Loaded cogs: %s", ", ".join(loaded) if loaded else "none")

    async def remove_cogs(self):
        for cog in ALL_COGS:
            with contextlib.suppress(commands.ExtensionNotLoaded):
                await self.client.unload_extension(cog)
