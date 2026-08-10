import asyncio
import copy
import datetime
import logging
import random

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button

from . import rpg_logic
from .util import MONSTERS_PATH, PLAYERS_PATH, SHOP_PATH, load_json, save_json

logger = logging.getLogger(__name__)

MENU_TITLE = "🔮 Adventure Menu - Choose an action:"

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


class RPGView(discord.ui.View):
    def __init__(self, cog, user_id):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ This menu is not for you!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Explore", style=discord.ButtonStyle.primary)
    async def explore_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        response = await self.cog.explore_action(interaction)
        await interaction.response.edit_message(content=response, embed=None, view=self)

    @discord.ui.button(label="Battle", style=discord.ButtonStyle.danger)
    async def battle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = self.cog.get_user(self.user_id)
        if user.get("defeated"):
            await interaction.response.edit_message(
                content="💀 You are defeated and cannot fight! Wait for health regeneration or use a potion.",
                view=self,
            )
            return
        now = datetime.datetime.now().timestamp()
        last_battle = user["cooldowns"].get("battle", 0)
        if now - last_battle < 10:
            remaining = 10 - (now - last_battle)
            await interaction.response.edit_message(
                content=f"⏳ You need to wait {remaining:.1f}s before starting a new battle!",
                view=self,
            )
            return
        if "current_monster" not in user:
            await interaction.response.edit_message(
                content="❌ No monster to fight! Use Explore first!",
                view=self,
            )
            return
        battle_view = BattleView(self.cog, self.user_id)
        await battle_view.create_embed()
        await interaction.response.edit_message(
            content="⚔️ Battle!",
            embed=battle_view.embed,
            view=battle_view,
        )

    @discord.ui.button(label="Shop", style=discord.ButtonStyle.success)
    async def shop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        shop_view = ShopView(self.cog, self.user_id)
        await shop_view.create_embed()
        await interaction.response.edit_message(
            content="🛒 RPG Shop",
            embed=shop_view.embed,
            view=shop_view,
        )

    @discord.ui.button(label="Inventory", style=discord.ButtonStyle.secondary)
    async def inventory_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = self.cog.get_user(self.user_id)
        embed = discord.Embed(title="Inventory", color=0x00FF00)
        if not user["inventory"]:
            embed.description = "Your inventory is empty!"
        else:
            for item, qty in user["inventory"].items():
                embed.add_field(name=item.capitalize(), value=f"Quantity: {qty}", inline=True)
        await interaction.response.edit_message(content="🎒 Inventory", embed=embed, view=self)

    @discord.ui.button(label="Stats", style=discord.ButtonStyle.secondary)
    async def stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = self.cog.get_user(self.user_id)
        embed = discord.Embed(title=f"{interaction.user.display_name}'s Stats", color=0x00FF00)
        embed.add_field(name="Level", value=user["level"], inline=True)
        embed.add_field(name="Health", value=f"{user['health']}/{user['max_health']}", inline=True)
        embed.add_field(name="Attack", value=user["attack"], inline=True)
        embed.add_field(name="Defense", value=user["defense"], inline=True)
        embed.add_field(
            name="Experience",
            value=f"{user['experience']}/{rpg_logic.xp_to_next_level(user['level'])}",
            inline=True,
        )
        embed.add_field(name="Gold", value=user["gold"], inline=True)
        await interaction.response.edit_message(content="📊 Stats", embed=embed, view=self)


class BattleView(discord.ui.View):
    def __init__(self, cog, user_id):
        super().__init__(timeout=30)
        self.cog = cog
        self.user_id = user_id
        self.embed = None

    async def create_embed(self):
        user = self.cog.get_user(self.user_id)
        monster = user.get("current_monster", {})
        embed = discord.Embed(title="⚔️ Battle", color=0xFF0000)
        embed.add_field(
            name=f"🦖 {monster.get('name', 'Unknown').capitalize()}",
            value=f"❤️ Health: {monster.get('health', 0)}",
            inline=False,
        )
        embed.add_field(
            name="Your Health",
            value=f"❤️ {user['health']}/{user['max_health']}",
            inline=False,
        )
        self.embed = embed

    @discord.ui.button(label="Attack", style=discord.ButtonStyle.danger)
    async def attack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = await self.cog.process_attack(interaction)
        await self.cog.render_after_attack(interaction, result)

    @discord.ui.button(label="Skills", style=discord.ButtonStyle.primary)
    async def skills_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = self.cog.get_user(self.user_id)
        if not user["skills"]:
            await interaction.response.send_message("❌ You have no learned skills!", ephemeral=True)
            return
        view = SkillMenuView(self.cog, self.user_id, list(user["skills"]), learn_only=False)
        await interaction.response.edit_message(
            content="🔮 Choose a skill to use:",
            view=view,
        )

    @discord.ui.button(label="Flee", style=discord.ButtonStyle.secondary)
    async def flee_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = self.cog.get_user(self.user_id)
        if random.random() < 0.5:
            del user["current_monster"]
            save_json(PLAYERS_PATH, self.cog.user_data)
            await interaction.response.edit_message(
                content="🏃♂️ You successfully fled!",
                embed=None,
                view=None,
            )
        else:
            monster = user.get("current_monster", {})
            damage = rpg_logic.monster_attack_damage(monster.get("attack", 0), user["defense"])
            user["health"] -= damage
            if user["health"] <= 0:
                user["health"] = 0
                user["defeated"] = True
                del user["current_monster"]
                save_json(PLAYERS_PATH, self.cog.user_data)
                await interaction.response.edit_message(
                    content="💀 You failed to flee and were defeated! Wait for health regeneration or use a potion to recover.",
                    embed=None,
                    view=None,
                )
            else:
                save_json(PLAYERS_PATH, self.cog.user_data)
                await self.create_embed()
                response = f"🏃♂️ You failed to flee! The {monster.get('name')} hit you for {damage} damage!"
                await interaction.response.edit_message(content=response, embed=self.embed, view=self)


class SkillMenuView(discord.ui.View):
    def __init__(self, cog, user_id, skills, learn_only=False):
        super().__init__(timeout=30)
        self.cog = cog
        self.user_id = user_id
        self.learn_only = learn_only

        for skill_name in skills:
            skill_data = next(
                (s for level in cog.SKILLS.values() for s in level if s["name"] == skill_name),
                None,
            )
            if not skill_data:
                logger.warning("Skill %s is not defined in SKILLS; skipping button", skill_name)
                continue
            label = skill_name
            if not learn_only:
                cost_map = rpg_logic.SKILL_COSTS.get(skill_name, {})
                cost_label = " · ".join(f"{k} {v}" for k, v in cost_map.items())
                if cost_label:
                    label += f" ({cost_label})"
            button = Button(label=label, style=discord.ButtonStyle.primary, row=0)
            button.callback = self._make_skill_callback(skill_name)
            self.add_item(button)

        back_button = Button(label="Back", style=discord.ButtonStyle.secondary, row=1)
        back_button.callback = self._back_callback
        self.add_item(back_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ This menu is not for you!", ephemeral=True)
            return False
        return True

    def _make_skill_callback(self, skill_name):
        async def _callback(interaction: discord.Interaction):
            if self.learn_only:
                await self._learn_skill(interaction, skill_name)
            else:
                await self._use_skill(interaction, skill_name)

        return _callback

    async def _learn_skill(self, interaction: discord.Interaction, skill_name: str):
        user = self.cog.get_user(self.user_id)
        if skill_name not in user["skills"]:
            user["skills"].append(skill_name)
            save_json(PLAYERS_PATH, self.cog.user_data)
        menu_view = RPGView(self.cog, self.user_id)
        await interaction.response.edit_message(
            content=f"✅ Learned **{skill_name}**!\n\n{MENU_TITLE}",
            embed=None,
            view=menu_view,
        )

    async def _use_skill(self, interaction: discord.Interaction, skill_name: str):
        result = await self.cog.process_attack(interaction, skill_name=skill_name)
        await self.cog.render_after_attack(interaction, result)

    async def _back_callback(self, interaction: discord.Interaction):
        if self.learn_only:
            menu_view = RPGView(self.cog, self.user_id)
            await interaction.response.edit_message(
                content=MENU_TITLE,
                embed=None,
                view=menu_view,
            )
        else:
            battle_view = BattleView(self.cog, self.user_id)
            await battle_view.create_embed()
            await interaction.response.edit_message(
                content="⚔️ Battle!",
                embed=battle_view.embed,
                view=battle_view,
            )


class ShopView(discord.ui.View):
    def __init__(self, cog, user_id):
        super().__init__(timeout=30)
        self.cog = cog
        self.user_id = user_id
        self.embed = None
        self._populate_buttons()

    def _populate_buttons(self):
        for idx, item in enumerate(self.cog.shop_data.get("items", [])):
            button = Button(
                label=f"Buy {item['name'].capitalize()} ({item['price']}g)",
                style=discord.ButtonStyle.success,
                disabled=item["stock"] <= 0,
            )
            button.callback = self._make_buy_callback(idx)
            self.add_item(button)

        back_button = Button(label="Back to Menu", style=discord.ButtonStyle.secondary)
        back_button.callback = self._back_to_menu
        self.add_item(back_button)

    def _make_buy_callback(self, idx):
        async def _buy(interaction: discord.Interaction):
            await self._handle_buy(interaction, idx)

        return _buy

    async def _back_to_menu(self, interaction: discord.Interaction):
        menu_view = RPGView(self.cog, self.user_id)
        await interaction.response.edit_message(
            content=MENU_TITLE,
            embed=None,
            view=menu_view,
        )

    async def create_embed(self):
        user = self.cog.get_user(self.user_id)
        self.embed = discord.Embed(title="🛒 RPG Shop", color=0x2B2D31)
        self.embed.set_footer(text=f"Your Gold: {user['gold']} 💰")
        for item in self.cog.shop_data.get("items", []):
            self.embed.add_field(
                name=f"{item['name'].capitalize()} ({item['stock']} left)",
                value=f"Price: {item['price']}g\nType: {item['type']}",
                inline=True,
            )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ This shop isn't for you!", ephemeral=True)
            return False
        return True

    async def _handle_buy(self, interaction: discord.Interaction, item_idx: int):
        user = self.cog.get_user(self.user_id)
        try:
            item_data = self.cog.shop_data["items"][item_idx]
        except IndexError:
            await interaction.response.send_message("❌ Item no longer available!", ephemeral=True)
            return

        if item_data["stock"] <= 0:
            await interaction.response.send_message("❌ This item is out of stock!", ephemeral=True)
            return

        if user["gold"] < item_data["price"]:
            await interaction.response.send_message("❌ You don't have enough gold!", ephemeral=True)
            return

        user["gold"] -= item_data["price"]
        user["inventory"][item_data["name"]] = user["inventory"].get(item_data["name"], 0) + 1
        self.cog.shop_data["items"][item_idx]["stock"] -= 1

        save_json(PLAYERS_PATH, self.cog.user_data)
        save_json(SHOP_PATH, self.cog.shop_data)

        shop_view = ShopView(self.cog, self.user_id)
        await shop_view.create_embed()
        await interaction.response.edit_message(
            content=f"✅ Successfully bought {item_data['name']} for {item_data['price']}g!",
            embed=shop_view.embed,
            view=shop_view,
        )


class RPG(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.user_data: dict = load_json(PLAYERS_PATH)
        self.shop_data: dict = load_json(SHOP_PATH)
        self.monsters: dict = load_json(MONSTERS_PATH)
        self.regen_task = None
        self.restock_task = None

        self.SKILLS = {
            2: [
                {"name": "Power Strike", "cost_type": "stamina", "cost": 20, "effect": {"attack_multiplier": 1.5}},
                {"name": "Mana Shield", "cost_type": "mana", "cost": 30, "effect": {"defense_bonus": 5}},
            ],
            4: [
                {"name": "Fireball", "cost_type": "mana", "cost": 40, "effect": {"damage_boost": 10}},
                {"name": "Dodge", "cost_type": "stamina", "cost": 25, "effect": {"evasion_chance": 0.3}},
            ],
        }

        self.items = {
            "potion": {"type": "heal", "value": 30},
            "sword": {"type": "weapon", "value": 5},
            "shield": {"type": "armor", "value": 5},
            "rare_artifact": {"type": "special", "value": 50},
        }

        self._default_shop_items = [
            {"name": "potion", "price": 50, "stock": 10, "type": "heal"},
            {"name": "sword", "price": 100, "stock": 5, "type": "weapon"},
            {"name": "shield", "price": 80, "stock": 5, "type": "armor"},
            {"name": "rare_artifact", "price": 500, "stock": 1, "type": "special"},
        ]

        if not self.shop_data:
            self.shop_data = {"items": copy.deepcopy(self._default_shop_items)}
            save_json(SHOP_PATH, self.shop_data)

        if not self.monsters:
            self.monsters = [
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
            save_json(MONSTERS_PATH, self.monsters)

    def get_user(self, user_id: str) -> dict:
        user = self.user_data.setdefault(user_id, {})
        for key, default in DEFAULT_USER.items():
            if key not in user:
                user[key] = default
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
            skill_data = next(
                (s for level in self.SKILLS.values() for s in level if s["name"] == skill_name),
                None,
            )
            if not skill_data:
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
                            if skill["name"] not in owned:
                                unlock_names.append(skill["name"])
                                owned.add(skill["name"])
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
        embed = discord.Embed(title=f"{interaction.user.display_name}'s Stats", color=0x00FF00)
        embed.add_field(name="Level", value=user["level"], inline=True)
        embed.add_field(name="Health", value=f"{user['health']}/{user['max_health']}", inline=True)
        embed.add_field(name="Stamina", value=f"{user['stamina']}/{user['max_stamina']}", inline=True)
        embed.add_field(name="Mana", value=f"{user['mana']}/{user['max_mana']}", inline=True)
        embed.add_field(name="Attack", value=user["attack"], inline=True)
        embed.add_field(name="Defense", value=user["defense"], inline=True)
        embed.add_field(
            name="Experience",
            value=f"{user['experience']}/{rpg_logic.xp_to_next_level(user['level'])}",
            inline=True,
        )
        embed.add_field(name="Gold", value=user["gold"], inline=True)
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
