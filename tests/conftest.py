# -*- coding: utf-8 -*-
"""Общая обвязка тестов: pygame без окна и звука, чистая игра на каждый тест."""

import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest  # noqa: E402

import PixRogue as G  # noqa: E402

TEST_SIZE = (540, 1200)


@pytest.fixture
def game():
    """Новая партия с фиксированным зерном — тесты воспроизводимы."""
    random.seed(20240913)
    return G.RogueGame(size=TEST_SIZE)


@pytest.fixture
def safe_game(game):
    """Партия без монстров и с запасом HP: изолирует проверяемое правило."""
    game.cur.monsters = []
    game.p.max_hp = game.p.hp = 9999
    game.p.food = 2000.0
    return game
