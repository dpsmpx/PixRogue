# -*- coding: utf-8 -*-
"""Случайный прогон партий без экрана — быстрый поиск падений и нарушений правил.

Играет за «обезьянку»: выбирает допустимые команды случайно, после каждого хода
проверяет инварианты мира. Любая пойманная проблема печатается вместе с зерном,
поэтому её можно воспроизвести точь-в-точь: ``python PixRogue.py --seed <зерно>``.

    python tools/fuzz.py                 # 40 партий по 600 ходов
    python tools/fuzz.py --games 200 --turns 2000
    python tools/fuzz.py --seed 12345 --games 1 -v

Зависит только от pygame (драйвер видео — dummy, окно не открывается).
"""

from __future__ import print_function

import argparse
import collections
import os
import random
import sys
import traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import PixRogue as G  # noqa: E402  (после настройки SDL)


# команды обычного режима; 'quit' и 'restart' исключены намеренно
PLAY_COMMANDS = [
    ('move', None), ('move', None), ('move', None), ('move', None),
    ('search', None), ('descend', None), ('ascend', None),
    ('quaff', None), ('read', None), ('zap', None), ('eat', None),
    ('throw', None), ('drop', None), ('wield', None), ('wear', None),
    ('takeoff', None), ('putring', None), ('remring', None),
    ('inventory', None), ('help', None), ('cancel', None),
]


class InvariantError(AssertionError):
    pass


def check(game):
    """Инварианты мира. Нарушение любого — баг в правилах, а не «так задумано»."""
    p, lv = game.p, game.cur

    def bad(msg):
        raise InvariantError(msg)

    if not (0 <= p.x < G.MAP_COLS and 0 <= p.y < G.MAP_ROWS):
        bad("игрок вне карты: %d,%d" % (p.x, p.y))
    if lv.grid[p.y][p.x] != G.FLOOR:
        bad("игрок в стене: %d,%d" % (p.x, p.y))
    if p.hp > p.max_hp:
        bad("HP %d > max %d" % (p.hp, p.max_hp))
    if p.max_hp < 1:
        bad("max_hp = %d" % p.max_hp)
    if game.state == 'play' and p.hp <= 0:
        bad("HP %d, но игра всё ещё идёт" % p.hp)
    if len(p.rings) > 2:
        bad("колец на руках: %d" % len(p.rings))
    if len(p.inventory) > 22:
        bad("в рюкзаке %d предметов (буквы кончаются на 22)" % len(p.inventory))

    for it in p.rings:
        if it not in p.inventory:
            bad("надетое кольцо не лежит в рюкзаке: %s" % it.subtype)
    for it, what in ((p.weapon, "оружие"), (p.armor, "броня")):
        if it is not None and it not in p.inventory:
            bad("%s не лежит в рюкзаке: %s" % (what, it.subtype))

    seen = {}
    for m in lv.monsters:
        if not (0 <= m.x < G.MAP_COLS and 0 <= m.y < G.MAP_ROWS):
            bad("монстр вне карты: %s %d,%d" % (m.name, m.x, m.y))
        if lv.grid[m.y][m.x] != G.FLOOR:
            bad("монстр в стене: %s %d,%d" % (m.name, m.x, m.y))
        if m.hp <= 0:
            bad("труп остался на карте: %s" % m.name)
        if (m.x, m.y) in seen:
            bad("два монстра в одной клетке: %s и %s" % (seen[(m.x, m.y)], m.name))
        seen[(m.x, m.y)] = m.name
        if game.state == 'play' and (m.x, m.y) == (p.x, p.y):
            bad("монстр стоит на игроке: %s" % m.name)

    for x, y, it in lv.items:
        if lv.grid[y][x] != G.FLOOR:
            bad("предмет в стене: %s %d,%d" % (it.subtype, x, y))
    for x, y, amount in lv.gold:
        if lv.grid[y][x] != G.FLOOR:
            bad("золото в стене: %d,%d" % (x, y))
        if amount <= 0:
            bad("кучка золота в %d монет" % amount)

    for it in p.inventory:
        game.item_name(it)               # именование не должно падать


def bfs_distances(level, start):
    """Расстояния в шагах (8 направлений) от клетки до всех достижимых полов.

    Используется и «водителем» обезьянки, и тестами связности уровня.
    """
    dist = {start: 0}
    queue = collections.deque([start])
    grid = level.grid
    while queue:
        x, y = queue.popleft()
        d = dist[(x, y)] + 1
        for dx, dy in G.DIRS8:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < G.MAP_COLS and 0 <= ny < G.MAP_ROWS):
                continue
            if grid[ny][nx] != G.FLOOR or (nx, ny) in dist:
                continue
            dist[(nx, ny)] = d
            queue.append((nx, ny))
    return dist


def toward_stairs(game, rnd, bias):
    """Шаг по кратчайшему пути к лестнице вниз.

    Без поиска пути «обезьянка» упирается в первую же стену и всю партию
    топчется на первом уровне — глубокая часть подземелья не проверяется.
    """
    target = game.cur.stairs_down or game.cur.stairs_up
    if not target or rnd.random() > bias:
        return rnd.choice(G.DIRS8 + ((0, 0),))
    dist = bfs_distances(game.cur, target)
    here = dist.get((game.p.x, game.p.y))
    if here is None:
        return rnd.choice(G.DIRS8)
    best, best_d = (0, 0), here
    for dx, dy in G.DIRS8:
        step_d = dist.get((game.p.x + dx, game.p.y + dy))
        if step_d is not None and step_d < best_d:
            best, best_d = (dx, dy), step_d
    return best


def step(game, rnd, bias=0.0):
    """Один шаг «обезьянки» с учётом текущего режима интерфейса."""
    if game.mode == 'select':
        rows = [r for r in game.overlay['rows'] if r['item'] is not None]
        if rows and rnd.random() < 0.85:
            game.choose_item(rnd.choice(rows)['item'])
        else:
            game.command('cancel')
        return
    if game.mode == 'direction':
        game.command('move', rnd.choice(G.DIRS8 + ((0, 0),)))
        return
    if game.mode in ('list', 'help'):
        game.command('cancel')
        return
    if bias and (game.p.x, game.p.y) == game.cur.stairs_down:
        game.command('descend')
        return
    cmd, arg = rnd.choice(PLAY_COMMANDS)
    if cmd == 'move':
        arg = toward_stairs(game, rnd, bias)
    game.command(cmd, arg)


def play_one(seed, turns, verbose=False, render_every=0, bias=0.7, tough=False):
    random.seed(seed)
    rnd = random.Random(seed ^ 0x5F5F)
    game = G.RogueGame(size=(540, 1200))
    check(game)
    for i in range(turns):
        if game.state != 'play':
            break
        if tough:
            # «обезьянка» играет плохо и гибнет на 3-5 уровне, поэтому глубокая
            # половина подземелья без подпитки не проверяется вовсе
            game.p.hp = game.p.max_hp
            game.p.food = 2000.0
        step(game, rnd, bias)
        check(game)
        if render_every and i % render_every == 0:
            game.render()
        if verbose and i % 100 == 0:
            print("  ход %5d  глубина %2d  HP %3d/%-3d  ходов %d"
                  % (i, game.depth, game.p.hp, game.p.max_hp, game.turn))
    game.render()                        # отрисовка финального кадра тоже код
    return game


def main(argv=None):
    ap = argparse.ArgumentParser(description="Случайные прогоны PixRogue без экрана.")
    ap.add_argument("--games", type=int, default=40, help="сколько партий (по умолчанию 40)")
    ap.add_argument("--turns", type=int, default=600, help="лимит команд на партию")
    ap.add_argument("--seed", type=int, default=None, help="зерно первой партии")
    ap.add_argument("--render-every", type=int, default=0,
                    help="отрисовывать кадр раз в N команд (медленно, но проверяет UI)")
    ap.add_argument("--bias", type=float, default=0.7, metavar="0..1",
                    help="доля шагов в сторону лестницы вниз; 0 — чистый хаос")
    ap.add_argument("--tough", action="store_true",
                    help="подлечивать и кормить героя, чтобы дойти до глубоких уровней")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    base = args.seed if args.seed is not None else random.randrange(1 << 30)
    failures = 0
    stats = {'won': 0, 'dead': 0, 'play': 0}
    deepest = 0
    for i in range(args.games):
        seed = base + i
        if args.verbose:
            print("партия %d/%d, зерно %d" % (i + 1, args.games, seed))
        try:
            game = play_one(seed, args.turns, args.verbose, args.render_every,
                            args.bias, args.tough)
        except Exception:
            failures += 1
            print("\n!!! ПАДЕНИЕ, зерно %d  (повтор: python PixRogue.py --seed %d)"
                  % (seed, seed))
            traceback.print_exc()
            continue
        stats[game.state] = stats.get(game.state, 0) + 1
        deepest = max(deepest, game.depth)

    print("\nпартий: %d, падений: %d" % (args.games, failures))
    print("исходы: погиб %d, победа %d, не закончено %d, максимальная глубина %d"
          % (stats.get('dead', 0), stats.get('won', 0), stats.get('play', 0), deepest))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
