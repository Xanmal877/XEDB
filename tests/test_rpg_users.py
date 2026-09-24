"""Tests for RPG player isolation and monster catalog loading."""

import discord
from discord.ext import commands

from Cogs.RPGCog import RPG
from Cogs.util import MONSTERS_PATH, load_json


def _rpg(tmp_path, monkeypatch):
    import Cogs.RPGCog as rpgcog

    monkeypatch.setattr(rpgcog, "PLAYERS_PATH", tmp_path / "players.json")
    monkeypatch.setattr(rpgcog, "SHOP_PATH", tmp_path / "shop-items.json")
    monkeypatch.setattr(rpgcog, "MONSTERS_PATH", tmp_path / "monsters.json")
    client = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    return RPG(client)


def test_get_user_does_not_share_mutable_defaults(tmp_path, monkeypatch):
    rpg = _rpg(tmp_path, monkeypatch)
    u1 = rpg.get_user("1")
    u2 = rpg.get_user("2")
    u1["inventory"]["potion"] = 1
    u1["skills"].append("Fireball")
    u1["cooldowns"]["explore"] = 123
    assert u2["inventory"] == {}
    assert u2["skills"] == []
    assert u2["cooldowns"] == {}


def test_tracked_monsters_file_is_a_list():
    data = load_json(MONSTERS_PATH, default=[])
    assert isinstance(data, list)
    assert any(m.get("name") == "Goblin" for m in data)


def test_rpg_loads_monsters_from_disk(tmp_path, monkeypatch):
    import Cogs.RPGCog as rpgcog
    from Cogs.util import save_json

    monsters_path = tmp_path / "monsters.json"
    save_json(monsters_path, [{"name": "UnitRat", "min_level": 1, "max_level": 1, "health": 1, "attack": 1}])
    monkeypatch.setattr(rpgcog, "PLAYERS_PATH", tmp_path / "players.json")
    monkeypatch.setattr(rpgcog, "SHOP_PATH", tmp_path / "shop-items.json")
    monkeypatch.setattr(rpgcog, "MONSTERS_PATH", monsters_path)
    client = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    rpg = RPG(client)
    assert rpg.monsters[0]["name"] == "UnitRat"
