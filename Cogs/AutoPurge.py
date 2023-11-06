from discord.ext import commands, tasks
import discord
import asyncio
from datetime import timedelta, datetime
from config import music_channel

class AutoPurge(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.channel_id = music_channel  # Replace with the ID of the channel you want to auto-purge
        self.purge_after_days = 7  # Set to 7 days
        self.auto_purge.start()  # Start the background task

    @commands.Cog.listener()
    async def on_ready(self):
        await self.client.tree.sync()
        print("AutoPurge Enabled")

    def cog_unload(self):
        self.auto_purge.cancel()  # Stop the background task when the cog is unloaded

    @tasks.loop(hours=24)  # Run this task every 24 hours
    async def auto_purge(self):
        channel = self.client.get_channel(self.channel_id)
        if channel:
            # Calculate the oldest message time allowed (1 week ago from now)
            oldest_allowed_time = datetime.utcnow() - timedelta(days=self.purge_after_days)
            
            # Fetch messages to delete
            messages_to_delete = []
            async for message in channel.history(limit=None, after=oldest_allowed_time, oldest_first=True):
                # Add messages to the list if they are older than a week
                if message.created_at < oldest_allowed_time:
                    messages_to_delete.append(message)
            
            # Bulk delete messages that are within the 14-day limit
            # Note: Bulk delete has a limit of 100 messages per call
            while messages_to_delete:
                try:
                    await channel.delete_messages(messages_to_delete[:100])
                    messages_to_delete = messages_to_delete[100:]
                except discord.NotFound:
                    # If some messages are not found, skip them
                    pass
                except discord.HTTPException as e:
                    print(f"Failed to delete messages: {e}")
                    break  # If there's an HTTPException, break out of the loop
                await asyncio.sleep(1.5)  # Sleep to respect rate limits

    @auto_purge.before_loop
    async def before_auto_purge(self):
        print('Waiting for the bot to be ready before starting the auto-purge task...')
        await self.client.wait_until_ready()

    # Add any other commands or listeners you need for this cog

async def setup(client):
    await client.add_cog(AutoPurge(client))
