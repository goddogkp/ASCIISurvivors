import math
import random
from config import (
    PLAYER_START_HP, PLAYER_START_SPEED, PLAYER_START_ARMOR,
    PLAYER_INVULN_FRAMES, PLAYER_CHAR, XP_PER_LEVEL, ENEMY_TYPES,
)


class Player:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.hp = PLAYER_START_HP
        self.max_hp = PLAYER_START_HP
        self.speed = PLAYER_START_SPEED
        self.armor = PLAYER_START_ARMOR
        self.xp = 0
        self.level = 1
        self.kills = 0
        self.invuln = 0       # frames remaining of invincibility
        self.dx = 0
        self.dy = 0
        self.char = PLAYER_CHAR

    def move(self, dx, dy, cols, rows, ui_rows=1):
        if dx == 0 and dy == 0:
            return
        length = math.sqrt(dx * dx + dy * dy)
        self.dx = dx / length
        self.dy = dy / length
        nx = self.x + self.dx * self.speed
        ny = self.y + self.dy * self.speed
        self.x = max(0, min(cols - 1, nx))
        self.y = max(ui_rows, min(rows - 1, ny))

    def take_damage(self, dmg):
        if self.invuln > 0:
            return
        actual = max(1, dmg - self.armor)
        self.hp -= actual
        self.invuln = PLAYER_INVULN_FRAMES

    def tick(self):
        if self.invuln > 0:
            self.invuln -= 1

    def gain_xp(self, amount):
        self.xp += amount

    def xp_for_next(self):
        if self.level < len(XP_PER_LEVEL):
            return XP_PER_LEVEL[self.level]
        # Beyond the table: scale by 1.3× per extra level
        extra = self.level - len(XP_PER_LEVEL) + 1
        return int(XP_PER_LEVEL[-1] * (1.3 ** extra))

    def should_level_up(self):
        needed = self.xp_for_next()
        return needed is not None and self.xp >= needed

    def level_up(self):
        self.level += 1

    @property
    def alive(self):
        return self.hp > 0


class Enemy:
    _id_counter = 0

    def __init__(self, x, y, etype):
        Enemy._id_counter += 1
        self.id = Enemy._id_counter
        self.x = int(x)
        self.y = int(y)
        defn = ENEMY_TYPES[etype]
        self.char = defn['char']
        self.color = defn['color']
        self.hp = defn['hp']
        self.max_hp = defn['hp']
        self.speed = defn['speed']
        self.xp_value = defn['xp']
        self.damage = defn['damage']
        self.etype = etype
        self.frac_x = float(x)
        self.frac_y = float(y)

    def scale(self, hp_mult, speed_mult):
        self.hp = max(1, int(self.hp * hp_mult))
        self.max_hp = self.hp
        self.speed = min(1.5, self.speed * speed_mult)

    def move_toward(self, px, py):
        dx = px - self.frac_x
        dy = py - self.frac_y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 0.5:
            return
        self.frac_x += (dx / dist) * self.speed
        self.frac_y += (dy / dist) * self.speed
        self.x = int(round(self.frac_x))
        self.y = int(round(self.frac_y))

    @property
    def alive(self):
        return self.hp > 0

    def take_damage(self, dmg):
        self.hp -= dmg


class XPGem:
    def __init__(self, x, y, value):
        self.x = int(x)
        self.y = int(y)
        self.value = value


class Bullet:
    def __init__(self, x, y, dx, dy, damage, char, color, max_range, speed=2):
        self.x = float(x)
        self.y = float(y)
        self.dx = dx
        self.dy = dy
        self.damage = damage
        self.char = char
        self.color = color
        self.remaining = max_range
        self.speed = speed
        self.active = True

    def tick(self, cols, rows, ui_rows=1):
        steps = self.speed
        self.x += self.dx * steps
        self.y += self.dy * steps
        self.remaining -= steps
        if (self.x < 0 or self.x >= cols or
                self.y < ui_rows or self.y >= rows or
                self.remaining <= 0):
            self.active = False

    def grid_pos(self):
        return (int(round(self.x)), int(round(self.y)))


class WhipSlash:
    """A short-lived area attack."""
    def __init__(self, cx, cy, horizontal, reach, damage, char, color, duration=4):
        self.cx = cx
        self.cy = cy
        self.horizontal = horizontal
        self.reach = reach
        self.damage = damage
        self.char = char
        self.color = color
        self.duration = duration
        self.active = True
        self.hit_ids = set()

    def cells(self):
        cells = []
        if self.horizontal:
            for dx in range(-self.reach, self.reach + 1):
                cells.append((self.cx + dx, self.cy))
        else:
            for dy in range(-self.reach, self.reach + 1):
                cells.append((self.cx, self.cy + dy))
        return cells

    def tick(self):
        self.duration -= 1
        if self.duration <= 0:
            self.active = False


class AoeBlast:
    """Fireball explosion lingering for a few frames."""
    def __init__(self, cx, cy, radius, damage, char, color, duration=5):
        self.cx = cx
        self.cy = cy
        self.radius = radius
        self.damage = damage
        self.char = char
        self.color = color
        self.duration = duration
        self.active = True
        self.hit_ids = set()

    def cells(self):
        cells = []
        for dy in range(-self.radius, self.radius + 1):
            for dx in range(-self.radius * 2, self.radius * 2 + 1):
                # Approximate circle (terminals are ~2:1 aspect)
                if (dx / 2) ** 2 + dy ** 2 <= self.radius ** 2:
                    cells.append((self.cx + dx, self.cy + dy))
        return cells

    def tick(self):
        self.duration -= 1
        if self.duration <= 0:
            self.active = False
