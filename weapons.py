import math
import copy
from config import WEAPON_DEFS
from entities import Bullet, WhipSlash, AoeBlast


def get_weapon_def(wid):
    for w in WEAPON_DEFS:
        if w['id'] == wid:
            return copy.deepcopy(w)
    raise KeyError(f"Unknown weapon: {wid}")


class WeaponInstance:
    """Tracks a weapon owned by the player including its current level."""
    def __init__(self, wid):
        self.defn = get_weapon_def(wid)
        self.level = 1
        self.cooldown_remaining = 0
        # orb state
        self.orb_angle = 0.0

    @property
    def id(self):
        return self.defn['id']

    @property
    def name(self):
        return self.defn['name']

    def _stat(self, key):
        """Return stat for current level, falling back to base def."""
        lvl_stats = self.defn.get('level_stats', {})
        for lv in range(self.level, 0, -1):
            if lv in lvl_stats and key in lvl_stats[lv]:
                return lvl_stats[lv][key]
        return self.defn.get(key)

    @property
    def damage(self):
        return self._stat('damage')

    @property
    def cooldown(self):
        return self._stat('cooldown') or 1

    @property
    def count(self):
        return self._stat('count') or 1

    @property
    def reach(self):
        return self._stat('reach') or 4

    @property
    def radius(self):
        return self._stat('radius') or 3

    @property
    def speed(self):
        return self._stat('speed') or 2

    @property
    def range(self):
        return self._stat('range') or 15

    def level_up(self):
        max_lv = max(self.defn.get('level_stats', {}).keys(), default=1)
        if self.level < max_lv:
            self.level += 1

    @property
    def max_level(self):
        return max(self.defn.get('level_stats', {}).keys(), default=1)

    def tick(self, player, enemies, cols, rows, frame):
        """Returns list of new projectile/effect objects."""
        behavior = self.defn['behavior']
        results = []

        if behavior == 'orb':
            results = self._tick_orb(player, frame)
        else:
            if self.cooldown_remaining > 0:
                self.cooldown_remaining -= 1
                return []
            if behavior == 'knife':
                results = self._fire_knife(player, enemies)
            elif behavior == 'whip':
                results = self._fire_whip(player)
            elif behavior == 'aoe':
                results = self._fire_aoe(player, enemies)
            if results is not None:
                self.cooldown_remaining = self.cooldown

        return results or []

    def _tick_orb(self, player, frame):
        # Orbs always exist; we just update angle and return "orb markers"
        speed_rads = 0.15  # radians per frame
        self.orb_angle += speed_rads
        orbs = []
        n = self.count
        for i in range(n):
            angle = self.orb_angle + (2 * math.pi * i / n)
            rx = self.radius * 2   # doubled for terminal aspect ratio
            ry = self.radius
            ox = int(round(player.x + rx * math.cos(angle)))
            oy = int(round(player.y + ry * math.sin(angle)))
            orbs.append(OrbMarker(ox, oy, self.damage, self.defn['char'], self.defn['color']))
        return orbs

    def _fire_knife(self, player, enemies):
        dx, dy = player.dx, player.dy
        if dx == 0 and dy == 0:
            dx = 1.0
        # Find nearest enemy direction if we have one
        if enemies:
            nearest = min(enemies, key=lambda e: (e.x - player.x)**2 + (e.y - player.y)**2)
            ex, ey = nearest.x - player.x, nearest.y - player.y
            dist = math.sqrt(ex*ex + ey*ey)
            if dist > 0:
                dx, dy = ex / dist, ey / dist

        bullets = []
        spread = self.count
        base_angle = math.atan2(dy, dx)
        spread_angle = math.radians(15)
        for i in range(spread):
            angle = base_angle + (i - (spread - 1) / 2) * spread_angle
            bdx = math.cos(angle)
            bdy = math.sin(angle)
            bullets.append(Bullet(
                player.x, player.y, bdx, bdy,
                self.damage, self.defn['char'], self.defn['color'],
                self.range, self.speed,
            ))
        return bullets

    def _fire_whip(self, player):
        # Alternate horizontal/vertical each activation
        if not hasattr(self, '_whip_horiz'):
            self._whip_horiz = True
        slash = WhipSlash(
            int(player.x), int(player.y),
            self._whip_horiz, self.reach,
            self.damage, self.defn['char'], self.defn['color'],
        )
        self._whip_horiz = not self._whip_horiz
        return [slash]

    def _fire_aoe(self, player, enemies):
        if not enemies:
            return []
        target = min(enemies, key=lambda e: (e.x - player.x)**2 + (e.y - player.y)**2)
        dx = target.x - player.x
        dy = target.y - player.y
        dist = math.sqrt(dx*dx + dy*dy)
        if dist == 0:
            return []
        speed = self.speed
        ndx = dx / dist * speed
        ndy = dy / dist * speed
        b = Bullet(
            player.x, player.y, ndx, ndy,
            self.damage, self.defn['char'], self.defn['color'],
            self.range, speed,
        )
        b.is_aoe = True
        b.aoe_radius = self.radius
        b.aoe_color = self.defn['color']
        return [b]


class OrbMarker:
    """Not a projectile — just marks where an orb is this frame."""
    def __init__(self, x, y, damage, char, color):
        self.x = x
        self.y = y
        self.damage = damage
        self.char = char
        self.color = color
        self.active = True
