# -*- coding: utf-8 -*-
"""Правила игры и регрессии на исправленные ошибки."""

import random

import pytest

import PixRogue as G


# --------------------------------------------------------------- таблицы ---
def test_every_subtype_has_a_russian_name():
    for sub in G.POTIONS + G.SCROLLS + G.RINGS + G.WANDS:
        assert sub in G.SUB_RU, "нет перевода для %s" % sub


def test_weapon_and_armor_tables_are_sane():
    for name, spec in G.WEAPONS.items():
        assert spec.dice >= 1 and spec.sides >= 1
        assert isinstance(spec.throwable, bool)
    for name in G.THROWABLE_STACK:
        assert G.is_throwable(name), "%s должен метаться" % name
    assert not G.is_throwable("нет такого оружия")
    for name, ac in G.ARMOR.items():
        assert 0 < ac <= 10


def test_monster_table_fields():
    for t in G.MONSTERS:
        assert 1 <= t.dmin <= t.dmax <= G.MAX_DEPTH
        assert t.hd >= 1 and t.xp >= 0
        assert t.dmg and all(len(a) == 2 for a in t.dmg)


# ---------------------------------------------------------- обличья -------
def test_assign_looks_is_a_bijection_and_keeps_globals_intact():
    before = list(G.POTION_LOOKS)
    look = G.assign_looks(G.POTIONS, G.POTION_LOOKS)
    assert set(look) == set(G.POTIONS)
    assert len(set(look.values())) == len(G.POTIONS), "два зелья выглядят одинаково"
    assert G.POTION_LOOKS == before, "глобальный список обличий мутирован"


def test_assign_looks_survives_a_short_table():
    """Таблицы предметов и обличий правятся независимо — нехватка обличий
    не должна ронять игру с IndexError."""
    look = G.assign_looks(["a", "b", "c", "d"], ["одно", "другое"])
    assert len(set(look.values())) == 4


# ----------------------------------------------------------- персонаж -----
def test_player_rejects_typos_in_field_names():
    p = G.Player()
    with pytest.raises(AttributeError):
        p.confsued = 5                       # опечатка вместо confused


def test_timers_tick_down_but_never_below_zero(safe_game):
    g = safe_game
    g.p.confused = 2
    for _ in range(5):
        g.end_turn()
    assert g.p.confused == 0


def test_str_bonuses_never_decrease_with_strength():
    prev = G.str_bonuses(1)
    for s in range(2, 40):
        cur = G.str_bonuses(s)
        assert cur[0] >= prev[0] and cur[1] >= prev[1]
        prev = cur


def test_gender_agreement():
    assert G.agree("змея", "повержен", "повержена", "повержено") == "повержена"
    assert G.agree("орк", "повержен", "повержена", "повержено") == "повержен"
    assert G.agree("ледяное чудо", "повержен", "повержена", "повержено") == "повержено"


# --------------------------------------------------------- инвентарь ------
def test_stackables_stack_and_singles_do_not(safe_game):
    g = safe_game
    g.p.inventory = []
    g.pick_up(G.Item("weapon", "стрела", count=5))
    g.pick_up(G.Item("weapon", "стрела", count=7))
    assert len(g.p.inventory) == 1 and g.p.inventory[0].count == 12
    g.pick_up(G.Item("weapon", "стрела", count=1, enchant=1))
    assert len(g.p.inventory) == 2, "разное зачарование не складывается в стопку"
    g.pick_up(G.Item("armor", "латы"))
    g.pick_up(G.Item("armor", "латы"))
    assert len(g.p.inventory) == 4, "броня в стопки не складывается"


def test_backpack_limit_leaves_the_item_on_the_floor(safe_game):
    g = safe_game
    g.p.inventory = [G.Item("wand", G.WANDS[i % len(G.WANDS)], charges=1) for i in range(22)]
    g.cur.items = []
    g.pick_up(G.Item("armor", "латы"))
    assert len(g.p.inventory) == 22
    assert [(x, y) for x, y, _ in g.cur.items] == [(g.p.x, g.p.y)]


def test_item_names_render_for_every_subtype(safe_game):
    g = safe_game
    for kind, subs in (("potion", G.POTIONS), ("scroll", G.SCROLLS),
                       ("ring", G.RINGS), ("wand", G.WANDS)):
        for sub in subs:
            it = G.Item(kind, sub, charges=3)
            unknown = g.item_name(it)
            g.identify(it)
            known = g.item_name(it)
            assert unknown and known and unknown != known
            assert G.SUB_RU[sub] in known


def test_dropping_equipped_gear_is_refused(safe_game):
    g = safe_game
    weapon = g.p.weapon
    g.command('drop')                       # откроется список
    g.choose_item(weapon)
    assert weapon in g.p.inventory and g.p.weapon is weapon


# ------------------------------------------------- регрессии на баги ------
def test_asleep_player_cannot_act_but_loses_the_turn(safe_game):
    """Сон обездвиживал только ноги: спящий персонаж всё ещё пил зелья,
    читал свитки и уходил по лестнице."""
    g = safe_game
    potion = G.Item("potion", "healing")
    g.p.inventory.append(potion)
    g.p.frozen = 3
    before = g.turn
    g.command('quaff')
    assert g.mode == 'play', "окно выбора не должно открываться во сне"
    assert potion in g.p.inventory
    assert g.turn == before + 1, "ход всё равно должен пройти"


def test_asleep_player_cannot_take_the_stairs(safe_game):
    g = safe_game
    g.p.x, g.p.y = g.cur.stairs_down
    g.p.frozen = 5
    g.command('descend')
    assert g.depth == 1


def test_trapdoor_does_not_fire_traps_of_the_level_we_left(safe_game):
    """Список ловушек покинутого уровня после падения сверялся с новой
    позицией игрока на новом уровне — и ловушка срабатывала «через уровень»."""
    g = safe_game
    g.enter_level(2, "up")
    arrival = g.cur.stairs_up
    g.enter_level(1, "down")
    g.p.x, g.p.y = 5, 5
    g.cur.grid[5][5] = G.FLOOR
    g.cur.grid[arrival[1]][arrival[0]] = G.FLOOR
    decoy = {'x': arrival[0], 'y': arrival[1], 'type': 'dart', 'found': False}
    g.cur.traps = [{'x': 5, 'y': 5, 'type': 'trapdoor', 'found': False}, decoy]
    g.on_enter_tile()
    assert g.depth == 2, "люк должен был утащить вниз"
    assert decoy['found'] is False, "ловушка первого уровня сработала на втором"


def test_monster_attacks_diagonally(safe_game):
    """Соседство считалось по манхэттену: монстр по диагонали не доставал,
    хотя игрок по диагонали бил свободно."""
    g = safe_game
    template = next(t for t in G.MONSTERS if t.name == "гоблин")
    spot = (g.p.x + 1, g.p.y + 1)
    g.cur.grid[spot[1]][spot[0]] = G.FLOOR
    m = G.Monster(template, spot[0], spot[1])
    m.awake = True
    g.cur.monsters = [m]
    attacked = []
    g.monster_attack_player = lambda mon: attacked.append(mon)
    g.move_monsters()
    assert attacked == [m]
    assert (m.x, m.y) == spot, "атакующий монстр не должен уходить с места"


def test_death_cause_is_not_overwritten(safe_game):
    g = safe_game
    g.p.hp = 1
    g.damage_player(50, "дракон")
    assert g.state == 'dead' and g.death_cause == "дракон"
    g.p.food = 0
    g.hunger_tick()
    assert g.death_cause == "дракон"
    assert g.p.hp == 0, "мёртвый персонаж не должен получать урон дальше"


def test_turns_stop_after_death(safe_game):
    g = safe_game
    g.p.hp = 1
    g.damage_player(50, "дракон")
    before = (g.turn, g.p.hp)
    for _ in range(10):
        g.end_turn()
    assert (g.turn, g.p.hp) == before, "регенерация воскрешала труп"


def test_relocation_never_lands_on_the_player(safe_game):
    """Вор сбегал через free_tile() и мог оказаться прямо на игроке."""
    g = safe_game
    template = next(t for t in G.MONSTERS if t.name == "лепрекон")
    m = G.Monster(template, g.p.x, g.p.y)
    g.cur.monsters = [m]
    for _ in range(300):
        g.flee_away(m)
        assert (m.x, m.y) != (g.p.x, g.p.y)
        assert g.cur.grid[m.y][m.x] == G.FLOOR


def test_confused_step_always_costs_a_turn(safe_game):
    """Спутанный персонаж, шагнувший в стену, раньше ходил бесплатно."""
    g = safe_game
    g.p.confused = 10 ** 6
    before = g.turn
    for _ in range(60):
        g.command('move', (1, 0))
    assert g.turn == before + 60


def test_deliberate_step_into_a_wall_is_free(safe_game):
    g = safe_game
    for y in range(1, G.MAP_ROWS - 1):
        for x in range(1, G.MAP_COLS - 1):
            if g.cur.grid[y][x] != G.FLOOR:
                continue
            for dx, dy in G.DIRS8:
                if g.cur.grid[y + dy][x + dx] != G.WALL:
                    continue
                g.p.x, g.p.y = x, y
                before = g.turn
                g.command('move', (dx, dy))
                assert g.turn == before, "шаг в стену не должен стоить хода"
                assert (g.p.x, g.p.y) == (x, y)
                return
    pytest.fail("на уровне не нашлось пола рядом со стеной")


def test_cancelling_a_prompt_clears_the_pending_action(safe_game):
    g = safe_game
    g.p.inventory.append(G.Item("potion", "poison"))
    g.command('quaff')
    assert g.mode == 'select'
    g.command('cancel')
    assert g.mode == 'play' and g.pending_action is None and g.overlay is None


def test_wand_beam_does_not_teleport_a_monster_onto_the_player(safe_game):
    g = safe_game
    template = next(t for t in G.MONSTERS if t.name == "змея")
    for _ in range(120):
        m = G.Monster(template, g.p.x + 1, g.p.y)
        g.cur.grid[g.p.y][g.p.x + 1] = G.FLOOR
        g.cur.monsters = [m]
        g.zap(G.Item("wand", "teleport_away", charges=5), (1, 0))
        if g.cur.monsters:
            assert (m.x, m.y) != (g.p.x, g.p.y)


# ------------------------------------------------------------- бой --------
def test_kill_drops_stolen_goods_and_grants_xp(safe_game):
    g = safe_game
    template = next(t for t in G.MONSTERS if t.name == "нимфа")
    m = G.Monster(template, g.p.x + 2, g.p.y)
    m.stolen = G.Item("potion", "healing")
    m.gold = 40
    g.cur.monsters = [m]
    g.cur.items, g.cur.gold = [], []
    xp_before = g.p.xp
    g.kill_monster(m)
    assert g.p.xp == xp_before + template.xp
    assert [it.subtype for _, _, it in g.cur.items] == ["healing"]
    assert [amount for _, _, amount in g.cur.gold] == [40]
    assert m not in g.cur.monsters


def test_experience_levels_follow_the_table(safe_game):
    g = safe_game
    g.gain_xp(G.XP_THRESHOLDS[4])
    assert g.p.xp_level == 5
    assert g.p.hp <= g.p.max_hp


def test_armor_class_counts_enchantment_and_rings(safe_game):
    g = safe_game
    g.p.armor = G.Item("armor", "латы", enchant=2)
    g.p.rings = [G.Item("ring", "protection", enchant=1)]
    assert g.player_ac() == G.ARMOR["латы"] - 2 - 1


def test_cursed_gear_sticks(safe_game):
    g = safe_game
    g.p.armor = G.Item("armor", "латы", cursed=True)
    g.take_off_armor()
    assert g.p.armor is not None
    g.p.weapon = G.Item("weapon", "кинжал", cursed=True)
    other = G.Item("weapon", "булава")
    g.p.inventory.append(other)
    g.wield(other)
    assert g.p.weapon is not other


def test_hunger_drains_and_food_restores(safe_game):
    g = safe_game
    g.p.food = 100.0
    g.hunger_tick()
    assert g.p.food < 100.0
    ration = G.Item("food", "паёк")
    g.p.inventory.append(ration)
    g.eat(ration)
    assert g.p.food > 100.0
    assert g.p.food <= 2000.0
    assert ration not in g.p.inventory


def test_hunger_labels_cover_the_whole_range(safe_game):
    g = safe_game
    seen = set()
    for food in (2000, 300, 150, 50, 0, -10):
        g.p.food = food
        seen.add(g.hunger_label())
    assert len(seen) == 5


def test_magic_mapping_reveals_the_level(safe_game):
    g = safe_game
    g.read(G.Item("scroll", "magic_mapping"))
    assert all(all(row) for row in g.cur.explored)


def test_amulet_is_required_to_win(safe_game):
    g = safe_game
    g.p.x, g.p.y = g.cur.stairs_up
    g.command('ascend')
    assert g.state == 'play'
    g.p.has_amulet = True
    g.command('ascend')
    assert g.state == 'won'
