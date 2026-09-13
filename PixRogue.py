# -*- coding: utf-8 -*-
"""
PixelRogue — классический Rogue в "пиксельном" стиле.

Версия для вертикального (портретного) экрана Redmi Note 13 (1080x2400)
с полноценной экранной сенсорной клавиатурой.

Стиль отрисовки сохранён: карта — ТОЛЬКО окрашенные квадраты, без ASCII-глифов.
Текст присутствует лишь в служебных панелях (сообщения / статус / клавиатура),
которые находятся в отдельных зонах и НИКОГДА не перекрывают пиксели карты.

Компоновка экрана сверху вниз:
    [ строка сообщений      ]  2 строки
    [ КАРТА (пиксели)       ]  40 x 50 клеток, по центру
    [ панель статуса        ]  4 строки
    [ СЕНСОРНАЯ КЛАВИАТУРА  ]  28 кнопок, 5 рядов
Все зоны рассчитываются от реального размера поверхности, поэтому раскладка
не ломается ни на телефоне, ни в оконном режиме на ПК.

Управление: экранные кнопки (тач) + физическая клавиатура (ПК) одновременно.
Выбор предмета из инвентаря — тап прямо по строке списка (или буква на ПК).

Механики оригинального Rogue: 26 уровней, Амулет Йендора, голод, опыт,
класс брони, монстры со спец-атаками, зелья/свитки/кольца/жезлы/оружие/броня
со случайными "обличьями" и идентификацией по применению, ловушки, туман войны.
"""

import argparse
import collections
import os
import pygame
import random
import sys

# ============================================================================
#  БАЗОВЫЕ КОНСТАНТЫ
# ============================================================================
IS_ANDROID = hasattr(sys, "getandroidapilevel")

REF_W, REF_H = 1080, 2400          # эталон: Redmi Note 13, портрет

MAP_COLS, MAP_ROWS = 40, 50        # карта вытянута по вертикали
GRID_COLS, GRID_ROWS = 3, 4        # сетка комнат (как в оригинале Rogue)

MAX_DEPTH = 26
FPS = 30
WALL, FLOOR = 1, 0

# восемь направлений шага (порядок — по часовой стрелке с запада)
DIRS8 = ((-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1))

# авто-повтор хода при удержании кнопки движения
HOLD_DELAY = 420                   # мс до начала повтора
HOLD_REPEAT = 150                  # мс между повторами

# ----------------------------------------------------------------- цвета ---
C = {
    'bg':          (8, 8, 12),
    'panel':       (20, 20, 27),
    'panel2':      (28, 28, 37),
    'line':        (52, 52, 66),
    'wall_lit':    (120, 105, 84),
    'wall_dark':   (62, 56, 45),
    'floor_lit':   (64, 64, 76),
    'floor_dark':  (38, 38, 46),
    'door':        (150, 100, 50),
    'text':        (224, 224, 228),
    'text_dim':    (146, 146, 158),
    'good':        (110, 220, 110),
    'bad':         (232, 92, 92),
    'warn':        (238, 202, 82),
    # сущности на карте
    'player':      (92, 168, 255),
    'gold':        (240, 200, 40),
    'food':        (122, 220, 92),
    'potion':      (220, 92, 200),
    'scroll':      (236, 226, 182),
    'ring':        (92, 220, 220),
    'wand':        (240, 150, 60),
    'weapon':      (196, 210, 226),
    'armor':       (180, 130, 80),
    'amulet':      (255, 240, 120),
    'trap':        (232, 60, 60),
    # лестницы — нейтрально-серая "семья", чтобы не путаться с синим игроком:
    # вниз = яркая (цель спуска), вверх = приглушённая
    'stairs_down': (255, 255, 255),
    'stairs_up':   (138, 142, 158),
    # кнопки по группам
    'btn_move':    (48, 62, 86),
    'btn_nav':     (52, 56, 64),
    'btn_use':     (74, 48, 84),
    'btn_gear':    (72, 60, 44),
    'btn_warn':    (86, 62, 34),
    'btn_danger':  (86, 40, 44),
    'btn_edge':    (96, 100, 118),
    'btn_press':   (140, 150, 178),
    'btn_off':     (30, 30, 36),
    'btn_text':    (236, 236, 240),
    'btn_text_off':(96, 96, 104),
}

# ============================================================================
#  ТАБЛИЦЫ ПРЕДМЕТОВ
# ============================================================================
POTIONS = ["healing", "extra_healing", "gain_strength", "restore_strength",
           "poison", "confusion", "blindness", "haste_self", "detect_monsters",
           "magic_detection", "raise_level", "see_invisible", "levitation",
           "hallucination", "sleep"]

SCROLLS = ["identify", "teleportation", "enchant_armor", "enchant_weapon",
           "remove_curse", "create_monster", "aggravate_monsters",
           "magic_mapping", "light", "hold_monster", "sleep", "scare_monster",
           "protect_armor"]

RINGS = ["protection", "add_strength", "dexterity", "increase_damage",
         "regeneration", "slow_digestion", "searching", "see_invisible",
         "stealth", "teleportation", "aggravate_monster", "adornment"]

WANDS = ["striking", "lightning", "fire", "cold", "magic_missile",
         "slow_monster", "haste_monster", "polymorph", "teleport_away",
         "cancellation", "drain_life", "light", "nothing"]

# имя -> характеристики оружия (кубиков, граней, можно ли метать)
WeaponSpec = collections.namedtuple("WeaponSpec", "dice sides throwable")

WEAPONS = {name: WeaponSpec(*spec) for name, spec in {
    "кинжал":            (1, 6, True),
    "дротик":            (1, 3, True),
    "короткий меч":      (2, 3, False),
    "булава":            (2, 4, False),
    "копьё":             (1, 8, True),
    "боевой молот":      (2, 5, False),
    "длинный меч":       (3, 4, False),
    "двуручный меч":     (4, 4, False),
    "короткий лук":      (1, 1, False),
    "стрела":            (1, 6, True),
}.items()}

BOW, ARROW = "короткий лук", "стрела"
THROWABLE_STACK = ("стрела", "дротик")

# имя -> базовый класс брони (чем меньше, тем лучше)
ARMOR = {
    "кожаный доспех":    8,
    "клёпаная кожа":     7,
    "кольчужный доспех": 7,
    "чешуйчатый доспех": 6,
    "кольчуга":          5,
    "ламинарный доспех": 4,
    "пластинчатый":      4,
    "латы":              3,
}

POTION_LOOKS = ["алое", "лазурное", "изумрудное", "янтарное", "пурпурное",
                "оранжевое", "розовое", "белое", "чёрное", "бурое", "мутное",
                "шипучее", "тёмное", "бирюзовое", "серебристое", "золотистое",
                "дымчатое", "молочное", "багровое", "ледяное"]
RING_LOOKS = ["алмазное", "рубиновое", "изумрудное", "сапфировое", "аметистовое",
              "топазовое", "опаловое", "гранатовое", "нефритовое", "жемчужное",
              "ониксовое", "обсидиановое", "коралловое", "агатовое", "янтарное"]
WAND_LOOKS = ["дубовый", "сосновый", "эбеновый", "серебряный", "золотой",
              "бронзовый", "медный", "железный", "стальной", "хрустальный",
              "стеклянный", "костяной", "резной", "нефритовый", "обсидиановый"]

SUB_RU = {
    "healing": "исцеление", "extra_healing": "полное исцеление",
    "gain_strength": "прибавление сил", "restore_strength": "возврат сил",
    "poison": "яд", "confusion": "смятение", "blindness": "слепота",
    "haste_self": "ускорение", "detect_monsters": "чутьё на монстров",
    "magic_detection": "чутьё на магию", "raise_level": "рост уровня",
    "see_invisible": "видеть незримое", "levitation": "левитация",
    "hallucination": "галлюцинации", "sleep": "сон",
    "identify": "опознание", "teleportation": "телепорт",
    "enchant_armor": "зачаровать броню", "enchant_weapon": "зачаровать оружие",
    "remove_curse": "снять проклятие", "create_monster": "создать монстра",
    "aggravate_monsters": "разъярить монстров", "magic_mapping": "карта уровня",
    "light": "свет", "hold_monster": "сковать монстра",
    "scare_monster": "испуг монстров", "protect_armor": "защита брони",
    "protection": "защита", "add_strength": "сила", "dexterity": "ловкость",
    "increase_damage": "урон", "regeneration": "регенерация",
    "slow_digestion": "медленное пищеварение", "searching": "поиск",
    "stealth": "скрытность", "aggravate_monster": "ярость монстров",
    "adornment": "украшение",
    "striking": "удар", "lightning": "молния", "fire": "огонь", "cold": "холод",
    "magic_missile": "магострела", "slow_monster": "замедление",
    "haste_monster": "ускорение монстра", "polymorph": "превращение",
    "teleport_away": "изгнание", "cancellation": "развеивание",
    "drain_life": "высасывание жизни", "nothing": "пустышка",
}


def assign_looks(subtypes, looks):
    """Случайное «обличье» каждому подтипу предмета.

    Списки обличий и списки предметов правятся независимо, поэтому таблица
    обличий может оказаться короче: тогда лишним выдаются нумерованные
    варианты вместо падения с IndexError. Глобальные списки не мутируются.
    """
    pool = list(looks)
    random.shuffle(pool)
    out = {}
    for i, sub in enumerate(subtypes):
        if i < len(pool):
            out[sub] = pool[i]
        else:
            out[sub] = "%s %d" % (pool[i % len(pool)], i // len(pool) + 1)
    return out


def make_scroll_title():
    syl = ["зел", "го", "кас", "фид", "неж", "кло", "пра", "ту", "вун", "аш",
           "бан", "мор", "икс", "вен", "дро", "лум", "сек", "вол", "рхо", "иб"]
    return " ".join("".join(random.choice(syl) for _ in range(random.randint(2, 3)))
                    for _ in range(random.randint(1, 2))).upper()


# ============================================================================
#  МОНСТРЫ
#  (имя, цвет, опыт, кости HP, класс брони, атаки [(n,d)], флаги, мин.гл, макс.гл)
#  Именованный кортеж: порядок полей совпадает с распаковкой в Monster.__init__,
#  но обращаться к «глубине появления» можно как t.dmin, а не как t[7].
# ============================================================================
MonsterType = collections.namedtuple(
    "MonsterType", "name color xp hd ac dmg flags dmin dmax")

MONSTERS = [MonsterType(*t) for t in [
    ("нетопырь",       (170, 120, 210), 1,    1,  3, [(1, 2)], {"fly", "erratic"},          1, 8),
    ("пустельга",      (235, 150, 60),  1,    1,  7, [(1, 4)], {"mean", "fly"},             1, 6),
    ("змея",           (120, 200, 80),  2,    1,  5, [(1, 3)], {"mean"},                    1, 7),
    ("гоблин",         (150, 200, 120), 3,    1,  5, [(1, 8)], {"mean"},                    1, 8),
    ("шакал",          (170, 120, 80),  2,    1,  7, [(1, 2)], {"mean"},                    1, 6),
    ("плавающий глаз", (120, 220, 220), 5,    1,  9, [(0, 0)], {"freeze_on_melee"},         1, 7),
    ("гремучая змея",  (230, 80, 80),   8,    1,  3, [(1, 6)], {"mean", "drain_str"},       2, 9),
    ("ледяное чудо",   (180, 230, 245), 5,    1,  9, [(0, 0)], {"mean", "freeze_player"},   2, 9),
    ("орк",            (200, 90, 70),   5,    1,  6, [(1, 8)], {"mean", "greedy"},          3, 10),
    ("зомби",          (130, 130, 130), 7,    2,  8, [(1, 8)], {"mean", "slow"},            4, 12),
    ("мухоловка",      (90, 180, 90),   80,   8,  3, [(1, 1)], {"hold", "stationary"},      5, 12),
    ("лепрекон",       (240, 200, 40),  10,   3,  8, [(1, 2)], {"steal_gold"},              5, 12),
    ("кентавр",        (230, 220, 90),  15,   4,  4, [(1, 6), (1, 6)], {"mean"},            6, 14),
    ("нимфа",          (230, 110, 220), 37,   3,  9, [(0, 0)], {"steal_item"},              7, 15),
    ("квагга",         (180, 140, 90),  15,   3,  3, [(1, 5), (1, 5)], {"mean"},            7, 14),
    ("акватор",        (90, 150, 230),  20,   5,  2, [(0, 0)], {"mean", "rust_armor"},      8, 16),
    ("йети",           (235, 235, 235), 50,   4,  6, [(1, 6), (1, 6)], {"mean"},            9, 16),
    ("вурдалак",       (110, 110, 130), 55,   5,  4, [(1, 6)], {"mean", "drain_xp"},        11, 18),
    ("тролль",         (90, 200, 110),  120,  6,  4, [(1, 8), (1, 8), (2, 6)], {"mean", "regen"},        10, 19),
    ("призрак",        (200, 200, 215), 120,  8,  3, [(4, 4)], {"mean", "invisible"},       13, 24),
    ("вампир",         (180, 70, 90),   350,  8,  1, [(1, 10)], {"mean", "drain_maxhp", "regen"},        13, 20),
    ("чёрный единорог",(160, 120, 220), 190,  7, -2, [(1, 9), (1, 9), (2, 9)], {"mean"},    16, 26),
    ("грифон",         (235, 160, 60),  2000, 13, 2, [(4, 3), (3, 5), (4, 3)], {"mean", "fly", "regen"}, 13, 26),
    ("медуза",         (110, 210, 110), 200,  8,  2, [(3, 4), (3, 4), (2, 5)], {"mean", "confuse"},      18, 26),
    ("дракон",         (235, 60, 60),   6800, 10, -1, [(1, 8), (1, 8), (3, 10)], {"mean", "breath_fire"},15, 26),
]]

XP_THRESHOLDS = [0, 10, 20, 40, 80, 160, 320, 640, 1300, 2600, 5200, 10000,
                 20000, 40000, 80000, 160000, 320000, 640000, 1300000, 2600000]

TRAP_TYPES = ["trapdoor", "teleport", "dart", "sleep_gas", "bear", "rust"]
TRAP_NAMES = {"trapdoor": "люк", "teleport": "телепорт-ловушка",
              "dart": "дротиковая ловушка", "sleep_gas": "усыпляющий газ",
              "bear": "медвежий капкан", "rust": "ржавая ловушка"}


def is_throwable(weapon_name):
    spec = WEAPONS.get(weapon_name)
    return bool(spec and spec.throwable)


def roll(n, d):
    """Сумма n бросков d-гранного кубика."""
    return sum(random.randint(1, d) for _ in range(n)) if n > 0 else 0


def gender(name):
    """Род существительного по окончанию — для согласования сообщений."""
    last = name.strip()[-1].lower()
    if last in "ая":
        return 'f'
    if last in "ое":
        return 'n'
    return 'm'


def agree(name, m, f, n):
    """Выбрать форму слова под род имени: 'повержен / повержена / повержено'."""
    g = gender(name)
    return f if g == 'f' else (n if g == 'n' else m)


def str_bonuses(s):
    """Бонусы силы: (к попаданию, к урону)."""
    if s <= 5:  return (-3, -2)
    if s <= 7:  return (-1, -1)
    if s <= 15: return (0, 0)
    if s == 16: return (0, 1)
    if s == 17: return (1, 1)
    if s == 18: return (1, 2)
    if s <= 20: return (2, 3)
    if s <= 30: return (3, 5)
    return (4, 6)


# ============================================================================
#  ДАННЫЕ
# ============================================================================
class Item:
    def __init__(self, kind, subtype, enchant=0, charges=0, count=1, cursed=False):
        self.kind = kind
        self.subtype = subtype
        self.enchant = enchant
        self.charges = charges
        self.count = count
        self.cursed = cursed
        self.known = False
        self.protected = False

    def base_ac(self):
        return ARMOR.get(self.subtype, 10)

    def stack_key(self):
        if self.kind in ("potion", "scroll", "food"):
            return (self.kind, self.subtype)
        if self.kind == "weapon" and self.subtype in THROWABLE_STACK:
            return (self.kind, self.subtype, self.enchant)
        return None


class Player:
    """Состояние персонажа.

    Явный класс со __slots__ вместо анонимного объекта: опечатка в имени поля
    падает сразу, а не создаёт молча новый атрибут, который никто не читает.
    """

    # временные эффекты: все тикают одинаково, поэтому перечислены один раз
    TIMERS = ("confused", "blind", "hasted", "frozen", "held", "see_invis",
              "levitate", "hallu", "detect_mon", "detect_items")

    __slots__ = ("x", "y", "hp", "max_hp", "strength", "max_strength", "xp",
                 "xp_level", "gold", "food", "inventory", "weapon", "armor",
                 "rings", "has_amulet") + TIMERS

    def __init__(self):
        self.x = self.y = 0
        self.max_hp = self.hp = 12
        self.strength = self.max_strength = 16
        self.xp = 0
        self.xp_level = 1
        self.gold = 0
        self.food = 1500.0
        self.inventory = []
        self.weapon = None
        self.armor = None
        self.rings = []
        self.has_amulet = False
        for t in self.TIMERS:
            setattr(self, t, 0)

    def tick_timers(self):
        for t in self.TIMERS:
            v = getattr(self, t)
            if v > 0:
                setattr(self, t, v - 1)

    def has_ring(self, subtype):
        return any(r.subtype == subtype for r in self.rings)


class Monster:
    def __init__(self, template, x, y):
        (self.name, self.color, self.xp, self.hd, self.ac, dmg,
         flags, self.dmin, self.dmax) = template
        self.dmg = list(dmg)
        self.flags = set(flags)          # копия! иначе жезлы портят шаблон
        self.max_hp = max(1, roll(self.hd, 8))
        self.hp = self.max_hp
        self.x, self.y = x, y
        self.awake = "mean" in self.flags
        self.fleeing = False
        self.gold = 0
        self.stolen = None


class Room:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.lit = True
        self.cx, self.cy = x + w // 2, y + h // 2


class Level:
    def __init__(self):
        self.grid = [[WALL] * MAP_COLS for _ in range(MAP_ROWS)]
        self.room_id = [[-1] * MAP_COLS for _ in range(MAP_ROWS)]
        self.explored = [[False] * MAP_COLS for _ in range(MAP_ROWS)]
        self.doors = set()
        self.rooms = []
        self.monsters = []
        self.items = []
        self.gold = []
        self.traps = []
        self.stairs_down = None
        self.stairs_up = None


# ============================================================================
#  РАСКЛАДКА ЭКРАНА
# ============================================================================
class Layout:
    """Все прямоугольники интерфейса, рассчитанные от реального размера окна."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.pad = max(3, round(w * 0.010))
        self.gap = max(2, self.pad // 2)
        pad = self.pad

        # --- размеры кнопок клавиатуры (5 рядов) ---
        # 0.106 * 1080 ≈ 114 px ≈ 7.3 мм на экране Redmi Note 13 (~395 ppi):
        # чуть выше эргономического минимума в 7 мм для уверенного нажатия пальцем
        self.btn_h = max(22, round(w * 0.106))
        # если экран короткий (окно на ПК) — ужимаем кнопки, чтобы влезла карта
        while 5 * self.btn_h + 6 * pad > h * 0.42 and self.btn_h > 22:
            self.btn_h -= 1
        self.kb_h = 5 * self.btn_h + 6 * pad
        self.kb_y = h - self.kb_h

        # --- панели текста ---
        self.line_h = max(11, round(w * 0.034))
        self.msg_h = 2 * self.line_h + 2 * pad
        self.status_h = 4 * self.line_h + 2 * pad
        self.status_y = self.kb_y - self.status_h

        # --- карта: строго между сообщениями и статусом ---
        band_top = self.msg_h + pad
        band_h = self.status_y - band_top - pad
        self.tile = max(2, min(w // MAP_COLS, band_h // MAP_ROWS))
        self.map_w = self.tile * MAP_COLS
        self.map_h = self.tile * MAP_ROWS
        self.map_x = (w - self.map_w) // 2
        self.map_y = band_top + max(0, (band_h - self.map_h) // 2)

        # --- геометрия блоков клавиатуры ---
        gap = self.gap
        dpad_total = int((w - 2 * pad) * 0.46)
        self.dcw = (dpad_total - 2 * gap) // 3
        self.dpad_x = pad
        self.right_x = pad + 3 * self.dcw + 2 * gap + pad
        right_total = w - self.right_x - pad
        self.rcw = (right_total - 2 * gap) // 3
        self.bcw = (w - 2 * pad - 4 * gap) // 5

    def row_y(self, i):
        return self.kb_y + self.pad + i * (self.btn_h + self.pad)


# ============================================================================
#  ИГРА
# ============================================================================
class RogueGame:
    VI_KEYS = {'h': (-1, 0), 'l': (1, 0), 'k': (0, -1), 'j': (0, 1),
               'y': (-1, -1), 'u': (1, -1), 'b': (-1, 1), 'n': (1, 1)}

    # команды, которые тратят ход (во сне/параличе недоступны)
    TURN_COMMANDS = frozenset((
        'move', 'descend', 'ascend', 'search', 'quaff', 'read', 'zap', 'eat',
        'throw', 'drop', 'wield', 'wear', 'takeoff', 'putring', 'remring'))

    def __init__(self, size=None):
        pygame.init()
        try:
            pygame.mixer.quit()          # звук не нужен; на Android экономит ресурсы
        except Exception:
            pass
        self.screen = self.create_window(size)
        # движение мыши/пальца ничего не меняет в пошаговой игре, но будит
        # перерисовку — глушим на входе, чтобы не жечь батарею
        for ev in ("MOUSEMOTION", "FINGERMOTION"):
            if hasattr(pygame, ev):
                pygame.event.set_blocked(getattr(pygame, ev))
        w, h = self.screen.get_size()
        self.L = Layout(w, h)
        self.fonts = {}
        self.font_path = self.pick_font_path()
        pygame.display.set_caption("PixelRogue")
        self.clock = pygame.time.Clock()
        self.build_keyboard()
        self.pressed_id = None
        self.hold_id = None
        self.hold_start = 0
        self.hold_last = 0
        self.hold_hp = 0
        self.dirty = True
        self.new_game()

    # ------------------------------------------------------------ окно ----
    def create_window(self, size=None):
        if size:                         # явный размер: отладка раскладок на ПК
            return pygame.display.set_mode(size)
        info = pygame.display.Info()
        sw, sh = info.current_w, info.current_h
        if IS_ANDROID:
            try:
                return pygame.display.set_mode((sw, sh))
            except Exception:
                return pygame.display.set_mode((0, 0))
        # на ПК — окно с пропорциями Redmi Note 13 (20:9)
        ph = min(1120, max(560, sh - 90))
        pw = int(ph * REF_W / REF_H)
        return pygame.display.set_mode((pw, ph))

    def pick_font_path(self):
        """Ищем шрифт с поддержкой кириллицы; иначе — встроенный."""
        for name in ("robotocondensed", "roboto", "notosans", "droidsans",
                     "dejavusanscondensed", "dejavusans", "liberationsans", "arial"):
            path = pygame.font.match_font(name)
            if not path:
                continue
            try:
                f = pygame.font.Font(path, 24)
                if not any(m is None for m in f.metrics("Ая Жё")):
                    return path
            except Exception:
                continue
        return None

    def F(self, size):
        size = max(8, int(size))
        if size not in self.fonts:
            try:
                self.fonts[size] = pygame.font.Font(self.font_path, size)
            except Exception:
                self.fonts[size] = pygame.font.Font(None, size)
        return self.fonts[size]

    # -------------------------------------------------- новая партия ------
    def new_game(self):
        self.look = {
            'potion': assign_looks(POTIONS, POTION_LOOKS),
            'scroll': {s: make_scroll_title() for s in SCROLLS},
            'ring':   assign_looks(RINGS, RING_LOOKS),
            'wand':   assign_looks(WANDS, WAND_LOOKS),
        }
        self.idd = {'potion': set(), 'scroll': set(), 'ring': set(), 'wand': set()}

        self.p = p = Player()

        self.regen_counter = 0
        self.haste_toggle = False
        self.turn = 0
        self.levels = {}
        self.depth = 0
        self.messages = []
        self.state = 'play'          # play / dead / won
        self.mode = 'play'           # play / select / direction / list / help
        self.pending = None
        self.pending_action = None
        self.overlay = None
        self.death_cause = ""

        mace = Item("weapon", "булава", enchant=1); mace.known = True
        mail = Item("armor", "кольчужный доспех", enchant=1); mail.known = True
        p.inventory += [mace, mail,
                        Item("weapon", "короткий лук"),
                        Item("weapon", "стрела", count=24),
                        Item("food", "паёк")]
        p.weapon = mace
        p.armor = mail

        self.msg("Добро пожаловать! Амулет Йендора ждёт на 26 уровне.")
        self.enter_level(1, "up")

    # ============================================================ УРОВНИ ==
    def enter_level(self, depth, arrive):
        self.depth = depth
        if depth not in self.levels:
            self.levels[depth] = self.build_level(depth)
        self.cur = self.levels[depth]
        if arrive == "up":
            self.p.x, self.p.y = self.cur.stairs_up
        else:
            self.p.x, self.p.y = (self.cur.stairs_down or self.cur.stairs_up)
        self.p.held = 0
        self.recompute_fov()

    def build_level(self, depth):
        """Генерация по сетке комнат — как в оригинальном Rogue (без наложений)."""
        lv = Level()
        cell_w = MAP_COLS // GRID_COLS
        cell_h = MAP_ROWS // GRID_ROWS
        cells = {}

        for gy in range(GRID_ROWS):
            for gx in range(GRID_COLS):
                ox, oy = gx * cell_w, gy * cell_h
                rw = random.randint(5, max(6, cell_w - 3))
                rh = random.randint(4, max(5, cell_h - 3))
                rx = ox + random.randint(1, max(1, cell_w - rw - 1))
                ry = oy + random.randint(1, max(1, cell_h - rh - 1))
                rx = max(1, min(rx, MAP_COLS - rw - 1))
                ry = max(1, min(ry, MAP_ROWS - rh - 1))
                room = Room(rx, ry, rw, rh)
                room.lit = (random.random() < 0.85 - depth * 0.012)
                rid = len(lv.rooms)
                for y in range(ry, ry + rh):
                    for x in range(rx, rx + rw):
                        lv.grid[y][x] = FLOOR
                        lv.room_id[y][x] = rid
                lv.rooms.append(room)
                cells[(gx, gy)] = rid

        # остовное дерево по сетке (гарантирует связность) + пара лишних связей
        visited = {(0, 0)}
        stack = [(0, 0)]
        edges = []
        while stack:
            cx, cy = stack[-1]
            nbrs = []
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (cx + dx, cy + dy)
                if 0 <= n[0] < GRID_COLS and 0 <= n[1] < GRID_ROWS and n not in visited:
                    nbrs.append(n)
            if nbrs:
                n = random.choice(nbrs)
                visited.add(n)
                edges.append(((cx, cy), n))
                stack.append(n)
            else:
                stack.pop()
        for _ in range(3):
            gx = random.randrange(GRID_COLS)
            gy = random.randrange(GRID_ROWS)
            dx, dy = random.choice([(1, 0), (0, 1)])
            n = (gx + dx, gy + dy)
            if 0 <= n[0] < GRID_COLS and 0 <= n[1] < GRID_ROWS:
                edges.append(((gx, gy), n))

        for a, b in edges:
            self.carve_corridor(lv, lv.rooms[cells[a]], lv.rooms[cells[b]])

        self.mark_doors(lv)

        lv.stairs_up = self.free_tile(lv)
        if depth < MAX_DEPTH:
            far = self.far_tile(lv, lv.stairs_up)
            lv.stairs_down = far
        self.populate(lv, depth)
        return lv

    def monster_pool(self, depth):
        """Монстры, подходящие для глубины; на всякий случай — непустой список."""
        pool = [m for m in MONSTERS if m.dmin <= depth <= m.dmax]
        return pool or sorted(MONSTERS, key=lambda m: m.dmin)[-3:]

    def carve_corridor(self, lv, a, b):
        """Г-образный коридор: не выходит за пределы двух соседних ячеек сетки."""
        x1, y1, x2, y2 = a.cx, a.cy, b.cx, b.cy
        if abs(x1 - x2) > abs(y1 - y2):
            for x in range(min(x1, x2), max(x1, x2) + 1):
                lv.grid[y1][x] = FLOOR
            for y in range(min(y1, y2), max(y1, y2) + 1):
                lv.grid[y][x2] = FLOOR
        else:
            for y in range(min(y1, y2), max(y1, y2) + 1):
                lv.grid[y][x1] = FLOOR
            for x in range(min(x1, x2), max(x1, x2) + 1):
                lv.grid[y2][x] = FLOOR

    def mark_doors(self, lv):
        """Дверь = клетка на границе комнаты, из которой выходит коридор."""
        for r in lv.rooms:
            for y in range(r.y, r.y + r.h):
                for x in range(r.x, r.x + r.w):
                    on_edge = (x == r.x or x == r.x + r.w - 1 or
                               y == r.y or y == r.y + r.h - 1)
                    if not on_edge:
                        continue
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = x + dx, y + dy
                        if not (0 <= nx < MAP_COLS and 0 <= ny < MAP_ROWS):
                            continue
                        if lv.grid[ny][nx] == FLOOR and lv.room_id[ny][nx] == -1:
                            lv.doors.add((x, y))
                            break

    def free_tile(self, lv, avoid=None):
        avoid = avoid or []
        for _ in range(3000):
            x = random.randint(1, MAP_COLS - 2)
            y = random.randint(1, MAP_ROWS - 2)
            if lv.grid[y][x] == FLOOR and (x, y) not in avoid:
                return (x, y)
        for y in range(MAP_ROWS):
            for x in range(MAP_COLS):
                if lv.grid[y][x] == FLOOR:
                    return (x, y)
        return (1, 1)

    def far_tile(self, lv, origin):
        """Клетка подальше от origin — чтобы лестницы не стояли рядом."""
        best, bestd = None, -1
        for _ in range(400):
            x, y = self.free_tile(lv, avoid=[origin])
            d = abs(x - origin[0]) + abs(y - origin[1])
            if d > bestd:
                best, bestd = (x, y), d
            if bestd > MAP_ROWS:
                break
        return best or self.free_tile(lv, avoid=[origin])

    def random_free_spot(self, lv, exclude_player=False):
        """Проходимая клетка, не занятая монстром (и, если нужно, игроком).

        Нужна всем «переносам»: телепорт игрока, бегство вора, изгнание жезлом.
        Раньше каждый из них брал free_tile() напрямую и мог поставить монстра
        прямо на игрока или на другого монстра.
        """
        for _ in range(200):
            x, y = self.free_tile(lv)
            if self.monster_at(lv, x, y):
                continue
            if exclude_player and (x, y) == (self.p.x, self.p.y):
                continue
            return (x, y)
        return None

    def occupied(self, lv, x, y):
        if lv.stairs_up == (x, y) or lv.stairs_down == (x, y):
            return True
        for m in lv.monsters:
            if m.x == x and m.y == y:
                return True
        for ix, iy, _ in lv.items:
            if ix == x and iy == y:
                return True
        for gx, gy, _ in lv.gold:
            if gx == x and gy == y:
                return True
        for t in lv.traps:
            if t['x'] == x and t['y'] == y:
                return True
        return (x, y) in lv.doors

    def populate(self, lv, depth):
        sx, sy = lv.stairs_up

        def spot():
            for _ in range(400):
                x, y = self.free_tile(lv)
                if self.occupied(lv, x, y) or (x, y) == (sx, sy):
                    continue
                return (x, y)
            return self.free_tile(lv)

        def spot_far():
            for _ in range(400):
                x, y = self.free_tile(lv)
                if self.occupied(lv, x, y):
                    continue
                if abs(x - sx) + abs(y - sy) < 9:
                    continue
                return (x, y)
            return spot()

        pool = self.monster_pool(depth)
        for _ in range(random.randint(3, 5) + depth // 4):
            x, y = spot_far()
            lv.monsters.append(Monster(random.choice(pool), x, y))

        for _ in range(random.randint(2, 5)):
            x, y = spot()
            lv.items.append([x, y, self.random_item(depth)])
        for _ in range(random.randint(1, 3)):
            x, y = spot()
            lv.gold.append([x, y, random.randint(2, 20) + depth * random.randint(1, 6)])
        for _ in range(random.randint(0, 2 + depth // 4)):
            x, y = spot()
            lv.traps.append({'x': x, 'y': y, 'type': random.choice(TRAP_TYPES), 'found': False})
        if depth == MAX_DEPTH:
            x, y = spot()
            lv.items.append([x, y, Item("amulet", "yendor")])

    def random_item(self, depth):
        cats = (["potion"] * 28 + ["scroll"] * 24 + ["ring"] * 6 + ["wand"] * 6 +
                ["weapon"] * 9 + ["armor"] * 9 + ["food"] * 14)
        k = random.choice(cats)
        if k == "potion":
            return Item("potion", random.choice(POTIONS))
        if k == "scroll":
            return Item("scroll", random.choice(SCROLLS))
        if k == "ring":
            return Item("ring", random.choice(RINGS),
                        enchant=random.randint(-1, 2), cursed=random.random() < 0.25)
        if k == "wand":
            return Item("wand", random.choice(WANDS), charges=random.randint(3, 7))
        if k == "weapon":
            name = random.choice(list(WEAPONS.keys()))
            cnt = random.randint(6, 18) if name in THROWABLE_STACK else 1
            ench = random.choice([-1, 0, 0, 1, 1, 2])
            return Item("weapon", name, enchant=ench, count=cnt, cursed=ench < 0)
        if k == "armor":
            name = random.choice(list(ARMOR.keys()))
            ench = random.choice([-1, 0, 0, 1, 1, 2])
            return Item("armor", name, enchant=ench, cursed=ench < 0)
        return Item("food", random.choice(["паёк", "слизневик"]))

    # ========================================================= ВИДИМОСТЬ ==
    def recompute_fov(self):
        lv = self.cur
        self.visible = [[False] * MAP_COLS for _ in range(MAP_ROWS)]
        px, py = self.p.x, self.p.y
        if self.p.blind > 0:
            self.reveal(px, py)
            return
        for yy in range(py - 1, py + 2):
            for xx in range(px - 1, px + 2):
                self.reveal(xx, yy)
        rid = lv.room_id[py][px] if 0 <= py < MAP_ROWS and 0 <= px < MAP_COLS else -1
        if rid >= 0 and lv.rooms[rid].lit:
            r = lv.rooms[rid]
            for yy in range(r.y - 1, r.y + r.h + 1):
                for xx in range(r.x - 1, r.x + r.w + 1):
                    self.reveal(xx, yy)

    def reveal(self, x, y):
        if 0 <= x < MAP_COLS and 0 <= y < MAP_ROWS:
            self.visible[y][x] = True
            self.cur.explored[y][x] = True

    # ==================================================== ХОД / ДЕЙСТВИЯ ==
    def try_move_player(self, dx, dy):
        if dx == 0 and dy == 0:
            self.end_turn()
            return
        confused = self.p.confused > 0
        if confused:
            dx, dy = random.choice(DIRS8)
        nx, ny = self.p.x + dx, self.p.y + dy
        if (not (0 <= nx < MAP_COLS and 0 <= ny < MAP_ROWS)
                or self.cur.grid[ny][nx] == WALL):
            # осознанный шаг в стену хода не стоит (как в оригинале),
            # а вот спутанный персонаж в неё именно врезается — и ход теряет
            if confused:
                self.msg("Ты врезаешься в стену.")
                self.end_turn()
            return
        m = self.monster_at(self.cur, nx, ny)
        if m is not None:
            self.attack_monster(m)
            self.end_turn()
            return
        if self.p.held > 0:
            self.msg("Тебя что-то держит — не вырваться!")
            self.end_turn()
            return
        self.p.x, self.p.y = nx, ny
        self.on_enter_tile()
        self.end_turn()

    def on_enter_tile(self):
        lv = self.cur
        for g in lv.gold[:]:
            if g[0] == self.p.x and g[1] == self.p.y:
                self.p.gold += g[2]
                self.msg("Подобрано золото: %d." % g[2])
                lv.gold.remove(g)
        for slot in lv.items[:]:
            if slot[0] == self.p.x and slot[1] == self.p.y:
                self.pick_up(slot[2])
                lv.items.remove(slot)
        px, py = self.p.x, self.p.y
        for t in lv.traps:
            if t['x'] == px and t['y'] == py:
                self.spring_trap(t)
                # Люк уводит на другой уровень, телепорт — на другую клетку:
                # оставшиеся ловушки ЭТОГО уровня к новой позиции уже не
                # относятся, иначе игрок ловит чужую ловушку сразу после падения.
                if self.cur is not lv or (self.p.x, self.p.y) != (px, py):
                    return
        if (self.p.x, self.p.y) == lv.stairs_down:
            self.msg("Здесь лестница вниз — жми «Вниз >».")
        elif (self.p.x, self.p.y) == lv.stairs_up:
            self.msg("Здесь лестница вверх — жми «Вверх <».")

    def pick_up(self, it):
        if it.kind == "amulet":
            self.p.has_amulet = True
            self.p.inventory.append(it)
            self.msg("Амулет Йендора твой! Теперь — наверх!")
            return
        key = it.stack_key()
        if key is not None:
            for ex in self.p.inventory:
                if ex.stack_key() == key:
                    ex.count += it.count
                    self.msg("Подобрано: %s." % self.item_name(it))
                    return
        if len(self.p.inventory) >= 22:
            self.msg("Рюкзак полон — предмет остался на полу.")
            self.cur.items.append([self.p.x, self.p.y, it])
            return
        self.p.inventory.append(it)
        self.msg("Подобрано: %s." % self.item_name(it))

    def spring_trap(self, t):
        t['found'] = True
        name = TRAP_NAMES[t['type']]
        if self.p.levitate > 0 and t['type'] in ("trapdoor", "dart", "bear"):
            self.msg("Ты паришь над ловушкой (%s)." % name)
            return
        self.msg("Ловушка! %s." % name)
        tp = t['type']
        if tp == "trapdoor":
            self.damage_player(roll(1, 6), "падение")
            if self.state == 'play' and self.depth < MAX_DEPTH:
                self.enter_level(self.depth + 1, "up")
        elif tp == "teleport":
            self.teleport_player()
        elif tp == "dart":
            self.damage_player(roll(1, 4), "дротик")
            if random.random() < 0.4:
                self.lose_strength(1)
        elif tp == "sleep_gas":
            self.p.frozen += random.randint(2, 5)
            self.msg("Ты засыпаешь от газа.")
        elif tp == "bear":
            self.p.held += random.randint(2, 5)
            self.msg("Капкан схватил тебя!")
        elif tp == "rust":
            self.rust_armor()

    def teleport_player(self):
        spot = self.random_free_spot(self.cur)
        if spot is None:
            return
        self.p.x, self.p.y = spot
        self.recompute_fov()

    def descend(self):
        if self.cur.stairs_down and (self.p.x, self.p.y) == self.cur.stairs_down:
            self.enter_level(self.depth + 1, "up")
            self.msg("Ты спускаешься на уровень %d." % self.depth)
        else:
            self.msg("Здесь нет лестницы вниз.")

    def ascend(self):
        if self.cur.stairs_up and (self.p.x, self.p.y) == self.cur.stairs_up:
            if self.depth == 1:
                if self.p.has_amulet:
                    self.state = 'won'
                else:
                    self.msg("Выход наверху, но без Амулета путь закрыт.")
                return
            self.enter_level(self.depth - 1, "down")
            self.msg("Ты поднимаешься на уровень %d." % self.depth)
        else:
            self.msg("Здесь нет лестницы вверх.")

    def search(self):
        found = 0
        for t in self.cur.traps:
            if not t['found'] and abs(t['x'] - self.p.x) <= 1 and abs(t['y'] - self.p.y) <= 1:
                t['found'] = True
                found += 1
        if found:
            self.msg("Найдено ловушек: %d." % found)
        else:
            self.msg("Ты ищешь, но ничего не находишь.")
        self.end_turn()

    # ============================================================== БОЙ ===
    def monster_at(self, lv, x, y):
        for m in lv.monsters:
            if m.x == x and m.y == y:
                return m
        return None

    def attack_monster(self, m):
        if "freeze_on_melee" in m.flags:
            self.msg("Ты бьёшь: %s." % m.name)
            if random.random() < 0.7:
                self.p.frozen += random.randint(2, 5)
                self.msg("Взгляд парализует тебя!")
        wpn = self.p.weapon
        hit_b, dam_b = str_bonuses(self.eff_str())
        ring_hit = sum(1 for r in self.p.rings if r.subtype == "dexterity")
        ring_dam = sum(1 for r in self.p.rings if r.subtype == "increase_damage")
        wb = wpn.enchant if wpn else 0
        swing = random.randint(1, 20)
        bonus = self.p.xp_level + hit_b + wb + ring_hit
        if self.p.food <= 150:
            bonus -= 1
        if swing == 1 or (swing != 20 and swing + bonus < 10 - m.ac):
            self.msg("Промах: %s." % m.name)
            return
        if wpn:
            spec = WEAPONS[wpn.subtype]
            dmg = roll(spec.dice, spec.sides) + dam_b + wb + ring_dam
        else:
            dmg = roll(1, 3) + dam_b
        dmg = max(1, dmg)
        m.hp -= dmg
        m.awake = True
        if m.hp <= 0:
            self.kill_monster(m)
        else:
            self.msg("Попадание: %s (%d)." % (m.name, dmg))
            if m.hp < m.max_hp // 4 and "mean" in m.flags and random.random() < 0.4:
                m.fleeing = True

    def kill_monster(self, m):
        self.msg("%s %s!" % (m.name.capitalize(),
                             agree(m.name, "повержен", "повержена", "повержено")))
        if m in self.cur.monsters:
            self.cur.monsters.remove(m)
        if m.stolen:
            self.cur.items.append([m.x, m.y, m.stolen])
        if m.gold:
            self.cur.gold.append([m.x, m.y, m.gold])
        self.gain_xp(m.xp)

    def gain_xp(self, amount):
        self.p.xp += amount
        new_level = 1
        for i, t in enumerate(XP_THRESHOLDS):
            if self.p.xp >= t:
                new_level = i + 1
        while self.p.xp_level < new_level:
            self.p.xp_level += 1
            gain = random.randint(4, 9)
            self.p.max_hp += gain
            self.p.hp += gain
            self.msg("Ты достигаешь %d уровня опыта!" % self.p.xp_level)

    def damage_player(self, dmg, source=""):
        if self.state != 'play':
            return                       # причину смерти перезаписывать нельзя
        self.p.hp -= max(0, dmg)
        if self.p.hp <= 0:
            self.p.hp = 0
            self.state = 'dead'
            self.death_cause = source

    def lose_strength(self, n):
        self.p.strength = max(3, self.p.strength - n)
        self.msg("Ты чувствуешь слабость.")

    def rust_armor(self):
        a = self.p.armor
        if not a:
            self.msg("Ржавчина, но брони на тебе нет.")
            return
        if a.protected:
            self.msg("Броня защищена от ржавчины.")
            return
        a.enchant -= 1
        a.known = True
        self.msg("Твоя броня ржавеет!")

    def eff_str(self):
        s = self.p.strength
        for r in self.p.rings:
            if r.subtype == "add_strength":
                s += (r.enchant if r.enchant else 1)
        return s

    def can_see_invisible(self):
        return self.p.see_invis > 0 or self.p.has_ring("see_invisible")

    def player_ac(self):
        ac = 10
        if self.p.armor:
            ac = self.p.armor.base_ac() - self.p.armor.enchant
        for r in self.p.rings:
            if r.subtype == "protection":
                ac -= (r.enchant if r.enchant else 1)
        return ac

    def adjacent_visible_monster(self):
        for m in self.cur.monsters:
            if abs(m.x - self.p.x) <= 1 and abs(m.y - self.p.y) <= 1:
                if self.visible[m.y][m.x] or self.p.detect_mon > 0:
                    return True
        return False

    # ========================================================= ПРЕДМЕТЫ ===
    def quaff(self, it):
        self.consume_one(it)
        self.idd['potion'].add(it.subtype)
        s = it.subtype
        if s == "healing":
            self.p.hp = min(self.p.max_hp, self.p.hp + roll(2, 8) + self.p.xp_level)
            if self.p.hp == self.p.max_hp:
                self.p.max_hp += 1; self.p.hp += 1
            self.msg("Тебе становится лучше.")
        elif s == "extra_healing":
            self.p.max_hp += 2
            self.p.hp = self.p.max_hp
            self.p.blind = self.p.confused = 0
            self.msg("Ты полностью исцелён!")
        elif s == "gain_strength":
            self.p.strength += 1
            self.p.max_strength = max(self.p.max_strength, self.p.strength)
            self.msg("Ты чувствуешь прилив сил.")
        elif s == "restore_strength":
            self.p.strength = self.p.max_strength
            self.msg("Сила восстановлена.")
        elif s == "poison":
            self.lose_strength(roll(1, 3))
            self.damage_player(roll(1, 6), "яд")
        elif s == "confusion":
            self.p.confused += random.randint(8, 16); self.msg("Голова кружится...")
        elif s == "blindness":
            self.p.blind += random.randint(40, 80); self.msg("Ты слепнешь!")
        elif s == "haste_self":
            self.p.hasted += random.randint(8, 16); self.msg("Ты движешься быстрее!")
        elif s == "detect_monsters":
            self.p.detect_mon = 9
            self.msg("Ты ощущаешь монстров." if self.cur.monsters else "Монстров рядом нет.")
        elif s == "magic_detection":
            self.p.detect_items = 9
            self.msg("Ты ощущаешь предметы." if self.cur.items else "Магии рядом нет.")
        elif s == "raise_level":
            self.p.xp = XP_THRESHOLDS[min(self.p.xp_level, len(XP_THRESHOLDS) - 1)]
            self.gain_xp(1)
        elif s == "see_invisible":
            self.p.see_invis += random.randint(40, 80); self.msg("Зрение обостряется.")
        elif s == "levitation":
            self.p.levitate += random.randint(15, 30); self.msg("Ты воспаряешь над полом.")
        elif s == "hallucination":
            self.p.hallu += random.randint(40, 80); self.msg("Краски мира поплыли...")
        elif s == "sleep":
            self.p.frozen += random.randint(4, 8); self.msg("Тебя клонит в сон.")
        self.end_turn()

    def read(self, it):
        self.consume_one(it)
        self.idd['scroll'].add(it.subtype)
        s = it.subtype
        if s == "identify":
            unid = [x for x in self.p.inventory if not self.is_identified(x)]
            if unid:
                tgt = random.choice(unid)
                self.identify(tgt)
                self.msg("Это: %s." % self.item_name(tgt))
            else:
                self.msg("Опознавать нечего.")
        elif s == "teleportation":
            self.teleport_player(); self.msg("Тебя переносит!")
        elif s == "enchant_weapon":
            if self.p.weapon:
                self.p.weapon.enchant += 1
                self.p.weapon.cursed = False
                self.p.weapon.known = True
                self.msg("Оружие вспыхивает синим.")
            else:
                self.msg("Нет оружия в руках.")
        elif s == "enchant_armor":
            if self.p.armor:
                self.p.armor.enchant += 1
                self.p.armor.cursed = False
                self.p.armor.known = True
                self.msg("Броня покрывается серебром.")
            else:
                self.msg("Брони на тебе нет.")
        elif s == "remove_curse":
            for x in [self.p.weapon, self.p.armor] + self.p.rings:
                if x:
                    x.cursed = False
            self.msg("Ты чувствуешь себя свободным.")
        elif s == "create_monster":
            self.spawn_near_player()
        elif s == "aggravate_monsters":
            for m in self.cur.monsters:
                m.awake = True; m.fleeing = False
            self.msg("Гул будит всех монстров!")
        elif s == "magic_mapping":
            for y in range(MAP_ROWS):
                for x in range(MAP_COLS):
                    self.cur.explored[y][x] = True
            self.msg("Карта уровня раскрывается.")
        elif s == "light":
            rid = self.cur.room_id[self.p.y][self.p.x]
            if rid >= 0:
                self.cur.rooms[rid].lit = True
            self.msg("Комната озаряется светом.")
        elif s == "hold_monster":
            for m in self.cur.monsters:
                if abs(m.x - self.p.x) <= 2 and abs(m.y - self.p.y) <= 2:
                    m.awake = False
            self.msg("Ближние монстры застывают.")
        elif s == "sleep":
            self.p.frozen += random.randint(4, 8); self.msg("Свиток усыпляет тебя!")
        elif s == "scare_monster":
            for m in self.cur.monsters:
                if abs(m.x - self.p.x) <= 4 and abs(m.y - self.p.y) <= 4:
                    m.fleeing = True
            self.msg("Монстры в ужасе разбегаются.")
        elif s == "protect_armor":
            if self.p.armor:
                self.p.armor.protected = True
                self.msg("Броня защищена от ржавчины.")
            else:
                self.msg("Брони на тебе нет.")
        self.recompute_fov()
        self.end_turn()

    def spawn_near_player(self):
        pool = self.monster_pool(self.depth)
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1)]:
            x, y = self.p.x + dx, self.p.y + dy
            if (0 <= x < MAP_COLS and 0 <= y < MAP_ROWS and
                    self.cur.grid[y][x] == FLOOR and not self.monster_at(self.cur, x, y)):
                self.cur.monsters.append(Monster(random.choice(pool), x, y))
                self.msg("Из воздуха возникает монстр!")
                return

    def zap(self, wand, d):
        if wand.charges <= 0:
            self.msg("Жезл иссяк.")
            self.end_turn(); return
        wand.charges -= 1
        self.idd['wand'].add(wand.subtype)
        dx, dy = d
        s = wand.subtype
        if s == "light":
            rid = self.cur.room_id[self.p.y][self.p.x]
            if rid >= 0:
                self.cur.rooms[rid].lit = True
            self.msg("Вспышка света!")
            self.recompute_fov(); self.end_turn(); return
        if s == "nothing":
            self.msg("Ничего не происходит.")
            self.end_turn(); return
        if s == "drain_life":
            self.damage_player(max(1, self.p.hp // 3), "жезл жизни")
            for m in self.cur.monsters[:]:
                if self.visible[m.y][m.x]:
                    m.hp -= roll(3, 6)
                    if m.hp <= 0:
                        self.kill_monster(m)
            self.msg("Волна высасывает жизнь вокруг.")
            self.end_turn(); return
        if dx == 0 and dy == 0:
            self.msg("Луч уходит в пол.")
            self.end_turn(); return
        x, y = self.p.x, self.p.y
        target = None
        for _ in range(20):
            x += dx; y += dy
            if not (0 <= x < MAP_COLS and 0 <= y < MAP_ROWS) or self.cur.grid[y][x] == WALL:
                break
            m = self.monster_at(self.cur, x, y)
            if m:
                target = m; break
        if not target:
            self.msg("Луч уходит в пустоту.")
            self.end_turn(); return
        if s in ("striking", "magic_missile"):
            target.hp -= roll(2, 6); self.msg("Луч бьёт: %s." % target.name)
        elif s in ("lightning", "fire", "cold"):
            target.hp -= roll(4, 6); self.msg("Заряд поражает: %s." % target.name)
        elif s == "slow_monster":
            target.flags.add("slow")
            self.msg("%s %s." % (target.name.capitalize(),
                                 agree(target.name, "замедлен", "замедлена", "замедлено")))
        elif s == "haste_monster":
            target.flags.discard("slow")
            self.msg("%s %s!" % (target.name.capitalize(),
                                 agree(target.name, "ускорен", "ускорена", "ускорено")))
        elif s == "polymorph":
            pool = self.monster_pool(self.depth)
            nm = Monster(random.choice(pool), target.x, target.y)
            self.cur.monsters.remove(target)
            self.cur.monsters.append(nm)
            self.msg("Превращение: %s -> %s!" % (target.name, nm.name))
            self.end_turn(); return
        elif s == "teleport_away":
            spot = self.random_free_spot(self.cur, exclude_player=True)
            if spot:
                target.x, target.y = spot
            self.msg("%s исчезает." % target.name.capitalize())
        elif s == "cancellation":
            target.flags = {f for f in target.flags if f == "fly"}
            self.msg("%s теряет свои силы." % target.name.capitalize())
        if target.hp <= 0 and target in self.cur.monsters:
            self.kill_monster(target)
        else:
            target.awake = True
        self.end_turn()

    def throw(self, weapon, d):
        dx, dy = d
        if dx == 0 and dy == 0:
            self.msg("Некуда метать.")
            self.end_turn(); return
        x, y = self.p.x, self.p.y
        target = None
        for _ in range(12):
            x += dx; y += dy
            if not (0 <= x < MAP_COLS and 0 <= y < MAP_ROWS) or self.cur.grid[y][x] == WALL:
                x -= dx; y -= dy
                break
            m = self.monster_at(self.cur, x, y)
            if m:
                target = m; break
        landed = (x, y)
        thrown = self.consume_one(weapon, give_copy=True)
        if target:
            spec = WEAPONS[weapon.subtype]
            bonus = self.p.xp_level + str_bonuses(self.eff_str())[0] + weapon.enchant
            if self.p.weapon and self.p.weapon.subtype == BOW and weapon.subtype == ARROW:
                bonus += 2
            if random.randint(1, 20) + bonus >= 10 - target.ac:
                dmg = max(1, roll(spec.dice, spec.sides) + weapon.enchant)
                target.hp -= dmg
                target.awake = True
                self.msg("Снаряд попадает в %s (%d)." % (target.name, dmg))
                if target.hp <= 0:
                    self.kill_monster(target)
            else:
                self.msg("Снаряд пролетает мимо.")
                if thrown and self.cur.grid[target.y][target.x] == FLOOR:
                    self.cur.items.append([target.x, target.y, thrown])
        else:
            self.msg("Снаряд падает на пол.")
            if thrown and self.cur.grid[landed[1]][landed[0]] == FLOOR:
                self.cur.items.append([landed[0], landed[1], thrown])
        self.end_turn()

    def wield(self, it):
        if self.p.weapon and self.p.weapon.cursed:
            self.msg("Текущее оружие приклеилось к руке (проклято).")
            return
        self.p.weapon = it
        self.msg("Теперь в руках: %s." % self.item_name(it))
        if it.cursed:
            it.known = True
            self.msg("Оружие зловеще прилипает к ладони!")
        self.end_turn()

    def wear(self, it):
        if self.p.armor:
            self.msg("Сначала сними текущую броню.")
            return
        self.p.armor = it
        self.msg("Ты надеваешь: %s." % self.item_name(it))
        if it.cursed:
            it.known = True
            self.msg("Броня сжимается на теле — не снять!")
        self.end_turn()

    def take_off_armor(self):
        if not self.p.armor:
            self.msg("На тебе нет брони.")
            return
        if self.p.armor.cursed:
            self.msg("Броня проклята и не снимается.")
            return
        self.msg("Ты снимаешь: %s." % self.item_name(self.p.armor))
        self.p.armor = None
        self.end_turn()

    def put_ring(self, it):
        if it in self.p.rings:
            self.msg("Кольцо уже надето.")
            return
        if len(self.p.rings) >= 2:
            self.msg("Оба кольца надеты — сними одно.")
            return
        self.p.rings.append(it)
        self.msg("Ты надеваешь кольцо: %s." % self.item_name(it))
        if it.cursed:
            it.known = True
            self.msg("Кольцо не желает сниматься!")
        self.end_turn()

    def remove_ring_cmd(self):
        wearable = [r for r in self.p.rings if not r.cursed]
        if not self.p.rings:
            self.msg("Колец на тебе нет.")
            return
        if not wearable:
            self.msg("Кольца прокляты и не снимаются.")
            return
        if len(wearable) == 1:
            self.do_remove_ring(wearable[0])
            return
        self.prompt_item("Какое кольцо снять?", lambda x: x in wearable, self.do_remove_ring)

    def do_remove_ring(self, r):
        if r in self.p.rings:
            self.p.rings.remove(r)
            self.msg("Ты снимаешь кольцо: %s." % self.item_name(r))
            self.end_turn()

    def eat(self, it):
        self.consume_one(it)
        if it.subtype == "слизневик":
            self.p.food += random.randint(500, 750)
            self.msg("Слизневик... на вкус отвратительно.")
        else:
            self.p.food += random.randint(1000, 1300)
            self.msg("Ты сыт.")
        self.p.food = min(self.p.food, 2000)
        self.end_turn()

    def drop(self, it):
        if it in (self.p.weapon, self.p.armor) or it in self.p.rings:
            self.msg("Сначала сними / убери предмет.")
            return
        self.consume_one(it, all_count=True)
        self.cur.items.append([self.p.x, self.p.y, it])
        self.msg("Брошено: %s." % self.item_name(it))
        self.end_turn()

    def consume_one(self, it, all_count=False, give_copy=False):
        copy = None
        if all_count or it.count <= 1:
            if it in self.p.inventory:
                self.p.inventory.remove(it)
            if it in self.p.rings:
                self.p.rings.remove(it)
            if it is self.p.weapon:
                self.p.weapon = None
            if it is self.p.armor:
                self.p.armor = None
            copy = it
        else:
            it.count -= 1
            if give_copy:
                copy = Item(it.kind, it.subtype, it.enchant, it.charges, 1, it.cursed)
        return copy

    # ================================================== КОНЕЦ ХОДА / ИИ ===
    def end_turn(self):
        if self.state != 'play':
            return
        self.turn += 1
        self.p.tick_timers()
        if self.p.has_ring("searching"):
            for t in self.cur.traps:
                if abs(t['x'] - self.p.x) <= 1 and abs(t['y'] - self.p.y) <= 1:
                    t['found'] = True
        if self.p.has_ring("teleportation") and random.random() < 0.04:
            self.teleport_player()
            self.msg("Кольцо внезапно переносит тебя!")
        do_monsters = True
        if self.p.hasted > 0:
            self.haste_toggle = not self.haste_toggle
            do_monsters = self.haste_toggle
        if do_monsters:
            self.move_monsters()
        if self.state == 'play':         # погиб в свой же ход — тикать нечему
            self.hunger_tick()
            self.regen_tick()
        self.recompute_fov()

    def regen_tick(self):
        rate = max(2, 21 - 2 * self.p.xp_level)
        if self.p.has_ring("regeneration"):
            rate = max(1, rate // 2)
        self.regen_counter += 1
        if self.regen_counter >= rate and self.p.hp < self.p.max_hp:
            self.p.hp += 1
            self.regen_counter = 0

    def hunger_tick(self):
        consume = 1.0
        for r in self.p.rings:
            if r.subtype == "slow_digestion":
                consume -= 0.5
            elif r.subtype == "regeneration":
                consume += 1.0
            elif r.subtype != "adornment":
                consume += 0.5
        self.p.food -= max(0.2, consume)
        if self.p.food <= 0:
            self.damage_player(1, "голод")
            if random.random() < 0.05:
                self.msg("Ты умираешь от голода!")
        elif self.p.food <= 50 and random.random() < 0.08:
            self.p.frozen = max(self.p.frozen, 1)
            self.msg("Ты теряешь сознание от голода!")

    def move_monsters(self):
        aggravate = self.p.has_ring("aggravate_monster")
        stealth = self.p.has_ring("stealth")
        for m in self.cur.monsters[:]:
            if m.hp <= 0 or self.state != 'play':
                continue
            if "regen" in m.flags and m.hp < m.max_hp and random.random() < 0.4:
                m.hp += 1
            dist = abs(m.x - self.p.x) + abs(m.y - self.p.y)
            # соседство — по Чебышёву: игрок бьёт по диагонали, монстр тоже
            # (раньше монстр по манхэттену «не дотягивался» и топтался рядом)
            adjacent = max(abs(m.x - self.p.x), abs(m.y - self.p.y)) <= 1
            if not m.awake:
                rid_p = self.cur.room_id[self.p.y][self.p.x]
                rid_m = self.cur.room_id[m.y][m.x]
                if aggravate or dist <= (3 if stealth else 5) or (rid_p >= 0 and rid_p == rid_m):
                    m.awake = True
            if not m.awake:
                continue
            if "stationary" in m.flags and not adjacent:
                continue
            if "slow" in m.flags and random.random() < 0.5:
                continue
            if ("breath_fire" in m.flags and (m.x == self.p.x or m.y == self.p.y)
                    and dist <= 6 and random.random() < 0.5):
                self.msg("%s дышит огнём!" % m.name.capitalize())
                self.damage_player(roll(2, 8) + self.depth // 3, "огонь дракона")
                continue
            if adjacent:
                self.monster_attack_player(m)
                continue
            if m.fleeing:
                tx = m.x - (1 if self.p.x > m.x else -1 if self.p.x < m.x else 0)
                ty = m.y - (1 if self.p.y > m.y else -1 if self.p.y < m.y else 0)
            elif "erratic" in m.flags and random.random() < 0.5:
                dx, dy = random.choice([(-1, 0), (1, 0), (0, -1), (0, 1)])
                tx, ty = m.x + dx, m.y + dy
            else:
                tx = m.x + (1 if self.p.x > m.x else -1 if self.p.x < m.x else 0)
                ty = m.y + (1 if self.p.y > m.y else -1 if self.p.y < m.y else 0)
            self.step_monster(m, tx, ty)

    def step_monster(self, m, tx, ty):
        if self.can_step(tx, ty):
            m.x, m.y = tx, ty
            return
        for nx, ny in ((m.x + (1 if tx > m.x else -1 if tx < m.x else 0), m.y),
                       (m.x, m.y + (1 if ty > m.y else -1 if ty < m.y else 0))):
            if self.can_step(nx, ny):
                m.x, m.y = nx, ny
                return

    def can_step(self, x, y):
        return (0 <= x < MAP_COLS and 0 <= y < MAP_ROWS and
                self.cur.grid[y][x] == FLOOR and
                not (x == self.p.x and y == self.p.y) and
                not self.monster_at(self.cur, x, y))

    def monster_attack_player(self, m):
        for (n, d) in m.dmg:
            r20 = random.randint(1, 20)
            if r20 == 1 or (r20 != 20 and r20 + m.hd < 17 - self.player_ac()):
                continue
            dmg = roll(n, d)
            fled = self.apply_monster_special(m)
            if dmg > 0:
                self.damage_player(dmg, m.name)
                self.msg("%s бьёт тебя (%d)." % (m.name.capitalize(), dmg))
            if self.state != 'play' or fled:
                return

    def apply_monster_special(self, m):
        f = m.flags
        if "drain_str" in f and random.random() < 0.5:
            self.lose_strength(1)
        if "drain_xp" in f and random.random() < 0.5:
            self.p.xp = max(0, self.p.xp - 50)
            self.msg("Ты чувствуешь, как уходит опыт.")
        if "drain_maxhp" in f and random.random() < 0.5:
            self.p.max_hp = max(1, self.p.max_hp - roll(1, 4))
            self.p.hp = min(self.p.hp, self.p.max_hp)
            self.msg("Силы жизни покидают тебя.")
        if "rust_armor" in f:
            self.rust_armor()
        if "freeze_player" in f and random.random() < 0.4:
            self.p.frozen += random.randint(1, 3)
            self.msg("Тебя сковывает холод!")
        if "confuse" in f and random.random() < 0.4:
            self.p.confused += random.randint(3, 8)
            self.msg("Взгляд монстра путает мысли.")
        if "hold" in f:
            self.p.held = max(self.p.held, random.randint(1, 3))
        if "steal_gold" in f and self.p.gold > 0:
            stolen = min(self.p.gold, random.randint(20, 80) + self.depth * 5)
            self.p.gold -= stolen
            m.gold += stolen
            self.flee_away(m)
            self.msg("%s крадёт золото (%d) и убегает!" % (m.name.capitalize(), stolen))
            return True
        if "steal_item" in f:
            loose = [it for it in self.p.inventory
                     if it not in (self.p.weapon, self.p.armor)
                     and it not in self.p.rings and it.kind != "amulet"]
            if loose:
                it = random.choice(loose)
                self.consume_one(it, all_count=True)
                m.stolen = it
                self.flee_away(m)
                self.msg("%s крадёт: %s — и исчезает!" % (m.name.capitalize(), self.item_name(it)))
                return True
        return False

    def flee_away(self, m):
        spot = self.random_free_spot(self.cur, exclude_player=True)
        if spot:
            m.x, m.y = spot
        m.fleeing = True

    # ====================================================== ИМЕНОВАНИЕ ====
    def is_identified(self, it):
        if it.kind in self.idd:
            return it.subtype in self.idd[it.kind]
        return it.known

    def identify(self, it):
        if it.kind in self.idd:
            self.idd[it.kind].add(it.subtype)
        it.known = True

    def item_name(self, it):
        # количество выносим суффиксом "xN" — так не нужно склонять
        # числительные ("12 стрела" / "12 стрел") и прилагательные при них
        cnt = " x%d" % it.count if it.count > 1 else ""
        ru = SUB_RU.get(it.subtype, it.subtype)
        if it.kind == "amulet":
            return "Амулет Йендора"
        if it.kind == "food":
            return "%s%s" % (it.subtype, cnt)
        if it.kind == "potion":
            if it.subtype in self.idd['potion']:
                return "зелье (%s)%s" % (ru, cnt)
            return "%s зелье%s" % (self.look['potion'][it.subtype], cnt)
        if it.kind == "scroll":
            if it.subtype in self.idd['scroll']:
                return "свиток (%s)%s" % (ru, cnt)
            return "свиток «%s»%s" % (self.look['scroll'][it.subtype], cnt)
        if it.kind == "ring":
            if it.subtype in self.idd['ring']:
                e = " %+d" % it.enchant if it.known and it.enchant else ""
                return "кольцо (%s)%s" % (ru, e)
            return "%s кольцо" % self.look['ring'][it.subtype]
        if it.kind == "wand":
            if it.subtype in self.idd['wand']:
                return "жезл (%s) [%d]" % (ru, it.charges)
            return "%s жезл" % self.look['wand'][it.subtype]
        if it.kind == "weapon":
            e = "%+d " % it.enchant if it.known and it.enchant else ""
            return "%s%s%s" % (e, it.subtype, cnt)
        if it.kind == "armor":
            e = "%+d " % it.enchant if it.known and it.enchant else ""
            return "%s%s" % (e, it.subtype)
        return ru

    def msg(self, text):
        self.messages.append(text)
        self.messages = self.messages[-40:]

    # ================================================ ЭКРАННАЯ КЛАВИАТУРА =
    def build_keyboard(self):
        """28 кнопок: 3x3 крестовина, 3x3 основные действия, 5x2 снаряжение."""
        L = self.L
        self.buttons = []
        gap = L.gap
        bh = L.btn_h

        def add(rect, label, cmd, arg=None, group='btn_nav', repeat=False):
            self.buttons.append({
                'rect': pygame.Rect(rect), 'label': label, 'cmd': cmd, 'arg': arg,
                'group': group, 'repeat': repeat, 'surf': None, 'surf_off': None,
                'id': len(self.buttons),
            })

        # --- крестовина движения (слева, 3x3) ---
        dpad = [
            ("1", (-1, -1)), ("2", (0, -1)), ("3", (1, -1)),
            ("4", (-1, 0)),  ("Ждать", (0, 0)),   ("6", (1, 0)),
            ("7", (-1, 1)),  ("8", (0, 1)),  ("9", (1, 1)),
        ]
        for i, (lab, d) in enumerate(dpad):
            r, c = divmod(i, 3)
            x = L.dpad_x + c * (L.dcw + gap)
            add((x, L.row_y(r), L.dcw, bh), lab, 'move', d, 'btn_move', repeat=(d != (0, 0)))

        # --- основные действия (справа, 3x3) ---
        right = [
            ("Вниз >", 'descend', 'btn_nav'), ("Вверх <", 'ascend', 'btn_nav'),
            ("Искать", 'search', 'btn_nav'),
            ("Инвент.", 'inventory', 'btn_nav'), ("Пить", 'quaff', 'btn_use'),
            ("Читать", 'read', 'btn_use'),
            ("Жезл", 'zap', 'btn_use'), ("Есть", 'eat', 'btn_use'),
            ("Справка", 'help', 'btn_nav'),
        ]
        for i, (lab, cmd, grp) in enumerate(right):
            r, c = divmod(i, 3)
            x = L.right_x + c * (L.rcw + gap)
            add((x, L.row_y(r), L.rcw, bh), lab, cmd, None, grp)

        # --- нижние два ряда (5x2) ---
        bottom = [
            ("Метнуть", 'throw', 'btn_gear'), ("Бросить", 'drop', 'btn_gear'),
            ("Оружие", 'wield', 'btn_gear'), ("Броня", 'wear', 'btn_gear'),
            ("Снять\nброню", 'takeoff', 'btn_gear'),
            ("Кольцо", 'putring', 'btn_gear'), ("Снять\nкольцо", 'remring', 'btn_gear'),
            ("Отмена", 'cancel', 'btn_warn'), ("Заново", 'restart', 'btn_danger'),
            ("Выход", 'quit', 'btn_danger'),
        ]
        for i, (lab, cmd, grp) in enumerate(bottom):
            r, c = divmod(i, 5)
            x = L.pad + c * (L.bcw + gap)
            add((x, L.row_y(3 + r), L.bcw, bh), lab, cmd, None, grp)

        # предрисованные подписи (чтобы не рендерить текст каждый кадр)
        for b in self.buttons:
            b['surf'] = self.render_label(b['label'], b['rect'], C['btn_text'])
            b['surf_off'] = self.render_label(b['label'], b['rect'], C['btn_text_off'])

    def render_label(self, label, rect, color):
        """Подпись кнопки: автоподбор размера, поддержка переноса '\\n'."""
        lines = label.split("\n")
        size = int(rect.h * (0.46 if len(lines) > 1 else 0.40))
        size = max(9, size)
        while size > 9:
            f = self.F(size)
            widest = max(f.size(t)[0] for t in lines)
            total = f.get_linesize() * len(lines)
            if widest <= rect.w - 8 and total <= rect.h - 6:
                break
            size -= 1
        f = self.F(size)
        surfs = [f.render(t, True, color) for t in lines]
        w = max(s.get_width() for s in surfs)
        h = sum(s.get_height() for s in surfs)
        out = pygame.Surface((w, h), pygame.SRCALPHA)
        y = 0
        for s in surfs:
            out.blit(s, ((w - s.get_width()) // 2, y))
            y += s.get_height()
        return out

    def button_enabled(self, b):
        cmd = b['cmd']
        if self.state in ('dead', 'won'):
            return cmd in ('restart', 'quit', 'help')
        if self.mode == 'select':
            return cmd == 'cancel'
        if self.mode == 'direction':
            return cmd in ('move', 'cancel')
        if self.mode in ('list', 'help'):
            return cmd in ('cancel', 'restart', 'quit')
        return True

    def button_at(self, pos):
        for b in self.buttons:
            if b['rect'].collidepoint(pos):
                return b
        return None

    # ===================================================== ВВОД / КОМАНДЫ =
    def command(self, cmd, arg=None):
        # --- экран смерти / победы ---
        if self.state in ('dead', 'won'):
            if cmd == 'restart':
                self.new_game()
            elif cmd == 'quit':
                self.quit()
            elif cmd == 'help':
                self.show_help()
            return

        # --- открытые окна ---
        if self.mode in ('list', 'help'):
            self.close_overlay()
            if cmd in ('restart', 'quit'):
                self.command(cmd)
            return
        if self.mode == 'select':
            if cmd == 'cancel':
                self.close_overlay()
            return
        if self.mode == 'direction':
            if cmd == 'cancel':
                self.close_overlay()
                self.msg("Отменено.")
            elif cmd == 'move':
                if arg == (0, 0):        # центр крестовины = отмена,
                    self.close_overlay() # чтобы не тратить заряд/снаряд впустую
                    self.msg("Отменено.")
                    return
                act = self.pending
                self.close_overlay()
                if act:
                    act(arg)
            return

        # --- обычная игра ---
        # Сон и паралич обездвиживают целиком: раньше спящий персонаж всё ещё
        # мог пить зелья, читать свитки и уходить по лестнице.
        if self.p.frozen > 0 and cmd in self.TURN_COMMANDS:
            self.msg("Ты не можешь пошевелиться!")
            self.end_turn()
            return
        if cmd == 'move':
            self.try_move_player(*arg)
        elif cmd == 'descend':
            self.descend()
        elif cmd == 'ascend':
            self.ascend()
        elif cmd == 'search':
            self.search()
        elif cmd == 'inventory':
            self.show_inventory()
        elif cmd == 'help':
            self.show_help()
        elif cmd == 'cancel':
            self.msg("Нечего отменять.")
        elif cmd == 'quaff':
            self.prompt_item("Выпить какое зелье?", lambda i: i.kind == "potion", self.quaff)
        elif cmd == 'read':
            self.prompt_item("Прочесть какой свиток?", lambda i: i.kind == "scroll", self.read)
        elif cmd == 'zap':
            self.prompt_item("Каким жезлом взмахнуть?", lambda i: i.kind == "wand", self.start_zap)
        elif cmd == 'eat':
            self.prompt_item("Что съесть?", lambda i: i.kind == "food", self.eat)
        elif cmd == 'throw':
            self.prompt_item("Что метнуть?",
                             lambda i: i.kind == "weapon" and is_throwable(i.subtype),
                             self.start_throw)
        elif cmd == 'drop':
            self.prompt_item("Что выбросить?", lambda i: True, self.drop)
        elif cmd == 'wield':
            self.prompt_item("Что взять в руки?", lambda i: i.kind == "weapon", self.wield)
        elif cmd == 'wear':
            self.prompt_item("Что надеть из брони?", lambda i: i.kind == "armor", self.wear)
        elif cmd == 'takeoff':
            self.take_off_armor()
        elif cmd == 'putring':
            self.prompt_item("Какое кольцо надеть?", lambda i: i.kind == "ring", self.put_ring)
        elif cmd == 'remring':
            self.remove_ring_cmd()
        elif cmd == 'restart':
            self.new_game()
        elif cmd == 'quit':
            self.quit()

    KEY_CMD = {
        '>': ('descend', None), '<': ('ascend', None), 's': ('search', None),
        'i': ('inventory', None), '?': ('help', None), '.': ('move', (0, 0)),
        'q': ('quaff', None), 'r': ('read', None), 'z': ('zap', None),
        'e': ('eat', None), 't': ('throw', None), 'd': ('drop', None),
        'w': ('wield', None), 'W': ('wear', None), 'T': ('takeoff', None),
        'P': ('putring', None), 'R': ('remring', None),
    }

    def handle_key(self, e):
        ch = e.unicode
        if e.key == pygame.K_ESCAPE:
            self.command('cancel')
            return
        if self.mode == 'select' and ch and len(ch) == 1:
            self.select_by_letter(ch)
            return
        dirs = {
            pygame.K_LEFT: (-1, 0), pygame.K_RIGHT: (1, 0),
            pygame.K_UP: (0, -1), pygame.K_DOWN: (0, 1),
            pygame.K_KP4: (-1, 0), pygame.K_KP6: (1, 0),
            pygame.K_KP8: (0, -1), pygame.K_KP2: (0, 1),
            pygame.K_KP7: (-1, -1), pygame.K_KP9: (1, -1),
            pygame.K_KP1: (-1, 1), pygame.K_KP3: (1, 1), pygame.K_KP5: (0, 0),
        }
        if e.key in dirs:
            self.command('move', dirs[e.key])
            return
        if ch in self.VI_KEYS:
            self.command('move', self.VI_KEYS[ch])
            return
        if ch in self.KEY_CMD:
            cmd, arg = self.KEY_CMD[ch]
            self.command(cmd, arg)
            return
        if self.state in ('dead', 'won') and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.new_game()

    def handle_mouse_down(self, pos):
        # 1) тап по строке списка выбора
        if self.overlay and self.overlay['kind'] == 'select':
            for row in self.overlay['rows']:
                if row['item'] is not None and row['rect'].collidepoint(pos):
                    self.choose_item(row['item'])
                    return
            if not self.overlay['rect'].collidepoint(pos):
                self.close_overlay()
                return
        # 2) тап по окну-списку/справке — закрыть
        elif self.overlay and self.overlay['kind'] in ('list', 'help'):
            b = self.button_at(pos)
            if b is None or not self.button_enabled(b):
                self.close_overlay()
                return
        # 3) кнопки клавиатуры
        b = self.button_at(pos)
        if b is None:
            return
        self.pressed_id = b['id']
        if not self.button_enabled(b):
            return
        self.command(b['cmd'], b['arg'])
        if b['repeat'] and self.state == 'play' and self.mode == 'play':
            self.hold_id = b['id']
            self.hold_start = pygame.time.get_ticks()
            self.hold_last = self.hold_start
            self.hold_hp = self.p.hp

    def handle_mouse_up(self):
        self.pressed_id = None
        self.hold_id = None

    def tick_hold(self):
        """Авто-повтор шага при удержании кнопки движения (с защитой)."""
        if self.hold_id is None:
            return
        if self.state != 'play' or self.mode != 'play':
            self.hold_id = None
            return
        if self.p.hp != self.hold_hp or self.adjacent_visible_monster():
            self.hold_id = None       # рядом враг или получен урон — стоп
            return
        now = pygame.time.get_ticks()
        if now - self.hold_start < HOLD_DELAY or now - self.hold_last < HOLD_REPEAT:
            return
        b = self.buttons[self.hold_id]
        self.hold_last = now
        self.command(b['cmd'], b['arg'])
        self.hold_hp = self.p.hp

    # ============================================================ ОКНА ====
    def close_overlay(self):
        self.overlay = None
        self.pending = None
        self.pending_action = None
        self.mode = 'play'

    def open_overlay(self, kind, title, rows, footer=None):
        """rows: список (текст, предмет|None[, цвет-образец]).
        Строки с предметом кликабельны, строки с цветом получают квадрат-образец."""
        L = self.L
        pad = L.pad
        n = len(rows) + (1 if footer else 0)
        w = int(L.w * 0.94)
        x = (L.w - w) // 2
        max_h = int((L.status_y - L.msg_h) * 0.96)
        lh = L.line_h + max(2, pad // 2)
        title_h = L.line_h + 2 * pad
        while title_h + n * lh + 2 * pad > max_h and lh > 12:
            lh -= 1
        h = min(max_h, title_h + n * lh + 2 * pad)
        y = L.map_y + max(0, (L.map_h - h) // 2)

        rect = pygame.Rect(x, y, w, h)
        out_rows = []
        ry = y + title_h
        for row in rows:
            text, item = row[0], row[1]
            swatch = row[2] if len(row) > 2 else None
            out_rows.append({'text': text, 'item': item, 'swatch': swatch,
                             'rect': pygame.Rect(x + pad, ry, w - 2 * pad, lh)})
            ry += lh
        if footer:
            out_rows.append({'text': footer, 'item': None, 'swatch': None,
                             'rect': pygame.Rect(x + pad, ry, w - 2 * pad, lh)})
        self.overlay = {'kind': kind, 'title': title, 'rows': out_rows,
                        'rect': rect, 'lh': lh, 'title_h': title_h}
        self.mode = 'select' if kind == 'select' else ('help' if kind == 'help' else 'list')

    def prompt_item(self, prompt, flt, action):
        items = [it for it in self.p.inventory if flt(it)]
        if not items:
            self.msg("У тебя нет ничего подходящего.")
            return
        rows = []
        for it in items:
            i = self.p.inventory.index(it)
            rows.append(("%s)  %s" % (chr(ord('a') + i), self.item_name(it)), it))
        self.pending_action = action
        self.open_overlay('select', prompt, rows, footer="Тап по строке — выбрать · Отмена")

    def choose_item(self, it):
        action = self.pending_action   # close_overlay сбрасывает поле — читаем до
        self.close_overlay()
        if action:
            action(it)

    def select_by_letter(self, ch):
        idx = ord(ch.lower()) - ord('a')
        if 0 <= idx < len(self.p.inventory):
            it = self.p.inventory[idx]
            for row in self.overlay['rows']:
                if row['item'] is it:
                    self.choose_item(it)
                    return
        self.msg("Неверный выбор.")

    def start_zap(self, wand):
        self.pending = lambda d: self.zap(wand, d)
        self.overlay = None
        self.mode = 'direction'
        self.msg("Куда взмахнуть жезлом? Выбери направление.")

    def start_throw(self, weapon):
        self.pending = lambda d: self.throw(weapon, d)
        self.mode = 'direction'
        self.overlay = None
        self.msg("Куда метнуть? Выбери направление.")

    def show_inventory(self):
        rows = []
        if not self.p.inventory:
            rows.append(("(пусто)", None))
        for i, it in enumerate(self.p.inventory):
            tag = ""
            if it is self.p.weapon:
                tag = "  [в руках]"
            elif it is self.p.armor:
                tag = "  [надета]"
            elif it in self.p.rings:
                tag = "  [на руке]"
            rows.append(("%s)  %s%s" % (chr(ord('a') + i), self.item_name(it), tag), None))
        self.open_overlay('list', "ИНВЕНТАРЬ", rows, footer="Тап по экрану — закрыть")

    def show_help(self):
        rows = [
            ("Цель: спуститься на 26 уровень, забрать", None),
            ("Амулет Йендора и подняться к выходу.", None),
            ("", None),
            ("Крестовина — шаг. Удержание — бег", None),
            ("(бег сам останавливается у врага).", None),
            ("«Ждать» — пропустить ход.", None),
            ("«Искать» — искать скрытые ловушки рядом.", None),
            ("«Вниз >» / «Вверх <» — лестница под ногами.", None),
            ("Пить / Читать / Жезл / Есть / Метнуть /", None),
            ("Бросить — выбор предмета тапом по списку.", None),
            ("Жезл и Метнуть затем просят направление.", None),
            ("AC: чем МЕНЬШЕ число, тем лучше броня.", None),
            ("", None),
            ("ЛЕГЕНДА ЦВЕТОВ:", None),
            ("ты", None, C['player']),
            ("лестница вниз", None, C['stairs_down']),
            ("лестница вверх", None, C['stairs_up']),
            ("дверь", None, C['door']),
            ("золото", None, C['gold']),
            ("еда", None, C['food']),
            ("зелье", None, C['potion']),
            ("свиток", None, C['scroll']),
            ("кольцо", None, C['ring']),
            ("жезл", None, C['wand']),
            ("оружие", None, C['weapon']),
            ("броня", None, C['armor']),
            ("АМУЛЕТ ЙЕНДОРА", None, C['amulet']),
            ("ловушка (найденная)", None, C['trap']),
            ("Прочие цвета — монстры.", None),
        ]
        self.open_overlay('help', "СПРАВКА", rows, footer="Тап по экрану — закрыть")

    # ======================================================== ОТРИСОВКА ===
    def wrap(self, text, font, width):
        words = text.split(' ')
        lines, cur = [], ""
        for wd in words:
            probe = wd if not cur else cur + " " + wd
            if font.size(probe)[0] <= width:
                cur = probe
            else:
                if cur:
                    lines.append(cur)
                cur = wd
        if cur:
            lines.append(cur)
        return lines

    def render(self):
        self.screen.fill(C['bg'])
        self.draw_messages()
        self.draw_map()
        self.draw_status()
        self.draw_keyboard()
        if self.overlay:
            self.draw_overlay()
        if self.state in ('dead', 'won'):
            self.draw_end()
        pygame.display.flip()

    def draw_messages(self):
        L = self.L
        pygame.draw.rect(self.screen, C['panel'], (0, 0, L.w, L.msg_h))
        f = self.F(int(L.line_h * 0.82))
        if self.mode == 'direction':
            text = "Выбери направление крестовиной (или Отмена)"
            color = C['warn']
        else:
            text = self.messages[-1] if self.messages else ""
            color = C['text']
        lines = self.wrap(text, f, L.w - 2 * L.pad)[:2]
        if len(lines) < 2 and len(self.messages) > 1 and self.mode != 'direction':
            prev = self.wrap(self.messages[-2], f, L.w - 2 * L.pad)[:1]
            if prev:
                self.screen.blit(f.render(prev[0], True, C['text_dim']), (L.pad, L.pad))
                y = L.pad + L.line_h
                self.screen.blit(f.render(lines[0] if lines else "", True, color), (L.pad, y))
                return
        y = L.pad
        for ln in lines:
            self.screen.blit(f.render(ln, True, color), (L.pad, y))
            y += L.line_h

    def draw_map(self):
        L = self.L
        lv = self.cur
        t = L.tile
        ox, oy = L.map_x, L.map_y
        # рамка вокруг игрового поля — визуально отделяет пиксели от интерфейса
        pygame.draw.rect(self.screen, C['line'],
                         (ox - 1, oy - 1, L.map_w + 2, L.map_h + 2), 1)
        rect = pygame.Rect(0, 0, t, t)
        blit = pygame.draw.rect
        for y in range(MAP_ROWS):
            row_e = lv.explored[y]
            row_v = self.visible[y]
            row_g = lv.grid[y]
            py = oy + y * t
            for x in range(MAP_COLS):
                if not row_e[x]:
                    continue
                vis = row_v[x]
                if row_g[x] == WALL:
                    col = C['wall_lit'] if vis else C['wall_dark']
                elif (x, y) in lv.doors:
                    col = C['door'] if vis else C['wall_dark']
                else:
                    col = C['floor_lit'] if vis else C['floor_dark']
                rect.update(ox + x * t, py, t, t)
                blit(self.screen, col, rect)

        def cell(cx, cy, color):
            rect.update(ox + cx * t, oy + cy * t, t, t)
            pygame.draw.rect(self.screen, color, rect)

        if lv.stairs_down and lv.explored[lv.stairs_down[1]][lv.stairs_down[0]]:
            cell(lv.stairs_down[0], lv.stairs_down[1], C['stairs_down'])
        if lv.stairs_up and lv.explored[lv.stairs_up[1]][lv.stairs_up[0]]:
            cell(lv.stairs_up[0], lv.stairs_up[1], C['stairs_up'])
        for tr in lv.traps:
            if tr['found'] and lv.explored[tr['y']][tr['x']]:
                cell(tr['x'], tr['y'], C['trap'])
        for gx, gy, _ in lv.gold:
            if lv.explored[gy][gx]:
                cell(gx, gy, self.hallu_color(C['gold']))
        for ix, iy, it in lv.items:
            if lv.explored[iy][ix] or self.p.detect_items > 0:
                key = 'amulet' if it.kind == 'amulet' else it.kind
                cell(ix, iy, self.hallu_color(C.get(key, C['text'])))
        for m in lv.monsters:
            sensed = self.p.detect_mon > 0
            if not sensed and not self.visible[m.y][m.x]:
                continue
            if "invisible" in m.flags and not self.can_see_invisible() and not sensed:
                continue
            cell(m.x, m.y, self.hallu_color(m.color))
        cell(self.p.x, self.p.y, C['player'])

    def hallu_color(self, base):
        if self.p.hallu > 0:
            r = random.Random("%d:%d,%d,%d" % (self.turn, base[0], base[1], base[2]))
            return (r.randint(60, 255), r.randint(60, 255), r.randint(60, 255))
        return base

    def draw_status(self):
        L = self.L
        p = self.p
        pygame.draw.rect(self.screen, C['panel'], (0, L.status_y, L.w, L.status_h))
        pygame.draw.line(self.screen, C['line'], (0, L.status_y), (L.w, L.status_y))
        f = self.F(int(L.line_h * 0.80))
        hp_col = C['good'] if p.hp > p.max_hp * 0.5 else (C['warn'] if p.hp > p.max_hp * 0.25 else C['bad'])
        hungry = p.food <= 300

        line1 = [("HP %d/%d" % (p.hp, p.max_hp), hp_col),
                 ("Сила %d/%d" % (self.eff_str(), p.max_strength), C['text']),
                 ("AC %d" % self.player_ac(), C['text']),
                 ("Ур.%d" % p.xp_level, C['text'])]
        line2 = [("Опыт %d" % p.xp, C['text_dim']),
                 ("Золото %d" % p.gold, C['gold']),
                 ("Глубина %d" % self.depth, C['text']),
                 (self.hunger_label(), C['warn'] if hungry else C['text_dim'])]

        y = L.status_y + L.pad
        for line in (line1, line2):
            x = L.pad
            for s, col in line:
                surf = f.render(s, True, col)
                self.screen.blit(surf, (x, y))
                x += surf.get_width() + max(8, L.pad * 2)
            y += L.line_h

        wname = self.item_name(p.weapon) if p.weapon else "—"
        aname = self.item_name(p.armor) if p.armor else "—"
        self.screen.blit(f.render("Оружие: %s | Броня: %s" % (wname, aname), True, C['text_dim']),
                         (L.pad, y))
        y += L.line_h
        fx = []
        if p.confused: fx.append("спутан")
        if p.blind: fx.append("слеп")
        if p.hasted: fx.append("ускорен")
        if p.frozen: fx.append("обездвижен")
        if p.held: fx.append("схвачен")
        if p.see_invis: fx.append("видит незримое")
        if p.levitate: fx.append("парит")
        if p.hallu: fx.append("галлюцинации")
        if p.detect_mon: fx.append("чует монстров")
        if p.detect_items: fx.append("чует предметы")
        rings = ", ".join(self.item_name(r) for r in p.rings) if p.rings else "—"
        tail = "Кольца: %s | Эффекты: %s" % (rings, ", ".join(fx) if fx else "—")
        tail = self.wrap(tail, f, L.w - 2 * L.pad)[0]
        self.screen.blit(f.render(tail, True, C['text_dim']), (L.pad, y))

    def hunger_label(self):
        f = self.p.food
        if f > 300: return "Сыт"
        if f > 150: return "Голоден"
        if f > 50:  return "Слаб"
        if f > 0:   return "Теряет силы"
        return "ГОЛОДАЕТ"

    def draw_keyboard(self):
        L = self.L
        pygame.draw.rect(self.screen, C['panel2'], (0, L.kb_y, L.w, L.kb_h))
        pygame.draw.line(self.screen, C['line'], (0, L.kb_y), (L.w, L.kb_y))
        for b in self.buttons:
            on = self.button_enabled(b)
            r = b['rect']
            if not on:
                base = C['btn_off']
            elif b['id'] == self.pressed_id:
                base = C['btn_press']
            else:
                base = C[b['group']]
            pygame.draw.rect(self.screen, base, r, border_radius=max(3, L.pad))
            pygame.draw.rect(self.screen, C['btn_edge'] if on else C['line'], r, 1,
                             border_radius=max(3, L.pad))
            s = b['surf'] if on else b['surf_off']
            self.screen.blit(s, (r.x + (r.w - s.get_width()) // 2,
                                 r.y + (r.h - s.get_height()) // 2))

    def draw_overlay(self):
        L = self.L
        ov = self.overlay
        r = ov['rect']
        shade = pygame.Surface((L.w, L.status_y), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        self.screen.blit(shade, (0, 0))
        pygame.draw.rect(self.screen, (26, 26, 34), r, border_radius=max(4, L.pad))
        pygame.draw.rect(self.screen, C['btn_edge'], r, 1, border_radius=max(4, L.pad))
        ft = self.F(int(L.line_h * 0.88))
        self.screen.blit(ft.render(ov['title'], True, C['text']), (r.x + L.pad, r.y + L.pad))
        fr = self.F(int(ov['lh'] * 0.78))
        for row in ov['rows']:
            if row['rect'].bottom > r.bottom - L.pad:
                break
            if row['item'] is not None:
                pygame.draw.rect(self.screen, (38, 38, 50), row['rect'],
                                 border_radius=max(2, L.pad // 2))
            tx = row['rect'].x + L.pad
            if row['swatch'] is not None:
                sw = int(row['rect'].h * 0.62)
                pygame.draw.rect(self.screen, row['swatch'],
                                 (tx, row['rect'].y + (row['rect'].h - sw) // 2, sw, sw))
                tx += sw + L.pad
            col = C['text'] if row['item'] is not None else C['text_dim']
            avail = row['rect'].right - tx - L.pad
            txt = row['text']
            if txt and fr.size(txt)[0] > avail:      # не обрезаем — ужимаем шрифт
                f2 = fr
                for size in range(int(ov['lh'] * 0.78), 8, -1):
                    f2 = self.F(size)
                    if f2.size(txt)[0] <= avail:
                        break
            else:
                f2 = fr
            if txt:
                self.screen.blit(f2.render(txt, True, col),
                                 (tx, row['rect'].y + max(1, (row['rect'].h - f2.get_height()) // 2)))

    def draw_end(self):
        L = self.L
        shade = pygame.Surface((L.w, L.status_y), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 185))
        self.screen.blit(shade, (0, 0))
        if self.state == 'won':
            title, col = "ПОБЕДА!", C['amulet']
            sub = "Ты вынес Амулет Йендора"
        else:
            title, col = "ТЫ ПОГИБ", C['bad']
            sub = "Причина: %s" % (self.death_cause or "неизвестна")
        fb = self.F(int(L.w * 0.075))
        fs = self.F(int(L.w * 0.038))
        cx = L.w // 2
        cy = L.map_y + L.map_h // 2
        t = fb.render(title, True, col)
        self.screen.blit(t, t.get_rect(center=(cx, cy - int(L.line_h * 2.2))))
        for i, line in enumerate((sub,
                                  "Глубина %d · Золото %d · Опыт %d" % (self.depth, self.p.gold, self.p.xp),
                                  "«Заново» — новая партия, «Выход» — закрыть")):
            s = fs.render(line, True, C['text'] if i < 2 else C['text_dim'])
            self.screen.blit(s, s.get_rect(center=(cx, cy + int(L.line_h * (0.4 + i * 1.3)))))

    # ============================================================ ЦИКЛ ====
    def quit(self):
        pygame.quit()
        sys.exit(0)

    def run(self):
        # Игра пошаговая: сама по себе картинка не меняется, поэтому кадр
        # перерисовывается только после события или хода. На телефоне это
        # снимает лишнюю нагрузку на CPU и экономит батарею.
        self.dirty = True
        while True:
            if self.hold_id is None and not self.dirty:
                # Пока нечего перерисовывать и никто не удерживает кнопку —
                # блокируемся на событии вместо холостых 30 кадров в секунду.
                events = [pygame.event.wait()]
                events.extend(pygame.event.get())
            else:
                events = pygame.event.get()
            if events:
                self.dirty = True
            for e in events:
                if e.type == pygame.QUIT:
                    self.quit()
                elif e.type == pygame.KEYDOWN:
                    self.handle_key(e)
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    self.handle_mouse_down(e.pos)
                elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                    self.handle_mouse_up()
            before = (self.p.x, self.p.y, self.turn)
            self.tick_hold()
            if (self.p.x, self.p.y, self.turn) != before:
                self.dirty = True
            if self.dirty:
                self.render()
                self.dirty = False
            self.clock.tick(FPS)


MIN_WINDOW = (240, 320)


def parse_size(text):
    """'1080x2400' -> (1080, 2400). Пусто -> None (размер по экрану)."""
    if not text:
        return None
    for sep in ("x", "X", "*", ","):
        if sep in text:
            w, _, h = text.partition(sep)
            size = (int(w), int(h))
            if size[0] < MIN_WINDOW[0] or size[1] < MIN_WINDOW[1]:
                raise ValueError("окно меньше %dx%d не вмещает интерфейс" % MIN_WINDOW)
            return size
    raise ValueError("размер задаётся как ШИРИНАxВЫСОТА, например 1080x2400")


def strip_launcher_noise(argv):
    """Убрать из argv то, что подложил лаунчер, а не игрок.

    Pydroid 3 (и не он один) кладёт в sys.argv всю командную строку целиком:
    ['python3', '/storage/.../PixRogue.py']. Для argparse это неизвестные
    аргументы — и игра падала с «unrecognized arguments» ещё до окна.
    Путь к интерпретатору и к самому скрипту аргументами игры не являются
    никогда, поэтому молча их отбрасываем.
    """
    script = os.path.basename(getattr(sys, "argv", [""])[0] or "")
    out = []
    for a in argv:
        base = os.path.basename(a).lower()
        if base.startswith("python") or base.endswith(".py"):
            continue
        if script and base == script.lower():
            continue
        out.append(a)
    return out


def build_parser():
    ap = argparse.ArgumentParser(
        prog="PixRogue",
        description="PixelRogue — классический Rogue в пиксельном стиле.")
    ap.add_argument("--seed", type=int, default=None,
                    help="зерно генератора: с одним зерном подземелье повторяется "
                         "в точности (нужно для отчётов об ошибках и тестов)")
    ap.add_argument("--size", default=None, metavar="ШИРИНАxВЫСОТА",
                    help="размер окна, например 1080x2400; по умолчанию — по экрану")
    return ap


def parse_args(argv):
    """Разбор аргументов, который не может помешать игре запуститься.

    Что бы ни лежало в командной строке, на выходе всегда рабочий набор
    настроек: непонятные аргументы пропускаются, испорченные значения
    заменяются значениями по умолчанию. Единственный штатный выход —
    явный --help.
    """
    ap = build_parser()
    try:
        args, unknown = ap.parse_known_args(strip_launcher_noise(argv))
    except SystemExit as exc:
        if exc.code in (0, None):        # это --help, так и задумано
            raise
        sys.stderr.write("PixRogue: аргументы не разобраны, "
                         "запускаюсь со значениями по умолчанию.\n")
        return ap.parse_args([])
    if unknown:
        sys.stderr.write("PixRogue: аргументы пропущены: %s\n" % " ".join(unknown))
    return args


def main(argv=None):
    args = parse_args(argv if argv is not None else list(getattr(sys, "argv", [])[1:]))
    random.seed(args.seed)               # None -> энтропия системы
    try:
        size = parse_size(args.size)
    except ValueError as exc:
        sys.stderr.write("PixRogue: --size %s — %s; беру размер по экрану.\n"
                         % (args.size, exc))
        size = None
    RogueGame(size=size).run()


if __name__ == "__main__":
    main()
