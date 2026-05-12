try:
    import curses
except ImportError:
    import windows_curses as curses

import time
import random
import math
import sys
import json
import os

from config import (
    FPS, FRAME_TIME, MIN_COLS, MIN_ROWS,
    ENEMY_SPAWN_INTERVAL, ENEMY_SPAWN_COUNT, ENEMY_SPAWN_SCALE_INTERVAL,
    ENEMY_HP_SCALE, ENEMY_SPEED_SCALE, MAX_ENEMIES, ENEMY_TYPES,
    COLOR_PAIRS, HP_BAR_WIDTH, XP_BAR_WIDTH,
    SIMPLE_COLORS, SIMPLE_ENEMY_COLOR, SIMPLE_PLAYER_COLOR,
    SIMPLE_WEAPON_COLOR, SIMPLE_PICKUP_COLOR,
    COLORBLIND_MODE, COLORBLIND_REMAP,
    MAGNET_DROP_RATE, BIG_XP_DROP_RATE, BIG_XP_MULTIPLIER,
    BOSS_DEFS, MINIBOSS_SPAWN_FRAME, BOSS_SPAWN_FRAME,
)
from entities import Player, Enemy, XPGem, Bullet, WhipSlash, AoeBlast, Boss
from weapons import WeaponInstance, OrbMarker
from upgrades import get_upgrade_choices

# Windows: poll real-time key state so movement is instant with no sliding.
if sys.platform == 'win32':
    import ctypes
    _user32 = ctypes.windll.user32
    def _poll_move():
        dx = dy = 0
        if _user32.GetAsyncKeyState(0x57) & 0x8000 or _user32.GetAsyncKeyState(0x26) & 0x8000: dy = -1
        if _user32.GetAsyncKeyState(0x53) & 0x8000 or _user32.GetAsyncKeyState(0x28) & 0x8000: dy =  1
        if _user32.GetAsyncKeyState(0x41) & 0x8000 or _user32.GetAsyncKeyState(0x25) & 0x8000: dx = -1
        if _user32.GetAsyncKeyState(0x44) & 0x8000 or _user32.GetAsyncKeyState(0x27) & 0x8000: dx =  1
        return dx, dy
else:
    _poll_move = None


# ── Score persistence ─────────────────────────────────────────────────────────

_SCORES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scores.json')

def _load_best_time():
    try:
        with open(_SCORES_FILE) as f:
            return int(json.load(f).get('best_time', 0))
    except (OSError, ValueError, json.JSONDecodeError):
        return 0

def _save_best_time(seconds):
    try:
        with open(_SCORES_FILE, 'w') as f:
            json.dump({'best_time': seconds}, f)
    except OSError:
        pass


# ── Color helpers ─────────────────────────────────────────────────────────────

# Mutable runtime state so the start screen can toggle modes without restarting.
_color_state = {
    'simple':     SIMPLE_COLORS,
    'colorblind': COLORBLIND_MODE,
}

_ROLE_COLORS = {
    'enemy':  lambda: SIMPLE_ENEMY_COLOR,
    'player': lambda: SIMPLE_PLAYER_COLOR,
    'weapon': lambda: SIMPLE_WEAPON_COLOR,
    'pickup': lambda: SIMPLE_PICKUP_COLOR,
}

def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(COLOR_PAIRS['white'],   curses.COLOR_WHITE,   -1)
    curses.init_pair(COLOR_PAIRS['red'],     curses.COLOR_RED,     -1)
    curses.init_pair(COLOR_PAIRS['green'],   curses.COLOR_GREEN,   -1)
    curses.init_pair(COLOR_PAIRS['yellow'],  curses.COLOR_YELLOW,  -1)
    curses.init_pair(COLOR_PAIRS['cyan'],    curses.COLOR_CYAN,    -1)
    curses.init_pair(COLOR_PAIRS['magenta'], curses.COLOR_MAGENTA, -1)
    curses.init_pair(COLOR_PAIRS['blue'],    curses.COLOR_BLUE,    -1)

def cp(name, role=None):
    if role is not None and _color_state['simple']:
        name = _ROLE_COLORS[role]()
    if _color_state['colorblind']:
        name = COLORBLIND_REMAP.get(name, name)
    return curses.color_pair(COLOR_PAIRS.get(name, COLOR_PAIRS['white']))


# ── Safe draw helpers ─────────────────────────────────────────────────────────

def safe_addch(win, y, x, ch, attr=0):
    rows, cols = win.getmaxyx()
    if 0 <= y < rows and 0 <= x < cols:
        try:
            win.addch(y, x, ch, attr)
        except curses.error:
            pass

def safe_addstr(win, y, x, s, attr=0):
    rows, cols = win.getmaxyx()
    if y < 0 or y >= rows or x >= cols:
        return
    if x < 0:
        s = s[-x:]
        x = 0
    s = s[:cols - x]
    if s:
        try:
            win.addstr(y, x, s, attr)
        except curses.error:
            pass


# ── Enemy spawning ─────────────────────────────────────────────────────────────

def spawn_enemies(player, enemies, cols, rows, ui_rows, difficulty):
    weights = [ENEMY_TYPES[k]['weight'] for k in ENEMY_TYPES]
    etype_keys = list(ENEMY_TYPES.keys())
    for _ in range(ENEMY_SPAWN_COUNT):
        if len(enemies) >= MAX_ENEMIES:
            break
        side = random.randint(0, 3)
        if side == 0:
            x, y = random.randint(0, cols - 1), ui_rows
        elif side == 1:
            x, y = random.randint(0, cols - 1), rows - 1
        elif side == 2:
            x, y = 0, random.randint(ui_rows, rows - 1)
        else:
            x, y = cols - 1, random.randint(ui_rows, rows - 1)
        etype = random.choices(etype_keys, weights=weights)[0]
        e = Enemy(x, y, etype)
        e.scale(ENEMY_HP_SCALE ** difficulty, ENEMY_SPEED_SCALE ** difficulty)
        enemies.append(e)


def spawn_boss(btype, cols, rows, ui_rows):
    defn = BOSS_DEFS[btype]
    size = defn['size']
    side = random.randint(0, 3)
    if side == 0:
        x, y = random.randint(0, max(0, cols - size)), ui_rows - size
    elif side == 1:
        x, y = random.randint(0, max(0, cols - size)), rows
    elif side == 2:
        x, y = -size, random.randint(ui_rows, max(ui_rows, rows - size))
    else:
        x, y = cols, random.randint(ui_rows, max(ui_rows, rows - size))
    return Boss(x, y, btype, defn)


# ── Collision ─────────────────────────────────────────────────────────────────

def resolve_collisions(player, enemies, bullets, slashes, blasts, orbs, gems, weapon_instances):
    enemy_map = {}
    for e in enemies:
        enemy_map.setdefault((e.x, e.y), []).append(e)

    killed = []

    for b in bullets:
        if not b.active:
            continue
        gx, gy = b.grid_pos()
        for e in enemy_map.get((gx, gy), []):
            if not e.alive:
                continue
            e.take_damage(b.damage)
            if not e.alive:
                killed.append(e)
            if getattr(b, 'is_aoe', False):
                blasts.append(AoeBlast(gx, gy, b.aoe_radius, b.damage, '*', b.aoe_color))
            b.active = False
            break

    for sl in slashes:
        if not sl.active:
            continue
        slash_cells = set(sl.cells())
        for e in enemies:
            if not e.alive or e.id in sl.hit_ids:
                continue
            if (e.x, e.y) in slash_cells:
                sl.hit_ids.add(e.id)
                e.take_damage(sl.damage)
                if not e.alive:
                    killed.append(e)

    for bl in blasts:
        if not bl.active:
            continue
        blast_cells = set(bl.cells())
        for e in enemies:
            if not e.alive or e.id in bl.hit_ids:
                continue
            if (e.x, e.y) in blast_cells:
                bl.hit_ids.add(e.id)
                e.take_damage(bl.damage)
                if not e.alive:
                    killed.append(e)

    for orb in orbs:
        for e in enemies:
            if e.alive and e.x == orb.x and e.y == orb.y:
                e.take_damage(orb.damage)
                if not e.alive:
                    killed.append(e)

    px, py = int(round(player.x)), int(round(player.y))
    for e in enemies:
        if e.alive and e.x == px and e.y == py:
            player.take_damage(e.damage)

    # Use a radius that covers the full stride so gems aren't skipped at speed > 1.
    pickup_radius = max(1.5, player.speed)
    collected = [g for g in gems if math.hypot(g.x - player.x, g.y - player.y) < pickup_radius]
    for g in collected:
        player.gain_xp(g.value)

    return killed, collected


# ── Rendering ─────────────────────────────────────────────────────────────────

UI_ROWS = 2


def draw_hud(stdscr, player, frame, cols):
    _, cols_win = stdscr.getmaxyx()
    seconds = frame // FPS
    minutes, secs = seconds // 60, seconds % 60

    hp_pct = max(0.0, player.hp / player.max_hp)
    xp_floor = player.xp_level_floor()
    xp_next  = player.xp_for_next()
    xp_span  = max(1, xp_next - xp_floor)
    xp_pct   = min(1.0, (player.xp - xp_floor) / xp_span)

    safe_addstr(stdscr, 0, 0, '╔' + '═' * (cols_win - 2) + '╗', cp('white'))

    hp_filled = int(HP_BAR_WIDTH * hp_pct)
    hp_bar = '█' * hp_filled + '░' * (HP_BAR_WIDTH - hp_filled)
    xp_filled = int(XP_BAR_WIDTH * xp_pct)
    xp_bar = '█' * xp_filled + '░' * (XP_BAR_WIDTH - xp_filled)

    hud = (f'║ HP[{hp_bar}]{player.hp:>4}/{player.max_hp:<4}'
           f' XP[{xp_bar}] Lv{player.level}'
           f' {minutes:02d}:{secs:02d}'
           f' Kills:{player.kills}')
    inner = cols_win - 2
    hud_content = hud[2:2 + inner]
    hud_line = '║' + hud_content.ljust(inner)[:inner] + '║'
    safe_addstr(stdscr, 1, 0, hud_line, cp('white'))

    bar_start_hp = 6
    safe_addstr(stdscr, 1, bar_start_hp, hp_bar[:hp_filled], cp('green', 'player') | curses.A_BOLD)
    safe_addstr(stdscr, 1, bar_start_hp + hp_filled, hp_bar[hp_filled:], cp('red'))

    xp_offset = bar_start_hp + HP_BAR_WIDTH + 2 + 9
    safe_addstr(stdscr, 1, xp_offset, xp_bar[:xp_filled], cp('yellow') | curses.A_BOLD)
    safe_addstr(stdscr, 1, xp_offset + xp_filled, xp_bar[xp_filled:], cp('white'))


def _bullet_char(b):
    adx, ady = abs(b.dx), abs(b.dy)
    if adx >= ady * 2: return '-'
    if ady >= adx * 2: return '|'
    return '/' if b.dx * b.dy < 0 else '\\'


def draw_game(stdscr, player, enemies, bullets, slashes, blasts, orbs, gems, bosses, enemy_bullets, cols, rows):
    for e in enemies:
        ex, ey = int(e.x), int(e.y)
        if UI_ROWS <= ey < rows and 0 <= ex < cols:
            safe_addch(stdscr, ey, ex, e.char, cp(e.color, 'enemy') | curses.A_BOLD)

    for g in gems:
        if UI_ROWS <= g.y < rows and 0 <= g.x < cols:
            attr = cp(g.color, 'pickup')
            if g.gem_type != 'normal':
                attr |= curses.A_BOLD
            safe_addch(stdscr, g.y, g.x, g.char, attr)

    for sl in slashes:
        if sl.active:
            for cx, cy in sl.cells():
                if UI_ROWS <= cy < rows and 0 <= cx < cols:
                    safe_addch(stdscr, cy, cx, sl.char, cp(sl.color, 'weapon') | curses.A_BOLD)

    for bl in blasts:
        if bl.active:
            for cx, cy in bl.cells():
                if UI_ROWS <= cy < rows and 0 <= cx < cols:
                    safe_addch(stdscr, cy, cx, bl.char, cp(bl.color, 'weapon') | curses.A_BOLD)

    for b in bullets:
        if b.active:
            bx, by = b.grid_pos()
            if UI_ROWS <= by < rows and 0 <= bx < cols:
                safe_addch(stdscr, by, bx, _bullet_char(b), cp(b.color, 'weapon') | curses.A_BOLD)

    for orb in orbs:
        if UI_ROWS <= orb.y < rows and 0 <= orb.x < cols:
            safe_addch(stdscr, orb.y, orb.x, orb.char, cp('cyan', 'weapon') | curses.A_BOLD)

    for boss in bosses:
        attr = cp(boss.color, 'enemy') | curses.A_BOLD
        for bx, by in boss.cells():
            if UI_ROWS <= by < rows and 0 <= bx < cols:
                safe_addch(stdscr, by, bx, boss.char, attr)

    for eb in enemy_bullets:
        if eb.active:
            ebx, eby = eb.grid_pos()
            if UI_ROWS <= eby < rows and 0 <= ebx < cols:
                safe_addch(stdscr, eby, ebx, eb.char, cp(eb.color, 'enemy') | curses.A_BOLD)

    py, px = int(round(player.y)), int(round(player.x))
    if player.invuln == 0 or player.invuln % 3 != 0:
        safe_addch(stdscr, py, px, player.char, cp('green', 'player') | curses.A_BOLD)


def draw_levelup(stdscr, choices, selected, cols, rows):
    bw = 50
    bh = len(choices) * 3 + 6
    bx = (cols - bw) // 2
    by = (rows - bh) // 2

    def bl(y, s, attr=0):
        safe_addstr(stdscr, by + y, bx, s, attr)

    bl(0, '╔' + '═' * (bw - 2) + '╗', cp('yellow') | curses.A_BOLD)
    bl(1, '║' + ' LEVEL UP! Choose an upgrade '.center(bw - 2) + '║', cp('yellow') | curses.A_BOLD)
    bl(2, '╠' + '═' * (bw - 2) + '╣', cp('yellow') | curses.A_BOLD)

    for i, upg in enumerate(choices):
        row = 3 + i * 3
        marker = '► ' if i == selected else '  '
        attr = (cp('cyan') | curses.A_BOLD) if i == selected else cp('white')
        safe_addstr(stdscr, by + row,     bx, '║' + (' ' * (bw - 2)) + '║', cp('yellow') | curses.A_BOLD)
        safe_addstr(stdscr, by + row,     bx + 2, f"{marker}{upg['name']}: {upg['desc']}"[:bw - 4], attr)
        safe_addstr(stdscr, by + row + 1, bx, '║' + (' ' * (bw - 2)) + '║', cp('yellow') | curses.A_BOLD)

    footer_row = 3 + len(choices) * 3
    bl(footer_row,     '╠' + '═' * (bw - 2) + '╣', cp('yellow') | curses.A_BOLD)
    bl(footer_row + 1, '║' + ' ↑↓/WS to choose  ENTER to pick '.center(bw - 2) + '║', cp('white'))
    bl(footer_row + 2, '╚' + '═' * (bw - 2) + '╝', cp('yellow') | curses.A_BOLD)


def draw_pause(stdscr, cols, rows):
    bw, bh = 30, 6
    bx = (cols - bw) // 2
    by = (rows - bh) // 2

    def bl(y, s, attr=0):
        safe_addstr(stdscr, by + y, bx, s, attr)

    bl(0, '╔' + '═' * (bw - 2) + '╗', cp('cyan') | curses.A_BOLD)
    bl(1, '║' + ' PAUSED '.center(bw - 2) + '║',   cp('cyan') | curses.A_BOLD)
    bl(2, '╠' + '═' * (bw - 2) + '╣',              cp('cyan') | curses.A_BOLD)
    bl(3, '║' + '  P  ·  Resume'.ljust(bw - 2) + '║',       cp('white'))
    bl(4, '║' + '  Q  ·  Quit to menu'.ljust(bw - 2) + '║', cp('white'))
    bl(5, '╚' + '═' * (bw - 2) + '╝',              cp('cyan') | curses.A_BOLD)


def draw_gameover(stdscr, player, frame, cols, rows):
    bw = 42
    bx = (cols - bw) // 2
    by = (rows - 12) // 2
    seconds = frame // FPS

    def bl(y, s, attr=0):
        safe_addstr(stdscr, by + y, bx, s, attr)

    bl(0,  '╔' + '═' * (bw - 2) + '╗', cp('red') | curses.A_BOLD)
    bl(1,  '║' + ' GAME OVER '.center(bw - 2) + '║', cp('red') | curses.A_BOLD)
    bl(2,  '╠' + '═' * (bw - 2) + '╣', cp('red') | curses.A_BOLD)
    bl(3,  '║' + f'  Survived: {seconds // 60:02d}:{seconds % 60:02d}'.ljust(bw - 2) + '║', cp('white'))
    bl(4,  '║' + f'  Level:    {player.level}'.ljust(bw - 2) + '║', cp('white'))
    bl(5,  '║' + f'  Kills:    {player.kills}'.ljust(bw - 2) + '║', cp('white'))
    bl(6,  '║' + f'  Max HP:   {player.max_hp}'.ljust(bw - 2) + '║', cp('white'))
    bl(7,  '║' + f'  Armor:    {player.armor}'.ljust(bw - 2) + '║', cp('white'))
    bl(8,  '╠' + '═' * (bw - 2) + '╣', cp('red') | curses.A_BOLD)
    bl(9,  '║' + ' R  ·  Restart   M  ·  Menu   Q  ·  Quit'.ljust(bw - 2) + '║', cp('yellow'))
    bl(10, '╚' + '═' * (bw - 2) + '╝', cp('red') | curses.A_BOLD)


def show_start_screen(stdscr, best_time):
    stdscr.timeout(-1)

    _TITLE = (
        " @@@@@@    @@@@@@    @@@@@@@  @@@  @@@      @@@@@@   @@@  @@@  @@@@@@@   @@@  @@@  @@@   @@@@@@   @@@@@@@    @@@@@@",
        "@@@@@@@@  @@@@@@@   @@@@@@@@  @@@  @@@     @@@@@@@   @@@  @@@  @@@@@@@@  @@@  @@@  @@@  @@@@@@@@  @@@@@@@@  @@@@@@@",
        "@@!  @@@  !@@       !@@       @@!  @@!     !@@       @@!  @@@  @@!  @@@  @@!  @@@  @@!  @@!  @@@  @@!  @@@  !@@",
        "!@!  @!@  !@!       !@!       !@!  !@!     !@!       !@!  @!@  !@!  @!@  !@!  @!@  !@!  !@!  @!@  !@!  @!@  !@!",
        "@!@!@!@!  !!@@!!    !@!       !!@  !!@     !!@@!!    @!@  !@!  @!@!!@!   @!@  !@!  !!@  @!@  !@!  @!@!!@!   !!@@!!",
        "!!!@!!!!   !!@!!!   !!!       !!!  !!!      !!@!!!   !@!  !!!  !!@!@!    !@!  !!!  !!!  !@!  !!!  !!@!@!     !!@!!!",
        "!!:  !!!       !:!  :!!       !!:  !!:          !:!  !!:  !!!  !!: :!!   :!:  !!:  !!:  !!:  !!!  !!: :!!        !:!",
        ":!:  !:!      !:!   :!:       :!:  :!:         !:!   :!:  !:!  :!:  !:!   ::!!:!   :!:  :!:  !:!  :!:  !:!      !:!",
        "::   :::  :::: ::    ::: :::   ::   ::     :::: ::   ::::: ::  ::   :::    ::::     ::  ::::: ::  ::   :::  :::: ::",
        " :   : :  :: : :     :: :: :  :    :       :: : :     : :  :    :   : :     :      :     : :  :    :   : :  :: : :",
    )

    _CTRL = (
        '┌─ Controls ──────────┐',
        '│  WASD/Arrows  Move  │',
        '│  ENTER      Confirm │',
        '│  P          Pause   │',
        '│  R          Restart │',
        '│  Q          Quit    │',
        '└──────────────────────┘',
    )
    _CW = len(_CTRL[0])

    def _draw():
        rows, cols = stdscr.getmaxyx()
        stdscr.erase()

        sc_on = _color_state['simple']
        cb_on = _color_state['colorblind']
        bt_str = f'{best_time // 60:02d}:{best_time % 60:02d}' if best_time > 0 else '--:--'

        ts = max(1, (rows - 16) // 2)
        art_w = max(len(l) for l in _TITLE)
        for i, line in enumerate(_TITLE):
            x = max(0, (cols - art_w) // 2)
            safe_addstr(stdscr, ts + i, x, line, cp('cyan') | curses.A_BOLD)

        iy = ts + 11
        safe_addstr(stdscr, iy,     2, f'  Best Run:  {bt_str}', cp('yellow'))
        safe_addstr(stdscr, iy + 1, 2,
                    f'  [S] Simple Colors:   {"ON " if sc_on else "OFF"}',
                    (cp('cyan') | curses.A_BOLD) if sc_on else cp('white'))
        safe_addstr(stdscr, iy + 2, 2,
                    f'  [C] Colorblind Mode: {"ON  (red→blue, green→yellow)" if cb_on else "OFF"}',
                    (cp('cyan') | curses.A_BOLD) if cb_on else cp('white'))
        safe_addstr(stdscr, iy + 4, 2,
                    '  ENTER / SPACE  ·  Play          Q  ·  Quit',
                    cp('white'))

        cx = max(0, cols - _CW - 1)
        cy = max(0, rows - len(_CTRL) - 1)
        for i, line in enumerate(_CTRL):
            safe_addstr(stdscr, cy + i, cx, line, cp('white'))

        stdscr.refresh()

    result = 'play'
    _draw()
    while True:
        k = stdscr.getch()
        if k in (ord('\n'), 10, 13, curses.KEY_ENTER, ord(' ')):
            break
        elif k == ord('q'):
            result = 'quit'
            break
        elif k == ord('s'):
            _color_state['simple'] = not _color_state['simple']
            _draw()
        elif k == ord('c'):
            _color_state['colorblind'] = not _color_state['colorblind']
            _draw()

    stdscr.timeout(0)
    return result


# ── Main game logic ───────────────────────────────────────────────────────────

def game_loop(stdscr):
    stdscr.timeout(0)  # guarantee non-blocking getch regardless of prior screen state
    rows, cols = stdscr.getmaxyx()

    if cols < MIN_COLS or rows < MIN_ROWS:
        stdscr.clear()
        safe_addstr(stdscr, 0, 0, f'Terminal too small! Need {MIN_COLS}x{MIN_ROWS}, got {cols}x{rows}')
        stdscr.refresh()
        time.sleep(2)
        return 'menu', 0

    player = Player(cols // 2, rows // 2)
    weapon_instances = [WeaponInstance('knife')]

    enemies, bullets, slashes, blasts, orbs, gems = [], [], [], [], [], []
    bosses, enemy_bullets = [], []
    miniboss_spawned = False
    boss_spawned = False

    frame = 0
    spawn_timer = 0
    difficulty = 0
    difficulty_timer = 0

    state = 'playing'   # 'playing' | 'levelup' | 'paused' | 'gameover'
    upgrade_choices = []
    upgrade_selected = 0

    last_time = time.monotonic()
    held = {'dx': 0, 'dy': 0, 'dx_ttl': 0, 'dy_ttl': 0}

    while True:
        now = time.monotonic()
        elapsed = now - last_time
        if elapsed < FRAME_TIME:
            time.sleep(FRAME_TIME - elapsed)
            continue
        last_time = now

        rows, cols = stdscr.getmaxyx()

        # ── Input ────────────────────────────────────────────────────────────
        this_dx, this_dy, action = None, None, None
        k = stdscr.getch()
        while k != -1:
            if k in (ord('w'), curses.KEY_UP):      this_dy = -1
            elif k in (ord('s'), curses.KEY_DOWN):   this_dy =  1
            if k in (ord('a'), curses.KEY_LEFT):     this_dx = -1
            elif k in (ord('d'), curses.KEY_RIGHT):  this_dx =  1
            if k in (ord('\n'), 10, 13, curses.KEY_ENTER): action = 'enter'
            elif k == ord('p'):  action = 'pause'
            elif k == ord('q'):  action = 'quit'
            elif k == ord('r'):  action = 'restart'
            elif k == ord('m'):  action = 'menu'
            k = stdscr.getch()

        # Movement: Windows uses hardware polling; others use TTL.
        if _poll_move is not None:
            move_dx, move_dy = _poll_move()
        else:
            if this_dx is not None:
                held['dx'], held['dx_ttl'] = this_dx, 6
            elif held['dx_ttl'] > 0:
                held['dx_ttl'] -= 1
                if held['dx_ttl'] == 0: held['dx'] = 0
            if this_dy is not None:
                held['dy'], held['dy_ttl'] = this_dy, 6
            elif held['dy_ttl'] > 0:
                held['dy_ttl'] -= 1
                if held['dy_ttl'] == 0: held['dy'] = 0
            move_dx, move_dy = held['dx'], held['dy']

        # ── State machine ─────────────────────────────────────────────────────
        if state == 'playing':
            if action == 'quit':
                return 'quit', frame
            if action == 'pause':
                state = 'paused'
            else:
                player.move(move_dx, move_dy, cols, rows, UI_ROWS)
                player.tick()

                orbs = []
                for w in weapon_instances:
                    for eff in w.tick(player, enemies, cols, rows, frame):
                        if isinstance(eff, OrbMarker):      orbs.append(eff)
                        elif isinstance(eff, WhipSlash):    slashes.append(eff)
                        elif isinstance(eff, AoeBlast):     blasts.append(eff)
                        elif isinstance(eff, Bullet):       bullets.append(eff)

                for b in bullets:
                    if b.active: b.tick(cols, rows, UI_ROWS)
                bullets = [b for b in bullets if b.active]

                for sl in slashes: sl.tick()
                slashes = [sl for sl in slashes if sl.active]
                for bl in blasts: bl.tick()
                blasts = [bl for bl in blasts if bl.active]

                for e in enemies:
                    e.move_toward(player.x, player.y)
                for boss in bosses:
                    boss.move_toward(player.x, player.y)
                    enemy_bullets.extend(boss.attack_tick(player.x, player.y))

                for eb in enemy_bullets:
                    if eb.active:
                        eb.tick(cols, rows, UI_ROWS)
                enemy_bullets = [eb for eb in enemy_bullets if eb.active]

                killed, collected = resolve_collisions(
                    player, enemies, bullets, slashes, blasts, orbs, gems, weapon_instances
                )
                for e in killed:
                    roll = random.random()
                    if roll < MAGNET_DROP_RATE:
                        gems.append(XPGem(e.x, e.y, 0, 'magnet'))
                    elif roll < MAGNET_DROP_RATE + BIG_XP_DROP_RATE:
                        gems.append(XPGem(e.x, e.y, e.xp_value * BIG_XP_MULTIPLIER, 'big'))
                    else:
                        gems.append(XPGem(e.x, e.y, e.xp_value))
                    player.kills += 1
                for g in collected:
                    gems.remove(g)
                if any(g.gem_type == 'magnet' for g in collected):
                    for g in gems:
                        player.gain_xp(g.value)
                    gems.clear()
                enemies = [e for e in enemies if e.alive]

                # Boss collision with player weapons
                px_i, py_i = int(round(player.x)), int(round(player.y))
                for b in bullets:
                    if not b.active:
                        continue
                    gx, gy = b.grid_pos()
                    for boss in bosses:
                        if boss.alive and (gx, gy) in set(boss.cells()):
                            boss.take_damage(b.damage)
                            b.active = False
                            break
                for sl in slashes:
                    if not sl.active:
                        continue
                    slash_cells = set(sl.cells())
                    for boss in bosses:
                        if boss.alive and boss.id not in sl.hit_ids:
                            if any(c in slash_cells for c in boss.cells()):
                                sl.hit_ids.add(boss.id)
                                boss.take_damage(sl.damage)
                for bl in blasts:
                    if not bl.active:
                        continue
                    blast_cells = set(bl.cells())
                    for boss in bosses:
                        if boss.alive and boss.id not in bl.hit_ids:
                            if any(c in blast_cells for c in boss.cells()):
                                bl.hit_ids.add(boss.id)
                                boss.take_damage(bl.damage)
                for orb in orbs:
                    for boss in bosses:
                        if boss.alive and (orb.x, orb.y) in set(boss.cells()):
                            boss.take_damage(orb.damage)
                # Boss contact and enemy-bullet damage to player
                for boss in bosses:
                    if boss.alive and (px_i, py_i) in set(boss.cells()):
                        player.take_damage(boss.damage)
                for eb in enemy_bullets:
                    if eb.active:
                        ebx, eby = eb.grid_pos()
                        if ebx == px_i and eby == py_i:
                            player.take_damage(eb.damage)
                            eb.active = False
                # Boss kills and drops
                for boss in bosses:
                    if not boss.alive:
                        cx, cy = int(boss.center[0]), int(boss.center[1])
                        gems.append(XPGem(cx, cy, boss.xp_value, 'big'))
                        player.kills += 1
                bosses = [b for b in bosses if b.alive]

                # Boss spawning
                if not miniboss_spawned and frame == MINIBOSS_SPAWN_FRAME:
                    bosses.append(spawn_boss('miniboss', cols, rows, UI_ROWS))
                    miniboss_spawned = True
                if not boss_spawned and frame == BOSS_SPAWN_FRAME:
                    bosses.append(spawn_boss('boss', cols, rows, UI_ROWS))
                    boss_spawned = True

                spawn_timer += 1
                if spawn_timer >= ENEMY_SPAWN_INTERVAL:
                    spawn_timer = 0
                    spawn_enemies(player, enemies, cols, rows, UI_ROWS, difficulty)

                difficulty_timer += 1
                if difficulty_timer >= ENEMY_SPAWN_SCALE_INTERVAL:
                    difficulty_timer = 0
                    difficulty += 1

                frame += 1

                if player.should_level_up():
                    player.level_up()
                    upgrade_choices = get_upgrade_choices(player, weapon_instances)
                    upgrade_selected = 0
                    if upgrade_choices:
                        state = 'levelup'

                if not player.alive:
                    state = 'gameover'

        elif state == 'levelup':
            if this_dy == -1:
                upgrade_selected = max(0, upgrade_selected - 1)
            elif this_dy == 1:
                upgrade_selected = min(len(upgrade_choices) - 1, upgrade_selected + 1)
            elif action == 'enter':
                if upgrade_choices:
                    upgrade_choices[upgrade_selected]['apply'](player, weapon_instances)
                state = 'playing'
            elif action == 'quit':
                return 'quit', frame

        elif state == 'paused':
            if action == 'pause':
                state = 'playing'
            elif action in ('quit', 'menu'):
                return 'menu', frame

        elif state == 'gameover':
            if action == 'restart':
                return 'restart', frame
            elif action in ('menu', 'enter'):
                return 'menu', frame
            elif action == 'quit':
                return 'quit', frame

        # ── Render ───────────────────────────────────────────────────────────
        stdscr.erase()
        draw_hud(stdscr, player, frame, cols)
        draw_game(stdscr, player, enemies, bullets, slashes, blasts, orbs, gems, bosses, enemy_bullets, cols, rows)

        if state == 'levelup':
            draw_levelup(stdscr, upgrade_choices, upgrade_selected, cols, rows)
        elif state == 'paused':
            draw_pause(stdscr, cols, rows)
        elif state == 'gameover':
            draw_gameover(stdscr, player, frame, cols, rows)

        stdscr.refresh()


def run_game(stdscr):
    init_colors()
    curses.curs_set(0)
    stdscr.keypad(True)
    stdscr.nodelay(True)

    best_time = _load_best_time()

    while True:
        result = show_start_screen(stdscr, best_time)
        if result == 'quit':
            break

        # Inner loop: R on game-over restarts without returning to the menu.
        while True:
            result, final_frame = game_loop(stdscr)
            run_seconds = final_frame // FPS
            if run_seconds > best_time:
                best_time = run_seconds
                _save_best_time(best_time)
            if result != 'restart':
                break

        if result == 'quit':
            break
        # 'menu' → fall through to show_start_screen again


def main():
    try:
        curses.wrapper(run_game)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
