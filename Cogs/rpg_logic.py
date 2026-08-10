"""Pure game-balance logic for the RPG cog.

No discord imports here - only stdlib. The cog imports this module and calls
these functions instead of doing inline math.
"""

import math
import random

SKILL_COSTS = {
    "Power Strike": {"stamina": 10},
    "Mana Shield": {"mana": 10},
    "Fireball": {"mana": 15},
    "Dodge": {"stamina": 10},
}


def player_attack_damage(attack: int, level: int) -> int:
    """Player base damage: attack scaled by level plus a small variance."""
    return max(1, attack + (level - 1) * 2 + random.randint(-2, 2))


def monster_attack_damage(attack: int, defense: int) -> int:
    """Monster damage reduced by the player's defense, minimum 1."""
    return max(1, attack - defense)


def xp_reward(monster: dict) -> int:
    """XP gained for defeating a monster, scaled by difficulty."""
    return monster["attack"] * 5 + monster["health"] // 5


def xp_to_next_level(level: int) -> int:
    """XP required to advance from *level* to the next one."""
    return level * 100


def apply_level_up(user: dict) -> None:
    """Level up: grow stats, then heal to full."""
    user["max_health"] += 5
    user["attack"] += 2
    user["defense"] += 1
    user["max_stamina"] += 10
    user["max_mana"] += 10
    user["health"] = user["max_health"]
    user["stamina"] = user["max_stamina"]
    user["mana"] = user["max_mana"]


def roll_crit(base_damage: int) -> int:
    """10% chance to deal 1.5x damage."""
    if random.random() < 0.1:
        return int(base_damage * 1.5)
    return base_damage


def skill_power_strike(base_damage: int) -> int:
    """Power Strike deals double damage."""
    return base_damage * 2


def skill_fireball(base_damage: int) -> int:
    """Fireball deals 2.5x damage."""
    return math.floor(base_damage * 2.5)


def skill_dodge_succeeds() -> bool:
    """Dodge avoids the incoming hit 50% of the time."""
    return random.random() < 0.5


def skill_mana_shield(damage: int) -> int:
    """Mana Shield halves incoming damage."""
    return math.ceil(damage / 2)


def _distance_to_range(level: int, monster: dict) -> int:
    """Distance from *level* to a monster's level range (0 if inside it)."""
    low = monster.get("min_level", 1)
    high = monster.get("max_level", low)
    if level < low:
        return low - level
    if level > high:
        return level - high
    return 0


def choose_monster(monsters: list, level: int) -> dict:
    """Pick a monster appropriate for *level*.

    Prefers monsters whose level range contains *level*; if none fit, picks
    the monsters with the smallest level gap and chooses one at random.
    """
    if not monsters:
        return None
    eligible = [m for m in monsters if _distance_to_range(level, m) == 0]
    if eligible:
        return random.choice(eligible)
    best_gap = min(_distance_to_range(level, m) for m in monsters)
    closest = [m for m in monsters if _distance_to_range(level, m) == best_gap]
    return random.choice(closest)
