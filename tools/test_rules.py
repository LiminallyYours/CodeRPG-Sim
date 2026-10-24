#!/usr/bin/env python3
"""Tests for the rules engine, run against a throwaway copy of the project:  python3 tools/test_rules.py

Each test gets a fresh temp copy of rules/, games/ and proposals/ with an empty state/, and drives
rules/rpg.py as the game master would, through its command line. The real save is never touched.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAMES = sorted(p.name for p in (ROOT / "games").glob("*") if (p / "world.md").is_file())


class Engine(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="rpg-test-"))
        for d in ("rules", "games", "proposals", "tools", ".claude/hooks", "mod/sounds"):
            shutil.copytree(ROOT / d, self.dir / d, ignore=shutil.ignore_patterns("__pycache__", "*.json.tmp"))
        (self.dir / "state").mkdir()
        for stale in (self.dir / "proposals").glob("*.json"):
            stale.unlink()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def rpg(self, *args, seed=None, ok=True):
        """Run one rpg.py command; by default it must succeed. Returns its output."""
        env = dict(os.environ)
        env.pop("RPG_SEED", None)
        if seed is not None:
            env["RPG_SEED"] = str(seed)
        r = subprocess.run([sys.executable, "rules/rpg.py", *args], cwd=self.dir, env=env,
                           capture_output=True, text=True, timeout=30)
        self.assertNotIn("Traceback", r.stderr, r.stderr)
        if ok is not None:
            self.assertEqual(r.returncode == 0, ok, "%s -> %d\n%s" % (" ".join(args), r.returncode, r.stdout))
        return r.stdout

    def save(self):
        return json.loads((self.dir / "state" / "save.json").read_text())

    def player(self, save):
        """The only player's record in a save (the shipped games' runs have one player until they get a cast)."""
        return next(iter(save["players"].values()))

    def me(self):
        return self.player(self.save())

    def meter(self):
        return self.save()["view"]["meter"]["left"]

    def meter_file(self):
        return json.loads((self.dir / "state" / "meter.json").read_text())["left"]

    def set_meter(self, left):
        self.write("state/meter.json", json.dumps({"left": left}))

    def run_py(self, script, *args, stdin=""):
        r = subprocess.run([sys.executable, script, *args], cwd=self.dir, input=stdin, capture_output=True, text=True, timeout=30)
        self.assertNotIn("Traceback", r.stderr, r.stderr)
        return r

    def write(self, rel, text):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    # ---------------------------------------------------------------- the kit and its games

    def test_every_game_validates(self):
        out = self.rpg("validate")
        for g in GAMES:
            self.assertIn("CONTENT OK: %s:" % g, out)

    def test_validate_catches_typos_in_a_games_json(self):
        self.write("games/%s/look.json" % GAMES[0], json.dumps({"palete": {}, "tabs": ["here", "inventory"]}))
        out = self.rpg("validate", "--game", GAMES[0], ok=False)
        self.assertIn("unknown key 'palete'", out)
        self.assertIn("unknown tab 'inventory'", out)
        self.write("games/%s/balance.json" % GAMES[0], json.dumps({"npc": {"memory_lnes": 3}}))
        self.assertIn("unknown key 'memory_lnes'", self.rpg("validate", "--game", GAMES[0], ok=False))

    def test_a_new_game_belongs_to_its_game_and_carries_its_look(self):
        for g in GAMES:
            self.rpg("game", "switch", g)
            self.rpg("newgame", seed=1)
            s = self.save()
            self.assertEqual(s["version"], 10)
            self.assertEqual(s["game"], g)
            self.assertEqual(s["view"]["game"]["id"], g)
            look = s["view"]["look"]
            for key in ("palette", "stat_labels", "stat_short", "currency", "tabs", "phrases"):
                self.assertIn(key, look)

    def test_the_station_names_its_own_stats_and_money(self):
        self.rpg("game", "switch", "flooded_station")
        out = self.rpg("newgame", seed=2)
        self.assertIn("Grit (might)", out)
        self.assertIn("Credits", out)
        self.assertEqual(self.save()["view"]["look"]["palette"]["accent"], "#4fc3c7")

    def test_a_games_settings_and_balance_override_only_what_they_name(self):
        self.rpg("game", "switch", "flooded_station")
        self.rpg("newgame", seed=3)
        moves = ["north", "south"] * 2
        outs = [self.rpg("move", d) for d in moves]
        self.assertIn("WORLD TURN DUE", outs[3])  # the station's settings: every 4 moves, not the preset's 5
        self.assertNotIn("WORLD TURN DUE", "".join(outs[:3]))
        s = self.save()
        self.assertEqual(s["view"]["carry_limit"], 6 + 2 * self.player(s)["stats"]["might"])  # its balance.json: carry_base 6

    def test_an_old_save_is_refused_and_a_new_game_replaces_it(self):
        self.write("state/save.json", json.dumps({"version": 6, "adventure": "The Dark Lighthouse", "status": "playing"}))
        self.assertIn("from the original CodeRPG", self.rpg("look", ok=False))
        self.assertIn("an old save", self.rpg("game", "list"))
        self.rpg("newgame", seed=4)
        self.assertEqual(self.save()["version"], 10)

    def test_switching_games_keeps_each_ones_save(self):
        first, second = GAMES[0], GAMES[1]
        self.rpg("game", "switch", first)
        self.rpg("newgame", seed=5)
        start = self.me()["location"]
        exit_dir = next(iter(self.me()["map"][start]["exits"]))
        self.rpg("move", exit_dir)
        moved_to = self.me()["location"]
        self.assertIn("No game yet", self.rpg("game", "switch", second))
        self.assertFalse((self.dir / "state" / "save.json").exists())
        self.rpg("newgame", seed=6)
        self.assertEqual(self.save()["game"], second)
        listing = self.rpg("game", "list")
        self.assertIn("* %s" % second, listing)
        self.assertIn("playing, 1 move in", listing)
        self.assertIn("The saved game continues", self.rpg("game", "switch", first))
        self.assertEqual(self.me()["location"], moved_to)
        self.assertTrue((self.dir / "state" / "shelf" / ("%s.json" % second)).is_file())
        self.assertIn("ALREADY PLAYING", self.rpg("game", "switch", first))
        self.assertIn("one of", self.rpg("game", "switch", "no_such_game", ok=False))

    def test_show_leaves_out_if_sections_that_dont_hold(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=7)
        flags = self.save()["flags"]
        craving = "craves_honey" if "craves_honey" in flags else "craves_fish"
        other = "craves_fish" if craving == "craves_honey" else "craves_honey"
        out = self.rpg("show", "characters", "grukk")
        self.assertIn("## If %s" % craving, out)
        self.assertNotIn("## If %s" % other, out)
        self.assertIn("## GM only", out)
        self.assertIn("## If %s" % other, self.rpg("show", "characters", "grukk", "--all"))
        self.assertIn("## Opening", self.rpg("show", "world"))
        self.assertIn("kind must be one of", self.rpg("show", "nonsense", "x", ok=False))

    def test_look_and_move_print_the_room_as_it_reads_now(self):
        self.rpg("game", "switch", "dark_lighthouse")
        out = self.rpg("newgame", seed=7)
        room = out[out.index("ROOM TEXT:"):]
        self.assertIn("A cobbled square opens onto a stone quay.", room)
        self.assertIn("## If not lamp_lit and not fleet_arrived", room)
        self.assertNotIn("## If lamp_lit\n", room)
        self.assertIn("## Details", room)
        self.assertNotIn("exits:", room)  # the front matter is look's own lines, not repeated
        self.assertNotIn("show rooms", out)
        self.rpg("flag", "set", "lamp_lit")
        room = self.rpg("look").split("ROOM TEXT:")[1]
        self.assertIn("## If lamp_lit\n", room)
        self.assertNotIn("## If not lamp_lit and not fleet_arrived", room)
        self.rpg("flag", "unset", "lamp_lit")
        out = self.rpg("move", "west")
        self.assertLess(out.index("MOVED west."), out.index("ROOM TEXT:"))
        self.assertIn("The base of the lighthouse is a round stone room", out.split("ROOM TEXT:")[1])
        self.assertFalse(out.split("ROOM TEXT:")[1].lstrip().startswith(("STATUS", "FLAGS", "INVENTORY")))  # prose only
        # the room text says where it ends, so a command chained after a move can be told from the prose
        self.assertTrue(out.rstrip().endswith("\nEND OF ROOM TEXT"))
        # a generated room's text comes the same way
        self.rpg("move", "east")
        room = {"id": "mooring_steps", "name": "The Mooring Steps", "direction": "south", "description": "Slick stone steps run down to the boats."}
        self.write("proposals/r.json", json.dumps(room))
        self.rpg("generate", "room", "proposals/r.json")
        out = self.rpg("move", "south")
        self.assertIn("LOCATION: The Mooring Steps (mooring_steps) [generated]", out)
        self.assertIn("Slick stone steps run down to the boats.", out.split("ROOM TEXT:")[1])
        # and in the other game
        self.rpg("game", "switch", "flooded_station")
        out = self.rpg("newgame", seed=31)
        start = self.me()["location"]
        body = (self.dir / "games" / "flooded_station" / "rooms" / ("%s.md" % start)).read_text().split("\n---", 1)[1].strip()
        self.assertIn(body.split("\n")[0], out.split("ROOM TEXT:")[1])

    def test_quests_finish_and_fail_by_their_flags(self):
        self.rpg("game", "switch", "flooded_station")
        self.rpg("newgame", seed=8)
        self.rpg("flag", "set", "pump_running")
        quest = self.save()["view"]["quests"][0]
        self.assertTrue(quest["complete"])
        # a fresh game where the tide wins: walk back and forth until the clock runs out
        self.rpg("newgame", seed=9)
        for i in range(40):
            self.rpg("move", "north" if i % 2 == 0 else "south")
            if "station_lost" in self.save()["flags"]:  # not the output: room text names the flag in its headings
                break
        quest = self.save()["view"]["quests"][0]
        self.assertTrue(quest["failed"])
        self.assertIn("station_lost", self.save()["flags"])

    def test_the_same_seed_rolls_the_same_run(self):
        a = self.rpg("newgame", seed=11).splitlines()[:4]
        b = self.rpg("newgame", seed=11).splitlines()[:4]
        self.assertEqual(a, b)

    # ---------------------------------------------------------------- seeds and daily worlds (no RPG_SEED)

    def play(self, seed):
        """A fixed little session from a named seed: what it rolled and printed."""
        outs = [self.rpg("newgame", seed)]
        for d in ("north", "south", "north"):
            outs.append(self.rpg("move", d))
        outs += [self.rpg("check", "wits", "normal") for _ in range(3)]
        outs.append(self.rpg("roll", "3d6"))
        s = self.save()
        return s["run"]["rolls"], s["run"]["variants"], s["run"]["clock"], s["run"]["weather"], outs[1:]

    def test_a_named_seed_rolls_the_same_run_for_anyone(self):
        for g in GAMES:
            self.rpg("game", "switch", g)
            first, again = self.play("kestrel-0042"), self.play("kestrel-0042")
            self.assertEqual(first, again)
            self.assertNotEqual(first, self.play("kestrel-0043"))

    def test_each_roll_moves_the_stream_on(self):
        self.rpg("newgame", "moss-1")
        checks = [self.rpg("check", "wits", "normal") for _ in range(6)]
        self.assertGreater(len(set(checks)), 1, "checks in a seeded run must not repeat one result")
        self.assertGreater(self.save()["run"]["dice_n"], 6)

    def test_a_seed_belongs_to_its_game(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", "same-seed")
        lighthouse = [self.rpg("roll", "1d1000") for _ in range(3)]
        self.rpg("game", "switch", "flooded_station")
        self.rpg("newgame", "same-seed")
        self.assertNotEqual(lighthouse, [self.rpg("roll", "1d1000") for _ in range(3)])

    def test_daily_world_and_the_run_label(self):
        import datetime
        today = datetime.date.today().isoformat()
        out = self.rpg("newgame", "daily")
        self.assertIn("SEED: %s, today's daily world" % today, out)
        s = self.save()
        self.assertEqual(s["run"]["seed"], today)
        self.assertEqual(s["view"]["run_label"], "%s · daily world" % today)
        self.rpg("newgame", "Ember-7")
        self.assertEqual(self.save()["view"]["run_label"], "%s · seed ember-7" % today)
        self.rpg("newgame")
        self.assertRegex(self.save()["run"]["seed"], r"^[a-z]+-\d{4}$")
        self.assertIn("a seed is", self.rpg("newgame", "no spaces!", ok=False))

    # ---------------------------------------------------------------- proposals never crash the script

    def test_malformed_proposals_are_refused_not_crashed(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=12)
        for text in ("not json", "[1, 2]", '{"id": 5}', '{"id": "ok_name", "name": "A", "tier": "laser"}',
                     '{"id": "x"}', '{"items": "lots"}'):
            p = self.write("proposals/bad.json", text)
            out = self.rpg("generate", "item", str(p.relative_to(self.dir)), ok=False)
            self.assertIn("REFUSED", out)
            self.assertFalse(p.exists(), "a refused proposal file is cleaned up")


    # ---------------------------------------------------------------- the meter and the owner's switches

    def at_the_lighthouse(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=20)
        self.rpg("move", "west")  # Ysolde, an agent character, is here

    def test_every_preset_has_the_same_switches(self):
        presets = json.loads((ROOT / "rules" / "presets.json").read_text())

        def shape(d):
            return {k: shape(v) if isinstance(v, dict) and k != "characters" else type(v).__name__ for k, v in d.items()}
        self.assertEqual({"thrifty", "normal", "rich", "simulation"}, set(presets))
        for name, p in presets.items():
            self.assertEqual(shape(p), shape(presets["normal"]), name)

    def test_the_simulation_preset_switches_off_the_deadline_curses_and_free_growth(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=42)
        v = self.save()
        self.assertIsNone(v["run"]["clock"])
        self.assertEqual(v["view"]["settings"]["generation"]["kinds"], ["extras", "characters", "side_quests"])
        self.rpg("flag", "set", "mirror_cursed")
        self.assertNotIn("CURSE:", self.rpg("look"))
        self.assertIn("rounds.clock must be move or round", self.settings_tool("set", "rounds.clock", "tick", ok=False))
        self.assertIn("unknown setting 'memory.recent'", self.settings_tool("set", "memory.recent", "3", ok=False))

    def test_only_extras_drain_the_meter_and_it_refills(self):
        self.at_the_lighthouse()
        self.rpg("meter", "refill")
        self.assertEqual(self.meter(), 30)
        for args in (("look",), ("move", "east"), ("move", "west"), ("check", "wits", "normal"),
                     ("npc-brief", "ysolde"), ("show", "characters", "ysolde")):
            self.rpg(*args)
        self.assertEqual(self.meter(), 30, "baseline play, authored agents included, is free")
        self.rpg("move", "east")
        self.rpg("world-brief", "room")  # generating something new: 2
        self.assertEqual(self.meter(), 28)
        self.rpg("world-brief", "turn")  # a world turn: 2
        self.assertEqual(self.meter(), 26)
        self.set_meter(3)
        self.rpg("world-brief", "room")
        self.assertEqual(self.meter(), 1)
        self.assertIn("spent until the next session", self.rpg("world-brief", "room", ok=False))
        self.assertEqual(self.meter(), 1, "a refused extra costs nothing")
        self.rpg("meter", "refill")
        self.assertEqual(self.meter(), 30)

    def test_a_flag_that_ends_someones_scene_still_lets_them_speak_this_turn(self):
        # bug 2026-10-23: `flag set grukk_cowed && npc-brief grukk` was refused, and the GM voiced Grukk itself
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=5)
        self.rpg("move", "east")
        self.assertIn("grukk [agent]", self.rpg("move", "east"))
        self.rpg("flag", "set", "grukk_cowed")
        brief = self.rpg("npc-brief", "grukk")
        self.assertIn("You are Grukk", brief)
        self.assertIn("parting", brief)
        # the next look starts a new turn: he's gone from the bridge now
        self.assertNotIn("grukk", self.rpg("look").split("CHARACTERS HERE:")[1].split("\n")[0])
        self.assertIn("not in this scene", self.rpg("npc-brief", "grukk", ok=False))
        # and leaving the room never carries anyone along
        self.rpg("flag", "unset", "grukk_cowed")
        self.rpg("look")
        self.rpg("move", "west")
        self.assertIn("not in this scene", self.rpg("npc-brief", "grukk", ok=False))
        self.assertEqual(self.save()["version"], 10)

    def test_a_spent_meter_stops_the_extras_and_play_goes_on(self):
        self.at_the_lighthouse()
        self.set_meter(0)
        look = self.rpg("look")
        self.assertIn("METER SPENT", look)
        self.assertIn("ysolde [agent]", look)  # agents are baseline: the meter never silences them
        self.assertIn("You are Ysolde", self.rpg("npc-brief", "ysolde"))
        self.rpg("move", "east")
        self.assertNotIn("may grow", self.rpg("look"))
        self.assertIn("spent", self.rpg("world-brief", "room", ok=False))
        for d in ("north", "south") * 4:  # moves still work, and no world turn falls due
            self.assertNotIn("WORLD TURN DUE", self.rpg("move", d))

    def test_the_meter_outlasts_new_games_and_switches(self):
        self.at_the_lighthouse()
        self.set_meter(12)
        self.rpg("newgame", seed=21)
        self.assertEqual(self.meter(), 12)
        self.rpg("game", "switch", "flooded_station")
        self.rpg("newgame", seed=22)
        self.assertEqual(self.meter(), 12)
        self.assertIn("METER: Power 12/30", self.rpg("look"))

    def settings_tool(self, *args, ok=True):
        r = self.run_py("tools/settings.py", *args)
        self.assertEqual(r.returncode == 0, ok, r.stdout)
        return r.stdout

    def test_the_owners_switches_are_enforced_by_the_rules(self):
        self.at_the_lighthouse()
        self.settings_tool("preset", "thrifty")
        look = self.rpg("look")
        self.assertIn("ysolde [minor, agent resting]", look)
        self.assertIn("METER: Lamp oil 10/10", look)
        self.assertIn("off in this game", self.rpg("world-brief", "turn", ok=False))
        self.assertIn("can appear in this game", self.rpg("world-brief", "character", ok=False))
        self.settings_tool("preset", "normal")
        self.settings_tool("set", "npc_agents.characters.ysolde", "false")
        self.assertIn("ysolde [minor, agent resting]", self.rpg("look"))
        self.settings_tool("unset", "npc_agents.characters.ysolde")
        self.assertIn("ysolde [agent]", self.rpg("look"))
        self.settings_tool("set", "world_turns.on", "false")
        self.rpg("newgame", seed=23)
        self.assertNotIn("WORLD TURN DUE", "".join(self.rpg("move", d) for d in ("north", "south") * 3))
        self.settings_tool("reset")
        self.assertIn("NPC AGENTS: on", self.rpg("settings"))
        self.assertIn("unknown setting", self.settings_tool("set", "npc_agents.loudness", "3", ok=False))
        self.assertIn("preset <", self.settings_tool("preset", "lavish", ok=False))

    def test_the_owners_cap_on_generation_holds(self):
        self.at_the_lighthouse()
        self.settings_tool("set", "generation.max_per_run", "1")
        self.rpg("move", "east")
        self.write("proposals/a.json", json.dumps({"id": "tin_whistle", "name": "Tin Whistle", "description": "A dented whistle.", "tier": "trinket"}))
        self.rpg("generate", "item", "proposals/a.json")
        self.rpg("move", "north")
        self.write("proposals/b.json", json.dumps({"id": "bone_dice", "name": "Bone Dice", "description": "Two worn dice.", "tier": "trinket"}))
        self.assertIn("as much as it may (1)", self.rpg("generate", "item", "proposals/b.json", ok=False))

    def test_validate_catches_bad_settings(self):
        g = "games/dark_lighthouse/settings.json"
        self.write(g, json.dumps({"preset": "lavish"}))
        self.assertIn("unknown preset 'lavish'", self.rpg("validate", "--game", "dark_lighthouse", ok=False))
        self.write(g, json.dumps({"preset": "normal", "overrides": {"world_turns": {"evry_moves": 3}},
                                  "extra": 1}))
        out = self.rpg("validate", "--game", "dark_lighthouse", ok=False)
        self.assertIn("unknown key 'evry_moves'", out)
        self.assertIn("unknown key 'extra'", out)
        self.write(g, json.dumps({"overrides": {"npc_agents": {"characters": {"pell": False, "nobody": False}}}}))
        out = self.rpg("validate", "--game", "dark_lighthouse", ok=False)
        self.assertIn("'pell' is minor", out)
        self.assertIn("unknown character 'nobody'", out)

    def test_opening_a_session_refills_the_meter(self):
        self.at_the_lighthouse()
        self.set_meter(9)
        self.assertEqual(self.run_py(".claude/hooks/session_start.py", stdin="{}").stdout, "")
        self.assertEqual(self.meter_file(), 30)
        self.assertEqual(self.meter(), 30)  # and the save's view shows it

    def test_the_save_carries_the_meter_and_switches_for_the_interface(self):
        self.at_the_lighthouse()
        v = self.save()["view"]
        self.assertEqual(set(v["meter"]), {"left", "capacity", "state"})
        self.assertEqual(v["settings"]["preset"], "normal")
        self.assertEqual(v["settings"]["prices"], {"generate": 2, "world_turn": 2, "craft": 2, "build": 3, "reuse": 1, "promote": 2, "scene": 2})
        self.set_meter(9)
        self.rpg("world-brief", "turn")
        self.assertEqual(self.save()["view"]["meter"]["state"], "low")  # 7 of 30
        self.set_meter(2)
        self.rpg("world-brief", "turn")
        self.assertEqual(self.save()["view"]["meter"]["state"], "spent")


    # ---------------------------------------------------------------- Stage 3: what the look needs from content

    def test_terrain_and_cards_reach_the_view(self):
        self.at_the_lighthouse()
        s = self.save()
        self.assertEqual(self.player(s)["map"]["lighthouse"]["terrain"], "stone")
        self.assertEqual(self.player(s)["map"]["harbor_square"]["terrain"], "water")
        ysolde = next(c for c in s["view"]["characters_here"] if c["id"] == "ysolde")
        self.assertRegex(ysolde["card"], r"^#[0-9a-f]{6}$")
        look = s["view"]["look"]
        for key in ("terrain", "sounds"):
            self.assertIn(key, look)
        self.assertIn("phases", look["phrases"])
        self.rpg("game", "switch", "flooded_station")
        self.rpg("newgame", seed=30)
        look = self.save()["view"]["look"]
        self.assertIn("metal", look["terrain"])  # a game adds its own terrain kinds
        self.assertEqual(look["sounds"]["step"], "splash")

    def test_validate_checks_terrain_cards_sounds_and_times(self):
        g = "games/dark_lighthouse"
        room = self.dir / g / "rooms" / "coast_road.md"
        room.write_text(room.read_text().replace("terrain: grass", "terrain: lava"))
        ch = self.dir / g / "characters" / "pell.md"
        ch.write_text(ch.read_text().replace("card: #d19a5a", "card: not a color!"))
        look = json.loads((self.dir / g / "look.json").read_text())
        look["sounds"] = {"step": "kazoo"}
        look["palette"]["accent_by_time"]["teatime"] = "#123456"
        look["speaker_colors"] = ["#8fae4a", "sage"]
        self.write(g + "/look.json", json.dumps(look))
        out = self.rpg("validate", "--game", "dark_lighthouse", ok=False)
        self.assertIn("terrain 'lava' isn't in the look's terrain", out)
        self.assertIn("characters/pell.md: card must be a color", out)
        self.assertIn("no kit sound 'kazoo'", out)
        self.assertIn("'teatime' is not one of world.md's times", out)
        self.assertNotIn("speaker_colors", out, "a named color is a color")
        look["speaker_colors"] = ["#8fae4a", "#12"]
        self.write(g + "/look.json", json.dumps(look))
        self.assertIn("look.json speaker_colors: must be a list of colors", self.rpg("validate", "--game", "dark_lighthouse", ok=False))
        look["speaker_colors"] = ["#8fae4a"]
        look["sections"] = {"you": "", "pockets": "POCKETS"}
        self.write(g + "/look.json", json.dumps(look))
        out = self.rpg("validate", "--game", "dark_lighthouse", ok=False)
        self.assertIn("look.json sections: you needs a label", out)
        self.assertIn("look.json sections: unknown key 'pockets'", out)
        look["sections"] = {}
        look["tab_keys"] = {"map": "g", "journal": "J", "here": "h"}
        self.write(g + "/look.json", json.dumps(look))
        out = self.rpg("validate", "--game", "dark_lighthouse", ok=False)
        self.assertIn("tab_keys: map's key must be one lowercase letter other than l and g", out)
        self.assertIn("tab_keys: journal's key must be one lowercase letter", out)
        look["tab_keys"] = {"map": "h", "journal": "j", "here": "h"}
        self.write(g + "/look.json", json.dumps(look))
        self.assertIn("look.json tab_keys: two tabs share a key", self.rpg("validate", "--game", "dark_lighthouse", ok=False))

    def test_rooms_carry_their_picture_as_a_mosaic(self):
        sys.path.insert(0, str(self.dir / "rules"))
        import base64
        import png
        self.at_the_lighthouse()
        pic = self.save()["view"]["picture"]
        self.assertEqual(pic["source"], "games/dark_lighthouse/art/lighthouse.png")
        self.assertEqual((pic["width"], pic["height"]), (44, 28))
        self.assertEqual(len(base64.b64decode(pic["rgb"])), 44 * 28 * 3)
        # a hand-made picture of another size replaces it: cropped to shape around its middle, averaged down
        red, blue = (200, 0, 0), (0, 0, 200)
        rows = [[red if x < 66 else blue for x in range(132)] for _ in range(70)]   # 132x70: wider than 44:28, sides trimmed
        png.write(self.dir / "games/dark_lighthouse/art/lighthouse.png", 132, 70, rows)
        self.step_out_and_back()
        rgb = base64.b64decode(self.save()["view"]["picture"]["rgb"])
        self.assertEqual(tuple(rgb[0:3]), red)
        self.assertEqual(tuple(rgb[43 * 3:44 * 3]), blue)
        # without its own picture, a room takes its terrain's; with none for its terrain, none at all
        (self.dir / "games/dark_lighthouse/art/lighthouse.png").unlink()
        self.step_out_and_back()
        self.assertRegex(self.save()["view"]["picture"]["source"], r"^rules/art/terrain/stone-\d\.png$")
        for f in (self.dir / "rules/art/terrain").glob("stone-*.png"):
            f.unlink()
        self.step_out_and_back()
        self.assertIsNone(self.save()["view"]["picture"])

    def test_pictures_from_other_programs_decode(self):
        """Palette, grey and transparent PNGs, with every row filter, read back as the pixels they hold."""
        sys.path.insert(0, str(self.dir / "rules"))
        import struct
        import zlib
        import png

        def paeth(a, b, c):
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            return a if pa <= pb and pa <= pc else b if pb <= pc else c

        def encode(w, h, depth, ctype, lines, bpp, plte=b"", interlace=0):
            out, prev = b"", bytes(len(lines[0]))
            for y, line in enumerate(lines):
                kind = y % 5
                f = bytearray()
                for x, v in enumerate(line):
                    a = line[x - bpp] if x >= bpp else 0
                    b, c = prev[x], prev[x - bpp] if x >= bpp else 0
                    f.append((v - (0, a, b, (a + b) >> 1, paeth(a, b, c))[kind]) & 255)
                out += bytes([kind]) + bytes(f)
                prev = line

            def chunk(k, body):
                return struct.pack(">I", len(body)) + k + body + struct.pack(">I", zlib.crc32(k + body) & 0xFFFFFFFF)
            return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, ctype, 0, 0, interlace))
                    + (chunk(b"PLTE", plte) if plte else b"") + chunk(b"IDAT", zlib.compress(out)) + chunk(b"IEND", b""))

        w, h = 8, 6
        colors = [(10 * x + 3 * y, 200 - 20 * x, 7 * y) for y in range(h) for x in range(w)]
        rgba = encode(w, h, 8, 6, [bytes(c for x in range(w) for c in colors[y * w + x] + (255,)) for y in range(h)], 4)
        self.assertEqual([px for row in png.pixels(rgba)[2] for px in row], colors)
        half = encode(w, h, 8, 6, [bytes(c for x in range(w) for c in (200, 100, 50, 128)) for y in range(h)], 4)
        self.assertEqual(png.pixels(half)[2][0][0], (100, 50, 25))  # half see-through, over black
        plte = bytes([0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0, 255])
        idx = [[(x + y) % 4 for x in range(w)] for y in range(h)]
        packed = [bytes((r[i] << 4) | r[i + 1] for i in range(0, w, 2)) for r in idx]   # 4 bits a pixel
        pal = png.pixels(encode(w, h, 4, 3, packed, 1, plte))[2]
        self.assertEqual(pal[1][2], (0, 0, 255))
        grey = png.pixels(encode(w, h, 8, 0, [bytes(x * 30 for x in range(w)) for _ in range(h)], 1))[2]
        self.assertEqual(grey[3][5], (150, 150, 150))
        self.assertIsNone(png.problem(encode(64, 48, 8, 6, [bytes(4 * 64)] * 48, 4)))
        self.assertIn("interlaced", png.problem(encode(64, 48, 8, 2, [bytes(3 * 64)] * 48, 3, interlace=1)))

    def step_out_and_back(self):
        """Leave the lighthouse and come back: a move saves, so the view (and its picture) is made afresh."""
        self.rpg("move", "east")
        self.rpg("move", "west")

    def test_validate_checks_pictures(self):
        sys.path.insert(0, str(self.dir / "rules"))
        import png
        g = "games/dark_lighthouse/art/"
        png.write(self.dir / (g + "nowhere.png"), 44, 28, [[(0, 0, 0)] * 44] * 28)
        png.write(self.dir / (g + "lighthouse.png"), 40, 40, [[(0, 0, 0)] * 40] * 40)
        png.write(self.dir / (g + "coast_road.png"), 300, 200, [[(0, 0, 0)] * 300] * 200)
        self.write(g + "gull_tavern.png", "not a picture")
        (self.dir / (g + "terrain")).mkdir()
        png.write(self.dir / (g + "terrain/lava-1.png"), 44, 28, [[(0, 0, 0)] * 44] * 28)
        out = self.rpg("validate", "--game", "dark_lighthouse", ok=False)
        self.assertIn("art/nowhere.png: unknown room 'nowhere'", out)
        self.assertIn("art/lighthouse.png: 40x40; a picture is 4:3 or wider", out)
        self.assertIn("art/coast_road.png: 300 pixels wide; a picture is at most 256", out)
        self.assertIn("art/gull_tavern.png: not a PNG file", out)
        self.assertIn("art/terrain/lava-1.png: names no terrain of the look's", out)
        # the kit's own terrain pictures are checked too
        self.write("rules/art/terrain/water-9.png", "nope")
        self.assertIn("kit: rules/art/terrain/water-9.png: not a PNG file", self.rpg("validate", "--game", "flooded_station", ok=False))

    def test_a_generated_room_takes_a_terrain(self):
        self.at_the_lighthouse()
        self.rpg("move", "east")  # Harbor Square, water, may grow south
        room = {"id": "mooring_steps", "name": "The Mooring Steps", "direction": "south", "description": "Slick stone steps."}
        self.write("proposals/r.json", json.dumps(room))
        self.rpg("generate", "room", "proposals/r.json")
        self.rpg("move", "south")
        self.assertEqual(self.me()["map"]["mooring_steps"]["terrain"], "water")  # the room it opens off
        picture = self.save()["view"]["picture"]["source"]
        self.assertRegex(picture, r"^rules/art/terrain/water-\d\.png$")  # no picture of its own: the kit's for its terrain
        self.rpg("move", "north")
        self.rpg("move", "south")
        self.assertEqual(self.save()["view"]["picture"]["source"], picture, "the same room always gets the same one")
        self.rpg("game", "switch", "flooded_station")
        self.rpg("newgame", seed=31)
        self.rpg("move", "north")
        self.rpg("move", "west")  # the Lab Wing may grow north
        bad = {"id": "specimen_store", "name": "Specimen Store", "direction": "north", "terrain": "lava", "description": "Shelves of jars."}
        self.write("proposals/s.json", json.dumps(bad))
        self.assertIn("terrain must be one of", self.rpg("generate", "room", "proposals/s.json", ok=False))
        good = dict(bad, terrain="metal")
        self.write("proposals/s.json", json.dumps(good))
        self.rpg("generate", "room", "proposals/s.json")
        self.rpg("move", "north")
        self.assertEqual(self.me()["map"]["specimen_store"]["terrain"], "metal")
        self.assertEqual(self.me()["map"]["specimen_store"]["made_by"], "world")
        self.assertRegex(self.save()["view"]["picture"]["source"], r"^games/flooded_station/art/terrain/metal-\d\.png$")  # the game's own


    # ---------------------------------------------------------------- Stage 4: curses

    def test_curse_examples_hold_and_the_mod_has_the_same_ones(self):
        sys.path.insert(0, str(ROOT / "rules"))
        import curse
        vectors = json.loads((ROOT / "rules" / "curse_vectors.json").read_text())
        for v in vectors:
            self.assertEqual(curse.apply(v["effect"], v["input"]), v["output"], v)
        mod_copy = (ROOT / "mod" / "tests" / "curse_vectors.ts").read_text().split("=", 1)[1]
        self.assertEqual(json.loads(mod_copy), vectors, "mod/tests/curse_vectors.ts must match rules/curse_vectors.json")
        for bad in ("sing", "word_limit 0", "suffix over", ""):
            self.assertRaises(ValueError, curse.parse, bad)

    def test_a_curse_takes_hold_by_its_flag_and_its_cure_lifts_it(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=40)
        self.assertEqual(json.loads(self.rpg("curse-text", "go north"))["text"], "go north")
        self.rpg("flag", "set", "mirror_cursed")
        look = self.rpg("look")
        self.assertIn("CURSE: The Backwards Tongue", look)
        self.assertIn("in reverse word order", look)
        self.assertEqual(self.save()["view"]["curses"], [{"id": "backwards_tongue", "name": "The Backwards Tongue", "effect": "reverse_words"}])
        out = json.loads(self.rpg("curse-text", "I ask Pell for help"))
        self.assertEqual(out, {"curses": ["The Backwards Tongue"], "text": "help for Pell ask I"})
        self.rpg("flag", "set", "tongue_salted")
        self.assertNotIn("CURSE:", self.rpg("look"))
        self.assertEqual(self.save()["view"]["curses"], [])
        self.rpg("flag", "unset", "tongue_salted")
        self.assertIn("CURSE:", self.rpg("look"))
        self.rpg("newgame", seed=41)  # no curse survives a new game
        self.assertEqual(self.save()["view"]["curses"], [])

    def test_validate_insists_every_curse_has_a_cause_and_a_reachable_cure(self):
        d = "games/dark_lighthouse/curses/"
        self.write(d + "hiccups.md", "---\nname: Hiccups\neffect: sing loudly\ncaused_by: mirror_cursed\n---\nHic.\n")
        out = self.rpg("validate", "--game", "dark_lighthouse", ok=False)
        self.assertIn("effect must be", out)
        self.assertIn("needs cured_by", out)
        self.write(d + "hiccups.md", "---\nname: Hiccups\neffect: word_limit 2\ncaused_by: mirror_cursed\ncured_by: hiccups_gone\n---\nHic.\n")
        self.assertIn("nothing in the game sets 'hiccups_gone'", self.rpg("validate", "--game", "dark_lighthouse", ok=False))
        self.write(d + "hiccups.md", "---\nname: Hiccups\neffect: word_limit 2\ncaused_by: mirror_cursed\ncured_by: has_no_such_thing\n---\nHic.\n")
        self.assertIn("unknown item 'no_such_thing'", self.rpg("validate", "--game", "dark_lighthouse", ok=False))


    # ---------------------------------------------------------------- Stage 5: the player leaves a mark

    def order(self, maker, proposal, ok=True):
        self.rpg("world-brief", "craft", maker)
        self.write("proposals/c.json", json.dumps(proposal))
        return self.rpg("generate", "craft", "proposals/c.json", ok=ok)

    def test_a_maker_takes_an_order_and_paying_makes_it_the_players(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=40)
        look = self.rpg("look")
        self.assertIn("MAKERS HERE: morwen makes trinket, light weapon", look)
        hook = {"id": "gaff_hook", "name": "Gaff Hook", "description": "A barbed hook on a short ash haft.", "tier": "weapon"}
        out = self.order("morwen", hook, ok=False)
        self.assertIn("tier must be one of trinket, light_weapon", out)  # outside her trade
        self.assertEqual(self.meter(), 28)  # the brief was paid for once
        self.write("proposals/c.json", json.dumps(dict(hook, tier="light_weapon")))
        out = self.rpg("generate", "craft", "proposals/c.json")  # the retry needs no new brief
        self.assertIn("COMMISSIONED: Gaff Hook (gaff_hook), light weapon, from Morwen", out)
        self.assertIn("PRICE: 3 coins, or in trade: smoked_fish", out)
        self.assertNotIn("gaff_hook", self.me()["inventory"])  # not theirs until paid
        self.assertIn("ORDERS WAITING: gaff_hook", self.rpg("look"))
        self.write("proposals/c.json", json.dumps(dict(hook, id="other_hook", name="Other Hook", tier="trinket")))
        self.assertIn("no order is open", self.rpg("generate", "craft", "proposals/c.json", ok=False))  # one brief, one order
        self.assertIn("COINS -3 -> 0", self.rpg("pay", "gaff_hook"))
        s = self.save()
        self.assertIn("gaff_hook", self.player(s)["inventory"])
        self.assertTrue(next(i for i in s["view"]["items"] if i["id"] == "gaff_hook")["own"])
        self.assertEqual(s["run"]["generated"], 0)  # orders don't use up the world's own allowance
        self.assertEqual(self.rpg("show", "items", "gaff_hook").count("made_by: player"), 1)
        self.assertIn("damage: 1d4", self.rpg("show", "items", "gaff_hook"))  # stats from the tier
        self.assertIn("no unpaid order", self.rpg("pay", "gaff_hook", ok=False))

    def test_a_maker_can_turn_an_order_down_and_takes_trade_in_kind(self):
        self.rpg("game", "switch", "flooded_station")
        self.rpg("newgame", seed=41)
        self.rpg("move", "north")  # the Common Deck: Bucket
        out = self.order("bucket", {"refuse": "Pump: NOT MY DEPARTMENT"}, ok=False)
        self.assertIn("Bucket turns the order down: Pump: NOT MY DEPARTMENT", out)
        self.assertIsNone(self.save()["run"]["ordering"])
        self.order("bucket", {"id": "scrap_whistle", "name": "Scrap Whistle", "description": "A whistle filed from conduit.", "tier": "trinket"})
        self.assertIn("takes no diving_knife", self.rpg("pay", "scrap_whistle", "diving_knife", ok=False))
        self.assertIn("not carrying sardine_tin", self.rpg("pay", "scrap_whistle", "sardine_tin", ok=False))
        self.rpg("gain", "sardine_tin")
        coins = self.me()["stats"]["coins"]
        self.rpg("move", "south")
        self.assertIn("isn't here", self.rpg("pay", "scrap_whistle", "sardine_tin", ok=False))
        self.rpg("move", "north")
        self.assertIn("PAID WITH: sardine_tin", self.rpg("pay", "scrap_whistle", "sardine_tin"))
        s = self.save()
        self.assertEqual(self.player(s)["stats"]["coins"], coins)
        self.assertNotIn("sardine_tin", self.player(s)["inventory"])
        self.assertIn("scrap_whistle", self.player(s)["inventory"])

    def test_the_owners_crafting_switch_and_limit_hold(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=42)
        self.settings_tool("set", "crafting.on", "false")
        self.assertNotIn("MAKERS HERE", self.rpg("look"))
        self.assertIn("no makers take orders", self.rpg("world-brief", "craft", "morwen", ok=False))
        self.assertEqual(self.meter(), 30)
        self.settings_tool("set", "crafting.on", "true")
        self.settings_tool("set", "crafting.max_per_run", "1")
        self.order("morwen", {"id": "cork_float", "name": "Cork Float", "description": "A painted cork float.", "tier": "trinket"})
        self.assertNotIn("MAKERS HERE", self.rpg("look"))
        self.assertIn("as much work as they will", self.rpg("world-brief", "craft", "morwen", ok=False))
        self.assertIn("CRAFTING: on, at most 1 orders per run", self.rpg("settings"))
        self.assertIn("isn't here to take an order", self.rpg("world-brief", "craft", "pell", ok=False))

    def test_the_save_holds_players_and_as_names_who_acts(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=43)
        s = self.save()
        self.assertEqual(list(s["players"]), ["player"])
        self.assertEqual(s["view"]["players"]["player"]["location"], s["players"]["player"]["location"])
        self.assertIn("STATUS: playing", self.rpg("look", "--as", "player"))
        self.assertIn("no one called 'nell' is playing", self.rpg("look", "--as", "nell", ok=False))
        self.assertIn("--as needs a player id", self.rpg("look", "--as", ok=False))

    def test_a_save_from_the_original_game_is_refused(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=43)
        s = self.save()
        s["version"] = 9
        self.write("state/save.json", json.dumps(s))
        self.assertIn("from the original CodeRPG", self.rpg("look", ok=False))
        self.assertIn("an old save", self.rpg("game", "list"))

    def test_validate_checks_makers(self):
        d = "games/dark_lighthouse/characters/morwen.md"
        text = (self.dir / d).read_text()
        self.write(d, text.replace("  - light_weapon", "  - harpoon").replace("  - smoked_fish", "  - kipper"))
        out = self.rpg("validate", "--game", "dark_lighthouse", ok=False)
        self.assertIn("makes 'harpoon', which isn't an item tier", out)
        self.assertIn("unknown item 'kipper'", out)
        kit = json.loads((self.dir / "rules/balance.json").read_text())
        del kit["generation"]["craft_price"]["tonic"]
        self.write("rules/balance.json", json.dumps(kit))
        self.write(d, text)
        self.assertIn("no price for the item tier 'tonic'", self.rpg("validate", "--game", "dark_lighthouse", ok=False))


    def test_a_builder_builds_where_they_stand_and_it_takes_a_few_moves(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=50)
        look = self.rpg("look")
        self.assertIn("BUILD SPOTS HERE: southwest: the bare stone footing", look)
        self.assertIn("may grow: south ", look)  # the quay steps; the footing is kept for the player
        self.rpg("world-brief", "build", "morwen")
        self.assertEqual(self.meter(), 27)
        loft = {"id": "net_loft", "name": "The Net-Loft", "direction": "south", "description": "A tarred loft."}
        self.write("proposals/b.json", json.dumps(loft))
        self.assertIn("it can only go southwest", self.rpg("generate", "build", "proposals/b.json", ok=False))
        self.write("proposals/b.json", json.dumps(dict(loft, direction="southwest", items=[{"id": "a_net"}])))
        self.assertIn("starts empty", self.rpg("generate", "build", "proposals/b.json", ok=False))
        self.write("proposals/b.json", json.dumps(dict(loft, direction="southwest")))
        out = self.rpg("generate", "build", "proposals/b.json")
        self.assertIn("COMMISSIONED: The Net-Loft (net_loft), to be built southwest of here by Morwen", out)
        self.assertIn("PRICE: 5 coins.", out)
        self.assertIn("not enough coins", self.rpg("pay", "net_loft", ok=False))
        self.rpg("coins", "+5")
        self.assertIn("builds for coins only", self.rpg("pay", "net_loft", "worn_dagger", ok=False))
        self.assertIn("ready in 3 moves", self.rpg("pay", "net_loft"))
        look = self.rpg("look")
        self.assertIn("BEING BUILT: net_loft (The Net-Loft), southwest of harbor_square: ready in 3 moves", look)
        self.assertNotIn("BUILD SPOTS HERE", look)  # the spot is taken
        self.assertNotIn("net_loft", self.save()["run"]["rooms"])  # it doesn't exist yet
        outs = [self.rpg("move", d) for d in ("north", "south", "north")]
        self.assertNotIn("is finished", outs[0] + outs[1])
        self.assertIn("BUILT: The Net-Loft (net_loft) is finished, southwest of Harbor Square, built for the player by Morwen", outs[2])
        # the map shows it at once, though the player is in the Gull: Harbor Square's entry is redrawn (bug 2026-10-23)
        square = self.me()["map"]["harbor_square"]
        self.assertEqual(square["exits"].get("southwest"), "net_loft")
        self.assertEqual(square["neighbors"].get("net_loft"), "The Net-Loft")
        self.assertIn("exit southwest -> The Net-Loft", self.rpg("move", "south"))
        self.rpg("move", "southwest")
        s = self.save()
        self.assertEqual(self.player(s)["map"]["net_loft"]["made_by"], "player")
        self.assertEqual(s["run"]["generated"], 0)
        self.assertTrue(any("The Net-Loft is finished" in r for r in s["run"]["rumors"]))  # people hear of it
        self.assertNotIn("BUILD SPOTS", self.rpg("look"))  # a built place offers no build spots of its own

    def test_the_world_grows_anywhere_free_but_not_too_deep(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=51)
        self.rpg("move", "west")  # the Lighthouse lists no expand: so any free cardinal way
        self.assertIn("may grow: north, west ", self.rpg("look"))  # south is the footing's square, kept for building
        for n, d in enumerate(("north", "north")):
            room = {"id": "cliff_path_%d" % n, "name": "Cliff Path %d" % n, "direction": d, "description": "A narrow path."}
            self.write("proposals/r.json", json.dumps(room))
            self.rpg("world-brief", "room")
            self.rpg("generate", "room", "proposals/r.json")
            self.rpg("move", d)
        self.assertEqual(self.save()["run"]["rooms"]["cliff_path_1"]["meta"]["depth"], 2)
        self.assertNotIn("may grow", self.rpg("look"))  # max_depth 2
        self.rpg("move", "south")
        self.assertIn("may grow: west ", self.rpg("look"))  # a generated room grows on: not back south, nor east onto the Gull
        w = self.dir / "games/dark_lighthouse/world.md"
        w.write_text(w.read_text().replace("rooms: anywhere", "rooms: yes"))
        self.assertNotIn("may grow", self.rpg("look"))  # marked: only authored rooms' expand: directions

    def test_validate_checks_build_spots(self):
        d = "games/dark_lighthouse/rooms/harbor_square.md"
        text = (self.dir / d).read_text()
        self.write(d, text.replace("  southwest: the bare", "  north: the bare"))
        self.assertIn("build direction 'north' is already an exit", self.rpg("validate", "--game", "dark_lighthouse", ok=False))
        road = "games/dark_lighthouse/rooms/coast_road.md"
        self.write(road, (self.dir / road).read_text().replace("expand: north\n", "expand: north\nbuild:\n  northwest: a lean-to\n"))
        self.write(d, text)
        out = self.rpg("validate", "--game", "dark_lighthouse", ok=False)
        self.assertIn("coast_road.md: build direction 'northwest' would land on another room's map square", out)  # the Gull's
        self.assertIn("coast_road.md: has build spots but no builder", out)
        self.write(d, text.replace("  - morwen\n", ""))
        self.assertIn("has build spots but no builder", self.rpg("validate", "--game", "dark_lighthouse", ok=False))


    # ---------------------------------------------------------------- 5.3 the library

    def library(self, game="dark_lighthouse"):
        return json.loads((self.dir / "state" / "library" / ("%s.json" % game)).read_text())["entries"]

    def tamsin(self):
        """Generate Old Tamsin (with wares) and her side quest, and finish it."""
        self.write("proposals/c.json", json.dumps({
            "id": "old_tamsin", "name": "Old Tamsin", "role": "a fishwife mending creels", "personality": "Sharp and kind.",
            "speech": "Clipped.", "knows": ["The light has been out three nights."], "wants": "Her creels mended.",
            "trades": [{"item": {"id": "creel_charm", "name": "Creel Charm", "description": "A knot of red wool.", "tier": "trinket"}, "price": 2}],
            "tier": "weak"}))
        self.rpg("generate", "character", "proposals/c.json")
        self.write("proposals/q.json", json.dumps({
            "id": "tamsins_creels", "name": "Tamsin's Creels", "giver": "old_tamsin", "summary": "Fetch twine.",
            "objectives": [{"text": "Bring her twine", "done_when": "side_tamsins_creels_done"}], "reward": {"coins": 1, "item": None}}))
        self.rpg("generate", "quest", "proposals/q.json")

    def test_a_befriended_person_comes_back_in_the_next_game_remembering_one_line(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=60)
        self.tamsin()
        lib = self.library()
        self.assertEqual(sorted(lib), ["old_tamsin"])  # one entry; her wares ride with her; side quests aren't kept
        self.assertEqual([b["id"] for b in lib["old_tamsin"]["bundle"]], ["creel_charm"])
        self.assertIsNone(lib["old_tamsin"]["friend"])
        self.rpg("remember", "old_tamsin", "Brought twine for my creels without being asked twice.")
        self.rpg("flag", "set", "side_tamsins_creels_done")
        self.assertEqual(self.library()["old_tamsin"]["friend"]["line"], "Brought twine for my creels without being asked twice.")
        out = self.rpg("newgame", seed=61)
        self.assertIn("FROM EARLIER RUNS (they're part of this world now): Old Tamsin (a friend, at harbor_square", out)
        self.assertIn("old_tamsin [minor, generated]", out)
        s = self.save()
        self.assertEqual(s["npc_memory"]["old_tamsin"], {"player": ["Brought twine for my creels without being asked twice."]})
        self.assertIn("creel_charm", s["run"]["items"])  # her wares
        self.assertNotIn("tamsins_creels", s["run"]["quests"])  # the quest was that run's
        self.assertEqual(s["run"]["generated"], 0)  # what comes back doesn't use up this run's allowance
        self.assertNotIn("side_tamsins_creels_done", s["flags"])

    def test_the_world_brings_back_a_library_entry_for_less(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=62)
        self.rpg("world-brief", "extra")
        self.write("proposals/e.json", json.dumps({"id": "jory_dockhand", "name": "Jory", "role": "a young dockhand", "look": "Freckled.",
                                                  "speech": "Fast.", "knows": ["The boats are late."]}))
        self.rpg("generate", "extra", "proposals/e.json")
        self.rpg("newgame", seed=63)
        self.rpg("meter", "refill")
        self.assertNotIn("jory", self.rpg("world-brief", "character"))  # an extra isn't offered as a character
        brief = self.rpg("world-brief", "extra")
        self.assertIn("- jory_dockhand: Jory (a young dockhand): Freckled", brief)
        self.assertIn('{"reuse": "<id from that list>"}', brief)
        self.assertEqual(self.meter(), 26)
        self.write("proposals/e.json", json.dumps({"reuse": "jory_dockhand"}))
        out = self.rpg("generate", "extra", "proposals/e.json")
        self.assertIn("brought back from an earlier run", out)
        self.assertEqual(self.meter_file(), 27)  # 2 for the brief, 1 back: reuse costs 1
        self.assertEqual(self.library()["jory_dockhand"]["runs"], 2)
        self.rpg("newgame", seed=69)
        self.write("proposals/e.json", json.dumps({"reuse": "jory_dockhand"}))
        self.rpg("generate", "extra", "proposals/e.json")  # without a brief, reuse costs its own price
        self.assertEqual(self.meter_file(), 26)
        self.rpg("newgame", seed=64)
        self.assertIn("FORGOTTEN", self.run_py("tools/library.py", "forget", "jory_dockhand").stdout)
        self.assertNotIn("jory", self.rpg("world-brief", "extra"))
        self.write("proposals/e.json", json.dumps({"reuse": "jory_dockhand"}))
        self.assertIn("isn't in the library", self.rpg("generate", "extra", "proposals/e.json", ok=False))

    def test_a_place_the_player_built_stands_in_the_next_game(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=65)
        self.rpg("world-brief", "build", "morwen")
        self.write("proposals/b.json", json.dumps({"id": "net_loft", "name": "The Net-Loft", "direction": "southwest", "description": "A tarred loft."}))
        self.rpg("generate", "build", "proposals/b.json")
        self.rpg("coins", "+5")
        self.rpg("pay", "net_loft")
        for d in ("north", "south", "north", "south"):
            self.rpg("move", d)
        self.assertEqual(self.library()["net_loft"]["worth_keeping"], "built by the player")
        out = self.rpg("newgame", seed=66)
        self.assertIn("The Net-Loft (the player's, southwest of Harbor Square)", out)
        self.assertIn("exit southwest -> The Net-Loft", out)
        self.assertNotIn("BUILD SPOTS HERE", out)
        self.rpg("move", "southwest")
        self.assertEqual(self.me()["map"]["net_loft"]["made_by"], "player")

    def test_the_owner_keeps_an_entry_for_good_and_a_bad_keep_changes_nothing(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=67)
        self.write("proposals/r.json", json.dumps({"id": "mooring_steps", "name": "The Mooring Steps", "direction": "south",
                                                  "description": "Slick stone steps.", "items": [{"id": "boat_hook", "name": "Boat Hook",
                                                  "description": "A long hook.", "tier": "weapon"}]}))
        self.rpg("generate", "room", "proposals/r.json")
        self.rpg("library", "suggest", "mooring_steps", "The player keeps coming back to fish here.")
        listing = self.run_py("tools/library.py", "list").stdout
        self.assertIn("the game master suggests keeping: The player keeps coming back to fish here.", listing)
        lib_file = self.dir / "state/library/dark_lighthouse.json"
        good = lib_file.read_text()
        bad = json.loads(good)
        bad["entries"]["mooring_steps"]["bundle"][0]["record"]["meta"]["damage"] = "lots"
        lib_file.write_text(json.dumps(bad))
        square = (self.dir / "games/dark_lighthouse/rooms/harbor_square.md").read_text()
        r = self.run_py("tools/library.py", "keep", "mooring_steps")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nothing was changed", r.stdout)
        self.assertEqual((self.dir / "games/dark_lighthouse/rooms/harbor_square.md").read_text(), square)
        self.assertFalse((self.dir / "games/dark_lighthouse/rooms/mooring_steps.md").exists())
        lib_file.write_text(good)
        r = self.run_py("tools/library.py", "keep", "mooring_steps")
        self.assertEqual(r.returncode, 0, r.stdout)
        square = (self.dir / "games/dark_lighthouse/rooms/harbor_square.md").read_text()
        self.assertIn("  south: mooring_steps", square)
        self.assertIn("expand: no\n", square)  # its only expand: direction is an exit now
        room = (self.dir / "games/dark_lighthouse/rooms/mooring_steps.md").read_text()
        self.assertIn("exits:\n  north: harbor_square", room)
        self.assertIn("items:\n  - boat_hook", room)
        self.assertNotIn("generated", room)
        self.assertIn("damage: 1d6", (self.dir / "games/dark_lighthouse/items/boat_hook.md").read_text())
        self.assertNotIn("mooring_steps", self.library())
        self.assertIn("CONTENT OK: dark_lighthouse", self.rpg("validate"))

    def test_the_library_keeps_to_its_size(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.write("games/dark_lighthouse/balance.json", json.dumps({"library": {"max_entries": 2}}))
        self.rpg("newgame", seed=68)
        for n, ways in enumerate(((), ("north",), ("south", "east"))):  # one find each in three rooms
            for d in ways:
                self.rpg("move", d)
            self.write("proposals/i.json", json.dumps({"id": "shell_%d" % n, "name": "Shell %d" % n, "description": "A shell.", "tier": "trinket"}))
            self.rpg("generate", "item", "proposals/i.json")
        self.assertEqual(sorted(self.library()), ["shell_1", "shell_2"])  # the oldest went


    # ---------------------------------------------------------------- 5.4 promotion

    def hob(self):
        """Old Hob, a generated extra in the Gull."""
        self.rpg("move", "north")
        self.write("proposals/e.json", json.dumps({"id": "hob_netman", "name": "Old Hob", "role": "an old fisherman",
                                                  "look": "White beard.", "speech": "Slow.", "knows": ["He fished fifty years."]}))
        self.rpg("generate", "extra", "proposals/e.json")

    def test_a_generated_person_the_player_keeps_coming_back_to_gets_their_own_agent(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=70)
        self.hob()
        out = self.rpg("talk", "hob_netman")
        self.assertIn("TALK: voice Old Hob yourself, from this (conversation 1):", out)
        self.assertIn("## How they speak", out)
        self.assertIn("conversation 1", self.rpg("talk", "hob_netman"))  # the same scene counts once
        self.assertIn("authored", self.rpg("talk", "pell", ok=False))
        for d in ("south", "north"):
            self.rpg("move", d)
        self.assertIn("conversation 2", self.rpg("talk", "hob_netman"))
        self.rpg("remember", "hob_netman", "Sat with me by the fire three nights running.")
        for d in ("south", "north"):
            self.rpg("move", d)
        meter = self.meter()
        out = self.rpg("talk", "hob_netman")
        self.assertIn("PROMOTED: Old Hob now speaks through their own agent", out)
        self.assertEqual(self.meter(), meter - 2)
        self.assertIn("hob_netman [agent, generated]", self.rpg("look"))
        brief = self.rpg("npc-brief", "hob_netman")
        self.assertIn("You are Old Hob, an old fisherman.", brief)
        self.assertIn("- Sat with me by the fire three nights running.", brief)
        self.assertNotIn("GM only", brief)
        self.assertIn("own agent", self.rpg("talk", "hob_netman"))
        person = next(p for p in self.save()["view"]["people"] if p["id"] == "hob_netman")
        self.assertTrue(person["promoted"])
        e = self.library()["hob_netman"]
        self.assertTrue(e["promoted"])
        self.assertEqual(e["friend"]["line"], "Sat with me by the fire three nights running.")
        out = self.rpg("newgame", seed=71)
        self.assertIn("Old Hob (a friend, at gull_tavern", out)
        self.rpg("move", "north")
        self.assertIn("hob_netman [agent, generated]", self.rpg("look"))  # still their own voice

    def test_the_owner_decides_whether_and_when_people_are_promoted(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.settings_tool("preset", "thrifty")
        self.rpg("newgame", seed=72)
        self.hob()
        for _ in range(4):
            self.assertIn("TALK: voice Old Hob yourself", self.rpg("talk", "hob_netman"))
            self.rpg("move", "south")
            self.rpg("move", "north")
        self.settings_tool("preset", "normal")
        self.settings_tool("set", "promotion.after_conversations", "1")
        self.settings_tool("set", "promotion.max_per_run", "0")
        self.assertIn("TALK: voice Old Hob yourself", self.rpg("talk", "hob_netman"))
        self.settings_tool("set", "promotion.max_per_run", "1")
        self.settings_tool("set", "npc_agents.on", "false")
        self.assertIn("TALK: voice Old Hob yourself", self.rpg("talk", "hob_netman"))  # no agents: no promotion
        self.settings_tool("set", "npc_agents.on", "true")
        self.assertIn("PROMOTED", self.rpg("talk", "hob_netman"))
        self.assertIn("PROMOTION: on, at most 1 per run, after 1 conversations", self.rpg("settings"))

    # ---------------------------------------------------------------- Stage 7: people with plans

    def world_turn(self, proposal, ok=True):
        self.write("proposals/wt.json", json.dumps(proposal))
        return self.rpg("world-turn", "proposals/wt.json", ok=ok)

    def test_people_with_plans_act_off_screen_and_the_player_hears_only_whats_near(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=80)
        self.rpg("move", "east")  # the Coast Road, next to the bridge, far from the lighthouse
        brief = self.rpg("world-brief", "turn")
        self.assertIn("grukk (Grukk), now at Greywater Bridge: forage", brief)
        self.assertIn("ysolde (Ysolde), now at The Lighthouse: to_quay", brief)
        self.assertIn('"plans": [{"who"', brief)
        out = self.world_turn({"plans": [{"who": "grukk", "step": "forage"}, {"who": "ysolde", "step": "sleep"}]})
        self.assertIn("SIGNAL", out)
        self.assertIn("Heavy bare feet thud", out)
        self.assertIn("NOW HERE: Grukk", out)
        self.assertNotIn("snoring", out, "the lighthouse is out of earshot")
        s = self.save()
        self.assertIn("grukk [agent]", self.rpg("look"))
        self.assertEqual([(x["text"][:16], x["kind"]) for x in s["view"]["signals"]], [("Heavy bare feet ", "plan")])
        self.assertIn("They say Ysolde finally slept, barred in her tower like a hermit.", s["run"]["rumors"])
        self.assertIn("lighthouse [BLOCKED: needs not ysolde_asleep]", self.rpg("move", "west").replace("The Lighthouse", "lighthouse"))
        self.assertNotIn("Plan:", self.rpg("show", "characters", "ysolde"))
        self.assertIn("Plan: sleep", self.rpg("show", "characters", "ysolde", "--all"))
        # only open steps, one each, and nobody the player is with
        self.assertIn("listed as open", self.world_turn({"plans": [{"who": "ysolde", "step": "to_quay"}]}, ok=False))
        self.assertIn("at most one", self.world_turn({"plans": [{"who": "ysolde", "step": "wake"}] * 2}, ok=False))
        self.assertIn("listed as open", self.world_turn({"plans": [{"who": "morwen", "step": "x"}]}, ok=False))
        self.assertIn("must be a list", self.world_turn({"plans": "wake"}, ok=False))
        self.rpg("flag", "unset", "ysolde_asleep")  # the player hammers on the door
        self.rpg("move", "west")
        self.assertNotIn("ysolde (Ysolde), now at", self.rpg("world-brief", "turn"), "someone the player is with never acts")
        self.assertIn("listed as open", self.world_turn({"plans": [{"who": "ysolde", "step": "to_quay"}]}, ok=False))

    def test_a_plan_moves_someone_and_the_rooms_follow(self):
        self.rpg("game", "switch", "flooded_station")
        self.rpg("newgame", seed=81)
        self.rpg("move", "north")  # the Common Deck, with Bucket
        self.assertIn("bucket [agent]", self.rpg("look"))
        self.rpg("move", "south")
        self.rpg("world-brief", "turn")
        out = self.world_turn({"plans": [{"who": "bucket", "step": "mop_upstairs"}, {"who": "halloran", "step": "check_tanks"}]})
        self.assertIn("OFF-SCREEN", out)  # the landing is two rooms away from both
        self.rpg("move", "north")
        self.assertIn("CHARACTERS HERE: none", self.rpg("look"))
        self.assertIn("cargo hoist's cage is up", self.rpg("show", "rooms", "common_deck"))
        look = self.rpg("move", "west")
        self.assertIn("halloran [agent]", look)
        self.rpg("move", "east")
        look = self.rpg("move", "up")
        self.assertIn("bucket [agent]", look)
        self.assertNotIn("halloran", look.split("CHARACTERS HERE:")[1].split("\n")[0])

    def test_the_owner_can_keep_people_from_following_plans(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.settings_tool("set", "world_turns.plans", "false")
        self.rpg("newgame", seed=82)
        self.assertNotIn("People with plans", self.rpg("world-brief", "turn"))
        self.assertIn("nobody has one now", self.world_turn({"plans": [{"who": "grukk", "step": "forage"}]}, ok=False))
        self.assertIn("people with plans: off", self.rpg("settings"))
        self.settings_tool("preset", "thrifty")
        self.assertIn("WORLD TURNS: off, every 8 moves; people with plans: off", self.rpg("settings"))

    def test_validate_checks_plans(self):
        g = "games/dark_lighthouse"
        ch = (self.dir / g / "characters" / "grukk.md").read_text()
        bad = ch.replace("## GM only", """## Plan: Nap time
does: naps

## Plan: steal (if not lamp_lit)
does: grabs something
sets: lamp_lit
near: a crash

## Plan: wander
does: wanders off
sets: troll_away
near: footsteps
mood: grumpy

## Plan: forage
does: twice
sets: grukk_stuck
near: stuck

## GM only""")
        self.write(g + "/characters/grukk.md", bad)
        out = self.rpg("validate", "--game", "dark_lighthouse", ok=False)
        for want in ("a plan heading is 'Plan: <step id>", "'lamp_lit' is part of the main story",
                     "plan flags are the character's own: grukk_<word>, not 'troll_away'", "unknown line 'mood: grumpy'",
                     "two plan steps are called 'forage'", "no plan step clears 'grukk_stuck'",
                     "nothing outside this file uses 'grukk_stuck'"):
            self.assertIn(want, out)
        self.write(g + "/characters/grukk.md", ch)
        room = (self.dir / g / "rooms" / "coast_road.md").read_text()
        self.write(g + "/rooms/coast_road.md", room.replace("  - grukk (if grukk_foraging and not grukk_friend", "  - grukk (if not grukk_friend"))
        self.assertIn("grukk stands in coast_road and greywater_bridge at once", self.rpg("validate", "--game", "dark_lighthouse", ok=False))
        self.write(g + "/rooms/coast_road.md", room.replace("  - grukk (if grukk_foraging", "  - pell (if grukk_foraging"))
        self.assertIn("after forage (grukk_foraging), grukk stands nowhere", self.rpg("validate", "--game", "dark_lighthouse", ok=False))
        self.write(g + "/rooms/coast_road.md", room)
        morwen = (self.dir / g / "characters" / "morwen.md").read_text()
        self.write(g + "/characters/morwen.md", morwen + "\n## Plan: nap\ndoes: naps\nsets: morwen_nap\nnear: a snore\n")
        self.assertIn("plans are for major characters", self.rpg("validate", "--game", "dark_lighthouse", ok=False))

    # ---------------------------------------------------------------- Stage 7: side scenes

    def at_the_mopping_dispute(self, seed=90):
        self.rpg("game", "switch", "flooded_station")
        self.rpg("newgame", seed=seed)
        self.rpg("flag", "set", "bucket_upstairs")  # as if Bucket's own plan had brought it up
        self.rpg("move", "north")
        return self.rpg("move", "up")

    def test_a_side_scene_is_offered_played_once_and_rewarded(self):
        self.rpg("meter", "refill")
        look = self.at_the_mopping_dispute()
        self.assertIn("SCENE HERE: mopping_dispute", look)
        self.assertNotIn("Plan:", self.rpg("show", "scenes", "mopping_dispute"))
        self.assertIn("SCENE STARTED: The Mopping Dispute, with Bucket and Dr. Ines Halloran. Up to 6 replies",
                      self.rpg("scene", "start", "mopping_dispute"))
        self.assertEqual(self.meter(), 28)
        self.assertIn("SCENE PLAYING: mopping_dispute (0 of 6", self.rpg("look"))
        for n in range(1, 7):
            brief = self.rpg("npc-brief", "bucket" if n % 2 else "halloran")
            self.assertIn("This is reply %d of the scene's 6." % n, brief)
            again = self.rpg("npc-brief", "bucket" if n % 2 else "halloran")  # looked at twice: still the same reply
            self.assertIn("This is reply %d of the scene's 6." % n, again)
        self.assertIn("It's the last one", brief)
        self.assertNotIn("A little scene", self.rpg("npc-brief", "bucket"), "past the cap, the brief is plain again")
        coins = self.me()["stats"]["coins"]
        out = self.rpg("scene", "end", "mopping_dispute", "reward")
        self.assertIn("REWARD: +1", out)
        s = self.save()
        self.assertEqual(self.player(s)["stats"]["coins"], coins + 1)
        self.assertIn("Refereed an argument", s["run"]["chronicle"][-1])
        self.assertNotIn("SCENE", self.rpg("look"))
        self.assertIn("already played", self.rpg("scene", "start", "mopping_dispute", ok=False))
        self.assertIn("isn't playing", self.rpg("scene", "end", "mopping_dispute", ok=False))

    def test_walking_away_ends_a_scene_without_reward(self):
        self.at_the_mopping_dispute()
        self.rpg("scene", "start", "mopping_dispute")
        coins = self.me()["stats"]["coins"]
        self.assertIn("SCENE OVER: the player walked away from The Mopping Dispute", self.rpg("move", "down"))
        self.assertEqual(self.me()["stats"]["coins"], coins)
        self.assertEqual(self.save()["run"]["scenes"]["mopping_dispute"]["status"], "done")

    def test_a_scene_needs_both_here_the_moment_and_the_owners_say(self):
        self.rpg("game", "switch", "flooded_station")
        self.rpg("newgame", seed=91)
        self.rpg("move", "north")
        self.rpg("move", "up")  # Halloran alone
        self.assertNotIn("SCENE HERE", self.rpg("look"))
        self.assertIn("aren't both here", self.rpg("scene", "start", "mopping_dispute", ok=False))
        self.rpg("flag", "set", "bucket_upstairs")
        self.rpg("flag", "set", "halloran_dozing")
        self.assertIn("moment isn't right", self.rpg("scene", "start", "mopping_dispute", ok=False))
        self.rpg("flag", "unset", "halloran_dozing")
        self.settings_tool("set", "npc_agents.characters.bucket", "false")
        self.assertIn("speaks through the game master", self.rpg("scene", "start", "mopping_dispute", ok=False))
        self.settings_tool("unset", "npc_agents.characters.bucket")
        self.settings_tool("set", "side_scenes.on", "false")
        self.assertNotIn("SCENE HERE", self.rpg("look"))
        self.assertIn("side scenes are off", self.rpg("scene", "start", "mopping_dispute", ok=False))
        self.settings_tool("unset", "side_scenes.on")
        self.set_meter(1)
        self.assertIn("spent", self.rpg("scene", "start", "mopping_dispute", ok=False))
        self.set_meter(30)
        self.settings_tool("set", "side_scenes.max_per_run", "0")
        self.assertIn("all the side scenes", self.rpg("scene", "start", "mopping_dispute", ok=False))
        self.settings_tool("preset", "thrifty")
        self.assertIn("SIDE SCENES: off", self.rpg("settings"))

    def test_validate_checks_scenes(self):
        g = "games/dark_lighthouse/scenes/shiniest_thing.md"
        good = (self.dir / g).read_text()
        bad = (good.replace("  - ysolde\n", "  - pell\n").replace("reward: coins 1", "reward: coins 9")
               .replace("## How it ends", "## Ending").replace("Otherwise", "Then flag set grukk_friend. Otherwise"))
        self.write(g, bad)
        out = self.rpg("validate", "--game", "dark_lighthouse", ok=False)
        for want in ("pell is minor", "pell is never in harbor_square", "reward is 'none' or 'coins N' with N from 1 to 2",
                     "needs a ## How it ends section", "needs a ## pell section", "scenes never change story flags"):
            self.assertIn(want, out)
        self.write(g, good.replace("where: harbor_square", "where: gull_tavern"))
        self.assertIn("grukk is never in gull_tavern", self.rpg("validate", "--game", "dark_lighthouse", ok=False))


    # ---------------------------------------------------------------- Stage 8: new worlds

    def test_the_kits_own_games_are_kit_complete(self):
        for g in GAMES:
            self.assertIn("(kit-complete)", self.rpg("validate", "--game", g, "--kit-complete"))

    def test_validate_checks_a_game_can_be_played_through(self):
        g = "games/dark_lighthouse"
        road, pell = self.dir / g / "rooms/coast_road.md", self.dir / g / "characters/pell.md"
        road.write_text(road.read_text().replace("east: greywater_bridge", "east: greywater_bridge (if bridge_mended or has_rope)"))
        pell.write_text(pell.read_text().replace("`coins -2`", "`coins 2`").replace("`gain honey_cake`", "`gain honey_cak`")
                        .replace("`flag set tongue_salted`", "`flag sett tongue_salted`"))
        out = self.rpg("validate", "--game", "dark_lighthouse", ok=False)
        for want in ("rooms/coast_road.md: a condition uses 'bridge_mended', but nothing in the game sets it",
                     "rooms/coast_road.md: condition 'has_rope': no item 'rope'",
                     "characters/pell.md: `coins 2`: use coins +N or coins -N",
                     "characters/pell.md: `gain honey_cak`: no item 'honey_cak'",
                     "characters/pell.md: `flag sett tongue_salted`: use flag set|unset"):
            self.assertIn(want, out)

    def test_kit_complete_says_what_a_world_lacks(self):
        w = self.dir / "drafts" / "w"
        shutil.copytree(self.dir / "games" / "flooded_station", w)
        for f in ("scenes/mopping_dispute.md", "curses/radio_habit.md", "rooms/the_landing.md", "look.json"):
            (w / f).unlink()
        (w / "notes.txt").write_text("scribbles")
        q = w / "quests" / "ride_out_the_surge.md"
        q.write_text(q.read_text().replace(" or evacuated\nfailed_by", "\nfailed_by").replace("## After the ending", "## Afterwards"))
        out = self.rpg("validate", "--dir", "drafts/w", "--kit-complete", ok=False)
        for want in ("kit: needs a side scene", "kit: needs a curse", "kit: needs a look.json of its own",
                     "kit: unexpected file notes.txt", "kit: quests/ride_out_the_surge.md needs a ## After the ending section",
                     "unknown room 'the_landing'"):
            self.assertIn(want, out)
        self.write("drafts/w/characters/bucket.md", "---\nname: Bucket\n")  # front matter never closed
        self.assertIn("checking stopped early: characters/bucket.md: front matter has no closing '---'",
                      self.rpg("validate", "--dir", "drafts/w", ok=False))
        self.assertIn("REFUSED", self.rpg("validate", "--dir", "drafts/nowhere", ok=False))

    def forge_draft(self, sentence=("a", "smugglers", "cove")):
        out = self.rpg("forge", "start", *sentence)
        d = out.split("FORGE STARTED: ")[1].split(".")[0]
        return d, out

    def finish_draft(self, d, title="The Smugglers Cove", game="dark_lighthouse"):
        world = self.dir / "state" / "forge" / d / "world"
        shutil.copytree(self.dir / "games" / game, world, dirs_exist_ok=True)
        wf = world / "world.md"
        wf.write_text(wf.read_text().replace("title: The Dark Lighthouse", "title: %s" % title)
                      .replace("title: The Flooded Station", "title: %s" % title))
        (self.dir / "state" / "forge" / d / "READY").write_text(title + "\n")

    def test_a_new_world_is_quoted_and_installed_as_a_forged_game(self):
        self.rpg("meter", "refill")
        self.assertIn("FORGE: a new world can be made. It doesn't use the meter.", self.rpg("forge", "quote"))
        d, out = self.forge_draft()
        self.assertIn('The player asked for: "a smugglers cove"', out)
        self.assertIn("validate --dir state/forge/%s/world --kit-complete" % d, out)
        self.assertEqual(30, self.meter_file())  # new worlds don't use the meter
        self.assertIn("only one at a time", self.rpg("forge", "start", ok=False))
        self.rpg("newgame")
        self.assertNotIn("NEW WORLD READY", self.rpg("look"))
        self.finish_draft(d)
        self.assertIn("NEW WORLD READY: %s" % d, self.rpg("look"))
        out = self.rpg("forge", "install", d)
        self.assertIn("INSTALLED: The Smugglers Cove (smugglers_cove)", out)
        signal = self.save()["view"]["signals"][-1]
        self.assertEqual("A new world has taken shape: The Smugglers Cove. /game smugglers_cove goes there.", signal["text"])
        self.assertEqual("world", signal["kind"], "the interface toasts only this kind")
        self.assertFalse((self.dir / "state" / "forge" / d).exists())
        home = self.dir / "state" / "worlds" / "smugglers_cove"
        self.assertEqual("normal", json.loads((home / "settings.json").read_text())["preset"])
        self.assertEqual("a smugglers cove", json.loads((home / "forged.json").read_text())["sentence"])
        self.assertIn("smugglers_cove: The Smugglers Cove (no game yet), a world forged in play", self.rpg("game", "list"))
        self.assertIn("SWITCHED", self.rpg("game", "switch", "smugglers_cove"))
        self.assertIn("NEW GAME: The Smugglers Cove", self.rpg("newgame"))
        self.assertIn("in state/worlds/smugglers_cove/", self.rpg("game", "show"))
        # the kit's checks cover only games/: a forged world that breaks later never fails them
        (home / "rooms" / "coast_road.md").write_text("---\nexits:\n  west: nowhere\n---\n")
        self.assertNotIn("smugglers_cove", self.rpg("validate"))
        self.assertIn("unknown room 'nowhere'", self.rpg("validate", "--game", "smugglers_cove", ok=False))
        # a second world with the same title gets its own id
        self.rpg("meter", "refill")
        d2, out = self.forge_draft(())
        self.assertIn("surprise them", out)
        self.assertIn("a surprise world", self.rpg("forge", "status"))
        self.finish_draft(d2)
        self.assertIn("(smugglers_cove_2)", self.rpg("forge", "install", d2))

    def test_new_worlds_follow_the_owners_switch_but_not_the_meter(self):
        self.settings_tool("preset", "thrifty")
        self.assertIn("FORGE OFF", self.rpg("forge", "quote"))
        self.assertIn("switched off", self.rpg("forge", "start", "x", ok=False))
        self.assertFalse((self.dir / "state" / "forge").exists() and any((self.dir / "state" / "forge").iterdir()))
        self.settings_tool("preset", "normal")
        self.assertIn("NEW WORLDS: on", self.rpg("settings"))
        self.assertIn("one sentence", self.rpg("forge", "start", "x" * 301, ok=False))
        self.set_meter(0)  # a spent meter doesn't stop a new world
        self.assertIn("FORGE: a new world can be made", self.rpg("forge", "quote"))
        self.assertIn("FORGE STARTED", self.rpg("forge", "start", "x"))
        self.assertEqual(0, self.meter_file())

    def test_a_stopped_or_failed_forge_waits_and_can_be_finished_later(self):
        self.rpg("meter", "refill")
        d, _ = self.forge_draft()
        # the worldsmith stopped without READY: the draft waits, unfinished
        self.assertIn("stopped before the world was finished", self.rpg("forge", "install", d, ok=False))
        self.assertIn("UNFINISHED: %s" % d, self.rpg("forge", "quote"))
        self.set_meter(4)
        out = self.rpg("forge", "resume", d)
        self.assertIn("An earlier attempt left files", out)
        self.assertEqual(4, self.meter_file())  # finishing one doesn't use the meter either
        # it says it's ready but doesn't pass: not installed, unfinished again
        self.finish_draft(d)
        (self.dir / "state/forge" / d / "world/scenes/shiniest_thing.md").unlink()
        self.assertIn("doesn't pass the checks", self.rpg("forge", "install", d, ok=False))
        self.assertFalse((self.dir / "state/forge" / d / "READY").exists())
        self.assertIn("unfinished", self.rpg("forge", "status"))
        self.assertFalse((self.dir / "state" / "worlds").exists())
        self.assertIn("DISCARDED", self.rpg("forge", "discard", d))
        self.assertIn("NO DRAFTS", self.rpg("forge", "status"))

    def test_a_forge_cut_off_by_closing_claude_code_counts_as_unfinished(self):
        self.rpg("meter", "refill")
        d, _ = self.forge_draft()
        self.assertIn("forging", self.rpg("forge", "status"))
        self.rpg("meter", "refill")  # what opening Claude Code again does
        self.assertIn("unfinished", self.rpg("forge", "status"))
        self.assertIn("FORGE STARTED", self.rpg("forge", "start", "another"))  # the old one no longer blocks a new one

    def test_the_worldsmiths_guard_keeps_it_to_its_draft(self):
        def ask(tool, agent="worldsmith", **args):
            event = {"tool_name": tool, "tool_input": args, "cwd": str(self.dir)}
            if agent:
                event["agent_type"] = agent
            out = self.run_py(".claude/hooks/forge_guard.py", stdin=json.dumps(event)).stdout.strip()
            return json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out else None
        self.assertEqual("deny", ask("Write", file_path="state/forge/draft_aaaaaa/world/world.md"))  # nothing forging
        self.rpg("meter", "refill")
        d, _ = self.forge_draft()
        self.assertEqual("allow", ask("Write", file_path="state/forge/%s/world/rooms/cove.md" % d))
        self.assertEqual("allow", ask("Edit", file_path=str(self.dir / "state/forge" / d / "world/world.md")))
        self.assertEqual("allow", ask("Write", file_path="state/forge/%s/READY" % d))
        for path in ("rules/rpg.py", "state/save.json", "state/forge/%s/forge.json" % d, "state/forge/%s/world/../../../x" % d):
            self.assertEqual("deny", ask("Write", file_path=path), path)
        self.assertEqual("allow", ask("Bash", command="python3 rules/rpg.py validate --dir state/forge/%s/world --kit-complete" % d))
        self.assertEqual("allow", ask("Bash", command="rm state/forge/%s/world/rooms/cove.md" % d))
        for cmd in ("python3 rules/rpg.py flag set x", "rm -rf state/forge/%s/world" % d, "ls",
                    "python3 rules/rpg.py validate --dir state/forge/%s/world --kit-complete; rm state/save.json" % d,
                    "rm state/forge/%s/world/../forge.json" % d):
            self.assertEqual("deny", ask("Bash", command=cmd), cmd)
        self.assertIsNone(ask("Read", file_path="games/dark_lighthouse/world.md"))
        self.assertIsNone(ask("Write", agent="npc", file_path="rules/x.md"))  # not its business
        (self.dir / "state/forge" / d / "READY").write_text("done")
        self.assertEqual("deny", ask("Write", file_path="state/forge/%s/world/world.md" % d))  # finished: hands off

    def test_the_owner_keeps_or_forgets_a_forged_world(self):
        self.rpg("meter", "refill")
        d, _ = self.forge_draft()
        self.finish_draft(d)
        self.rpg("forge", "install", d)
        self.rpg("newgame")  # a game of the lighthouse goes on meanwhile
        out = self.run_py("tools/worlds.py", "list").stdout
        self.assertIn('smugglers_cove: The Smugglers Cove, forged', out)
        self.assertIn('from "a smugglers cove"; no game yet', out)
        self.rpg("game", "switch", "smugglers_cove")
        self.rpg("newgame")
        self.assertIn("switch to another game first", self.run_py("tools/worlds.py", "forget", "smugglers_cove", "--yes").stdout)
        self.rpg("game", "switch", "dark_lighthouse")
        self.assertIn("Would delete", self.run_py("tools/worlds.py", "forget", "smugglers_cove").stdout)
        self.assertTrue((self.dir / "state/worlds/smugglers_cove").is_dir())
        # keep: it becomes one of the kit's games, checked with them, its saved game intact
        self.write("state/worlds/smugglers_cove/rooms/coast_road.md", "---\nexits:\n  west: nowhere\n---\n")
        out = self.run_py("tools/worlds.py", "keep", "smugglers_cove").stdout
        self.assertIn("stays a forged world", out)
        self.assertTrue((self.dir / "state/worlds/smugglers_cove").is_dir())
        shutil.copy(self.dir / "games/dark_lighthouse/rooms/coast_road.md", self.dir / "state/worlds/smugglers_cove/rooms/coast_road.md")
        self.assertIn("KEPT", self.run_py("tools/worlds.py", "keep", "smugglers_cove").stdout)
        self.assertIn("CONTENT OK: smugglers_cove", self.rpg("validate"))
        self.assertNotIn("forged in play", self.rpg("game", "list"))
        self.assertIn("The saved game continues", self.rpg("game", "switch", "smugglers_cove"))
        # forget: a second world, with its shelved save and library, goes for good
        self.rpg("meter", "refill")
        d2, _ = self.forge_draft()
        self.finish_draft(d2, title="The Salt Mines")
        self.rpg("forge", "install", d2)
        self.rpg("game", "switch", "salt_mines")
        self.rpg("newgame")
        self.write("state/library/salt_mines.json", json.dumps({"entries": {}}))
        self.rpg("game", "switch", "dark_lighthouse")
        out = self.run_py("tools/worlds.py", "forget", "salt_mines", "--yes").stdout
        self.assertIn("FORGOTTEN", out)
        for gone in ("state/worlds/salt_mines", "state/shelf/salt_mines.json", "state/library/salt_mines.json"):
            self.assertFalse((self.dir / gone).exists(), gone)
        self.assertNotIn("salt_mines", self.rpg("game", "list"))

if __name__ == "__main__":
    unittest.main(verbosity=2)
