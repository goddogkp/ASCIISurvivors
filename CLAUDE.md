Build a real terminal Vampire Survivors clone in Python using curses.
Core requirements:

Runs entirely in a real terminal via Python's curses library (no OpenGL, no fake renderer, no GUI)
Must work on Windows (via windows-curses pip package) and Linux/Mac
Real-time game loop at ~15 FPS using non-blocking input
Terminal size aware — detect cols/rows and adapt the play area

Player:

Moves with WASD or arrow keys
Has HP, XP, and level
Weapons fire automatically every tick

Enemies:

Spawn from outside screen edges on a timer
Move toward the player
Scale in HP and speed as time progresses
Different ASCII chars per type (Z, z, W, v, M)

Weapons (at least 3):

Orb: rotates around player
Knife: fires in movement direction
Whip: horizontal/vertical slash hitbox
Each represented by a distinct ASCII char

Progression:

Kill enemies → drop XP gems (*)
Level up → pause game, show upgrade menu (pick 1 of 3)
Upgrades: new weapon, weapon level, speed, max HP, armor

UI (drawn with box-drawing chars):

Top bar: HP, XP, level, timer, enemy kill count
Level-up screen overlaid on game
Game over screen with stats

Code structure:

Keep it in a single game.py file to start
Use windows-curses with a try/except fallback so it works cross-platform
Include a requirements.txt with just windows-curses
Add a README.md with how to run it

Aesthetic:

ANSI color via curses color pairs — enemies red, player green, XP yellow, bullets white
Box-drawing characters for all UI borders (╔ ═ ║ ╚)
Keep it readable at 80×24 (standard terminal minimum)

Modularity & configurability:

All tunable values live in a single config.py file at the top of the project — things like FPS, enemy spawn rate, XP thresholds per level, weapon damage/cooldown/range, enemy HP/speed scaling, color scheme. No magic numbers buried in logic.
Weapons are defined as data, not hardcoded logic — a list of weapon definitions (name, char, color, damage, cooldown, behavior type) so adding a new weapon means adding a new entry, not writing new game logic
Enemy types follow the same pattern — a dictionary of enemy definitions with their char, color, HP, speed, XP value
Upgrade pool is also data-driven — a list of upgrade definitions that the level-up system pulls from, so new upgrades can be dropped in without touching the picker logic
Separate files: game.py (loop + rendering), entities.py (player, enemy, bullet classes), weapons.py (weapon definitions + behavior), config.py (all tunable values), upgrades.py (upgrade pool)