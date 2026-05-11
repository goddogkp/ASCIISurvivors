try:
    import curses
except ImportError:
    import windows_curses as curses

import time
import random
import math
import sys

from config import (
    FPS, FRAME_TIME, MIN_COLS, MIN_ROWS,
    ENEMY_SPAWN_INTERVAL, ENEMY_SPAWN_COUNT, ENEMY_SPAWN_SCALE_INTERVAL,
    ENEMY_HP_SCALE, ENEMY_SPEED_SCALE, MAX_ENEMIES, ENEMY_TYPES,
    COLOR_PAIRS, HP_BAR_WIDTH, XP_BAR_WIDTH,
    SIMPLE_COLORS, SIMPLE_ENEMY_COLOR, SIMPLE_PLAYER_COLOR,
    SIMPLE_WEAPON_COLOR, SIMPLE_PICKUP_COLOR,
    COLORBLIND_MODE, COLORBLIND_REMAP,
)
from entities import Player, Enemy, XPGem, Bullet, WhipSlash, AoeBlast
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


# ── Color helpers ─────────────────────────────────────────────────────────────

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


_ROLE_COLORS = {
    'enemy':  lambda: SIMPLE_ENEMY_COLOR,
    'player': lambda: SIMPLE_PLAYER_COLOR,
    'weapon': lambda: SIMPLE_WEAPON_COLOR,
    'pickup': lambda: SIMPLE_PICKUP_COLOR,
}

def cp(name, role=None):
    # 1. Simple colors: override by entity role
    if role is not None and SIMPLE_COLORS:
        name = _ROLE_COLORS[role]()
    # 2. Colorblind remap: applied on top (chains with simple colors)
    if COLORBLIND_MODE:
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
    if y < 0 or y >= rows:
        return
    if x >= cols:
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
        hp_mult = ENEMY_HP_SCALE ** difficulty
        sp_mult = ENEMY_SPEED_SCALE ** difficulty
        e.scale(hp_mult, sp_mult)
        enemies.append(e)


# ── Collision ─────────────────────────────────────────────────────────────────

def resolve_collisions(player, enemies, bullets, slashes, blasts, orbs, gems, weapon_instances):
    enemy_map = {}
    for e in enemies:
        key = (e.x, e.y)
        enemy_map.setdefault(key, []).append(e)

    killed = []

    # Bullets vs enemies
    for b in bullets:
        if not b.active:
            continue
        gx, gy = b.grid_pos()
        hits = enemy_map.get((gx, gy), [])
        for e in hits:
            if not e.alive:
                continue
            e.take_damage(b.damage)
            if not e.alive:
                killed.append(e)
            # AOE: create blast on impact
            if getattr(b, 'is_aoe', False):
                blasts.append(AoeBlast(gx, gy, b.aoe_radius, b.damage, '*', b.aoe_color))
                b.active = False
            else:
                b.active = False
            break

    # Slashes vs enemies
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

    # Blasts vs enemies
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

    # Orbs vs enemies (by position)
    for orb in orbs:
        for e in enemies:
            if not e.alive:
                continue
            if e.x == orb.x and e.y == orb.y:
                e.take_damage(orb.damage)
                if not e.alive:
                    killed.append(e)

    # Enemies vs player
    px, py = int(round(player.x)), int(round(player.y))
    for e in enemies:
        if not e.alive:
            continue
        if e.x == px and e.y == py:
            player.take_damage(e.damage)

    # XP gem pickup
    collected = []
    for g in gems:
        if g.x == px and g.y == py:
            player.gain_xp(g.value)
            collected.append(g)

    return killed, collected


# ── Rendering ─────────────────────────────────────────────────────────────────

UI_ROWS = 2  # rows reserved at top for HUD


def draw_hud(stdscr, player, frame, cols):
    rows_win, cols_win = stdscr.getmaxyx()
    seconds = frame // FPS
    minutes = seconds // 60
    secs = seconds % 60

    hp_pct = max(0.0, player.hp / player.max_hp)
    xp_next = player.xp_for_next()
    xp_pct = (player.xp / xp_next) if xp_next else 1.0
    xp_pct = min(1.0, xp_pct)

    # Top border
    safe_addstr(stdscr, 0, 0, '╔' + '═' * (cols_win - 2) + '╗', cp('white'))

    # Build HUD line
    hp_filled = int(HP_BAR_WIDTH * hp_pct)
    hp_bar = '█' * hp_filled + '░' * (HP_BAR_WIDTH - hp_filled)
    xp_filled = int(XP_BAR_WIDTH * xp_pct)
    xp_bar = '█' * xp_filled + '░' * (XP_BAR_WIDTH - xp_filled)

    hud = (f'║ HP[{hp_bar}]{player.hp:>4}/{player.max_hp:<4}'
           f' XP[{xp_bar}] Lv{player.level}'
           f' {minutes:02d}:{secs:02d}'
           f' Kills:{player.kills}')
    # Pad / trim to fit
    inner = cols_win - 2
    hud_content = hud[2:2 + inner]  # strip leading ║ space pair, but keep ║
    hud_line = '║' + hud_content.ljust(inner)[:inner] + '║' if len(hud_content) < inner else '║' + hud_content[:inner] + '║'

    safe_addstr(stdscr, 1, 0, hud_line, cp('white'))

    # Highlight bars — use player role so simple+colorblind modes apply
    bar_start_hp = 6
    safe_addstr(stdscr, 1, bar_start_hp, hp_bar[:hp_filled], cp('green', 'player') | curses.A_BOLD)
    safe_addstr(stdscr, 1, bar_start_hp + hp_filled, hp_bar[hp_filled:], cp('red'))

    xp_offset = bar_start_hp + HP_BAR_WIDTH + 2 + 9  # after HP section
    safe_addstr(stdscr, 1, xp_offset, xp_bar[:xp_filled], cp('yellow') | curses.A_BOLD)
    safe_addstr(stdscr, 1, xp_offset + xp_filled, xp_bar[xp_filled:], cp('white'))


def _bullet_char(b):
    adx, ady = abs(b.dx), abs(b.dy)
    if adx >= ady * 2: return '-'
    if ady >= adx * 2: return '|'
    return '/' if b.dx * b.dy < 0 else '\\'


def draw_game(stdscr, player, enemies, bullets, slashes, blasts, orbs, gems, cols, rows):
    # Enemies
    for e in enemies:
        ex, ey = int(e.x), int(e.y)
        if UI_ROWS <= ey < rows and 0 <= ex < cols:
            attr = cp(e.color, 'enemy') | curses.A_BOLD
            safe_addch(stdscr, ey, ex, e.char, attr)

    # XP gems
    for g in gems:
        if UI_ROWS <= g.y < rows and 0 <= g.x < cols:
            safe_addch(stdscr, g.y, g.x, '*', cp('yellow', 'pickup'))

    # Slashes
    for sl in slashes:
        if sl.active:
            for cx, cy in sl.cells():
                if UI_ROWS <= cy < rows and 0 <= cx < cols:
                    safe_addch(stdscr, cy, cx, sl.char, cp(sl.color, 'weapon') | curses.A_BOLD)

    # Blasts
    for bl in blasts:
        if bl.active:
            for cx, cy in bl.cells():
                if UI_ROWS <= cy < rows and 0 <= cx < cols:
                    safe_addch(stdscr, cy, cx, bl.char, cp(bl.color, 'weapon') | curses.A_BOLD)

    # Bullets
    for b in bullets:
        if b.active:
            bx, by = b.grid_pos()
            if UI_ROWS <= by < rows and 0 <= bx < cols:
                safe_addch(stdscr, by, bx, _bullet_char(b), cp(b.color, 'weapon') | curses.A_BOLD)

    # Orbs
    for orb in orbs:
        if UI_ROWS <= orb.y < rows and 0 <= orb.x < cols:
            safe_addch(stdscr, orb.y, orb.x, orb.char, cp('cyan', 'weapon') | curses.A_BOLD)

    # Player (blink when invuln)
    py = int(round(player.y))
    px = int(round(player.x))
    if player.invuln == 0 or player.invuln % 3 != 0:
        safe_addch(stdscr, py, px, player.char, cp('green', 'player') | curses.A_BOLD)


def draw_levelup(stdscr, choices, selected, cols, rows):
    bw = 50
    bh = len(choices) * 3 + 6
    bx = (cols - bw) // 2
    by = (rows - bh) // 2

    def box_line(y, s, attr=0):
        safe_addstr(stdscr, by + y, bx, s, attr)

    box_line(0, '╔' + '═' * (bw - 2) + '╗', cp('yellow') | curses.A_BOLD)
    title = ' LEVEL UP! Choose an upgrade '
    box_line(1, '║' + title.center(bw - 2) + '║', cp('yellow') | curses.A_BOLD)
    box_line(2, '╠' + '═' * (bw - 2) + '╣', cp('yellow') | curses.A_BOLD)

    for i, upg in enumerate(choices):
        row = 3 + i * 3
        marker = '► ' if i == selected else '  '
        attr = (cp('cyan') | curses.A_BOLD) if i == selected else cp('white')
        safe_addstr(stdscr, by + row, bx, '║' + (' ' * (bw - 2)) + '║', cp('yellow') | curses.A_BOLD)
        label = f"{marker}{upg['name']}: {upg['desc']}"
        safe_addstr(stdscr, by + row, bx + 2, label[:bw - 4], attr)
        safe_addstr(stdscr, by + row + 1, bx, '║' + (' ' * (bw - 2)) + '║', cp('yellow') | curses.A_BOLD)

    footer_row = 3 + len(choices) * 3
    box_line(footer_row, '╠' + '═' * (bw - 2) + '╣', cp('yellow') | curses.A_BOLD)
    hint = ' ↑↓/WS to choose  ENTER to pick '
    box_line(footer_row + 1, '║' + hint.center(bw - 2) + '║', cp('white'))
    box_line(footer_row + 2, '╚' + '═' * (bw - 2) + '╝', cp('yellow') | curses.A_BOLD)


def draw_gameover(stdscr, player, frame, cols, rows):
    bw = 40
    bh = 12
    bx = (cols - bw) // 2
    by = (rows - bh) // 2
    seconds = frame // FPS

    def bl(y, s, attr=0):
        safe_addstr(stdscr, by + y, bx, s, attr)

    bl(0,  '╔' + '═' * (bw - 2) + '╗', cp('red') | curses.A_BOLD)
    bl(1,  '║' + ' GAME OVER '.center(bw - 2) + '║', cp('red') | curses.A_BOLD)
    bl(2,  '╠' + '═' * (bw - 2) + '╣', cp('red') | curses.A_BOLD)
    bl(3,  '║' + f'  Survived: {seconds // 60:02d}:{seconds % 60:02d}'.ljust(bw - 2) + '║', cp('white'))
    bl(4,  '║' + f'  Level: {player.level}'.ljust(bw - 2) + '║', cp('white'))
    bl(5,  '║' + f'  Kills: {player.kills}'.ljust(bw - 2) + '║', cp('white'))
    bl(6,  '║' + f'  Max HP: {player.max_hp}'.ljust(bw - 2) + '║', cp('white'))
    bl(7,  '║' + f'  Armor: {player.armor}'.ljust(bw - 2) + '║', cp('white'))
    bl(8,  '╠' + '═' * (bw - 2) + '╣', cp('red') | curses.A_BOLD)
    bl(9,  '║' + '  Press R to restart  Q to quit'.ljust(bw - 2) + '║', cp('yellow'))
    bl(10, '╚' + '═' * (bw - 2) + '╝', cp('red') | curses.A_BOLD)


# ── Main game logic ───────────────────────────────────────────────────────────

def run_game(stdscr):
    init_colors()
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)

    while True:
        result = game_loop(stdscr)
        if result != 'restart':
            break


def game_loop(stdscr):
    rows, cols = stdscr.getmaxyx()

    if cols < MIN_COLS or rows < MIN_ROWS:
        stdscr.clear()
        safe_addstr(stdscr, 0, 0, f'Terminal too small! Need {MIN_COLS}x{MIN_ROWS}, got {cols}x{rows}')
        stdscr.refresh()
        time.sleep(2)
        return 'quit'

    player = Player(cols // 2, rows // 2)
    weapon_instances = [WeaponInstance('knife')]

    enemies = []
    bullets = []
    slashes = []
    blasts = []
    orbs = []
    gems = []

    frame = 0
    spawn_timer = 0
    difficulty = 0
    difficulty_timer = 0

    state = 'playing'   # 'playing', 'levelup', 'gameover'
    upgrade_choices = []
    upgrade_selected = 0

    last_time = time.monotonic()
    # Persists movement direction across key-repeat gaps (~400 ms OS initial delay)
    held = {'dx': 0, 'dy': 0, 'dx_ttl': 0, 'dy_ttl': 0}

    while True:
        now = time.monotonic()
        elapsed = now - last_time

        # Frame rate cap
        if elapsed < FRAME_TIME:
            time.sleep(FRAME_TIME - elapsed)
            continue
        last_time = now

        rows, cols = stdscr.getmaxyx()

        # ── Input ────────────────────────────────────────────────────────────
        # Drain getch for action keys and menu navigation (always needed).
        this_dx, this_dy, action = None, None, None
        k = stdscr.getch()
        while k != -1:
            if k in (ord('w'), curses.KEY_UP):      this_dy = -1
            elif k in (ord('s'), curses.KEY_DOWN):   this_dy =  1
            if k in (ord('a'), curses.KEY_LEFT):     this_dx = -1
            elif k in (ord('d'), curses.KEY_RIGHT):  this_dx =  1
            if k in (ord('\n'), 10, 13, curses.KEY_ENTER): action = 'enter'
            elif k == ord('q'):  action = 'quit'
            elif k == ord('r'):  action = 'restart'
            k = stdscr.getch()

        # Movement: Windows polls hardware key state (instant stop, no sliding).
        # Other platforms fall back to the TTL approach for the key-repeat gap.
        if _poll_move is not None:
            move_dx, move_dy = _poll_move()
        else:
            if this_dx is not None:
                held['dx'], held['dx_ttl'] = this_dx, 6
            elif held['dx_ttl'] > 0:
                held['dx_ttl'] -= 1
                if held['dx_ttl'] == 0:
                    held['dx'] = 0
            if this_dy is not None:
                held['dy'], held['dy_ttl'] = this_dy, 6
            elif held['dy_ttl'] > 0:
                held['dy_ttl'] -= 1
                if held['dy_ttl'] == 0:
                    held['dy'] = 0
            move_dx, move_dy = held['dx'], held['dy']

        if state == 'playing':
            if action == 'quit':
                return 'quit'

            # ── Update ───────────────────────────────────────────────────────
            player.move(move_dx, move_dy, cols, rows, UI_ROWS)
            player.tick()

            # Weapon ticks
            orbs = []
            for w in weapon_instances:
                new_effects = w.tick(player, enemies, cols, rows, frame)
                for eff in new_effects:
                    if isinstance(eff, OrbMarker):
                        orbs.append(eff)
                    elif isinstance(eff, WhipSlash):
                        slashes.append(eff)
                    elif isinstance(eff, AoeBlast):
                        blasts.append(eff)
                    elif isinstance(eff, Bullet):
                        bullets.append(eff)

            # Move bullets
            for b in bullets:
                if b.active:
                    b.tick(cols, rows, UI_ROWS)
            bullets = [b for b in bullets if b.active]

            # Tick slashes / blasts
            for sl in slashes:
                sl.tick()
            slashes = [sl for sl in slashes if sl.active]
            for bl in blasts:
                bl.tick()
            blasts = [bl for bl in blasts if bl.active]

            # Move enemies
            for e in enemies:
                e.move_toward(player.x, player.y)

            # Collisions
            killed, collected = resolve_collisions(
                player, enemies, bullets, slashes, blasts, orbs, gems, weapon_instances
            )
            for e in killed:
                gems.append(XPGem(e.x, e.y, e.xp_value))
                player.kills += 1
            for g in collected:
                gems.remove(g)
            enemies = [e for e in enemies if e.alive]

            # Spawn
            spawn_timer += 1
            if spawn_timer >= ENEMY_SPAWN_INTERVAL:
                spawn_timer = 0
                spawn_enemies(player, enemies, cols, rows, UI_ROWS, difficulty)

            # Difficulty scaling
            difficulty_timer += 1
            if difficulty_timer >= ENEMY_SPAWN_SCALE_INTERVAL:
                difficulty_timer = 0
                difficulty += 1

            frame += 1

            # Check level up
            if player.should_level_up():
                player.level_up()
                upgrade_choices = get_upgrade_choices(player, weapon_instances)
                upgrade_selected = 0
                if upgrade_choices:
                    state = 'levelup'

            # Check death
            if not player.alive:
                state = 'gameover'

        elif state == 'levelup':
            if this_dy == -1:
                upgrade_selected = max(0, upgrade_selected - 1)
            elif this_dy == 1:
                upgrade_selected = min(len(upgrade_choices) - 1, upgrade_selected + 1)
            elif action == 'enter':
                if upgrade_choices:
                    upg = upgrade_choices[upgrade_selected]
                    upg['apply'](player, weapon_instances)
                state = 'playing'
            elif action == 'quit':
                return 'quit'

        elif state == 'gameover':
            if action == 'restart':
                return 'restart'
            elif action == 'quit':
                return 'quit'

        # ── Render ───────────────────────────────────────────────────────────
        stdscr.erase()

        if state in ('playing', 'levelup'):
            draw_hud(stdscr, player, frame, cols)
            draw_game(stdscr, player, enemies, bullets, slashes, blasts, orbs, gems, cols, rows)
            if state == 'levelup':
                draw_levelup(stdscr, upgrade_choices, upgrade_selected, cols, rows)
        elif state == 'gameover':
            draw_hud(stdscr, player, frame, cols)
            draw_game(stdscr, player, enemies, bullets, slashes, blasts, orbs, gems, cols, rows)
            draw_gameover(stdscr, player, frame, cols, rows)

        stdscr.refresh()


def main():
    try:
        curses.wrapper(run_game)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
