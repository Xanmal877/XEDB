"""Tests for the pure RPG combat/growth logic in Cogs/rpg_logic.py."""

import random

from Cogs import rpg_logic

MONSTERS = [
    {"name": "Rat", "min_level": 1, "max_level": 3, "health": 20, "attack": 2},
    {"name": "Orc", "min_level": 3, "max_level": 8, "health": 80, "attack": 8},
    {"name": "Kraken", "min_level": 20, "max_level": 25, "health": 250, "attack": 18},
]


def test_player_attack_damage_floor():
    assert rpg_logic.player_attack_damage(1, 1) >= 1


def test_player_attack_damage_scales_with_level():
    random.seed(42)
    low = rpg_logic.player_attack_damage(10, 1)
    random.seed(42)
    high = rpg_logic.player_attack_damage(10, 10)
    assert high > low


def test_monster_attack_damage_floor():
    assert rpg_logic.monster_attack_damage(2, 5) == 1


def test_monster_attack_damage_reduced_by_defense():
    assert rpg_logic.monster_attack_damage(10, 4) == 6


def test_xp_reward_scales():
    assert rpg_logic.xp_reward({"attack": 5, "health": 50}) == 35
    assert rpg_logic.xp_reward({"attack": 10, "health": 100}) == 70


def test_xp_to_next_level():
    assert rpg_logic.xp_to_next_level(1) == 100
    assert rpg_logic.xp_to_next_level(4) == 400


def test_apply_level_up_grows_stats_and_heals():
    user = {
        "level": 1,
        "health": 30,
        "max_health": 100,
        "stamina": 10,
        "max_stamina": 100,
        "mana": 10,
        "max_mana": 100,
        "attack": 10,
        "defense": 5,
    }
    rpg_logic.apply_level_up(user)
    assert user["max_health"] == 105
    assert user["attack"] == 12
    assert user["defense"] == 6
    assert user["health"] == user["max_health"]
    assert user["stamina"] == user["max_stamina"]
    assert user["mana"] == user["max_mana"]


def test_roll_crit_may_boost():
    random.seed(0)  # ensures a crit roll succeeds in this seed
    assert rpg_logic.roll_crit(100) >= 100


def test_skills():
    assert rpg_logic.skill_power_strike(10) == 20
    assert rpg_logic.skill_fireball(10) == 25
    assert rpg_logic.skill_mana_shield(11) == 6


def test_skill_costs_defined():
    assert rpg_logic.SKILL_COSTS["Power Strike"] == {"stamina": 10}
    assert rpg_logic.SKILL_COSTS["Fireball"] == {"mana": 15}


def test_choose_monster_prefers_in_range():
    random.seed(7)
    monster = rpg_logic.choose_monster(MONSTERS, 2)
    assert monster["name"] == "Rat"


def test_choose_monster_falls_back_to_closest():
    # Level 30 has no in-range monster; closest is the Kraken (gap 5 vs 10/22).
    monster = rpg_logic.choose_monster(MONSTERS, 30)
    assert monster["name"] == "Kraken"


def test_choose_monster_returns_none_for_empty():
    assert rpg_logic.choose_monster([], 1) is None
