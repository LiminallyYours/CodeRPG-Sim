#!/usr/bin/env python3
"""Tests for the rules engine, run against a throwaway copy of the project:  python3 tools/test_rules.py

Each test gets a fresh temp copy of rules/, games/ and proposals/ with an empty state/, and drives
rules/rpg.py as the game master would, through its command line. The real save is never touched.
"""
import csv
import datetime
import getpass
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAMES = sorted(p.name for p in (ROOT / "games").glob("*") if (p / "world.md").is_file())
SIM_GAMES = ("thirteenth_stroke",)  # the worlds with the simulation's whole economy (PLAN.md step 17)
STRICT_GAMES = ("wendleford",)  # the worlds built for the simulation, held to SIM-WORLD-SPEC.md (validate --sim-strict)


class Engine(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="rpg-test-"))
        for d in ("rules", "games", "cast", "proposals", "tools", ".claude/hooks", ".claude/agents", "mod/sounds"):
            shutil.copytree(ROOT / d, self.dir / d, ignore=shutil.ignore_patterns("__pycache__", "*.json.tmp"))
        (self.dir / "state").mkdir()
        for stale in (self.dir / "proposals").glob("*.json"):
            stale.unlink()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def rpg(self, *args, seed=None, ok=True, as_=None):
        """Run one rpg.py command; by default it must succeed. Returns its output. It acts as `as_`, by default
        the save's first player (the shipped games' first cast member plays as the original's one player did);
        `as_=False` passes no --as."""
        if as_ is None:
            save = self.dir / "state" / "save.json"
            players = json.loads(save.read_text()).get("players") if save.is_file() else None
            as_ = next(iter(players)) if isinstance(players, dict) and players else False
        if as_ and "--as" not in args:
            args += ("--as", as_)
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
        """The first player's record in a save: the one the tests act as."""
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

    def room_exits(self, room):
        """A room's exits as the active game's file gives them, {direction: target room}, conditions dropped."""
        text = (self.dir / "games" / self.save()["game"] / "rooms" / ("%s.md" % room)).read_text()
        out = {}
        for line in text.split("exits:\n", 1)[1].splitlines():
            m = re.match(r"^  (\w+): (\w+)", line)
            if not m:
                break
            out[m.group(1)] = m.group(2)
        return out

    def play(self, seed):
        """A fixed little session from a named seed: what it rolled and printed."""
        outs = [self.rpg("newgame", seed)]
        here = self.save()["players"][next(iter(self.save()["players"]))]["location"]
        exits = self.room_exits(here)
        way = sorted(exits)[0]  # out by the start room's first way, back, and out again: whatever the world's map
        back = next(d for d, target in self.room_exits(exits[way]).items() if target == here)
        for d in (way, back, way):
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
        self.assertIn("WORLD TURNS: on, every 2 rounds;", self.rpg("settings"))  # the clock counts rounds here
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
        self.set_meter(9)
        r = subprocess.run([sys.executable, ".claude/hooks/session_start.py"], cwd=self.dir, input="{}", capture_output=True, text=True,
                           env=dict(os.environ, CODERPG_NO_REFILL="1"))
        self.assertEqual((r.stdout, self.meter_file()), ("", 9), "a round's session from tools/rounds.py doesn't refill it")

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

    def lighthouse_economy(self, work="  stat: wits\n  pay: 1-3\n  dc: 2\n", buys="  trinket: 1\n  light_weapon: 2\n"):
        """The Lighthouse with paid work in Harbor Square and Morwen buying as well as making."""
        g = self.dir / "games" / "dark_lighthouse"
        for f, key, block in (("rooms/harbor_square.md", "work", work), ("characters/morwen.md", "buys", buys)):
            text = (g / f).read_text()
            (g / f).write_text(text.replace("---\n", "---\n%s:\n%s" % (key, block), 1))
        self.rpg("game", "switch", "dark_lighthouse")

    def log(self):
        return [json.loads(line) for line in (self.dir / "state" / "log" / ("%s.jsonl" % self.save()["run"]["id"])).read_text().splitlines()]

    def test_work_pays_after_a_check_once_per_visit(self):
        self.lighthouse_economy()
        self.rpg("newgame", seed=60)  # Wren in Harbor Square
        self.assertIn("WORK HERE: Wits vs DC 2, pays 1-3 coins, once per visit. If the player works here: `work`.", self.rpg("look"))
        coins = self.me()["stats"]["coins"]
        out = self.rpg("work")
        self.assertRegex(out, r"WORK wits vs DC 2: d20 \d+ \+\d+ = \d+ -> SUCCESS")
        paid = self.me()["stats"]["coins"] - coins
        self.assertTrue(1 <= paid <= 3)
        self.assertIn("PAID: %d coins for the work" % paid, out)
        self.assertIn("(done this visit)", self.rpg("look"))
        self.assertIn("already worked here this visit", self.rpg("work", ok=False))
        self.rpg("move", "east")
        self.assertIn("no paid work here", self.rpg("work", ok=False))
        self.rpg("move", "west")
        self.assertIn("WORK wits", self.rpg("work"))  # a new visit
        coin_entries = [e for e in self.log() if e["kind"] == "coins"]
        self.assertTrue(coin_entries and all(e["reason"] == "work" and e["note"] == "harbor_square" for e in coin_entries))

    def test_a_buyer_buys_made_things_but_not_the_worlds_own(self):
        self.lighthouse_economy()
        self.rpg("newgame", seed=40)
        self.assertIn("BUYERS HERE: morwen buys trinket 1, light weapon 2. If the player sells something: `sell <item>`.", self.rpg("look"))
        self.order("morwen", {"id": "gaff_hook", "name": "Gaff Hook", "description": "A barbed hook.", "tier": "light_weapon"})
        self.rpg("pay", "gaff_hook")
        coins = self.me()["stats"]["coins"]
        self.assertIn("doesn't buy worn_dagger: it has no tier", self.rpg("sell", "worn_dagger", ok=False))
        self.assertIn("SOLD: gaff_hook to Morwen for 2 coins. COINS +2", self.rpg("sell", "gaff_hook"))
        self.assertEqual(self.me()["stats"]["coins"], coins + 2)
        self.assertNotIn("gaff_hook", self.me()["inventory"])
        self.assertIn("not carrying gaff_hook", self.rpg("sell", "gaff_hook", ok=False))
        self.assertIn("isn't a buyer here", self.rpg("sell", "worn_dagger", "pell", ok=False))
        self.rpg("move", "east")
        self.assertIn("nobody here buys things", self.rpg("sell", "worn_dagger", ok=False))
        entries = self.log()
        self.assertEqual([(e["delta"], e["reason"]) for e in entries if e["kind"] == "coins"], [(-3, "order"), (2, "sale")])
        self.assertIn(("used", "sold to morwen"), [(e["step"], e.get("how")) for e in entries if e["kind"] == "order"])

    def test_validate_checks_work_buyers_and_what_a_simulation_needs(self):
        out = self.rpg("validate", "--game", "dark_lighthouse", "--sim-complete", ok=False)  # as shipped: neither
        for want in ("sim: needs a room with paid work (work:)", "sim: needs a buyer (buys:)",
                     "sim: world.md generation rooms must be no"):
            self.assertIn(want, out)
        self.assertNotIn("sim: needs a maker", out)
        self.assertNotIn("sim: needs a cast", out)
        self.lighthouse_economy(work="  stat: luck\n  pay: 0-9\n  dc: tricky\n  hours: 3\n",
                                buys="  hat: 1\n  light_weapon: 3\n  trinket: free\n")
        out = self.rpg("validate", "--game", "dark_lighthouse", ok=False)
        for want in ("rooms/harbor_square.md: work: unknown key 'hours'", "work: stat must be one of might, agility, wits",
                     "work: pay must be a whole number or a range like 1-3, from 1 to 4", "work: dc must be a number",
                     "characters/morwen.md: buys: 'hat' isn't an item tier",
                     "buys: light_weapon: pays 3, but having one made costs 3; a buyer must pay less",
                     "buys: trinket: the price must be a whole number"):
            self.assertIn(want, out)

    def test_the_save_holds_players_and_as_names_who_acts(self):
        self.rpg("game", "switch", "dark_lighthouse")
        out = self.rpg("newgame", seed=43)
        s = self.save()
        self.assertEqual(list(s["players"]), ["wren", "corin"])
        cast = json.loads((self.dir / "games/dark_lighthouse/cast.json").read_text())
        self.assertIn("CAST: Wren (wren, opus, they/them) at Harbor Square; Corin (corin, opus, they/them) at The Gull\n", out,
                      "everyone on the one model the settings name")
        self.assertNotEqual(cast[1]["model"], "opus", "though Corin's own is another")
        self.assertEqual(s["players"]["corin"]["location"], "gull_tavern")
        self.assertEqual(s["players"]["corin"]["stats"]["coins"], 4)
        self.assertEqual(s["view"]["players"]["corin"]["location_name"], "The Gull")
        self.assertIn("LOCATION: The Gull", self.rpg("look", as_="corin"))
        self.assertIn("say who acts: --as <wren|corin>", self.rpg("look", ok=False, as_=False))
        self.assertIn("no one called 'nell' is playing", self.rpg("look", as_="nell", ok=False))
        self.assertIn("--as needs a player id", self.rpg("look", "--as", ok=False))

    def test_the_cast_says_how_to_speak_of_each_person(self):
        self.rpg("game", "switch", "thirteenth_stroke")
        out = self.rpg("newgame", seed=43)
        self.assertIn("Dilly Quickstep (dilly, opus, they/them) at ", out)
        self.assertIn("Hobb Ashcombe (hobb, opus, he/him) at ", out)
        self.assertIn("PEOPLE HERE: Dilly Quickstep (dilly, they/them; carrying lamplighters_pole).", self.rpg("look", as_="marigold"))
        self.assertIn("Marigold Thimble (she/her) at The Lopsided Square", self.rpg("world-brief", "turn", as_=False))

    def test_two_players_share_a_room_and_its_things(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=43)
        self.assertNotIn("PEOPLE HERE", self.rpg("look", as_="wren"))
        self.rpg("move", "south", as_="corin")  # from the Gull to Harbor Square, where Wren is
        self.assertEqual(self.save()["players"]["corin"]["location"], "harbor_square")
        self.assertIn("PEOPLE HERE: Corin (corin, they/them; carrying healing_tonic).", self.rpg("look", as_="wren"))  # the cast names none
        self.assertIn("PEOPLE HERE: Wren (wren, they/them; carrying worn_dagger (in hand), healing_tonic).", self.rpg("look", as_="corin"))
        self.assertIn("What they carry is theirs: the story shows only what anyone could plainly see of it.", self.rpg("look", as_="corin"))
        self.rpg("drop", "healing_tonic", as_="corin")
        self.assertIn("healing_tonic", self.rpg("look", as_="wren").split("ITEMS HERE:")[1].split("\n")[0])
        self.rpg("take", "healing_tonic", as_="wren")
        self.assertIn("is not here", self.rpg("take", "healing_tonic", as_="corin", ok=False))
        s = self.save()
        self.assertEqual(s["players"]["wren"]["inventory"].count("healing_tonic"), 2)
        self.assertNotIn("healing_tonic", s["players"]["corin"]["inventory"])

    def test_an_npc_sees_the_players_as_people_and_remembers_each_one(self):
        self.at_the_lighthouse()  # Wren, with Ysolde
        for d in ("south", "west"):
            self.rpg("move", d, as_="corin")
        self.rpg("remember", "ysolde", "Asked about the lens and listened.")
        brief = self.rpg("npc-brief", "ysolde", as_="corin")
        self.assertIn("Present: Corin (they/them), Wren (they/them).", brief, "how to speak of each, the same every time")
        self.assertIn("Corin is the one talking to you.", brief)
        self.assertIn("## What you remember about Corin\nYou have never met this person before.", brief)
        self.assertIn("## What you remember about Wren\n- Asked about the lens and listened.", brief)
        self.assertNotIn("player", brief.lower())
        self.assertNotIn("Asked about the lens", self.rpg("show", "characters", "ysolde", as_="corin"))

    def test_every_coin_change_is_logged_with_its_reason_and_refused_commands_leave_none(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=43)
        self.assertIn("the reason must be one of", self.rpg("coins", "+2", "luck", ok=False))
        self.rpg("coins", "+2", "gift")
        self.rpg("coins", "-1", "purchase", as_="corin")
        self.assertIn("not enough coins", self.rpg("coins", "-99", "purchase", ok=False))
        run = self.save()["run"]["id"]
        lines = (self.dir / "state" / "log" / ("%s.jsonl" % run)).read_text().splitlines()
        entries = [json.loads(line) for line in lines]  # every line is one JSON object
        coins = [e for e in entries if e["kind"] == "coins"]
        self.assertEqual([(e["player"], e["delta"], e["reason"], e["balance"]) for e in coins],
                         [("wren", 2, "gift", 5), ("corin", -1, "purchase", 3)])
        commands = [(e["command"], e["refused"]) for e in entries if e["kind"] == "command"]
        self.assertEqual(commands, [("newgame", False), ("coins", True), ("coins", False), ("coins", False), ("coins", True)])
        self.assertTrue(all(e["kind"] in ("command", "coins") and "round" in e and "move" in e for e in entries))
        self.assertIn("coins +2 (gift) -> 5", self.rpg("log"))
        self.assertIn("command coins +2 gift", self.rpg("log"))

    def three_players(self):
        """The Lighthouse with a third cast member, Tam, in Harbor Square."""
        d = "games/dark_lighthouse/cast.json"
        cast = json.loads((self.dir / d).read_text())
        cast.append(dict(cast[1], id="tam", name="Tam", home="harbor_square"))
        self.write(d, json.dumps(cast))
        self.rpg("game", "switch", "dark_lighthouse")

    def take_turn(self, pid, do="I look around.", journal="Getting my bearings.", story="You look around."):
        self.write("proposals/reply.txt", "DO: %s\nJOURNAL: %s\n" % (do, journal))
        self.rpg("reply", pid, "proposals/reply.txt")
        self.rpg("look", as_=pid)
        self.write("proposals/story.txt", story)
        return self.rpg("narrate", pid, "proposals/story.txt")

    def test_a_quest_won_by_one_is_told_to_everyone_and_the_run_goes_on(self):
        self.rpg("game", "switch", "thirteenth_stroke")
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=44)
        order = [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().split(", ")]
        first, others = order[0], order[1:]
        self.write("proposals/reply.txt", "DO: I jam the poker in the gear.\nJOURNAL: To stop the clock.\n")
        self.rpg("reply", first, "proposals/reply.txt")
        out = self.rpg("flag", "set", "clock_stopped", as_=first)
        self.assertIn("ENDING: Before the Thirteenth Stroke is done.", out)
        self.assertIn("`ending <file>` before `narrate`", out)
        self.write("proposals/story.txt", "The gear stops dead.")
        self.assertIn("an ending is still to be told", self.rpg("narrate", first, "proposals/story.txt", ok=False))
        self.write("proposals/ending.txt", "Word came that the town clock had stopped a whisker before midnight.")
        self.assertIn("ENDING TOLD", self.rpg("ending", "proposals/ending.txt", as_=first))
        self.assertIn("no quest has been decided", self.rpg("ending", "proposals/ending.txt", as_=first, ok=False))
        self.assertIn("NARRATED", self.rpg("narrate", first, "proposals/story.txt"))
        save = self.save()
        rooms = {save["players"][p]["location"] for p in others}
        self.assertGreater(len(rooms), 1, "the others are in several places, and all hear of it")
        for p in others:
            self.assertIn({"kind": "seen", "text": "Word came that the town clock had stopped a whisker before midnight."},
                          [{k: e[k] for k in ("kind", "text")} for e in save["players"][p]["memory"]["recent"]])
        self.assertNotIn("Word came", json.dumps(save["players"][first]["memory"]), "their own story tells them")
        self.assertEqual(save["run"]["endings"]["thirteenth_stroke"]["by"], first)
        for p in others:
            self.take_turn(p)
        self.assertNotIn("ENDING", self.rpg("round", "end"))
        self.rpg("round", "start")  # the run goes on
        ending = [e for e in self.log_entries() if e["kind"] == "ending"]
        self.assertEqual([(e["quests"], sorted(e["heard_by"])) for e in ending], [({"thirteenth_stroke": "done"}, sorted(others))])

    def test_an_ending_decided_between_rounds_is_told_for_no_one(self):
        self.rpg("game", "switch", "thirteenth_stroke")
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=44)
        self.play_round()
        state = self.save()
        state["flags"].append("shadows_carted")  # as the clock would at the thirteenth stroke, at a round's end
        self.write("state/save.json", json.dumps(state))
        out = self.rpg("round", "start", ok=False)
        self.assertIn("ENDING: Before the Thirteenth Stroke is lost.", out)
        self.assertIn("(no --as) before the next `round start`", out)
        self.write("proposals/ending.txt", "Thirteen strokes boomed out over the town, the last one wrong.")
        self.assertIn("ENDING TOLD: Marigold Thimble (marigold), ", self.rpg("ending", "proposals/ending.txt", as_=False))
        self.rpg("round", "start")

    def test_the_options_a_person_weighed_go_in_the_log_only_and_are_cut_never_refused(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=43)
        first = self.rpg("round", "start").split(": ", 1)[1].split(", ")[0].split("(")[1].rstrip(")")
        self.write("proposals/reply.txt", "OPTIONS:\n- Mend the nets with Morwen (for: paying my way)\n"
                   "* Climb to the lighthouse (for: finding out what's wrong with the lamp)\n- Wait for morning\n"
                   "DO: I climb to the lighthouse.\nJOURNAL: The lamp matters most tonight.\n")
        out = self.rpg("reply", first, "proposals/reply.txt")
        self.assertIn("OPTIONS: 3, kept in the log", out)
        self.assertNotIn("Mend the nets", out, "the referee runs the turn from the DO line alone")
        action = [e for e in self.log_of() if e["kind"] == "action"][-1]
        self.assertEqual(action["options"], [
            {"text": "Mend the nets with Morwen", "for": "paying my way", "chosen": False},
            {"text": "Climb to the lighthouse", "for": "finding out what's wrong with the lamp", "chosen": True},
            {"text": "Wait for morning", "for": None, "chosen": False}])
        self.assertNotIn("options_cut", action)
        self.assertEqual((action["do"], action["journal"]), ("I climb to the lighthouse.", "The lamp matters most tonight."))
        self.rpg("look", as_=first)
        self.write("proposals/story.txt", "You climb.")
        self.rpg("narrate", first, "proposals/story.txt")
        memory = json.dumps(self.save()["players"][first]["memory"])
        self.assertNotIn("Mend the nets", memory)
        second = [p for p in self.save()["players"] if p != first][0]
        self.assertNotIn("Mend the nets", self.rpg("brief", second, as_=False))
        many = "".join("- Option number %d, said at some length so the list runs long (for: something)\n" % i for i in range(40))
        self.write("proposals/reply.txt", "OPTIONS:\n%sDO: I look around.\nJOURNAL: Getting my bearings.\n" % many)
        self.assertIn("(cut at the limit)", self.rpg("reply", second, "proposals/reply.txt"))
        action = [e for e in self.log_of() if e["kind"] == "action"][-1]
        self.assertTrue(action["options_cut"])
        limit = json.loads((self.dir / "rules" / "balance.json").read_text())["turns"]["options_chars"]
        self.assertLessEqual(sum(len("- %s (for: %s)" % (o["text"], o["for"])) for o in action["options"]), limit)
        self.assertEqual(action["do"], "I look around.")
        audit = self.run_py("tools/audit.py", "state/log/%s.jsonl" % self.save()["run"]["id"]).stdout
        self.assertIn("== OPTIONS\n  %s: options in 1 of 1 replies (3 options 1x)\n    r1 chose: Climb to the lighthouse "
                      "(for: finding out what's wrong with the lamp)\n  %s: " % (first, second), audit)
        self.assertIn("r1 chose: NONE MARKED  <<< cut at the limit", audit)

    def test_words_said_aloud_reach_the_others_here_on_their_next_turn(self):
        self.rpg("game", "switch", "flooded_station")  # Sol and Ade both start on the Landing
        self.rpg("newgame", seed=44)
        first, second = [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().split(", ")]
        names = {pid: pl["name"] for pid, pl in self.save()["players"].items()}
        self.write("proposals/reply.txt", "DO: I ask whether the lift still works.\nJOURNAL: I need to get down.\n")
        self.rpg("reply", first, "proposals/reply.txt")
        self.write("proposals/words.txt", '"Does the lift still work?"')
        self.assertIn("they'll read it on their next turn", self.rpg("say", "proposals/words.txt", as_=first))
        self.write("proposals/words.txt", "Hello?")
        self.assertIn("it's %s's turn" % first, self.rpg("say", "proposals/words.txt", as_=second, ok=False))
        heard = self.rpg("brief", second)
        self.assertIn('What you were told: %s says: "Does the lift still work?"' % names[first], heard)
        self.assertIn("How it begins", heard, "words heard before a first turn don't take the opening away")
        self.assertNotIn("What you were told", self.rpg("brief", first))
        speech = [e for e in self.log_of() if e["kind"] == "speech"]
        self.assertEqual([(e["player"], e["text"], e["heard_by"]) for e in speech], [(first, "Does the lift still work?", [second])])
        exits = self.save()["players"][first]["map"][self.save()["players"][first]["location"]]["exits"]
        self.rpg("move", next(iter(exits)), as_=first)
        self.write("proposals/words.txt", "Anyone?")
        self.assertIn("NOT KEPT: no one else of the cast here is awake to hear it", self.rpg("say", "proposals/words.txt", as_=first),
                      "accepted quietly: nothing to retry")
        self.assertFalse((self.dir / "proposals/words.txt").exists(), "words no one heard leave nothing behind")

    def test_the_others_there_see_and_hear_a_turn_on_their_next(self):
        self.three_players()  # Wren and Tam in Harbor Square, Corin north in the Gull
        self.rpg("newgame", seed=43)
        note = "Wren asks Morwen about the lamp and heads north into the Gull. Morwen calls after her: \"Mind the stairs.\""
        for pid in [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().split(", ")]:
            if pid != "wren":
                self.take_turn(pid)
                continue
            self.write("proposals/reply.txt", "DO: I ask Morwen about the lamp, then go to the Gull.\nJOURNAL: The lamp.\n")
            self.rpg("reply", "wren", "proposals/reply.txt")
            self.rpg("move", "north", as_="wren")
            self.write("proposals/note.txt", "x" * 801)
            self.assertIn("at most 800 characters", self.rpg("witnessed", "proposals/note.txt", as_="wren", ok=False))
            self.write("proposals/note.txt", note)
            self.assertIn("Corin (corin), Tam (tam)", self.rpg("witnessed", "proposals/note.txt", as_="wren"))
            self.write("proposals/story.txt", "You climb to the Gull.")
            self.rpg("narrate", "wren", "proposals/story.txt")
        self.rpg("round", "end")
        players = self.save()["players"]
        for pid in ("corin", "tam"):  # Tam saw her leave, Corin saw her come in
            self.assertIn({"round": 1, "kind": "seen", "text": note, "uses": 0}, players[pid]["memory"]["recent"])
        self.assertNotIn(note, json.dumps(players["wren"]["memory"]))
        self.assertIn("What happened: " + note, self.rpg("brief", "tam"))
        self.assertEqual([(e["player"], e["seen_by"]) for e in self.log_of() if e["kind"] == "witnessed"], [("wren", ["corin", "tam"])])

    def test_what_one_learns_where_others_hear_they_learn_too(self):
        self.rpg("game", "switch", "thirteenth_stroke")
        self.rpg("newgame", seed=43)  # Marigold and Dilly in the square, with Pip
        self.rpg("quest", "take", "thirteenth_stroke", as_="dilly")  # so it shows in what she's working on
        self.rpg("round", "start")
        if self.save()["run"]["round_state"]["order"][0] != "marigold":
            self.take_turn("dilly")
        self.write("proposals/reply.txt", "DO: I ask Pip about her brother.\nJOURNAL: She knows something.\n")
        self.rpg("reply", "marigold", "proposals/reply.txt")
        self.rpg("flag", "set", "heard_of_shadows", as_="marigold")
        def witnessed(flag, ok=True):  # the note file is used up each time, refused or not
            self.write("proposals/note.txt", "Marigold asked Pip about her brother, and Pip told her the whole story.")
            return self.rpg("witnessed", "proposals/note.txt", flag, as_="marigold", ok=ok)
        self.assertIn("a shared flag is everyone's already", witnessed("craves_giggle", ok=False))
        self.assertIn("nothing of it to learn", witnessed("caught_sneaking", ok=False))
        self.assertIn("They learned it too: heard_of_shadows", witnessed("heard_of_shadows"))
        self.assertEqual(self.save()["players"]["dilly"]["flags"], ["heard_of_shadows"])
        self.assertIn("[done] Find out why", self.rpg("pane", "dilly"))
        self.assertEqual([e["learned"] for e in self.log_of() if e["kind"] == "witnessed"], [["heard_of_shadows"]])

    def test_no_one_witnesses_a_turn_with_no_one_there(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=43)  # Corin is in the Gull; Wren goes from the square east, where nobody is
        self.rpg("round", "start")
        if self.save()["run"]["round_state"]["order"][0] != "wren":
            self.take_turn("corin")
        self.write("proposals/reply.txt", "DO: I walk east.\nJOURNAL: To see the coast.\n")
        self.rpg("reply", "wren", "proposals/reply.txt")
        self.rpg("move", "east", as_="wren")
        self.write("proposals/note.txt", "Wren walks east.")
        self.assertIn("NOT KEPT: no one else was there to see it", self.rpg("witnessed", "proposals/note.txt", as_="wren"),
                      "accepted quietly: nothing to retry")

    # ---------------------------------------------------------------- trades between people

    def round_with(self, **turns):
        """A round in its drawn order: each player named takes the turn given (a function of their id), the rest look
        around. Returns what `round end` printed."""
        order = [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().splitlines()[0].split(", ")]
        for pid in order:
            (turns.get(pid) or self.take_turn)(pid)
        return self.rpg("round", "end")

    def turn(self, pid, do, *commands):
        """`pid`'s turn: their reply, then each rules command (a tuple, run as them), then the story. Returns what
        the commands printed."""
        self.write("proposals/reply.txt", "DO: %s\nJOURNAL: To see what comes of it.\n" % do)
        self.rpg("reply", pid, "proposals/reply.txt")
        out = [self.rpg(*c, as_=pid, ok=None) for c in commands]
        self.write("proposals/story.txt", "You do it.")
        self.rpg("narrate", pid, "proposals/story.txt")
        return out

    def offer(self, terms):
        """The command for an offer of `terms`, its file written now (each its own, since a file is used up once read)."""
        self.offers = getattr(self, "offers", 0) + 1
        path = "proposals/offer-%d.json" % self.offers
        self.write(path, json.dumps(terms))
        return ("trade", "offer", path)

    def test_a_gift_stays_open_when_the_giver_walks_off_and_can_still_be_taken(self):
        self.three_players()  # Wren and Tam in Harbor Square
        self.rpg("newgame", seed=44)
        way = next(iter(self.save()["players"]["wren"]["map"]["harbor_square"]["exits"]))
        out = []
        ended = self.round_with(wren=lambda pid: out.extend(self.turn(pid, "I press a coin into Tam's hand and go.",
                                                                      self.offer({"to": "tam", "give": {"coins": 1}}), ("move", way))))
        self.assertNotIn("OFFER LAPSED", "".join(out) + ended)
        self.assertIn("## Offered to you\n- Wren offers you 1 coins", self.rpg("pane", "tam"))
        wren, tam = (self.save()["players"][p]["stats"]["coins"] for p in ("wren", "tam"))
        self.round_with(tam=lambda pid: out.extend(self.turn(pid, "I keep the coin.", ("trade", "accept", "t1"))))
        self.assertIn("ACCEPTED t1: Tam takes Wren's offer.", out[-1])
        self.assertEqual([self.save()["players"][p]["stats"]["coins"] for p in ("wren", "tam")], [wren - 1, tam + 1])

    def trade_entries(self):
        return [(e["trade"], e["step"], e.get("why")) for e in self.log_entries() if e["kind"] == "trade"]

    def test_an_offer_is_made_face_to_face_and_only_the_two_of_them_see_it(self):
        self.three_players()  # Wren and Tam in Harbor Square; Corin in the Gull
        self.rpg("newgame", seed=44)
        out = []

        def wren(pid):
            for terms in ({"to": "wren", "give": {"coins": 1}}, {"to": "nobody", "give": {"coins": 1}},
                          {"to": "corin", "give": {"coins": 1}}, {"to": "tam", "give": {"items": ["healing_tonic", "healing_tonic"]}},
                          {"to": "tam", "give": {"coins": 4}}, {"to": "tam", "give": {"items": ["harbor_square"]}},
                          {"to": "tam", "give": {"items": ["no_such_thing"]}}, {"to": "tam", "give": {"coins": -1}},
                          {"to": "tam"}, {"to": "tam", "give": {"coins": 1}, "price": 3},
                          {"to": "tam", "give": {"items": ["worn_dagger"], "coins": 1}, "want": {"items": ["healing_tonic"]}}):
                self.write("proposals/offer.json", json.dumps(terms))
                out.append(self.rpg("trade", "offer", "proposals/offer.json", as_=pid, ok=None))
            out.append(self.rpg("look", as_=pid))
            self.write("proposals/story.txt", "You hold out the dagger.")
            self.rpg("narrate", pid, "proposals/story.txt")

        def reply_wren(pid):
            self.write("proposals/reply.txt", "DO: I hold out my dagger and a coin to Tam for the tonic.\nJOURNAL: Tam needs it more.\n")
            self.rpg("reply", pid, "proposals/reply.txt")
            wren(pid)
        self.round_with(wren=reply_wren)
        refusals = ["an offer is made to someone else", "no one called 'nobody' is playing", "Corin isn't here: an offer is made face to face",
                    "doesn't have healing_tonic to give", "doesn't have 4 coins to give", "harbor_square is a place, and places can't change hands",
                    "no item called 'no_such_thing'", "give coins must be a whole number", "the offer gives nothing and asks for nothing",
                    "an offer holds only to, give and want"]
        for said, got in zip(refusals, out):
            self.assertIn("REFUSED: ", got)
            self.assertIn(said, got)
        self.assertIn("OFFERED t1 to Tam (tam): gives Worn Dagger and 1 coins; asks for Healing Tonic.", out[10])
        self.assertIn("OFFERS HERE: t1 to Tam (tam): gives worn_dagger, 1 coins; asks for healing_tonic. Theirs to answer", out[11])
        self.assertFalse((self.dir / "proposals" / "offer.json").exists(), "the file is used up")
        tam, wren_pane = self.rpg("pane", "tam"), self.rpg("pane", "wren")
        self.assertIn("## Offered to you\n- Wren offers you Worn Dagger and 1 coins, and asks for Healing Tonic in return.", tam)
        self.assertIn("## You offered\n- To Tam: Worn Dagger and 1 coins, asking for Healing Tonic in return.", wren_pane)
        self.assertNotIn("You offered", tam)
        self.assertNotIn("Offered", self.rpg("pane", "corin"))
        for pane in (tam, wren_pane):
            self.assertIsNone(self.FORBIDDEN.search(pane), pane)
        self.assertIn("Offered to you", self.rpg("brief", "tam"), "the brief carries the pane")
        looked = []
        self.round_with(tam=lambda pid: looked.append(self.turn(pid, "I think about it.", ("look",))[0]))
        self.assertIn("OFFERS HERE: t1 from Wren (wren): gives worn_dagger, 1 coins; asks for healing_tonic. If the player takes it: "
                      "`trade accept t1`", looked[0])
        offered = next(e for e in self.log_entries() if e["kind"] == "trade")
        self.assertEqual((offered["trade"], offered["step"], offered["offered_by"], offered["to"], offered["give"], offered["want"],
                          offered["words"], offered["journal"]),
                         ("t1", "offered", "wren", "tam", {"items": ["worn_dagger"], "coins": 1}, {"items": ["healing_tonic"], "coins": 0},
                          "I hold out my dagger and a coin to Tam for the tonic.", "Tam needs it more."))

    def test_an_offer_ends_when_turned_down_replaced_parted_from_or_left_too_long(self):
        self.three_players()
        self.rpg("newgame", seed=44)
        gift, ask = self.offer({"to": "tam", "give": {"coins": 1}}), {"to": "tam", "want": {"items": ["healing_tonic"]}}
        out = []
        self.round_with(wren=lambda pid: out.extend(self.turn(pid, "I offer Tam a coin, then ask for the tonic instead.",
                                                              gift, self.offer(ask), ("trade", "decline", "t2"))))
        self.assertIn("OFFER LAPSED: t1, replaced by this one.", out[1])
        self.assertIn("REFUSED: only Tam can turn down t2", out[2])
        self.assertIn("## Offered to you\n- Wren asks you for Healing Tonic, offering nothing in return.", self.rpg("pane", "tam"))
        self.assertIn("- You asked Tam for Healing Tonic, offering nothing in return.", self.rpg("pane", "wren"))
        ended = self.round_with(tam=lambda pid: out.extend(self.turn(pid, "I say no.", ("trade", "decline", "t2"), ("trade", "decline", "t2"))))
        self.assertIn("DECLINED t2: Tam turns down Wren's offer.", out[3])
        self.assertIn("REFUSED: t2 is over (declined)", out[4])
        self.assertNotIn("Offered", self.rpg("pane", "tam"))
        self.assertNotIn("OFFER LAPSED", ended)
        # left unanswered: made in round 3, it stands through rounds 4 and 5
        self.round_with(wren=lambda pid: self.turn(pid, "I offer Tam a coin.", self.offer({"to": "tam", "give": {"coins": 1}})))
        self.assertNotIn("OFFER LAPSED", self.round_with())
        self.assertIn("OFFER LAPSED: t3, Wren to Tam (no answer in time).", self.round_with())
        # parted: Tam walks off (a trade; a gift would stand)
        self.round_with(wren=lambda pid: self.turn(pid, "I offer Tam a coin for the tonic.",
                                                    self.offer({"to": "tam", "give": {"coins": 1}, "want": {"items": ["healing_tonic"]}})))
        way = next(iter(self.save()["players"]["tam"]["map"]["harbor_square"]["exits"]))
        moved = []
        self.round_with(tam=lambda pid: moved.extend(self.turn(pid, "I walk off.", ("move", way))))
        self.assertIn("OFFER LAPSED: t4, Wren to Tam (they're no longer together).", moved[0])
        self.assertEqual(self.trade_entries(), [("t1", "offered", None), ("t1", "lapsed", "replaced"), ("t2", "offered", None),
                                                ("t2", "declined", None), ("t3", "offered", None), ("t3", "lapsed", "time"),
                                                ("t4", "offered", None), ("t4", "lapsed", "parted")])
        self.assertEqual(self.save()["players"]["tam"]["stats"]["coins"], 4, "nothing changed hands")

    def holdings(self, *pids):
        players = self.save()["players"]
        return [(sorted(players[p]["inventory"]), players[p]["equipped"], players[p]["stats"]["coins"]) for p in pids]

    def test_accepting_hands_both_sides_over_at_once(self):
        self.three_players()
        self.rpg("newgame", seed=44)
        wren_had, tam_had = self.holdings("wren", "tam")
        self.assertEqual((wren_had, tam_had), ((["healing_tonic", "worn_dagger"], "worn_dagger", 3), (["healing_tonic"], None, 4)))
        out = []
        self.round_with(wren=lambda pid: out.extend(self.turn(pid, "I offer Tam my dagger and a coin for the tonic.", self.offer(
            {"to": "tam", "give": {"items": ["worn_dagger"], "coins": 1}, "want": {"items": ["healing_tonic"]}}), ("trade", "accept", "t1"))))
        self.assertIn("REFUSED: only Tam can accept t1", out[1])
        self.round_with(tam=lambda pid: out.extend(self.turn(pid, "I take it.", ("trade", "accept", "t1"), ("trade", "accept", "t1"))))
        self.assertIn("ACCEPTED t1: Tam takes Wren's offer. Wren hands over Worn Dagger and 1 coins; Tam hands over Healing Tonic.", out[2])
        self.assertIn("REFUSED: t1 is over (accepted)", out[3])
        self.assertEqual(self.holdings("wren", "tam"), [(["healing_tonic", "healing_tonic"], None, 2), (["worn_dagger"], None, 5)],
                         "the dagger was in Wren's hand: let go of, and handed over")
        coins = [(e["player"], e["delta"], e["reason"], e.get("note")) for e in self.log_entries() if e["kind"] == "coins"]
        self.assertEqual(coins, [("wren", -1, "trade", "t1"), ("tam", 1, "trade", "t1")])
        accepted = [e for e in self.log_entries() if e["kind"] == "trade"][-1]
        self.assertEqual((accepted["step"], accepted["player"], accepted["words"]), ("accepted", "tam", "I take it."))
        self.assertNotIn("Offered", self.rpg("pane", "tam"))
        # a gift of something made to order: it stays made for Wren, whoever has it
        charm = {"id": "shell_charm", "name": "Shell Charm", "description": "A cockle shell on a cord.", "tier": "trinket"}

        def order_and_give(pid):
            self.write("proposals/reply.txt", "DO: I have Morwen make a charm, and give it to Tam.\nJOURNAL: A thank-you.\n")
            self.rpg("reply", pid, "proposals/reply.txt")
            self.order("morwen", charm)
            self.rpg("pay", "shell_charm", as_=pid)
            out.append(self.rpg("pane", pid))
            out.append(self.rpg(*self.offer({"to": "tam", "give": {"items": ["shell_charm"]}}), as_=pid))
            self.write("proposals/story.txt", "Morwen ties off the cord.")
            self.rpg("narrate", pid, "proposals/story.txt")
        self.round_with(wren=order_and_give)
        self.assertIn("Shell Charm (made for you)", out[4])
        self.assertIn("## Offered to you\n- Wren offers you Shell Charm, and asks nothing in return.", self.rpg("pane", "tam"))
        self.assertNotIn("shell_charm", self.save()["players"]["tam"]["inventory"], "a gift is the other's only once taken")
        self.round_with(tam=lambda pid: out.extend(self.turn(pid, "I take the charm.", ("trade", "accept", "t2"))))
        self.assertIn("ACCEPTED t2: Tam takes Wren's offer. Wren hands over Shell Charm; Tam hands over nothing.", out[6])
        tam = self.rpg("pane", "tam")
        self.assertIn("Shell Charm", tam)
        self.assertNotIn("made for you", tam)
        used = [(e["order"], e["id"], e["how"], e["player"]) for e in self.log_entries() if e["kind"] == "order" and e["step"] == "used"]
        self.assertIn(("o1", "shell_charm", "traded", "wren"), used)
        out = self.run_py("tools/audit.py", "state/log/%s.jsonl" % self.save()["run"]["id"]).stdout
        self.assertIn("== TRADES\n  t1 r1 wren -> tam: gives worn_dagger, 1 coins; wants healing_tonic: accepted r2\n"
                      "  t2 r3 wren -> tam: gives shell_charm; wants nothing: accepted r4\n== ", out, "coins balanced, so nothing flagged")

    def test_the_dashboard_feed_shows_each_trade_and_what_both_hold_after(self):
        self.three_players()
        self.rpg("newgame", seed=44)
        self.round_with(wren=lambda pid: self.turn(pid, "I offer Tam my dagger and a coin for the tonic.", self.offer(
            {"to": "tam", "give": {"items": ["worn_dagger"], "coins": 1}, "want": {"items": ["healing_tonic"]}})))
        self.round_with(tam=lambda pid: self.turn(pid, "I take it.", ("trade", "accept", "t1")))
        self.round_with(wren=lambda pid: self.turn(pid, "I ask Tam for the dagger back.", self.offer({"to": "tam", "want": {"items": ["worn_dagger"]}})))
        for _ in range(2):
            self.round_with()
        feed = json.loads(self.run_py("-c", "import json, sys; sys.path.insert(0, 'tools'); import dashboard; print(json.dumps(dashboard.live()['feed']))").stdout)
        turns = {(i["round"], i["name"]): i["trades"] for i in feed if i["kind"] == "turn"}
        self.assertEqual(turns[(1, "Wren")], ["Offered Tam Worn Dagger, 1 coins for Healing Tonic."])
        self.assertEqual(turns[(2, "Tam")], ["Took Wren's offer: Wren gave Worn Dagger, 1 coins, Tam gave Healing Tonic. "
                                             "Wren now has 2 coins and Healing Tonic, Healing Tonic; Tam now has 5 coins and Worn Dagger."])
        self.assertEqual(turns[(3, "Wren")], ["Asked Tam for Worn Dagger, offering nothing back."])
        self.assertIn({"kind": "trade", "key": feed[1]["key"], "round": 5, "text": "Wren's offer to Tam lapsed: no answer in time."}, feed,
                      "an offer lapsing between turns gets a line of its own")

    def test_an_accept_that_cant_happen_changes_nothing_and_the_offer_stands(self):
        self.three_players()
        self.rpg("newgame", seed=44)
        out = []

        def offers(pid):
            self.write("proposals/reply.txt", "DO: I offer Tam my dagger, and then my cutlass and lens.\nJOURNAL: To be rid of them.\n")
            self.rpg("reply", pid, "proposals/reply.txt")
            for i in ("boarding_cutlass", "brass_lens"):
                self.rpg("gain", i, as_=pid)
            self.rpg(*self.offer({"to": "tam", "give": {"items": ["worn_dagger"]}, "want": {"items": ["honey_cake"]}}), as_=pid)
            self.rpg("drop", "worn_dagger", as_=pid)  # and then thinks better of it
            self.write("proposals/story.txt", "You set the dagger down.")
            self.rpg("narrate", pid, "proposals/story.txt")
        self.round_with(wren=offers)
        self.round_with(tam=lambda pid: out.extend(self.turn(pid, "I take Wren's offer.", ("trade", "accept", "t1"))))
        self.assertIn("REFUSED: Wren doesn't have worn_dagger now", out[0])
        self.assertIn("## Offered to you", self.rpg("pane", "tam"), "a refused accept leaves the offer standing")
        self.round_with(wren=lambda pid: self.turn(pid, "I offer Tam the cutlass and the lens for a honey cake.", self.offer(
            {"to": "tam", "give": {"items": ["boarding_cutlass", "brass_lens"]}, "want": {"items": ["honey_cake"]}})))
        before = self.holdings("wren", "tam")

        def tries(pid):
            self.write("proposals/reply.txt", "DO: I take Wren's offer.\nJOURNAL: A fair swap.\n")
            self.rpg("reply", pid, "proposals/reply.txt")
            out.append(self.rpg("trade", "accept", "t2", as_=pid, ok=False))  # no honey cake to give yet
            for _ in range(3):
                self.rpg("gain", "honey_cake", as_=pid)
            out.append(self.rpg("trade", "accept", "t2", as_=pid, ok=False))  # 1 + 3 - 1 + 6 = 9, and Tam carries 8 at most
            self.write("proposals/story.txt", "You reach for it.")
            self.rpg("narrate", pid, "proposals/story.txt")
        self.round_with(tam=tries)
        self.assertIn("REFUSED: Tam doesn't have honey_cake now", out[1])
        self.assertIn("REFUSED: Tam can't carry it all: Boarding Cutlass and Brass Lens would make a load of 9, and 8 is the most", out[2])
        self.assertEqual(self.holdings("wren")[0], before[0])
        self.assertEqual(self.holdings("tam")[0][0], ["healing_tonic"] + ["honey_cake"] * 3)
        self.assertEqual([e["step"] for e in self.log_entries() if e["kind"] == "trade"], ["offered", "lapsed", "offered"])
        self.assertFalse([e for e in self.log_entries() if e["kind"] == "coins"])

    def grabs(self, pid, do, *tries):
        """`pid`'s turn: each try a (seed, contest arguments) pair, run as them with those dice. Returns the outputs."""
        self.write("proposals/reply.txt", "DO: %s\nJOURNAL: I want it.\n" % do)
        self.rpg("reply", pid, "proposals/reply.txt")
        out = [self.rpg("contest", *args, as_=pid, seed=seed, ok=None) for seed, args in tries]
        self.write("proposals/story.txt", "You reach for it.")
        self.rpg("narrate", pid, "proposals/story.txt")
        return out

    def test_a_grab_goes_to_the_higher_roll_and_a_tie_stays_with_the_one_holding_it(self):
        self.three_players()  # Wren (Gumption +2, the dagger in hand) and Tam (Wiggle +1) in Harbor Square; Corin in the Gull
        self.rpg("newgame", seed=44)
        before, out = self.holdings("wren", "tam"), []
        grab = ("agility", "wren", "might", "--take", "worn_dagger")

        def refused(pid):
            out.extend(self.grabs(pid, "I grab at things.", *[(1, a) for a in (
                ("might", "corin", "might", "--take", "worn_dagger"), ("might", "tam", "might", "--take", "healing_tonic"),
                ("luck", "wren", "might", "--take", "worn_dagger"), ("might", "wren", "might", "--take", "brass_lens"),
                ("might", "wren", "might"))]))
            out.append(self.rpg("contest", *grab, as_="wren", ok=False))
        self.round_with(tam=refused)
        for said, got in zip(["Corin isn't here", "a contest is with someone else", "stat must be one of might, agility, wits",
                              "Wren isn't holding brass_lens", "usage: contest", "it's"], out):
            self.assertIn(said, got)
        self.assertEqual(self.holdings("wren", "tam"), before)

        def too_heavy(pid):
            self.write("proposals/reply.txt", "DO: I grab Wren's dagger, my arms full.\nJOURNAL: I want it.\n")
            self.rpg("reply", pid, "proposals/reply.txt")
            for i in ("boarding_cutlass", "brass_lens", "honey_cake"):
                self.rpg("gain", i, as_=pid)  # a load of 8, the most Tam can carry
            out.append(self.rpg("contest", *grab, as_=pid, seed=2, ok=False))
            for i in ("boarding_cutlass", "brass_lens", "honey_cake"):
                self.rpg("lose", i, as_=pid)
            self.write("proposals/story.txt", "Your arms are full.")
            self.rpg("narrate", pid, "proposals/story.txt")
        self.round_with(tam=too_heavy)
        self.assertIn("REFUSED: too heavy", out[-1])
        self.assertFalse([e for e in self.log_entries() if e["kind"] == "contest"], "a refused grab rolls nothing")
        # seed 7: 19 + 1 against 18 + 2, a tie; seed 1: 16 + 1 against 16 + 2; seed 2: 18 + 1 against 11 + 2
        self.round_with(tam=lambda pid: out.extend(self.grabs(pid, "I snatch Wren's dagger.", (7, grab), (1, grab), (2, grab))))
        self.assertIn("CONTEST for Worn Dagger: Tam agility d20 19 +1 = 20; Wren might d20 18 +2 = 20 -> Wren KEEPS hold of it (a tie)", out[-3])
        self.assertIn("Wren might d20 16 +2 = 18 -> Wren KEEPS hold of it\n", out[-2])
        self.assertIn("-> Tam TAKES it  [weight 2/8]", out[-1])
        self.assertIn("Wren was there and sees it in the onlookers' note (`witnessed`)", out[-1])
        self.assertEqual(self.holdings("wren", "tam"), [(["healing_tonic"], None, 3), (["healing_tonic", "worn_dagger"], None, 4)],
                         "the dagger was in Wren's hand: let go of, and taken")
        contests = [e for e in self.log_entries() if e["kind"] == "contest"]
        self.assertEqual([(e["player"], e["against"], e["item"], e["winner"], e["rolls"]["tam"]["total"], e["rolls"]["wren"]["total"])
                          for e in contests], [("tam", "wren", "worn_dagger", "wren", 20, 20), ("tam", "wren", "worn_dagger", "wren", 17, 18),
                                               ("tam", "wren", "worn_dagger", "tam", 19, 13)])
        self.assertEqual((contests[-1]["rolls"]["wren"]["stat"], contests[-1]["words"]), ("might", "I snatch Wren's dagger."))
        # a thing made to order, grabbed: its order's record says so
        charm = {"id": "shell_charm", "name": "Shell Charm", "description": "A cockle shell on a cord.", "tier": "trinket"}

        def order(pid):
            self.write("proposals/reply.txt", "DO: I have Morwen make me a charm.\nJOURNAL: For luck.\n")
            self.rpg("reply", pid, "proposals/reply.txt")
            self.order("morwen", charm)
            self.rpg("pay", "shell_charm", as_=pid)
            self.write("proposals/story.txt", "Morwen ties off the cord.")
            self.rpg("narrate", pid, "proposals/story.txt")
        self.round_with(wren=order)
        self.round_with(tam=lambda pid: self.grabs(pid, "I snatch the charm.", (2, ("agility", "wren", "might", "--take", "shell_charm"))))
        self.assertIn("shell_charm", self.save()["players"]["tam"]["inventory"])
        used = [(e["order"], e["id"], e["how"], e["player"]) for e in self.log_entries() if e["kind"] == "order" and e["step"] == "used"]
        self.assertIn(("o1", "shell_charm", "snatched", "wren"), used)
        out = self.run_py("tools/audit.py", "state/log/%s.jsonl" % self.save()["run"]["id"]).stdout
        self.assertIn("== CONTESTS\n  r3 tam -> wren: worn_dagger, agility 20 against might 20: kept (a tie)\n"
                      "  r3 tam -> wren: worn_dagger, agility 17 against might 18: kept\n"
                      "  r3 tam -> wren: worn_dagger, agility 19 against might 13: taken\n", out)
        feed = json.loads(self.run_py("-c", "import json, sys; sys.path.insert(0, 'tools'); import dashboard; print(json.dumps(dashboard.live()['feed']))").stdout)
        turns = {(i["round"], i["name"]): i["trades"] for i in feed if i["kind"] == "turn"}
        self.assertEqual(turns[(3, "Tam")], ["Grabbed at Wren's Worn Dagger: agility 20 against might 20; Wren kept hold of it (a tie).",
                                             "Grabbed at Wren's Worn Dagger: agility 17 against might 18; Wren kept hold of it.",
                                             "Grabbed at Wren's Worn Dagger: agility 19 against might 13; took it."])

    def test_those_passed_on_the_way_see_someone_go_by(self):
        self.rpg("game", "switch", "thirteenth_stroke")
        self.rpg("newgame", seed=43)  # Hobb in the tower; Marigold and Dilly in the square below; Hester in Crooked Lane
        out = []

        def hobb(pid):
            self.write("proposals/reply.txt", "DO: I go down through the square to Crooked Lane.\nJOURNAL: To find a poker.\n")
            self.rpg("reply", pid, "proposals/reply.txt")
            self.rpg("move", "south", as_=pid)
            self.rpg("move", "south", as_=pid)
            for note, extra in (("Hobb came down the lane from the square.", ()), ("Hobb crossed the square, heading south.", ("--in", "lopsided_square")),
                                ("Hobb again.", ("--in", "crooked_lane")), ("Hobb again.", ("--in", "lopsided_square"))):
                self.write("proposals/note.txt", note)
                out.append(self.rpg("witnessed", "proposals/note.txt", *extra, as_=pid, ok=None))
            self.write("proposals/story.txt", "You go down to the lane.")
            self.rpg("narrate", pid, "proposals/story.txt")
        self.round_with(hobb=hobb)
        self.assertIn("WITNESSED by Hester Gimbal (hester)", out[0])
        self.assertIn("ALSO PASSED: lopsided_square, where Marigold Thimble, Dilly Quickstep saw Hobb Ashcombe go by: a short note of that "
                      "for them, `witnessed <file> --in lopsided_square`.", out[0])
        self.assertIn("WITNESSED by Marigold Thimble (marigold), Dilly Quickstep (dilly)", out[1])
        self.assertNotIn("ALSO PASSED", out[1])
        self.assertIn("REFUSED: crooked_lane isn't a room Hobb Ashcombe passed through this turn with someone else in it (lopsided_square)", out[2])
        self.assertIn("WITNESSED by Marigold", out[3], "a second note for the same room is the referee's to judge")
        seen = lambda p: [m["text"] for m in self.save()["players"][p]["memory"]["recent"] if m["kind"] == "seen"]  # noqa: E731
        self.assertIn("Hobb crossed the square, heading south.", seen("dilly"))
        self.assertNotIn("Hobb came down the lane from the square.", seen("dilly"), "they saw only the passing")
        self.assertEqual(seen("hester")[-1:], ["Hobb came down the lane from the square."])
        self.assertFalse(list((self.dir / "proposals").glob("note.txt")), "a refused note's file is used up too")

    def test_what_one_person_learns_stays_their_own(self):
        self.rpg("game", "switch", "thirteenth_stroke")
        self.rpg("newgame", seed=43)  # Marigold and Dilly both start in the square, with Pip
        for pid in ("marigold", "dilly"):
            self.rpg("quest", "take", "thirteenth_stroke", as_=pid)
        self.assertIn("(Marigold Thimble's own)", self.rpg("flag", "set", "heard_of_shadows", as_="marigold"))
        self.assertIn("[done] Find out why", self.rpg("pane", "marigold"))
        self.assertNotIn("[done] Find out why", self.rpg("pane", "dilly"))
        told = "You've told this person everything"
        self.assertIn(told, self.rpg("show", "characters", "pip", as_="marigold"))
        self.assertNotIn(told, self.rpg("show", "characters", "pip", as_="dilly"))
        self.rpg("flag", "set", "clock_stopped", as_="marigold")  # a fact about the world: everyone's
        self.assertIn("Before the Thirteenth Stroke (done)", self.rpg("pane", "dilly"))
        flags = [l for l in self.rpg("look", as_="dilly").splitlines() if l.startswith("FLAGS:")][0]
        self.assertIn("clock_stopped", flags)
        self.assertNotIn("heard_of_shadows", flags)
        self.assertNotIn("heard_of_shadows", self.save()["flags"])
        self.rpg("flag", "unset", "heard_of_shadows", as_="marigold")
        self.assertEqual(self.save()["players"]["marigold"]["flags"], [])

    def test_a_personal_flag_may_not_decide_where_things_are(self):
        path = self.dir / "games" / "dark_lighthouse" / "world.md"
        path.write_text(path.read_text().replace("personal_flags: lamp_quest_started,", "personal_flags: grukk_friend, lamp_quest_started,"))
        out = self.rpg("validate", "--game", "dark_lighthouse", ok=False)
        self.assertIn("rooms/greywater_bridge.md exits: grukk_friend is personal", out)
        self.assertIn("rooms/greywater_bridge.md characters: grukk_friend is personal", out)

    def test_a_player_hears_the_talk_going_around_only_among_people(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=43)
        self.rpg("move", "east")  # Wren to the Coast Road, where nobody is; Corin stays in the Gull with Pell
        self.write("proposals/wt.json", json.dumps({"rumors": ["The keeper's lamp burned blue last night."], "moves": []}))
        self.rpg("world-turn", "proposals/wt.json", as_=False)
        self.rpg("look")
        self.assertNotIn("The keeper's lamp", self.rpg("pane", "wren"))
        self.assertNotIn("The keeper's lamp", self.rpg("brief", "wren"))
        self.assertIn("## Talk going around\n- The keeper's lamp burned blue last night.", self.rpg("brief", "corin"))
        self.rpg("move", "west")  # back to Harbor Square, where Morwen is
        self.assertIn("The keeper's lamp", self.rpg("pane", "wren"))
        self.assertEqual(self.save()["players"]["wren"]["heard"], ["The keeper's lamp burned blue last night."])

    def test_the_dashboard_shows_the_run_and_asks_rpg_to_pause_it(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=43)
        self.play_round()
        self.rpg("round", "start")
        server = subprocess.Popen([sys.executable, "tools/dashboard.py", "--port", "0"], cwd=self.dir,
                                  stdout=subprocess.PIPE, text=True)
        try:
            url = server.stdout.readline().split("DASHBOARD: ")[1].strip()

            def get(path, **headers):
                req = urllib.request.Request(url + path.lstrip("/"), headers=headers)
                with urllib.request.urlopen(req, timeout=10) as r:
                    return r.read().decode("utf-8")

            def post(path, **headers):
                req = urllib.request.Request(url + path.lstrip("/"), data=b"", method="POST", headers=headers)
                try:
                    with urllib.request.urlopen(req, timeout=10) as r:
                        return r.status, json.loads(r.read())
                except urllib.error.HTTPError as e:
                    return e.code, None

            self.assertIn("<title>Run dashboard</title>", get("/"))
            live = json.loads(get("/api/live"))
            self.assertEqual(live["game"]["title"], self.save()["adventure"])
            self.assertEqual((live["run"]["round"], live["run"]["played"], live["run"]["open"]), (2, 1, True))
            self.assertEqual([p["id"] for p in live["people"]], ["wren", "corin"])
            self.assertEqual(sum(p["now"] for p in live["people"]), 1)
            wren = live["people"][0]
            self.assertEqual((wren["coins"], wren["journal"], wren["journal_round"]), (3, "Getting my bearings.", 1))
            turns = [f for f in live["feed"] if f["kind"] == "turn"]
            self.assertEqual(len(turns), 2)
            self.assertTrue(all(t["story"].startswith("Moment 1 for") and t["do"] == "I look around." for t in turns))
            self.assertEqual(live["feed"][0], {"kind": "round", "key": "r2", "round": 2, "order": live["run"]["order"],
                                               "commands": [{"text": "round start", "said": "ROUND 2: Corin (corin), Wren (wren)", "refused": False}]})
            self.assertEqual(live["happening"], {"stage": "between", "next": "Corin", "round": 2, "steps": live["feed"][0]["commands"]})
            self.assertIn("/api/brief/", get("/"))
            page = get("/")
            self.assertIn("/api/stamp", page)
            self.assertNotIn("setInterval(load", page, "the page never reloads by itself: it lights a signal")
            for word in ("Narrative", "World", "Engine", "First", "Prior", "Next", "Current", "Go to most recent"):
                self.assertIn(">%s<" % word, page)
            stamp = json.loads(get("/api/stamp"))
            self.assertEqual(stamp, live["stamp"], "the signal's stamp and the loaded page's agree")
            self.assertEqual((stamp["turns"], stamp["rounds_closed"], stamp["last_closed"], stamp["stop"]), (2, 1, 1, None))
            with self.assertRaises(urllib.error.HTTPError):
                get("/api/live", Host="elsewhere.example")
            self.assertEqual(post("/api/run/pause")[0], 403, "no ask without the page's own header")
            self.assertIsNone(self.save()["run"].get("stop"))
            code, said = post("/api/run/pause", **{"X-Dashboard": "1"})
            self.assertEqual((code, said["ok"]), (200, True))
            self.assertEqual(self.save()["run"]["stop"], "pause")
            self.assertEqual(json.loads(get("/api/live"))["run"]["stop"], "pause")
            self.assertEqual(json.loads(get("/api/stamp"))["stop"], "pause", "a pause asked lights the signal")
            rows = list(csv.DictReader(io.StringIO(get("/export.csv"))))
            self.assertEqual(len(rows), len(self.log_of()))
        finally:
            server.terminate()
            server.wait(timeout=10)
            server.stdout.close()

    def test_the_dashboard_files_every_kind_of_entry_under_its_turn_or_round_and_counts_the_spend(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=43)
        self.play_round()
        log = self.dir / "state" / "log" / ("%s.jsonl" % self.save()["run"]["id"])

        def e(kind, round_, player=None, **fields):
            return dict({"kind": kind, "t": "2026-10-25T12:00:00", "round": round_, "order_position": 1 if player else None,
                         "player": player, "move": 1}, **fields)

        def cmd(round_, command, args, output, player=None, refused=False):
            return e("command", round_, player, command=command, args=args, output=output, refused=refused)
        brief_text = "## Who I am (a note to myself)\nA brief."
        entries = [
            e("round", 2, phase="start", order=["wren", "corin"], draw={}),
            e("brief", 2, "wren", text=brief_text, versions={}),
            e("action", 2, "wren", do="I ask Morwen about the lamp.", journal="To know.", model="sonnet",
              exact_model="claude-sonnet-5-5", spend=0.01, options=[{"text": "Ask Morwen", "for": "knowing", "chosen": True}]),
            cmd(2, "look", [], "LOCATION: The Gull", "wren"),
            e("voice", 2, "wren", agent="npc", about="morwen", model="sonnet", reply="SAY: The lamp burns blue.\nREMEMBER: none", spend=0.02),
            e("speech", 2, "wren", text="About the lamp?", heard_by=["corin"]),
            e("witnessed", 2, "wren", text="Wren asked Morwen about the lamp.", seen_by=["corin"], learned=[]),
            e("coins", 2, "wren", delta=-2, reason="order", balance=1),
            e("order", 2, "wren", order="o1", step="asked", what="craft", maker="morwen"),
            cmd(2, "say", ["proposals/words.txt"], "REFUSED: no one is here to hear it", "wren", refused=True),
            cmd(2, "chronicle", ["Wren asked about the lamp."], "CHRONICLED: Wren asked about the lamp."),
            e("narration", 2, "wren", text="Morwen tells you the lamp burns blue."),
            cmd(2, "narrate", ["wren", "proposals/story.txt"], "NARRATED"),
            e("round", 2, phase="end", order=["wren", "corin"], world_turn_due=True),
            e("memory", 2, "wren", rounds=[1, 2], text="I asked about the lamp.", replaced=3, model="sonnet", spend=0.005,
              learned=["Morwen keeps the lamp."], learned_given=True),
            e("voice", 2, agent="world", about="turn", model="sonnet", reply='{"rumors": []}', spend=0.03),
            cmd(2, "world-turn", ["proposals/world-turn.json"],
                "WORLD TURN: 1 rumors, 1 moves\n  rumor: The lamp burns blue.\n  morwen is now at gull_tavern\nSIGNAL for Wren: a gull cries"),
            e("referee", 2, round_run=2, session="s", spend=0.4, seconds=120.0, context=60000),
            cmd(2, "run", ["status"], "RUN: going"),
            e("round", 3, phase="start", order=["corin", "wren"], draw={}),
            e("brief", 3, "corin", text="A second brief.", versions={}),
        ]
        with log.open("a", encoding="utf-8") as f:
            f.writelines(json.dumps(x) + "\n" for x in entries)
        live = json.loads(self.run_py("-c", "import json, sys; sys.path.insert(0, 'tools'); import dashboard; print(json.dumps(dashboard.live()))").stdout)
        by_key = {i["key"]: i for i in live["feed"]}
        turn = by_key["2:wren"]
        self.assertEqual((turn["do"], turn["exact_model"], turn["options"], turn["brief_chars"]),
                         ("I ask Morwen about the lamp.", "claude-sonnet-5-5", [{"text": "Ask Morwen", "for": "knowing", "chosen": True}], len(brief_text)))
        self.assertEqual([(v["about"], v["said"]) for v in turn["voices"]], [("Morwen", "The lamp burns blue.")], "a townsperson's SAY: line")
        self.assertEqual(turn["notes"], [{"text": "Wren asked Morwen about the lamp.", "seen_by": ["Corin"]}])
        self.assertEqual(turn["money"], ["-2 coins (order); now 1.", "Order o1: asked Morwen to make something."])
        self.assertEqual(turn["chronicle"], ["Wren asked about the lamp."], "the chronicle is no one's, but it falls in the turn")
        self.assertEqual(turn["heard_by"], ["Corin"])
        self.assertEqual(turn["story"], "Morwen tells you the lamp burns blue.")
        self.assertAlmostEqual(turn["spend"], 0.03, msg="their reply and the townsperson asked")
        self.assertEqual([c["text"] for c in turn["commands"] if c["refused"]], ["say proposals/words.txt"])
        self.assertNotIn("run status", [c["text"] for c in by_key["e2"]["commands"]], "the referee's lookups are left out")
        end = by_key["e2"]
        self.assertEqual([(m["who"], m["rounds"], m["replaced"], m["learned"]) for m in end["memories"]],
                         [("Wren", [1, 2], 3, ["Morwen keeps the lamp."])])
        self.assertEqual(end["world"], ["Rumor: The lamp burns blue.", "Morwen is now at The Gull."], "no SIGNAL: that's the referee's")
        self.assertEqual(end["referee"], {"spend": 0.4, "seconds": 120.0, "context": 60000})
        self.assertEqual([v["agent"] for v in end["voices"]], ["world"])
        meter = live["meter"]
        spend = sum(x.get("spend") or 0 for x in self.log_of())
        self.assertAlmostEqual(meter["spend"]["total"], spend)
        self.assertEqual({k: round(v, 3) for k, v in meter["spend"].items() if k != "total"},
                         {"referee": 0.4, "people": 0.01, "voices": 0.05, "memory": 0.005})
        self.assertEqual([r["round"] for r in meter["rounds"]], [3, 2, 1])
        self.assertEqual((meter["rounds"][1]["seconds"], meter["rounds"][1]["context"], meter["rounds"][1]["refused"]), (120.0, 60000, 1))
        self.assertTrue(meter["rounds"][0]["open"])
        self.assertEqual(live["happening"]["stage"], "deciding")
        self.assertEqual((live["happening"]["who"], live["happening"]["told"]), ("Corin", len("A second brief.")))
        wren = next(p for p in live["people"] if p["id"] == "wren")
        self.assertEqual((wren["exact_models"], round(wren["spend"], 3), wren["told"]), (["claude-sonnet-5-5"], 0.015, len(brief_text)))
        self.assertEqual(by_key["3:corin"]["do"], "", "a turn shows from its brief, while they decide")
        at = turn["brief_at"]
        got = json.loads(self.run_py("-c", "import json, sys; sys.path.insert(0, 'tools'); import dashboard; print(json.dumps([dashboard.brief_at(%d), dashboard.brief_at(0)]))" % at).stdout)
        self.assertEqual(got, [{"text": brief_text}, None], "a brief by its line in the log, and nothing else")

    def test_the_dashboards_turns_and_world_views_and_its_coverage_come_from_the_log_and_save_and_write_nothing(self):
        self.rpg("game", "switch", "wendleford")
        self.rpg("newgame", seed=46)

        def round_of(doing):
            order = [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().split(", ")]
            for pid in order:
                self.rpg("brief", pid)
                self.write("proposals/reply.txt", "DO: I get on with my day.\nJOURNAL: Busy.\n")
                self.rpg("reply", pid, "proposals/reply.txt")
                for command in doing.get(pid, ()):
                    out = self.rpg(*command, as_=pid)
                    if "ENDING:" in out:
                        self.write("proposals/ending.txt", "Word of it goes round the square.")
                        self.rpg("ending", "proposals/ending.txt", as_=pid)
                self.write("proposals/story.txt", "Your day goes on.")
                self.rpg("narrate", pid, "proposals/story.txt")
            return self.rpg("round", "end")
        round_of({"hobb": [["move", "south"], ["contest", "might", "dilly", "might", "--take", "tinderbox"], ["quest", "take", "wage_box"],
                           ["outcome", "partly"]],
                  "dilly": [["buy", "bread"], ["eat", "bread"], ["outcome", "done"]],
                  "marigold": [["work"]], "hester": [["work"]]})
        s = self.save()
        s["players"]["marigold"]["stats"]["coins"] = 10
        self.write("state/save.json", json.dumps(s))
        round_of({"hobb": [["move", "south"], ["work"], ["outcome", "not_there", "a ferryman"]],
                  "marigold": [["move", "west"], ["move", "northwest"], ["rent", "mabry_cottage"]],
                  "dilly": [["move", "south"], ["work"], ["flag", "set", "wage_box_found"]]})
        log = self.dir / "state" / "log" / ("%s.jsonl" % self.save()["run"]["id"])
        before = (self.dir / "state" / "save.json").read_bytes(), log.read_bytes()
        code = ("import json, sys; sys.path.insert(0, 'tools'); import dashboard; d = dashboard.live(); "
                "t = next(x for x in d['feed'] if x['kind'] == 'turn' and x['player'] == 'hobb' and x['round'] == 2); "
                "print(json.dumps([d, dashboard.steps_of(t['first'], t['last'], 'hobb')]))")
        live, steps = json.loads(self.run_py("-c", code).stdout)
        self.assertEqual(before, ((self.dir / "state" / "save.json").read_bytes(), log.read_bytes()), "the dashboard writes nothing")
        turns = {(x["round"], x["player"]): x for x in live["feed"] if x["kind"] == "turn"}
        self.assertEqual([x["kind"] for x in live["feed"]][0], "round_end", "newest first")
        dilly = turns[(1, "dilly")]
        self.assertTrue(dilly["where"].startswith("Market Square, morning on day 1"), dilly["where"])
        self.assertEqual(dilly["outcome"], {"result": "done", "what": None})
        self.assertIn("BOUGHT: Loaf of Bread from Bet Lamb for 1 pennies. COINS -1 -> 3", dilly["world_changes"])
        hobb = turns[(2, "hobb")]
        kept = [m["text"] for m in self.save()["players"]["hobb"]["memory"]["recent"] if m["kind"] == "changed" and m["round"] == 2]
        self.assertEqual([hobb["changed"]], kept, "the engine's own what-changed line")
        self.assertEqual(hobb["outcome"], {"result": "not_there", "what": "a ferryman"})
        self.assertTrue(any(line.startswith("EFFORT on the new bridge") for line in hobb["world_changes"]))
        self.assertIn("ROOM TEXT:", next(x["said"] for x in steps if x["text"] == "move south"), "every command's whole output, on asking")
        self.assertEqual(turns[(1, "hobb")]["with"], "Constance Lowe", "he wakes in the barn, where Constance sleeps too")
        self.assertIn("Bet Lamb", dilly["with"])
        w = live["world"]
        square = next(p for p in w["places"] if p["name"] == "Market Square")
        self.assertEqual((square["people"], square["cast"]), (["Bet Lamb", "Ned Pike"], []), "day 1: the market; the cast have gone")
        bridge = next(p for p in w["projects"] if p["name"] == "the new bridge")
        self.assertEqual(sorted((b["name"], b["turns"]) for b in bridge["by"]), [("Dilly Quickstep", 1), ("Hobb Ashcombe", 1)])
        self.assertTrue(all(b["most"] for b in bridge["by"]), "a tie for most is shared")
        self.assertIn("The Cottage on Lark Lane: Marigold Thimble's to the end of day 7", w["lets"])
        people = {p["name"]: p for p in w["people"]}
        self.assertIn("The Cottage on Lark Lane (to the end of day 7)", people["Marigold Thimble"]["own"])
        self.assertIn("The Reeve's Wage Box", people["Hobb Ashcombe"]["taken_on"])
        self.assertTrue(people["Dilly Quickstep"]["needs"][0].startswith("You"), "needs in words")
        rumor = next(r for r in w["rumors"] if r["text"].startswith("Ned Pike swears"))
        self.assertIsInstance(rumor["heard_by"], list)
        box = next(q for q in w["hooks"]["quests"] if q["name"] == "The Reeve's Wage Box")
        self.assertEqual((box["state"], box["ended"]["by"], box["ended"]["round"]), ("complete", "Dilly Quickstep", 2))
        self.assertEqual(box["taken_on"], ["Hobb Ashcombe (round 1)"])
        self.assertEqual(box["objectives"][2]["waits_on"], "wage_box_found")
        events = {e["id"]: e["state"] for e in w["hooks"]["events"]}
        self.assertEqual((events["false_lead"], events["rain"]), ("happened", "waiting"), "the false lead came as round 1 ended, before the box was found")
        self.assertIn("r1 Hobb Ashcombe took on The Reeve's Wage Box", w["hooks"]["timeline"])
        self.assertIn("r2 The Reeve's Wage Box done (Dilly Quickstep)", w["hooks"]["timeline"])
        self.assertIn("The Cottage on Lark Lane: to let, Marigold Thimble's to the end of day 7", w["hooks"]["prizes"])
        coverage = dict(live["coverage"])
        self.assertEqual((coverage["a grab"], coverage["a place let, taken or renewed"], coverage["an ending"], coverage["a quest taken on"]),
                         (1, 1, 1, 1))
        self.assertEqual(live["coverage"], [list(x) for x in json.loads(self.run_py("-c", "import json, sys; sys.path.insert(0, 'tools'); "
                         "import audit; print(json.dumps(audit.coverage(audit.read_jsonl(sys.argv[1]))))", str(log)).stdout)],
                         "the dashboard's strip and the audit count the same")

    def test_a_world_may_advise_the_referee_and_run_status_says_so(self):
        self.rpg("game", "switch", "wendleford")
        self.rpg("newgame", seed=47)
        status = self.rpg("run", "status")
        self.assertIn("FOR THE REFEREE (this world's own notes; follow them):\n- Wages", status)
        self.assertIn("no back pay is owed", status)
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=47)
        self.assertNotIn("FOR THE REFEREE", self.rpg("run", "status"), "a world without notes shows none")

    def test_a_page_says_how_far_the_worlds_time_has_moved_since_they_last_acted(self):
        self.rpg("game", "switch", "wendleford")
        self.rpg("newgame", seed=48)
        self.assertNotIn("Since you last acted", self.rpg("brief", "hobb"), "nothing before they've acted")
        order = [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().split(", ")]
        for pid in order:
            self.write("proposals/reply.txt", "DO: I wait.\nJOURNAL: Busy.\n")
            self.rpg("reply", pid, "proposals/reply.txt")
            self.write("proposals/story.txt", "The morning goes by.")
            self.rpg("narrate", pid, "proposals/story.txt")
        self.rpg("round", "end")
        brief = self.rpg("brief", "hobb")
        self.assertIn("Since you last acted: it was morning on day 1; now it's afternoon on day 1.", brief)
        self.assertNotIn("turn", brief.split("## Where you are")[1].split("\n")[3].lower(), "no talk of turns")
        self.assertIsNone(self.FORBIDDEN.search(brief.split("## Where you are")[1]))

    def test_the_log_exports_as_csv_one_row_per_entry(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=43)
        self.play_round()
        run = self.save()["run"]["id"]
        out = self.run_py("tools/dashboard.py", "--csv", run)
        rows = list(csv.DictReader(io.StringIO(out.stdout)))
        entries = self.log_of()
        self.assertEqual(len(rows), len(entries))
        self.assertEqual(list(rows[0])[:6], ["kind", "t", "round", "order_position", "player", "move"])
        self.assertEqual([r["kind"] for r in rows], [e["kind"] for e in entries])
        narration = next(r for r in rows if r["kind"] == "narration")
        self.assertTrue(narration["text"].startswith("Moment 1 for"))
        start = next(r for r in rows if r["kind"] == "round" and r["phase"] == "start")
        self.assertEqual(json.loads(start["order"]), next(e for e in entries if e["kind"] == "round")["order"])
        self.assertEqual(self.run_py("tools/dashboard.py", "--csv").stdout, out.stdout, "the current run by default")
        missing = self.run_py("tools/dashboard.py", "--csv", "nosuchrun")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("no log for run 'nosuchrun'", missing.stderr)

    def play_round(self):
        order = self.rpg("round", "start").split(": ", 1)[1].strip()
        ids = [part.split("(")[1].rstrip(")") for part in order.split(", ")]
        n = self.save()["run"]["round"]
        for pid in ids:
            self.take_turn(pid, story="Moment %d for %s." % (n, pid))
        return ids, self.rpg("round", "end")

    def test_rounds_draw_a_balanced_order_from_the_seed(self):
        self.three_players()
        self.rpg("newgame", "even-1")
        orders = [self.play_round()[0] for _ in range(30)]
        self.rpg("newgame", "even-1")
        self.assertEqual([self.play_round()[0] for _ in range(5)], orders[:5], "the same seed draws the same orders")
        self.assertEqual(len(set(map(tuple, orders))), 6, "every order turns up")
        for a in ("wren", "corin", "tam"):
            for b in ("wren", "corin", "tam"):
                if a < b:
                    ahead = sum(1 for o in orders if o.index(a) < o.index(b))
                    self.assertLessEqual(abs(ahead - (30 - ahead)), 2, (a, b, ahead))
        log = [json.loads(line) for line in (self.dir / "state" / "log" / ("%s.jsonl" % self.save()["run"]["id"])).read_text().splitlines()]
        starts = [e for e in log if e["kind"] == "round" and e["phase"] == "start"]
        self.assertEqual(len(starts), 5)
        self.assertEqual(starts[0]["draw"]["candidates"], 6)
        looks = [e for e in log if e["kind"] == "command" and e["command"] == "look" and e["round"] == 1]
        self.assertEqual([e["order_position"] for e in looks], [1, 2, 3])

    def test_a_round_goes_in_order_and_ends_when_everyone_has_had_their_turn(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=43)
        self.assertIn("no round is open", self.rpg("round", "end", ok=False))
        first, second = [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().split(", ")]
        self.assertIn("still open", self.rpg("round", "start", ok=False))
        self.assertIn("it's %s's turn" % first, self.rpg("look", as_=second, ok=False))
        self.write("proposals/reply.txt", "DO: I wait.")
        self.assertIn("it isn't %s's turn" % second, self.rpg("reply", second, "proposals/reply.txt", ok=False))
        self.write("proposals/story.txt", "You wait.")
        self.assertIn("hasn't replied", self.rpg("narrate", first, "proposals/story.txt", ok=False))
        self.write("proposals/reply.txt", "I just wait, no labels.")
        self.assertIn("no DO: line", self.rpg("reply", first, "proposals/reply.txt", ok=False))
        self.write("proposals/reply.txt", "DO: %s\nJOURNAL: Too much." % ("I wait. " * 160))
        self.assertIn("the DO line is at most 1200 characters", self.rpg("reply", first, "proposals/reply.txt", ok=False))
        self.assertIn("Next: %s." % second, self.take_turn(first))
        self.assertIn("still to act: %s" % second, self.rpg("round", "end", ok=False))
        status = self.rpg("run", "status", as_=False)
        self.assertIn("next to act: %s (waiting for their reply)" % second, status)
        pl = self.save()["players"][second]
        self.assertIn("%s (%s, opus, " % (pl["name"], second), status.split("CAST: ")[1])
        self.assertIn("STORY SO FAR: nothing yet", status)
        self.rpg("chronicle", "The lamp went out at dusk.", as_=second)
        self.assertIn("STORY SO FAR:\n- The lamp went out at dusk.\nROUND 1 OPEN", self.rpg("run", "status", as_=False),
                      "a referee starting a round reads where the story stands")
        self.write("proposals/reply.txt", "DO: I look around.")
        self.rpg("reply", second, "proposals/reply.txt")
        self.assertIn("next to act: %s (they have replied" % second, self.rpg("run", "status", as_=False))
        self.rpg("look", as_=second)
        self.write("proposals/story.txt", "You wait.")
        self.assertIn("Everyone has had their turn", self.rpg("narrate", second, "proposals/story.txt"))
        self.assertIn("ROUND 1 ENDS.", self.rpg("round", "end"))
        log = self.rpg("log", "40")
        self.assertIn("action", log)
        entries = [json.loads(line) for line in (self.dir / "state" / "log" / ("%s.jsonl" % self.save()["run"]["id"])).read_text().splitlines()]
        actions = [e for e in entries if e["kind"] == "action"]
        self.assertEqual([(e["player"], e["do"], e["model"], e["order_position"]) for e in actions],
                         [(first, "I look around.", "opus", 1), (second, "I look around.", "opus", 2)], "the model each was asked on")
        self.assertEqual(len([e for e in entries if e["kind"] == "narration"]), 2)

    def test_the_owner_pauses_resumes_and_ends_a_run_between_rounds(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=43)
        order = [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().split(", ")]
        self.take_turn(order[0])
        self.assertIn("PAUSE ASKED: round 1 is in progress (1 still to act), and finishes first", self.rpg("run", "pause"))
        self.take_turn(order[1])  # the round in progress goes on
        self.assertIn("NO MORE ROUNDS FOR NOW: the owner has paused the run", self.rpg("round", "end"))
        self.assertIn("paused the run", self.rpg("round", "start", ok=False))
        self.assertIn("RUN: pause asked; 1 round played", self.rpg("run", "status"))
        self.rpg("run", "resume")
        self.assertIn("isn't paused", self.rpg("run", "resume", ok=False))
        self.rpg("round", "start")
        self.assertIn("END ASKED: round 2 is in progress (2 still to act), and finishes first; then the run closes",
                      self.rpg("run", "end"))
        for pid in self.save()["run"]["round_state"]["order"]:
            self.take_turn(pid)
        self.assertIn("NO MORE ROUNDS FOR NOW: the run has ended (round 2 was its last)", self.rpg("round", "end"))
        self.assertIn("RUN: ended; 2 rounds played", self.rpg("run", "status"))
        self.assertIn("has ended", self.rpg("round", "start", ok=False))
        self.assertIn("already ended", self.rpg("run", "pause", ok=False))
        entries = [json.loads(line) for line in (self.dir / "state" / "log" / ("%s.jsonl" % self.save()["run"]["id"])).read_text().splitlines()]
        runs = [e for e in entries if e["kind"] == "run"]
        self.assertEqual([e["action"] for e in runs], ["pause", "resume", "end", "ended"])
        self.assertEqual((runs[-1]["rounds"], sorted(runs[-1]["players"])), (2, ["corin", "wren"]))
        self.rpg("newgame", seed=44)  # a new run starts afresh
        self.rpg("round", "start")

    def test_a_run_stops_at_the_owners_round_limit(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.settings_tool("preset", "simulation")
        self.assertIn("ROUNDS: the world's clock moves by round; at most 50 rounds per run", self.rpg("settings"))
        self.assertIn("MEMORY: the last 5 rounds word for word; older ones condensed every 5 rounds, or past 45000 characters held (self)",
                      self.rpg("settings"))
        self.settings_tool("set", "rounds.max_per_run", "2")
        self.rpg("newgame", seed=43)
        self.play_round()
        _, end = self.play_round()
        self.assertIn("NO MORE ROUNDS FOR NOW: the run has had its 2 rounds (rounds.max_per_run)", end)
        self.assertIn("had its 2 rounds", self.rpg("round", "start", ok=False))
        self.settings_tool("set", "rounds.max_per_run", "0")  # no limit
        self.assertIn("no limit on rounds", self.rpg("run", "status"))
        self.rpg("round", "start")
        self.assertIn("rounds.max_per_run must be a whole number", self.settings_tool("set", "rounds.max_per_run", "-1", ok=False))

    STAND_IN = """#!/usr/bin/env python3
import json, os, sys, pathlib
d = pathlib.Path(__file__).parent
n = 0
while True:  # claim the next number, safely when several are asked at once (the bench)
    try:
        os.close(os.open(str(d / ("asked-%d.txt" % n)), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        break
    except FileExistsError:
        n += 1
(d / ("asked-%d.txt" % n)).write_text(sys.stdin.read())
(d / ("argv-%d.json" % n)).write_text(json.dumps(sys.argv[1:]))
(d / ("cwd-%d.json" % n)).write_text(json.dumps([str(pathlib.Path.cwd()), sorted(p.name for p in pathlib.Path.cwd().iterdir())]))
answers = json.loads((d / "answers.json").read_text())
answer = answers[min(n, len(answers) - 1)]
if answer == "<fail>":
    print(json.dumps({"type": "result", "is_error": True, "result": "API Error: overloaded"})); sys.exit(1)
print(json.dumps({"type": "result", "is_error": False, "result": answer, "total_cost_usd": 0.0012, "modelUsage": {"claude-test-1": {}}}))
"""

    def ask(self, *args, answers, ok=True, tool="tools/ask.py"):
        """tools/ask.py (or another tool that asks through it) with a stand-in for claude that keeps what it was
        handed (asked-<n>.txt, argv-<n>.json) and gives the answers in turn ("<fail>": no answer comes)."""
        shutil.rmtree(self.dir / "stand_in", ignore_errors=True)
        stand_in = self.write("stand_in/claude", self.STAND_IN)
        stand_in.chmod(0o755)
        self.write("stand_in/answers.json", json.dumps(answers))
        env = dict(os.environ, CODERPG_CLAUDE=str(stand_in))
        r = subprocess.run([sys.executable, tool, *args], cwd=self.dir, env=env, capture_output=True, text=True, timeout=60)
        self.assertNotIn("Traceback", r.stderr, r.stderr)
        self.assertEqual(r.returncode == 0, ok, r.stdout + r.stderr)
        asked = sorted((self.dir / "stand_in").glob("asked-*.txt"))
        return r.stdout, [a.read_text() for a in asked], [json.loads((self.dir / "stand_in" / ("argv-%d.json" % i)).read_text())
                                                        for i in range(len(asked))]

    def test_the_story_so_far_is_the_referees_own_record_for_no_one_at_any_time(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.rpg("newgame", seed=43)
        first, second = [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().split(", ")]
        self.take_turn(first)
        self.assertIn("CHRONICLED", self.rpg("chronicle", "The lamp went out at dusk.", as_=first),
                      "a line written after their story is stored, though the turn is no longer theirs")
        self.take_turn(second)
        self.rpg("round", "end")
        self.rpg("chronicle", "Nobody slept.", as_=False)
        self.assertEqual(self.save()["run"]["chronicle"][-2:], ["The lamp went out at dusk.", "Nobody slept."])
        lines = [e for e in self.log_entries() if e["kind"] == "command" and e["command"] == "chronicle"]
        self.assertEqual([(e["refused"], e["player"]) for e in lines], [(False, None), (False, None)], "no one's, each time")

    def test_the_procedures_name_the_story_lines_limit_as_the_rules_set_it(self):
        limit = json.loads((ROOT / "rules" / "balance.json").read_text())["world"]["text_line_chars"]
        for skill in ("rounds", "gm-turn"):
            text = (ROOT / ".claude" / "skills" / skill / "SKILL.md").read_text()
            said = re.findall(r"chronicle \"<one line, past tense>\"`, with no `--as`[^.]*?at most (\d+) characters", text)
            self.assertEqual(said, [str(limit)], "%s names the chronicle's limit, and it's the one the rules enforce" % skill)

    def log_entries(self):
        return [json.loads(line) for line in (self.dir / "state" / "log" / ("%s.jsonl" % self.save()["run"]["id"])).read_text().splitlines()]

    def test_audit_looks_for_signs_of_claude_codes_lines_in_what_people_wrote(self):
        self.rpg("game", "switch", "flooded_station")
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=44)
        first = self.rpg("round", "start").split(": ", 1)[1].split("(")[1].split(")")[0]
        year = str(datetime.date.today().year)
        self.write("proposals/reply.txt", "DO: I write a haiku about the tide.\nJOURNAL: It's %s, and someone@example.org owes me.\n" % year)
        self.rpg("reply", first, "proposals/reply.txt")
        self.rpg("look", as_=first)
        self.write("proposals/story.txt", "You think of Claude, an old friend.")  # the referee's words: not looked at
        self.rpg("narrate", first, "proposals/story.txt")
        out = self.run_py("tools/audit.py", "state/log/%s.jsonl" % self.save()["run"]["id"]).stdout
        signs = out.split("== SIGNS OF CLAUDE CODE'S LINES\n")[1].split("\n== ")[0].splitlines()
        self.assertEqual([s.split(": ...")[0] for s in signs],
                         ["  r1 %s do 'haiku'" % first, "  r1 %s journal '%s'" % (first, year), "  r1 %s journal 'someone@example.org'" % first])
        self.assertIn("== LEAKS\n  none", out, "a separate list from the leaks")

    def test_audit_shows_what_the_referee_kept_for_later_rounds(self):
        self.rpg("game", "switch", "thirteenth_stroke")
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=43)  # Marigold and Dilly in the square, with Mags (minor) and Pip (agent)
        self.round_with(marigold=lambda pid: self.turn(pid, "I ask Mags what she buys.", ("look",), ("show", "characters", "mags"),
                                                       ("note", "Mags's cart has a squeaky left wheel."), ("show", "characters", "pip")),
                        dilly=lambda pid: self.turn(pid, "I ask Mags about bottles.", ("look",), ("show", "characters", "mags"),
                                                    ("remember", "mags", "Asked after bottles; promised one by dusk."),
                                                    ("chronicle", "Dilly promised Mags a bottle by dusk.")))
        out = self.run_py("tools/audit.py", "state/log/%s.jsonl" % self.save()["run"]["id"]).stdout
        self.assertIn("== CONTINUITY\n  r1: 1 notes, 1 story lines, 1 remembered\n  r1 marigold: mags (minor) spoken to, nothing remembered\n== ", out,
                      "Pip speaks through an agent, and Dilly's turn kept what Mags learned")

    def test_audit_scans_only_what_people_read_for_leaks(self):
        entries = [{"kind": "witnessed", "round": 1, "player": "a", "text": "She waved.", "learned": ["heard_of_shadows"]},
                   {"kind": "memory", "round": 1, "player": "a", "text": "I waved.", "learned": ["The rules here are odd."]}]
        hits = json.loads(self.run_py("-c", "import json, sys; sys.path.insert(0, 'tools'); import audit; "
                                      "print(json.dumps(audit.leaks(json.loads(sys.argv[1]))))", json.dumps(entries)).stdout)
        self.assertEqual(len(hits), 1, hits)  # the memory's learned list is read; a note's flag names aren't
        self.assertIn("memory 'rules'", hits[0])

    def test_audit_reads_a_run_back(self):
        self.rpg("game", "switch", "flooded_station")  # Sol and Ade both start on the Landing
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=44)
        first, second = [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().split(", ")]
        self.write("proposals/reply.txt", "DO: I wave.\nJOURNAL: To be friendly.\n")
        self.rpg("reply", first, "proposals/reply.txt")
        self.rpg("look", as_=first)
        self.write("proposals/note.txt", "Someone waved from the far end of the landing.")
        self.rpg("witnessed", "proposals/note.txt", as_=first)
        self.write("proposals/story.txt", "You wave.")
        self.rpg("narrate", first, "proposals/story.txt")
        self.take_turn(second)  # someone there, and no note: the audit says so
        self.rpg("round", "end")
        brief = self.rpg("brief", first)
        rows = [{"type": "assistant", "message": {"id": "m1", "usage": {"input_tokens": 10, "cache_read_input_tokens": 990, "output_tokens": 5},
                 "content": [{"type": "tool_use", "name": "Bash", "input": {"command": "python3 rules/rpg.py look --as %s | sed -n 1,5p" % first}},
                             {"type": "tool_use", "name": "Agent", "input": {"subagent_type": "npc", "prompt": "Made up by the referee."}},
                             {"type": "tool_use", "name": "Agent", "input": {"subagent_type": "player", "model": "haiku", "prompt": brief}}]}}]
        self.write("transcript.jsonl", "\n".join(json.dumps(r) for r in rows))
        log = "state/log/%s.jsonl" % self.save()["run"]["id"]
        r = self.run_py("tools/audit.py", log, "--transcript", "transcript.jsonl")
        out = r.stdout
        self.assertEqual(r.returncode, 0, out)
        self.assertIn("== LEAKS\n  none", out)
        self.assertIn("2 turns with someone else there, 1 with a note", out)
        self.assertIn("r1 %s: no note" % second, out)
        self.assertIn("== COINS\n  none moved", out)
        self.assertIn("  %s: none" % first, out.split("== FLAGS")[1])
        self.assertIn("== CUT READS\n  look: 1", out)
        self.assertIn("npc (its own model): <<< NOT what rpg.py printed", out)
        self.assertIn("player (haiku): holds what rpg.py printed", out)
        self.assertIn("1 calls; largest context 1000 tokens; 5 output tokens", out)

    def test_ask_hands_the_brief_on_unchanged_and_stores_the_reply(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=43)
        first = self.rpg("round", "start").split(": ", 1)[1].split("(")[1].split(")")[0]
        out, asked, argv = self.ask(first, answers=["DO: I look out to sea.\nJOURNAL: To get my bearings."])
        self.assertIn("REPLY from", out)
        self.assertIn("DO: I look out to sea.", out)
        self.assertNotIn("## Who I am", out, "the referee never holds the brief")
        briefs = [e["text"] for e in self.log_entries() if e["kind"] == "brief"]
        self.assertEqual(asked, [briefs[-1]], "the brief, byte for byte as printed and logged")
        model = "opus"  # the one model the settings name for everyone (cast.model)
        self.assertEqual(argv[0][argv[0].index("--model") + 1], model)
        self.assertEqual(argv[0][argv[0].index("--effort") + 1], "medium", "the effort player.md names")
        for flag in ("-p", "--safe-mode", "--no-session-persistence"):
            self.assertIn(flag, argv[0])
        self.assertEqual(argv[0][argv[0].index("--tools") + 1], "", "no tools")
        system = argv[0][argv[0].index("--system-prompt") + 1]
        self.assertTrue(system.startswith("You are a person living your own life."), system[:80])
        self.assertNotIn("---", system, "the instructions without player.md's front matter")
        where = Path(json.loads((self.dir / "stand_in" / "cwd-0.json").read_text())[0]).resolve()
        self.assertEqual(where, Path("/tmp/here").resolve(), "asked from a plain folder outside the game's")
        for name in (self.dir.name, ROOT.name, "coderpg", getpass.getuser()):
            self.assertNotIn(name.lower(), where.as_posix().lower(), "whose path names neither the game's folder nor the owner")
        self.assertFalse(any((d / ".git").exists() for d in (where, *where.parents)), "and isn't in a git repository")
        action =[e for e in self.log_entries() if e["kind"] == "action"][-1]
        self.assertEqual((action["do"], action["spend"]), ("I look out to sea.", 0.0012))
        self.assertIn("already replied", self.rpg("reply", first, "proposals/reply-%s.txt" % first, ok=False))

    def test_the_log_records_which_version_of_each_text_a_person_was_given(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=43)

        def round_through_ask():
            order = [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().split(", ")]
            sent = []
            for pid in order:
                _, _, argv = self.ask(pid, answers=["DO: I wait.\nJOURNAL: To see."])
                sent.append(argv[0][argv[0].index("--system-prompt") + 1])
                self.rpg("look", as_=pid)
                self.write("proposals/story.txt", "You wait.")
                self.rpg("narrate", pid, "proposals/story.txt")
            self.rpg("round", "end")
            return order, sent

        order, sent = round_through_ask()
        entries = self.log_entries()
        tag = lambda text: hashlib.sha256(text.encode()).hexdigest()[:8]  # noqa: E731
        first = [e for e in entries if e["kind"] == "action" and e["player"] == order[0]][0]
        shared = ["brief", "thinkback", "universe", "public:dark_lighthouse", "instructions:player"]  # the world's public knowledge too
        self.assertEqual(sorted(first["versions"]), sorted(shared + ["cast:" + order[0]]))
        self.assertEqual(first["versions"]["instructions:player"], tag(sent[0]), "the instructions as sent to them")
        self.assertEqual([e["versions"] for e in entries if e["kind"] == "brief" and e["player"] == order[0]], [first["versions"]])
        texts = [e for e in entries if e["kind"] == "text"]
        self.assertEqual(sorted(e["name"] for e in texts), sorted(shared + ["cast:" + p for p in order]),
                         "each text logged whole once, however often it's used")
        whole = {e["name"]: e for e in texts}
        self.assertEqual(whole["instructions:player"]["text"], sent[0])
        self.assertEqual(whole["brief"]["text"], (self.dir / "rules" / "people" / "brief.md").read_text())
        self.assertEqual(tag(whole["brief"]["text"]), first["versions"]["brief"])
        brief = self.dir / "rules" / "people" / "brief.md"
        brief.write_text(brief.read_text() + "# edited partway\n")  # a new version, though no one reads a comment
        round_through_ask()
        texts = [e for e in self.log_entries() if e["kind"] == "text"]
        self.assertEqual([e["round"] for e in texts if e["name"] == "brief"], [1, 2], "the new version logged whole when first used")
        out = self.run_py("tools/audit.py", "state/log/%s.jsonl" % self.save()["run"]["id"]).stdout
        line = next(l for l in out.split("== VERSIONS\n")[1].splitlines() if l.startswith("  brief:"))
        self.assertTrue(line.endswith("(r2-2)  <<< changed partway"), line)
        self.assertIn("  instructions:player: %s (r1-2)\n" % tag(sent[0]), out)

    def test_everyone_is_asked_on_one_model_unless_the_settings_say_each_their_own(self):
        self.rpg("game", "switch", "thirteenth_stroke")
        self.settings_tool("preset", "simulation")
        self.assertIn("PEOPLE: everyone asked on opus", self.rpg("settings"))
        cast = json.loads((self.dir / "games" / "thirteenth_stroke" / "cast.json").read_text())
        self.assertGreater(len({e["model"] for e in cast}), 1, "the cast names more than one model of its own")
        self.rpg("newgame", seed=43)
        status = self.rpg("run", "status", as_=False)
        for e in cast:
            self.assertIn("(%s, opus, " % e["id"], status)
        first = self.rpg("round", "start").split(": ", 1)[1].split("(")[1].split(")")[0]
        _, _, argv = self.ask(first, answers=["DO: I wait.\nJOURNAL: To see."])
        self.assertEqual(argv[0][argv[0].index("--model") + 1], "opus")
        action = [e for e in self.log_entries() if e["kind"] == "action"][-1]
        self.assertEqual((action["model"], action["exact_model"]), ("opus", "claude-test-1"), "the nickname, and the version that answered")
        out = self.run_py("tools/audit.py", "state/log/%s.jsonl" % self.save()["run"]["id"]).stdout
        self.assertIn("  model opus: claude-test-1 (r1-1)\n", out)
        self.settings_tool("set", "cast.model", "own")
        self.assertIn("PEOPLE: each asked on their own model", self.rpg("settings"))
        status = self.rpg("run", "status", as_=False)
        for e in cast:
            self.assertIn("(%s, %s, " % (e["id"], e["model"]), status)
        self.assertIn("cast.model must be haiku or sonnet or opus or fable or own", self.settings_tool("set", "cast.model", "gpt", ok=False))
        self.settings_tool("set", "cast.model", "own")  # a refused value stays saved until it's put right
        path = self.dir / "games" / "thirteenth_stroke" / "cast.json"
        path.write_text(json.dumps([{k: v for k, v in e.items() if k != "model"} for e in cast]))
        self.assertIn("needs a model, since the settings ask each person's own", self.rpg("validate", "--game", "thirteenth_stroke", ok=False))
        self.settings_tool("set", "cast.model", "haiku")
        self.rpg("validate", "--game", "thirteenth_stroke")

    def test_the_bench_puts_kept_moments_again_under_each_variant(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=43)
        order = [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().split(", ")]
        logged = self.rpg("brief", order[0])
        for pid in order:
            self.take_turn(pid)
        self.rpg("round", "end")
        log = "state/log/%s.jsonl" % self.save()["run"]["id"]
        bench = lambda *a, answers=("DO: I wait.\nJOURNAL: x",), ok=True: self.ask(*a, answers=list(answers), ok=ok, tool="tools/bench.py")  # noqa: E731
        self.assertIn("KEPT past: %s, " % order[0], bench("add", "past", log, order[0], "1", "--note", "a moment from round 1")[0])
        self.assertEqual(json.loads((self.dir / "bench/moments/past.json").read_text())["brief"] + "\n", logged, "the brief as logged")
        self.assertIn("KEPT now: %s, " % order[1], bench("save", "now", order[1])[0])
        self.assertIn("frozen", bench("list")[0])
        words = self.dir / "rules" / "people" / "brief.md"
        words.write_text(words.read_text().replace("closing:         What do you do now?", "closing: And now?"))
        out, asked, _ = bench("run", "--dry")
        self.assertEqual(asked, [], "a dry run asks no one")
        self.assertIn("(%s, frozen)\n%s\n" % (order[0], logged.rstrip("\n")), out, "a frozen brief is as it was")
        self.assertIn("(%s, rebuilt now)" % order[1], out)
        rebuilt = out.split("(%s, rebuilt now)\n" % order[1])[1].split("\n\n===== ")[0]
        self.assertTrue(rebuilt.rstrip().endswith("And now?"), "a saved game's brief has the new wording")
        self.write("bench/variants/plain.md", "---\nname: plain\n---\nYou are someone. Reply with DO: and JOURNAL: lines.\n")
        entries = len(self.log_entries())
        out, asked, argv = bench("run", "--variant", ".claude/agents/player.md", "--variant", "bench/variants/plain.md", "--times", "2",
                                 answers=["DO: I think of Claude.\nJOURNAL: x"])
        self.assertEqual(len(asked), 8, "2 moments, 2 variants, twice each")
        self.assertEqual(len(set(asked)), 2, "two briefs, each sent the same every time")
        self.assertIn(logged.rstrip("\n"), asked, "the frozen one byte for byte")
        self.assertIn(rebuilt.rstrip("\n"), asked, "the rebuilt one as the dry run showed it")
        systems = {a[a.index("--system-prompt") + 1] for a in argv}
        self.assertIn("You are someone. Reply with DO: and JOURNAL: lines.", systems)
        self.assertEqual(len(systems), 2)
        self.assertEqual({(a[a.index("--model") + 1], a[a.index("--effort") + 1]) for a in argv}, {("opus", "medium")},
                         "play's model and effort, whatever the variant")
        self.assertIn("===== now: %s" % order[1], out)
        self.assertIn("--- plain (instructions ", out)
        self.assertIn("== LEAKS IN THE BRIEFS\n  none", out)
        self.assertIn("'Claude'", out.split("== SIGNS OF CLAUDE CODE'S LINES IN THE REPLIES\n")[1])
        self.assertIn("== THE REPLY FORM (as `rpg.py reply` would read it)\n", out)
        self.assertIn("\n  past, today: 2 of 2 taken; options in 0 (-); one marked chosen in 0\n", out)
        kept = json.loads(sorted((self.dir / "bench/results").glob("*.json"))[-1].read_text())
        self.assertEqual((len(kept["replies"]), sorted(kept["variants"]), kept["moments"]["past"]["kind"]), (8, ["plain", "today"], "brief"))
        self.assertEqual(kept["replies"][0]["exact_model"], "claude-test-1")
        self.assertEqual(len(self.log_entries()), entries, "the game's own log is untouched")
        out = bench("run", "past", "--times", "1", answers=["OPTIONS:\n- Wait (for: rest)\n* Go (for: news)\nDO: I go.\nJOURNAL: x"])[0]
        self.assertIn("\n  past, today: 1 of 1 taken; options in 1 (2); one marked chosen in 1\n", out)

    def test_the_bench_keeps_a_think_back_from_a_log_and_reads_its_replies_as_memory_store_would(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.settings_tool("preset", "simulation")
        self.settings_tool("set", "memory.recent_rounds", "1")
        self.settings_tool("set", "memory.condense_every", "1")
        self.rpg("newgame", seed=43)
        self.play_round()
        self.play_round()
        think = self.rpg("memory", "condense", "wren")
        log = "state/log/%s.jsonl" % self.save()["run"]["id"]
        bench = lambda *a, answers=(), ok=True: self.ask(*a, answers=list(answers), ok=ok, tool="tools/bench.py")  # noqa: E731
        bench("add", "tb", log, "wren", "1", "--thinkback", ok=False)  # nothing was folded in round 1
        bench("add", "tb", log, "wren", "2", "--thinkback")
        stretch = json.loads((self.dir / "bench/moments/tb.json").read_text())["stretch"]
        self.assertTrue(stretch.startswith("### Moment 1") and stretch in think and "Reply" not in stretch, stretch)
        self.assertIn("think", bench("list")[0])
        out, asked, _ = bench("run", "tb", "--times", "2", answers=["MEMORY: I looked about.\nLEARNED: Morwen keeps the lamp.\nLEARNED: x", "I forgot the form."])
        self.assertEqual(asked, [think.rstrip("\n")] * 2, "the stretch kept, the rest built afresh: as asked in the run")
        think_md = self.dir / "rules" / "people" / "thinkback.md"
        think_md.write_text(think_md.read_text().replace("Some time has passed.", "Days have gone by."))
        self.assertIn("Days have gone by. Think back", bench("run", "tb", "--dry")[0], "the current wording")
        self.assertIn("\n  tb, today: a memory in 2 of 2; things learned in each: ", out)
        self.assertTrue(re.search(r"things learned in each: (2, -|-, 2)\n", out), out)

    def voice(self, *args, answers, ok=True):
        return self.ask(*args, answers=answers, ok=ok, tool="tools/voice.py")

    def test_voice_asks_a_townsperson_with_their_brief_and_the_scene_unchanged(self):
        self.rpg("game", "switch", "thirteenth_stroke")
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=43)  # Marigold and Dilly in the square, with Mags (minor) and Pip (agent)
        first = self.rpg("round", "start").split(": ", 1)[1].split("(")[1].split(")")[0]
        self.write("proposals/reply.txt", "DO: I ask Pip where the toys went.\nJOURNAL: To find out.\n")
        self.rpg("reply", first, "proposals/reply.txt")
        self.rpg("look", as_=first)
        self.write("proposals/scene-pip.txt", "## What just happened\nShe asks where the toys went.")
        out, asked, _ = self.voice("npc", "pip", "proposals/scene-pip.txt", "--as", first, answers=["SAY: Hi."], ok=False)
        self.assertIn("VOICE REFUSED", out)
        self.assertEqual(asked, [], "a scene without both parts asks no one")
        scene = "## The scene so far\n(the scene just began)\n\n## What just happened\nShe asks Pip where the toys went."
        self.write("proposals/scene-pip.txt", scene + "\n")
        reply = "SAY: Down the lane! *points*\nINTENT: none\nREMEMBER: Asked about the toys."
        out, asked, argv = self.voice("npc", "pip", "proposals/scene-pip.txt", "--as", first, answers=[reply])
        self.assertEqual(out, "REPLY from pip:\n%s\n" % reply, "only the reply: the referee never holds the brief")
        brief = [e for e in self.log_entries() if e["kind"] == "command" and e["command"] == "npc-brief"][-1]["output"]
        self.assertTrue(brief.startswith("You are Pip"), brief[:40])
        self.assertEqual(asked, [brief + "\n\n" + scene], "the brief as printed, then the referee's two parts, byte for byte")
        self.assertEqual((argv[0][argv[0].index("--model") + 1], argv[0][argv[0].index("--effort") + 1]), ("sonnet", "medium"),
                         "the model and effort npc.md names")
        self.assertEqual(argv[0][argv[0].index("--tools") + 1], "")
        system = argv[0][argv[0].index("--system-prompt") + 1]
        self.assertTrue(system.startswith("You are playing one character"), system[:60])
        self.assertNotIn("omitClaudeMd", system, "npc.md's instructions without its front matter")
        voiced = [e for e in self.log_entries() if e["kind"] == "voice"]
        self.assertEqual([(e["agent"], e["about"], e["player"], e["model"], e["effort"], e["added"], e["reply"], e["spend"]) for e in voiced],
                         [("npc", "pip", first, "sonnet", "medium", scene, reply, 0.0012)])
        self.assertEqual(voiced[0]["versions"], {"instructions:npc": hashlib.sha256(system.encode()).hexdigest()[:8]},
                         "the version of the instructions it was asked with")
        self.assertFalse((self.dir / "proposals" / "voiced.json").exists(), "the record is used up once logged")
        out, asked, _ = self.voice("npc", "mags", "proposals/scene-pip.txt", "--as", first, answers=["SAY: Hi."], ok=False)
        self.assertIn("minor character", out)
        self.assertEqual(asked, [], "a refused brief asks no one")

    def test_voice_asks_the_world_agent_and_keeps_its_proposal_exactly(self):
        self.rpg("game", "switch", "thirteenth_stroke")
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=43)
        self.play_round()
        proposal = '{"rumors": ["The fog is thick tonight."], "plans": []}'
        out, asked, argv = self.voice("world", "turn", answers=[proposal])  # between rounds: no one's
        self.assertEqual(out, "PROPOSAL from the world agent (turn), saved exactly as given to proposals/world-turn.json:\n%s\n" % proposal)
        self.assertEqual((self.dir / "proposals" / "world-turn.json").read_text(), proposal)
        briefs = [e for e in self.log_entries() if e["kind"] == "command" and e["command"] == "world-brief"]
        self.assertEqual(asked, [briefs[-1]["output"]], "the brief alone, as printed")
        self.assertTrue(argv[0][argv[0].index("--system-prompt") + 1].startswith("You add small things"))
        meter = self.meter_file()
        self.write("proposals/why.txt", "Your last proposal was refused: rumors must be short.")
        out, asked, _ = self.voice("world", "turn", "proposals/why.txt", "--again", answers=[proposal])
        self.assertEqual(asked, [briefs[-1]["output"] + "\n\nYour last proposal was refused: rumors must be short."])
        self.assertEqual(len([e for e in self.log_entries() if e["kind"] == "command" and e["command"] == "world-brief"]), 1,
                         "asked again on the same brief: world-brief isn't run twice")
        self.assertEqual(self.meter_file(), meter, "so nothing is charged twice")
        voiced = [(e["agent"], e["about"], e["player"], e["again"]) for e in self.log_entries() if e["kind"] == "voice"]
        self.assertEqual(voiced, [("world", "turn", None, False), ("world", "turn", None, True)])
        out, asked, _ = self.voice("world", "turn", answers=["<fail>"], ok=False)
        self.assertIn("VOICE FAILED: the world agent for turn didn't answer, twice", out)
        self.assertEqual(len(asked), 2, "asked once more, then given up")
        self.assertEqual(len([e for e in self.log_entries() if e["kind"] == "voice"]), 2, "nothing logged for a call that didn't come")
        audit = self.run_py("tools/audit.py", "state/log/%s.jsonl" % self.save()["run"]["id"]).stdout
        self.assertIn("== VOICES\n  r1 no one: world agent for turn (sonnet, medium)\n  r1 no one: world agent for turn (sonnet, medium), asked again\n", audit)
        self.assertIn("  world agent, sonnet: 2 replies, $0.00", audit)

    SENDER = """#!/usr/bin/env python3
import json, os, sys, urllib.request
if sys.argv[1:] == ["--version"]:
    print("9.9.9 (Claude Code)"); sys.exit(0)
system = sys.argv[sys.argv.index("--system-prompt") + 1]
body = {"system": [{"type": "text", "text": "x-billing-line"}, {"type": "text", "text": system}],
        "messages": [{"role": "user", "content": [{"type": "text", "text": "a reminder with an email"},
                                                  {"type": "text", "text": sys.stdin.read()}]},
                     {"role": "system", "content": [{"type": "text", "text": "# Environment\\nWorking directory: " + os.getcwd()}]}],
        "tools": []}
req = urllib.request.Request(os.environ["ANTHROPIC_BASE_URL"] + "/v1/messages?beta=true", data=json.dumps(body).encode(),
                             headers={"Authorization": "Bearer SECRET-TOKEN-123", "content-type": "application/json"})
try:
    urllib.request.urlopen(req)
except Exception:
    pass
print(json.dumps({"type": "result", "is_error": True, "result": "API Error: 400"})); sys.exit(1)
"""

    REFEREE = """#!/usr/bin/env python3
import json, os, pathlib, re, subprocess, sys
d = pathlib.Path(__file__).parent
n = len(list(d.glob("call-*.json")))
(d / ("call-%d.json" % n)).write_text(json.dumps({"argv": sys.argv[1:], "no_refill": os.environ.get("CODERPG_NO_REFILL")}))
rpg = lambda *a: subprocess.run([sys.executable, "rules/rpg.py", *a], capture_output=True, text=True).stdout
subprocess.run([sys.executable, ".claude/hooks/session_start.py"], input=b"{}", capture_output=True)  # as Claude Code would
meter = pathlib.Path("state/meter.json")
m = json.loads(meter.read_text())
m["left"] -= 2  # a world turn's price
meter.write_text(json.dumps(m))
mode = os.environ.get("STAND_IN", "")
if mode == "fail@%d" % n:
    print(json.dumps({"type": "result", "is_error": True, "result": "API Error: overloaded"}))
    sys.exit(1)
order = re.findall(r"\\((\\w+)\\)", rpg("round", "start"))
for i, pid in enumerate(order):
    if mode == "open@%d" % n and i == 1:
        break
    pathlib.Path("proposals/r.txt").write_text("DO: I wait.\\nJOURNAL: x\\n")
    rpg("reply", pid, "proposals/r.txt")
    rpg("look", "--as", pid)
    pathlib.Path("proposals/s.txt").write_text("You wait.")
    rpg("narrate", pid, "proposals/s.txt")
    if mode == "pause@%d" % n and i == 0:
        rpg("run", "pause")  # the owner presses Pause mid-round
else:
    rpg("round", "end")
print(json.dumps({"type": "assistant", "message": {"usage": {"input_tokens": 10, "cache_read_input_tokens": 20000 + 1000 * n}}}))
print(json.dumps({"type": "result", "is_error": False, "result": "Round done.", "session_id": "s%d" % n, "total_cost_usd": 0.4}))
"""

    def run_rounds(self, *args, mode=""):
        """tools/rounds.py with a stand-in referee that plays each round through rpg.py. Returns its output and the calls."""
        shutil.rmtree(self.dir / "referee", ignore_errors=True)
        stand_in = self.write("referee/claude", self.REFEREE)
        stand_in.chmod(0o755)
        r = subprocess.run([sys.executable, "tools/rounds.py", *args], cwd=self.dir, capture_output=True, text=True, timeout=120,
                           env=dict(os.environ, CODERPG_CLAUDE=str(stand_in), STAND_IN=mode))
        self.assertNotIn("Traceback", r.stderr, r.stderr)
        calls = [json.loads((self.dir / "referee" / ("call-%d.json" % i)).read_text()) for i in range(len(list((self.dir / "referee").glob("call-*.json"))))]
        return r.stdout, calls

    def test_rounds_runs_each_round_with_a_fresh_referee(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=43)
        self.set_meter(9)
        out, calls = self.run_rounds("3")
        self.assertIn("REFILLED", out)
        for n in (1, 2, 3):
            self.assertRegex(out, r"ROUND %d: \$0\.40, \dm\d\ds" % n)
        self.assertIn("context up to 22k. Round done.\nSTOPPED: the 3 rounds asked for are done.\n3 rounds run, $1.20 for the referee", out)
        self.assertEqual([(c["argv"][:2], c["argv"][c["argv"].index("--model") + 1], c["no_refill"]) for c in calls],
                         [(["-p", "/rounds 1 from-script"], "sonnet", "1")] * 3, "one fresh session a round")
        self.assertEqual(self.meter_file(), 24, "refilled once when the run started, never by a round's session")
        refs = [(e["round_run"], e["session"], e["spend"], e["context"]) for e in self.log_entries() if e["kind"] == "referee"]
        self.assertEqual(refs, [(1, "s0", 0.4, 20010), (2, "s1", 0.4, 21010), (3, "s2", 0.4, 22010)])
        for n in range(2):  # two of the three sessions' transcripts, where Claude Code keeps them
            rows = [{"type": "assistant", "message": {"id": "m%d" % n, "usage": {"input_tokens": 5, "cache_read_input_tokens": 995 + n, "output_tokens": 7},
                     "content": [{"type": "tool_use", "name": "Bash", "input": {"command": "python3 rules/rpg.py look --as wren | head -5"}}]}}]
            self.write("projects/-some-folder/s%d.jsonl" % n, "\n".join(json.dumps(r) for r in rows))
        r = subprocess.run([sys.executable, "tools/audit.py", "--referee"], cwd=self.dir, capture_output=True, text=True,
                           env=dict(os.environ, CODERPG_PROJECTS=str(self.dir / "projects")))
        self.assertIn("== CUT READS\n  look: 2\n", r.stdout)
        self.assertRegex(r.stdout, r"== REFEREE, A ROUND A LINE\n  r1: \$0\.40, \d+s, 1 calls, largest context 1000 tokens, 7 output tokens\n"
                                   r"  r2: \$0\.40, \d+s, 1 calls, largest context 1001 tokens, 7 output tokens\n"
                                   r"  r3: \$0\.40, \d+s, context up to 22010 tokens; session s2 not found")
        self.settings_tool("set", "rounds.max_per_run", "4")
        out, calls = self.run_rounds("--model", "opus")
        self.assertIn("ROUND 4: $0.40", out)
        self.assertIn("STOPPED: the run has had its 4 rounds (rounds.max_per_run)", out)
        self.assertEqual([c["argv"][c["argv"].index("--model") + 1] for c in calls], ["opus"])

    def test_rounds_stops_for_a_pause_a_failed_session_or_a_round_left_open(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=43)
        self.rpg("run", "pause", as_=False)
        out, calls = self.run_rounds("3", mode="pause@0")
        self.assertIn("RESUMED", out, "starting it is the owner's say to go on")
        self.assertIn("ROUND 1: ", out)
        self.assertIn("STOPPED: the owner asked for a pause", out, "a pause pressed mid-round stops it after that round")
        self.assertEqual(len(calls), 1)
        out, calls = self.run_rounds("3", mode="fail@0")
        self.assertIn("STOPPED: round 2's referee session failed (API Error: overloaded)", out)
        self.assertNotIn("ROUND 2 OPEN", self.rpg("run", "status", as_=False))
        out, calls = self.run_rounds("3", mode="open@1")
        self.assertIn("ROUND 2: ", out)
        self.assertIn("STOPPED: round 3 was left open (Round done.); the next run finishes it.", out)
        self.assertIn("ROUND 3 OPEN", self.rpg("run", "status", as_=False))

    def test_probe_shows_what_a_person_is_sent_and_keeps_no_token(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=43)
        self.rpg("round", "start")
        sender = self.write("stand_in/claude", self.SENDER)
        sender.chmod(0o755)
        save, logged = self.save(), len(self.log_entries())
        r = subprocess.run([sys.executable, "tools/probe.py", "corin"], cwd=self.dir, env=dict(os.environ, CODERPG_CLAUDE=str(sender)),
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = r.stdout
        self.assertIn("PROBE: corin (", out)
        self.assertIn("9.9.9 (Claude Code), asked from %s. 1 request(s) reached the stand-in, none went on" % Path("/tmp/here").resolve(), out)
        self.assertIn("== system[0]\nx-billing-line\n== system[1] (the player's instructions, exactly)\nYou are a person living your own life.", out)
        self.assertIn("== messages[0] user, part 1\na reminder with an email\n== messages[0] user, part 2 (the brief, exactly)\n", out)
        self.assertIn("== messages[1] system, part 1\n# Environment\nWorking directory: %s" % Path("/tmp/here").resolve(), out)
        self.assertIn("== tools: none", out)
        self.assertNotIn("SECRET-TOKEN", out + r.stderr)
        self.assertNotIn("Authorization", out + r.stderr)
        self.assertEqual(self.save(), save, "the brief was made from a copy")
        self.assertEqual(len(self.log_entries()), logged)

    def test_ask_asks_once_more_when_a_reply_is_refused_and_then_gives_up(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=43)
        first = self.rpg("round", "start").split(": ", 1)[1].split("(")[1].split(")")[0]
        out, asked, _ = self.ask(first, answers=["I just stand there.", "DO: I wait.\nJOURNAL: Nothing yet."])
        self.assertIn("DO: I wait.", out)
        self.assertEqual(len(asked), 2)
        self.assertEqual(asked[0], asked[1], "asked again with the same brief")
        self.rpg("game", "switch", "flooded_station")
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=43)
        first = self.rpg("round", "start").split(": ", 1)[1].split("(")[1].split(")")[0]
        out, asked, _ = self.ask(first, answers=["Nothing to say."], ok=False)
        self.assertIn("ASK FAILED: %s's reply was refused twice" % first, out)
        self.assertEqual(len(asked), 2)

    def test_ask_memory_condenses_through_the_person_and_asks_nothing_when_nothing_is_due(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.settings_tool("preset", "simulation")
        self.settings_tool("set", "memory.recent_rounds", "1")
        self.settings_tool("set", "memory.max_chars", "50")
        self.rpg("newgame", seed=43)
        self.play_round()
        out, asked, _ = self.ask("wren", "--memory", answers=["MEMORY: Nothing much."])
        self.assertIn("NOTHING TO CONDENSE", out)
        self.assertEqual(asked, [])
        self.play_round()
        out, asked, argv = self.ask("wren", "--memory", answers=["MEMORY: I looked about the harbor."])
        self.assertIn("REMEMBERED by Wren, rounds 1-1", out)
        condensing = [e for e in self.log_entries() if e["kind"] == "command" and e["command"] == "memory"
                      and e["args"][:1] == ["condense"] and not e["refused"]][-1]
        self.assertEqual(asked, [condensing["output"]])
        memory = [e for e in self.log_entries() if e["kind"] == "memory"][-1]
        self.assertEqual((memory["text"], memory["spend"]), ("I looked about the harbor.", 0.0012))

    def test_memory_keeps_recent_rounds_and_condenses_older_ones_in_their_own_words(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.settings_tool("preset", "simulation")  # 5 kept, condensed every 5
        self.rpg("newgame", seed=43)
        for _ in range(9):
            self.play_round()
        self.assertIn("NOTHING TO CONDENSE for Wren: 9 rounds", self.rpg("memory", "condense", "wren"))
        self.write("proposals/m.txt", "MEMORY: Nothing.")
        self.assertIn("no condensing is waiting", self.rpg("memory", "store", "wren", "proposals/m.txt", ok=False))
        self.play_round()
        brief = self.rpg("memory", "condense", "wren")
        self.assertIn("### Moment 1", brief)
        self.assertIn("Moment 5 for wren.", brief)
        self.assertNotIn("Moment 6 for wren.", brief)
        self.assertIn("MEMORY: <what you remember", brief)
        self.write("proposals/m.txt", "MEMORY: I spent those first nights looking around and learning nothing.")
        self.assertIn("rounds 1-5", self.rpg("memory", "store", "wren", "proposals/m.txt"))
        mem = self.save()["players"]["wren"]["memory"]
        self.assertEqual(sorted({e["round"] for e in mem["recent"]}), [6, 7, 8, 9, 10])
        self.assertEqual(mem["condensed"], [{"rounds": [1, 5], "kind": "condensed", "round": 10, "uses": 0,
                                             "text": "I spent those first nights looking around and learning nothing."}])
        self.assertEqual(sorted({e["round"] for e in self.save()["players"]["corin"]["memory"]["recent"]}), list(range(1, 11)))
        entries = [json.loads(line) for line in (self.dir / "state" / "log" / ("%s.jsonl" % self.save()["run"]["id"])).read_text().splitlines()]
        self.assertEqual([(e["rounds"], e["replaced"]) for e in entries if e["kind"] == "memory"], [([1, 5], 15)])  # did, why, happened: nothing changed
        self.assertEqual(len([e for e in entries if e["kind"] == "narration" and e["player"] == "wren"]), 10, "the log forgets nothing")

    def test_the_size_cap_condenses_early_and_each_stretch_is_remembered_apart(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.settings_tool("preset", "simulation")
        self.settings_tool("set", "memory.recent_rounds", "1")
        self.settings_tool("set", "memory.max_chars", "50")  # far under a round's memory, so it's due once 2 are held
        self.rpg("newgame", seed=43)
        self.play_round()
        self.assertIn("NOTHING TO CONDENSE", self.rpg("memory", "condense", "wren"))  # one round held, and one is kept
        for words in ("I looked about the harbor.", "I asked after the lighthouse."):
            self.play_round()
            self.assertIn("### Moment", self.rpg("memory", "condense", "wren"))
            self.write("proposals/m.txt", "MEMORY: %s" % words)
            self.rpg("memory", "store", "wren", "proposals/m.txt")
        self.assertEqual([c["rounds"] for c in self.save()["players"]["wren"]["memory"]["condensed"]], [[1, 1], [2, 2]])
        self.assertIn("## What you remember from before\nI looked about the harbor.\n\nI asked after the lighthouse.\n\n## Lately",
                      self.rpg("brief", "wren"))

    def thirteenth_round(self, hobb=()):
        """A round of The Thirteenth Stroke in which Hobb's turn runs the given commands (each a list of arguments)."""
        for pid in [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().split(", ")]:
            self.write("proposals/reply.txt", "DO: I look around.\nJOURNAL: Getting my bearings.\n")
            self.rpg("reply", pid, "proposals/reply.txt")
            for command in hobb if pid == "hobb" else ():
                self.rpg(*command, as_="hobb")
            self.write("proposals/story.txt", "You look around.")
            self.rpg("narrate", pid, "proposals/story.txt")
        self.rpg("round", "end")

    def test_a_moment_ends_with_what_changed_for_them_not_a_copy_of_how_things_stood(self):
        self.rpg("game", "switch", "thirteenth_stroke")
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=44)
        self.assertEqual(self.save()["players"]["hobb"]["snapshot"]["place"], "The Tock Tower")  # how he began
        self.thirteenth_round(hobb=[["move", "south"], ["coins", "-2", "gift"], ["hurt", "2"], ["gain", "iron_poker"],
                                    ["equip", "iron_poker"], ["lose", "tally_stick"]])
        self.thirteenth_round()  # nothing changes for him
        self.thirteenth_round(hobb=[["gain", "bent_umbrella"], ["equip", "bent_umbrella"]])
        brief = self.rpg("brief", "hobb")
        line = re.search(r"### Moment 1\n(?:.*\n)*?What changed: (.*)\n", brief).group(1)
        self.assertTrue(line.startswith("you went from The Tock Tower to The Lopsided Square; buttons 6 to 4; health 13 to 11; "
                                        "you got Iron Poker; you no longer had Tally Stick; you took Iron Poker in hand; you met "), line)
        self.assertIn("Pip Pumbleton", line)
        moment2 = brief.split("### Moment 2")[1].split("### Moment 3")[0]
        self.assertNotIn("What changed", moment2)  # nothing changed, so no line
        self.assertIn("What changed: you got Bent Umbrella; you took Bent Umbrella in hand; you put Iron Poker away.", brief)
        self.assertNotIn("How things stood after", brief)
        self.assertIn("## You\nHealth 11 of 13.", brief)  # how things stand now, in full as before
        for e in self.save()["players"]["hobb"]["memory"]["recent"]:
            self.assertNotEqual(e["kind"], "status")

    def test_a_moment_kept_with_a_copy_of_how_things_stood_is_still_shown_with_it(self):
        self.rpg("game", "switch", "thirteenth_stroke")
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=44)
        self.thirteenth_round()
        s = self.save()
        s["players"]["hobb"]["memory"]["recent"].append({"round": 1, "kind": "status", "text": "## You\nMoney: 6 buttons.", "uses": 0})
        del s["players"]["hobb"]["snapshot"]  # a save from before: nothing to compare with, so no line
        self.write("state/save.json", json.dumps(s))
        self.assertIn("How things stood after:\n  You:\n    Money: 6 buttons.", self.rpg("brief", "hobb"))
        self.thirteenth_round(hobb=[["move", "south"]])
        self.assertNotIn("What changed", self.rpg("brief", "hobb"))
        self.thirteenth_round(hobb=[["move", "north"]])
        self.assertIn("What changed: you went from The Lopsided Square to The Tock Tower.", self.rpg("brief", "hobb"))

    def test_what_they_learn_is_theirs_to_keep_up_at_each_think_back(self):
        self.rpg("game", "switch", "thirteenth_stroke")
        self.settings_tool("preset", "simulation")
        for key, value in (("memory.recent_rounds", "1"), ("memory.condense_every", "1"), ("memory.learned_max", "2")):
            self.settings_tool("set", key, value)
        self.assertIn("the think-back sees the whole Who I am note, and keeps at most 2 things learned", self.rpg("settings"))
        self.rpg("newgame", seed=44)
        self.thirteenth_round()
        self.thirteenth_round()
        think = self.rpg("memory", "condense", "hobb")
        self.assertIn("## What you've learned so far\nNothing yet.\n", think)
        self.assertIn("at most 2 lines", think)
        self.write("proposals/m.txt", "MEMORY: I looked about.\nLEARNED: %s\nLEARNED:\n- Nell makes things to order.\n- A third thing." % ("a" * 300))
        self.assertIn("2 things learned (cut at the limit)", self.rpg("memory", "store", "hobb", "proposals/m.txt"))
        self.assertEqual(self.save()["players"]["hobb"]["learned"], ["a" * 240, "Nell makes things to order."])
        self.assertEqual(self.save()["players"]["hobb"]["memory"]["condensed"][-1]["text"], "I looked about.")
        self.thirteenth_round()
        self.assertIn("## What you've learned so far\n- %s\n- Nell makes things to order.\n" % ("a" * 240), self.rpg("memory", "condense", "hobb"))
        self.write("proposals/m.txt", "MEMORY: More looking about.")  # no LEARNED: lines: the list stands
        self.assertIn("what they've learned left as it was", self.rpg("memory", "store", "hobb", "proposals/m.txt"))
        self.assertEqual(self.save()["players"]["hobb"]["learned"], ["a" * 240, "Nell makes things to order."])
        self.thirteenth_round()
        self.rpg("memory", "condense", "hobb")
        self.write("proposals/m.txt", "LEARNED: Only this.")
        self.assertIn("no MEMORY", self.rpg("memory", "store", "hobb", "proposals/m.txt", ok=False))
        self.write("proposals/m.txt", "MEMORY: Ambrose told me plain.\nLEARNED: Ambrose builds sheds, for five buttons.")
        self.rpg("memory", "store", "hobb", "proposals/m.txt")  # rewritten whole: what they leave out is gone
        s = self.save()
        self.assertEqual(s["players"]["hobb"]["learned"], ["Ambrose builds sheds, for five buttons."])
        s["players"]["hobb"]["kept"] = [{"round": 4, "text": "The clock stopped."}]
        self.write("state/save.json", json.dumps(s))
        self.assertIn("## What I know\n- Ambrose builds sheds, for five buttons.\n- The clock stopped.\n\n## What everyone", self.rpg("brief", "hobb"))
        memories = [e for e in self.log_entries() if e["kind"] == "memory"]
        self.assertEqual([(e["learned_given"], len(e["learned"]), e["learned_cut"], e["sees"]) for e in memories],
                         [(True, 2, True, "who_i_am"), (False, 2, False, "who_i_am"), (True, 1, False, "who_i_am")])
        audit = self.run_py("tools/audit.py", "state/log/%s.jsonl" % s["run"]["id"]).stdout
        self.assertIn("learned, 2  <<< cut at the limit", audit)
        self.assertIn("learned, 2 (left as it was)", audit)
        self.assertIn("      - Ambrose builds sheds, for five buttons.", audit)

    DAYS_EVENTS = ("\n\n## At: gulls_quiet\nwhen: day 3, dusk\nif: not lamp_lit\nsets: gulls_quiet\n"
                   "seen: All along the harbor the gulls fall quiet at once.\nrumor: The gulls went quiet at dusk.\n"
                   "\n## At: fleet_home\nwhen: day 9, dusk\nsets: fleet_arrived\n"
                   "\n## At: fleet_lost\nwhen: day 9, dusk\nif: not lamp_lit\nsets: fleet_lost\n")

    def days_world(self, events=DAYS_EVENTS):
        """The Dark Lighthouse with days that go round, one time of day a round: its deadline clock taken out, and
        what the clock set set by timed events instead."""
        self.rpg("game", "switch", "dark_lighthouse")
        self.settings_tool("preset", "simulation")
        self.settings_tool("set", "rounds.time_every", "1")
        path = self.dir / "games" / "dark_lighthouse" / "world.md"
        text = re.sub(r"\nclock:\n(?:[ #].*\n)+", "\n", path.read_text()).replace("\ntimes:\n", "\ndays: yes\ntimes:\n", 1)
        path.write_text(text.rstrip("\n") + events)
        room = self.dir / "games" / "dark_lighthouse" / "rooms" / "harbor_square.md"
        room.write_text(room.read_text().rstrip("\n") + "\n\n## If after_day_1 and time_dusk\nThe gulls know you by now.\n")

    def test_in_a_world_with_days_the_times_go_round_and_the_days_are_counted(self):
        self.days_world()
        self.assertIn("CONTENT OK: dark_lighthouse", self.rpg("validate"))
        self.rpg("newgame", seed=43)
        self.assertIn("## Where you are\nHarbor Square, dusk on day 1", self.rpg("brief", "wren"))
        look = self.rpg("look", as_="wren")
        self.assertIn("TIME AND WEATHER: dusk on day 1", look)
        self.assertIn("time_dusk, day_1", look)
        self.assertNotIn("know you by now", look)
        for _ in range(4):
            self.play_round()
        look = self.rpg("look", as_="wren")
        self.assertIn("TIME AND WEATHER: dusk on day 2", look)
        self.assertIn("time_dusk, day_2, after_day_1", look)
        self.assertIn("The gulls know you by now.", look, "a room's text can follow the time and the day")
        self.play_round()
        self.assertIn("nightfall on day 2", self.rpg("pane", "wren"))
        self.assertNotIn("know you by now", self.rpg("look", as_="wren"))
        self.assertIn("## Now\nnightfall on day 2", self.rpg("world-brief", "turn", as_=False), "life off-screen keeps the hours")
        self.assertIn("names are automatic", self.rpg("flag", "set", "day_3", as_="wren", ok=False))
        self.assertIn("needs rounds.time_every of 1 or more", self.settings_tool("set", "rounds.time_every", "0", ok=False))

    def test_a_timed_event_happens_once_when_its_day_and_time_come_if_its_condition_holds(self):
        self.days_world()
        self.rpg("newgame", seed=43)
        for _ in range(7):
            self.play_round()
        self.assertNotIn("gulls_quiet", self.save()["flags"])
        _, end = self.play_round()  # the end of round 8 brings dusk on day 3
        self.assertIn("AT gulls_quiet (day 3, dusk): flag set: gulls_quiet;", end)
        self.assertIn("gulls_quiet", self.save()["flags"])
        for pid, pl in self.save()["players"].items():
            self.assertIn({"round": 8, "kind": "seen", "text": "All along the harbor the gulls fall quiet at once.", "uses": 0},
                          pl["memory"]["recent"], pid)
        self.assertIn("The gulls went quiet at dusk.", self.save()["run"]["rumors"])
        events = [e for e in self.log_entries() if e["kind"] == "event"]
        self.assertEqual([(e["id"], e["happened"], e["player"]) for e in events], [("gulls_quiet", True, None)])
        for _ in range(4):
            _, end = self.play_round()  # dusk on day 4: it never comes again
            self.assertNotIn("AT gulls_quiet", end)
        self.rpg("newgame", seed=43)  # again, with the lamp lit: the event's time comes, but it doesn't happen
        self.rpg("flag", "set", "lamp_lit", as_="wren")  # which wins the quest: its ending is told first
        self.write("proposals/ending.txt", "The lamp blazes out over the water.")
        self.rpg("ending", "proposals/ending.txt", as_=False)
        for _ in range(7):
            self.play_round()
        _, end = self.play_round()
        self.assertIn("AT gulls_quiet (day 3, dusk): not, since not lamp_lit doesn't hold; nothing happens", end)
        self.assertNotIn("gulls_quiet", self.save()["flags"])

    def test_validate_holds_days_and_timed_events_to_their_shape(self):
        self.days_world(events="\n\n## At: early\nwhen: day 1, dusk\nseen: x\n\n## At: odd\nwhen: day 2, noon\nsets: lamp_quest_started\n"
                               "colour: blue\n\n## At: Bad Name\nwhen: day 2, dusk\n\n## At: dawn\nwhen: tomorrow\nrumor: y\n")
        room = self.dir / "games" / "dark_lighthouse" / "rooms" / "harbor_square.md"
        room.write_text(room.read_text() + "\n## If time_noon or day_0\nNoon.\n")
        out = self.rpg("validate", "--game", "dark_lighthouse", ok=False)
        for expected in ("day 1, dusk is when the run begins", "the time one of times: (dusk, nightfall, deep night, the small hours)",
                         "'colour: blue' isn't one of when:", "sets: 'lamp_quest_started' must be a shared flag name",
                         "the heading is `## At: <id>`", "needs `when: day <n>, <a time of day>`",
                         "condition 'time_noon': no time of day like that", "condition 'day_0': a day is a number from 1",
                         "a condition uses 'fleet_arrived', but nothing in the game sets it"):
            self.assertIn(expected, out)
        path = self.dir / "games" / "dark_lighthouse" / "world.md"
        path.write_text(path.read_text().replace("days: yes", "days: no"))
        out = self.rpg("validate", "--game", "dark_lighthouse", ok=False)
        self.assertIn("`## At:` sections need `days: yes`", out)
        self.assertIn("condition 'day_0': days are counted only in a world with `days: yes`", out)
        self.rpg("game", "switch", "thirteenth_stroke")
        path = self.dir / "games" / "thirteenth_stroke" / "world.md"
        path.write_text(path.read_text().replace("\ntimes:\n", "\ndays: yes\ntimes:\n", 1))
        self.assertIn("days: yes can't go with a clock:", self.rpg("validate", "--game", "thirteenth_stroke", ok=False))

    def needs_world(self):
        """The days world with needs: food (the honey cake) and sleep at the small hours, beds at the Gull, the
        harbor square rough."""
        self.days_world()
        games = self.dir / "games" / "dark_lighthouse"
        world = games / "world.md"
        world.write_text(world.read_text().replace("days: yes\n", "days: yes\nneeds: food, sleep\nsleep_at: the small hours\n", 1))
        for path, line in ((games / "rooms" / "gull_tavern.md", "sleep: bed"), (games / "rooms" / "harbor_square.md", "sleep: rough"),
                           (games / "items" / "honey_cake.md", "food: yes")):
            path.write_text(path.read_text().replace("---\n", "---\n%s\n" % line, 1))

    def round_doing(self, doing=None):
        """A round in which each person named runs the given commands (each a list of arguments) on their turn."""
        for pid in [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().splitlines()[0].split(", ")]:
            self.write("proposals/reply.txt", "DO: I look around.\nJOURNAL: Getting my bearings.\n")
            self.rpg("reply", pid, "proposals/reply.txt")
            for command in (doing or {}).get(pid, ()):
                self.rpg(*command, as_=pid)
            self.write("proposals/story.txt", "You look around.")
            self.rpg("narrate", pid, "proposals/story.txt")
        return self.rpg("round", "end")

    def test_hunger_comes_with_each_day_unfed_and_eating_ends_it(self):
        self.needs_world()
        self.assertIn("CONTENT OK: dark_lighthouse", self.rpg("validate"))
        self.rpg("newgame", seed=43)
        pane = self.rpg("pane", "corin")
        self.assertIn("## What you're working on\nWhat you need: You haven't eaten yet today. You slept well last night.", pane)
        for _ in range(3):
            self.round_doing()
        end = self.round_doing()  # the small hours give way to dusk on day 2: a day gone by unfed, a night unslept
        self.assertIn("NEED: Corin (corin) is hungry now", end)
        self.assertIn("NEED: Corin (corin) is tired now", end)
        self.assertIn("What you need: You're hungry: you went all yesterday without food. You're tired: you didn't sleep properly "
                      "last night.", self.rpg("pane", "corin"))
        self.assertIn("vs DC 10: d20 ", self.rpg("check", "wits", "10", as_="corin"))
        self.assertIn(" +1 = ", self.rpg("check", "wits", "10", as_="corin"), "Wits 2, less 1 for being tired")
        for _ in range(4):
            end = self.round_doing()
        self.assertIn("NEED: Corin (corin) is weak now", end)
        self.assertIn("NEED: Corin (corin) is exhausted now", end)
        pane = self.rpg("pane", "corin")
        self.assertIn("You're weak with hunger: it's days since you ate. You're worn out: night after night without sleep.", pane)
        self.assertIn(" -1, ", pane.split("## You\n")[1].split("\n")[0], "weak: Might shown one less")
        self.assertIn(" -3 = ", self.rpg("check", "might", "10", as_="corin"), "Might 0, weak -1, worn out -2")
        self.assertIn("NEEDS: food: weak; sleep: exhausted", self.rpg("look", as_="corin"))
        self.rpg("gain", "honey_cake", as_="corin")
        self.assertIn("FOOD CARRIED: honey_cake", self.rpg("look", as_="corin"))
        self.assertIn("isn't food", self.rpg("eat", "healing_tonic", as_="corin", ok=False))
        self.assertIn("ATE: Honey Cake.", self.rpg("eat", "honey_cake", as_="corin"))
        self.assertNotIn("honey_cake", self.save()["players"]["corin"]["inventory"])
        self.assertIn("What you need: You've eaten today.", self.rpg("pane", "corin"))
        self.assertIn(" -2 = ", self.rpg("check", "might", "10", as_="corin"), "fed: only worn out now")
        needs = [(e["player"], e["need"], e.get("now") or e.get("met")) for e in self.log_entries() if e["kind"] == "need"]
        self.assertIn(("corin", "food", "honey_cake"), needs)
        self.assertIn("corin food: met (honey_cake, by eat)", self.run_py("tools/audit.py", "state/log/%s.jsonl" % self.save()["run"]["id"]).stdout)

    def test_sleep_is_chosen_at_its_time_in_a_bed_or_rough_and_a_rough_night_spares_the_worst(self):
        self.needs_world()
        self.rpg("newgame", seed=43)
        self.rpg("move", "east", as_="wren")  # the coast road: nowhere to sleep
        self.assertIn("isn't time for bed (that's deep night or the small hours); it's dusk", self.rpg("sleep", as_="corin", ok=False))
        for _ in range(3):
            self.round_doing()
        self.assertIn("IT'S THE TIME FOR SLEEP", self.rpg("look", as_="corin"))
        self.assertIn("nowhere to sleep here", self.rpg("sleep", as_="wren", ok=False))
        self.rpg("move", "west", as_="wren")
        self.assertIn("It's the time for sleep, if you mean to.", self.rpg("pane", "corin"))
        end = self.round_doing({"corin": [["sleep"]], "wren": [["sleep"]]})  # Corin in a bed at the Gull, Wren rough in the square
        self.assertIn("NEED: Wren (wren) is tired now", end)
        self.assertNotIn("Corin (corin) is tired", end, "a night in a bed: rested")
        self.assertEqual([self.save()["players"][p]["needs"]["sleep"] for p in ("corin", "wren")], ["rested", "tired"])
        for _ in range(3):
            self.round_doing()
        self.round_doing({"wren": [["sleep"]]})  # rough again; Corin sits up all night
        self.assertEqual([self.save()["players"][p]["needs"]["sleep"] for p in ("corin", "wren")], ["tired", "tired"])
        for _ in range(3):
            self.round_doing()
        self.round_doing()  # a second night without sleep for Corin; Wren's first
        self.assertEqual([self.save()["players"][p]["needs"]["sleep"] for p in ("corin", "wren")], ["exhausted", "tired"])
        self.assertIn("You're worn out: night after night without sleep.", self.rpg("pane", "corin"))
        for _ in range(3):
            self.round_doing()
        self.round_doing({"corin": [["sleep"]]})
        self.assertEqual(self.save()["players"]["corin"]["needs"]["sleep"], "rested", "a night in a bed puts it right")

    def test_to_bed_early_they_sleep_through_the_night_unasked_seeing_and_hearing_nothing(self):
        self.needs_world()
        self.three_players()  # Wren and Tam in Harbor Square (rough), Corin at the Gull (a bed)
        self.rpg("newgame", seed=43)
        self.round_doing()  # dusk
        self.assertIn("isn't time for bed (that's deep night or the small hours); it's nightfall", self.rpg("sleep", as_="corin", ok=False))
        self.round_doing()  # nightfall
        self.round_doing({"corin": [["sleep"]], "wren": [["sleep"]]})  # deep night: the time before the time for sleep
        players = self.save()["players"]
        self.assertTrue(players["corin"].get("asleep") and players["wren"].get("asleep"), "deep night, the time before the small hours")
        start = self.rpg("round", "start")  # the small hours: they sleep through it
        self.assertEqual(start.splitlines()[0], "ROUND 4: Tam (tam)")
        self.assertIn("ASLEEP (they sleep through this round, not asked): ", start.splitlines()[1])
        self.assertIn("Wren (wren)", start.splitlines()[1])
        self.assertIn("Wren (wren, ", self.rpg("look", as_="tam"))
        self.assertIn("ASLEEP: sees and hears nothing till morning", self.rpg("look", as_="tam"))
        self.write("proposals/reply.txt", "DO: I call out to Wren.\nJOURNAL: Company.\n")
        self.rpg("reply", "tam", "proposals/reply.txt")
        self.write("proposals/words.txt", "Wren?")
        self.assertIn("NOT KEPT: no one else of the cast here is awake", self.rpg("say", "proposals/words.txt", as_="tam"))
        self.write("proposals/note.txt", "Tam called out across the square.")
        self.assertIn("NOT KEPT: no one else was there to see it", self.rpg("witnessed", "proposals/note.txt", as_="tam"))
        self.write("proposals/story.txt", "You call out.")
        self.rpg("narrate", "tam", "proposals/story.txt")
        self.rpg("round", "end")  # the night gone by, without them
        players = self.save()["players"]
        self.assertEqual([players[p]["needs"]["sleep"] for p in ("corin", "wren", "tam")], ["rested", "tired", "tired"])
        self.assertEqual([players[p]["needs"]["sleepless"] for p in ("corin", "wren", "tam")], [0, 0, 1], "Wren slept, rough; Tam didn't")
        self.assertFalse(any(pl.get("asleep") for pl in players.values()), "the night gone by, they're awake")
        self.assertNotIn("Wren?", self.rpg("brief", "wren"))
        self.assertEqual(sorted((e["round"], e["player"]) for e in self.log_entries() if e["kind"] == "asleep"), [(4, "corin"), (4, "wren")])
        self.assertIn("Wren (wren)", self.rpg("round", "start").splitlines()[0], "morning: asked again")
        out = self.run_py("tools/audit.py", "state/log/%s.jsonl" % self.save()["run"]["id"]).stdout
        self.assertIn("r4 wren asleep through the round, in harbor_square", out)

    def test_content_can_meet_a_need_and_validate_holds_needs_to_what_meets_them(self):
        self.needs_world()
        self.rpg("newgame", seed=43)
        self.assertIn("MET: food (content)", self.rpg("meet", "food", as_="wren"))
        self.assertEqual(self.save()["players"]["wren"]["needs"]["ate"], True)
        self.assertIn("isn't time for bed", self.rpg("meet", "sleep", as_="wren", ok=False))
        self.assertIn("NEEDS: on (food, sleep); wants shown", self.rpg("settings"))
        self.settings_tool("set", "needs.on", "false")
        self.assertIn("nobody here needs to eat", self.rpg("eat", "honey_cake", as_="corin", ok=False))
        self.assertNotIn("What you need", self.rpg("pane", "corin"))
        self.assertNotIn("NEEDS:", self.rpg("look", as_="corin"))
        self.settings_tool("set", "needs.on", "true")
        games = self.dir / "games" / "dark_lighthouse"
        world = games / "world.md"
        world.write_text(world.read_text().replace("needs: food, sleep\nsleep_at: the small hours\n", "needs: food, sleep, warmth\n"))
        for path, old, new in ((games / "rooms" / "gull_tavern.md", "sleep: bed", "sleep: soft"), (games / "rooms" / "harbor_square.md", "sleep: rough\n", ""),
                               (games / "items" / "honey_cake.md", "food: yes", "food: maybe")):
            path.write_text(path.read_text().replace(old, new))
        room = games / "rooms" / "coast_road.md"
        room.write_text(room.read_text() + "\nA bench here (`meet sleep soft`).\n")
        out = self.rpg("validate", "--game", "dark_lighthouse", ok=False)
        for expected in ("needs: 'warmth' isn't a need the kit knows", "rooms/gull_tavern.md: sleep: must be bed or rough",
                         "items/honey_cake.md: food: must be yes or no", "needs `sleep_at:`, one of its times of day",
                         "no item is `food: yes`, and nothing says `meet food`", "use meet food, or meet sleep [bed|rough]"):
            self.assertIn(expected, out)
        world.write_text(world.read_text().replace("days: yes", "days: no"))
        self.assertIn("needs: need `days: yes`", self.rpg("validate", "--game", "dark_lighthouse", ok=False))

    def selling_world(self, coins=10, paid_beds=None):
        """The needs world with Pell selling at the Gull (honey cake 1, one smoked fish for 2), a bed there for 2 a
        night, and the Gull to let from Pell (3 for 2 days); everyone with `coins` to spend."""
        self.needs_world()
        games = self.dir / "games" / "dark_lighthouse"
        pell = games / "characters" / "pell.md"
        pell.write_text(pell.read_text().replace("---\n", "---\nsells:\n  honey_cake: 1\n  smoked_fish: 2, 1 in stock\n", 1)
                        .replace("minor: yes", "minor: no"))  # his own agent here, so his brief can be read
        gull = games / "rooms" / "gull_tavern.md"
        gull.write_text(gull.read_text().replace("sleep: bed\n", "sleep: bed\nbed_price: 2\nrent: 3 for 2 days\nlandlord: pell\n", 1))
        if paid_beds:
            cast = games / "cast.json"
            entries = json.loads(cast.read_text())
            entries[0]["paid_beds"] = paid_beds
            cast.write_text(json.dumps(entries))
        self.rpg("newgame", seed=43)
        s = self.save()
        for pl in s["players"].values():
            pl["stats"]["coins"] = coins
        self.write("state/save.json", json.dumps(s))

    def test_a_seller_sells_at_their_price_while_they_have_any(self):
        self.selling_world()
        self.assertIn("CONTENT OK: dark_lighthouse", self.rpg("validate"))
        look = self.rpg("look", as_="corin")
        self.assertIn("SELLERS HERE: Pell (pell): honey_cake 1, smoked_fish 2, 1 left.", look)
        self.assertIn("LETS HERE: The Gull (gull_tavern), 3 coins for 2 days, from pell: free.", look)
        brief = self.rpg("npc-brief", "pell", as_="corin")
        self.assertIn("## What you sell, at these prices and no other\n- Honey Cake: 1 coins\n- Smoked Fish: 2 coins (1 left)", brief)
        self.assertIn("## What you let, on these terms and no other\n- The Gull: 3 coins for 2 days, free to let", brief)
        self.assertNotIn("coins", self.rpg("pane", "corin").split("## You\n")[1].split("Carrying")[0].replace("Money: 10 coins.", ""),
                         "no price in anyone's pane")
        self.assertIn("BOUGHT: Honey Cake from Pell for 1 coins. COINS -1 -> 9", self.rpg("buy", "honey_cake", as_="corin"))
        self.assertIn("COINS -2 -> 7; 0 left", self.rpg("buy", "smoked_fish", as_="corin"))
        self.assertIn("Pell has no Smoked Fish left", self.rpg("buy", "smoked_fish", as_="corin", ok=False))
        self.assertIn("nobody here sells brass_lens", self.rpg("buy", "brass_lens", as_="corin", ok=False))
        self.assertIn("nobody here sells honey_cake", self.rpg("buy", "honey_cake", as_="wren", ok=False), "Pell is at the Gull")
        self.assertEqual(self.save()["players"]["corin"]["inventory"].count("honey_cake"), 1)
        self.rpg("buy", "honey_cake", as_="corin")
        self.assertEqual(self.save()["players"]["corin"]["inventory"].count("honey_cake"), 2, "two of a thing")
        s = self.save()
        s["players"]["corin"]["stats"]["coins"] = 0
        self.write("state/save.json", json.dumps(s))
        self.assertIn("Honey Cake costs 1 coins, and they have 0", self.rpg("buy", "honey_cake", as_="corin", ok=False))
        self.assertIn("(none left)", self.rpg("npc-brief", "pell", as_="corin"))
        entries = self.log_entries()
        self.assertEqual([(e["item"], e["price"], e["left"]) for e in entries if e["kind"] == "purchase"],
                         [("honey_cake", 1, None), ("smoked_fish", 2, 0), ("honey_cake", 1, None)])
        self.assertEqual({e["reason"] for e in entries if e["kind"] == "coins"}, {"purchase"})
        audit = self.run_py("tools/audit.py", "state/log/%s.jsonl" % s["run"]["id"]).stdout
        self.assertIn("corin bought smoked_fish from pell for 2 (0 left)", audit)
        s["players"]["corin"]["stats"]["coins"] = 6
        self.write("state/save.json", json.dumps(s))
        self.assertIn("to the end of day 2", self.rpg("rent", "gull_tavern", as_="corin"))
        self.assertIn("to the end of day 4", self.rpg("rent", "gull_tavern", as_="corin"), "paid again, it runs on from where it ends")
        self.assertIn("corin renewed gull_tavern to the end of day 4, for 3", self.run_py("tools/audit.py", "state/log/%s.jsonl" % s["run"]["id"]).stdout)

    def test_a_bed_is_paid_for_at_bedtime_and_a_place_let_is_its_tenants_till_its_days_run_out(self):
        self.selling_world(coins=4, paid_beds=[{"room": "gull_tavern", "nights": 1}])  # Wren has tonight paid for at the Gull
        self.assertIn("A bed is paid for at The Gull, for tonight.", self.rpg("pane", "wren"))
        self.assertIn("landlord (pell) isn't here", self.rpg("rent", "gull_tavern", as_="wren", ok=False))
        self.assertIn("RENTED: The Gull, Corin's to the end of day 2, from Pell for 3 coins. COINS -3 -> 1", self.rpg("rent", "gull_tavern", as_="corin"))
        self.assertIn("Your own places: The Gull (yours to the end of day 2)", self.rpg("pane", "corin"))
        self.rpg("move", "north", as_="wren")
        self.assertIn("let to someone else until the end of day 2", self.rpg("rent", "gull_tavern", as_="wren", ok=False))
        self.rpg("drop", "healing_tonic", as_="corin")
        self.assertIn("refused", self.rpg("take", "healing_tonic", as_="wren", ok=False).lower(), "what the tenant leaves stays theirs")
        for _ in range(3):
            self.round_doing()
        self.round_doing({"corin": [["sleep"]], "wren": [["sleep"]]})  # the small hours: his own bed, and her night paid ahead
        self.assertEqual([self.save()["players"][p]["stats"]["coins"] for p in ("corin", "wren")], [1, 4], "neither paid tonight")
        self.assertEqual(self.save()["players"]["wren"]["paid_beds"], {"gull_tavern": 0})
        self.assertNotIn("A bed is paid for", self.rpg("pane", "wren"))
        for _ in range(3):
            self.round_doing()
        self.round_doing({"wren": [["sleep"]]})  # the second night: she pays for her bed
        self.assertEqual(self.save()["players"]["wren"]["stats"]["coins"], 2)
        self.assertIn("COINS -2", [e for e in self.log_entries() if e["kind"] == "command" and e["command"] == "sleep"][-1]["output"])
        self.assertIn("LET ENDS: The Gull is no longer Corin's", "\n".join([e for e in self.log_entries() if e["kind"] == "round"][-1]["events"]))
        corin = self.save()["players"]["corin"]
        self.assertIn("Your time at The Gull has run out: it isn't yours any more.", [m["text"] for m in corin["memory"]["recent"]])
        self.assertNotIn("yours to the end of day", self.rpg("pane", "corin"))
        s = self.save()
        s["players"]["wren"]["stats"]["coins"] = 1
        self.write("state/save.json", json.dumps(s))
        for _ in range(3):
            self.round_doing()
        order = [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().split(", ")]
        for pid in order:
            self.write("proposals/reply.txt", "DO: I go to bed.\nJOURNAL: Tired.\n")
            self.rpg("reply", pid, "proposals/reply.txt")
            if pid == "wren":
                self.assertIn("a bed here is 2 coins a night, and they have 1", self.rpg("sleep", as_="wren", ok=False))
            self.write("proposals/story.txt", "You look around.")
            self.rpg("narrate", pid, "proposals/story.txt")
        self.rpg("round", "end")

    def test_the_referee_records_what_each_turn_came_to_and_the_audit_counts_it_with_every_mechanic(self):
        self.rpg("newgame", seed=45)
        self.assertIn("no one's turn now", self.rpg("outcome", "done", as_="corin", ok=False))
        order = [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().split(", ")]
        first, second = order[0], order[1]
        self.write("proposals/reply.txt", "DO: I ask the fisherman for a boat.\nJOURNAL: To get across.\n")
        self.rpg("reply", first, "proposals/reply.txt")
        self.assertIn("it's %s's turn" % first, self.rpg("outcome", "done", as_=second, ok=False))
        self.assertIn("outcome done|partly|failed|refused|out_of_reach|not_there", self.rpg("outcome", "maybe", as_=first, ok=False))
        self.assertIn("say what was reached for", self.rpg("outcome", "not_there", as_=first, ok=False))
        self.rpg("outcome", "done", as_=first)
        self.assertIn("OUTCOME for", self.rpg("outcome", "not_there", "a", "boat", "for", "hire", as_=first))
        self.rpg("move", "south", as_=first)
        self.write("proposals/story.txt", "Nobody here hires boats.")
        self.assertNotIn("No outcome was recorded", self.rpg("narrate", first, "proposals/story.txt"))
        self.write("proposals/reply.txt", "DO: I look about.\nJOURNAL: Getting my bearings.\n")
        self.rpg("reply", second, "proposals/reply.txt")
        self.write("proposals/story.txt", "You look about.")
        self.assertIn("No outcome was recorded for this turn", self.rpg("narrate", second, "proposals/story.txt"))
        self.rpg("round", "end")
        self.assertEqual([(e["player"], e["result"], e["what"]) for e in self.log_entries() if e["kind"] == "outcome"],
                         [(first, "done", None), (first, "not_there", "a boat for hire")])
        audit = self.run_py("tools/audit.py", "state/log/%s.jsonl" % self.save()["run"]["id"]).stdout
        self.assertIn("== HEADLINE\n  rounds 1, ", audit)
        self.assertIn("never used: a check written in content; ", audit)
        self.assertRegex(audit, r"\n  moving +1\n")
        self.assertRegex(audit, r"\n  a turn's outcome: reached for something that isn't there +1\n")
        self.assertRegex(audit, r"\n  a turn's outcome: done +never\n", "the last word in a turn stands")
        self.assertIn("  %s: not_there 1\n  r1 %s not_there: a boat for hire\n  NO OUTCOME RECORDED: r1 %s" % (first, first, second), audit)
        sys.path.insert(0, str(ROOT / "tools"))
        import audit as audit_module
        names = [name for name, _ in audit_module.coverage([])]
        self.assertEqual(len(names), len(set(names)), "each mechanic counted once")

    def test_a_place_to_let_with_no_bed_price_is_only_its_tenants_to_sleep_in(self):
        self.selling_world(coins=6)
        gull = self.dir / "games" / "dark_lighthouse" / "rooms" / "gull_tavern.md"
        gull.write_text(gull.read_text().replace("bed_price: 2\n", ""))
        self.rpg("move", "north", as_="wren")  # to the Gull, beside Corin and Pell
        for _ in range(3):
            self.round_doing()
        order = [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().split(", ")]
        for pid in order:  # the small hours, both at the Gull
            self.write("proposals/reply.txt", "DO: I go to bed.\nJOURNAL: Tired.\n")
            self.rpg("reply", pid, "proposals/reply.txt")
            if pid == "wren":
                self.assertIn("isn't theirs to sleep in: it's to let", self.rpg("sleep", as_="wren", ok=False), "not yet let to anyone")
                self.rpg("rent", "gull_tavern", as_="wren")
                self.assertIn("SLEPT: The Gull, in a bed (their own, while the let lasts)", self.rpg("sleep", as_="wren"))
            else:
                self.assertIn("isn't theirs to sleep in: it's to let", self.rpg("sleep", as_="corin", ok=False))
            self.write("proposals/story.txt", "You look around.")
            self.rpg("narrate", pid, "proposals/story.txt")
        self.rpg("round", "end")
        self.assertEqual([self.save()["players"][p]["stats"]["coins"] for p in ("corin", "wren")], [6, 3], "nobody slept free but the tenant")

    def test_validate_holds_sellers_beds_and_lets_to_their_shape(self):
        self.needs_world()
        games = self.dir / "games" / "dark_lighthouse"
        pell = games / "characters" / "pell.md"
        pell.write_text(pell.read_text().replace("---\n", "---\nsells:\n  kipper: 1\n  honey_cake: cheap\n", 1))
        square = games / "rooms" / "harbor_square.md"
        square.write_text(square.read_text().replace("sleep: rough\n", "sleep: rough\nbed_price: 2\nrent: 3 a week\nlandlord: nobody\n", 1))
        coast = games / "rooms" / "coast_road.md"
        coast.write_text(coast.read_text() + "\nA sign (`rent coast_road`).\n")
        cast = games / "cast.json"
        entries = json.loads(cast.read_text())
        entries[0]["paid_beds"] = [{"room": "coast_road", "nights": 0}]
        cast.write_text(json.dumps(entries))
        out = self.rpg("validate", "--game", "dark_lighthouse", ok=False)
        for expected in ("characters/pell.md: sells: no item 'kipper'", 'sells: honey_cake: a price, or "<price>, <n> in stock"',
                         "rooms/harbor_square.md: bed_price: a whole number, in a room with sleep: bed",
                         'rooms/harbor_square.md: rent: "<price> for <n> days", with a landlord:',
                         "paid_beds: each is", "no place to let called 'coast_road'"):
            self.assertIn(expected, out)

    def projects_world(self):
        """The needs world with shared work: mending the nets in the harbor square (no check, a meal for it, over if the
        nets burn), and sweeping the Gull's hall (a check too hard to pass)."""
        self.needs_world()
        rooms = self.dir / "games" / "dark_lighthouse" / "rooms"
        square = rooms / "harbor_square.md"
        square.write_text(square.read_text().replace("---\n", "---\nproject:\n  id: nets\n  name: mending the nets\n"
                                                     "  stages: 2: nets_half; 4: nets_mended\n  until: not nets_burned\n  meal: yes\n", 1)
                          + "\nIf the nets catch fire (`flag set nets_burned`), there's no mending them.\n")
        gull = rooms / "gull_tavern.md"
        gull.write_text(gull.read_text().replace("---\n", "---\nproject:\n  id: hall\n  stages: 1: hall_swept\n  stat: wits\n  dc: 30\n", 1))
        self.rpg("newgame", seed=43)

    def test_shared_work_counts_each_turn_of_effort_and_its_stages_set_their_flags(self):
        self.projects_world()
        self.assertIn("CONTENT OK: dark_lighthouse", self.rpg("validate"))
        self.assertIn("SHARED WORK HERE: mending the nets (nets): 0 done; Wren has given it 0 turns", self.rpg("look", as_="wren"))
        out = self.round_doing({"wren": [["work"]]})
        work = [e for e in self.log_entries() if e["kind"] == "command" and e["command"] == "work"][-1]["output"]
        self.assertIn("EFFORT on mending the nets: Wren has given it 1 turn; 1 done in all", work)
        self.assertIn("FED: the work there comes with a meal", work)
        self.assertNotIn("WORK ", work.split("EFFORT")[0], "no check: every turn moves it on")
        self.assertTrue(self.save()["players"]["wren"]["needs"]["ate"])
        self.assertIn("ROUND 1 ENDS", out)
        order = [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().split(", ")]
        for pid in order:
            self.write("proposals/reply.txt", "DO: I mend nets.\nJOURNAL: For the town.\n")
            self.rpg("reply", pid, "proposals/reply.txt")
            if pid == "wren":
                self.assertIn("STAGE: mending the nets has come to 2: flag set: nets_half", self.rpg("work", as_="wren"))
                self.assertIn("already worked here this turn", self.rpg("work", as_="wren", ok=False))
            self.write("proposals/story.txt", "You mend.")
            self.rpg("narrate", pid, "proposals/story.txt")
        self.rpg("round", "end")
        self.assertIn("nets_half", self.save()["flags"])
        self.assertIn("most_nets", self.rpg("look", as_="wren"))
        self.assertNotIn("most_nets", self.rpg("look", as_="corin"))
        self.rpg("move", "south", as_="corin")
        for _ in range(2):
            self.round_doing({"wren": [["work"]], "corin": [["work"]]})
        self.assertIn("nets_mended", self.save()["flags"])
        self.round_doing({"corin": [["work"]]})
        self.round_doing({"corin": [["work"]]})  # Corin has caught up: four turns each
        self.assertIn("most_nets", self.rpg("look", as_="wren"))
        self.assertIn("most_nets", self.rpg("look", as_="corin"), "a tie: both of them")
        self.assertIn("PROJECT nets (mending the nets, at Harbor Square): 8 done; stages 2 nets_half (reached), 4 nets_mended "
                      "(reached); Wren 4; Corin 4", self.rpg("project", "nets"))
        self.rpg("flag", "set", "nets_burned", as_="wren")
        self.assertIn("mending the nets is over", self.rpg("work", as_="wren", ok=False))
        self.assertEqual([e["stage"] for e in self.log_entries() if e["kind"] == "project"], ["nets_half", "nets_mended"])
        audit = self.run_py("tools/audit.py", "state/log/%s.jsonl" % self.save()["run"]["id"]).stdout
        self.assertIn("nets corin: 4 turns, 4 moved it on, 0 paid", audit)

    def test_a_check_on_shared_work_moves_it_on_only_on_success_but_every_try_is_effort_and_paid_work_pays_each_turn(self):
        self.projects_world()
        self.round_doing({"corin": [["work"]]})
        work = [e for e in self.log_entries() if e["kind"] == "command" and e["command"] == "work"][-1]["output"]
        self.assertIn("WORK wits vs DC 30", work)
        self.assertIn("-> FAILURE", work)
        self.assertIn("0 done in all (this one moved nothing on, but it counts as their effort)", work)
        self.assertNotIn("NOT PAID", work, "there's no pay here to miss")
        gull = self.dir / "games" / "dark_lighthouse" / "rooms" / "gull_tavern.md"
        gull.write_text(gull.read_text().replace("project:\n", "work:\n  stat: wits\n  pay: 1\n  dc: 1\nproject:\n", 1))
        coins = self.save()["players"]["corin"]["stats"]["coins"]
        for _ in range(2):
            self.round_doing({"corin": [["work"]]})  # paid work on shared work: every turn, with its own check
        self.assertEqual(self.save()["players"]["corin"]["stats"]["coins"], coins + 2)
        self.assertEqual(self.save()["run"]["projects"]["hall"], {"total": 2, "by": {"corin": 3}, "stages": ["hall_swept"]})

    def test_paid_work_is_there_only_while_its_condition_holds(self):
        self.needs_world()
        gull = self.dir / "games" / "dark_lighthouse" / "rooms" / "gull_tavern.md"
        gull.write_text(gull.read_text().replace("---\n", "---\nwork:\n  stat: wits\n  pay: 1\n  dc: 1\n  if: cellar_flooded\n", 1)
                        + "\nIf the cellar floods (`flag set cellar_flooded`), the landlord pays for bailing.\n")
        self.assertIn("CONTENT OK: dark_lighthouse", self.rpg("validate"))
        self.rpg("newgame", seed=43)
        self.assertNotIn("WORK HERE", self.rpg("look", as_="corin"))
        self.assertIn("there's no paid work here", self.rpg("work", as_="corin", ok=False))
        self.rpg("flag", "set", "cellar_flooded", as_="corin")
        self.assertIn("WORK HERE: ", self.rpg("look", as_="corin"))
        coins = self.save()["players"]["corin"]["stats"]["coins"]
        self.round_doing({"corin": [["work"]]})
        self.assertEqual(self.save()["players"]["corin"]["stats"]["coins"], coins + 1)
        self.rpg("flag", "unset", "cellar_flooded", as_="corin")
        self.assertNotIn("WORK HERE", self.rpg("look", as_="corin"))
        gull.write_text(gull.read_text().replace("if: cellar_flooded", "if: cellar_drained"))
        self.assertIn("a condition uses 'cellar_drained', but nothing in the game sets it", self.rpg("validate", ok=False))

    def test_the_world_turn_is_told_what_is_settled_once_it_has_left_the_story_so_far(self):
        self.rpg("game", "switch", "wendleford")
        self.rpg("newgame", seed=44)
        brief = self.rpg("world-brief", "turn", as_=False)
        self.assertNotIn("## What's settled", brief)
        self.assertIn("based only on the story so far,\npublic knowledge and what's settled", brief)
        self.rpg("flag", "set", "wage_box_found", as_="hester")
        self.write("proposals/ending.txt", "The reeve has her box back, and the reward is paid.")
        self.rpg("ending", "proposals/ending.txt", as_="hester")
        for i in range(7):
            self.rpg("chronicle", "Something else happened, %d." % i, as_=False)
        state = self.save()
        state["run"]["projects"] = {"bridge": {"total": 8, "by": {"hobb": 8}, "stages": ["bridge_half", "bridge_mended"]},
                                    "harvest": {"total": 4, "by": {"dilly": 4}, "stages": ["harvest_half"]}}
        self.write("state/save.json", json.dumps(state))
        brief = self.rpg("world-brief", "turn", as_=False)
        self.assertIn("## What's settled (never say otherwise)\n- The Reeve's Wage Box: The reeve has her box back, and the "
                      "reward is paid.\n- the new bridge: done\n", brief)
        self.assertNotIn("Dunn's harvest: done", brief, "half done isn't settled")
        self.assertNotIn("## What's settled", self.rpg("world-brief", "extra", as_="hester"), "only the world turn")

    def test_a_notice_board_takes_notices_from_people_and_the_world_turn_and_shows_them_there(self):
        self.rpg("game", "switch", "wendleford")
        self.rpg("newgame", seed=44)  # Dilly starts in the square, by the board; Hester at the smithy, which has none
        self.write("proposals/n.txt", "WANTED: a dry corner to sleep. Ask Dilly.")
        self.assertIn("there's no notice board here", self.rpg("post", "proposals/n.txt", as_="hester", ok=False))
        self.assertIn("PUT UP on the board at Market Square", self.rpg("post", "proposals/n.txt", as_="dilly"))
        self.assertIn('On the notice board: "WANTED: a dry corner to sleep. Ask Dilly." (put up on day 1).',
                      self.rpg("brief", "dilly"))
        self.assertNotIn("On the notice board", self.rpg("brief", "hester"), "read only at the board")
        for i in range(8):
            self.write("proposals/n.txt", "FOR SALE: a lantern, number %d." % i)
            self.rpg("post", "proposals/n.txt", as_="dilly")
        board = self.save()["run"]["boards"]["market_square"]
        self.assertEqual(len(board), 8, "the last eight kept")
        self.assertNotIn("dry corner", json.dumps(board))
        self.assertIn('NOTICE BOARD: 1. "FOR SALE: a lantern, number 7." (Dilly Quickstep)', self.rpg("look", as_="dilly"))
        wt = {"rumors": [], "moves": [], "notices": [{"room": "market_square", "text": "Lost: a grey hen. Bet Lamb."}]}
        self.assertIn("Never offer work, goods or rewards the town doesn't already have.", self.rpg("world-brief", "turn", as_=False))
        self.write("proposals/wt.json", json.dumps(dict(wt, notices=wt["notices"] * 2)))
        self.assertIn("at most one notice", self.rpg("world-turn", "proposals/wt.json", as_=False, ok=False))
        self.write("proposals/wt.json", json.dumps(dict(wt, notices=[{"room": "smithy", "text": "Lost: a hen."}])))
        self.assertIn("a notice goes on a board", self.rpg("world-turn", "proposals/wt.json", as_=False, ok=False))
        self.write("proposals/wt.json", json.dumps(wt))
        self.assertIn("notice put up at market_square: Lost: a grey hen. Bet Lamb.", self.rpg("world-turn", "proposals/wt.json", as_=False))
        look = self.rpg("look", as_="dilly")
        self.assertIn('1. "Lost: a grey hen. Bet Lamb." (put up off-screen)', look)
        self.assertIn("isn't theirs to take down", self.rpg("post", "take", "1", as_="dilly", ok=False))
        self.assertIn("TAKEN DOWN from the board: FOR SALE: a lantern, number 7.", self.rpg("post", "take", "2", as_="dilly"))
        self.assertEqual(len(self.save()["run"]["boards"]["market_square"]), 7)
        square = self.dir / "games" / "wendleford" / "rooms" / "market_square.md"
        square.write_text(square.read_text().replace("board: yes", "board: maybe"))
        self.assertIn("board: yes or no", self.rpg("validate", "--game", "wendleford", ok=False))

    def test_in_a_world_with_needs_nobody_goes_below_1_health_and_a_nights_sleep_mends(self):
        self.rpg("game", "switch", "wendleford")
        self.rpg("newgame", seed=44)
        out = self.rpg("hurt", "20", as_="hester")
        self.assertIn("HP 1/10 (knocked down: at the end of their strength, but not out)", out)
        self.assertEqual(self.save()["players"]["hester"]["status"], "playing")
        state = self.save()
        for pid in ("hobb", "hester", "dilly"):
            state["players"][pid]["stats"]["hp"] = 3
        self.write("state/save.json", json.dumps(state))
        for _ in range(3):
            self.round_doing()
        end = self.round_doing({"hobb": [["sleep"]], "hester": [["sleep"]]})  # the night: Hobb in the hayloft, Hester her loft
        self.assertIn("MENDED: Hobb Ashcombe (hobb) +1 health after a night sleeping rough -> 4 of 12", end)
        self.assertIn("MENDED: Hester Gimbal (hester) +2 health after a night in a bed -> 5 of 10", end)
        self.assertNotIn("MENDED: Dilly", end, "no sleep, no mending")
        self.assertNotIn("MENDED: Marigold", end, "already whole")
        self.assertEqual({p: self.save()["players"][p]["stats"]["hp"] for p in ("hobb", "hester", "dilly", "marigold")},
                         {"hobb": 4, "hester": 5, "dilly": 3, "marigold": 8})
        self.rpg("game", "switch", "dark_lighthouse")  # an adventure, without needs: defeat at 0 as ever
        self.rpg("newgame", seed=44)
        self.assertIn("PLAYER DEFEATED (HP 0)", self.rpg("hurt", "99"))

    def test_a_scuffle_knocks_the_one_who_comes_off_worse_but_never_below_1(self):
        self.rpg("game", "switch", "wendleford")
        self.rpg("newgame", seed=44)
        self.rpg("move", "east", as_="hester")  # from the smithy into the square, where Dilly is
        self.assertIn("isn't here", self.rpg("contest", "might", "hobb", "might", "--scuffle", as_="dilly", ok=False))
        self.assertIn("usage", self.rpg("contest", "might", "hester", "might", "--scuffle", "--take", "notebook", as_="dilly", ok=False))
        state = self.save()
        for pid in ("dilly", "hester"):
            state["players"][pid]["stats"]["hp"] = 1
        self.write("state/save.json", json.dumps(state))
        outs = [self.rpg("contest", "might", "hester", "agility", "--scuffle", as_="dilly") for _ in range(6)]
        for out in outs:
            self.assertRegex(out, r"SCUFFLE: Dilly Quickstep might d20 \d+ [+-]\d+ = -?\d+; Hester Gimbal agility d20 ")
            self.assertTrue("takes a knock of" in out or "a tie, nobody hurt" in out, out)
        self.assertTrue(any("not out" in o for o in outs), "a knock at 1 health holds them at 1")
        self.assertEqual([self.save()["players"][p]["stats"]["hp"] for p in ("dilly", "hester")], [1, 1])
        self.assertEqual({p["status"] for p in self.save()["players"].values()}, {"playing"})
        entry = [e for e in self.log_entries() if e["kind"] == "contest"][-1]
        self.assertTrue(entry["scuffle"])
        self.assertIsNone(entry["item"])

    def test_someone_new_may_arrive_once_a_day_where_the_world_says_who_may(self):
        self.rpg("game", "switch", "wendleford")
        self.rpg("newgame", seed=44)
        brief = self.rpg("world-brief", "turn", as_=False)
        self.assertIn("Someone new may arrive today (at most one a day", brief)
        self.assertIn("Who may arrive here: Travellers on the road,", brief)
        wat = {"id": "wat_harlow", "name": "Wat Harlow", "role": "a farmhand come for the harvest work",
               "personality": "Big, slow and good-natured.", "speech": "Slow and broad.", "knows": ["He walked in from Coombe."],
               "wants": "A day's work.", "tier": None}
        self.write("proposals/wt.json", json.dumps({"rumors": [], "moves": [], "arrival": dict(wat, room="nowhere")}))
        self.assertIn("an arrival comes to a room that exists", self.rpg("world-turn", "proposals/wt.json", as_=False, ok=False))
        self.write("proposals/wt.json", json.dumps({"rumors": [], "moves": [], "arrival": dict(wat, room="wheatsheaf")}))
        self.assertIn("arrived: Wat Harlow (wat_harlow), a farmhand come for the harvest work, at wheatsheaf",
                      self.rpg("world-turn", "proposals/wt.json", as_=False))
        run = self.save()["run"]
        self.assertEqual((run["arrivals"], run["placements"]["wheatsheaf"], run["generated"]), ({"1": "wat_harlow"}, ["wat_harlow"], 1))
        self.assertIn("wat_harlow [minor, generated]", self.rpg("look", as_="marigold"))
        self.assertNotIn("Someone new may arrive", self.rpg("world-brief", "turn", as_=False), "one a day")
        nan = dict(wat, id="nan_cole", name="Nan Cole", role="a pedlar", room="market_square")
        self.write("proposals/wt.json", json.dumps({"rumors": [], "moves": [], "arrival": nan}))
        self.assertIn("no one new arrives on this world turn", self.rpg("world-turn", "proposals/wt.json", as_=False, ok=False))
        for _ in range(4):
            self.round_doing()  # the next morning
        self.assertIn("Someone new may arrive today", self.rpg("world-brief", "turn", as_=False))
        self.rpg("game", "switch", "dark_lighthouse")  # a world that doesn't say who may arrive: no one does
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=44)
        self.assertNotIn("Someone new may arrive", self.rpg("world-brief", "turn", as_=False))
        self.write("proposals/wt.json", json.dumps({"rumors": [], "moves": [], "arrival": dict(wat, room="harbor_square")}))
        self.assertIn("no one new arrives on this world turn", self.rpg("world-turn", "proposals/wt.json", as_=False, ok=False))

    def test_validate_holds_shared_work_to_its_shape(self):
        self.needs_world()
        rooms = self.dir / "games" / "dark_lighthouse" / "rooms"
        for name, spec in (("harbor_square", "project:\n  id: nets\n  stages: half\n  stat: luck\n  dc: lots\n  meal: maybe\n  pay: 2\n"),
                           ("gull_tavern", "project:\n  id: nets\n  stages: 2: lamp_quest_started\n"), ("coast_road", "project:\n  name: x\n")):
            path = rooms / ("%s.md" % name)
            path.write_text(path.read_text().replace("---\n", "---\n" + spec, 1))
        lighthouse = rooms / "lighthouse.md"
        lighthouse.write_text(lighthouse.read_text() + "\n## If most_roads\nA road.\n")
        out = self.rpg("validate", "--game", "dark_lighthouse", ok=False)
        for expected in ('stages: "<amount>: <flag>; ..."', "stat must be one of", "dc must be a number", "meal must be yes or no",
                         "pay isn't one of id, name", "project: nets is also the shared work at", "stage flag 'lamp_quest_started' must be a shared flag",
                         "coast_road.md: project: needs an id", "condition 'most_roads': no shared work called 'roads'"):
            self.assertIn(expected, out)

    def test_validate_warns_of_what_ignores_the_ending_and_of_the_player_and_passes_the_world_all_the_same(self):
        out = self.rpg("validate")
        self.assertIn("WARNING: thirteenth_stroke: characters/tibbersnatch.md: `## If craves_whistle` never asks how the quest "
                      "ended (clock_stopped, shadows_carted, shadows_freed)", out)
        self.assertIn('WARNING: thirteenth_stroke: characters/nell.md: says "the player" 2 times where their agent reads it', out)
        self.assertIn("CONTENT OK: thirteenth_stroke", out)
        self.assertIn("CONTENT OK: thirteenth_stroke", self.rpg("validate", "--game", "thirteenth_stroke", "--sim-complete"))
        out = self.rpg("validate", "--game", "thirteenth_stroke", "--sim-strict", ok=False)
        for expected in ("sim-strict: needs days that go on", "sim-strict: needs at least one need", "sim-strict: needs someone who sells",
                         "sim-strict: needs shared work", "sim-strict: needs something scarce", "sim-strict: world.md has `## Who the player is`",
                         "sim-strict: characters/tibbersnatch.md: `## If craves_whistle` never asks"):
            self.assertIn(expected, out)
        self.assertNotIn("WARNING:", out, "under the strict check they're errors")

    def test_a_world_built_for_the_simulation_passes_the_strict_check(self):
        self.projects_world()
        games = self.dir / "games" / "dark_lighthouse"
        pell = games / "characters" / "pell.md"
        pell.write_text(pell.read_text().replace("---\n", "---\nsells:\n  honey_cake: 1\n  smoked_fish: 2, 1 in stock\n", 1))
        morwen = games / "characters" / "morwen.md"
        morwen.write_text(morwen.read_text().replace("---\n", "---\nbuys:\n  trinket: 1\n", 1))
        square = games / "rooms" / "harbor_square.md"
        square.write_text(square.read_text().replace("---\n", "---\nwork:\n  stat: might\n  pay: 1-2\n", 1))
        world = games / "world.md"
        text = re.sub(r"\n## Who the player is\n.*?(?=\n## )", "\n", world.read_text(), flags=re.S)
        world.write_text(re.sub(r"(\n  (?:rooms|items)): \w+", r"\1: no", text))
        for path in (games / "characters").glob("*.md"):  # the lone hero's words gone, and every want following the ending
            body = re.sub(r"\bthe player\b", "the one talking to you", path.read_text(), flags=re.I)
            path.write_text(re.sub(r"^(## If (?!.*lamp_lit).*)$", r"\1 and not lamp_lit", body, flags=re.M))
        out = self.rpg("validate", "--game", "dark_lighthouse", "--sim-strict")
        self.assertIn("CONTENT OK: dark_lighthouse:", out)
        self.assertIn("(sim-strict)", out)
        world.write_text(world.read_text().replace("needs: food, sleep\n", ""))
        self.assertIn("sim-strict: needs at least one need", self.rpg("validate", "--game", "dark_lighthouse", "--sim-strict", ok=False))

    def made_hobb(self, **changes):
        """An entry for Hobb in The Thirteenth Stroke as the generator might write it from his archetype."""
        arch = json.loads((ROOT / "cast" / "hobb.json").read_text())
        old = next(e for e in json.loads((ROOT / "games" / "thirteenth_stroke" / "cast.json").read_text()) if e["id"] == "hobb")
        entry = {"id": "hobb", "name": arch["name"], "pronouns": arch["pronouns"], "voice": arch["voice"], "wont_do": arch["wont_do"],
                 "backstory": "About twenty-five. I carry coal to every hearth in Wumbleby and sleep on the sacks behind the Tock Tower.",
                 "wants_and_needs": ["four walls of my own, and a door that locks", "to owe nobody in Wumbleby a button"],
                 "avoids_and_dislikes": ["owing anyone, even a thank-you", "spending a button I needn't"],
                 "priorities": ["owing nobody", "four walls of my own", "putting right what's gone wrong"],
                 "how_i_am": "I keep a tally of every button and spend none I needn't. I keep my own company and let others lead, and I'd "
                             "sooner go unnoticed. What I say I'll do, I do, and I pay what I owe the same day.",
                 "look": "Big and slow, soot to the elbows, a sack over one shoulder.",
                 "knows": ["Old Ambrose keeps the town clock and builds sheds for a price."],
                 "people": [{"who": "ambrose", "how": "I sleep in his coal yard by his leave."}],
                 "home": old["home"], "inventory": old["inventory"], "equipped": None, "attributes": old["attributes"],
                 "hp": old["hp"], "coins": old["coins"], "opening": "You're awake on the coal sacks behind the tower, and the clock ticks too fast."}
        entry.update(changes)
        return entry

    def test_the_generator_makes_an_entry_from_the_archetype_and_checks_it(self):
        out, asked, argv = self.ask("make", "thirteenth_stroke", "hobb", answers=["```json\n%s\n```" % json.dumps(self.made_hobb())], tool="tools/cast.py")
        self.assertIn("MADE: Hobb Ashcombe for thirteenth_stroke, in proposals/cast-hobb.json", out)
        self.assertIn("PROBLEMS: none", out)
        self.assertIn("# How they lean (1 to 5; 3 is ordinary, and only the others are listed)\n- With money: 1 (1: I hold on to every coin;", asked[0])
        self.assertIn("## Places (id: name. what it is)\n- ", asked[0])
        self.assertNotIn("- Initiative:", asked[0], "an ordinary rating isn't listed")
        system = argv[0][argv[0].index("--system-prompt") + 1]
        self.assertTrue(system.startswith("You write one person's entry for a world"), system[:60])
        made = json.loads((self.dir / "proposals" / "cast-hobb.json").read_text())
        self.assertEqual((made["archetype"], sorted(made["made_with"])), ("hobb", ["archetype", "cost", "definitions", "generate", "model", "when"]))
        bad = self.made_hobb(voice="Loud.", how_i_am="I hold on to every coin, 5 of them, and the dice say so.")
        out, _, _ = self.ask("make", "thirteenth_stroke", "hobb", answers=[json.dumps(bad)], ok=False, tool="tools/cast.py")
        for expected in ("how_i_am has a number in it", "how_i_am has a trait's line word for word: 'I hold on to every coin'",
                         "a word of the machinery, 'dice'", "voice must be the archetype's, word for word"):
            self.assertIn(expected, out)
        out, _, _ = self.ask("make", "thirteenth_stroke", "hobb", answers=["I can't."], ok=False, tool="tools/cast.py")
        self.assertEqual((self.dir / "proposals" / "cast-hobb.txt").read_text(), "I can't.", "a reply with no entry is kept as it came")

    def test_the_generator_keeps_a_situation_already_decided_and_writes_around_it(self):
        reply = self.made_hobb(home="lopsided_square", coins=2, situation="sleeping in a ditch", people=[], inventory=["tally_stick"])
        out, asked, _ = self.ask("make", "wendleford", "hobb", answers=[json.dumps(reply)], tool="tools/cast.py")
        self.assertIn("# Their situation here, already decided (keep it as given)\n- They start in: The Tithe Barn (tithe_barn)\n"
                      "- Their money: 6 pennies\n- Sleeps in the tithe barn's hayloft", asked[0])
        made = json.loads((self.dir / "proposals" / "cast-hobb.json").read_text())
        self.assertEqual((made["home"], made["coins"], made["situation"][:30]), ("tithe_barn", 6, "Sleeps in the tithe barn's hay"),
                         "what was decided stays, whatever the reply says")
        out, asked, _ = self.ask("make", "wendleford", "marigold", answers=["{}"], ok=False, tool="tools/cast.py")
        self.assertIn("- Already paid for: a bed at The Wheatsheaf, 1 night\n", asked[0])
        s = self.rpg("validate", "--game", "wendleford")
        cast = self.dir / "games" / "wendleford" / "cast.json"
        cast.write_text(cast.read_text().replace('"situation": "Sleeps', '"situation": "' + "x" * 300 + 'Sleeps', 1))
        self.assertIn("situation is one line of at most 240 characters", self.rpg("validate", "--game", "wendleford", ok=False))

    def test_an_entry_made_from_an_archetype_opens_the_brief_in_its_own_layout(self):
        self.write("proposals/cast-hobb.json", json.dumps(self.made_hobb(archetype="hobb")))
        out, _, _ = self.ask("apply", "thirteenth_stroke", "hobb", answers=[], tool="tools/cast.py")
        self.assertIn("APPLIED: hobb's entry is in games/thirteenth_stroke/cast.json.", out)
        self.assertIn("CONTENT OK: thirteenth_stroke", out)
        self.rpg("game", "switch", "thirteenth_stroke")
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=44)
        brief = self.rpg("brief", "hobb")
        self.assertIn("## Who I am (a note to myself)\nI'm Hobb Ashcombe (he/him). About twenty-five. I carry coal", brief)
        self.assertIn("What I want: four walls of my own, and a door that locks; to owe nobody in Wumbleby a button.\n"
                      "What I steer clear of: owing anyone, even a thank-you; spending a button I needn't.\n"
                      "What I won't do: I won't take what isn't mine; I won't leave a debt unpaid.\n"
                      "What comes first: owing nobody then four walls of my own then putting right what's gone wrong.\n"
                      "People I know: Ambrose Tock: I sleep in his coal yard by his leave.\n"
                      "I keep a tally of every button", brief)
        self.assertNotIn("What drives me", brief)
        self.assertIn("What you want: four walls of my own, and a door that locks; to owe nobody in Wumbleby a button.", brief)
        self.assertIsNone(self.FORBIDDEN.search(brief.split("## What everyone")[0]))
        tags = [e for e in self.log_entries() if e["kind"] == "brief"][-1]["versions"]
        self.assertIn("archetype:hobb", tags)
        self.assertIn("definitions", tags)
        self.assertIn("What drives me: I want to be admired; I love fine things.", self.rpg("brief", "marigold"), "hand-written entries as before")

    def test_the_round_trip_sets_what_the_note_shows_beside_the_archetypes_ratings(self):
        self.write("proposals/cast-hobb.json", json.dumps(self.made_hobb(archetype="hobb")))
        defs = json.loads((ROOT / "rules" / "people" / "defaults.json").read_text())
        arch = json.loads((ROOT / "cast" / "hobb.json").read_text())
        answer = "\n".join("%s: %d" % (k, arch[part][k]) for part in ("attributes", "ways") for k in defs[part])
        answer = answer.replace("with_money: 1", "with_money: 4").replace("honesty: 5\n", "")
        out, asked, argv = self.ask("check", "thirteenth_stroke", "hobb", "--proposal", answers=[answer], tool="tools/cast.py")
        self.assertIn("# The note\n## Who I am (a note to myself)\nI'm Hobb Ashcombe (he/him).", asked[0])
        self.assertIn("- with_money: 1 = I hold on to every coin; 5 = I spend whatever I have", asked[0])
        self.assertIn("with_money         1  read 4   <<< +3", out)
        self.assertIn("honesty            5  read ?   <<< not answered", out)
        self.assertIn("FLAGGED: 2 of 32, 2 or more apart; 30 read exactly", out)
        kept = json.loads(sorted((self.dir / "bench" / "results").glob("cast-check-thirteenth_stroke-hobb-*.json"))[-1].read_text())
        self.assertEqual((kept["entry"], kept["archetype"], len(kept["rows"])), ("proposal", "hobb", 32))
        out, asked, _ = self.ask("check", "thirteenth_stroke", "hobb", "--archetype", "hobb", answers=[answer], tool="tools/cast.py")
        self.assertIn("What drives me", asked[0], "the hand-written entry, as its brief shows it")

    def test_validate_holds_the_definitions_the_archetypes_and_entries_made_from_them(self):
        arch = self.dir / "cast" / "hobb.json"
        data = json.loads(arch.read_text())
        data["attributes"]["kindness"] = 7
        del data["ways"]["wait"]
        data["attributes"]["luck"] = 3
        arch.write_text(json.dumps(data))
        cast = self.dir / "games" / "thirteenth_stroke" / "cast.json"
        entries = json.loads(cast.read_text())
        entries[1] = self.made_hobb(archetype="hobb", personality="I'm Hobb.", wont_do=["I won't."])
        cast.write_text(json.dumps(entries))
        out = self.rpg("validate", ok=False)
        for expected in ("cast/hobb.json: attributes kindness needs a rating from 1 to 5", "cast/hobb.json: ways wait needs a rating",
                         "cast/hobb.json: attributes luck isn't in the definitions", "wont_do must be the archetype's, word for word",
                         "personality is for a hand-written entry"):
            self.assertIn(expected, out)

    def test_a_person_strikes_what_no_longer_holds_from_what_they_learned_on_their_own_turn(self):
        self.rpg("game", "switch", "thirteenth_stroke")
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=44)
        s = self.save()
        s["players"]["hobb"]["learned"] = ["Ambrose builds sheds, for five buttons.", "I still need to fetch a poker.",
                                           "The peddler will trade the jar for a tin whistle."]
        s["players"]["hobb"]["kept"] = [{"round": 1, "text": "The clock stopped."}]
        self.write("state/save.json", json.dumps(s))
        order = [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().split(", ")]
        for pid in order[:order.index("hobb")]:
            self.take_turn(pid)
        self.write("proposals/reply.txt", "DO: I climb to the gearloft.\nJOURNAL: The clock's stopped.\n"
                   "NO LONGER: I still need to fetch the poker\nNO LONGER: the peddler will trade the jar for a tin whistle.\n"
                   "NO LONGER: The clock stopped.\n")
        out = self.rpg("reply", "hobb", "proposals/reply.txt")
        self.assertIn("NO LONGER: 2 struck from what they've learned (of 3 named)", out)
        self.assertNotIn("fetch", out, "the referee is told how many, not what")
        pl = self.save()["players"]["hobb"]
        self.assertEqual(pl["learned"], ["Ambrose builds sheds, for five buttons."])
        self.assertEqual(pl["kept"], [{"round": 1, "text": "The clock stopped."}], "what the run settled isn't theirs to strike")
        self.assertEqual(pl["turn"]["journal"], "The clock's stopped.")
        self.assertNotIn("NO LONGER", json.dumps(pl["memory"]))
        action = [e for e in self.log_entries() if e["kind"] == "action"][-1]
        self.assertEqual(action["no_longer"], [
            {"said": "I still need to fetch the poker", "struck": "I still need to fetch a poker."},
            {"said": "the peddler will trade the jar for a tin whistle.", "struck": "The peddler will trade the jar for a tin whistle."},
            {"said": "The clock stopped.", "struck": None}])
        audit = self.run_py("tools/audit.py", "state/log/%s.jsonl" % self.save()["run"]["id"]).stdout
        self.assertIn("hobb no longer: 'The clock stopped.' -> matched nothing on their list", audit)
        self.assertIn("## What I know\n- Ambrose builds sheds, for five buttons.\n- The clock stopped.\n", self.rpg("brief", "hobb"))

    def test_the_think_back_sees_their_whole_note_or_only_their_voice(self):
        self.rpg("game", "switch", "thirteenth_stroke")
        self.settings_tool("preset", "simulation")
        self.settings_tool("set", "memory.recent_rounds", "1")
        self.settings_tool("set", "memory.condense_every", "1")
        self.rpg("newgame", seed=44)
        self.thirteenth_round()
        self.thirteenth_round()
        think = self.rpg("memory", "condense", "hobb")
        self.assertIn("You are Hobb Ashcombe. This is the note you keep about yourself:\n\n## Who I am (a note to myself)\n"
                      "I'm Hobb Ashcombe (he/him).", think)
        self.assertIn("What drives me: I want a place of my own", think)
        self.settings_tool("set", "memory.thinkback_sees", "voice")
        think = self.rpg("memory", "condense", "hobb")
        self.assertIn("You are Hobb Ashcombe. How you speak, in your own words: Few words, said slow and plain.", think)
        self.assertNotIn("What drives me", think)
        self.assertIsNone(self.FORBIDDEN.search(think.replace("Hobb Ashcombe", "")), think)
        self.write("proposals/m.txt", "MEMORY: I looked about.")
        self.rpg("memory", "store", "hobb", "proposals/m.txt")
        self.assertEqual([e["sees"] for e in self.log_entries() if e["kind"] == "memory"], ["voice"])
        self.assertIn("memory.thinkback_sees must be who_i_am or voice", self.settings_tool("set", "memory.thinkback_sees", "all", ok=False))
        self.assertIn("memory.learned_max must be a whole number, at least 1", self.settings_tool("set", "memory.learned_max", "0", ok=False))

    def test_in_a_simulation_the_clock_moves_by_rounds_not_moves(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=43)
        for d in ("east", "west", "east"):
            self.assertNotIn("WORLD TURN DUE", self.rpg("move", d))
        self.assertEqual(self.save()["run"]["moves"], 0)
        _, end = self.play_round()
        self.assertNotIn("WORLD TURN DUE", end)
        _, end = self.play_round()
        self.assertIn("WORLD TURN DUE", end)  # every 2 rounds in the simulation preset
        self.assertEqual(self.save()["run"]["moves"], 2)
        # between rounds the world turn is no one's: it runs without --as, and its brief says where everyone is
        brief = self.rpg("world-brief", "turn", as_=False)
        self.assertIn("## Where the players are\nWren (they/them) at ", brief)
        self.assertIn("; Corin (they/them) at ", brief)
        self.assertNotIn("## Where the player is", brief)
        self.assertIn("say who acts", self.rpg("world-brief", "extra", as_=False, ok=False))
        self.write("proposals/wt.json", json.dumps({"rumors": ["The keeper's lamp burned blue last night."], "moves": []}))
        self.assertIn("WORLD TURN: 1 rumors", self.rpg("world-turn", "proposals/wt.json", as_=False))
        self.assertNotIn("WORLD TURN DUE", self.rpg("look"))

    def test_a_building_is_finished_after_its_rounds(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=50)
        self.rpg("world-brief", "build", "morwen")
        self.write("proposals/b.json", json.dumps({"id": "net_loft", "name": "The Net-Loft", "direction": "southwest",
                                                   "terrain": "indoors", "description": "A loft for drying nets."}))
        self.rpg("generate", "build", "proposals/b.json")
        self.rpg("coins", "+5", "gift")
        self.assertIn("ready in 3 rounds", self.rpg("pay", "net_loft"))
        ends = [self.play_round()[1] for _ in range(4)]
        built = [i for i, e in enumerate(ends) if "BUILT: The Net-Loft" in e]
        self.assertEqual(len(built), 1)
        self.assertIn("net_loft", self.me()["map"]["harbor_square"]["exits"].values())
        told = [e["text"] for e in self.me()["memory"]["recent"] if e["kind"] == "seen" and "is finished" in e["text"]]
        self.assertEqual(told, ["The Net-Loft is finished, southwest of Harbor Square: Morwen built it for you."])
        self.assertNotIn("built it for you", json.dumps(self.save()["players"]["corin"]["memory"]), "only its owner is told")
        self.assertIn("## What I know\n- The Net-Loft is finished, southwest of Harbor Square: Morwen built it for you.\n",
                      self.rpg("brief", "wren", as_=False), "and kept where it never fades")
        self.assertNotIn("## What I know", self.rpg("brief", "corin", as_=False))

    def test_an_order_is_logged_from_what_was_asked_to_each_use(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.settings_tool("preset", "simulation")  # built by rounds
        self.rpg("newgame", seed=50)  # Wren in Harbor Square, with Morwen
        self.rpg("round", "start")
        first = self.save()["run"]["round_state"]["order"][0]
        if first != "wren":
            self.take_turn(first)
        self.write("proposals/reply.txt", "DO: I ask Morwen to build me a loft for my things.\nJOURNAL: I want somewhere of my own.")
        self.rpg("reply", "wren", "proposals/reply.txt")
        self.rpg("world-brief", "build", "morwen")
        self.write("proposals/b.json", json.dumps({"id": "net_loft", "name": "The Net-Loft", "direction": "southwest",
                                                   "terrain": "indoors", "description": "A loft for drying nets."}))
        self.rpg("generate", "build", "proposals/b.json")
        self.rpg("coins", "+5", "gift")
        self.rpg("pay", "net_loft")
        self.write("proposals/story.txt", "Morwen spits on her palm and shakes on it.")
        self.rpg("narrate", "wren", "proposals/story.txt")
        if first == "wren":
            self.take_turn("corin")
        self.rpg("round", "end")
        for _ in range(3):
            self.play_round()
        self.rpg("move", "southwest")
        self.rpg("drop", "worn_dagger")
        self.assertIn("STASH: The Net-Loft is Wren's own place", self.rpg("look"))
        self.rpg("move", "south", as_="corin")
        self.rpg("move", "southwest", as_="corin")
        self.assertIn("this is Wren's stash", self.rpg("take", "worn_dagger", as_="corin", ok=False))
        self.rpg("take", "worn_dagger")
        entries = [json.loads(line) for line in (self.dir / "state" / "log" / ("%s.jsonl" % self.save()["run"]["id"])).read_text().splitlines()]
        steps = [(e["step"], e.get("how")) for e in entries if e["kind"] == "order"]
        self.assertEqual(steps, [("asked", None), ("shaped", None), ("priced", None), ("paid", None), ("delivered", None),
                                 ("used", "entered"), ("used", "entered")])
        asked = next(e for e in entries if e["kind"] == "order")
        self.assertEqual((asked["order"], asked["player"], asked["words"], asked["journal"]),
                         ("o1", "wren", "I ask Morwen to build me a loft for my things.", "I want somewhere of my own."))
        self.assertTrue(all(e["order"] == "o1" for e in entries if e["kind"] == "order"))
        self.assertEqual(self.save()["run"]["rooms"]["net_loft"]["meta"]["owner"], "wren")

    FORBIDDEN = re.compile(r"\b(games?|rules?|dice|flags?|agents?|models?|players?|logs?|d20|dc|rolls?|checks?|"
                           r"rpg|refused|generated|meter)\b|\[(agent|minor)|--as|\b[a-z]+_[a-z_]+\b", re.I)

    def test_the_words_people_read_come_from_rules_people(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.settings_tool("preset", "simulation")
        self.settings_tool("set", "memory.recent_rounds", "1")
        self.settings_tool("set", "memory.condense_every", "1")
        self.rpg("newgame", seed=43)
        brief = self.dir / "rules" / "people" / "brief.md"
        text = brief.read_text()
        brief.write_text(text.replace("closing:         What do you do now?", "closing:  And now, {name}?")
                             .replace("money:           Money: {n} {currency}.", "money: You have {n} {currency} to your name."))
        self.assertIn("closing has a gap the code doesn't fill: name", self.rpg("validate", ok=False))
        brief.write_text(text.replace("closing:         What do you do now?", "closing:  And now?")
                             .replace("money:           Money: {n} {currency}.", "money: You have {n} {currency} to your name."))
        order = [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().split(", ")]
        first = order[0]
        out = self.rpg("brief", first)
        self.assertTrue(out.endswith("\nAnd now?\n"), out[-60:])
        self.assertIn("\nYou have ", out)
        self.assertNotIn("Money:", out)
        for pid in order:
            self.take_turn(pid)
        self.rpg("round", "end")
        self.play_round()
        think = self.dir / "rules" / "people" / "thinkback.md"
        think.write_text(think.read_text().replace("Some time has passed.", "Days have gone by."))
        self.assertIn("Days have gone by. Think back", self.rpg("memory", "condense", first))
        brief.write_text(text.replace("closing:         What do you do now?\n", "").replace("\nand:", "\nan_d:"))
        out = self.rpg("validate", ok=False)
        self.assertIn("kit: rules/people/brief.md: closing is missing", out)
        self.assertIn("kit: rules/people/brief.md: an_d isn't a phrase the code uses", out)
        think.write_text("Remember, {who}: {stretch}")
        self.assertIn("kit: rules/people/thinkback.md has a gap the code doesn't fill: who", self.rpg("validate", ok=False))

    def test_the_words_in_rules_people_name_none_of_the_machinery(self):
        phrases = re.findall(r"^[a-z_]+:[ \t]*(.*)$", (ROOT / "rules" / "people" / "brief.md").read_text(), re.M)
        self.assertGreater(len(phrases), 50)
        think = re.sub(r"\A\s*<!--.*?-->", "", (ROOT / "rules" / "people" / "thinkback.md").read_text(), flags=re.S)
        universe = [l for l in (ROOT / "rules" / "people" / "universe.md").read_text().splitlines() if l.strip() and not l.startswith("#")]
        self.assertGreaterEqual(len(universe), 3)
        for text in phrases + [think] + universe:
            self.assertIsNone(self.FORBIDDEN.search(re.sub(r"\{[a-z_]+\}", "", text)), text)

    def test_a_brief_holds_the_players_own_life_and_nothing_of_the_machinery(self):
        for game in GAMES:
            self.rpg("game", "switch", game)
            self.settings_tool("preset", "simulation")
            self.rpg("newgame", seed=44)
            ids = list(self.save()["players"])
            briefs = []
            for _ in range(3):
                order = [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().split(", ")]
                for pid in order:
                    briefs.append(self.rpg("brief", pid))
                    exits = list(self.save()["players"][pid]["map"][self.save()["players"][pid]["location"]]["exits"])
                    self.write("proposals/reply.txt", "DO: I walk %s, humming %s.\nJOURNAL: To see what is there." % (exits[0], pid))
                    self.rpg("reply", pid, "proposals/reply.txt")
                    self.rpg("move", exits[0], as_=pid)
                    self.rpg("check", "wits", "easy", as_=pid)
                    self.write("proposals/story.txt", "You walk on.")
                    self.rpg("narrate", pid, "proposals/story.txt")
                self.rpg("round", "end")
            for brief in briefs:
                self.assertIsNone(self.FORBIDDEN.search(brief), (game, self.FORBIDDEN.search(brief), brief))
            first = self.rpg("brief", ids[0], as_=False)
            self.assertIn("### Moment 3", first)
            self.assertNotIn("How it begins", first, "the opening is the first turn's only")
            self.assertIn("How it begins", briefs[0])
            other = self.save()["players"][ids[1]]
            self.assertNotIn("humming %s" % ids[1], first, "another's memory")
            self.assertIn("humming %s" % ids[0], first)
            logged = [e for e in self.log_of() if e["kind"] == "brief"]
            self.assertEqual(logged[-1]["text"], first.rstrip("\n"))
            self.assertTrue(all(e["uses"] >= 1 for e in self.save()["players"][ids[0]]["memory"]["recent"]))

    def test_dice_lines_reach_the_brief_only_when_the_owner_turns_them_on(self):
        self.rpg("game", "switch", "dark_lighthouse")
        self.settings_tool("preset", "simulation")
        self.rpg("newgame", seed=44)
        order = [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().split(", ")]
        for pid in order:
            self.write("proposals/reply.txt", "DO: I try to climb the wall.")
            self.rpg("reply", pid, "proposals/reply.txt")
            self.rpg("check", "agility", "hard", as_=pid)
            self.write("proposals/story.txt", "You try.")
            self.rpg("narrate", pid, "proposals/story.txt")
        self.rpg("round", "end")
        self.assertNotIn("CHECK agility", self.rpg("brief", order[0], as_=False))
        self.settings_tool("set", "brief.dice_lines", "true")
        self.assertIn("CHECK agility vs DC 16", self.rpg("brief", order[0], as_=False))

    def log_of(self):
        return [json.loads(line) for line in (self.dir / "state" / "log" / ("%s.jsonl" % self.save()["run"]["id"])).read_text().splitlines()]

    def test_a_person_knows_what_they_knew_at_the_start_what_everyone_knows_and_what_the_run_settled(self):
        self.rpg("game", "switch", "thirteenth_stroke")
        self.settings_tool("preset", "simulation")
        path = self.dir / "games" / "thirteenth_stroke" / "cast.json"
        cast = json.loads(path.read_text())
        hobb = next(e for e in cast if e["id"] == "hobb")
        hobb.update(knows=["Ambrose Tock builds sheds and porches, for a price.", "Nell Fizzlewick makes sweets to order."],
                    people=[{"who": "ambrose", "how": "He lets me sleep on the coal sacks, which counts as owing."},
                            {"who": "marigold", "how": "She mends every coat in town, mine included."}],
                    look="a big, slow, soot-grimed man in a coal-black coat")
        path.write_text(json.dumps(cast))
        self.assertIn("CONTENT OK: thirteenth_stroke", self.rpg("validate"))
        self.rpg("newgame", seed=43)
        self.assertIn("ambrose", self.save()["players"]["hobb"]["met"], "someone they know they've met already")
        brief = self.rpg("brief", "hobb", as_=False)
        self.assertIn("## Who I am (a note to myself)\nI'm Hobb Ashcombe (he/him). Big, slow", brief)
        self.assertIn("People I know: Ambrose Tock: He lets me sleep on the coal sacks, which counts as owing; "
                      "Marigold Thimble: She mends every coat in town, mine included.\n\n## What I know\n"
                      "- Ambrose Tock builds sheds and porches, for a price.\n- Nell Fizzlewick makes sweets to order.\n\n"
                      "## What everyone around here knows\n- Folk pay for things in buttons, and most have little to spare.\n", brief)
        self.assertIn("- Three days ago a peddler called Mister Tibbersnatch rolled into town", brief, "the world's public knowledge")
        self.assertLess(brief.index("## What everyone around here knows"), brief.index("## How it begins"))
        marigold = self.rpg("brief", "marigold", as_=False)
        self.assertIn("I'm Marigold Thimble (she/her).", marigold)
        self.assertNotIn("## What I know", marigold, "no facts of her own yet, and nothing settled")
        self.assertIn("## What you're working on\nWhat you want: I want to be admired; I love fine things.\n\n", marigold, "her wants beside")
        self.assertNotIn("What you've taken on", marigold, "the town's problem is known, but not hers until she takes it on")
        # what others see of him, for the referee and the townspeople alike (Pip, in the square, has an agent's voice)
        self.rpg("move", "south", as_="hobb")  # the Tock Tower to the square, where Marigold is
        self.assertIn("Hobb Ashcombe (hobb, he/him; a big, slow, soot-grimed man in a coal-black coat; carrying", self.rpg("look", as_="marigold"))
        self.assertIn("Hobb Ashcombe (he/him; a big, slow, soot-grimed man in a coal-black coat)", self.rpg("npc-brief", "pip", as_="marigold"))
        # taking the town's problem on, and setting it aside
        look = self.rpg("look", as_="marigold")
        self.assertIn("QUESTS: Before the Thirteenth Stroke (thirteenth_stroke): not taken on.", look)
        self.assertIn("TAKEN ON: Before the Thirteenth Stroke", self.rpg("quest", "take", "thirteenth_stroke", as_="marigold"))
        self.assertIn("already taken on", self.rpg("quest", "take", "thirteenth_stroke", as_="marigold", ok=False))
        self.assertIn("## What you're working on\nWhat you want: I want to be admired; I love fine things.\nWhat you've taken on:\n"
                      "- Before the Thirteenth Stroke: ", self.rpg("pane", "marigold"))
        self.assertNotIn("What you've taken on", self.rpg("pane", "hobb"), "hers, not his")
        self.assertIn("SET ASIDE", self.rpg("quest", "leave", "thirteenth_stroke", as_="marigold"))
        self.assertNotIn("What you've taken on", self.rpg("pane", "marigold"))
        self.settings_tool("set", "brief.wants", "false")  # wants not shown: what they've taken on alone, as before
        self.rpg("quest", "take", "thirteenth_stroke", as_="marigold")
        self.assertIn("## What you're working on\nBefore the Thirteenth Stroke: ", self.rpg("pane", "marigold"))
        self.rpg("quest", "leave", "thirteenth_stroke", as_="marigold")
        self.assertNotIn("## What you're working on", self.rpg("pane", "marigold"))
        self.settings_tool("set", "brief.wants", "true")
        self.assertIn("no quest 'nope'", self.rpg("quest", "take", "nope", as_="marigold", ok=False))
        # an ending: everyone keeps what the town saw of it, the one who brought it about too, and it never fades
        order = [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().split(", ")]
        self.write("proposals/reply.txt", "DO: I jam the poker in the gear.\nJOURNAL: To stop the clock.\n")
        self.rpg("reply", order[0], "proposals/reply.txt")
        self.rpg("flag", "set", "clock_stopped", as_=order[0])
        self.write("proposals/ending.txt", "Word came that the town clock had stopped a whisker before midnight.")
        self.rpg("ending", "proposals/ending.txt", as_=order[0])
        self.write("proposals/story.txt", "The gear stops dead.")
        self.rpg("narrate", order[0], "proposals/story.txt")
        for pid in order[1:]:
            self.take_turn(pid)
        self.rpg("round", "end")
        for _ in range(6):
            self.play_round()
        for pid in order:
            self.assertIn("## What I know\n%s- Word came that the town clock had stopped a whisker before midnight.\n" % (
                "- Ambrose Tock builds sheds and porches, for a price.\n- Nell Fizzlewick makes sweets to order.\n" if pid == "hobb" else ""),
                self.rpg("brief", pid, as_=False))

    def test_validate_checks_what_a_cast_entry_says_they_know(self):
        path = self.dir / "games" / "dark_lighthouse" / "cast.json"
        cast = json.loads(path.read_text())
        cast[0].update(knows=["x" * 300], people=[{"who": "nobody_here", "how": "We met once."}, {"who": cast[0]["id"], "how": "Me."}],
                       look="")
        cast[1].update(knows="a fact", people=[{"who": "morwen"}])
        path.write_text(json.dumps(cast))
        out = self.rpg("validate", ok=False)
        first, second = cast[0]["id"], cast[1]["id"]
        self.assertIn("cast.json %s: knows must be a list of at most 8 facts, each a line of at most 240 characters" % first, out)
        self.assertIn("cast.json %s: people: 'nobody_here' is neither another of the cast nor a character in this world" % first, out)
        self.assertIn("cast.json %s: people: '%s' is neither" % (first, first), out, "not themselves")
        self.assertIn("cast.json %s: look must be a line of at most 240 characters" % first, out)
        self.assertIn("cast.json %s: knows must be a list" % second, out)
        self.assertIn('cast.json %s: people must be a list of at most 8 {"who", "how"}' % second, out)

    def test_a_blank_person_has_a_name_a_place_and_money_and_nothing_of_their_own(self):
        d = "games/dark_lighthouse/cast.json"
        cast = json.loads((self.dir / d).read_text())
        other, home = cast[0]["id"], cast[1]["home"]
        cast[1] = {"id": "entity1", "name": "Entity1", "home": home, "coins": 5, "blank": True}
        self.write(d, json.dumps(cast + [{"id": "entity2", "name": "Entity2", "home": home, "blank": True, "voice": "Slow."},
                                         {"id": "entity3", "name": "Entity3", "home": home, "blank": False}]))
        out = self.rpg("validate", "--game", "dark_lighthouse", ok=False)
        self.assertIn("cast.json entity2: a blank person has no voice", out)
        self.assertIn("cast.json entity3: blank is true, or left out", out)
        self.assertNotIn("cast.json entity1", out)
        self.write(d, json.dumps(cast))
        self.rpg("validate", "--game", "dark_lighthouse")
        self.rpg("game", "switch", "dark_lighthouse")
        self.settings_tool("preset", "simulation")
        self.settings_tool("set", "memory.recent_rounds", "1")
        self.settings_tool("set", "memory.condense_every", "1")
        self.rpg("newgame", seed=43)
        order = [p.split("(")[1].rstrip(")") for p in self.rpg("round", "start").split(": ", 1)[1].strip().split(", ")]
        brief = self.rpg("brief", "entity1", as_=False)
        self.assertTrue(brief.startswith("## What everyone around here knows\n"), "no Who I am note")
        self.assertNotIn("## How it begins", brief)
        self.assertIn("## You\nYou're Entity1.\nHealth", brief)
        self.assertIn("Money: 5 ", brief)
        self.assertIsNone(self.FORBIDDEN.search(brief))
        theirs = self.rpg("brief", other, as_=False)
        self.assertTrue(theirs.startswith("## Who I am"))
        self.assertIn("## How it begins", theirs)
        self.assertIn("## You\nHealth", theirs, "only a blank person is named under You")
        for pid in order:
            self.take_turn(pid)
        self.rpg("round", "end")
        self.play_round()
        thinkback = self.rpg("memory", "condense", "entity1", as_=False)
        self.assertIn("You are Entity1. \n", thinkback)
        self.assertNotIn("This is the note you keep about yourself", thinkback)
        self.assertIsNone(self.FORBIDDEN.search(thinkback))

    def test_validate_checks_the_cast(self):
        d = "games/dark_lighthouse/cast.json"
        cast = json.loads((self.dir / d).read_text())
        cast[1].update(id="morwen", model="gpt", home="atlantis", inventory=["kipper"], hp=99, attributes={"might": 9},
                       pronouns="Her")
        cast.append(dict(cast[0], extra=1))
        self.write(d, json.dumps(cast))
        out = self.rpg("validate", "--game", "dark_lighthouse", ok=False)
        for problem in ("the id is also a character's", "model must be one of", "home 'atlantis' is not a room",
                        "unknown item 'kipper'", "hp must be a whole number", "attributes must be whole numbers",
                        "the id is used twice", "unknown key 'extra'", "pronouns are written like she/her"):
            self.assertIn(problem, out)
        (self.dir / d).unlink()
        self.rpg("validate", "--game", "dark_lighthouse")  # a world without a cast is valid content
        self.assertIn("has no cast", self.rpg("newgame", ok=False))

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
        self.rpg("coins", "+5", "gift")
        self.assertIn("builds for coins only", self.rpg("pay", "net_loft", "worn_dagger", ok=False))
        self.assertIn("ready in 3 moves", self.rpg("pay", "net_loft"))
        look = self.rpg("look")
        self.assertIn("BEING BUILT: net_loft (The Net-Loft), southwest of harbor_square: ready in 3 moves", look)
        self.assertNotIn("BUILD SPOTS HERE", look)  # the spot is taken
        self.assertNotIn("net_loft", self.save()["run"]["rooms"])  # it doesn't exist yet
        outs = [self.rpg("move", d) for d in ("north", "south", "north")]
        self.assertNotIn("is finished", outs[0] + outs[1])
        self.assertIn("BUILT: The Net-Loft (net_loft) is finished, southwest of Harbor Square, built for Wren (wren) by Morwen", outs[2])
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
        self.assertEqual(s["npc_memory"]["old_tamsin"], {"wren": ["Brought twine for my creels without being asked twice."], "corin": ["Brought twine for my creels without being asked twice."]})
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
        self.rpg("coins", "+5", "gift")
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
        self.assertIn("NOW HERE for Wren: Grukk", out)
        self.assertIn("SIGNAL for Wren", out)
        self.assertNotIn("for Corin", out, "the Gull is out of earshot of both")
        self.assertNotIn("snoring", out, "the lighthouse is out of earshot")
        s = self.save()
        seen = lambda pid: [x["text"][:16] for x in s["players"][pid].get("memory", {}).get("recent", []) if x["kind"] == "seen"]
        self.assertEqual(seen("wren"), ["Heavy bare feet "])  # kept in their memory, not only handed over once
        self.assertEqual(seen("corin"), [])
        self.assertIn("What happened: Heavy bare feet", self.rpg("brief", "wren"))
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

    def test_the_kits_own_games_are_kit_complete_and_the_simulations_world_sim_complete(self):
        for g in GAMES:
            if g in STRICT_GAMES:  # built for the simulation: the strict check, with --sim-complete's own
                self.assertIn("(sim-strict)", self.rpg("validate", "--game", g, "--sim-complete", "--sim-strict"))
            elif g in SIM_GAMES:  # its buyer is a fifth person, past the kit's 3-4; --sim-complete takes the kit check's place
                self.assertIn("(sim-complete)", self.rpg("validate", "--game", g, "--sim-complete"))
            else:
                self.assertIn("(kit-complete)", self.rpg("validate", "--game", g, "--kit-complete"))

    def test_validate_checks_a_game_can_be_played_through(self):
        g = "games/dark_lighthouse"
        road, pell = self.dir / g / "rooms/coast_road.md", self.dir / g / "characters/pell.md"
        road.write_text(road.read_text().replace("east: greywater_bridge", "east: greywater_bridge (if bridge_mended or has_rope)"))
        pell.write_text(pell.read_text().replace("`coins -2 purchase`", "`coins -2 bribe`").replace("`gain honey_cake`", "`gain honey_cak`")
                        .replace("`flag set tongue_salted`", "`flag sett tongue_salted`"))
        out = self.rpg("validate", "--game", "dark_lighthouse", ok=False)
        for want in ("rooms/coast_road.md: a condition uses 'bridge_mended', but nothing in the game sets it",
                     "rooms/coast_road.md: condition 'has_rope': no item 'rope'",
                     "characters/pell.md: `coins -2 bribe`: use coins +N <reason> or coins -N <reason>",
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

def run_in_parallel(jobs):
    """`--jobs N`: the tests split into N parts (at most the machine's cores), each run in a process of its own; every
    test plays in its own temp copy, so they don't meet. Prints any failure in full, then one summary like unittest's."""
    def each(suite):
        for t in suite:
            yield from each(t) if isinstance(t, unittest.TestSuite) else [t]
    ids = [t.id().split(".", 1)[1] for t in each(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))]
    jobs = max(1, min(jobs, os.cpu_count() or 1, len(ids)))
    started = datetime.datetime.now()
    procs = [subprocess.Popen([sys.executable, __file__, "-q", *ids[i::jobs]], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
             for i in range(jobs)]
    failed = [out for out in (p.communicate()[0] for p in procs) if not re.search(r"\nOK\b[^\n]*\s*$", out)]
    for out in failed:
        print(out)
    print("Ran %d tests in %.3fs (%d processes)\n\n%s" % (len(ids), (datetime.datetime.now() - started).total_seconds(), jobs,
                                                          "FAILED (%d of %d parts)" % (len(failed), jobs) if failed else "OK"))
    return 1 if failed else 0


if __name__ == "__main__":
    if "--jobs" in sys.argv:
        i = sys.argv.index("--jobs")
        sys.exit(run_in_parallel(int(sys.argv[i + 1])))
    unittest.main(verbosity=2)
