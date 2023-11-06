import warnings
import sys
import discord
from discord.ext import commands
import asyncio
import tracemalloc
import os
import random
from SakiVocab import load_all_vocab_files
from config import TamaToken

tracemalloc.start()

# ======================[ GLOBAL VARIABLES ]================================
user_message_logs = {} # creates message log dictionary
vocab_data = load_all_vocab_files() # Call the function to populate vocab_data

# ======================[ BOT SETUP ]======================
Token = TamaToken #Discord Bot Token

# Define the bot
client = commands.Bot(command_prefix="!", intents=discord.Intents.all())
client.chatlog_dir = "logs/"

# Add a decorator to allow only specific user IDs to run the command
def is_owner():
    def predicate(ctx):
        return ctx.author.id == 175421668850794506  # Replace with your Discord User ID
    return commands.check(predicate)


# Inside your code, before the warning occurs, you can suppress it like this:
warnings.filterwarnings("ignore", category=UserWarning)

# ======================[ UTILITY FUNCTIONS ]======================

# ==========================
# Message Logging
# ==========================

def add_message_to_log(author_id, content):
    if author_id not in user_message_logs:
        user_message_logs[author_id] = []

    user_message_logs[author_id].append({"role": "user", "content": content})

# ======================[ EVENT HANDLERS ]======================

## ---- On Ready Event ----

@client.event
async def on_ready():
    try:
        print("on_ready Triggered")
        guild = discord.utils.get(client.guilds, name='The Dark Void of Gaming')
        if guild:
            print(f"Guild found: {guild.name}")
        else:
            print("Guild not found")
            return

    except Exception as e:
        print(f"An error occurred in on_ready: {e}")

## ---- On Message Event ----

import random  # Don't forget to import the 'random' module for random choice functionality

@client.event
async def on_message(message):
    try:
        if message.content.startswith('!'):
            await client.process_commands(message)
            return

        if message.author.bot:
            return

        if message.channel.name != "tamachat":
            return

        # Add the received message to the log
        add_message_to_log(message.author.id, message.content)

        user_input = message.content.lower()  # Convert user input to lowercase for case-insensitive matching

        for key, vocab_info in vocab_data.items():
            specific_triggers = vocab_info.get("TriggerWords", set())
            random_responses = vocab_info.get("Responses", {})

            for trigger_word in specific_triggers:
                if trigger_word in user_input:
                    response_options = random_responses.get(trigger_word, [])
                    if response_options:
                        response = random.choice(response_options)
                        await message.channel.send(response)
                        return

        # If no specific trigger word is matched from any vocab file, send a default response
        default_responses = ["I'm not sure what you mean.", "Could you please clarify?", "Let's talk about something else."]
        response = random.choice(default_responses)
        await message.channel.send(response)

    except Exception as e:
        print(f"Error in on_message: {str(e)}")

    await client.process_commands(message)  # Process any remaining commands


# ======================[ MAIN ROUTINE ]======================



# ======================[ COGS]======================

@client.command()
@is_owner()  # Make sure only you can run this command
async def kill(ctx):
    await ctx.send("Shutting down...")
    await client.logout()
    await client.close()
    sys.exit(0)  # Add this line to terminate the program

@client.command()
async def load(ctx, extension):
    try:
        client.load_extension(f'Cogs.{extension}')
        await ctx.send(f'Loaded {extension} successfully!')
    except Exception as e:
        await ctx.send(f'Could not load {extension}. Error: {e}')

@client.command()
async def unload(ctx, extension):
    try:
        client.unload_extension(f'Cogs.{extension}')
        await ctx.send(f'Unloaded {extension} successfully!')
    except Exception as e:
        await ctx.send(f'Could not unload {extension}. Error: {e}')

@client.command()
async def reload(ctx, extension):
    try:
        await client.unload_extension(f'Cogs.{extension}')
        print("Cog Unloaded")
        await client.load_extension(f'Cogs.{extension}')
        print("Cog Reloaded")
        await ctx.send(f'Reloaded {extension} successfully!')
    except Exception as e:
        await ctx.send(f'Could not reload {extension}. Error: {e}')




# =====================
# Main Async Function
# =====================

async def main():
    await load()
    print("Tama Online!")
    await client.start(Token)


if __name__ == "__main__":
    asyncio.run(main())
