# -*- coding: utf-8 -*-
"""Запуск игры: что бы ни лежало в командной строке, окно должно открыться.

Pydroid 3 кладёт в sys.argv всю команду целиком — ['python3', '/.../PixRogue.py'] —
и раньше argparse убивал игру с «unrecognized arguments» до первого кадра.
"""

import pytest

import PixRogue as G

# как выглядит sys.argv[1:] у разных лаунчеров и при ошибках игрока
LAUNCHES = [
    [],
    ["python3", "/storage/emulated/0/CODE/PYTHON/PixRogue-main/PixRogue.py"],
    ["/usr/bin/python3.12", "PixRogue.py"],
    ["python", "C:\\\\Games\\\\PixRogue\\\\PixRogue.py"],
    ["PixRogue.py"],
    ["--seed", "777"],
    ["--seed", "777", "--size", "720x1600"],
    ["python3", "/sdcard/PixRogue.py", "--seed", "42"],
    ["--seed", "не-число"],
    ["--size", "мусор"],
    ["--size", "10x10"],
    ["--такого-нет"],
    ["--такого-нет", "--size", "540x1200"],
    ["-", "--", "???"],
]


@pytest.mark.parametrize("argv", LAUNCHES)
def test_any_command_line_still_starts_the_game(argv, monkeypatch):
    started = {}

    class FakeGame(object):
        def __init__(self, size=None):
            started['size'] = size

        def run(self):
            started['ran'] = True

    monkeypatch.setattr(G, "RogueGame", FakeGame)
    G.main(argv)
    assert started.get('ran') is True, "игра не дошла до главного цикла"
    assert started['size'] is None or (
        started['size'][0] >= G.MIN_WINDOW[0] and started['size'][1] >= G.MIN_WINDOW[1])


def test_launcher_noise_is_not_taken_for_arguments():
    args = G.parse_args(["python3", "/storage/emulated/0/CODE/PYTHON/PixRogue-main/PixRogue.py"])
    assert args.seed is None and args.size is None


def test_real_arguments_survive_launcher_noise():
    args = G.parse_args(["python3", "/sdcard/PixRogue.py", "--seed", "42",
                         "--size", "720x1600"])
    assert args.seed == 42 and args.size == "720x1600"


def test_unknown_arguments_are_skipped_not_fatal():
    args = G.parse_args(["--такого-нет", "--size", "540x1200"])
    assert args.size == "540x1200"


def test_broken_value_falls_back_to_defaults():
    args = G.parse_args(["--seed", "не-число"])
    assert args.seed is None and args.size is None


def test_help_still_exits_normally():
    with pytest.raises(SystemExit) as exc:
        G.parse_args(["--help"])
    assert exc.value.code in (0, None)


def test_window_size_is_parsed():
    assert G.parse_size("1080x2400") == (1080, 2400)
    assert G.parse_size("720X1600") == (720, 1600)
    assert G.parse_size("540*1200") == (540, 1200)
    assert G.parse_size(None) is None
    for bad in ("что-то не то", "10x10", "0x0", "abcxdef"):
        with pytest.raises(ValueError):
            G.parse_size(bad)


def test_seed_reaches_the_game(monkeypatch):
    import random

    class FakeGame(object):
        def __init__(self, size=None):
            pass

        def run(self):
            pass

    monkeypatch.setattr(G, "RogueGame", FakeGame)
    G.main(["--seed", "12345"])
    first = [random.random() for _ in range(5)]
    G.main(["--seed", "12345"])
    assert [random.random() for _ in range(5)] == first
