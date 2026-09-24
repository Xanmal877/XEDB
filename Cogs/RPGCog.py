import asyncio
import copy
import datetime
import logging
import random

import discord
from discord import app_commands
from discord.ext import commands, tasks

from . import rpg_logic
from .rpg_views import MENU_TITLE, BattleView, RPGView, SkillMenuView, build_stats_embed
from .util import MONSTERS_PATH, PLAYERS_PATH, SHOP_PATH, load_json, save_json

logger = logging.getLogger(__name__)

DEFAULT_USER = {
    "level": 1,
    "health": 100,
    "max_health": 100,
    "stamina": 100,
    "max_stamina": 100,
    "mana": 100,
    "max_mana": 100,
    "attack": 10,
    "defense": 5,
    "experience": 0,
    "gold": 0,
    "inventory": {},
    "cooldowns": {},
    "skills": [],
    "defeated": False,
}


SKILL_UNLOCKS = rpg_logic.SKILL_UNLOCKS


ITEM_EFFECTS = {
    "potion": {"type": "heal", "value": 30},
    "sword": {"type": "weapon", "value": 5},
    "shield": {"type": "armor", "value": 5},
    "rare_artifact": {"type": "special", "value": 50},
}

SHOP_PRICES = {
    "potion": 50,
    "sword": 100,
    "shield": 80,
    "rare_artifact": 500,
}

SHOP_STOCK = {
    "potion": 10,
    "sword": 5,
    "shield": 5,
    "rare_artifact": 1,
}

DEFAULT_MONSTERS = [
    {"name": "Goblin", "min_level": 1, "max_level": 5, "health": 50, "attack": 5},
    {"name": "Rat", "min_level": 1, "max_level": 3, "health": 20, "attack": 2},
    {"name": "Giant Spider", "min_level": 1, "max_level": 4, "health": 25, "attack": 3},
    {"name": "Skeleton", "min_level": 2, "max_level": 5, "health": 35, "attack": 4},
    {"name": "Slime", "min_level": 1, "max_level": 3, "health": 30, "attack": 2},
    {"name": "Wolf", "min_level": 2, "max_level": 5, "health": 40, "attack": 5},
    {"name": "Kobold", "min_level": 1, "max_level": 5, "health": 45, "attack": 4},
    {"name": "Giant Bat", "min_level": 1, "max_level": 4, "health": 22, "attack": 3},
    {"name": "Zombie", "min_level": 2, "max_level": 6, "health": 50, "attack": 4},
    {"name": "Imp", "min_level": 1, "max_level": 4, "health": 25, "attack": 3},
    {"name": "Orc", "min_level": 3, "max_level": 8, "health": 80, "attack": 8},
    {"name": "Hobgoblin", "min_level": 5, "max_level": 10, "health": 70, "attack": 7},
    {"name": "Wight", "min_level": 6, "max_level": 12, "health": 85, "attack": 8},
    {"name": "Ogre", "min_level": 7, "max_level": 14, "health": 100, "attack": 10},
    {"name": "Troll", "min_level": 8, "max_level": 15, "health": 120, "attack": 12},
    {"name": "Dragon", "min_level": 10, "max_level": 20, "health": 200, "attack": 15},
    {"name": "Lich", "min_level": 15, "max_level": 20, "health": 180, "attack": 14},
    {"name": "Kraken", "min_level": 20, "max_level": 25, "health": 250, "attack": 18},
]


class RPG(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.user_data: dict = load_json(PLAYERS_PATH)
        self.shop_data: dict = load_json(SHOP_PATH)
        self.monsters = load_json(MONSTERS_PATH, default=[])
        self.regen_task = None
        self.restock_task = None

        self.SKILLS = SKILL_UNLOCKS
        self.items = ITEM_EFFECTS

        self._default_shop_items = [
            {"name": name, "price": SHOP_PRICES[name], "stock": SHOP_STOCK[name], "type": ITEM_EFFECTS[name]["type"]}
            for name in ITEM_EFFECTS
        ]

        if not self.shop_data:
            self.shop_data = {"items": copy.deepcopy(self._default_shop_items)}
            save_json(SHOP_PATH, self.shop_data)

        if not self.monsters:
            self.monsters = copy.deepcopy(DEFAULT_MONSTERS)
            save_json(MONSTERS_PATH, self.monsters)

    def get_user(self, user_id: str) -> dict:
        user = self.user_data.setdefault(user_id, {})
        for key, default in DEFAULT_USER.items():
            if key not in user:
                user[key] = copy.deepcopy(default)
        if not isinstance(user.get("inventory"), dict):
            user["inventory"] = {}
        if not isinstance(user.get("cooldowns"), dict):
            user["cooldowns"] = {}
        if not isinstance(user.get("skills"), list):
            user["skills"] = []
        user["health"] = min(user["health"], user["max_health"])
        user["stamina"] = min(user["stamina"], user["max_stamina"])
        user["mana"] = min(user["mana"], user["max_mana"])
        user["defeated"] = bool(user.get("defeated"))
        return user

    async def cog_load(self):
        """Start the regeneration and restock tasks when cog loads."""
        self.regen_task = asyncio.create_task(self.regen_resources())
        self.restock_task = self.restock_shop.start()

    def cog_unload(self):
        """Cancel regeneration and restock tasks on cog unload."""
        if self.regen_task and not self.regen_task.done():
            self.regen_task.cancel()
        if self.restock_task:
            self.restock_task.cancel()

    @tasks.loop(minutes=10)
    async def restock_shop(self):
        """Restore each shop item's stock toward its default value."""
        try:
            for item in self.shop_data.get("items", []):
                default = next(
                    (d for d in self._default_shop_items if d["name"] == item.get("name")),
                    None,
                )
                if default is not None:
                    item["stock"] = min(default["stock"], item.get("stock", 0) + 1)
            save_json(SHOP_PATH, self.shop_data)
        except Exception:
            logger.exception("Error restocking shop")

    @restock_shop.before_loop
    async def before_restock(self):
        await self.client.wait_until_ready()

    async def regen_resources(self):
        """Regenerate 10 stamina/mana per minute; defeated players heal 5 HP/min."""
        await self.client.wait_until_ready()
        while not self.client.is_closed():
            try:
                await asyncio.sleep(60)
                for user_id in list(self.user_data.keys()):
                    user = self.get_user(user_id)
                    user["stamina"] = min(user["max_stamina"], user["stamina"] + 10)
                    user["mana"] = min(user["max_mana"], user["mana"] + 10)
                    if user.get("defeated"):
                        user["health"] = min(user["max_health"], user["health"] + 5)
                        if user["health"] > 0:
                            user["defeated"] = False
                save_json(PLAYERS_PATH, self.user_data)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error in regen_resources")
                await asyncio.sleep(5)

    @app_commands.command(name="register", description="Start your RPG adventure!")
    @app_commands.guild_only()
    async def register(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if user_id in self.user_data:
            await interaction.response.send_message("❌ You're already registered! Use `/playrpg` to start playing!", ephemeral=True)
            return

        self.get_user(user_id)
        save_json(PLAYERS_PATH, self.user_data)
        await interaction.response.send_message("🎉 Welcome to the RPG! Use `/playrpg` to access your adventure menu!", ephemeral=True)

    @app_commands.command(name="playrpg", description="Access your RPG menu")
    @app_commands.guild_only()
    async def playrpg(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        if user_id not in self.user_data:
            await interaction.response.send_message("❌ You need to register first with `/register`!", ephemeral=True)
            return

        view = RPGView(self, user_id)
        await interaction.response.send_message(
            MENU_TITLE,
            view=view,
            ephemeral=True,
        )

    async def explore_action(self, interaction: discord.Interaction) -> str:
        user_id = str(interaction.user.id)
        user = self.get_user(user_id)
        current_time = datetime.datetime.now().timestamp()

        if user.get("defeated"):
            return "💀 You are defeated and cannot explore! Wait for health regeneration or use a potion."

        if current_time - user["cooldowns"].get("explore", 0) < 5:
            remaining = 5 - (current_time - user["cooldowns"].get("explore", 0))
            return f"⏳ You need to wait {remaining:.1f}s before exploring again!"

        user["cooldowns"]["explore"] = current_time

        outcome = random.choice(["gold", "item", "monster", "nothing"])
        response = ""

        if outcome == "gold":
            gold_found = random.randint(10, 50)
            user["gold"] += gold_found
            response = f"💰 You found {gold_found} gold!"
        elif outcome == "item":
            item = random.choice(list(self.items.keys()))
            user["inventory"][item] = user["inventory"].get(item, 0) + 1
            response = f"🎁 You found a {item}!"
        elif outcome == "monster":
            if not self.monsters:
                return "❌ No monsters are defined in the game!"
            monster = copy.deepcopy(rpg_logic.choose_monster(self.monsters, user["level"]))
            if monster is None:
                return "❌ No monsters are defined in the game!"
            user["current_monster"] = monster
            response = f"🐉 You encountered a {monster['name']}! Use the Battle menu to fight it!"
        else:
            response = "🌲 You explored but found nothing..."

        save_json(PLAYERS_PATH, self.user_data)
        return response

    async def process_attack(self, interaction: discord.Interaction, skill_name: str | None = None):
        user = self.get_user(str(interaction.user.id))

        if user.get("defeated"):
            return ("💀 You are defeated and cannot fight!", [])
        if "current_monster" not in user:
            return ("❌ No monster to fight!", [])

        monster = user["current_monster"]

        player_damage = 0
        dodged = False
        shielded = False
        if skill_name:
            if not rpg_logic.is_known_skill(skill_name):
                return (f"❌ Skill {skill_name} not found!", [])

            cost_map = rpg_logic.SKILL_COSTS.get(skill_name, {})
            for resource, cost in cost_map.items():
                if user.get(resource, 0) < cost:
                    return (f"❌ Not enough {resource} to use {skill_name}!", [])
            for resource, cost in cost_map.items():
                user[resource] -= cost

            base_damage = rpg_logic.player_attack_damage(user["attack"], user["level"])
            if skill_name == "Power Strike":
                player_damage = rpg_logic.skill_power_strike(base_damage)
            elif skill_name == "Fireball":
                player_damage = rpg_logic.skill_fireball(base_damage)
            elif skill_name == "Dodge":
                dodged = rpg_logic.skill_dodge_succeeds()
            elif skill_name == "Mana Shield":
                shielded = True
            else:
                player_damage = base_damage
        else:
            player_damage = rpg_logic.roll_crit(rpg_logic.player_attack_damage(user["attack"], user["level"]))

        monster["health"] -= player_damage

        if monster["health"] <= 0:
            exp_gain = rpg_logic.xp_reward(monster)
            gold_gain = random.randint(10, 30)
            user["experience"] += exp_gain
            user["gold"] += gold_gain
            response = f"⚔️ You defeated the {monster['name']}!\n🏆 Gained {exp_gain} XP and {gold_gain} gold!"
            del user["current_monster"]
            user["cooldowns"]["battle"] = datetime.datetime.now().timestamp()

            unlock_names = []
            owned = set(user["skills"])
            while user["experience"] >= rpg_logic.xp_to_next_level(user["level"]):
                old_level = user["level"]
                user["level"] += 1
                rpg_logic.apply_level_up(user)
                response += f"\n🎉 Level up! You're now level {user['level']}!"
                for unlock_level in (2, 4):
                    if old_level < unlock_level <= user["level"]:
                        for skill in self.SKILLS.get(unlock_level, []):
                            if skill not in owned:
                                unlock_names.append(skill)
                                owned.add(skill)
            save_json(PLAYERS_PATH, self.user_data)
            return (response, unlock_names)

        if dodged:
            monster_damage = 0
        elif shielded:
            monster_damage = rpg_logic.skill_mana_shield(rpg_logic.monster_attack_damage(monster["attack"], user["defense"]))
        else:
            monster_damage = rpg_logic.monster_attack_damage(monster["attack"], user["defense"])

        user["health"] -= monster_damage
        save_json(PLAYERS_PATH, self.user_data)

        if user["health"] <= 0:
            user["health"] = 0
            user["defeated"] = True
            del user["current_monster"]
            return (
                "💀 You were defeated! Wait for health regeneration or use a potion to recover.",
                [],
            )

        if dodged:
            response = f"🌀 You dodged the {monster['name']}'s attack! It dealt no damage!"
        elif shielded:
            response = (
                f"🛡️ Mana Shield absorbed most of the damage!\n"
                f"💔 The {monster['name']} hit you for {monster_damage} damage!\n"
                f"❤️ Your health: {user['health']}/{user['max_health']}"
            )
        elif skill_name:
            response = (
                f"✨ You used **{skill_name}** for {player_damage} damage!\n"
                f"💔 The {monster['name']} hit you for {monster_damage} damage!\n"
                f"❤️ Your health: {user['health']}/{user['max_health']}"
            )
        else:
            response = (
                f"⚔️ You attacked the {monster['name']} for {player_damage} damage!\n"
                f"💔 The {monster['name']} hit you for {monster_damage} damage!\n"
                f"❤️ Your health: {user['health']}/{user['max_health']}"
            )
        return (response, [])

    async def render_after_attack(self, interaction: discord.Interaction, result):
        response, unlock_names = result
        user_id = str(interaction.user.id)
        user = self.get_user(user_id)

        if unlock_names:
            view = SkillMenuView(self, user_id, unlock_names, learn_only=True)
            await interaction.response.edit_message(content=response, embed=None, view=view)
            return

        if user.get("defeated"):
            await interaction.response.edit_message(content=response, embed=None, view=None)
            return

        if "current_monster" not in user:
            menu_view = RPGView(self, user_id)
            await interaction.response.edit_message(
                content=f"{response}\n\n{MENU_TITLE}",
                embed=None,
                view=menu_view,
            )
            return

        battle_view = BattleView(self, user_id)
        await battle_view.create_embed()
        await interaction.response.edit_message(
            content=response,
            embed=battle_view.embed,
            view=battle_view,
        )

    @app_commands.command(name="stats", description="Check your character stats")
    @app_commands.guild_only()
    async def stats(self, interaction: discord.Interaction):
        user = self.get_user(str(interaction.user.id))
        embed = build_stats_embed(user, interaction.user.display_name)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="use", description="Use an item from your inventory")
    @app_commands.guild_only()
    async def use(self, interaction: discord.Interaction, item: str):
        user_id = str(interaction.user.id)
        user = self.get_user(user_id)
        item = item.lower()

        if user["inventory"].get(item, 0) <= 0:
            await interaction.response.send_message(f"You don't have any {item}!", ephemeral=True)
            return

        item_data = self.items.get(item)
        if not item_data:
            await interaction.response.send_message("That item doesn't exist!", ephemeral=True)
            return

        item_type = item_data["type"]
        if item_type == "heal":
            user["health"] = min(user["max_health"], user["health"] + item_data["value"])
            user["defeated"] = False
            response = f"❤️ Healed for {item_data['value']} HP!"
        elif item_type == "weapon":
            user["attack"] += item_data["value"]
            response = f"⚔️ Attack increased by {item_data['value']}!"
        elif item_type == "armor":
            user["defense"] += item_data["value"]
            response = f"🛡️ Defense increased by {item_data['value']}!"
        elif item_type == "special":
            user["gold"] += item_data.get("value", 50)
            response = f"💰 The rare artifact granted you {item_data.get('value', 50)} gold!"
        else:
            await interaction.response.send_message("❌ That item can't be used!", ephemeral=True)
            return

        user["inventory"][item] -= 1
        if user["inventory"][item] == 0:
            del user["inventory"][item]

        save_json(PLAYERS_PATH, self.user_data)
        await interaction.response.send_message(response, ephemeral=True)


async def setup(client):
    await client.add_cog(RPG(client))
    logger.info("RPG System Online")
