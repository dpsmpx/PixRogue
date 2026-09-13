# -*- coding: utf-8 -*-
"""Генерация подземелья: связность, лестницы, население."""

import random

import PixRogue as G
from tools.fuzz import bfs_distances

ALL_DEPTHS = list(range(1, G.MAX_DEPTH + 1))


def floor_tiles(lv):
    return {(x, y)
            for y in range(G.MAP_ROWS)
            for x in range(G.MAP_COLS)
            if lv.grid[y][x] == G.FLOOR}


def test_every_floor_tile_is_reachable(game):
    """Остовное дерево по сетке комнат обязано давать связный уровень:
    иначе лестница вниз может оказаться в отрезанном куске карты."""
    for depth in ALL_DEPTHS:
        random.seed(depth * 7919)
        lv = game.build_level(depth)
        reached = set(bfs_distances(lv, lv.stairs_up))
        assert reached == floor_tiles(lv), "уровень %d: недостижимых клеток %d" % (
            depth, len(floor_tiles(lv) - reached))


def test_stairs_present_and_apart(game):
    for depth in ALL_DEPTHS:
        random.seed(depth * 104729)
        lv = game.build_level(depth)
        assert lv.stairs_up is not None
        if depth < G.MAX_DEPTH:
            assert lv.stairs_down is not None
            assert lv.stairs_down != lv.stairs_up
        else:
            assert lv.stairs_down is None, "с 26 уровня спуска быть не должно"


def test_amulet_only_on_the_last_level(game):
    for depth in (1, 12, 25, G.MAX_DEPTH):
        random.seed(depth * 31337)
        lv = game.build_level(depth)
        amulets = [it for _, _, it in lv.items if it.kind == "amulet"]
        assert len(amulets) == (1 if depth == G.MAX_DEPTH else 0)


def test_level_contents_stand_on_floor(game):
    for depth in ALL_DEPTHS:
        random.seed(depth * 65537)
        lv = game.build_level(depth)
        for m in lv.monsters:
            assert lv.grid[m.y][m.x] == G.FLOOR
        for x, y, _ in lv.items:
            assert lv.grid[y][x] == G.FLOOR
        for x, y, amount in lv.gold:
            assert lv.grid[y][x] == G.FLOOR and amount > 0
        for t in lv.traps:
            assert lv.grid[t['y']][t['x']] == G.FLOOR
            assert t['type'] in G.TRAP_NAMES


def test_monsters_respect_their_depth_range(game):
    for depth in ALL_DEPTHS:
        random.seed(depth * 15485863)
        lv = game.build_level(depth)
        by_name = {t.name: t for t in G.MONSTERS}
        for m in lv.monsters:
            t = by_name[m.name]
            assert t.dmin <= depth <= t.dmax


def test_rooms_do_not_overlap(game):
    """Комнаты раскладываются по ячейкам сетки — пересечений быть не может."""
    for depth in ALL_DEPTHS:
        random.seed(depth * 2654435761)
        lv = game.build_level(depth)
        seen = set()
        for r in lv.rooms:
            assert 0 < r.x and r.x + r.w <= G.MAP_COLS - 1
            assert 0 < r.y and r.y + r.h <= G.MAP_ROWS - 1
            cells = {(x, y) for y in range(r.y, r.y + r.h)
                     for x in range(r.x, r.x + r.w)}
            assert not (cells & seen)
            seen |= cells


def test_same_seed_builds_the_same_dungeon():
    """--seed обязан воспроизводить партию целиком, иначе отчёты об ошибках
    невозможно повторить."""
    def signature():
        random.seed(4242)
        g = G.RogueGame(size=(540, 1200))
        return (
            [row[:] for row in g.cur.grid],
            sorted((m.name, m.x, m.y, m.hp) for m in g.cur.monsters),
            sorted((it.kind, it.subtype, x, y) for x, y, it in g.cur.items),
            g.cur.stairs_up, g.cur.stairs_down,
            dict(g.look['potion']),
        )
    assert signature() == signature()
