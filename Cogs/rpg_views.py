"""RPG Discord views (menu, battle, skills, shop)."""

import datetime
import logging
import random

import discord
from discord.ui import Button

from . import rpg_logic
from .util import PLAYERS_PATH, SHOP_PATH, save_json

logger = logging.getLogger(__name__)

MENU_TITLE = "🔮 Adventure Menu - Choose an action:"

def build_stats_embed(user: dict, display_name: str) -> discord.Embed:
    """Single source for the stats panel used by both `/stats` and the RPG menu."""
    embed = discord.Embed(title=f"{display_name}'s Stats", color=0x00FF00)
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
    return embed


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
        embed = build_stats_embed(user, interaction.user.display_name)
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
            if not rpg_logic.is_known_skill(skill_name):
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

