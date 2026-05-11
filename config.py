FPS = 15
FRAME_TIME = 1.0 / FPS

# Display
MIN_COLS = 80
MIN_ROWS = 24

# Player
PLAYER_CHAR = '@'
PLAYER_START_HP = 100
PLAYER_START_SPEED = 1
PLAYER_START_ARMOR = 0
PLAYER_INVULN_FRAMES = 15  # frames of invincibility after hit

# XP / Leveling
XP_PER_LEVEL = [0, 10, 25, 45, 70, 100, 135, 175, 220, 270, 325]  # cumulative XP needed
XP_GEM_CHAR = '*'

# Enemy spawning
ENEMY_SPAWN_INTERVAL = 45   # frames between spawns
ENEMY_SPAWN_COUNT = 2       # enemies per spawn event
ENEMY_SPAWN_SCALE_INTERVAL = 1800  # frames (~2 min) between difficulty steps
ENEMY_HP_SCALE = 1.25
ENEMY_SPEED_SCALE = 1.15
MAX_ENEMIES = 80

# Enemy definitions: char, color_pair_id, base_hp, base_speed, xp_value, damage
ENEMY_TYPES = {
    'zombie': {
        'char': 'Z', 'color': 'red', 'hp': 5, 'speed': 0.20,
        'xp': 1, 'damage': 5, 'weight': 40,
    },
    'runner': {
        'char': 'z', 'color': 'red', 'hp': 2, 'speed': 0.38,
        'xp': 1, 'damage': 3, 'weight': 30,
    },
    'wolf': {
        'char': 'W', 'color': 'magenta', 'hp': 10, 'speed': 0.25,
        'xp': 2, 'damage': 8, 'weight': 20,
    },
    'bat': {
        'char': 'v', 'color': 'magenta', 'hp': 3, 'speed': 0.32,
        'xp': 1, 'damage': 4, 'weight': 25,
    },
    'monster': {
        'char': 'M', 'color': 'red', 'hp': 25, 'speed': 0.13,
        'xp': 5, 'damage': 15, 'weight': 10,
    },
}

# Weapon definitions: name, char, color, damage, cooldown (frames), behavior, level_stats
WEAPON_DEFS = [
    {
        'id': 'orb',
        'name': 'Magic Orb',
        'char': 'o',
        'color': 'cyan',
        'damage': 8,
        'cooldown': 0,   # orbs are continuous, rotation speed matters
        'behavior': 'orb',
        'count': 1,
        'radius': 3,
        'level_stats': {
            2: {'damage': 12, 'count': 2},
            3: {'damage': 16, 'count': 3, 'radius': 4},
            4: {'damage': 22, 'count': 4},
            5: {'damage': 30, 'count': 5, 'radius': 5},
        },
    },
    {
        'id': 'knife',
        'name': 'Knife',
        'char': '-',
        'color': 'white',
        'damage': 12,
        'cooldown': 20,
        'behavior': 'knife',
        'speed': 2,
        'range': 15,
        'level_stats': {
            2: {'damage': 18, 'cooldown': 17},
            3: {'damage': 25, 'cooldown': 14, 'count': 2},
            4: {'damage': 33, 'cooldown': 11},
            5: {'damage': 44, 'cooldown': 8, 'count': 3},
        },
    },
    {
        'id': 'whip',
        'name': 'Whip',
        'char': '~',
        'color': 'yellow',
        'damage': 15,
        'cooldown': 30,
        'behavior': 'whip',
        'reach': 4,
        'level_stats': {
            2: {'damage': 22, 'reach': 5},
            3: {'damage': 30, 'cooldown': 25, 'reach': 6},
            4: {'damage': 40, 'reach': 7},
            5: {'damage': 55, 'cooldown': 20, 'reach': 9},
        },
    },
    {
        'id': 'fireball',
        'name': 'Fireball',
        'char': '*',
        'color': 'red',
        'damage': 20,
        'cooldown': 40,
        'behavior': 'aoe',
        'radius': 2,
        'speed': 1,
        'range': 12,
        'level_stats': {
            2: {'damage': 28, 'radius': 3},
            3: {'damage': 38, 'cooldown': 33},
            4: {'damage': 50, 'radius': 4},
            5: {'damage': 65, 'cooldown': 25, 'radius': 5},
        },
    },
]

# Color pair IDs (assigned in game.py init)
COLOR_PAIRS = {
    'white':   1,
    'red':     2,
    'green':   3,
    'yellow':  4,
    'cyan':    5,
    'magenta': 6,
    'blue':    7,
}

# UI
HP_BAR_WIDTH = 20
XP_BAR_WIDTH = 20

# ── Color Modes ───────────────────────────────────────────────────────────────

# Simple Colors: flatten all entity colors to fixed role-based colors.
# Useful for custom themes or as a base for colorblind mode.
SIMPLE_COLORS = True
SIMPLE_ENEMY_COLOR  = 'red'      # all enemies
SIMPLE_PLAYER_COLOR = 'green'    # player @
SIMPLE_WEAPON_COLOR = 'cyan'     # all projectiles / weapons
SIMPLE_PICKUP_COLOR = 'magenta'  # XP gems

# Colorblind Mode: remap colors that are hard to distinguish.
# Applied after SIMPLE_COLORS, so they stack correctly.
# Defaults target red/green colorblindness (deuteranopia / protanopia):
#   enemies (red)  → blue   — distinct from player yellow
#   player (green) → yellow — distinct from enemy blue
# Edit COLORBLIND_REMAP to adjust for other colorblindness types.
COLORBLIND_MODE = True
COLORBLIND_REMAP = {
    'red':   'blue',
    'green': 'yellow',
}
