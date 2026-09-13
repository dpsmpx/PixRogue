# -*- coding: utf-8 -*-
"""Сквозные прогоны: спуск до Амулета и обратно + случайные партии."""

import random

import PixRogue as G
from tools.fuzz import check, play_one


def test_full_descent_and_victory(game):
    """Проходим всю арку: 26 уровней вниз, Амулет, подъём и победа."""
    game.cur.monsters = []
    game.p.max_hp = game.p.hp = 10 ** 6

    for depth in range(1, G.MAX_DEPTH):
        assert game.depth == depth
        game.p.x, game.p.y = game.cur.stairs_down
        game.cur.monsters = []
        game.command('descend')
        check(game)

    assert game.depth == G.MAX_DEPTH
    amulet_at = next((x, y) for x, y, it in game.cur.items if it.kind == "amulet")
    game.p.x, game.p.y = amulet_at
    game.on_enter_tile()
    assert game.p.has_amulet
    assert any(it.kind == "amulet" for it in game.p.inventory)

    for depth in range(G.MAX_DEPTH, 1, -1):
        assert game.depth == depth
        game.p.x, game.p.y = game.cur.stairs_up
        game.cur.monsters = []
        game.command('ascend')
        check(game)

    assert game.depth == 1
    game.p.x, game.p.y = game.cur.stairs_up
    game.command('ascend')
    assert game.state == 'won'
    game.render()


def test_levels_are_remembered_between_visits(game):
    """Уровни не перегенерируются: спрятанный запас должен пережить возврат."""
    game.p.x, game.p.y = game.cur.stairs_down
    stash = G.Item("food", "паёк")
    game.cur.items.append([game.p.x, game.p.y, stash])
    grid_before = [row[:] for row in game.cur.grid]
    game.command('descend')
    game.p.x, game.p.y = game.cur.stairs_up
    game.command('ascend')
    assert game.depth == 1
    assert [row[:] for row in game.cur.grid] == grid_before
    assert any(it is stash for _, _, it in game.cur.items)


def test_random_games_keep_the_world_consistent():
    """Короткий фуззинг: ловит падения и нарушения инвариантов после правок."""
    for seed in range(6):
        game = play_one(seed * 977 + 13, turns=400)
        check(game)
        assert game.state in ('play', 'dead', 'won')


def test_restart_starts_a_clean_game(game):
    game.p.gold = 500
    game.p.has_amulet = True
    game.depth = 9
    game.command('restart')
    assert game.p.gold == 0 and game.depth == 1 and not game.p.has_amulet
    assert game.p.hp == game.p.max_hp == 12
    assert game.state == 'play' and game.mode == 'play'
    check(game)
