from discord import Button, ButtonStyle, Embed
import discord
from discord.ext import commands
from discord.ui import Button, View
import json
import asyncio  # For asynchronous sleep
from random import randint
import sys

character_database = "F:\Coding Projects\Bots\Python\Xans-Python-Discord-Bot\RPG Files\character_database.json"
monster_database = "F:\Coding Projects\Bots\Python\Xans-Python-Discord-Bot\RPG Files\monster_database.json"


class RPGCog(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.character_database = {}
        self.monster_database = {
    "slime": {"health": 20, "attack": 5, "defense": 2, "experience": 3}
}

    @commands.Cog.listener()
    async def on_ready(self):
        print("Basic RPG Ready!")
        try:
            with open(character_database, "r") as f:
                self.character_database = await json.load(f)
            with open(monster_database, "r") as f:
                self.monster_database = await json.load(f)
            print(f"Loaded character_database: {self.character_database}")
        except FileNotFoundError:
            print("No JSON file found, initializing empty database.")
            self.character_database = {}

    @commands.command()
    async def start(self, ctx):
        # Try to load the database first
        try:
            with open(character_database, "r") as f:
                self.character_database = json.load(f)
        except FileNotFoundError:
            await ctx.send("Database file not found, initializing empty database.")
            self.character_database = {}
            
        # Continue with the original functionality
        author_id = str(ctx.author.id)
        if author_id not in self.character_database:
            await ctx.send("You don't have a character yet. Create one using the 'create (name) (class)' command.")
            return
        player_character = self.character_database[author_id]
        await ctx.send(f"Welcome back, {ctx.author.display_name}! Your adventure begins now as a {player_character['class']}!")



    @commands.command(name="create")
    async def create(self, ctx, character_name, character_class):
        author_id = str(ctx.author.id)
        valid_classes = ["warrior", "mage", "rogue", "monk"]
        if character_class.lower() not in valid_classes:
            await ctx.send("Invalid character class. Choose from: Warrior, Mage, Rogue, Monk.")
            return
        if author_id in self.character_database:
            await ctx.send("You already have a character. Use a different name.")
            return

        # Default DnD stats
        base_stats = {
            "strength": 10,
            "dexterity": 10,
            "constitution": 10,
            "intelligence": 10,
            "wisdom": 10,
            "charisma": 10
        }

        # Add statistics based on class
        if character_class.lower() == "warrior":
            stats = {"health": 100, "attack": 10, "defense": 10, "magic_attack": 2, "magic_defense": 5, "strength": 15}
        elif character_class.lower() == "mage":
            stats = {"health": 70, "attack": 8, "defense": 5, "magic_attack": 15, "magic_defense": 10, "intelligence": 15}
        elif character_class.lower() == "rogue":
            stats = {"health": 80, "attack": 12, "defense": 8, "magic_attack": 7, "magic_defense": 7, "dexterity": 15}
        else: # monk
            stats = {"health": 100, "attack": 12, "defense": 8, "magic_attack": 3, "magic_defense": 8, "wisdom": 15}

        # Merge the base stats and specific stats
        combined_stats = {**base_stats, **stats}

        # Create new character
        new_character = {
            "name": character_name,
            "class": character_class.lower(),
            "level": 1,
            "experience": 0,
            **combined_stats  # Merge the stats into the new character
        }

        self.character_database[author_id] = new_character  # Add new character to dictionary

        with open(character_database, "w") as f:
            json.dump(self.character_database, f)

        await ctx.send(f"Character {character_name} created successfully!")  # Send confirmation message




    @commands.command()
    async def stats(self, ctx):
        author_id = str(ctx.author.id)
        if author_id not in self.character_database:
            await ctx.send("You don't have a character yet. Create one using the 'create (name) (class)' command.")
            return
        char = self.character_database[author_id]
        await ctx.send(f"""🌟 Character Stats for {char['name']} 🌟
        Class: {char['class'].capitalize()}
        Level: {char['level']}
        Experience: {char['experience']}
        💖 Health: {char['health']}
        🗡️ Attack: {char['attack']}
        🛡️ Defense: {char['defense']}
        🌟 Magic Attack: {char['magic_attack']}
        ✨ Magic Defense: {char['magic_defense']}
        💪 Strength: {char['strength']}
        🤸‍♂️ Dexterity: {char['dexterity']}
        🛡️ Constitution: {char['constitution']}
        🧠 Intelligence: {char['intelligence']}
        🌟 Wisdom: {char['wisdom']}
        😄 Charisma: {char['charisma']}""")





    @commands.command(name="rename")
    async def rename_character(self, ctx, new_name: str):
        author_id = str(ctx.author.id)
        if author_id not in self.character_database:
            await ctx.send("You don't have a character yet. Create one using the 'create (name) (class)' command.")
            return

        self.character_database[author_id]["name"] = new_name
        with open(character_database, "w") as f:
            json.dump(self.character_database, f)

        await ctx.send(f"Character renamed to {new_name}!")


    @commands.command(name="change_class")
    async def change_class(self, ctx, new_class: str):
        author_id = str(ctx.author.id)
        valid_classes = ["warrior", "mage", "rogue", "monk"]
        if new_class.lower() not in valid_classes:
            await ctx.send("Invalid character class. Choose from: Warrior, Mage, Rogue, Monk.")
            return

        if author_id not in self.character_database:
            await ctx.send("You don't have a character yet. Create one using the 'create (name) (class)' command.")
            return

        # Add statistics based on class
        if new_class.lower() == "warrior":
            stats = {"health": 100, "attack": 10, "defense": 10, "magic_attack": 2, "magic_defense": 5}
        elif new_class.lower() == "mage":
            stats = {"health": 70, "attack": 8, "defense": 5, "magic_attack": 15, "magic_defense": 10}
        elif new_class.lower() == "rogue":
            stats = {"health": 80, "attack": 12, "defense": 8, "magic_attack": 7, "magic_defense": 7}
        else: # monk
            stats = {"health": 100, "attack": 12, "defense": 8, "magic_attack": 3, "magic_defense": 8}

        self.character_database[author_id].update({"class": new_class.lower(), **stats})
        with open(character_database, "w") as f:
            json.dump(self.character_database, f)

        await ctx.send(f"Class changed to {new_class.capitalize()}!")



    @commands.command(name="battle")
    async def battle(self, ctx, monster_name):
        author_id = str(ctx.author.id)

        if author_id not in self.character_database:
            await ctx.send("You don't have a character yet. Create one using the 'create (name) (class)' command.")
            return

        if monster_name not in self.monster_database:
            await ctx.send("That monster does not exist.")
            return

        player = self.character_database[author_id]
        monster = self.monster_database[monster_name].copy()

        def check(msg):
            return msg.author == ctx.author and msg.channel == ctx.channel and \
                msg.content.lower() in ["attack", "defend"]

        while True:
            if player["health"] <= 0:
                await ctx.send(f"{player['name']} has been defeated. 😢")
                break

            if monster["health"] <= 0:
                await ctx.send(f"{monster_name} has been defeated! 🌟")
                player["experience"] += monster["experience"]
                await ctx.send(f"You gained {monster['experience']} experience points!")
                break

            await ctx.send(f"A wild {monster_name} appears! Type 'attack' to attack or 'defend' to defend.")

            try:
                msg = await self.bot.wait_for('message', timeout=30, check=check)

                if msg.content.lower() == "attack":
                    self.execute_attack(player, monster)
                    await ctx.send(f"{player['name']} hits {monster_name} for {player['last_attack']} damage! 🗡️")
                elif msg.content.lower() == "defend":
                    await ctx.send(f"{player['name']} defends!")

                self.execute_attack(monster, player)
                await ctx.send(f"{monster_name} hits {player['name']} for {monster['last_attack']} damage! 🤕")
            except asyncio.TimeoutError:
                await ctx.send("You took too long to choose an action!")
                break

        with open('character_database.json', "w") as f:
            json.dump(self.character_database, f)

    def execute_attack(self, attacker, defender):
        attack_power = randint(0, attacker["attack"])
        defender["health"] -= attack_power
        attacker["last_attack"] = attack_power






async def setup(client):
    await client.add_cog(RPGCog(client))