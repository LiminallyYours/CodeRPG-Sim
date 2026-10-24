#!/usr/bin/env python3
"""The game owner's cost switches, per game:  python3 tools/settings.py <command> [--game <id>]

    show                      the switches in effect (the preset with its overrides) and the prices
    preset <thrifty|normal|rich|simulation>
                              pick a preset; keeps the overrides
    set <key> <value>         override one switch, e.g.  set world_turns.every_moves 8
                                                         set npc_agents.on false
                                                         set npc_agents.characters.grukk false
    unset <key>               drop an override, so the preset's value applies again
    reset                     drop every override

It writes games/<id>/settings.json and then checks the game with `rpg.py validate`. The game master
can't run it: it isn't in the project's allowed commands, so the owner stays in charge of what play costs.
Without --game it changes the game being played.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "rules"))
import content  # noqa: E402
import rpg  # noqa: E402


def fail(msg):
    print("settings: %s" % msg)
    sys.exit(1)


def value_of(text):
    """'true' / 'false' / a whole number / anything else as text."""
    low = text.lower()
    if low in ("true", "on", "yes"):
        return True
    if low in ("false", "off", "no"):
        return False
    try:
        return int(text)
    except ValueError:
        return text


def main(argv):
    if "--game" in argv:
        i = argv.index("--game")
        game = argv[i + 1] if i + 1 < len(argv) else ""
        argv = argv[:i] + argv[i + 2:]
    else:
        game = rpg.active_game()
    if game not in content.list_games():
        fail("no game %r (games: %s)" % (game, ", ".join(content.list_games())))
    if not argv:
        print(__doc__.strip())
        return 2
    rpg.choose_game(game)
    path = content.game_dir() / "settings.json"
    own = json.loads(path.read_text()) if path.is_file() else {"preset": "normal", "overrides": {}}
    own.setdefault("overrides", {})
    presets = content.kit_presets()
    cmd, args = argv[0], argv[1:]

    if cmd == "show":
        rpg.cmd_settings([])
        if own["overrides"]:
            print("OVERRIDES: %s" % json.dumps(own["overrides"]))
        return 0
    if cmd == "preset":
        if not args or args[0] not in presets:
            fail("preset <%s>" % "|".join(presets))
        own["preset"] = args[0]
    elif cmd in ("set", "unset"):
        if not args or (cmd == "set" and len(args) < 2):
            fail("%s <key>%s" % (cmd, " <value>" if cmd == "set" else ""))
        keys = args[0].split(".")
        node, base = own["overrides"], presets["normal"]
        for k in keys[:-1]:
            if not isinstance(base, dict) or k not in base:
                fail("unknown setting %r" % args[0])
            base = base[k]
            node = node.setdefault(k, {})
        last = keys[-1]
        is_character = keys[:2] == ["npc_agents", "characters"] and len(keys) == 3
        if not is_character and (not isinstance(base, dict) or last not in base):
            fail("unknown setting %r" % args[0])
        if cmd == "set":
            node[last] = value_of(args[1])
        else:
            node.pop(last, None)
    elif cmd == "reset":
        own["overrides"] = {}
    else:
        fail("unknown command %r" % cmd)

    rpg.write_json(path, own)
    check = subprocess.run([sys.executable, str(ROOT / "rules" / "rpg.py"), "validate", "--game", game],
                           capture_output=True, text=True)
    if check.returncode != 0:
        print(check.stdout.strip())
        fail("the change was saved, but the game no longer validates; fix it with `unset` or by hand")
    rpg.choose_game(game)
    rpg.cmd_settings([])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
