"""Tests for shared cog data registries (RPG items/shop/monsters)."""

from Cogs import rpg_logic
from Cogs.RPGCog import DEFAULT_MONSTERS, ITEM_EFFECTS, SHOP_PRICES, SHOP_STOCK


def test_every_item_has_a_price_and_stock():
    assert set(ITEM_EFFECTS) == set(SHOP_PRICES) == set(SHOP_STOCK)


def test_every_item_has_a_known_effect_type():
    known = {"heal", "weapon", "armor", "special"}
    for name, effect in ITEM_EFFECTS.items():
        assert effect["type"] in known, f"{name} has unknown effect type"
        assert effect["value"] > 0


def test_default_monsters_are_well_formed():
    assert DEFAULT_MONSTERS
    for monster in DEFAULT_MONSTERS:
        assert monster["min_level"] <= monster["max_level"]
        assert monster["health"] > 0
        assert monster["attack"] > 0


def test_every_monster_is_choosable_at_some_level():
    # A monster whose range never overlaps a player level is dead content.
    for monster in DEFAULT_MONSTERS:
        for level in range(1, 26):
            if rpg_logic.choose_monster([monster], level) == monster:
                break
        else:
            raise AssertionError(f"{monster['name']} is unreachable at every level")
