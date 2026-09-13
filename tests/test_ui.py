# -*- coding: utf-8 -*-
"""Раскладка экрана, клавиатура и отрисовка: зоны не должны пересекаться,
а ни один режим — падать при рисовании."""

import random

import pygame
import pytest

import PixRogue as G

SIZES = [(1080, 2400), (1080, 2260), (1080, 2160), (720, 1600),
         (1440, 3200), (540, 1200), (480, 960), (400, 800), (360, 640),
         (320, 480), (1200, 900)]

# 'quit' завершает процесс — в тестах не вызываем
SAFE_COMMANDS = ['move', 'descend', 'ascend', 'search', 'inventory', 'help',
                 'cancel', 'quaff', 'read', 'zap', 'eat', 'throw', 'drop',
                 'wield', 'wear', 'takeoff', 'putring', 'remring', 'restart']


@pytest.mark.parametrize("size", SIZES)
def test_zones_never_overlap(size):
    L = G.Layout(*size)
    w, h = size
    assert 0 < L.msg_h < L.status_y
    assert L.msg_h <= L.map_y, "карта заезжает на строку сообщений"
    assert L.map_y + L.map_h <= L.status_y, "карта заезжает на панель статуса"
    assert L.status_y + L.status_h == L.kb_y, "между статусом и клавиатурой дыра"
    assert L.kb_y + L.kb_h <= h, "клавиатура не влезла в экран"
    assert 0 <= L.map_x and L.map_x + L.map_w <= w
    assert L.tile >= 2


@pytest.mark.parametrize("size", SIZES)
def test_buttons_fit_the_keyboard_and_do_not_overlap(size):
    random.seed(1)
    game = G.RogueGame(size=size)
    kb = pygame.Rect(0, game.L.kb_y, game.L.w, game.L.kb_h)
    assert len(game.buttons) == 28
    for i, b in enumerate(game.buttons):
        assert kb.contains(b['rect']), "кнопка %s вне зоны клавиатуры" % b['label']
        assert b['rect'].w > 0 and b['rect'].h > 0
        for other in game.buttons[i + 1:]:
            assert not b['rect'].colliderect(other['rect']), \
                "кнопки %s и %s накладываются" % (b['label'], other['label'])


@pytest.mark.parametrize("size", SIZES)
def test_button_labels_fit_inside_their_buttons(size):
    random.seed(2)
    game = G.RogueGame(size=size)
    for b in game.buttons:
        surf = b['surf']
        assert surf.get_width() <= b['rect'].w, "подпись %s шире кнопки" % b['label']
        assert surf.get_height() <= b['rect'].h, "подпись %s выше кнопки" % b['label']


def test_every_button_command_is_dispatched(game):
    """Кнопка с опечаткой в имени команды молча ничего не делает —
    проверяем, что все команды клавиатуры реально обрабатываются."""
    handled = set(SAFE_COMMANDS) | {'quit'}
    for b in game.buttons:
        assert b['cmd'] in handled, "кнопка %s шлёт неизвестную команду %s" % (
            b['label'], b['cmd'])
    for key, (cmd, _) in G.RogueGame.KEY_CMD.items():
        assert cmd in handled, "клавиша %s шлёт неизвестную команду %s" % (key, cmd)


@pytest.mark.parametrize("cmd", SAFE_COMMANDS)
def test_commands_do_not_crash_and_still_render(cmd):
    random.seed(31337)
    game = G.RogueGame(size=(540, 1200))
    game.p.inventory.append(G.Item("wand", "fire", charges=3))
    game.p.inventory.append(G.Item("potion", "healing"))
    game.p.inventory.append(G.Item("scroll", "identify"))
    game.p.inventory.append(G.Item("ring", "protection"))
    arg = (1, 0) if cmd == 'move' else None
    game.command(cmd, arg)
    game.render()
    if game.mode == 'select':
        rows = [r for r in game.overlay['rows'] if r['item'] is not None]
        assert rows, "пустой список выбора открываться не должен"
        game.choose_item(rows[0]['item'])
        game.render()
    assert game.mode in ('play', 'select', 'direction', 'list', 'help')


def test_direction_prompt_center_cancels_without_spending_a_charge(game):
    wand = G.Item("wand", "fire", charges=3)
    game.p.inventory.append(wand)
    game.command('zap')
    game.choose_item(wand)
    assert game.mode == 'direction'
    game.command('move', (0, 0))
    assert game.mode == 'play' and wand.charges == 3


def test_end_screens_render(game):
    for state in ('dead', 'won'):
        game.state = state
        game.death_cause = "дракон"
        game.render()
    game.command('restart')
    assert game.state == 'play'


def test_disabled_buttons_match_the_mode(game):
    game.mode = 'select'
    assert {b['cmd'] for b in game.buttons if game.button_enabled(b)} == {'cancel'}
    game.mode = 'direction'
    assert {b['cmd'] for b in game.buttons if game.button_enabled(b)} == {'move', 'cancel'}
    game.mode = 'play'
    game.state = 'dead'
    assert {b['cmd'] for b in game.buttons if game.button_enabled(b)} == {
        'restart', 'quit', 'help'}


def test_full_inventory_overlay_renders(game):
    game.p.inventory = [G.Item("potion", G.POTIONS[i % len(G.POTIONS)])
                        for i in range(22)]
    game.show_inventory()
    game.render()
    assert game.overlay['rect'].bottom <= game.L.status_y


def test_word_wrap_keeps_lines_inside_the_width(game):
    font = game.F(20)
    text = " ".join("слово%d" % i for i in range(40))
    for width in (120, 300, 900):
        for line in game.wrap(text, font, width):
            assert font.size(line)[0] <= width or " " not in line


def test_hallucination_recolors_but_stays_a_valid_color(game):
    game.p.hallu = 5
    for base in (G.C['gold'], G.C['potion']):
        col = game.hallu_color(base)
        assert len(col) == 3 and all(0 <= c <= 255 for c in col)
    game.p.hallu = 0
    assert game.hallu_color(G.C['gold']) == G.C['gold']



def test_main_loop_handles_a_queued_burst_of_events():
    """Главный цикл: клавиша, тап по кнопке движения и выход — всё за один
    проход, потому что события уже лежат в очереди."""
    random.seed(9)
    game = G.RogueGame(size=(540, 1200))
    move_button = next(b for b in game.buttons if b['cmd'] == 'move' and b['arg'] != (0, 0))
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_i, unicode='i'))
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, unicode=''))
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                         pos=move_button['rect'].center))
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1,
                                         pos=move_button['rect'].center))
    pygame.event.post(pygame.event.Event(pygame.QUIT))
    game.quit = lambda: (_ for _ in ()).throw(SystemExit(0))
    with pytest.raises(SystemExit):
        game.run()
    assert game.turn >= 1, "тап по крестовине должен был потратить ход"


def test_idle_main_loop_sleeps_until_an_event_arrives():
    """В простое цикл обязан блокироваться на ожидании события, а не крутить
    30 холостых кадров в секунду — от этого напрямую зависит расход батареи."""
    import time

    random.seed(11)
    game = G.RogueGame(size=(540, 1200))
    game.quit = lambda: (_ for _ in ()).throw(SystemExit(0))
    pygame.event.clear()
    pygame.time.set_timer(pygame.QUIT, 300, loops=1)
    started = time.time()
    frames = [0]
    real_render = game.render

    def counting_render():
        frames[0] += 1
        real_render()

    game.render = counting_render
    try:
        with pytest.raises(SystemExit):
            game.run()
    finally:
        pygame.time.set_timer(pygame.QUIT, 0)
    assert time.time() - started >= 0.2, "цикл не дождался события"
    assert frames[0] <= 3, "в простое нарисовано %d кадров" % frames[0]
