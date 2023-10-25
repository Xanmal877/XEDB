from discord import Button, ButtonStyle, Embed
import json
from discord.ext import commands

character_database = "F:/Coding Projects/Bots/Python/Xans-Python-Discord-Bot/RPG Files/character_database.json"
monster_database = "F:/Coding Projects/Bots/Python/Xans-Python-Discord-Bot/RPG Files/monster_database.json"


class RPGCog(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.character_database = {}
        self.monster_database = {
            "slime": {"health": 20, "attack": 5}
        }
        self.battles = {}  # To keep track of ongoing battles

    @commands.Cog.listener()
    async def on_ready(self):
        print("Basic RPG Ready!")
        try:
            with open(character_database, "r") as f:
                self.character_database = json.load(f)
            with open(monster_database, "r") as f:
                self.monster_database = json.load(f)
            print(f"Loaded character_database: {self.character_database}")
            print(f"Loaded monster_database: {self.monster_database}")
        except FileNotFoundError:
            print("No JSON file found, initializing empty database.")
            self.character_database = {}

    @commands.command(name="info", ignore_case=True)
    async def info(self, ctx):
        print("info command called")  # add this line to check if the function is being called
        embed = Embed(title="🌟 RPG Bot Commands 🌟", description="List of available commands:", color=0x00ff00)
        embed.add_field(name="!start", value="Start your RPG adventure!", inline=False)
        embed.add_field(name="!create [name] [class]", value="Create a new character.", inline=False)
        embed.add_field(name="!stats", value="View your character's stats.", inline=False)
        embed.add_field(name="!rename [new_name]", value="Rename your character.", inline=False)
        embed.add_field(name="!change_class [new_class]", value="Change your character's class.", inline=False)
        embed.add_field(name="!battle [monster_name]", value="Battle with a monster.", inline=False)

        print("sending message")  # add this line to check if the message is being sent
        await ctx.send(embed=embed)

    @commands.command(name="start", ignore_case=True)
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

    @commands.command(name="create", ignore_case=True)
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

    @commands.command(name="stats", ignore_case=True)
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


    @commands.command(name="battle", ignore_case=True)
    async def battle(self, ctx, monster_name):
        author_id = str(ctx.author.id)

        if author_id not in self.character_database:
            await ctx.send("You don't have a character yet.")
            return

        if monster_name not in self.monster_database:
            await ctx.send("That monster does not exist.")
            return

        player = self.character_database[author_id]
        monster = self.monster_database[monster_name].copy()

        self.battles[author_id] = {"player": player, "monster": monster}
        await ctx.send(f"A wild {monster_name} appears! Use `!attack` or `!defend` to take actions.")

    @commands.command(name='attack', aliases=['atk'], ignore_case=True)
    async def attack(self, ctx, monster_name):
        author_id = str(ctx.author.id)

        if author_id not in self.battles:
            await ctx.send("You're not in a battle.")
            return

        battle = self.battles[author_id]
        player = battle["player"]
        monster = battle["monster"]

        player_attack = player.get("attack", 0)
        monster_defense = monster.get("defense", 0)

        # Perform attack calculations here
        damage = player_attack - monster_defense
        if damage < 0:
            damage = 0  # Make sure damage is never negative

        monster["health"] -= damage

        await ctx.send(f"You attack the {monster_name} and deal {damage} damage!")

        if monster["health"] <= 0:
            experience_gain = monster.get("experience", 0)
            player["experience"] += experience_gain
            await ctx.send(f"You have defeated the monster and gained {experience_gain} experience points!")
            del self.battles[author_id]
            return

        # Monster turn
        monster_attack = monster.get("attack", 0)
        player_defense = player.get("defense", 0)

        # Perform monster attack calculations here
        damage = monster_attack - player_defense
        if damage < 0:
            damage = 0  # Make sure damage is never negative

        player["health"] -= damage

        await ctx.send(f"The {monster_name} attacks you and deals {damage} damage!")

        if player["health"] <= 0:
            await ctx.send(f"Game over! You were defeated by the {monster}.")
            del self.battles[author_id]  # Remove the battle as it's now over

    @commands.command(name="defend", ignore_case=True)
    async def defend(self, ctx):
        author_id = str(ctx.author.id)

        if author_id not in self.battles:
            await ctx.send("You're not in a battle.")
            return

        battle = self.battles[author_id]
        battle["player_defense_boost"] = 20  # Increase defense by 20 for this turn

        await ctx.send("You take a defensive stance, boosting your defense by 20 for this turn!")
        
        
async def setup(client):
    await client.add_cog(RPGCog(client))