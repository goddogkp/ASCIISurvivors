# ASCII Survivors

A terminal-based Vampire Survivors clone built with Python and curses.

## Requirements

- Python 3.8+
- Terminal: 80×24 minimum (larger is better)

## Install & Run

```bash
pip install -r requirements.txt
python game.py
```

## Controls

| Key | Action |
|-----|--------|
| WASD / Arrow keys | Move |
| Enter | Confirm upgrade |
| Q | Quit |
| R | Restart (game over screen) |

## Weapons

| Weapon | Char | Description |
|--------|------|-------------|
| Knife | `-` | Fires toward nearest enemy |
| Magic Orb | `o` | Rotates around player, damages on contact |
| Whip | `~` | Horizontal/vertical area slash |
| Fireball | `*` | Homing AoE explosion |

## Enemies

| Char | Name | Notes |
|------|------|-------|
| Z | Zombie | Slow, tanky |
| z | Runner | Fast, fragile |
| W | Wolf | Medium speed and HP |
| v | Bat | Fast, medium HP |
| M | Monster | Very slow, very tanky, high XP |

## Files

- `game.py` — main loop and rendering
- `entities.py` — Player, Enemy, Bullet, and effect classes
- `weapons.py` — weapon definitions and fire behaviors
- `upgrades.py` — upgrade pool and selection logic
- `config.py` — all tunable values (FPS, damage, spawn rates, etc.)
