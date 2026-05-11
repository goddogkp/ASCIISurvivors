import random
from config import WEAPON_DEFS

# Each upgrade: id, name, description, apply(player, weapon_instances) -> bool (False = not applicable)
UPGRADE_POOL = [
    {
        'id': 'speed_up',
        'name': 'Swift Boots',
        'desc': 'Move speed +0.2',
        'apply': lambda p, ws: _stat_up(p, 'speed', 0.2),
        'repeatable': True,
    },
    {
        'id': 'max_hp',
        'name': 'Iron Will',
        'desc': 'Max HP +25, heal +25',
        'apply': lambda p, ws: _hp_up(p, 25),
        'repeatable': True,
    },
    {
        'id': 'armor',
        'name': 'Plate Mail',
        'desc': 'Armor +2 (reduces all damage)',
        'apply': lambda p, ws: _stat_up(p, 'armor', 2),
        'repeatable': True,
    },
    {
        'id': 'new_orb',
        'name': 'Magic Orb',
        'desc': 'Gain: Magic Orb weapon',
        'apply': lambda p, ws: _add_weapon(ws, 'orb'),
        'repeatable': False,
        'weapon_id': 'orb',
    },
    {
        'id': 'new_knife',
        'name': 'Knife',
        'desc': 'Gain: Knife weapon',
        'apply': lambda p, ws: _add_weapon(ws, 'knife'),
        'repeatable': False,
        'weapon_id': 'knife',
    },
    {
        'id': 'new_whip',
        'name': 'Whip',
        'desc': 'Gain: Whip weapon',
        'apply': lambda p, ws: _add_weapon(ws, 'whip'),
        'repeatable': False,
        'weapon_id': 'whip',
    },
    {
        'id': 'new_fireball',
        'name': 'Fireball',
        'desc': 'Gain: Fireball weapon',
        'apply': lambda p, ws: _add_weapon(ws, 'fireball'),
        'repeatable': False,
        'weapon_id': 'fireball',
    },
    {
        'id': 'lvl_orb',
        'name': 'Orb+ ',
        'desc': 'Magic Orb level up',
        'apply': lambda p, ws: _lvl_weapon(ws, 'orb'),
        'repeatable': True,
        'requires_weapon': 'orb',
    },
    {
        'id': 'lvl_knife',
        'name': 'Knife+',
        'desc': 'Knife level up',
        'apply': lambda p, ws: _lvl_weapon(ws, 'knife'),
        'repeatable': True,
        'requires_weapon': 'knife',
    },
    {
        'id': 'lvl_whip',
        'name': 'Whip+',
        'desc': 'Whip level up',
        'apply': lambda p, ws: _lvl_weapon(ws, 'whip'),
        'repeatable': True,
        'requires_weapon': 'whip',
    },
    {
        'id': 'lvl_fireball',
        'name': 'Fireball+',
        'desc': 'Fireball level up',
        'apply': lambda p, ws: _lvl_weapon(ws, 'fireball'),
        'repeatable': True,
        'requires_weapon': 'fireball',
    },
]


def _stat_up(player, attr, amount):
    setattr(player, attr, getattr(player, attr) + amount)
    return True


def _hp_up(player, amount):
    player.max_hp += amount
    player.hp = min(player.max_hp, player.hp + amount)
    return True


def _add_weapon(weapon_instances, wid):
    if any(w.id == wid for w in weapon_instances):
        return False
    from weapons import WeaponInstance
    weapon_instances.append(WeaponInstance(wid))
    return True


def _lvl_weapon(weapon_instances, wid):
    for w in weapon_instances:
        if w.id == wid and w.level < w.max_level:
            w.level_up()
            return True
    return False


def get_upgrade_choices(player, weapon_instances, count=3):
    owned_ids = {w.id for w in weapon_instances}
    candidates = []
    for upg in UPGRADE_POOL:
        # Skip new-weapon upgrades for weapons already owned
        if 'weapon_id' in upg and upg['weapon_id'] in owned_ids:
            continue
        # Skip level-up upgrades for weapons not owned or at max level
        if 'requires_weapon' in upg:
            wid = upg['requires_weapon']
            if wid not in owned_ids:
                continue
            w = next((x for x in weapon_instances if x.id == wid), None)
            if w and w.level >= w.max_level:
                continue
        candidates.append(upg)
    if not candidates:
        return []
    random.shuffle(candidates)
    return candidates[:count]
