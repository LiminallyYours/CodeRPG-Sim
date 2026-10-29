#!/usr/bin/env python3
"""CodeRPG rules engine. Every change to state/save.json goes through this script.

Usage: python3 rules/rpg.py <command> [args]   (run with no args for the command list)

Output is plain text meant for the game master to narrate from.
A refused action prints "REFUSED: <reason>" and exits with status 1; state is unchanged.

The world is the active game's authored content (games/<id>/) plus this run's generated content,
kept in the save's `run` section. Both are looked up through ent(); generated entries win nothing
over authored ones (their ids can't collide), they only add.

state/save.json is the active game's save. Other games' saves wait in state/shelf/<game>.json and
are swapped in by `game switch`, so switching loses nothing.
"""
import contextlib
import datetime
import difflib
import hashlib
import io
import itertools
import json
import os
import random
import re
import shutil
import struct
import sys
import uuid
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import content  # noqa: E402
import png  # noqa: E402
import curse  # noqa: E402
import dice  # noqa: E402
import generate  # noqa: E402
import library  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SAVE = ROOT / "state" / "save.json"
SHELF = ROOT / "state" / "shelf"
ACTIVE = ROOT / "state" / "active.json"
METER = ROOT / "state" / "meter.json"
LOG = ROOT / "state" / "log"  # one JSON-lines file per run: the record for study (state/log/<run id>.jsonl)
FORGE = ROOT / "state" / "forge"  # drafts of new worlds, each written by a worldsmith agent (Stage 8)
BALANCE = {}  # the active game's rule numbers; set by choose_game()
SETTINGS = {}  # the owner's switches for the active game (preset + overrides); set by choose_game()
STATE_VERSION = 10  # 10: the simulation fork's save, with a list of players (`players`)
OLDEST_VERSION = 10  # older saves are the original game's, one player each, and aren't upgraded
STATS = ("might", "agility", "wits")
GEN_KINDS = ("extras", "rooms", "items", "characters", "side_quests")
SEED = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
# words for a new run's seed when the player doesn't name one: plain, and no game's in particular
SEED_WORDS = ("amber", "birch", "cinder", "drift", "ember", "fennel", "gale", "hollow", "iris", "juniper",
              "kestrel", "lantern", "moss", "nettle", "onyx", "pebble", "quill", "rook", "sorrel", "thistle",
              "umber", "vale", "willow", "yarrow")


def empty_run():
    return {"id": uuid.uuid4().hex[:12], "variants": {}, "rolls": {}, "clock": None, "moves": 0, "weather": None,
            "rooms": {}, "characters": {}, "items": {}, "quests": {},
            "exits": {}, "placements": {}, "notes": {}, "chronicle": [], "rumors": [],
            "used_encounters": [], "world_turn_due": False, "generated": 0,
            "commissions": {}, "ordering": None}


# Each entry upgrades a save from version N to N+1. The fork starts at version 10 and has none yet.
MIGRATIONS = {}


class Refused(Exception):
    pass


# ---------------------------------------------------------------- who is acting
# The save holds a list of players (`players`, keyed by id, from the game's cast). A command that acts for one of
# them, or reads the world as one of them sees it, needs `--as <id>`; it is refused without. Everything about a player (where they are, what they carry,
# their stats, the map of where they've been, who they've met) is read through me(state); the world is shared.

ACTOR = None  # the id given with --as; set by main()
COMMAND = None  # the command being run; set by main()
REFEREE_COMMANDS = ("round", "run", "log", "brief", "pane", "reply", "narrate", "memory")  # they name the player themselves
NO_ONE_COMMANDS = ("world-brief", "world-turn", "ending")  # also run for no one: between rounds
RECORD_COMMANDS = ("chronicle",)  # the referee's own record: run for no one, at any time, whatever --as says


def no_one(state):
    """True for a world turn run with no --as (between rounds): it reads the shared world, and no one's place in it."""
    return ACTOR is None and COMMAND in NO_ONE_COMMANDS


def actor_id(state):
    """The id of the player this command acts for."""
    players = state["players"]
    if ACTOR is not None:
        if ACTOR not in players:
            raise Refused("no one called %r is playing (players: %s)" % (ACTOR, ", ".join(players)))
        return ACTOR
    raise Refused("say who acts: --as <%s>" % "|".join(players))


def me(state):
    """The acting player's record in the save."""
    return state["players"][actor_id(state)]


class acting:
    """`with acting(pid):` reads the save as player `pid` for a while (the view is drawn for every player)."""
    def __init__(self, pid):
        self.pid = pid

    def __enter__(self):
        global ACTOR
        self.was, ACTOR = ACTOR, self.pid

    def __exit__(self, *exc):
        global ACTOR
        ACTOR = self.was


# ---------------------------------------------------------------- the log: the record for study
# Everything that happens in a run is written to state/log/<run id>.jsonl as it happens, one JSON object per
# line, by the code that made the change: never from anyone's description of events. The save holds where
# things stand; the log holds how they got there.

COIN_REASONS = ("job", "work", "sale", "purchase", "trade", "toll", "order", "reward", "gift", "encounter")


_PENDING = []  # entries made by this command, written with the save, so a refused command leaves none


def log(state, kind, **fields):
    """One entry for the run's log, written when the save is (flush_log). Each carries the round, the acting
    player's place in its order, the player and the move count, then its own fields."""
    run = state["run"]
    pid = ACTOR if ACTOR in state.get("players", {}) else None
    entry = {"kind": kind, "t": datetime.datetime.now().isoformat(timespec="seconds"),
             "round": run.get("round"), "order_position": order_position(run, pid), "player": pid,
             "move": run.get("moves", 0)}
    entry.update(fields)
    _PENDING.append((run["id"], entry))


def flush_log():
    """Write the entries waiting, each to its run's file."""
    if not _PENDING:
        return
    LOG.mkdir(parents=True, exist_ok=True)
    for run_id, entry in _PENDING:
        with (LOG / ("%s.jsonl" % run_id)).open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    del _PENDING[:]


def log_entries(run_id):
    """Every entry of a run's log, in order."""
    path = LOG / ("%s.jsonl" % run_id)
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def order_position(run, pid):
    """Where `pid` stands in this round's order (1 = first), or None outside a round."""
    order = (run.get("round_state") or {}).get("order") or []
    return order.index(pid) + 1 if pid in order else None


def order_asked(state, maker, kind):
    """An order is being placed: give it an id, and log what the player asked for, in their own words this turn."""
    run = state["run"]
    run["order_n"] = run.get("order_n", 0) + 1
    order = "o%d" % run["order_n"]
    turn = me(state).get("turn") or {}
    this_turn = turn.get("round") == run.get("round")
    log(state, "order", order=order, step="asked", what=kind, maker=maker,
        words=turn.get("do") if this_turn else None, journal=turn.get("journal") if this_turn else None)
    return {"maker": maker, "kind": kind, "order": order}


def made_for(state, ident):
    """The player an item or place was made to order for (who paid for it), or None: made for one person, it stays
    made for them in whoever's hands it ends up."""
    com = state["run"]["commissions"].get(ident)
    return (com.get("by") or com.get("ordered_by")) if com and com["status"] == "done" else None


def order_of(state, ident):
    """The order that made this item or place, or None."""
    com = state["run"]["commissions"].get(ident)
    return com.get("order") if com else None


def log_use(state, ident, how):
    """Something a player had made is used, moved, traded or entered."""
    order = order_of(state, ident)
    if order:
        log(state, "order", order=order, step="used", id=ident, how=how)


def change_coins(state, delta, reason, note=None):
    """The one way money moves: the acting player gains or loses `delta`, and the log says why."""
    s = me(state)["stats"]
    s["coins"] += delta
    log(state, "coins", delta=delta, reason=reason, balance=s["coins"], **({"note": note} if note else {}))
    return s["coins"]


def npc_memory_of(state, npc):
    """What `npc` remembers about the acting player (their own list, kept per player)."""
    return state.get("npc_memory", {}).get(npc, {}).get(actor_id(state), [])


def npc_memory_list(state, npc):
    """The same list, created if need be, to add to."""
    return state.setdefault("npc_memory", {}).setdefault(npc, {}).setdefault(actor_id(state), [])


# ---------------------------------------------------------------- which game

def read_json(path):
    """A JSON file's contents, or None if it's missing or unreadable."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_json(path, data):
    """Write atomically, so a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, path)


def active_game():
    """Which game is being played: the save's, else state/active.json's, else the first installed."""
    games = content.list_games()
    if not games:
        raise Refused("no games installed in games/")
    save, active = read_json(SAVE), read_json(ACTIVE)
    for data in (save, active):
        ident = data.get("game") if isinstance(data, dict) else None
        if ident in games:
            return ident
    return games[0]


def choose_game(ident, folder=None):
    """Make `ident` the game this run reads (from `folder` for a draft), with its rule numbers and the owner's switches."""
    global BALANCE, SETTINGS
    content.use_game(ident, folder)
    BALANCE = content.balance()
    try:
        SETTINGS = content.settings()
    except ValueError:
        SETTINGS = dict(content.kit_presets()["normal"], preset="normal")  # validate reports the bad file


# ---------------------------------------------------------------- the meter: what the extras cost
# Baseline play is free: every game-master turn, every rules command, and the authored characters
# speaking through their agents. Only extras beyond the game as written have a price (the game's
# balance.json `meter.prices`): generating something new, a world turn, and later stages' extras. The
# owner's settings give the capacity. It refills each time Claude Code is opened in the folder
# (`meter refill`, from the SessionStart hook). When it can't pay for an extra, that extra doesn't
# happen: nothing new is generated and the world doesn't stir off-screen, and the game as written plays
# on. It lives outside every save, so it carries across games.

def resource():
    return content.look()["resource"]


def meter():
    cap = int(SETTINGS["meter"]["capacity"])
    data = read_json(METER)
    left = data.get("left", cap) if isinstance(data, dict) else cap
    return {"left": max(0, min(cap, int(left))), "capacity": cap}


def price(kind):
    prices = BALANCE["meter"]["prices"]
    if kind not in prices:
        raise Refused("no price for %r (kinds: %s)" % (kind, ", ".join(prices)))
    return int(prices[kind])


def can_pay(kind):
    return meter()["left"] >= price(kind)


def charge(kind):
    """Take the price of one `kind` of action from the meter. It never goes below 0."""
    m = meter()
    left = max(0, m["left"] - price(kind))
    write_json(METER, {"left": left, "session": meter_session()})
    return left


def meter_session():
    """A mark that changes each time the meter is refilled, which happens when Claude Code is opened here: a forge
    started under an older mark lost its worldsmith when Claude Code closed."""
    data = read_json(METER)
    return data.get("session") if isinstance(data, dict) else None


def meter_state(m=None):
    m = m or meter()
    low = m["left"] * 100 <= m["capacity"] * BALANCE["meter"]["low_at_percent"]
    return "spent" if m["left"] == 0 else "low" if low else "ok"


def active_curses(state):
    """The curses on the player now, in id order: each while its `caused_by` holds and its `cured_by` doesn't.
    They follow from flags, so none survives a new game. The owner's `curses.on` switch turns them all off."""
    if not SETTINGS["curses"]["on"]:
        return []
    flags = condition_flags(state)
    out = []
    for c in content.ids("curses"):
        meta = content.load("curses", c)
        if content.condition_holds(meta.get("caused_by"), flags) and not content.condition_holds(meta.get("cured_by"), flags):
            out.append(dict(meta, id=c))
    return out


def cursed_words(state, text):
    """The player's words as they come out under every curse on them, in order."""
    for c in active_curses(state):
        text = curse.apply(c["effect"], text)
    return text


def agents_resting(ident):
    """Why a non-minor character can't speak through its own agent right now (the owner's switches), or None.
    Agents are baseline play, so the meter never silences them."""
    agents = SETTINGS["npc_agents"]
    if not agents["on"]:
        return "the owner has the game master voice every character"
    if not agents["characters"].get(ident, True):
        return "the owner has the game master voice this character"
    return None


# ---------------------------------------------------------------- the world: content + this run

_RUN = empty_run()  # the loaded save's run section; set by load_state and newgame


def ent(kind, ident):
    """One room, character, item or quest, authored or generated, as a dict with `id` and `body`."""
    if content.exists(kind, ident):
        e = content.load(kind, ident)
    elif ident in _RUN.get(kind, {}):
        g = _RUN[kind][ident]
        e = json.loads(json.dumps(g["meta"]))
        e.update(id=ident, body=g.get("body", ""), generated="yes")
    else:
        raise Refused("no %s named %r in content or in this run" % (kind[:-1], ident))
    if kind == "rooms":
        e["exits"] = dict(e.get("exits") or {}, **_RUN.get("exits", {}).get(ident, {}))
        # once: someone the owner kept for good (tools/library.py) may still be placed by this run too
        e["characters"] = list(dict.fromkeys(list(e.get("characters") or []) + list(_RUN.get("placements", {}).get(ident, []))))
    return e


def ent_exists(kind, ident):
    return content.exists(kind, ident) or ident in _RUN.get(kind, {})


def ent_ids(kind):
    return content.ids(kind) + sorted(_RUN.get(kind, {}))


def is_generated(kind, ident):
    return not content.exists(kind, ident) and ident in _RUN.get(kind, {})


def made_by(kind, ident):
    """Who made a run entity: "player" (ordered from a maker or builder), "world" (generated), or None (authored)."""
    if not is_generated(kind, ident):
        return None
    return _RUN[kind][ident]["meta"].get("made_by", "world")


def world():
    return content.load_world()


def policy():
    """What may be generated now: the content allows it and the owner's settings switch it on."""
    gen = world().get("generation") or {}
    owner = SETTINGS["generation"]
    allowed = {k: str(gen.get(k, "no")).lower() in (("yes", "marked", "anywhere") if k == "rooms" else ("yes",)) for k in GEN_KINDS}
    return {k: allowed[k] and owner["on"] and owner["kinds"].get(k, False) for k in GEN_KINDS}


def growth():
    """Where the world may grow new places: "anywhere" (any free way, unless a room says otherwise), "marked"
    (only the directions rooms list in `expand:`), or "no". world.md's `generation: rooms:` sets it; yes = marked."""
    v = str((world().get("generation") or {}).get("rooms", "no")).lower()
    return "anywhere" if v == "anywhere" else "marked" if v in ("yes", "marked") else "no"


# ---------------------------------------------------------------- orders: what the player has made
# A maker is a character whose content gives `makes:` (item tiers) and maybe `accepts:` (material items
# that pay for the work instead of money). The player describes what they want; the world agent shapes
# it within the maker's tiers (`world-brief craft <maker>`, then `generate craft`). It waits as an order
# in `run.commissions` until the player pays (`pay <id>`); then it's theirs, marked made_by: player.
# Prices come from balance.json, never from an agent.

def makes(ident):
    """The item tiers a character makes to order (none for anyone else)."""
    tiers = BALANCE["generation"]["item_tiers"]
    return [t for t in options_of(ent("characters", ident).get("makes") or "") if t in tiers]


def accepts(ident):
    """The items a maker takes as payment instead of money."""
    return options_of(ent("characters", ident).get("accepts") or "")


def builds(ident):
    """Whether a character builds places to order (`builds: yes`)."""
    return str(ent("characters", ident).get("builds", "no")).lower() == "yes"


def buys(ident):
    """What a buyer pays for each item tier (`buys:`), {tier: price}; empty for anyone else."""
    tiers = BALANCE["generation"]["item_tiers"]
    prices = ent("characters", ident).get("buys")
    return {t: p for t, p in prices.items() if t in tiers and isinstance(p, int)} if isinstance(prices, dict) else {}


# ---------------------------------------------------------------- spending: sellers, beds and places to let
# A character may give `sells:` (an item and its price, endless unless "<price>, <n> in stock"): `buy` buys from one
# present. A room may give `bed_price:` (a night's bed, paid when they turn in with `sleep`) and `rent:` ("<price>
# for <n> days", to its `landlord:`, who must be present): the first to pay is its tenant until the days run out,
# sleeps there free, and what they leave there stays theirs, as in a place built for them. Prices are told on
# asking: the seller's or landlord's brief has them, never anyone's pane.
_SELLS = re.compile(r"^(\d+)(?:\s*,\s*(\d+)\s+in stock)?$")
_RENT = re.compile(r"^(\d+)\s+for\s+(\d+)\s+days?$")


def sells(ident):
    """What a seller has (`sells:`), {item: {"price", "stock"}}, stock None for endless; empty for anyone else."""
    out = {}
    for i, v in (ent("characters", ident).get("sells") or {}).items() if isinstance(ent("characters", ident).get("sells"), dict) else ():
        m = _SELLS.match(str(v).strip())
        if m:
            out[i] = {"price": int(m.group(1)), "stock": int(m.group(2)) if m.group(2) else None}
    return out


def stock_left(state, seller, ident):
    """How many of a thing a seller has left this run, or None for endless."""
    first = sells(seller).get(ident, {}).get("stock")
    return None if first is None else state["run"].get("stock", {}).get(seller, {}).get(ident, first)


def rent_of(room):
    """A room's terms to let (`rent:` "<price> for <n> days", `landlord:`), {"price", "days", "landlord"}, or None."""
    m = _RENT.match(str(room.get("rent") or "").strip())
    return {"price": int(m.group(1)), "days": int(m.group(2)), "landlord": room.get("landlord")} if m else None


def let_of(state, room_id):
    """The let on a room now, {"tenant", "until"} (the last day it's theirs), or None."""
    let = state["run"].get("lets", {}).get(room_id)
    return let if let and day_of(state) and day_of(state) <= let["until"] else None


def lets_tick(state):
    """A new day: lets whose last day has gone by end; the tenant knows, and may pay again."""
    out = []
    for room_id, let in list(state["run"].get("lets", {}).items()):
        if day_of(state) > let["until"]:
            del state["run"]["lets"][room_id]
            name = ent("rooms", room_id).get("name", room_id)
            pl = state["players"].get(let["tenant"])
            if pl:
                remember(pl, "seen", phrase("let_ended", place=name), state["run"].get("round") or 0)
            with acting(let["tenant"] if pl else None):
                log(state, "let", room=room_id, step="ended", tenant=let["tenant"])
            out.append("LET ENDS: %s is no longer %s's (their days ran out); they know" % (name, pl["name"] if pl else let["tenant"]))
    return out


def cmd_buy(args):
    """buy <item> [<seller>]: the person buys something a seller here has, at the seller's price."""
    state = load_state()
    require_playing(state)
    ident = args[0]
    sellers = [c for c in characters_here(state) if ident in sells(c)]
    if len(args) > 1:
        if args[1] not in characters_here(state) or ident not in sells(args[1]):
            raise Refused("%s doesn't sell %s here (sellers of it here: %s)" % (args[1], ident, ", ".join(sellers) or "none"))
        seller = args[1]
    elif len(sellers) == 1:
        seller = sellers[0]
    elif sellers:
        raise Refused("say who from: buy <item> <seller> (sellers of it here: %s)" % ", ".join(sellers))
    else:
        raise Refused("nobody here sells %s" % ident)
    price, left, who = sells(seller)[ident]["price"], stock_left(state, seller, ident), ent("characters", seller).get("name", seller)
    if left == 0:
        raise Refused("%s has no %s left" % (who, item(ident).get("name", ident)))
    if me(state)["stats"]["coins"] < price:
        raise Refused("%s costs %d %s, and they have %d" % (item(ident).get("name", ident), price, currency(), me(state)["stats"]["coins"]))
    check_carry(state, ident)
    if left is not None:
        state["run"].setdefault("stock", {}).setdefault(seller, {})[ident] = left - 1
    change_coins(state, -price, "purchase", ident)
    me(state)["inventory"].append(ident)
    log(state, "purchase", item=ident, seller=seller, price=price, left=None if left is None else left - 1)
    save_state(state)
    print("BOUGHT: %s from %s for %d %s. COINS -%d -> %d%s" % (item(ident).get("name", ident), who, price, currency(), price,
          me(state)["stats"]["coins"], "; %d left" % (left - 1) if left is not None else ""))


def cmd_rent(args):
    """rent <room>: the person takes a place to let from its landlord, who is here: theirs for its days."""
    state = load_state()
    require_playing(state)
    room_id = args[0]
    if not ent_exists("rooms", room_id) or not rent_of(ent("rooms", room_id)):
        raise Refused("%s isn't a place to let" % room_id)
    if not has_days():
        raise Refused("a let runs for days, and this world doesn't count them")
    terms, name = rent_of(ent("rooms", room_id)), ent("rooms", room_id).get("name", room_id)
    if terms["landlord"] not in characters_here(state):
        raise Refused("%s's landlord (%s) isn't here" % (name, terms["landlord"]))
    let, pid = let_of(state, room_id), actor_id(state)
    if let and let["tenant"] != pid:
        raise Refused("%s is let to someone else until the end of day %d" % (name, let["until"]))
    if me(state)["stats"]["coins"] < terms["price"]:
        raise Refused("%s is %d %s for %d days, and they have %d" % (name, terms["price"], currency(), terms["days"], me(state)["stats"]["coins"]))
    until = (let["until"] if let else day_of(state) - 1) + terms["days"]  # paid again, it runs on from where it ends
    state["run"].setdefault("lets", {})[room_id] = {"tenant": pid, "until": until}
    change_coins(state, -terms["price"], "purchase", room_id)
    log(state, "let", room=room_id, step="renewed" if let else "taken", tenant=pid, price=terms["price"], until=until,
        landlord=terms["landlord"])
    save_state(state)
    print("RENTED: %s, %s's to the end of day %d, from %s for %d %s. COINS -%d -> %d. They sleep there free, and what "
          "they leave there stays theirs." % (name, me(state)["name"], until, ent("characters", terms["landlord"]).get("name", terms["landlord"]),
                                             terms["price"], currency(), terms["price"], me(state)["stats"]["coins"]))


# ---------------------------------------------------------------- earning: paid work and a buyer
# A room may give `work:` (a stat, a pay range and a DC): a player there can work once per visit, a check
# first, and is paid in coins on a success. A character with `buys:` pays a set price per item tier for
# things made or found (anything with a tier); the world's own things have none, and aren't bought.

def work_of(room, flags=None):
    """A room's paid work as {stat, low, high, dc}, or None: None too when its `if:` doesn't hold under these flags
    (given no flags, the work as written, whatever its condition). Validate has checked its shape."""
    spec = room.get("work")
    if not isinstance(spec, dict):
        return None
    if flags is not None and not content.condition_holds(spec.get("if"), flags):
        return None
    low, _, high = str(spec.get("pay", "")).partition("-")
    return {"stat": spec.get("stat"), "low": int(low), "high": int(high or low), "dc": resolve_dc(spec.get("dc", "normal"))}


_STAGE = re.compile(r"^\s*(\d+)\s*:\s*([a-z][a-z0-9_]*)\s*$")


def project_of(room):
    """A room's shared work (`project:`) as {id, name, stages: [(amount, flag)], until, stat, dc, meal}, or None. Each
    turn someone works there adds to their own count; the work moves on by a turn, or by a success when it gives a
    `dc`; each stage's flag is set (shared) when the work reaches its amount; `until:` closes it."""
    spec = room.get("project")
    if not isinstance(spec, dict) or not spec.get("id"):
        return None
    stages = [(int(m.group(1)), m.group(2)) for m in (_STAGE.match(s) for s in str(spec.get("stages") or "").split(";")) if m]
    return {"id": str(spec["id"]), "name": spec.get("name") or spec["id"], "stages": sorted(stages), "until": spec.get("until"),
            "stat": spec.get("stat", "might"),
            "dc": resolve_dc(spec["dc"]) if str(spec.get("dc")).isdigit() or spec.get("dc") in ("easy", "normal", "hard") else None,
            "meal": str(spec.get("meal", "no")).lower() == "yes"}


def project_rooms():
    """{project id: room id} for every room with shared work."""
    return {project_of(content.load("rooms", r))["id"]: r for r in content.ids("rooms") if project_of(content.load("rooms", r))}


def project_state(state, ident):
    return state["run"].setdefault("projects", {}).setdefault(ident, {"total": 0, "by": {}, "stages": []})


def has_board(room):
    """A place with a notice board (`board: yes`), where people, and the world's off-screen turn, put up notices."""
    return str(room.get("board", "no")).lower() == "yes"


def notices(state, room_id):
    """The notices on a place's board, oldest first: {"text", "by" (a person's id, or None for the world's), "day", "round"}."""
    return state["run"].get("boards", {}).get(room_id, [])


def put_up(state, room_id, text, by):
    """A notice on a place's board; the board keeps only its last few (balance.json world.notices_per_board)."""
    board = state["run"].setdefault("boards", {}).setdefault(room_id, [])
    board.append({"text": text, "by": by, "day": day_of(state), "round": state["run"].get("round", 0)})
    del board[:-int(BALANCE["world"]["notices_per_board"])]


def most_conditions(state, pid):
    """most_<project> for each shared work where this person's count is the highest (ties: all of them)."""
    out = []
    for ident, rec in state["run"].get("projects", {}).items():
        top = max(rec["by"].values() or [0])
        if top and rec["by"].get(pid) == top:
            out.append("most_" + ident)
    return out


def cmd_project(args):
    """project <id>: how a shared work stands, for the referee: the total, the stages reached, each person's count."""
    state = load_state()
    rooms = project_rooms()
    if args[0] not in rooms:
        raise Refused("no shared work called %r (there is: %s)" % (args[0], ", ".join(rooms) or "none"))
    spec, rec = project_of(ent("rooms", rooms[args[0]])), project_state(state, args[0])
    print("PROJECT %s (%s, at %s): %d done; stages %s; %s" % (args[0], spec["name"], ent("rooms", rooms[args[0]]).get("name"), rec["total"],
          ", ".join("%d %s%s" % (n, f, " (reached)" if f in rec["stages"] else "") for n, f in spec["stages"]) or "none",
          "; ".join("%s %d" % (state["players"][p]["name"] if p in state["players"] else p, n) for p, n in
                    sorted(rec["by"].items(), key=lambda kv: -kv[1])) or "nobody has helped yet"))


ORDER_KINDS = {"craft": ("item", "crafting", "makers"), "build": ("room", "building", "builders")}


def why_no_order(state, kind="craft"):
    """Why no maker (craft) or builder (build) takes a new order now: the owner's switches, this run's orders,
    the meter. None when one can be placed."""
    what, switch_name, who = ORDER_KINDS[kind]
    switch = SETTINGS[switch_name]
    if not switch["on"]:
        return "no %s take orders in this game (the owner's settings)" % who
    if sum(1 for c in state["run"]["commissions"].values() if c["kind"] == what) >= int(switch["max_per_run"]):
        return "the %s have taken as much work as they will this run (%d orders)" % (who, int(switch["max_per_run"]))
    if not can_pay(kind):
        return "the %s is spent until the next session, so no new work is taken on" % resource()["name"].lower()
    return None


def order_name(ident, com):
    return com["record"]["meta"]["name"] if "record" in com else item(ident).get("name", ident)


def price_text(com):
    """'3 coins, or in trade: smoked_fish' for an order. Only made items can be paid for in trade."""
    trade = accepts(com["maker"]) if com["kind"] == "item" and ent_exists("characters", com["maker"]) else []
    return "%d %s%s" % (com["price"], currency(), ", or in trade: %s" % ", ".join(trade) if trade else "")


# ---------------------------------------------------------------- where new places can go
# Every room has a square on the map, found by walking the exits from the start room (up and down are drawn
# as north and south, as the mod draws them). A new place may only go where its square is free, so the map
# never overlaps. Build spots (`build:` on a room) are reserved for the player: the world never grows there.

STEP = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0), "up": (0, -1), "down": (0, 1),
        "northeast": (1, -1), "northwest": (-1, -1), "southeast": (1, 1), "southwest": (-1, 1)}
CARDINAL = ("north", "south", "east", "west")


def layout():
    """Every reachable room's map square, from the start room through every exit (open or not)."""
    start = world()["start_room"]
    pos, queue = {start: (0, 0)}, [start]
    taken = {(0, 0)}
    while queue:
        r = queue.pop(0)
        x, y = pos[r]
        for d, target in (ent("rooms", r).get("exits") or {}).items():
            dest = content.split_condition(target)[0]
            if d not in STEP or dest in pos or not ent_exists("rooms", dest):
                continue
            sq = (x + STEP[d][0], y + STEP[d][1])
            if sq in taken:
                continue
            pos[dest] = sq
            taken.add(sq)
            queue.append(dest)
    return pos


def square_of(room_id, d, pos):
    """The map square a new place `d` of this room would take, or None (in and out aren't drawn)."""
    if d not in STEP or room_id not in pos:
        return None
    x, y = pos[room_id]
    return (x + STEP[d][0], y + STEP[d][1])


def reserved_squares(pos):
    """The squares every authored build spot will take: kept free for the player."""
    out = set()
    for r in content.ids("rooms"):
        spots = content.load("rooms", r).get("build")
        for d in (spots if isinstance(spots, dict) else {}):
            sq = square_of(r, d, pos)
            if sq:
                out.add(sq)
    return out


def square_free(room_id, d, pos, keep=frozenset()):
    """Whether a new place `d` of this room would have a map square of its own, not one of `keep`
    (always free for in and out, and for a room the map can't place)."""
    sq = square_of(room_id, d, pos)
    if sq is None:
        return d not in STEP or room_id not in pos
    return sq not in set(pos.values()) and sq not in keep


def room_depth(room):
    """How many generated rooms deep a room is: 0 for authored ones."""
    return int(room.get("depth", 1)) if room.get("generated") else 0


def build_spots(state, room):
    """This room's free build spots, {direction: what could go there}: content lists them, and none has an exit
    or a paid-for building yet. Generated and built rooms have none."""
    spots = room.get("build") if not room.get("generated") else None
    if not isinstance(spots, dict):
        return {}
    busy = {c["direction"] for c in state["run"]["commissions"].values()
            if c["kind"] == "room" and c["room"] == room["id"] and c["status"] != "ordered"}
    return {d: str(t) for d, t in spots.items() if d not in (room.get("exits") or {}) and d not in busy}


# ---------------------------------------------------------------- people with plans: life off-screen
# A major character's content may list what they do when the player isn't with them (`## Plan:` sections).
# Each step sets or clears one of their own flags, and the rooms' conditions do the rest: where they stand,
# whether a door is barred. On a world turn the world agent may pick one open step per character; the rules
# check it's open and apply it. The player learns of it only by its signal: the step's `near:` line when it
# happens in or next to their room, otherwise its `rumor:`. Someone the player is with never acts.

def plan_steps(ident):
    """A character's plan steps (authored major characters only; others have none)."""
    if not content.exists("characters", ident) or is_minor(ident):
        return []
    return [s for s in content.plans(ent("characters", ident)["body"]) if s["step"]]


def where_is(ident, flags):
    """The room a character stands in under these flags, or None."""
    return next((r for r in ent_ids("rooms") if ident in content.visible(ent("rooms", r).get("characters"), flags)), None)


def neighbours(room_id):
    """Rooms joined to this one by an exit either way, open or not: close enough to hear through."""
    out = {content.split_condition(t)[0] for t in (ent("rooms", room_id).get("exits") or {}).values()}
    for r in ent_ids("rooms"):
        if any(content.split_condition(t)[0] == room_id for t in (ent("rooms", r).get("exits") or {}).values()):
            out.add(r)
    return out


def open_steps(state):
    """{character: [steps open now]} for everyone who may act off-screen this world turn."""
    if not (SETTINGS["world_turns"]["on"] and SETTINGS["world_turns"]["plans"]):
        return {}
    flags, here = condition_flags(state), with_anyone(state)
    out = {}
    for c in content.ids("characters"):
        if c in here:
            continue
        steps = [s for s in plan_steps(c) if content.condition_holds(s["when"], flags)]
        if steps:
            out[c] = steps
    return out


def add_signal(state, text, kind="plan"):
    """Something the player notices, for the interface's chime (`view.signals`, the last 3). `kind` says what:
    `plan` (someone close by acted on their plan; the story tells it) or `world` (a new world is ready; also a toast)."""
    run = state["run"]
    run["signal_n"] = run.get("signal_n", 0) + 1
    run.setdefault("signals", []).append({"n": run["signal_n"], "text": text, "move": run["moves"], "kind": kind})
    del run["signals"][:-3]


def playing(state):
    """The ids of the players still playing, in the cast's order."""
    return [pid for pid, pl in state["players"].items() if pl["status"] == "playing"]


def with_anyone(state):
    """Every character in a room with at least one player still playing: no one with company acts off-screen."""
    out = set()
    for pid in playing(state):
        with acting(pid):
            out.update(characters_here(state))
    return out


def sight(state):
    """{player: the characters they can see now}."""
    out = {}
    for pid in playing(state):
        with acting(pid):
            out[pid] = set(characters_here(state))
    return out


def apply_plan(state, who, step):
    """Carry out one plan step. Returns the lines for the game master, or None when it would take someone
    out of a player's sight (then it's undone: whoever a player is with stays). Each player close by notices it
    (it goes into their memory, read on their next turn); further off, it becomes a rumor."""
    flag = step.get("sets") or step.get("clears")
    seen_before = sight(state)
    before = where_is(who, condition_flags(state))
    had = flag in state["flags"]
    if step.get("sets"):
        set_flag(state, flag)
    elif had:
        state["flags"].remove(flag)
    seen_after = sight(state)
    if any(not seen_before[pid] <= seen_after[pid] for pid in seen_before):
        if had and flag not in state["flags"]:
            state["flags"].append(flag)
        elif not had and flag in state["flags"]:
            state["flags"].remove(flag)
        return None
    after = where_is(who, condition_flags(state))
    run, out, heard = state["run"], [], False
    name = ent("characters", who).get("name", who)
    for pid in seen_before:
        pl = state["players"][pid]
        here = pl["location"]
        if any(r and (r == here or here in neighbours(r)) for r in (before, after)):
            heard = True
            remember(pl, "seen", step["near"], run.get("round") or 0)
            out.append("SIGNAL for %s (they notice this close by: one sentence of what they see or hear, woven into "
                       "their next narration; don't explain it): %s" % (pl["name"], step["near"]))
        if after == here and before != here:
            out.append("NOW HERE for %s: %s has just arrived where they are (%s)" % (pl["name"], name, step["does"]))
    if heard:
        add_signal(state, step["near"])
    elif step.get("rumor"):
        run["rumors"].append(step["rumor"])
        del run["rumors"][:-BALANCE["world"]["rumors_kept"]]
    if not out:
        out.append("OFF-SCREEN: someone out of everyone's sight did something; it shows only in the rooms and "
                   "what people say. Don't mention it.")
    return out


# ---------------------------------------------------------------- side scenes: two characters, for fun
# A game may write short scenes for two agent characters together (`scenes/<id>.md`): an argument, a contest.
# When both are in the scene's room and its `when:` holds, `look` says so and the game master shows it starting;
# it begins only if the player takes it up (`scene start`, which charges). While it plays, each character's
# npc-brief carries the premise and their part, and counts the replies up to the owner's cap. `scene end` gives
# the scene's small reward, if the game master says it was earned, and a chronicle line. It changes no story
# flags, plays once per run, and walking out ends it.

def scene(ident):
    return content.load("scenes", ident)


def scene_cast(sc):
    return [str(c) for c in (sc.get("with") or [])]


def scenes_run(state):
    return state["run"].setdefault("scenes", {})


def scene_playing(state):
    """The scene playing now, as (id, its run record), or (None, None)."""
    return next(((i, r) for i, r in scenes_run(state).items() if r["status"] == "playing"), (None, None))


def why_no_scene(state, ident):
    """Why this scene can't start now, or None."""
    sw, sc = SETTINGS["side_scenes"], scene(ident)
    if not sw["on"]:
        return "side scenes are off in this game's settings"
    if any(agents_resting(c) for c in scene_cast(sc)):
        return "one of them speaks through the game master just now, so the scene isn't played"
    if ident in scenes_run(state):
        return "this scene has already played in this run"
    if sum(1 for _ in scenes_run(state)) >= int(sw["max_per_run"]):
        return "this run has had all the side scenes the owner allows (%d)" % int(sw["max_per_run"])
    if scene_playing(state)[0]:
        return "another scene is playing"
    here = characters_here(state)
    if me(state)["location"] != sc.get("where") or not all(c in here for c in scene_cast(sc)):
        return "they aren't both here"
    if not content.condition_holds(sc.get("when"), condition_flags(state)):
        return "the moment isn't right for it"
    if not can_pay("scene"):
        return "the %s is spent until the next session" % resource()["name"].lower()
    return None


def scene_reward(sc):
    """(coins) the scene may give: `reward: coins N`, or 0 for `none`."""
    m = re.fullmatch(r"coins\s+(\d+)", str(sc.get("reward") or "none").strip())
    return int(m.group(1)) if m else 0


def scene_part(ident, who):
    """The premise and this character's part, for their npc-brief while the scene plays."""
    body = dict(content.sections(scene(ident)["body"]))
    return body.get("Premise", ""), body.get(who, "")


def end_scene(state, ident, reward):
    run, sc = state["run"], scene(ident)
    rec = scenes_run(state)[ident]
    rec.update(status="done", ended_at=run["moves"])
    out = ["SCENE ENDED: %s" % sc.get("name", ident)]
    coins = scene_reward(sc) if reward else 0
    if coins:
        change_coins(state, coins, "reward", "scene %s" % ident)
        rec["rewarded"] = coins
        out.append("REWARD: %+d %s -> %d" % (coins, currency(), me(state)["stats"]["coins"]))
    if sc.get("chronicle"):
        run["chronicle"].append(str(sc["chronicle"]))
    return out


def cmd_scene(args):
    """scene start <id> | scene end <id> [reward]: play one of the game's side scenes."""
    state = load_state()
    require_playing(state)
    if len(args) < 2 or args[0] not in ("start", "end"):
        raise Refused("use: scene start <id> | scene end <id> [reward]")
    action, ident = args[0], args[1]
    if not content.exists("scenes", ident):
        raise Refused("no scene named %r in this game" % ident)
    sc = scene(ident)
    if action == "start":
        why = why_no_scene(state, ident)
        if why:
            raise Refused("%s; the moment passes, and nothing comes of it" % why)
        charge("scene")
        scenes_run(state)[ident] = {"status": "playing", "replies": 0, "started_at": state["run"]["moves"]}
        save_state(state)
        cast = [ent("characters", c).get("name", c) for c in scene_cast(sc)]
        print("SCENE STARTED: %s, with %s. Up to %d replies between them in all. For each thing the player says or does, "
              "one reply from each (see gm-turn, Side scenes); each one's npc-brief carries the scene and says when it's "
              "the last reply. End it with `scene end %s` (add `reward` only if its How it ends says it's earned)."
              % (sc.get("name", ident), " and ".join(cast), int(SETTINGS["side_scenes"]["replies"]), ident))
        return
    rec = scenes_run(state).get(ident)
    if not rec or rec["status"] != "playing":
        raise Refused("that scene isn't playing")
    lines = end_scene(state, ident, len(args) > 2 and args[2] == "reward")
    save_state(state)
    print("\n".join(lines))


# ---------------------------------------------------------------- the library: what lasts across runs
# Everything generated or player-made in a run goes into the game's library (rules/library.py, kept in
# state/library/<game>.json, outside every save). A new game brings back the places the player built and
# the people they befriended; the world agent is shown a few fitting entries and may bring one back instead
# of inventing. Only the owner keeps an entry for good or forgets it (tools/library.py).

def lib():
    return library.load(content.game_id())


def lib_save(data):
    library.save(content.game_id(), data)


def lib_limit():
    return int(BALANCE["library"]["max_entries"])


REQUEST_KIND = {"extra": "characters", "character": "characters", "room": "rooms", "item": "items"}


def record_patch(state, request, patch):
    """Put what one generation made into the library: one entry, with what came with it."""
    kind = REQUEST_KIND.get(request)
    if not kind or not patch[kind]:
        return
    ident = next(iter(patch[kind]))
    placed = {i for items in patch["room_items"].values() for i in items}
    bundle = [{"kind": k, "id": i, "record": patch[k][i], "placed": i in placed}
              for k in library.KINDS for i in patch[k] if i != ident]
    attach = None
    if kind == "rooms":
        attach = {"room": me(state)["location"], "direction": next(iter(patch["exits"][me(state)["location"]]))}
    data = lib()
    library.add(data, lib_limit(), ident, kind, "world", patch[kind][ident], bundle, me(state)["location"], attach)
    lib_save(data)


def note_friends(state):
    """People the player befriended by finishing the side quest they gave: the library brings them back in
    later runs, remembering one line (their last memory of the player, or the job done)."""
    run = state["run"]
    done = run.setdefault("befriended", [])
    new = []
    for pid in state["players"]:  # by any player: the quest's flags are the world's
        with acting(pid):
            flags = condition_flags(state)
            new += [(q, rec["meta"].get("giver"), npc_memory_of(state, rec["meta"].get("giver")))
                    for q, rec in run["quests"].items()
                    if rec["meta"].get("giver") in run["characters"] and rec["meta"].get("giver") not in done
                    and rec["meta"].get("giver") not in [g for _, g, _ in new] and quest_view(q, flags)["complete"]]
    if not new:
        return
    data = lib()
    for q, giver, memory in new:
        name = ent("quests", q).get("name", q)
        library.befriend(data, giver, "finished their side quest (%s)" % name, memory[-1] if memory else "Did right by me once: %s." % name)
        done.append(giver)
    lib_save(data)


def carry_over(state):
    """Bring back what lasts from earlier runs: places the player had built (at their build spots, if the
    content still has them) and the people they befriended (where they were, remembering one line). Stats
    come from today's tiers. Returns a line for each."""
    data, run, back = lib(), state["run"], []
    order = sorted(data["entries"].items(), key=lambda kv: kv[1]["kind"] != "rooms")  # places first: friends may live there
    for ident, e in order:
        if e.get("forgotten") or content.exists(e["kind"], ident):
            continue
        if e["kind"] == "rooms" and e["origin"] == "player":
            a = e.get("attach") or {}
            if not content.exists("rooms", a.get("room", "")):
                continue
            parent = content.load("rooms", a["room"])
            if a.get("direction") not in (parent.get("build") or {}) or a["direction"] in (parent.get("exits") or {}):
                continue
            rec = generate.retier("rooms", e["record"], BALANCE["generation"])
            rec["meta"]["carried"] = "yes"
            run["rooms"][ident] = dict(rec, made_at_move=0)
            run["exits"].setdefault(a["room"], {})[a["direction"]] = ident
            back.append("%s (the player's, %s of %s)" % (rec["meta"]["name"], a["direction"], parent.get("name", a["room"])))
        elif e["kind"] == "characters" and e.get("friend"):
            where = e.get("where")
            if not (content.exists("rooms", where or "") or where in run["rooms"]):
                continue
            rec = generate.retier("characters", e["record"], BALANCE["generation"])
            rec["meta"]["carried"] = "yes"
            if e.get("promoted"):  # they still speak for themselves
                rec["meta"].update(minor="no", promoted="yes")
            run["characters"][ident] = dict(rec, made_at_move=0)
            for b in e.get("bundle") or []:  # their wares
                if b["kind"] == "items" and not content.exists("items", b["id"]):
                    run["items"][b["id"]] = dict(generate.retier("items", b["record"], BALANCE["generation"]), made_at_move=0)
            run["placements"].setdefault(where, []).append(ident)
            state["npc_memory"][ident] = {pid: [e["friend"]["line"]] for pid in state["players"]}
            run.setdefault("befriended", []).append(ident)
            back.append("%s (a friend, at %s, remembers: %s)" % (rec["meta"].get("name", ident), where, e["friend"]["line"]))
        else:
            continue
        library.seen(data, ident)
    lib_save(data)
    return back


def refund(amount):
    """Give back part of an extra's price (a world brief answered by reusing a library entry)."""
    m = meter()
    write_json(METER, {"left": min(m["capacity"], m["left"] + amount)})


# ---------------------------------------------------------------- state I/O

def load_state():
    global _RUN
    if not SAVE.is_file():
        raise Refused("no save file. Start a game with /newgame.")
    state = json.loads(SAVE.read_text())
    if state.get("version", 1) < OLDEST_VERSION:
        raise Refused("this save is from the original CodeRPG, with one player, and can't be continued here. Start a new game with /newgame.")
    state = migrate(state)
    _RUN = state["run"]
    if _RUN.get("seed"):
        dice.use_stream(stream_key(state), _RUN.get("dice_n", 0))
    whose = whose_turn(state)
    if whose and ACTOR in state["players"] and ACTOR != whose and COMMAND not in REFEREE_COMMANDS:
        raise Refused("it's %s's turn in round %d, not %s's" % (whose, _RUN["round"], ACTOR))
    return state


def stream_key(state):
    """The run's dice stream: the same game and seed roll the same dice, in the same order."""
    return "%s:%s" % (state["game"], state["run"]["seed"])


def migrate(state):
    v = state.get("version", 1)
    if v > STATE_VERSION:
        raise Refused("save is version %d but this engine only knows up to %d" % (v, STATE_VERSION))
    while v < STATE_VERSION:
        state = MIGRATIONS[v](state)
        v += 1
        state["version"] = v
    return state


def condition_flags(state):
    """The names content conditions are checked against: the shared story flags and the acting player's own
    (the world's `personal_flags`), plus the automatic kinds that are true while they hold: has_<item>
    (carrying it), met_<character> (seen them in a room), and the clock's (time_conditions)."""
    if no_one(state):  # a world turn between rounds: the shared story flags alone, and the time
        return list(state["flags"]) + time_conditions(state)
    return (list(state["flags"]) + list(me(state).get("flags", [])) + ["has_" + i for i in me(state)["inventory"]]
            + ["met_" + c for c in me(state).get("met", [])] + time_conditions(state) + most_conditions(state, actor_id(state)))


def personal_flags():
    """The flags that are each player's own (world.md `personal_flags:`): what a person learns or goes through."""
    return set(options_of(world().get("personal_flags") or []))


def flags_of(state, name):
    """The list a flag lives in: the acting player's own for a personal flag, the shared story flags otherwise."""
    if name not in personal_flags():
        return state["flags"]
    if no_one(state):
        raise Refused("%s is someone's own (personal_flags), so it needs --as <player>" % name)
    return me(state).setdefault("flags", [])


_DONE = re.compile(r"^(.*?)\s*\(done when\s+(.+)\)\s*$")


def quest_view(ident, flags):
    """A quest's journal: objectives done so far, then the current one; later ones stay hidden."""
    q = ent("quests", ident)
    objectives = []
    for line in q.get("objectives") or []:
        m = _DONE.match(str(line))
        text, cond = (m.group(1), m.group(2)) if m else (str(line), None)
        done = cond is not None and content.condition_holds(cond, flags)
        objectives.append({"text": text, "done": done})
    complete = content.condition_holds(q.get("completed_by"), flags) if q.get("completed_by") else False
    failed = not complete and bool(q.get("failed_by")) and content.condition_holds(q.get("failed_by"), flags)
    shown, current_found = [], False
    for o in objectives:
        if o["done"] or complete:
            shown.append(o)
        elif not current_found and not failed:
            shown.append(o)
            current_found = True
    return {"id": ident, "name": q.get("name", ident), "complete": complete, "failed": failed,
            "side": is_generated("quests", ident), "objectives": shown}


AUTOMATIC = ("has_", "met_", "time_", "day_", "after_day_", "most_")  # condition names the code holds true, never set


def has_days():
    """Whether the world's times of day go round and days are counted (world.md `days: yes`)."""
    return str(world().get("days", "no")).lower() == "yes"


def time_steps(state):
    """How many times of day have gone by since the run began: one every `rounds.time_every` ticks."""
    every = int(SETTINGS["rounds"]["time_every"])
    return state["run"]["moves"] // every if every > 0 else 0


def day_of(state):
    """Which day it is (1 on the first), in a world with days; else None."""
    return time_steps(state) // len(world()["times"]) + 1 if has_days() and world().get("times") else None


def time_slug(text):
    """A time of day as a condition names it: `time_` and its words joined with _ ("a quarter to twelve": time_a_quarter_to_twelve)."""
    return "time_" + re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")


def time_conditions(state):
    """The automatic conditions the clock holds true now: time_<the time of day>, and in a world with days, day_<n>
    and after_day_<k> for every day already gone by. Shared by everyone, like the world's own flags."""
    now = time_of_day(state)
    out = [time_slug(now)] if now else []
    day = day_of(state)
    if day:
        out += ["day_%d" % day] + ["after_day_%d" % k for k in range(1, day)]
    return out


def when_text(state):
    """The time of day as people hear it: "morning", or "morning on day 2" in a world with days."""
    now, day = time_of_day(state), day_of(state)
    return phrase("time_on_day", time=now, n=day) if now and day else now


def time_of_day(state):
    times = world().get("times") or []
    clock = state["run"].get("clock")
    if not times:
        return None
    if has_days():  # the times go round, one every rounds.time_every ticks, whatever the quest does
        return times[time_steps(state) % len(times)]
    if not clock:
        every = int(SETTINGS["rounds"]["time_every"])  # with no deadline, time moves on every few ticks and stays at the last
        return times[min(len(times) - 1, state["run"]["moves"] // every)] if every > 0 else times[0]
    return times[min(len(times) - 1, state["run"]["moves"] * len(times) // max(1, clock["total"]))]


def map_room(state, ident):
    """Record a room on the map as it is now: its open exits, where they lead, and how its tile looks."""
    room, flags = ent("rooms", ident), condition_flags(state)
    exits = {}
    for d, target in (room.get("exits") or {}).items():
        dest, cond = content.split_condition(target)
        if content.condition_holds(cond, flags):
            exits[d] = dest
    me(state).setdefault("map", {})[ident] = {
        "name": room.get("name", ident), "exits": exits,
        "terrain": room.get("terrain"), "color": room.get("color"),  # how the map tile looks
        "made_by": made_by("rooms", ident),
        # where those exits lead, by name: the player can see or has been told, even before visiting
        "neighbors": {dest: ent("rooms", dest).get("name", dest) for dest in exits.values() if ent_exists("rooms", dest)},
    }


def refresh_view(state):
    """Derived fields for interfaces (the mod's pane, /map, /inventory, the dashboard), so they never read content.
    Each player's `map` and `met` are history: rooms visited (with the exits open when last there) and characters
    seen. `view` is a snapshot recomputed on every save: `view.players` holds each player's part, and the top level
    is the shared world plus the acting player's part (the first player's when no one is acting)."""
    run = state["run"]
    clock = run.get("clock")
    shared = {
        "game": {"id": state["game"], "title": state["adventure"]},
        "run_label": run_label(state),
        "look": content.look(),
        "time": time_of_day(state),
        "day": day_of(state),
        "weather": run.get("weather"),
        "clock": {"name": clock["name"], "left": clock["left"], "total": clock["total"]} if clock else None,
        "meter": dict(meter(), state=meter_state()),
        "settings": settings_view(),
        "chronicle": run["chronicle"][-BALANCE["world"]["chronicle_lines"]:],
        "rumors": run["rumors"][-BALANCE["world"]["rumors_kept"]:],
        "signals": [{"n": x["n"], "text": x["text"], "kind": x.get("kind", "plan")} for x in run.get("signals", [])],  # what the player noticed close by
    }
    players = {}
    for pid in state["players"]:
        with acting(pid):
            players[pid] = player_view(state)
    main = ACTOR if ACTOR in players else next(iter(players))
    state["view"] = dict(shared, players=players, **players[main])


def player_view(state):
    """The acting player's part of the view."""
    room = room_here(state)
    here = characters_here(state)
    met = me(state).setdefault("met", [])
    met.extend(c for c in here if c not in met)
    flags = condition_flags(state)
    map_room(state, room["id"])
    for entry in me(state)["map"].values():  # rooms visited before neighbors were recorded
        if "neighbors" not in entry:
            entry["neighbors"] = {d: ent("rooms", d).get("name", d) for d in entry["exits"].values() if ent_exists("rooms", d)}

    def who(c):
        ch = ent("characters", c)
        return {"id": c, "name": ch.get("name", c), "role": ch.get("role", ""), "generated": is_generated("characters", c),
                "card": ch.get("card"), "promoted": ch.get("promoted") == "yes"}

    art = content.game_dir() / "art" / ("%s.txt" % room["id"])
    return {
        "name": me(state)["name"],
        "location": room["id"],
        "location_name": room.get("name", room["id"]),
        "location_generated": is_generated("rooms", room["id"]),
        "status": me(state)["status"],
        "stats": dict(me(state)["stats"]),
        "items": [{"id": i, "name": item(i).get("name", i) if ent_exists("items", i) else i, "equipped": i == me(state)["equipped"],
                   "own": made_for(state, i) == actor_id(state)} for i in me(state)["inventory"]],
        "weight": carried_weight(state),
        "carry_limit": carry_limit(state),
        "characters_here": [who(c) for c in here],
        "people": [dict(who(c), here=c in here, memory=npc_memory_of(state, c))
                   for c in met if ent_exists("characters", c)],
        "foes": [dict(who(c), hp=state["npcs"][c]["hp"], max_hp=state["npcs"][c]["max_hp"])
                 for c in here if c in state["npcs"] and state["npcs"][c]["hp"] > 0],  # fought and still standing
        "quests": [quest_view(q, flags) for q in ent_ids("quests")],  # ids come from files that exist
        "art": art.read_text(encoding="utf-8").rstrip("\n") if art.is_file() else None,
        "picture": picture_view(state, room),
        "curses": [{"id": c["id"], "name": c.get("name", c["id"]), "effect": c["effect"]} for c in active_curses(state)],
    }


KIT_ART = Path(__file__).resolve().parent / "art" / "terrain"


def terrain_pictures(folder, terrain):
    """A terrain's pictures in a folder, `<terrain>.png` and `<terrain>-<n>.png`, in name order."""
    if not terrain or not folder.is_dir():
        return []
    return sorted(p for p in folder.glob("*.png") if p.stem == terrain or re.fullmatch(re.escape(terrain) + r"-\d+", p.stem))


def picture_path(room):
    """The room's picture: its own (`art/<room>.png`), else its terrain's from the game (`art/terrain/`), else from
    the kit (`rules/art/terrain/`), the variant picked by a stable hash of the room's id so a room always looks the
    same; else None. Generated and forged rooms go through the same chain."""
    own = content.game_dir() / "art" / ("%s.png" % room["id"])
    if own.is_file():
        return own
    for folder in (content.game_dir() / "art" / "terrain", KIT_ART):
        found = terrain_pictures(folder, room.get("terrain"))
        if found:
            return found[zlib.crc32(room["id"].encode("utf-8")) % len(found)]
    return None


def picture_view(state, room):
    """The room's picture as the margin draws it: the mosaic (44 x 28 pixels, base64 of r, g, b bytes), decoded
    once and carried over from the last save while the file is unchanged. None when there's no picture."""
    path = picture_path(room)
    if path is None:
        return None
    st = path.stat()
    try:
        source = path.relative_to(ROOT).as_posix()
    except ValueError:
        source = str(path)
    stamp = "%d:%d" % (st.st_size, st.st_mtime_ns)
    old = (state.get("view") or {}).get("picture") or {}
    if old.get("source") == source and old.get("stamp") == stamp:
        return old
    try:
        rgb = png.mosaic(path.read_bytes())
    except (ValueError, KeyError, IndexError, zlib.error, struct.error):
        return None  # validate says why
    return {"source": source, "stamp": stamp, "width": png.MOSAIC_W, "height": png.MOSAIC_H, "rgb": rgb}


def settings_view():
    """The owner's switches and what each action costs, as /budget shows them."""
    agents, turns, gen = SETTINGS["npc_agents"], SETTINGS["world_turns"], SETTINGS["generation"]
    return {
        "preset": SETTINGS["preset"],
        "capacity": SETTINGS["meter"]["capacity"],
        "prices": dict(BALANCE["meter"]["prices"]),
        "npc_agents": {"on": agents["on"], "lines_per_exchange": agents["lines_per_exchange"],
                       "off_for": sorted(c for c, on in agents["characters"].items() if not on)},
        "world_turns": {"on": turns["on"], "every_moves": turns["every_moves"], "plans": turns["plans"]},
        "generation": {"on": gen["on"], "max_per_run": gen["max_per_run"], "kinds": [k for k, on in policy().items() if on]},
        "crafting": {"on": SETTINGS["crafting"]["on"], "max_per_run": SETTINGS["crafting"]["max_per_run"]},
        "building": {"on": SETTINGS["building"]["on"], "max_per_run": SETTINGS["building"]["max_per_run"]},
        "promotion": {k: SETTINGS["promotion"][k] for k in ("on", "max_per_run", "after_conversations")},
        "side_scenes": {k: SETTINGS["side_scenes"][k] for k in ("on", "max_per_run", "replies")},
        "new_worlds": {"on": SETTINGS["new_worlds"]["on"]},
    }


def run_label(state):
    """'2026-10-21 · seed ember-4821' or '2026-10-21 · daily world': what the title card says about this run."""
    run = state["run"]
    if not run.get("seed"):
        return None
    return "%s · %s" % (run.get("started", "?"), "daily world" if run.get("daily") else "seed %s" % run["seed"])


def save_state(state):
    if dice.position() is not None:
        state["run"]["dice_n"] = dice.position()
    note_friends(state)
    refresh_view(state)
    write_json(SAVE, state)
    flush_log()


def require_playing(state):
    if me(state)["status"] != "playing":
        raise Refused("the game is over (%s). Start again with /newgame." % me(state)["status"])


# ---------------------------------------------------------------- helpers

def item(ident):
    return ent("items", ident)


def carried_weight(state):
    return sum(int(item(i).get("weight", 0)) for i in me(state)["inventory"] if ent_exists("items", i))


def carry_limit(state):
    return BALANCE["carry_base"] + BALANCE["carry_per_might"] * stat(state, actor_id(state), "might")


def check_carry(state, ident):
    w = carried_weight(state) + int(item(ident).get("weight", 0))
    if w > carry_limit(state):
        raise Refused("too heavy: carrying %s would make %d, limit is %d. Drop something first."
                      % (ident, w, carry_limit(state)))


def room_here(state):
    return ent("rooms", me(state)["location"])


def characters_here(state):
    """Who is in the player's room. A generated character drops out once defeated (authored ones say so in
    their room's conditions), and anyone whose file has gone missing is skipped rather than breaking the save."""
    flags = condition_flags(state)
    return [c for c in content.visible(room_here(state).get("characters"), flags)
            if ent_exists("characters", c) and not (is_generated("characters", c) and "%s_defeated" % c in flags)]


def players_here(state):
    """The players in the acting player's room who are still playing: the acting player first, then the cast's order."""
    here, me_id = me(state)["location"], actor_id(state)
    return [me_id] + [pid for pid, pl in state["players"].items()
                      if pid != me_id and pl["location"] == here and pl["status"] == "playing"]


def overhear(state):
    """The acting player hears the talk going around when they're among the world's people: every rumor they
    haven't heard yet joins what they have. Alone, or with only other players, they hear nothing new."""
    if not characters_here(state):
        return False
    kept = BALANCE["world"]["rumors_kept"]
    heard = me(state).setdefault("heard", [])
    new = [r for r in state["run"]["rumors"][-kept:] if r not in heard]
    heard.extend(new)
    del heard[:-kept]
    return bool(new)


def is_minor(ident):
    return str(ent("characters", ident).get("minor", "no")).lower() == "yes"


def stat_label(stat):
    """How this game names a stat: 'Might', or 'Grit (might)' when it renames one."""
    label = content.look()["stat_labels"].get(stat, stat.capitalize())
    return label if label.lower() == stat else "%s (%s)" % (label, stat)


def currency():
    return content.look().get("currency", "coins")


def player_defense(state):
    return BALANCE["player_defense_base"] + stat(state, actor_id(state), "agility")


def set_flag(state, name):
    flags = flags_of(state, name)
    if name not in flags:
        flags.append(name)


def flags_line(state):
    """The shared story flags, then the acting player's own."""
    own = [] if no_one(state) else me(state).get("flags", [])
    return (", ".join(state["flags"]) or "none") + ("; %s's own: %s" % (me(state)["name"], ", ".join(own)) if own else "")


def hp_line(state):
    s = me(state)["stats"]
    return "HP %d/%d" % (s["hp"], s["max_hp"])


def damage_player(state, amount):
    s = me(state)["stats"]
    s["hp"] = max(0, s["hp"] - amount)
    if s["hp"] == 0:
        me(state)["status"] = "defeated"
        return "PLAYER DEFEATED (HP 0). The game is over; /newgame to start again."
    return "Player " + hp_line(state)


def resolve_dc(text):
    if str(text).isdigit():
        return int(text)
    if text in BALANCE["dc"]:
        return BALANCE["dc"][text]
    raise Refused("DC must be a number or one of %s" % ", ".join(BALANCE["dc"]))


def d20_test(mod, target):
    """Roll the check die + mod against a target number. Natural 20 always passes, natural 1 always fails."""
    total, faces, _ = dice.roll(BALANCE["check_die"])
    nat = faces[0]
    total += mod
    ok = nat == 20 or (nat != 1 and total >= target)
    note = " (natural 20)" if nat == 20 else " (natural 1)" if nat == 1 else ""
    return ok, nat, total, note


def pick(options):
    """One of `options`, chosen by a die roll."""
    return options[dice.roll("1d%d" % len(options))[0] - 1]


def options_of(value):
    """A comma-separated string or a YAML list, as a list of non-empty strings."""
    parts = value if isinstance(value, list) else str(value or "").split(",")
    return [str(x).strip() for x in parts if str(x).strip()]


def moves_text(n):
    return "%d move%s" % (n, "" if n == 1 else "s")


def unused_expansions(room):
    """The directions the world may grow a new place in from this room, by the game's `growth()`:
    - marked: the authored room's `expand:` directions;
    - anywhere: the room's `expand:` directions if it lists any, else north, south, east and west; `expand: no`
      opts out. Generated rooms grow too, until `generation.max_depth` rooms deep.
    Never through an exit, a build spot, or onto a map square that's already taken."""
    mode, raw = growth(), room.get("expand")
    listed = [] if str(raw).strip().lower() in ("no", "none") else options_of(raw or "")
    if mode == "no":
        return []
    if room.get("generated"):
        if mode != "anywhere" or room_depth(room) >= int(BALANCE["generation"]["max_depth"]):
            return []
        dirs = list(CARDINAL)
    elif mode == "marked":
        dirs = listed
    else:
        dirs = listed if raw is not None else list(CARDINAL)
    pos = layout()
    keep = reserved_squares(pos)
    return [d for d in dirs if d not in (room.get("exits") or {}) and square_free(room["id"], d, pos, keep)]


def short_line(text, what):
    text = " ".join(text.split())
    limit = BALANCE["world"]["text_line_chars"]
    if not text:
        raise Refused("usage: %s <one short line>" % what)
    if len(text) > limit:
        raise Refused("%s lines must be at most %d characters (got %d)" % (what, limit, len(text)))
    return text


# ---------------------------------------------------------------- encounters and the clock

_EFFECT = re.compile(r"\(effect:\s*([^)]+)\)")


def apply_effect(state, effect):
    """Apply one encounter effect: coins ±N, gain <item>, hurt <dice>, heal <dice>, flag <name>, none."""
    words = effect.split()
    if not words or words[0] == "none":
        return None
    verb, arg = words[0], " ".join(words[1:])
    s = me(state)["stats"]
    if verb == "coins":
        delta = max(int(arg), -s["coins"])
        if delta == 0:
            return "COINS: nothing to take, the purse is empty"
        change_coins(state, delta, "encounter")
        return "COINS %+d -> %d" % (delta, s["coins"])
    if verb == "gain":
        try:
            check_carry(state, arg)
        except Refused:
            return "GAIN %s refused: too heavy to carry" % arg
        me(state)["inventory"].append(arg)
        return "GAINED: %s" % arg
    if verb == "hurt":
        # a random event can wound but never kill: it leaves at least 1 HP
        total, faces, mod = dice.roll(arg)
        dealt = max(0, min(total, s["hp"] - 1))
        held = "" if dealt == total else ", held to %d" % dealt
        return "HURT %s%s. %s" % (dice.describe(arg, total, faces, mod), held, damage_player(state, dealt))
    if verb == "heal":
        total, faces, mod = dice.roll(arg)
        before = s["hp"]
        s["hp"] = min(s["max_hp"], s["hp"] + max(0, total))
        return "HEAL %s; healed %d. %s" % (dice.describe(arg, total, faces, mod), s["hp"] - before, hp_line(state))
    if verb == "flag":
        set_flag(state, arg)
        return "FLAG set %s" % arg
    raise Refused("unknown encounter effect %r" % effect)


def roll_encounter(state, room):
    """On entering a room with an encounter table, maybe something happens. Code decides, content describes."""
    table_id = room.get("encounters")
    if not table_id:
        return []
    table = content.load("tables", table_id)
    hits, sides = [int(x) for x in re.findall(r"\d+", str(table.get("chance", "1 in 6")))[:2]]
    roll = dice.roll("1d%d" % sides)[0]
    if roll > hits:
        return []
    used = state["run"]["used_encounters"]
    entries = [(i, e) for i, e in enumerate(table.get("entries") or [])
               if not ("(once)" in e and "%s:%d" % (table_id, i) in used)]
    if not entries:
        return []
    i, entry = pick(entries)
    if "(once)" in entry:
        used.append("%s:%d" % (table_id, i))
    text = _EFFECT.sub("", entry).replace("(once)", "").strip()
    out = ["ENCOUNTER: %s" % text]
    m = _EFFECT.search(entry)
    if m:
        result = apply_effect(state, m.group(1).strip())
        if result:
            out.append("  effect: %s" % result)
    return out


def by_rounds():
    """Whether the world's clock moves once per round (the simulation) rather than once per move."""
    return SETTINGS["rounds"]["clock"] == "round"


def ticks_text(n):
    """A count of the world clock's ticks, in what it counts: rounds in the simulation, moves otherwise."""
    return "%d round%s" % (n, "" if n == 1 else "s") if by_rounds() else moves_text(n)


def tick_move(state):
    """Each tick passes time: the clock runs down and, every few ticks, the world takes a turn. A tick is a move,
    or a round when the owner's `rounds.clock` says so; `run.moves` counts them."""
    run, out = state["run"], []
    before = time_steps(state)
    run["moves"] += 1
    if time_steps(state) != before:  # a time of day has gone by: a night slept or not, a day eaten in or not
        out += needs_tick(state, before)
        if has_days() and time_steps(state) % len(world()["times"]) == 0:
            out += lets_tick(state)
    clock = run.get("clock")
    if clock and clock["left"] > 0:
        clock["left"] -= 1
        if clock["left"] == 0:
            set_flag(state, clock["flag"])
            out.append("CLOCK: %s. Flag set: %s" % (clock["name"], clock["flag"]))
            if clock.get("also_flag") and content.condition_holds(clock.get("also_if"), condition_flags(state)):
                set_flag(state, clock["also_flag"])
                out.append("CLOCK: and since %s, flag set: %s" % (clock["also_if"], clock["also_flag"]))
        elif clock["left"] <= 3:
            out.append("CLOCK: %s in %s" % (clock["name"], ticks_text(clock["left"])))
    out += timed_events(state)
    if run["moves"] % BALANCE["world"]["weather_every_moves"] == 0:
        weathers = world().get("weather") or []
        if weathers:
            run["weather"] = pick(weathers)
    for ident, com in run["commissions"].items():
        if com["kind"] == "room" and com["status"] == "building" and run["moves"] >= com["ready_at"]:
            out.append(finish_building(state, ident, com))
    turns = SETTINGS["world_turns"]
    if turns["on"] and run["moves"] % max(1, int(turns["every_moves"])) == 0 and can_pay("world_turn"):
        run["world_turn_due"] = True
        out.append("WORLD TURN DUE: run `tools/voice.py world turn`, then `world-turn` on what it saved (see gm-turn)")
    return out


NEEDS = ("food", "sleep")
SLEEP_PLACES = ("bed", "rough")


def world_needs():
    """The needs people have in this world (world.md `needs:`), when the owner's `needs.on` allows: only in a world
    with days, since food is daily and sleep nightly."""
    if not SETTINGS["needs"]["on"] or not has_days():
        return []
    return [n for n in options_of(world().get("needs") or []) if n in NEEDS]


def needs_of(pl):
    """A person's needs as they stand: `ate` (today), `unfed` (whole days gone by without food), `slept` (how, this
    night: bed, rough or None), `sleep` (rested, tired or exhausted) and `sleepless` (nights in a row without any)."""
    return pl.setdefault("needs", {"ate": False, "unfed": 0, "slept": None, "sleep": "rested", "sleepless": 0})


def food_state(pl):
    """fed, due (not yet today), hungry or weak."""
    n, b = needs_of(pl), BALANCE["needs"]
    if n["unfed"] >= b["weak_after_days"]:
        return "weak"
    if n["unfed"] >= b["hungry_after_days"]:
        return "hungry"
    return "fed" if n["ate"] else "due"


def stat(state, pid, k):
    """A person's attribute as it stands: weak from hunger takes from their Might (balance.json needs.weak_might)."""
    pl = state["players"][pid]
    weak = "food" in world_needs() and k == "might" and food_state(pl) == "weak"
    return pl["stats"][k] + (BALANCE["needs"]["weak_might"] if weak else 0)


def attempt_mod(state, pid, k):
    """What a person adds to a d20 for an attempt with an attribute: the attribute as it stands, and less when tired
    (needs.tired_checks) or worn out (needs.exhausted_checks as well): everything is harder."""
    mod = stat(state, pid, k)
    if "sleep" in world_needs():
        sleep, b = needs_of(state["players"][pid])["sleep"], BALANCE["needs"]
        mod += {"tired": b["tired_checks"], "exhausted": b["tired_checks"] + b["exhausted_checks"]}.get(sleep, 0)
    return mod


def needs_tick(state, before):
    """A time of day has gone by. When it was the world's time for sleep (world.md `sleep_at:`), each person slept in
    a bed (rested), rough (tired, but spared worse) or not at all (tired, and worn out after needs.exhausted_after_nights
    such nights in a row); when a new day begins, each who didn't eat the day before goes a day further unfed."""
    needs, out = world_needs(), []
    if not needs:
        return out
    times = world()["times"]  # a world with needs has days, so it has times of day (validate)
    was, b = times[before % len(times)], BALANCE["needs"]
    for pid, pl in state["players"].items():
        if pl["status"] != "playing":
            continue
        n, changed = needs_of(pl), []
        if "sleep" in needs and was == world().get("sleep_at"):
            old = n["sleep"]
            n["sleepless"] = 0 if n["slept"] else n["sleepless"] + 1
            n["sleep"] = "rested" if n["slept"] == "bed" else "exhausted" if n["sleepless"] >= b["exhausted_after_nights"] else "tired"
            n["slept"] = None
            pl.pop("asleep", None)  # the night has gone by: they're awake for the morning
            if n["sleep"] != old:
                changed.append(("sleep", n["sleep"]))
        if "food" in needs and time_steps(state) % len(times) == 0:  # a new day
            old = food_state(pl)
            n["unfed"] = 0 if n["ate"] else n["unfed"] + 1
            n["ate"] = False
            if food_state(pl) != old and food_state(pl) in ("hungry", "weak"):
                changed.append(("food", food_state(pl)))
        for need, now in changed:
            with acting(pid):
                log(state, "need", need=need, now=now)
            out.append("NEED: %s (%s) is %s now" % (pl["name"], pid, now))
    return out


def met(state, need, how, by):
    """`need` met for the acting person: food eaten (how: what), sleep had (how: bed or rough), by `eat`, `sleep` or
    the content (`meet`)."""
    n = needs_of(me(state))
    if need == "food":
        n["ate"], n["unfed"] = True, 0  # fed: hunger and weakness end at once
    else:
        n["slept"] = how
        me(state)["asleep"] = True  # asleep till the night has gone by: not asked, seeing and hearing nothing
    log(state, "need", need=need, met=how, by=by)


def require_need(need):
    if need not in world_needs():
        raise Refused("nobody here needs %s: this world has no such need, or needs are off (needs.on)" % (
            "to eat" if need == "food" else "to sleep"))


def bed_times():
    """When a person may go to bed: the world's time for sleep (`sleep_at:`), and the time of day just before it;
    gone to bed early, they sleep through the time for sleep."""
    times, at = world()["times"], world().get("sleep_at")
    return [times[times.index(at) - 1], at] if len(times) > 1 else [at]


def awake(state, pids):
    """Those of `pids` who aren't asleep: a sleeper sees and hears nothing till morning."""
    return [p for p in pids if not state["players"][p].get("asleep")]


def require_sleep_time(state):
    if time_of_day(state) not in bed_times():
        raise Refused("it isn't time for bed (that's %s); it's %s" % (" or ".join(bed_times()), time_of_day(state)))
    if needs_of(me(state))["slept"]:
        raise Refused("they've already slept this night (%s)" % needs_of(me(state))["slept"])


def cmd_eat(args):
    """eat <item>: the person eats something they carry that's food (`food: yes`): it's gone, and they're fed."""
    state = load_state()
    require_playing(state)
    require_need("food")
    ident = args[0]
    if ident not in me(state)["inventory"]:
        raise Refused("they aren't carrying %s" % ident)
    if str(item(ident).get("food", "no")).lower() != "yes":
        raise Refused("%s isn't food" % item(ident).get("name", ident))
    remove_from_inventory(state, ident)
    log_use(state, ident, "eaten")
    met(state, "food", ident, "eat")
    save_state(state)
    print("ATE: %s. They're fed: hunger and weakness end now; they need food again tomorrow." % item(ident).get("name", ident))


def cmd_sleep(args):
    """sleep: the person sleeps where they are, at the world's time for sleep or the time just before it (then they
    sleep through it), in a place for it (a room's `sleep:` bed, or rough). Asleep, they aren't asked again, and see
    and hear nothing, till the night has gone by. Logged; how they slept shows once the night has gone by."""
    state = load_state()
    require_playing(state)
    require_need("sleep")
    require_sleep_time(state)
    place = str(room_here(state).get("sleep") or "").lower()
    if place not in SLEEP_PLACES:
        raise Refused("there's nowhere to sleep here (%s); somewhere with a bed, or rough" % room_here(state).get("name", ""))
    room, pl, paid = room_here(state), me(state), ""
    price = room.get("bed_price") if isinstance(room.get("bed_price"), int) else 0
    if let_of(state, room["id"]) and let_of(state, room["id"])["tenant"] == actor_id(state):
        paid = " (their own, while the let lasts)"
    elif pl.get("paid_beds", {}).get(room["id"]):
        pl["paid_beds"][room["id"]] -= 1
        paid = " (a night already paid for)"
    elif price:
        if pl["stats"]["coins"] < price:
            raise Refused("a bed here is %d %s a night, and they have %d" % (price, currency(), pl["stats"]["coins"]))
        change_coins(state, -price, "purchase", "a night's bed at %s" % room["id"])
        paid = " for %d %s (COINS -%d -> %d)" % (price, currency(), price, pl["stats"]["coins"])
    elif rent_of(room):  # a place to let with no price for a night: only its tenant's bed
        let = let_of(state, room["id"])
        raise Refused("%s isn't theirs to sleep in: it's %s" % (room.get("name", room["id"]), "let to someone else until the end of day %d"
                      % let["until"] if let else "to let, and only whoever takes it (`rent`) sleeps there"))
    met(state, "sleep", place, "sleep")
    save_state(state)
    print("SLEPT: %s, %s%s. They're asleep now, not asked again till morning; when the night has gone by they'll be %s." % (
        room.get("name", ""), "in a bed" if place == "bed" else "rough", paid, "rested" if place == "bed" else "tired, though spared worse"))


def cmd_meet(args):
    """meet food | meet sleep [bed|rough]: a need met as the content says (a supper at the inn, a meal for a day's
    help), for what `eat` and `sleep` don't cover. Run only when the content says so, as with flags."""
    state = load_state()
    require_playing(state)
    need = args[0]
    if need not in NEEDS:
        raise Refused("meet food | meet sleep [bed|rough]")
    require_need(need)
    if need == "sleep":
        how = args[1] if len(args) > 1 else "bed"
        if how not in SLEEP_PLACES:
            raise Refused("sleep is bed or rough")
        require_sleep_time(state)
    else:
        how = "content"
    met(state, need, how, "content")
    save_state(state)
    print("MET: %s (%s), as the content says." % (need, how))


def needs_words(state, pid):
    """Where a person's needs stand, in words (brief.md), never numbers: what they read under What you're working on."""
    pl, needs, out = state["players"][pid], world_needs(), []
    if "food" in needs:
        out.append(phrase("food_" + food_state(pl)))
    if "sleep" in needs:
        n = needs_of(pl)
        if n["slept"]:
            out.append(phrase("sleep_slept"))
        elif time_of_day(state) == world().get("sleep_at"):
            out.append(phrase("sleep_time"))
        out.append(phrase("sleep_" + n["sleep"]))
    return out


_WHEN = re.compile(r"^day\s+(\d+)\s*,\s*(.+?)\s*$", re.I)


def when_of(text):
    """`day 3, night` -> (3, "night"), or None."""
    m = _WHEN.match(str(text or ""))
    return (int(m.group(1)), m.group(2)) if m else None


def timed_events(state):
    """world.md's `## At:` sections whose day and time have just come: each happens once, for everyone, if its
    `if:` holds then (else it never does). Its flag is shared; what everyone notices goes into every memory, as a
    sign of the world moving does; its rumor into the talk going around."""
    run, out = state["run"], []
    if not has_days():
        return out
    now, fired = (day_of(state), time_of_day(state)), run.setdefault("fired", [])
    for ev in content.timed(world()["body"]):
        if ev["id"] in fired or when_of(ev.get("when")) != now:
            continue
        fired.append(ev["id"])  # its time has come, whether or not it happens: it never comes again
        holds = content.condition_holds(ev.get("if"), list(state["flags"]) + time_conditions(state))
        with acting(None):
            log(state, "event", id=ev["id"], when=ev["when"], happened=holds, sets=ev.get("sets"), seen=ev.get("seen"), rumor=ev.get("rumor"))
        if not holds:
            out.append("AT %s (%s): not, since %s doesn't hold; nothing happens" % (ev["id"], ev["when"], ev["if"]))
            continue
        if ev.get("sets"):
            set_flag(state, ev["sets"])
        for pl in state["players"].values():
            if ev.get("seen") and pl["status"] == "playing":
                remember(pl, "seen", ev["seen"], run.get("round") or 0)
        if ev.get("rumor"):
            run["rumors"].append(ev["rumor"])
            del run["rumors"][:-BALANCE["world"]["rumors_kept"]]
        out.append("AT %s (%s):%s%s nothing for you to do: everyone playing has noticed it (it's in their memory), "
                   "and the world follows the flag" % (ev["id"], ev["when"], " flag set: %s;" % ev["sets"] if ev.get("sets") else "",
                                                      " %r;" % ev["seen"] if ev.get("seen") else ""))
    return out


def finish_building(state, ident, com):
    """A paid-for building is done: the place joins the world, with a way to it from where it was ordered.
    People hear of it, so they start using it."""
    run = state["run"]
    record = com.pop("record")
    record["meta"].update(owner=com.get("by"), use="stash")  # phase 1: every built place is its owner's stash
    run["rooms"][ident] = dict(record, made_at_move=run["moves"])
    with acting(com.get("by") if com.get("by") in state["players"] else ACTOR):
        log(state, "order", order=com.get("order"), step="delivered", id=ident)
    run["exits"].setdefault(com["room"], {})[com["direction"]] = ident
    com["status"] = "done"
    owner = com.get("by")
    if owner in state["players"] and com["room"] in state["players"][owner].get("map", {}):
        with acting(owner):  # the player had it built, so it's on their map at once, wherever they are
            map_room(state, com["room"])
    name, where = record["meta"]["name"], ent("rooms", com["room"]).get("name", com["room"])
    maker = ent("characters", com["maker"]).get("name", com["maker"])
    if owner in state["players"]:  # they hear of it, whether or not the story tells them (as signals go to memory)
        line = phrase("finished", place=name, direction=com["direction"], where=where, builder=maker)
        remember(state["players"][owner], "seen", line, run.get("round") or 0)
        keep(state["players"][owner], line, run.get("round") or 0)
    run["rumors"].append(phrase("finished_rumor", place=name, direction=com["direction"], where=where))
    del run["rumors"][:-BALANCE["world"]["rumors_kept"]]
    data = lib()
    library.add(data, lib_limit(), ident, "rooms", "player", record, where=com["room"],
                attach={"room": com["room"], "direction": com["direction"]}, worth_keeping="built by the player")
    lib_save(data)
    whose = "%s (%s)" % (state["players"][owner]["name"], owner) if owner in state["players"] else "the player"
    return ("BUILT: %s (%s) is finished, %s of %s, built for %s by %s. It's open now; describe it when they next see "
            "it, or tell it as news if someone would." % (name, ident, com["direction"], where, whose, maker))


# ---------------------------------------------------------------- commands

def cmd_newgame(args):
    """newgame [seed | daily]: a fresh run. The same seed rolls the same run in this game for anyone."""
    global _RUN
    today = datetime.date.today().isoformat()
    want = args[0].lower() if args else None
    if want == "daily":
        seed = today
    elif want:
        if not SEED.match(want):
            raise Refused("a seed is 1-40 letters, digits, dashes or underscores, or 'daily' for today's world")
        seed = want
    else:
        seed = "%s-%04d" % (dice.fresh_choice(SEED_WORDS), dice.fresh_choice(range(10000)))
    cast = content.cast()
    if not cast:
        raise Refused("this world has no cast (games/%s/cast.json): nobody to play it" % content.game_id())
    dice.use_stream("%s:%s" % (content.game_id(), seed), 0)
    w = world()
    run = empty_run()
    run.update(seed=seed, started=today, daily=want == "daily", dice_n=0)
    _RUN = run
    players = {p["id"]: cast_player(p, w, run) for p in cast}
    flags = list(w.get("flags") or [])
    for name, opts in (w.get("variants") or {}).items():
        choice = pick(options_of(opts))
        run["variants"][name] = choice
        flags.append(choice)
    if w.get("clock") and SETTINGS["clock"]["on"]:  # the owner's switch: off, the deadline never comes
        c = w["clock"]
        total = max(1, dice.roll(c["moves"])[0])
        run["clock"] = {"name": c["name"], "flag": c["flag"], "total": total, "left": total,
                        "also_if": c.get("also_if"), "also_flag": c.get("also_flag")}
    if w.get("weather"):
        run["weather"] = pick(w["weather"])
    state = {
        "version": STATE_VERSION,
        "game": content.game_id(),
        "adventure": w.get("title", "Untitled"),
        "players": players,
        "flags": flags,
        "room_items": {r: content.visible(content.load("rooms", r).get("items"), flags) for r in content.ids("rooms")},
        "npcs": {},
        "npc_memory": {},
        "run": run,
    }
    back = carry_over(state)
    refresh_view(state)
    for pid, pl in players.items():  # how each began: their first moment's what-changed line compares with it
        pl["snapshot"] = snapshot(state, pid)
    first = ACTOR if ACTOR in players else next(iter(players))
    with acting(first):  # the look that ends a new game is the first player's, or the one named with --as
        save_state(state)
    write_json(ACTIVE, {"game": state["game"]})
    for stale in (ROOT / "proposals").glob("*.json"):
        stale.unlink()
    print("NEW GAME: %s" % state["adventure"])
    print("SEED: %s%s (the same seed rolls the same run)" % (seed, ", today's daily world" if run["daily"] else ""))
    print(cast_line(state))
    for pid, rolled in run["rolls"].items():
        print("ROLLED for %s: %s" % (pid, ", ".join("%s %d" % kv for kv in rolled.items())))
    if run["variants"]:
        print("THIS RUN (secret from the player): %s" % ", ".join("%s=%s" % kv for kv in run["variants"].items()))
    if run["clock"]:
        print("CLOCK: %s in %s" % (run["clock"]["name"], ticks_text(run["clock"]["total"])))
    if back:
        print("FROM EARLIER RUNS (they're part of this world now): %s" % "; ".join(back))
    with acting(first):
        cmd_look([])


def looks(pid):
    """What anyone sees of a person in the cast (their entry's `look`), for the referee's and the townspeople's
    lines, so everyone describes them the same way; empty when the entry gives none."""
    look = cast_entry(pid).get("look")
    return "; " + look if look else ""


def pronouns(pid):
    """How to speak of a person in the cast: their entry's `pronouns`, or they/them when it gives none."""
    return cast_entry(pid).get("pronouns") or "they/them"


def model_for(state, pid):
    """The model `pid` is asked on: the owner's `cast.model` for everyone, or, when it's `own`, their cast entry's."""
    setting = SETTINGS["cast"]["model"]
    return state["players"][pid].get("model") if setting == "own" else setting


def cast_line(state):
    """CAST: who plays, with the model each is asked on, their pronouns, and where each is now."""
    return "CAST: %s" % "; ".join("%s (%s, %s, %s) at %s%s" % (
        pl["name"], pid, model_for(state, pid), pronouns(pid), ent("rooms", pl["location"]).get("name", pl["location"]),
        "" if pl["status"] == "playing" else ", %s" % pl["status"]) for pid, pl in state["players"].items())


def cast_player(entry, w, run):
    """One player's record at the start of a run, from their cast entry. What the entry leaves out comes from the
    world file's starting character: stats (rolled by its `rolls:` when the entry gives no `attributes`), coins,
    belongings and the weapon in hand."""
    if entry.get("attributes") is None:
        stats = dict(w.get("stats") or {})
        for k in STATS + ("max_hp",):
            stats.setdefault(k, 0)
        rolled = {}
        for k, spec in (w.get("rolls") or {}).items():
            stats[k] = rolled[k] = dice.roll(spec)[0]
        if rolled:
            run["rolls"][entry["id"]] = rolled
    else:
        stats = {k: int(entry["attributes"].get(k, 0)) for k in STATS}
        stats["max_hp"] = int(entry["hp"])
    stats["hp"] = stats["max_hp"]
    stats["coins"] = int(entry.get("coins", w.get("coins", 0)))
    inventory = list(entry.get("inventory", w.get("inventory") or []))
    equipped = entry.get("equipped", w.get("equipped") if "inventory" not in entry else None)
    known = [k["who"] for k in entry.get("people") or [] if content.exists("characters", k["who"])]  # people they know already
    return {"name": entry["name"], "model": entry.get("model"), "status": "playing", "location": entry["home"],
            "stats": stats, "inventory": inventory, "equipped": equipped if equipped in inventory else None,
            "map": {}, "met": known, "present": None, "worked": None, "taken_on": [],
            "paid_beds": {b["room"]: int(b["nights"]) for b in entry.get("paid_beds") or []}}


def cmd_look(args):
    state = load_state()
    run = state["run"]
    room = room_here(state)
    flags = condition_flags(state)
    print("STATUS: %s | %s | %s | %s %d" % (me(state)["status"], hp_line(state), " ".join(
        "%s %+d" % (stat_label(k), stat(state, actor_id(state), k)) for k in STATS), currency().capitalize(), me(state)["stats"]["coins"]))
    print("LOCATION: %s (%s)%s" % (room.get("name", room["id"]), room["id"], " [generated]" if room.get("generated") else ""))
    texture = [x for x in (when_text(state), run.get("weather")) if x]
    if texture:
        print("TIME AND WEATHER: %s" % ", ".join(texture))
    if run.get("clock"):
        c = run["clock"]
        print("CLOCK STATUS: %s" % (("%s in %s" % (c["name"], ticks_text(c["left"]))) if c["left"] else "%s: it has happened" % c["name"]))
    m, res = meter(), resource()
    print("METER: %s %d/%d" % (res["name"], m["left"], m["capacity"]))
    for c in active_curses(state):
        print("CURSE: %s (`rpg.py show curses %s`): the player's words come out %s. Resolve what they meant; in the "
              "story, and to every character, they said the words as they came out." % (c.get("name", c["id"]), c["id"], curse.describe(c["effect"])))
    if meter_state(m) == "low":
        print("METER LOW: %s (you may let it show once, lightly, in the story)" % res["low"])
    elif meter_state(m) == "spent":
        print("METER SPENT: %s Nothing new can be generated and the world won't stir off-screen until the next session."
              % res["spent"])
    for d, target in (room.get("exits") or {}).items():
        dest, cond = content.split_condition(target)
        name = ent("rooms", dest).get("name", dest) if ent_exists("rooms", dest) else dest
        if content.condition_holds(cond, flags):
            print("  exit %s -> %s" % (d, name))
        else:
            print("  exit %s -> %s [BLOCKED: needs %s]" % (d, name, cond))
    if policy()["rooms"] and can_pay("generate") and unused_expansions(room):
        print("  may grow: %s (a new place can be generated there if the player goes that way)" % ", ".join(unused_expansions(room)))
    here = state["room_items"].get(room["id"], [])
    print("ITEMS HERE: %s" % (", ".join(i + (" [generated]" if is_generated("items", i) else "") for i in here) or "none"))
    here = characters_here(state)
    # A turn begins with a look or a move: who is here now may still speak this turn, even after a flag takes them
    # out of the scene (npc-brief).
    present = {"room": room["id"], "characters": here}
    heard = overhear(state)
    if heard or me(state).get("present") != present:
        me(state)["present"] = present
        save_state(state)
    voice = {c: "minor" if is_minor(c) else "minor, agent resting" if agents_resting(c) else "agent" for c in here}
    chars = ["%s [%s%s]" % (c, voice[c], ", generated" if is_generated("characters", c) else "") for c in here]
    print("CHARACTERS HERE: %s" % (", ".join(chars) or "none"))
    others = players_here(state)[1:]
    if others:
        print("PEOPLE HERE: %s. Each acts on their own turn: never speak or decide for them. What the player says "
              "aloud, they hear: `say <file>`; what they see and hear of the turn: `witnessed <file>`. What they carry is "
              "theirs: the story shows only what anyone could plainly see of it." % ", ".join(
            "%s (%s, %s%s; carrying %s%s)" % (state["players"][p]["name"], p, pronouns(p), looks(p), ", ".join(
                i + (" (in hand)" if i == state["players"][p]["equipped"] else "") for i in state["players"][p]["inventory"]) or "nothing",
                "; ASLEEP: sees and hears nothing till morning" if state["players"][p].get("asleep") else "")
            for p in others))
    offers = open_trades(state, actor_id(state))
    if offers:
        terms = lambda s: ", ".join(s["items"] + (["%d %s" % (s["coins"], currency())] if s["coins"] else [])) or "nothing"  # noqa: E731
        print("OFFERS HERE: %s" % " | ".join(
            "%s from %s (%s): gives %s; asks for %s. If the player takes it: `trade accept %s`; turns it down: `trade decline %s`" % (
                t["id"], state["players"][t["from"]]["name"], t["from"], terms(t["give"]), terms(t["want"]), t["id"], t["id"])
            if t["to"] == actor_id(state) else
            "%s to %s (%s): gives %s; asks for %s. Theirs to answer, on their own turn" % (
                t["id"], state["players"][t["to"]]["name"], t["to"], terms(t["give"]), terms(t["want"])) for t in offers))
    makers = [c for c in here if makes(c)]
    if makers and not why_no_order(state):
        print("MAKERS HERE: %s. If the player orders something made: `world-brief craft <maker>` (see gm-turn)."
              % "; ".join("%s makes %s" % (c, ", ".join(t.replace("_", " ") for t in makes(c))) for c in makers))
    spots, builders = build_spots(state, room), [c for c in here if builds(c)]
    if spots and builders and not why_no_order(state, "build"):
        print("BUILD SPOTS HERE: %s. Builders here: %s. If the player orders something built: `world-brief build <builder>` "
              "(see gm-turn)." % ("; ".join("%s: %s" % kv for kv in spots.items()), ", ".join(builders)))
    job = work_of(room, condition_flags(state))
    if job:
        print("WORK HERE: %s vs DC %d, pays %s %s, once per visit%s. If the player works here: `work`." % (
            stat_label(job["stat"]), job["dc"], "%d-%d" % (job["low"], job["high"]) if job["high"] > job["low"] else job["low"],
            currency(), " (done this visit)" if me(state).get("worked") == room["id"] else ""))
    shared = project_of(room)
    if shared:  # for the referee: how the shared work stands, and whether this person has helped this turn
        rec, open_ = project_state(state, shared["id"]), content.condition_holds(shared["until"], condition_flags(state))
        print("SHARED WORK HERE: %s (%s): %d done%s; %s has given it %d turns%s. If the player works on it: `work` (once a turn)." % (
            shared["name"], shared["id"], rec["total"], "" if open_ else ", OVER (no more to do)", me(state)["name"],
            rec["by"].get(actor_id(state), 0), " (done this turn)" if me(state).get("helped") == [room["id"], state["run"].get("round") or state["run"]["moves"]] else ""))
    reach, taken = quests_in_reach(state), me(state).get("taken_on", [])
    if reach:
        print("QUESTS: %s. When the player sets out to work on one, or agrees to a job: `quest take <id>`; when they set "
              "one aside: `quest leave <id>`." % "; ".join("%s (%s): %s" % (ent("quests", q).get("name", q), q, "taken on" if q in taken
                                                                             else "not taken on") for q in reach))
    sellers = [c for c in here if sells(c)]
    if sellers:  # for the referee: the prices are the seller's to tell when asked, never announced
        print("SELLERS HERE: %s. If the player buys something: `buy <item>` (or `buy <item> <seller>`)." % "; ".join(
            "%s (%s): %s" % (ent("characters", c).get("name", c), c, ", ".join("%s %d%s" % (i, s["price"], "" if stock_left(state, c, i) is None
                                                                                  else ", %d left" % stock_left(state, c, i)) for i, s in sells(c).items()))
            for c in sellers))
    lets = [r for r in content.ids("rooms") if rent_of(ent("rooms", r)) and rent_of(ent("rooms", r))["landlord"] in here]
    if lets:
        print("LETS HERE: %s. If the player takes one: `rent <room>`." % "; ".join(
            "%s (%s), %d %s for %d days, from %s: %s" % (ent("rooms", r).get("name", r), r, rent_of(ent("rooms", r))["price"], currency(),
                                                        rent_of(ent("rooms", r))["days"], rent_of(ent("rooms", r))["landlord"],
                                                        "let to %s to the end of day %d" % (state["players"][let_of(state, r)["tenant"]]["name"], let_of(state, r)["until"])
                                                        if let_of(state, r) else "free") for r in lets))
    buyers = [c for c in here if buys(c)]
    if buyers:
        print("BUYERS HERE: %s. If the player sells something: `sell <item>`." % "; ".join(
            "%s buys %s" % (c, ", ".join("%s %d" % (t.replace("_", " "), p) for t, p in buys(c).items())) for c in buyers))
    waiting = [(i, c) for i, c in run["commissions"].items() if c["status"] == "ordered"]
    if waiting:
        print("ORDERS WAITING: %s. When the player pays: `pay <id>` (an item may be paid for in trade: `pay <id> <material>`)."
              % " | ".join("%s (%s) from %s, unpaid: %s" % (i, order_name(i, c), c["maker"], price_text(c)) for i, c in waiting))
    going_up = [(i, c) for i, c in run["commissions"].items() if c["status"] == "building"]
    if going_up:
        print("BEING BUILT: %s" % " | ".join("%s (%s), %s of %s: ready in %s" % (
            i, order_name(i, c), c["direction"], c["room"], ticks_text(max(0, c["ready_at"] - run["moves"]))) for i, c in going_up))
    playing, rec = scene_playing(state)
    if playing:
        print("SCENE PLAYING: %s (%d of %d replies so far). One reply from each per player message; `scene end %s` when "
              "it's over." % (playing, rec["replies"], int(SETTINGS["side_scenes"]["replies"]), playing))
    for s in content.ids("scenes") if not playing else ():
        if not why_no_scene(state, s):
            print("SCENE HERE: %s (%s). Show it beginning, from `show scenes %s` (How it starts); if the player takes it up, "
                  "`scene start %s` (see gm-turn, Side scenes)." % (s, scene(s).get("name", s), s, s))
    if sum(1 for v in voice.values() if v == "agent") >= 2:
        print("AGENT LINES PER TURN: at most %d between them" % SETTINGS["npc_agents"]["lines_per_exchange"])
    notes = run["notes"].get(room["id"], [])
    if notes:
        print("ESTABLISHED HERE: %s" % " | ".join(notes))
    if has_board(room):  # newest first, numbered as `post take` takes them
        board = list(reversed(notices(state, room["id"])))
        print("NOTICE BOARD: %s. If the player puts up a notice: `post <file>`; takes down their own: `post take <n>`." % (
            "; ".join('%d. "%s" (%s)' % (i + 1, n["text"], state["players"][n["by"]]["name"] if n["by"] in state["players"]
                                         else "put up off-screen") for i, n in enumerate(board)) or "nothing put up"))
    owner = stash_owner(state, room["id"])
    if owner:
        print("STASH: %s is %s's own place; what's left here only %s can take." % (
            room.get("name", room["id"]), state["players"][owner]["name"], state["players"][owner]["name"]))
    inv = ["%s%s" % (i, " (equipped)" if i == me(state)["equipped"] else "") for i in me(state)["inventory"]]
    print("INVENTORY: %s  [weight %d/%d]" % (", ".join(inv) or "nothing", carried_weight(state), carry_limit(state)))
    print("FLAGS: %s" % flags_line(state))
    own = me(state).get("flags", [])
    print("ALSO TRUE: %s" % (", ".join(f for f in flags if f not in state["flags"] and f not in own) or "none"))
    gen_q = [q for q in ent_ids("quests") if is_generated("quests", q)]
    if gen_q:
        print("SIDE QUESTS: %s (read with `rpg.py show quests <id>`)" % ", ".join(gen_q))
    if run["world_turn_due"]:
        print("WORLD TURN DUE: run `tools/voice.py world turn`, then `world-turn` on what it saved (see gm-turn)")
    for d in drafts():
        if draft_status(d) == "ready":
            print("NEW WORLD READY: %s: run `rpg.py forge install %s`, then tell the player in one line (see gm-turn)." % (d, d))
    # Last, so a move or a look is one command: the room as it reads now (the `## If` sections that hold), as
    # `show rooms` prints its body. Nothing between these two lines is a status line; the end line lets the mod
    # tell a command chained after this one from the prose.
    if world_needs():  # for the referee: where this person's needs stand, and what here meets them
        n, place = needs_of(me(state)), room_here(state).get("sleep")
        food = [i for i in me(state)["inventory"] if str(item(i).get("food", "no")).lower() == "yes"]
        print("NEEDS: %s%s%s%s" % ("; ".join(x for x in (
            "food: %s" % food_state(me(state)) if "food" in world_needs() else "",
            "sleep: %s%s" % (n["sleep"], ", slept this night (%s)" % n["slept"] if n["slept"] else "") if "sleep" in world_needs() else "") if x),
            "; FOOD CARRIED: %s (`eat <item>`)" % ", ".join(food) if food else "",
            "; SLEEP HERE: %s (`sleep`, at %s)" % (place, " or ".join(bed_times())) if place and "sleep" in world_needs() else "",
            "; IT'S THE TIME FOR SLEEP" if time_of_day(state) == world().get("sleep_at") else ""))
    print("ROOM TEXT:")
    print(room_text(state, room))
    print("END OF ROOM TEXT")


def room_text(state, room):
    """A room's prose as it reads now, authored or generated alike."""
    return applicable((room.get("body") or "").strip(), condition_flags(state)) or "(no description)"


def cmd_move(args):
    state = load_state()
    require_playing(state)
    want = args[0]
    exits = room_here(state).get("exits") or {}
    if want not in exits:
        # allow naming the destination room instead of the direction
        match = [d for d, t in exits.items() if content.split_condition(t)[0] == want]
        if not match:
            grow = unused_expansions(room_here(state)) if policy()["rooms"] else []
            hint = " This room may grow %s: generate a room there first." % "/".join(grow) if want in grow else ""
            raise Refused("no exit %r here. Exits: %s.%s" % (want, ", ".join(exits) or "none", hint))
        want = match[0]
    dest, cond = content.split_condition(exits[want])
    if not content.condition_holds(cond, condition_flags(state)):
        raise Refused("the way %s is blocked (needs %s)" % (want, cond))
    me(state)["location"] = dest
    me(state)["worked"] = None  # a new visit: there may be work here again
    turn = me(state).get("turn") or {}
    if turn.get("round") == state["run"].get("round") and state["run"].get("round_state"):
        turn.setdefault("passed", []).append(dest)  # who saw them go by (witnessed --in)
    log_use(state, dest, "entered")
    left, _ = scene_playing(state)
    events = lapse_trades(state)
    if left:
        end_scene(state, left, False)
        events.append("SCENE OVER: the player walked away from %s; it's done, with no reward." % scene(left).get("name", left))
    if not by_rounds():  # in a simulation the clock moves once per round, at `round end`
        events += tick_move(state)
    events += roll_encounter(state, ent("rooms", dest))
    save_state(state)
    print("MOVED %s." % want)
    for line in events:
        print(line)
    cmd_look([])


def cmd_take(args):
    state = load_state()
    require_playing(state)
    ident = args[0]
    here = state["room_items"].setdefault(me(state)["location"], [])
    if ident not in here:
        raise Refused("%s is not here. Items here: %s" % (ident, ", ".join(here) or "none"))
    owner = stash_owner(state, me(state)["location"])
    if owner and owner != actor_id(state):
        raise Refused("this is %s's stash: what's left here is theirs, and stays put" % state["players"][owner]["name"])
    check_carry(state, ident)
    here.remove(ident)
    me(state)["inventory"].append(ident)
    log_use(state, ident, "taken")
    save_state(state)
    print("TAKEN: %s  [weight %d/%d]" % (ident, carried_weight(state), carry_limit(state)))


def stash_owner(state, room_id):
    """The player whose stash this room is, or None. Things left in a stash can be taken only by its owner."""
    meta = (state["run"]["rooms"].get(room_id) or {}).get("meta") or {}
    if meta.get("use") == "stash" and meta.get("owner") in state["players"]:
        return meta["owner"]
    let = let_of(state, room_id)  # a place let is its tenant's while it lasts
    return let["tenant"] if let and let["tenant"] in state["players"] else None


def remove_from_inventory(state, ident):
    if ident not in me(state)["inventory"]:
        raise Refused("you are not carrying %s" % ident)
    me(state)["inventory"].remove(ident)
    if me(state)["equipped"] == ident and ident not in me(state)["inventory"]:
        me(state)["equipped"] = None


def cmd_drop(args):
    state = load_state()
    require_playing(state)
    ident = args[0]
    remove_from_inventory(state, ident)
    state["room_items"].setdefault(me(state)["location"], []).append(ident)
    log_use(state, ident, "left in %s" % me(state)["location"])
    save_state(state)
    print("DROPPED: %s in %s" % (ident, me(state)["location"]))


def cmd_gain(args):
    state = load_state()
    require_playing(state)
    ident = args[0]
    check_carry(state, ident)
    me(state)["inventory"].append(ident)
    log_use(state, ident, "received")
    save_state(state)
    print("GAINED: %s  [weight %d/%d]" % (ident, carried_weight(state), carry_limit(state)))


def cmd_lose(args):
    state = load_state()
    require_playing(state)
    remove_from_inventory(state, args[0])
    log_use(state, args[0], "given away")
    save_state(state)
    print("LOST: %s" % args[0])


def cmd_equip(args):
    state = load_state()
    require_playing(state)
    ident = args[0]
    if ident not in me(state)["inventory"]:
        raise Refused("you are not carrying %s" % ident)
    if not item(ident).get("damage"):
        raise Refused("%s is not a weapon (no damage)" % ident)
    me(state)["equipped"] = ident
    log_use(state, ident, "equipped")
    save_state(state)
    print("EQUIPPED: %s (damage %s)" % (ident, item(ident)["damage"]))


def cmd_use(args):
    state = load_state()
    require_playing(state)
    ident = args[0]
    if ident not in me(state)["inventory"]:
        raise Refused("you are not carrying %s" % ident)
    heal = item(ident).get("heal")
    if not heal:
        raise Refused("%s has no mechanical use; use it in the story per its item file" % ident)
    total, faces, mod = dice.roll(heal)
    s = me(state)["stats"]
    before = s["hp"]
    s["hp"] = min(s["max_hp"], s["hp"] + total)
    remove_from_inventory(state, ident)
    log_use(state, ident, "used up")
    save_state(state)
    print("USED %s: heal %s; healed %d. %s" % (ident, dice.describe(heal, total, faces, mod), s["hp"] - before, hp_line(state)))


def cmd_roll(args):
    try:
        state = load_state()
    except Refused:
        state = None  # no game: a loose roll
    spec = args[0]
    total, faces, mod = dice.roll(spec)
    if state:
        save_state(state)  # the run's dice stream has moved on
    print("ROLL %s" % dice.describe(spec, total, faces, mod))


def cmd_check(args):
    state = load_state()
    require_playing(state)
    stat, dc = args[0].lower(), resolve_dc(args[1])
    if stat not in STATS:
        raise Refused("stat must be one of %s" % ", ".join(STATS))
    mod = attempt_mod(state, actor_id(state), stat)  # tired or weak: it shows here, never in the story's numbers
    ok, nat, total, note = d20_test(mod, dc)
    save_state(state)  # the run's dice stream has moved on
    print("CHECK %s vs DC %d: d20 %d %+d = %d%s -> %s"
          % (stat, dc, nat, mod, total, note, "SUCCESS" if ok else "FAILURE"))


def cmd_attack(args):
    state = load_state()
    require_playing(state)
    target = args[0]
    if target not in characters_here(state):
        raise Refused("%s is not here" % target)
    foe = ent("characters", target)
    if "hp" not in foe:
        raise Refused("%s has no combat stats and cannot be fought" % target)
    npc = state["npcs"].setdefault(target, {"hp": int(foe["hp"]), "max_hp": int(foe["hp"])})
    if npc["hp"] <= 0:
        raise Refused("%s is already defeated" % target)

    out = []
    # player swings
    weapon = me(state)["equipped"]
    if weapon:
        log_use(state, weapon, "fought with")
    dmg_spec = item(weapon)["damage"] if weapon else BALANCE["unarmed_damage"]
    mod = attempt_mod(state, actor_id(state), "might")
    ok, nat, total, note = d20_test(mod, int(foe["defense"]))
    out.append("PLAYER ATTACKS %s with %s: d20 %d %+d = %d vs defense %s%s -> %s"
               % (target, weapon or "bare hands", nat, mod, total, foe["defense"], note, "HIT" if ok else "MISS"))
    if ok:
        crit = nat == 20 and BALANCE["crit_extra_damage_dice"]
        dmg, faces, dmod = dice.roll(dmg_spec, extra_dice=crit)
        dmg = max(1, dmg)
        npc["hp"] = max(0, npc["hp"] - dmg)
        out.append("  damage %s%s -> %s HP %d/%s"
                   % (dice.describe(dmg_spec, dmg, faces, dmod), " (critical: double dice)" if crit else "",
                      target, npc["hp"], foe["hp"]))
    if npc["hp"] == 0:
        set_flag(state, "%s_defeated" % target)
        out.append("%s IS DEFEATED. Flag set: %s_defeated" % (target.upper(), target))
    else:
        # foe swings back
        amod = int(foe.get("attack", 0))
        ok, nat, total, note = d20_test(amod, player_defense(state))
        out.append("%s ATTACKS: d20 %d %+d = %d vs your defense %d%s -> %s"
                   % (target.upper(), nat, amod, total, player_defense(state), note, "HIT" if ok else "MISS"))
        if ok:
            crit = nat == 20 and BALANCE["crit_extra_damage_dice"]
            dmg, faces, dmod = dice.roll(foe["damage"], extra_dice=crit)
            dmg = max(1, dmg)
            out.append("  damage %s%s -> %s" % (dice.describe(foe["damage"], dmg, faces, dmod),
                                                 " (critical: double dice)" if crit else "", damage_player(state, dmg)))
    save_state(state)
    print("\n".join(out))


def cmd_hurt(args):
    state = load_state()
    require_playing(state)
    total, faces, mod = dice.roll(args[0])
    total = max(0, total)
    msg = damage_player(state, total)
    save_state(state)
    print("HURT %s. %s" % (dice.describe(args[0], total, faces, mod), msg))


def cmd_heal(args):
    state = load_state()
    require_playing(state)
    total, faces, mod = dice.roll(args[0])
    s = me(state)["stats"]
    before = s["hp"]
    s["hp"] = min(s["max_hp"], s["hp"] + max(0, total))
    save_state(state)
    print("HEAL %s; healed %d. %s" % (dice.describe(args[0], total, faces, mod), s["hp"] - before, hp_line(state)))


def cmd_coins(args):
    """coins <+n|-n> <reason>: money changes hands in the story; the reason goes in the log."""
    state = load_state()
    require_playing(state)
    reason = args[1]
    if reason not in COIN_REASONS:
        raise Refused("the reason must be one of %s" % ", ".join(COIN_REASONS))
    try:
        delta = int(args[0])
    except ValueError:
        raise Refused("coins takes a signed whole number, e.g. +3 or -2")
    if abs(delta) > 999:
        raise Refused("coins changes are at most 999 at a time")
    s = me(state)["stats"]
    if s["coins"] + delta < 0:
        raise Refused("not enough coins: have %d, need %d" % (s["coins"], -delta))
    change_coins(state, delta, reason)
    save_state(state)
    print("COINS %+d -> %d" % (delta, s["coins"]))


def cmd_flag(args):
    state = load_state()
    require_playing(state)
    action, name = args[0], args[1]
    if not re.fullmatch(r"[a-z0-9_]+", name):
        raise Refused("flag names are lowercase letters, digits and underscores")
    if name.startswith(AUTOMATIC):
        raise Refused("has_, met_, time_, day_ and after_day_ names are automatic (carrying an item, having met "
                      "someone, the time and the day) and can't be set")
    if action == "set":
        set_flag(state, name)
    elif action == "unset":
        if name in flags_of(state, name):
            flags_of(state, name).remove(name)
    else:
        raise Refused("use: flag set <name> | flag unset <name>")
    save_state(state)
    print("FLAG %s %s%s. Flags: %s" % (action, name, " (%s's own)" % me(state)["name"] if name in personal_flags() else "",
                                       flags_line(state)))
    for line in ending_lines(state):
        print(line)


def cmd_npc_brief(args):
    """Everything an NPC agent is allowed to know, built from its character file and state."""
    state = load_state()
    ident = args[0]
    present = me(state).get("present") or {}
    # someone a flag has just taken out of the scene still has their parting line, this turn and in this room
    leaving = (ident not in characters_here(state) and present.get("room") == me(state)["location"]
               and ident in present.get("characters", []))
    if ident not in characters_here(state) and not leaving:
        raise Refused("%s is not in this scene" % ident)
    if is_minor(ident):
        raise Refused("%s is a minor character; the game master plays them directly" % ident)
    why = agents_resting(ident)
    if why:
        raise Refused("%s speaks through you right now (%s). Voice them yourself from `rpg.py show characters %s`, "
                      "as for a [minor] character." % (ident, why, ident))
    ch = ent("characters", ident)
    flags = condition_flags(state)
    lines = ["You are %s, %s." % (ch.get("name", ident), ch.get("role", "a character in this world")), ""]
    now = []
    for heading, text in content.sections(ch["body"]):
        cond = content.section_condition(heading)
        if heading.lower().startswith("gm") or content.is_plan(heading):
            continue
        if cond is not None:
            if content.condition_holds(cond, flags):
                now.append(text)
            continue
        lines += ["## " + heading if heading else "", text, ""]
    if now:
        lines += ["## Right now", "\n\n".join(now), ""]
    room = room_here(state)
    people = players_here(state)  # the one speaking to them first; to them, players are people like any other
    others = ["%s (%s)" % (ent("characters", c).get("name", c), ent("characters", c).get("role", ""))
              for c in characters_here(state) if c != ident]
    # each person with how to speak of them, so the world's people do it the same way every time (step 41: Dilly was
    # "young miss" one round and "young sir" the next)
    lines += ["## The scene", "You are at %s. Present: %s." % (
        room.get("name", room["id"]), ", ".join(["%s (%s%s)" % (state["players"][pid]["name"], pronouns(pid), looks(pid)) for pid in people] + others)),
        "%s is the one talking to you." % me(state)["name"], ""]
    if leaving:
        lines += ["This is your parting line: what just happened takes you out of this scene.", ""]
    playing, rec = scene_playing(state)
    cap = int(SETTINGS["side_scenes"]["replies"])
    again = playing and rec.get("last") == ident  # the two take turns, so a second brief in a row is the same reply
    if playing and ident in scene_cast(scene(playing)) and (rec["replies"] < cap or again):
        premise, part = scene_part(playing, ident)
        if not again:
            rec["replies"] += 1
            rec["last"] = ident
            save_state(state)
        lines += ["## A little scene you're in", premise, "", part, "",
                  "This is reply %d of the scene's %d.%s" % (rec["replies"], cap, " It's the last one: bring the scene to a close."
                                                            if rec["replies"] >= cap else ""), ""]
    wares = sells(ident)
    if wares:  # what they sell is theirs to tell when asked, at these prices and no other
        lines += ["## What you sell, at these prices and no other"] + ["- %s: %d %s%s" % (
            item(i).get("name", i), s["price"], currency(), "" if stock_left(state, ident, i) is None else
            (" (none left)" if stock_left(state, ident, i) == 0 else " (%d left)" % stock_left(state, ident, i))) for i, s in wares.items()] + [""]
    mine = [r for r in content.ids("rooms") if rent_of(ent("rooms", r)) and rent_of(ent("rooms", r))["landlord"] == ident]
    if mine:
        lines += ["## What you let, on these terms and no other"] + ["- %s: %d %s for %d days, %s" % (
            ent("rooms", r).get("name", r), rent_of(ent("rooms", r))["price"], currency(), rent_of(ent("rooms", r))["days"],
            "let to %s to the end of day %d" % (state["players"][let_of(state, r)["tenant"]]["name"], let_of(state, r)["until"])
            if let_of(state, r) else "free to let") for r in mine] + [""]
    rumors = state["run"]["rumors"][-3:]
    if rumors:
        lines += ["## Talk going around (you may have heard it)"] + ["- " + r for r in rumors] + [""]
    for pid in people:
        with acting(pid):
            memory = npc_memory_of(state, ident)
        lines.append("## What you remember about %s" % state["players"][pid]["name"])
        lines += ["- " + m for m in memory] if memory else ["You have never met this person before."]
        lines.append("")
    print("\n".join(l for l in lines).strip())


def cmd_remember(args):
    state = load_state()
    require_playing(state)
    ident, text = args[0], " ".join(args[1:]).strip()
    if not ent_exists("characters", ident):
        raise Refused("no character named %r" % ident)
    if not text:
        raise Refused("usage: remember <character> <one short line>")
    limit = BALANCE["npc"]["memory_line_chars"]
    if len(text) > limit:
        raise Refused("memory lines must be at most %d characters (got %d); shorten it" % (limit, len(text)))
    mem = npc_memory_list(state, ident)
    mem.append(text)
    del mem[:-BALANCE["npc"]["memory_lines"]]
    save_state(state)
    print("REMEMBERED by %s (%d/%d lines): %s" % (ident, len(mem), BALANCE["npc"]["memory_lines"], text))


# ---------------------------------------------------------------- run content: show, generate, notes, world turns

def applicable(body, flags):
    """A body with only the `## If` sections that hold now; every other section is kept, except plans (`## Plan:`),
    which are for the rules alone."""
    out = []
    for heading, text in content.sections(body):
        cond = content.section_condition(heading)
        if content.is_plan(heading) or cond is not None and not content.condition_holds(cond, flags):
            continue
        out.append(("## %s\n%s" % (heading, text)) if heading else text)
    return "\n\n".join(out)


def cmd_show(args):
    """show <kind> <id> [--all] | show world: a room, character, item, quest or table as it reads now.
    Authored or generated alike; `## If` sections that don't hold are left out unless --all."""
    try:
        state = load_state()
        flags = condition_flags(state)
    except Refused:
        state, flags = None, None  # no game yet: everything is shown
    if "--all" in args:
        flags = None
        args = [a for a in args if a != "--all"]
    if args[0] == "world":
        w = content.load_world()
        text = (content.game_dir() / "world.md").read_text(encoding="utf-8").strip()
        meta, body = text.split("\n---", 1)[0], w["body"]
        print(meta + "\n---\n" + (body if flags is None else applicable(body, flags)))
        return
    if len(args) < 2:
        raise Refused("usage: show <rooms|characters|items|quests|tables> <id>, or show world")
    kind, ident = args[0], args[1]
    if kind not in content.KINDS:
        raise Refused("kind must be one of %s, or world" % ", ".join(content.KINDS))
    memory = npc_memory_of(state, ident) if state and kind == "characters" else []
    remembered = ("\n\n## What they remember about %s (the player acting)\n" % me(state)["name"]
                  + "\n".join("- " + m for m in memory)) if memory else ""
    if content.exists(kind, ident):
        text = content.path_of(kind, ident).read_text(encoding="utf-8").strip()
        if text.startswith("---") and "\n---" in text[3:]:
            head, body = text[3:].split("\n---", 1)
            text = "---" + head + "\n---\n" + (body.strip() if flags is None else applicable(body.strip(), flags))
        print(text + remembered)
        return
    e = ent(kind, ident)
    meta = {k: v for k, v in e.items() if k not in ("id", "body")}
    print("---")
    for k, v in meta.items():
        if isinstance(v, dict):
            print("%s:" % k)
            for kk, vv in v.items():
                print("  %s: %s" % (kk, vv))
        elif isinstance(v, list):
            print("%s:" % k)
            for x in v:
                print("  - %s" % x)
        else:
            print("%s: %s" % (k, v))
    print("---")
    print((e["body"] if flags is None else applicable(e["body"], flags)) + remembered)


def gen_context(state):
    room = {} if no_one(state) else room_here(state)  # a world turn between rounds happens nowhere in particular
    here = room.get("id")
    here_items = state["room_items"].get(here, [])
    names = [ent(k, i).get("name", i) for k in ("rooms", "characters", "items", "quests") for i in ent_ids(k)]
    ids = [i for k in content.KINDS for i in ent_ids(k)]
    run = state["run"]
    ordering = run.get("ordering") or {}
    maker = ordering.get("maker") if ent_exists("characters", ordering.get("maker") or "") else None
    kind = ordering.get("kind", "craft")
    for i, com in run["commissions"].items():
        if "record" in com:  # a building not finished yet still holds its id and name
            ids.append(i)
            names.append(com["record"]["meta"]["name"])
    return generate.Context(
        location=here, taken_ids=ids, taken_names=names, expand=unused_expansions(room) if here else [],
        policy=policy(), balance=dict(BALANCE["generation"], max_per_run=SETTINGS["generation"]["max_per_run"]),
        count=run["generated"],
        items_found_here=sum(1 for i in here_items if is_generated("items", i)),
        extras_here=sum(1 for c in run["placements"].get(here, []) if ent("characters", c).get("extra") == "yes"),
        characters_here=characters_here(state) if here else [], room_ids=ent_ids("rooms"),
        generated_people=list(run["characters"]),
        terrains=list(content.look().get("terrain") or {}), terrain_here=room.get("terrain"),
        moves=run["moves"], maker=maker if kind == "craft" else None, makes=makes(maker) if maker and kind == "craft" else (),
        builder=maker if kind == "build" else None, build_spots=build_spots(state, room) if here else {},
        depth_here=room_depth(room),
        plan_steps={c: [st["step"] for st in steps] for c, steps in open_steps(state).items()},
        board_rooms=[r for r in ent_ids("rooms") if has_board(ent("rooms", r))])


def apply_patch(state, patch):
    run = state["run"]
    stamp = run["moves"]
    for kind in ("rooms", "characters", "items", "quests"):
        for ident, rec in patch[kind].items():
            run[kind][ident] = dict(rec, made_at_move=stamp)
    for room, ex in patch["exits"].items():
        run["exits"].setdefault(room, {}).update(ex)
    for room, people in patch["placements"].items():
        run["placements"].setdefault(room, []).extend(people)
    for room, items in patch["room_items"].items():
        state["room_items"].setdefault(room, []).extend(items)
    for ident, com in patch["commissions"].items():
        run["commissions"][ident] = com
    # the world's own inventions count toward the run's limit; what the player ordered has its own limits
    run["generated"] = sum(1 for k in ("rooms", "characters", "items", "quests") for rec in run[k].values()
                           if rec["meta"].get("made_by", "world") == "world" and not rec["meta"].get("carried"))


def read_json_arg(args):
    """The proposal: a JSON file (normally proposals/<name>.json, written by the GM), or stdin."""
    if args and not Path(args[0]).is_file():
        raise Refused("no proposal file at %s" % args[0])
    raw = Path(args[0]).read_text(encoding="utf-8") if args else sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise Refused("the proposal is not valid JSON: %s" % e)
    if not isinstance(data, dict):
        raise Refused("the proposal must be one JSON object")
    return data


def done_with(args):
    """A proposal file in proposals/ is used up once read, applied or refused, so a stale one can't linger."""
    if args and Path(args[0]).is_file() and Path(args[0]).resolve().parent == (ROOT / "proposals").resolve():
        Path(args[0]).unlink()


MALFORMED = (ValueError, TypeError, AttributeError, KeyError)


def cmd_generate(args):
    """generate <extra|room|item|character|quest> [file]: check a world-agent proposal (JSON on stdin) and add it."""
    state = load_state()
    require_playing(state)
    kind = args[0]
    if kind not in generate.KINDS:
        raise Refused("kind must be one of %s" % ", ".join(generate.KINDS))
    ordering = state["run"].get("ordering") or {}
    maker = ordering.get("maker")
    if kind in ORDER_KINDS and maker and ordering.get("kind", "craft") != kind:
        raise Refused("the open order is a %s order; run `world-brief %s <%s>` first" % (ordering.get("kind", "craft"), kind,
                                                                                      "maker" if kind == "craft" else "builder"))
    try:
        if kind in ORDER_KINDS and maker and maker not in characters_here(state):
            raise Refused("the order was being placed with %s, who isn't here any more; nothing is made" % maker)
        proposal = read_json_arg(args[1:])
        reused = proposal.get("reuse") if kind in generate.REUSE_KINDS else None
        try:
            if reused is not None:
                if state["run"].get("brief") != kind and not can_pay("reuse"):
                    raise Refused("the %s is spent until the next session, so no one comes back: it doesn't happen"
                                  % resource()["name"].lower())
                entry = lib()["entries"].get(reused) if isinstance(reused, str) else None
                if not entry or entry.get("forgotten"):
                    raise ValueError("%r isn't in the library" % (reused,))
                patch = generate.reuse(reused, entry, gen_context(state), kind, proposal.get("direction"))
            else:
                patch = generate.KINDS[kind](proposal, gen_context(state))
        except generate.Declined as e:
            log(state, "order", order=ordering.get("order"), step="declined", reason=str(e))
            state["run"]["ordering"] = None
            save_state(state)
            raise Refused("%s turns the order down: %s. Narrate it in character; nothing is made"
                          % (ent("characters", maker).get("name", maker), e))
        except ValueError as e:
            raise Refused("proposal rejected: %s" % e)
        except MALFORMED[1:] as e:
            raise Refused("proposal rejected: it doesn't match the JSON shape in the brief (%s)" % e)
    finally:
        done_with(args[1:])
    if kind == "build":  # a newer order for the same spot replaces an unpaid one
        com = next(iter(patch["commissions"].values()))
        for i, old in list(state["run"]["commissions"].items()):
            if old["kind"] == "room" and old["status"] == "ordered" and (old["room"], old["direction"]) == (com["room"], com["direction"]):
                del state["run"]["commissions"][i]
    if kind in ORDER_KINDS:
        for i, com in patch["commissions"].items():
            com.update(order=ordering.get("order"), ordered_by=actor_id(state))
            meta = (patch["items"][i] if kind == "craft" else com["record"])["meta"]
            log(state, "order", order=com["order"], step="shaped", what=com["kind"], id=i, name=meta.get("name", i),
                tier=meta.get("tier"), use="stash" if kind == "build" else None, maker=com["maker"])
            log(state, "order", order=com["order"], step="priced", id=i, price=com["price"],
                trade=list(accepts(com["maker"])) if kind == "craft" else [])
    apply_patch(state, patch)
    if kind in ORDER_KINDS:
        state["run"]["ordering"] = None
        save_state(state)
        for i, com in patch["commissions"].items():
            who = ent("characters", com["maker"]).get("name", com["maker"])
            if kind == "craft":
                meta = patch["items"][i]["meta"]
                print("COMMISSIONED: %s (%s), %s, from %s" % (meta["name"], i, meta["tier"].replace("_", " "), who))
                print("PRICE: %s. The maker names it in character. When the player pays, run `pay %s` (or `pay %s <material>`); "
                      "until then it isn't theirs." % (price_text(com), i, i))
            else:
                print("COMMISSIONED: %s (%s), to be built %s of here by %s" % (com["record"]["meta"]["name"], i, com["direction"], who))
                print("PRICE: %s. The builder names it in character. When the player pays, run `pay %s`; it takes %s to build, "
                      "and until then it doesn't exist." % (price_text(com), i, ticks_text(int(BALANCE["generation"]["build_moves"]))))
        return
    paid_for = state["run"].get("brief") == kind
    state["run"]["brief"] = None
    save_state(state)
    if reused is not None:
        data = lib()
        library.seen(data, reused)
        lib_save(data)
        if paid_for:  # bringing something back is cheaper than inventing it
            refund(price("generate") - price("reuse"))
        else:
            charge("reuse")
    else:
        record_patch(state, kind, patch)
    made = ["%s %s (%s)" % (k[:-1], patch[k][i]["meta"].get("name", i), i)
            for k in ("rooms", "characters", "items", "quests") for i in patch[k]]
    print("GENERATED: %s" % ", ".join(made))
    for room, ex in patch["exits"].items():
        for d, dest in ex.items():
            print("  new exit: %s %s -> %s" % (room, d, dest))
    for room, items in patch["room_items"].items():
        print("  placed in %s: %s" % (room, ", ".join(items)))
    for room, people in patch["placements"].items():
        print("  present in %s: %s" % (room, ", ".join(people)))
    if reused is not None:
        print("  (brought back from an earlier run; the player hasn't met them in this one)")
    print("Read them with `rpg.py show <kind> <id>`. Run total: %d/%d" % (state["run"]["generated"], SETTINGS["generation"]["max_per_run"]))


def cmd_pay(args):
    """pay <order> [<material>]: the player pays the maker or builder for an order, in money or (for a made item)
    with an item they take in trade. A made item is handed over at once and is the player's own; a building
    starts, and is finished `generation.build_moves` moves later."""
    state = load_state()
    require_playing(state)
    ident, run = args[0], state["run"]
    com = run["commissions"].get(ident)
    if not com or com["status"] != "ordered":
        waiting = [i for i, c in run["commissions"].items() if c["status"] == "ordered"]
        raise Refused("no unpaid order %r. Orders waiting: %s" % (ident, ", ".join(waiting) or "none"))
    maker = com["maker"]
    who = ent("characters", maker).get("name", maker)
    if maker not in characters_here(state):
        raise Refused("%s isn't here; the order waits with them" % who)
    s = me(state)["stats"]
    material = args[1] if len(args) > 1 else None
    if material and com["kind"] == "room":
        raise Refused("%s builds for %s only" % (who, currency()))
    if com["kind"] == "room" and com["direction"] not in build_spots(state, ent("rooms", com["room"])):
        raise Refused("something is already being built %s of here" % com["direction"])
    if material:
        if material not in accepts(maker):
            raise Refused("%s takes no %s in trade (takes: %s)" % (who, material, ", ".join(accepts(maker)) or "only " + currency()))
        remove_from_inventory(state, material)
        log_use(state, material, "paid with")
        paid = "PAID WITH: %s" % material
    else:
        if s["coins"] < com["price"]:
            raise Refused("not enough %s: the price is %d and the player has %d" % (currency(), com["price"], s["coins"]))
        change_coins(state, -com["price"], "order", ident)
        paid = "COINS -%d -> %d" % (com["price"], s["coins"])
    log(state, "order", order=com.get("order"), step="paid", id=ident, price=com["price"], material=material)
    if com["kind"] == "room":
        wait = int(BALANCE["generation"]["build_moves"])
        com.update(status="building", paid_at=run["moves"], ready_at=run["moves"] + wait, by=actor_id(state))
        save_state(state)
        print(paid)
        print("BUILDING: %s (%s), %s of here, by %s: ready in %s. It doesn't exist until then."
              % (order_name(ident, com), ident, com["direction"], who, ticks_text(wait)))
        return
    com.update(status="done", paid_at=run["moves"], by=actor_id(state))
    check_carry(state, ident)
    me(state)["inventory"].append(ident)
    run["items"][ident]["meta"]["owner"] = actor_id(state)
    log(state, "order", order=com.get("order"), step="delivered", id=ident)
    save_state(state)
    data = lib()
    library.add(data, lib_limit(), ident, "items", "player", run["items"][ident], where=None)
    lib_save(data)
    print(paid)
    print("MADE: %s (%s), made for the player by %s. It's theirs now.  [weight %d/%d]"
          % (item(ident).get("name", ident), ident, who, carried_weight(state), carry_limit(state)))


def cmd_work(args):
    """work: the player works where they stand, if the room pays for work: a check against its stat, then coins on
    a success. Once per visit, whatever the outcome; walking away and coming back is a new visit. Where the room has
    shared work (`project:`), once each turn instead, and each turn counts as their effort on it (help_with)."""
    state = load_state()
    require_playing(state)
    room = room_here(state)
    job, shared = work_of(room, condition_flags(state)), project_of(room)
    if shared and not content.condition_holds(shared["until"], condition_flags(state)):
        if not job:
            raise Refused("%s is over: there's no more of it to do" % shared["name"])
        shared = None
    if not job and not shared:
        raise Refused("there's no paid work here, nor shared work")
    if shared:  # shared work: every turn there counts, so a whole day can go to it
        turn = [room["id"], state["run"].get("round") or state["run"]["moves"]]
        if me(state).get("helped") == turn:
            raise Refused("they've already worked here this turn")
        me(state)["helped"] = turn
    elif me(state).get("worked") == room["id"]:
        raise Refused("the player has already worked here this visit; there's work again after they leave and come back")
    me(state)["worked"] = room["id"]
    ok = True
    test = (job["stat"], job["dc"]) if job else (shared["stat"], shared["dc"]) if shared["dc"] is not None else None
    if test:
        mod = attempt_mod(state, actor_id(state), test[0])
        ok, nat, total, note = d20_test(mod, test[1])
        print("WORK %s vs DC %d: d20 %d %+d = %d%s -> %s"
              % (test[0], test[1], nat, mod, total, note, "SUCCESS" if ok else "FAILURE"))
    if shared:
        help_with(state, shared, ok)
    if job and ok:
        pay = job["low"] + dice.roll("1d%d" % (job["high"] - job["low"] + 1))[0] - 1
        change_coins(state, pay, "work", room["id"])
        print("PAID: %d %s for the work. COINS +%d -> %d" % (pay, currency(), pay, me(state)["stats"]["coins"]))
    elif job:
        print("NOT PAID: the work went wrong this time; %s." % ("there's more to do next turn" if shared else "nothing more here until the next visit"))
    save_state(state)


def help_with(state, shared, ok):
    """A turn of someone's effort on shared work: it counts for them whatever came of it, moves the work on when it
    went well, sets each stage's flag once the work reaches it, and earns a meal where the work gives one."""
    pid, rec = actor_id(state), project_state(state, shared["id"])
    rec["by"][pid] = rec["by"].get(pid, 0) + 1
    if ok:
        rec["total"] += 1
    log(state, "effort", project=shared["id"], moved=ok, total=rec["total"], theirs=rec["by"][pid])
    print("EFFORT on %s: %s has given it %d turn%s; %d done in all%s" % (shared["name"], me(state)["name"], rec["by"][pid],
          "" if rec["by"][pid] == 1 else "s", rec["total"], "" if ok else " (this one moved nothing on, but it counts as their effort)"))
    for amount, flag in shared["stages"]:
        if rec["total"] >= amount and flag not in rec["stages"]:
            rec["stages"].append(flag)
            set_flag(state, flag)
            log(state, "project", project=shared["id"], stage=flag, total=rec["total"])
            print("STAGE: %s has come to %d: flag set: %s" % (shared["name"], amount, flag))
    if shared["meal"] and "food" in world_needs():
        met(state, "food", shared["id"], "work")
        print("FED: the work there comes with a meal; they've eaten today.")


def cmd_sell(args):
    """sell <item> [<buyer>]: the player sells a carried item to a buyer here, at the buyer's price for its tier.
    Only things with a tier (made to order, or found) are bought; the world's own things are not."""
    state = load_state()
    require_playing(state)
    ident = args[0]
    if ident not in me(state)["inventory"]:
        raise Refused("you are not carrying %s" % ident)
    buyers = [c for c in characters_here(state) if buys(c)]
    if len(args) > 1:
        if args[1] not in buyers:
            raise Refused("%s isn't a buyer here (buyers here: %s)" % (args[1], ", ".join(buyers) or "none"))
        buyer = args[1]
    elif len(buyers) == 1:
        buyer = buyers[0]
    elif buyers:
        raise Refused("say who buys it: sell <item> <buyer> (buyers here: %s)" % ", ".join(buyers))
    else:
        raise Refused("nobody here buys things")
    who, tier = ent("characters", buyer).get("name", buyer), item(ident).get("tier")
    prices = buys(buyer)
    if tier not in prices:
        raise Refused("%s doesn't buy %s: %s" % (who, ident, "they buy %s" % ", ".join(t.replace("_", " ") for t in prices)
                      if tier else "it has no tier (only things made or found are bought)"))
    remove_from_inventory(state, ident)
    log_use(state, ident, "sold to %s" % buyer)
    change_coins(state, prices[tier], "sale", ident)
    save_state(state)
    print("SOLD: %s to %s for %d %s. COINS +%d -> %d"
          % (ident, who, prices[tier], currency(), prices[tier], me(state)["stats"]["coins"]))


def why_not_promoted(state, ident, count):
    """Why a generated person isn't promoted to their own agent now, or None when they are due."""
    switch = SETTINGS["promotion"]
    if not switch["on"]:
        return "promotion is off in this game's settings"
    if count < int(switch["after_conversations"]):
        return "%d of %d conversations" % (count, int(switch["after_conversations"]))
    if sum(1 for rec in state["run"]["characters"].values() if rec["meta"].get("promoted") == "yes"
           and not rec["meta"].get("carried")) >= int(switch["max_per_run"]):
        return "this run has promoted as many people as it may"
    if agents_resting(ident):
        return agents_resting(ident)
    if not can_pay("promote"):
        return "the meter can't pay for it"
    return None


def cmd_talk(args):
    """talk <generated person>: run before voicing a generated person in a scene. Counts one conversation per
    scene; after the owner's number of them, the person is promoted to their own agent, with their own memory
    of the player, for the rest of the run (and comes back that way in later runs)."""
    state = load_state()
    require_playing(state)
    ident, run = args[0], state["run"]
    if ident not in characters_here(state):
        raise Refused("%s isn't here" % ident)
    if not is_generated("characters", ident):
        raise Refused("%s is authored: voice them as `look` marks them, without `talk`" % ident)
    t = run.setdefault("talks", {}).setdefault(ident, {"count": 0, "scene": None})
    if t["scene"] != run["moves"]:  # one conversation per scene: a scene lasts until the player moves
        t.update(count=t["count"] + 1, scene=run["moves"])
    name = ent("characters", ident).get("name", ident)
    promoted = is_minor(ident) and why_not_promoted(state, ident, t["count"]) is None
    if promoted:
        run["characters"][ident]["meta"].update(minor="no", promoted="yes")
        charge("promote")
        memory = npc_memory_of(state, ident)
        data = lib()
        library.promote(data, ident, memory[-1] if memory else "Kept coming back to talk with me.")
        lib_save(data)
    save_state(state)
    if promoted:
        print("PROMOTED: %s now speaks through their own agent, with their own memory of the player. From this exchange on "
              "they're [agent]: ask them with `tools/voice.py npc %s <scene file>` (see gm-turn)." % (name, ident))
    elif not is_minor(ident):
        print("TALK: %s speaks through their own agent: ask them with `tools/voice.py npc %s <scene file>` (see gm-turn)." % (name, ident))
    else:
        print("TALK: voice %s yourself, from this (conversation %d):" % (name, t["count"]))
        cmd_show(["characters", ident])


def cmd_library(args):
    """library suggest <id> <why>: tell the owner a generated or player-made thing deserves keeping for good.
    The owner decides (tools/library.py); this only marks the entry."""
    if args[0] != "suggest" or len(args) < 3:
        raise Refused("use: library suggest <id> <one short line why>")
    data = lib()
    e = data["entries"].get(args[1])
    if not e:
        raise Refused("%s isn't in the library (only generated and player-made things are)" % args[1])
    e["suggested"] = short_line(" ".join(args[2:]), "library suggest")
    lib_save(data)
    print("SUGGESTED for keeping: %s (%s). The owner decides." % (e["record"]["meta"].get("name", args[1]), e["suggested"]))


def cmd_post(args):
    """post <file> | post take <n>: the person puts up a notice on the board where they stand, in their own words (from
    a file), or takes down one of their own (n as `look` numbers the board, 1 the newest)."""
    state = load_state()
    require_playing(state)
    room, pid = room_here(state), actor_id(state)
    if not has_board(room):
        raise Refused("there's no notice board here")
    if args[0] == "take":
        board = list(reversed(notices(state, room["id"])))
        if len(args) < 2 or not args[1].isdigit() or not 1 <= int(args[1]) <= len(board):
            raise Refused("usage: post take <n>, n as `look` numbers the board's notices (1 is the newest)")
        notice = board[int(args[1]) - 1]
        if notice["by"] != pid:
            raise Refused("that notice isn't theirs to take down")
        state["run"]["boards"][room["id"]].remove(notice)
        log(state, "notice", room=room["id"], text=notice["text"], taken=True)
        save_state(state)
        print("TAKEN DOWN from the board: %s" % notice["text"])
        return
    text = " ".join(text_arg(args[0], "notice", generate.NOTICE_CHARS).split())
    put_up(state, room["id"], text, pid)
    log(state, "notice", room=room["id"], text=text)
    save_state(state)
    print("PUT UP on the board at %s: %s" % (room.get("name", room["id"]), text))


def cmd_note(args):
    """note <text>: record a small detail you established about this room, so it stays true."""
    state = load_state()
    text = short_line(" ".join(args), "note")
    notes = state["run"]["notes"].setdefault(me(state)["location"], [])
    notes.append(text)
    del notes[:-BALANCE["world"]["notes_per_room"]]
    save_state(state)
    print("NOTED for %s: %s" % (me(state)["location"], text))


def quests_in_reach(state):
    """The quests the acting person could take on: the world's own, and side jobs from someone they've met."""
    return [q for q in ent_ids("quests") if not is_generated("quests", q) or ent("quests", q).get("giver") in me(state).get("met", [])]


def cmd_quest(args):
    """quest take|leave <quest>: the person has taken a quest on (they mean to work on it, or agreed to the job), so
    it shows in their "What you're working on"; or they've set it aside. Everyone knows the world's problem; caring
    about it is their own."""
    state = load_state()
    require_playing(state)
    if len(args) != 2 or args[0] not in ("take", "leave"):
        raise Refused("usage: quest take|leave <quest>")
    q, pl = args[1], me(state)
    if not ent_exists("quests", q):
        raise Refused("no quest %r" % q)
    taken = pl.setdefault("taken_on", [])
    name = ent("quests", q).get("name", q)
    if args[0] == "take":
        if q not in quests_in_reach(state):
            raise Refused("%s hasn't met whoever gives %s" % (pl["name"], q))
        if q in taken:
            raise Refused("%s has already taken on %s" % (pl["name"], name))
        taken.append(q)
    else:
        if q not in taken:
            raise Refused("%s hasn't taken on %s" % (pl["name"], name))
        taken.remove(q)
    save_state(state)
    print("%s: %s %s" % ("TAKEN ON" if args[0] == "take" else "SET ASIDE", name, "now shows in what %s is working on" % pl["name"]
                         if args[0] == "take" else "no longer shows in what %s is working on" % pl["name"]))


OUTCOMES = {"done": "done", "partly": "partly done", "failed": "failed a check", "refused": "refused by someone",
            "out_of_reach": "out of reach", "not_there": "reached for something that isn't there"}


def cmd_outcome(args):
    """outcome <done|partly|failed|refused|out_of_reach|not_there> [<what>]: what the turn came to, for the record only
    (never told, never acted on): the referee's own word on the person's turn, which the audit counts. Out of reach
    and not there name what was reached for. Run again in the same turn, the last one stands."""
    state = load_state()
    require_playing(state)
    pid, rs = actor_id(state), state["run"].get("round_state")
    if not rs or whose_turn(state) != pid:
        raise Refused("an outcome is for the turn being played; it's no one's turn now" if not rs else "it isn't %s's turn" % me(state)["name"])
    if args[0] not in OUTCOMES:
        raise Refused("outcome %s [<what>]" % "|".join(OUTCOMES))
    what = " ".join(args[1:]).strip()
    if args[0] in ("out_of_reach", "not_there") and not what:
        raise Refused("say what was reached for: outcome %s <what>" % args[0])
    what = short_line(what, "outcome") if what else None
    rs.setdefault("outcomes", {})[pid] = args[0]
    log(state, "outcome", result=args[0], what=what)
    save_state(state)
    print("OUTCOME for %s: %s%s" % (me(state)["name"], OUTCOMES[args[0]], ": %s" % what if what else ""))


def cmd_chronicle(args):
    """chronicle <text>: one line for the story so far."""
    state = load_state()
    text = short_line(" ".join(args), "chronicle")
    state["run"]["chronicle"].append(text)
    save_state(state)
    print("CHRONICLED: %s" % text)


def _section(body, title):
    for heading, text in content.sections(body):
        if heading.lower() == title.lower():
            return text
    return ""


def settled_lines(state):
    """What this run has settled, for the world agent's off-screen turn: each quest ending told, in the words everyone
    heard, and each shared work finished, so its rumours never say otherwise once they've left the story so far."""
    out = []
    for q, e in state["run"].get("endings", {}).items():
        out.append("%s: %s" % (ent("quests", q).get("name", q), e.get("text") or e["outcome"]))
    rooms = project_rooms()
    for ident, rec in state["run"].get("projects", {}).items():
        shared = project_of(ent("rooms", rooms[ident])) if ident in rooms else None
        if shared and shared["stages"] and shared["stages"][-1][1] in rec["stages"]:
            out.append("%s: done" % shared["name"])
    return out


def cmd_world_brief(args):
    """world-brief <extra|room|item|character|quest|turn>: the prompt for the world agent."""
    state = load_state()
    request = args[0]
    if request not in tuple(generate.KINDS) + ("turn",):
        raise Refused("request must be one of %s, turn" % ", ".join(generate.KINDS))
    pol = policy()
    maker = None
    if request in ORDER_KINDS:
        if len(args) < 2:
            raise Refused("usage: world-brief %s <%s>" % (request, "maker" if request == "craft" else "builder"))
        maker = args[1]
        if maker not in characters_here(state):
            raise Refused("%s isn't here to take an order" % maker)
        if request == "craft" and not makes(maker):
            raise Refused("%s makes nothing to order; they turn the request away in character" % maker)
        if request == "build" and not builds(maker):
            raise Refused("%s builds nothing to order; they turn the request away in character" % maker)
        if request == "build" and not build_spots(state, room_here(state)):
            raise Refused("there's nowhere here that anything could be built; %s says so in character" % maker)
        why = why_no_order(state, request)
        if why:
            raise Refused("%s; %s turns the order away in character" % (why, maker))
    elif request != "turn" and not pol[{"extra": "extras", "room": "rooms", "item": "items",
                                        "character": "characters", "quest": "side_quests"}[request]]:
        raise Refused("no new %ss can appear in this game (its content or the owner's settings rule them out): "
                      "it doesn't exist" % request)
    if request == "turn" and not SETTINGS["world_turns"]["on"]:
        raise Refused("world turns are off in this game's settings; nothing happens off-screen")
    cost = {"turn": "world_turn", "craft": "craft", "build": "build"}.get(request, "generate")
    if not can_pay(cost):
        raise Refused("the %s is spent until the next session, so nothing new turns up: it doesn't exist"
                      % resource()["name"].lower())
    w = world()
    if request != "turn" and no_one(state):
        actor_id(state)  # anything but a world turn is for the player acting: refused without --as
    room = {} if no_one(state) else room_here(state)
    if request == "room" and not unused_expansions(room):
        raise Refused("%s has no direction left where a new place could be; "
                      "the way the player wants doesn't exist" % room.get("name", room["id"]))
    flags = condition_flags(state)
    run = state["run"]
    out = ["# World brief: %s" % request, "",
           "## The adventure", "%s. %s" % (w.get("title", ""), _section(w["body"], "Tone")), "",
           "## What everyone around here knows", _section(w["body"], "Public knowledge") or "(nothing listed)", ""]
    if has_days():  # life off-screen keeps the hours: who's asleep, who's at work
        out += ["## Now", ", ".join(x for x in (when_text(state), state["run"].get("weather")) if x), ""]
    if room:
        desc = [room["body"].split("\n## ")[0].strip()]
        for heading, text in content.sections(room["body"]):
            cond = content.section_condition(heading)
            if cond and content.condition_holds(cond, flags):
                desc.append(text)
        out += ["## Where the player is", "%s. %s" % (room.get("name", room["id"]), " ".join(desc))]
    else:
        out += ["## Where the players are", "; ".join("%s (%s) at %s" % (state["players"][p]["name"], pronouns(p), ent(
            "rooms", state["players"][p]["location"]).get("name", state["players"][p]["location"])) for p in playing(state)) + "."]
    notes = run["notes"].get(room.get("id"), [])
    if notes:
        out += ["Established details: " + " | ".join(notes)]
    texture = [x for x in (when_text(state), run.get("weather")) if x]
    if texture:
        out += ["Time and weather: " + ", ".join(texture)]
    out += ["", "## Names and ids already in use (never reuse or imitate them)"]
    for kind in ("rooms", "characters", "items", "quests"):
        out.append("- %s: %s" % (kind, ", ".join("%s (%s)" % (i, ent(kind, i).get("name", i)) for i in ent_ids(kind))))
    if run["chronicle"]:
        out += ["", "## The story so far"] + ["- " + c for c in run["chronicle"][-6:]]
    settled = settled_lines(state) if request == "turn" else []
    if settled:
        out += ["", "## What's settled (never say otherwise)"] + ["- " + x for x in settled]
    fits, lib_data = [], None
    if request in REQUEST_KIND:
        kind = REQUEST_KIND[request]
        lib_data = lib()
        fits = library.fitting(lib_data, kind, request == "extra", room["id"], set(ent_ids(kind)),
                               int(BALANCE["library"]["brief_entries"]))
        if fits:
            out += ["", "## From earlier runs (bring one back if it fits here, rather than inventing)"]
            out += ["- %s: %s" % (i, library.summary(lib_data["entries"][i])) for i in fits]
        run["brief"] = request
    out += ["", "## Your task"]
    g = BALANCE["generation"]
    out += ["Limits: ids 3-30 characters; names up to 40; each line of 'knows' or 'rumors' up to 160 characters, at most 3 lines;",
            "roles up to 80; look and speech up to 200; personality and summary up to 300; room descriptions up to 900.", ""]
    if request == "turn":
        people = ["%s (%s), now at %s" % (c, ent("characters", c).get("name", c),
                                         next((r for r, ps in run["placements"].items() if c in ps), "?"))
                  for c in run["characters"]]
        built = ["%s (%s)" % (r, ent("rooms", r).get("name", r)) for r in run["rooms"] if made_by("rooms", r) == "player"]
        planned = open_steps(state)
        out += ["Time passes off-screen. Write what people around here start saying, based only on the story so far,",
                "public knowledge and what's settled, and optionally move generated people to another room that exists.",
                "Generated people: %s" % (", ".join(people) or "none"),
                "Places the player had built (people may start using them, and talking about them): %s" % (", ".join(built) or "none"),
                "Rooms: %s" % ", ".join(ent_ids("rooms"))]
        if planned:
            out += ["", "People with plans may each do one of the things listed for them, or nothing. Choose only what fits",
                    "the story so far and the moment; often most of them carry on as they are. Never invent a step."]
            for c, steps in planned.items():
                at = where_is(c, condition_flags(state))
                out.append("- %s (%s), now at %s: %s" % (c, ent("characters", c).get("name", c),
                                                       ent("rooms", at).get("name", at) if at else "somewhere out of the way",
                                                       "; ".join("%s (%s)" % (st["step"], st["does"]) for st in steps)))
            out += ["Their rumors are taken care of: don't write gossip about what they do.", ""]
        boards = [r for r in ent_ids("rooms") if has_board(ent("rooms", r))]
        if boards:
            out += ["", "Notice boards (newest first). You may put up at most one notice, as a townsperson or a passing stranger",
                    "would, signed. Never offer work, goods or rewards the town doesn't already have."]
            out += ["- %s (%s): %s" % (r, ent("rooms", r).get("name", r), " | ".join(n["text"] for n in reversed(notices(state, r)))
                                       or "nothing put up") for r in boards] + [""]
        out += ['JSON: {"rumors": ["<up to 3 short lines of gossip>"], "moves": [{"id": "<generated person>", "room": "<room id>"}]%s%s}'
                % (', "plans": [{"who": "<character id>", "step": "<step>"}]' if planned else "",
                   ', "notices": [{"room": "<a room with a board>", "text": "<one notice, up to %d characters>"}]'
                   % generate.NOTICE_CHARS if boards else "")]
    elif request == "extra":
        out += ["Make the unnamed person the player is addressing into someone specific, consistent with this place.",
                "They know ONLY public knowledge, what anyone here could see, and gossip; no secrets, no clues beyond that.",
                'JSON: {"id": "<new_id>", "name": "<name>", "role": "<what they are, a few words>", "look": "<one line>",',
                '       "speech": "<how they talk>", "knows": ["<up to 3 short lines>"]}']
    elif request == "room":
        out += ["Make the new place the player is heading into, %s from here." % " or ".join(unused_expansions(room)),
                "It is small and self-contained. It must not hold anything the main quest needs, and nothing that solves it.",
                "Items get a tier, never numbers: %s. Up to 2 items and 1 character (see the character schema; optional)." % ", ".join(g["item_tiers"]),
                "Its terrain is one of: %s (optional; it defaults to this room's)." % ", ".join(content.look().get("terrain") or {}),
                'JSON: {"id": "<new_id>", "name": "<name>", "direction": "<%s>", "terrain": "<terrain>", "description": "<what the player sees, 2-4 sentences>",' % "|".join(unused_expansions(room)),
                '       "items": [{"id": "...", "name": "...", "description": "...", "tier": "<tier>"}], "characters": []}']
    elif request == "item":
        out += ["Make one small thing the player finds here by searching. Modest: not a key to anything, not quest-related.",
                "Tiers (stats come from the tier): %s." % ", ".join(g["item_tiers"]),
                'JSON: {"id": "<new_id>", "name": "<name>", "description": "<one or two sentences>", "tier": "<tier>"}']
    elif request == "character":
        out += ["Make a minor character who would plausibly be here. They know only public knowledge and their own life.",
                "Optional: up to 2 trades of new items (price 1-6 coins), and a fighting tier (%s) only if they would fight." % ", ".join(g["foe_tiers"]),
                'JSON: {"id": "...", "name": "...", "role": "...", "personality": "...", "speech": "...", "knows": ["..."],',
                '       "wants": "...", "trades": [{"item": {"id": "...", "name": "...", "description": "...", "tier": "..."}, "price": 2}], "tier": null}']
    elif request == "craft":
        ch = ent("characters", maker)
        who = ch.get("name", maker)
        out += ["The player is ordering something from %s (%s). Shape what they ask for into one item %s would make."
                % (who, ch.get("role", ""), who),
                "%s makes only these kinds of thing (an item's stats come from its kind, never from you): %s."
                % (who, ", ".join(makes(maker)))]
        trade = next((t for h, t in content.sections(ch["body"]) if re.fullmatch(r"What \w+ makes?", h)), "")
        if trade:
            out.append("Their trade: " + " ".join(trade.split()))
        out += ["Keep the player's idea, and their name for it if they gave one. It is modest: nothing beyond its kind,",
                "and nothing the main quest needs. If the request is outside the trade, or would solve or shortcut the main",
                "quest, turn it down instead.",
                'JSON: {"id": "<new_id>", "name": "<name>", "description": "<one or two sentences>", "tier": "<%s>"}' % "|".join(makes(maker)),
                'or, to turn it down: {"refuse": "<why, in a few words>"}']
        run["ordering"] = order_asked(state, maker, "craft")
    elif request == "build":
        ch = ent("characters", maker)
        who, spots = ch.get("name", maker), build_spots(state, room)
        out += ["The player is asking %s (%s) to build something here. Where it can go:" % (who, ch.get("role", ""))]
        out += ["- %s: %s" % kv for kv in spots.items()]
        trade = next((t for h, t in content.sections(ch["body"]) if re.fullmatch(r"What \w+ builds?", h)), "")
        if trade:
            out.append("What %s builds: %s" % (who, " ".join(trade.split())))
        out += ["Shape what they ask for into one small place that fits that spot, and keep the name they gave it if any.",
                "It starts empty (no items, no people), and it must not hold or replace anything the main quest needs.",
                "If the request doesn't fit the spot or the builder, turn it down instead.",
                "Its terrain is one of: %s (optional; it defaults to this room's)." % ", ".join(content.look().get("terrain") or {}),
                'JSON: {"id": "<new_id>", "name": "<name>", "direction": "<%s>", "terrain": "<terrain>",' % "|".join(spots),
                '       "description": "<what the player will see there, 2-4 sentences>"}',
                'or, to turn it down: {"refuse": "<why, in a few words>"}']
        run["ordering"] = order_asked(state, maker, "build")
    elif request == "quest":
        here = characters_here(state)
        out += ["Make a small side quest offered by someone present (%s). It must not touch the main quest." % ", ".join(here or ["no one"]),
                "Its flags are its own: side_<quest id>_<word>. Conditions may also use has_<item> and met_<character>.",
                "Reward: 0-%d coins and optionally one new item (a tier)." % g["side_quest_max_coins"],
                'JSON: {"id": "...", "name": "...", "giver": "<id>", "summary": "...",',
                '       "objectives": [{"text": "...", "done_when": "side_<id>_<word>"}], "reward": {"coins": 2, "item": null}}']
    if fits:
        out.append('or, to bring one back from earlier runs: {"reuse": "<id from that list>"%s}'
                   % (', "direction": "<%s>"' % "|".join(unused_expansions(room)) if request == "room" else ""))
    out += ["", "Reply with the JSON object only."]
    charge(cost)
    save_state(state)
    print("\n".join(out))


def cmd_world_turn(args):
    """world-turn [file]: apply the world agent's off-screen turn (JSON on stdin)."""
    state = load_state()
    try:
        proposal = read_json_arg(args)
        try:
            patch = generate.world_turn(proposal, gen_context(state))
        except ValueError as e:
            raise Refused("world turn rejected: %s" % e)
        except MALFORMED[1:] as e:
            raise Refused("world turn rejected: it doesn't match the JSON shape in the brief (%s)" % e)
    finally:
        done_with(args)
    run = state["run"]
    run["rumors"].extend(patch["rumors"])
    del run["rumors"][:-BALANCE["world"]["rumors_kept"]]
    for mv in patch["moves"]:
        for people in run["placements"].values():
            if mv["id"] in people:
                people.remove(mv["id"])
        run["placements"].setdefault(mv["room"], []).append(mv["id"])
    done = []
    for p in patch["plans"]:
        lines = apply_plan(state, p["who"], next(st for st in plan_steps(p["who"]) if st["step"] == p["step"]))
        if lines:
            done += [l for l in lines if l not in done]
    for n in patch["notices"]:
        put_up(state, n["room"], n["text"], None)
    run["world_turn_due"] = False
    save_state(state)
    print("WORLD TURN: %d rumors, %d moves%s" % (len(patch["rumors"]), len(patch["moves"]),
                                              ", 1 notice" if patch["notices"] else ""))
    for n in patch["notices"]:
        print("  notice put up at %s: %s" % (n["room"], n["text"]))
    for r in patch["rumors"]:
        print("  rumor: %s" % r)
    for mv in patch["moves"]:
        print("  %s is now at %s" % (mv["id"], mv["room"]))
    for line in done + ending_lines(state):
        print(line)


OPEN_KEYS = ("terrain", "by_command")  # a game may add its own terrain kinds and command phrases


def unknown_keys(over, base, where, problems):
    """Keys in a game's JSON that the kit's defaults don't have: almost always a typo."""
    for k, v in over.items():
        if k not in base:
            problems.append("%s: unknown key %r (known: %s)" % (where, k, ", ".join(base)))
        elif isinstance(v, dict) and isinstance(base[k], dict) and base[k] and k not in OPEN_KEYS:
            unknown_keys(v, base[k], "%s %s" % (where, k), problems)


WARNINGS = []  # what validate_game found that a world may live with (printed as warnings; errors under --sim-strict)


def world_warnings(w):
    """Two lessons of the runs (SIM-WORLD-SPEC.md section 2, 1 and 8), as warnings: a character's conditional text or
    plan that turns on the story's flags but never on how its quest ended (Tibbersnatch craved the whistle after the
    shadows were freed), and "the player" in what a townsperson's own agent reads (worlds written for one hero)."""
    ends, out = set(), []
    for q in content.ids("quests"):
        meta = content.load("quests", q)
        for k in ("completed_by", "failed_by"):
            ends.update(generate.TERM.findall(str(meta.get(k) or "")))
    for c in content.ids("characters"):
        body = content.load("characters", c)["body"]
        conds = [(h, content.section_condition(h)) for h, _ in content.sections(body) if content.section_condition(h)]
        conds += [("Plan: %s" % st["step"], st["when"]) for st in content.plans(body) if st.get("when")]
        for heading, cond in conds:
            terms = set(generate.TERM.findall(cond))
            story = {x for x in terms if not x.startswith(AUTOMATIC) and not x.startswith(c + "_")}
            if ends and story and not terms & ends:
                out.append("characters/%s.md: `## %s` never asks how the quest ended (%s): after it ends, it still holds"
                           % (c, heading, ", ".join(sorted(ends))))
        read = [body.split("\n## ")[0]] + [text for h, text in content.sections(body) if not h.lower().startswith("gm") and not content.is_plan(h)]
        n = sum(len(re.findall(r"\bthe player\b", x, re.I)) for x in read)
        if n:
            out.append("characters/%s.md: says \"the player\" %d time%s where their agent reads it: say who they are to them instead"
                       % (c, n, "" if n == 1 else "s"))
    return out


def validate_sim_strict(w, problems):
    """What a world built for the simulation needs (SIM-WORLD-SPEC.md section 5), beyond --sim-complete: days that go
    on, needs and what meets them, things for sale, shared work, a quest, something scarce, public knowledge, nothing
    written for a lone hero. What only a reader can judge (each kind of want served; public knowledge never saying
    which places pay or who buys) the spec lists for a human read. `validate --sim-strict`."""
    people = [content.load("characters", c) for c in content.ids("characters")]
    rooms = [content.load("rooms", r) for r in content.ids("rooms")]
    if str(w.get("days", "no")).lower() != "yes":
        problems.append("sim-strict: needs days that go on (days: yes)")
    if not options_of(w.get("needs") or []):
        problems.append("sim-strict: needs at least one need (needs:), and something to meet it")
    if not any(c.get("sells") for c in people):
        problems.append("sim-strict: needs someone who sells things at set prices (sells:)")
    if not any(r.get("project") for r in rooms):
        problems.append("sim-strict: needs shared work (a room's project:)")
    if not content.ids("quests"):
        problems.append("sim-strict: needs a quest (a problem or mystery of its own size, beside the shared work)")
    if not any(rent_of(r) for r in rooms) and not any(_SELLS.match(str(v).strip()) and _SELLS.match(str(v).strip()).group(2)
                                                       for c in people for v in (c.get("sells") or {}).values()):
        problems.append("sim-strict: needs something scarce: a place to let (rent:), or a thing in short stock (\"<price>, <n> in stock\")")
    if not public_knowledge():
        problems.append("sim-strict: needs public knowledge (world.md ## Public knowledge): what everyone around here knows")
    if any(h.strip().lower() == "who the player is" for h, _ in content.sections(w["body"])):
        problems.append("sim-strict: world.md has `## Who the player is`: a world for the cast is written for no lone hero")
    problems += ["sim-strict: " + x for x in world_warnings(w)]


def validate_game(kit=False, sim=False, strict=False):
    """Every problem in the active game's content: references, formats, soundness, and its JSON settings. With `kit`,
    also everything a world needs for every kit feature to work in it (what a forged world must pass); with `sim`,
    everything a simulation needs (`validate_sim_complete`)."""
    problems = []
    for name, base in (("look.json", content.kit_look()), ("balance.json", content.kit_balance())):
        try:
            data = content.game_json(name)
        except ValueError as e:
            problems.append("%s: not valid JSON (%s)" % (name, e))
            continue
        unknown_keys(data, base, name, problems)
    presets = content.kit_presets()
    try:
        own = content.game_json("settings.json")
    except ValueError as e:
        own = {}
        problems.append("settings.json: not valid JSON (%s)" % e)
    unknown_keys(own, {"preset": "", "overrides": {}}, "settings.json", problems)
    if own.get("preset", "normal") not in presets:
        problems.append("settings.json: unknown preset %r (presets: %s)" % (own.get("preset"), ", ".join(presets)))
    overrides = own.get("overrides") or {}
    unknown_keys(overrides, presets["normal"], "settings.json overrides", problems)
    merged = content.deep_merge(presets.get(own.get("preset", "normal"), presets["normal"]), overrides)
    for key, allowed in (("rounds.clock", ("move", "round")), ("memory.condenser", ("self", "neutral")),
                         ("memory.thinkback_sees", ("who_i_am", "voice")),
                         ("cast.model", tuple(BALANCE["cast"]["models"]) + ("own",))):
        section, name = key.split(".")
        if (merged.get(section) or {}).get(name) not in allowed:
            problems.append("settings.json: %s must be %s" % (key, " or ".join(allowed)))
    most = (merged.get("memory") or {}).get("learned_max")
    if not isinstance(most, int) or isinstance(most, bool) or most < 1:
        problems.append("settings.json: memory.learned_max must be a whole number, at least 1")
    cap = (merged.get("rounds") or {}).get("max_per_run")
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 0:
        problems.append("settings.json: rounds.max_per_run must be a whole number (0 for no limit)")
    every = (merged.get("rounds") or {}).get("time_every")
    if str(world().get("days", "no")).lower() == "yes" and (not isinstance(every, int) or every < 1):
        problems.append("settings.json: a world with days: yes needs rounds.time_every of 1 or more (ticks to each time of day)")
    for c in ((overrides.get("npc_agents") or {}).get("characters") or {}):
        if not content.exists("characters", c):
            problems.append("settings.json npc_agents characters: unknown character %r" % c)
        elif str(content.load("characters", c).get("minor", "no")).lower() == "yes":
            problems.append("settings.json npc_agents characters: %r is minor, so it never has an agent" % c)
    look = content.look()
    color = re.compile(r"^(#[0-9a-fA-F]{6}|[a-z]+)$")
    terrains = look.get("terrain") or {}
    for name, t in terrains.items():
        for k in ("bg", "fg"):
            if not color.match(str((t or {}).get(k, ""))):
                problems.append("look.json terrain %s: %s must be a color like #1f4060" % (name, k))
    sounds_dir = ROOT / "mod" / "sounds"  # the mod's sound bank; without the mod there's nothing to check against
    bank = {p.stem for p in sounds_dir.glob("*.wav")}
    for beat, sound in (look.get("sounds") or {}).items() if sounds_dir.is_dir() else ():
        if sound is not None and sound not in bank:
            problems.append("look.json sounds %s: no kit sound %r (the bank: %s)" % (beat, sound, ", ".join(sorted(bank))))
    times = world().get("times") or []
    for t in (look["palette"].get("accent_by_time") or {}):
        if t not in times:
            problems.append("look.json palette accent_by_time: %r is not one of world.md's times" % t)
    for r in content.ids("rooms"):
        room = content.load("rooms", r)
        if room.get("terrain") is not None and room["terrain"] not in terrains:
            problems.append("rooms/%s.md: terrain %r isn't in the look's terrain (%s)" % (r, room["terrain"], ", ".join(terrains)))
        if room.get("color") is not None and not color.match(str(room["color"])):
            problems.append("rooms/%s.md: color must look like #4a6b8a" % r)
    speakers = look.get("speaker_colors")
    if not isinstance(speakers, list) or not speakers or not all(color.match(str(x)) for x in speakers):
        problems.append("look.json speaker_colors: must be a list of colors like #8fae4a")
    for key, label in (look.get("sections") or {}).items():
        if not isinstance(label, str) or not label.strip():
            problems.append("look.json sections: %s needs a label" % key)
    for c in content.ids("characters"):
        card = content.load("characters", c).get("card")
        if card is not None and not color.match(str(card)):
            problems.append("characters/%s.md: card must be a color like #8fae4a" % c)
    for t in look.get("tabs") or []:
        if t not in ("here", "map", "journal"):
            problems.append("look.json tabs: unknown tab %r (tabs: here, map, journal)" % t)
    keys = look.get("tab_keys") or {}
    for tab, key in keys.items():
        # the margin's own keys are l (look around), g (the guide) and 1-9 (the ways out); a mod's hotkey must be one letter
        if not re.fullmatch(r"[a-z]", str(key)) or key in ("l", "g"):
            problems.append("look.json tab_keys: %s's key must be one lowercase letter other than l and g (the margin's own)" % tab)
    if len(set(keys.values())) < len(keys):
        problems.append("look.json tab_keys: two tabs share a key")
    for stat in STATS:
        if not str(look["stat_labels"].get(stat, "")).strip():
            problems.append("look.json stat_labels: %s needs a label" % stat)

    def need(kind, ident, where):
        if not content.exists(kind, ident):
            problems.append("%s: unknown %s %r" % (where, kind[:-1], ident))

    def need_dice(spec, where):
        try:
            dice.parse(spec)
        except ValueError as e:
            problems.append("%s: %s" % (where, e))

    w = content.load_world()
    need("rooms", w.get("start_room", ""), "world.md start_room")
    for i in (w.get("inventory") or []):
        need("items", i, "world.md inventory")
    for k, spec in (w.get("rolls") or {}).items():
        need_dice(spec, "world.md rolls %s" % k)
    variant_flags = set()
    for name, opts in (w.get("variants") or {}).items():
        if len(options_of(opts)) < 2:
            problems.append("world.md variants %s: needs at least two comma-separated flags" % name)
        variant_flags.update(options_of(opts))
    personal = set(options_of(w.get("personal_flags") or []))
    for f in sorted(personal):
        if not re.fullmatch(r"[a-z][a-z0-9_]*", f) or f.startswith(AUTOMATIC):
            problems.append("world.md personal_flags: %r isn't a flag content can set" % f)

    def placing(cond, where):
        """A personal flag may not decide where things are: each person would see a different world."""
        hit = personal & set(generate.TERM.findall(str(cond or "")))
        if hit:
            problems.append("%s: %s is personal, so it can't decide where things are or what happens off-screen"
                            % (where, ", ".join(sorted(hit))))
    for f in sorted(personal & variant_flags):
        placing(f, "world.md variants")
    for k in ("flag", "also_flag", "also_if"):
        placing((w.get("clock") or {}).get(k), "world.md clock %s" % k)
    for r in content.ids("rooms"):
        room = content.load("rooms", r)
        for key in ("exits", "items", "characters"):
            values = room.get(key) or []
            for v in (values.values() if isinstance(values, dict) else values):
                placing(content.split_condition(v)[1], "rooms/%s.md %s" % (r, key))
    for c in content.ids("characters"):
        for step in content.plans(content.load("characters", c)["body"]):
            for key in ("when", "sets", "clears"):
                placing(step.get(key), "characters/%s.md plan %s" % (c, key))
    if w.get("clock"):
        for k in ("name", "moves", "flag"):
            if k not in w["clock"]:
                problems.append("world.md clock: missing %s" % k)
        need_dice(w["clock"].get("moves", "1"), "world.md clock moves")
        if bool(w["clock"].get("also_if")) != bool(w["clock"].get("also_flag")):
            problems.append("world.md clock: also_if and also_flag go together")
    for k, v in (w.get("generation") or {}).items():
        if k not in GEN_KINDS:
            problems.append("world.md generation: unknown kind %r (kinds: %s)" % (k, ", ".join(GEN_KINDS)))
        elif str(v).lower() not in (("yes", "no", "marked", "anywhere") if k == "rooms" else ("yes", "no")):
            problems.append("world.md generation %s: %r should be %s" % (k, v, "yes, no, marked or anywhere" if k == "rooms" else "yes or no"))
    try:
        pos = layout()
    except Refused:
        pos = {}  # the map can't be laid out from a missing room; that's reported above or below
    claimed = {}
    for r in content.ids("rooms"):
        room = content.load("rooms", r)
        where = "rooms/%s.md" % r
        for d, t in (room.get("exits") or {}).items():
            need("rooms", content.split_condition(t)[0], where + " exit " + d)
        for i in (room.get("items") or []):
            need("items", content.split_condition(i)[0], where + " items")
        for c in (room.get("characters") or []):
            need("characters", content.split_condition(c)[0], where + " characters")
        if room.get("expand") is not None and not isinstance(room["expand"], (str, list)):
            problems.append("%s: expand must be directions, comma-separated or as a list, or no" % where)
        expand = [] if str(room.get("expand")).strip().lower() in ("no", "none") else options_of(room.get("expand") or "")
        for d in expand:
            if d not in generate.OPPOSITE:
                problems.append("%s: expand direction %r has no opposite" % (where, d))
            if d in (room.get("exits") or {}):
                problems.append("%s: expand direction %r is already an exit" % (where, d))
        spots = room.get("build")
        if spots is not None and not isinstance(spots, dict):
            problems.append("%s: build gives directions, each with what could be built there (direction: text)" % where)
            spots = {}
        for d in spots or {}:
            if d not in generate.OPPOSITE:
                problems.append("%s: build direction %r has no opposite" % (where, d))
            elif d in (room.get("exits") or {}) or d in expand:
                problems.append("%s: build direction %r is already an exit or an expand direction" % (where, d))
            elif not square_free(r, d, pos):
                problems.append("%s: build direction %r would land on another room's map square" % (where, d))
            sq = square_of(r, d, pos)
            if sq and sq in claimed:
                problems.append("%s: build direction %r takes the same map square as a build spot in %s" % (where, d, claimed[sq]))
            elif sq:
                claimed[sq] = r
        if spots and not any(str(content.load("characters", c).get("builds", "no")).lower() == "yes"
                             for c in (content.split_condition(x)[0] for x in room.get("characters") or [])
                             if content.exists("characters", c)):
            problems.append("%s: has build spots but no builder (`builds: yes`) among its characters" % where)
        if room.get("encounters"):
            need("tables", room["encounters"], where + " encounters")
        if room.get("work") is not None:
            problems.extend("%s: work: %s" % (where, x) for x in work_problems(room["work"]))
        if "board" in room and str(room["board"]).lower() not in ("yes", "no"):
            problems.append("%s: board: yes or no (a notice board people can put notices up on)" % where)
    for t in content.ids("tables"):
        table = content.load("tables", t)
        if not re.match(r"^\s*\d+\s+in\s+\d+\s*$", str(table.get("chance", ""))):
            problems.append("tables/%s.md: chance must look like '2 in 6'" % t)
        for e in table.get("entries") or []:
            m = _EFFECT.search(e)
            if not m:
                continue
            words = m.group(1).split()
            if words[0] not in ("coins", "gain", "hurt", "heal", "flag", "none"):
                problems.append("tables/%s.md: unknown effect %r" % (t, m.group(1)))
            elif words[0] == "gain" and len(words) > 1:
                need("items", words[1], "tables/%s.md gain" % t)
            elif words[0] in ("hurt", "heal") and len(words) > 1:
                need_dice(words[1], "tables/%s.md %s" % (t, words[0]))
    for q in content.ids("quests"):
        for line in content.load("quests", q).get("objectives") or []:
            if not _DONE.match(str(line)):
                problems.append("quests/%s.md: objective needs '(done when <condition>)': %s" % (q, line))
    art_dir = content.game_dir() / "art"
    for a in (sorted(art_dir.glob("*.txt")) if art_dir.is_dir() else []):
        need("rooms", a.stem, "art/%s" % a.name)
    for a in (sorted(art_dir.glob("*.png")) if art_dir.is_dir() else []):
        need("rooms", a.stem, "art/%s" % a.name)
        why = png.problem(a.read_bytes())
        if why:
            problems.append("art/%s: %s" % (a.name, why))
    problems.extend("art/terrain/%s" % x for x in terrain_art_problems(art_dir / "terrain", terrains))
    for c in content.ids("characters"):
        ch = content.load("characters", c)
        if str(ch.get("minor", "no")).lower() not in ("yes", "no"):
            problems.append("characters/%s.md: minor must be yes or no" % c)
        if "hp" in ch:
            for k in ("defense", "attack", "damage"):
                if k not in ch:
                    problems.append("characters/%s.md: has hp but no %s" % (c, k))
        for t in options_of(ch.get("makes") or ""):
            if t not in BALANCE["generation"]["item_tiers"]:
                problems.append("characters/%s.md: makes %r, which isn't an item tier (%s)"
                                % (c, t, ", ".join(BALANCE["generation"]["item_tiers"])))
        for i in options_of(ch.get("accepts") or ""):
            need("items", i, "characters/%s.md accepts" % c)
        if str(ch.get("builds", "no")).lower() not in ("yes", "no"):
            problems.append("characters/%s.md: builds must be yes or no" % c)
        if ch.get("accepts") and not ch.get("makes"):
            problems.append("characters/%s.md: accepts goes with makes (it's what a maker takes in trade)" % c)
        if ch.get("buys") is not None:
            problems.extend("characters/%s.md: buys: %s" % (c, x) for x in buys_problems(ch["buys"]))
    for t in BALANCE["generation"]["item_tiers"]:
        if t not in BALANCE["generation"]["craft_price"]:
            problems.append("balance.json generation craft_price: no price for the item tier %r" % t)
    for i in content.ids("items"):
        it = content.load("items", i)
        for k in ("damage", "heal"):
            if it.get(k):
                need_dice(it[k], "items/%s.md" % i)
    flag_text = "\n".join(path.read_text(encoding="utf-8") for path in content.game_dir().rglob("*.md"))
    for c in content.ids("curses"):
        meta, where = content.load("curses", c), "curses/%s.md" % c
        try:
            curse.parse(meta.get("effect"))
        except ValueError as e:
            problems.append("%s: %s" % (where, e))
        for key in ("caused_by", "cured_by"):
            if not meta.get(key):
                problems.append("%s: needs %s (a condition); every curse has a cause and a cure" % (where, key))
        own = content.path_of("curses", c).read_text(encoding="utf-8")
        for term in generate.TERM.findall(str(meta.get("cured_by") or "")):
            if term.startswith("has_"):
                need("items", term[4:], where + " cured_by")
            elif term.startswith("met_"):
                need("characters", term[4:], where + " cured_by")
            elif flag_text.replace(own, "").count(term) == 0:
                problems.append("%s: nothing in the game sets %r, so the curse can't be cured" % (where, term))
    validate_plans(w, flag_text, problems)
    validate_days(w, problems)
    validate_needs(w, problems)
    validate_selling(w, problems)
    validate_projects(w, problems)
    validate_scenes(problems)
    validate_cast(problems)
    validate_soundness(w, problems)
    if kit:
        validate_kit_complete(w, problems)
    if sim or strict:
        validate_sim_complete(w, problems)
    WARNINGS[:] = [] if strict else world_warnings(w)
    if strict:
        validate_sim_strict(w, problems)
    return problems, "%d rooms, %d characters, %d items, %d quests, %d tables, %d curses, %d scenes" % tuple(len(content.ids(k)) for k in content.KINDS)


def work_problems(spec):
    """What's wrong with a room's `work:` (stat, pay as a range like 1-3, and optionally dc and if), as a list."""
    if not isinstance(spec, dict):
        return ["give stat, pay (a range like 1-3) and optionally dc and if, each on its own indented line"]
    out = ["unknown key %r (keys: stat, pay, dc, if)" % k for k in sorted(set(spec) - {"stat", "pay", "dc", "if"})]
    if "if" in spec and not (isinstance(spec["if"], str) and spec["if"].strip()):
        out.append("if must be a condition (paid work only while it holds)")
    if spec.get("stat") not in STATS:
        out.append("stat must be one of %s" % ", ".join(STATS))
    cap = int(BALANCE["work"]["max_pay"])
    m = re.fullmatch(r"(\d+)(?:-(\d+))?", str(spec.get("pay", "")))
    if not m or not 1 <= int(m.group(1)) <= int(m.group(2) or m.group(1)) <= cap:
        out.append("pay must be a whole number or a range like 1-3, from 1 to %d (balance.json work.max_pay)" % cap)
    if "dc" in spec and not (str(spec["dc"]).isdigit() or spec["dc"] in BALANCE["dc"]):
        out.append("dc must be a number or one of %s" % ", ".join(BALANCE["dc"]))
    return out


def buys_problems(prices):
    """What's wrong with a buyer's `buys:` (an item tier and a price on each line), as a list. A buyer pays less than
    the tier costs to have made, or money could be made from nothing."""
    tiers, cost = BALANCE["generation"]["item_tiers"], BALANCE["generation"]["craft_price"]
    if not isinstance(prices, dict) or not prices:
        return ["give an item tier and a price on each indented line (tier: price)"]
    out = []
    for t, p in prices.items():
        if t not in tiers:
            out.append("%r isn't an item tier (%s)" % (t, ", ".join(tiers)))
        elif not isinstance(p, int) or p < 1:
            out.append("%s: the price must be a whole number from 1" % t)
        elif p >= int(cost[t]):
            out.append("%s: pays %d, but having one made costs %d; a buyer must pay less" % (t, p, int(cost[t])))
    return out


def quest_flags(w):
    """Every flag the main story turns on: quests' conditions, the clock's flags and the variants. Plans keep off them."""
    out = set()
    for q in content.ids("quests"):
        meta = content.load("quests", q)
        for k in ("started_by", "completed_by", "failed_by"):
            out.update(generate.TERM.findall(str(meta.get(k) or "")))
        for line in meta.get("objectives") or []:
            m = _DONE.match(str(line))
            if m:
                out.update(generate.TERM.findall(m.group(2)))
    clock = w.get("clock") or {}
    out.update(x for x in (clock.get("flag"), clock.get("also_flag")) if x)
    for opts in (w.get("variants") or {}).values():
        out.update(options_of(opts))
    return out


def validate_plans(w, flag_text, problems):
    """Plans: well formed, each on the character's own flags, each undoable, each showing somewhere, and never
    leaving the character in two rooms at once (checked from the start of the game)."""
    story = quest_flags(w)
    for c in content.ids("characters"):
        meta = content.load("characters", c)
        steps, where = content.plans(meta["body"]), "characters/%s.md" % c
        if not steps:
            continue
        if str(meta.get("minor", "no")).lower() == "yes":
            problems.append("%s: plans are for major characters (minor: no); the game master plays minor ones on the spot" % where)
        own = content.path_of("characters", c).read_text(encoding="utf-8")
        seen, sets, clears = set(), set(), set()
        for st in steps:
            at = "%s ## %s" % (where, st["heading"])
            if not st["step"]:
                problems.append("%s: a plan heading is 'Plan: <step id> (if <condition>)', the id lowercase with underscores" % at)
                continue
            if st["step"] in seen:
                problems.append("%s: two plan steps are called %r" % (at, st["step"]))
            seen.add(st["step"])
            for line in st["bad"]:
                problems.append("%s: unknown line %r (plan lines: %s)" % (at, line, ", ".join(content.PLAN_KEYS)))
            for k in ("does", "near"):
                if not st.get(k):
                    problems.append("%s: needs %s:" % (at, k))
            for k in ("does", "near", "rumor"):
                if len(st.get(k) or "") > 160:
                    problems.append("%s: %s is longer than 160 characters" % (at, k))
            if bool(st.get("sets")) == bool(st.get("clears")):
                problems.append("%s: a step either sets or clears one flag" % at)
                continue
            flag = st.get("sets") or st.get("clears")
            (sets if st.get("sets") else clears).add(flag)
            if not re.fullmatch(r"%s_[a-z0-9_]+" % re.escape(c), flag):
                problems.append("%s: plan flags are the character's own: %s_<word>, not %r" % (at, c, flag))
            if flag in story:
                problems.append("%s: %r is part of the main story; plans never touch it" % (at, flag))
            if flag_text.replace(own, "").count(flag) == 0:
                problems.append("%s: nothing outside this file uses %r, so the step would change nothing" % (at, flag))
        for f in sorted(sets - clears):
            problems.append("%s: no plan step clears %r, so once set it would stay for good" % (where, f))
        for f in sorted(clears - sets):
            problems.append("%s: no plan step sets %r" % (where, f))
        own_flags = sorted(sets | clears)
        start = list(w.get("flags") or [])

        def rooms_with(flags):
            return [r for r in content.ids("rooms") if c in content.visible(content.load("rooms", r).get("characters"), flags)]

        for n in range(2 ** len(own_flags)):
            flags = start + [f for i, f in enumerate(own_flags) if n >> i & 1]
            rooms = rooms_with(flags)
            if len(rooms) > 1:
                problems.append("%s: with %s, %s stands in %s at once" % (
                    where, ", ".join(f for f in own_flags if f in flags) or "none of their plan flags", c, " and ".join(rooms)))
        # Someone who stands somewhere at the start must stand somewhere after any run of their plan steps (followed
        # from the start of the game), or a step would make them vanish: a room's condition forgotten.
        if rooms_with(start):
            seen_states, todo = {frozenset()}, [frozenset()]
            while todo:
                now = todo.pop()
                for st in steps:
                    flag = st.get("sets") or st.get("clears")
                    if not st["step"] or not flag or not content.condition_holds(st["when"], start + sorted(now)):
                        continue
                    nxt = now | {flag} if st.get("sets") else now - {flag}
                    if nxt not in seen_states:
                        seen_states.add(nxt)
                        todo.append(nxt)
                        if not rooms_with(start + sorted(nxt)):
                            problems.append("%s: after %s (%s), %s stands nowhere; a room's characters need a condition "
                                            "for it" % (where, st["step"], ", ".join(sorted(nxt)) or "no plan flags", c))


CAST_ID = re.compile(r"^[a-z][a-z0-9_]{0,23}$")
CAST_TEXT = ("name", "personality", "voice", "opening")  # a hand-written entry; one made from an archetype has these:
MADE_TEXT = ("name", "voice", "opening", "backstory", "how_i_am")
MADE_LISTS = ("wants_and_needs", "avoids_and_dislikes", "wont_do", "priorities")
# a blank person (`"blank": true`): a name, a place, money and what everyone knows; no note, no wants, no history
BLANK_LEAVES_OUT = ("personality", "voice", "opening", "motivations", "backstory", "how_i_am", "knows", "people", "look",
                    "archetype", "made_with", "situation") + MADE_LISTS
ARCHETYPES = ROOT / "cast"  # the people anywhere (PERSON-STRUCTURE-PROPOSAL.md 5.2): ratings never shown to them


def definitions():
    """The definitions of the attributes and ways of acting (rules/people/defaults.json), with the world's own lines
    (games/<id>/people.json) in their place where it gives any: the scale, and each one's name, low and high line."""
    base = json.loads(people_file("defaults.json"))
    try:
        own = content.game_json("people.json")
    except ValueError:
        own = {}
    return content.deep_merge(base, own or {})


def archetype(ident):
    """A person anywhere (cast/<id>.json), or None."""
    path = ARCHETYPES / ("%s.json" % ident)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def archetype_problems(arch, defs, where):
    """What's wrong with an archetype: its parts, and a rating on the scale for every attribute and way."""
    out, scale = [], defs["scale"]
    for k in ("id", "name", "pronouns", "voice"):
        if not isinstance(arch.get(k), str) or not arch[k].strip():
            out.append("%s: %s must be some text" % (where, k))
    for k in MADE_LISTS:
        if not isinstance(arch.get(k), list) or not arch[k] or not all(isinstance(x, str) and x.strip() for x in arch[k]):
            out.append("%s: %s must be a list of short lines" % (where, k))
    for part in ("attributes", "ways"):
        given = arch.get(part) if isinstance(arch.get(part), dict) else {}
        for k in defs[part]:
            v = given.get(k)
            if not isinstance(v, int) or isinstance(v, bool) or not scale["min"] <= v <= scale["max"]:
                out.append("%s: %s %s needs a rating from %d to %d" % (where, part, k, scale["min"], scale["max"]))
        out += ["%s: %s %s isn't in the definitions" % (where, part, k) for k in given if k not in defs[part]]
    unknown = set(arch) - {"id", "name", "pronouns", "voice", "attributes", "ways"} - set(MADE_LISTS)
    if unknown:
        out.append("%s: unknown key%s %s" % (where, "s" if len(unknown) > 1 else "", ", ".join(sorted(unknown))))
    return out


def made_entry_problems(e, where):
    """A cast entry made from an archetype: the archetype exists and passes; its name, pronouns, voice and what they
    won't do are the archetype's word for word; its lists are short lines; the old hand-written fields are gone."""
    out, limits = [], BALANCE["cast"]
    arch = archetype(str(e.get("archetype")))
    if not arch:
        return out + ["%s: archetype: no cast/%s.json" % (where, e.get("archetype"))]
    out += archetype_problems(arch, definitions(), "cast/%s.json" % e["archetype"])
    for k in ("name", "pronouns", "voice", "wont_do"):
        if e.get(k) != arch.get(k):
            out.append("%s: %s must be the archetype's, word for word" % (where, k))
    for k in MADE_LISTS:
        v = e.get(k)
        if not isinstance(v, list) or not 1 <= len(v) <= int(limits["list_max"]) or not all(
                isinstance(x, str) and x.strip() and len(x) <= int(limits["line_chars"]) for x in v):
            out.append("%s: %s must be 1 to %d lines of at most %d characters" % (where, k, int(limits["list_max"]), int(limits["line_chars"])))
    for k in ("backstory", "how_i_am"):
        if isinstance(e.get(k), str) and len(e[k]) > int(limits["note_chars"]):
            out.append("%s: %s is at most %d characters" % (where, k, int(limits["note_chars"])))
    out += ["%s: %s is for a hand-written entry; one made from an archetype has %s" % (where, k, alt)
            for k, alt in (("personality", "backstory and how_i_am"), ("motivations", "wants_and_needs")) if k in e]
    return out


def validate_cast(problems):
    """The cast file (`cast.json`), if the game has one: a list of the people who play it."""
    try:
        data = content.game_json("cast.json")
    except ValueError as e:
        problems.append("cast.json: not valid JSON (%s)" % e)
        return
    if data == {}:
        return  # no cast file
    limits = BALANCE["cast"]
    if not isinstance(data, list) or not data:
        problems.append("cast.json must be a list of one entry per player")
        return
    if len(data) > int(limits["max_players"]):
        problems.append("cast.json: at most %d players (has %d)" % (int(limits["max_players"]), len(data)))
    seen_ids, seen_names = set(), set()
    known = {"id", "model", "pronouns", "motivations", "attributes", "hp", "coins", "inventory", "equipped", "home",
             "knows", "people", "look", "paid_beds", "archetype", "made_with", "situation", "blank"} | set(CAST_TEXT) | set(MADE_TEXT) | set(MADE_LISTS)
    cast_ids = {e.get("id") for e in data if isinstance(e, dict)}
    for n, e in enumerate(data, 1):
        if not isinstance(e, dict):
            problems.append("cast.json entry %d is not an object" % n)
            continue
        ident = e.get("id")
        where = "cast.json %s" % (ident if isinstance(ident, str) else "entry %d" % n)
        for k in sorted(set(e) - known):
            problems.append("%s: unknown key %r" % (where, k))
        if "situation" in e and (not isinstance(e["situation"], str) or not e["situation"].strip()
                                 or len(e["situation"]) > int(limits["line_chars"])):  # for the generator only: never shown
            problems.append("%s: situation is one line of at most %d characters" % (where, int(limits["line_chars"])))
        if not isinstance(ident, str) or not CAST_ID.match(ident):
            problems.append("%s: id must be lowercase letters, digits and underscores, starting with a letter" % where)
        elif ident in seen_ids:
            problems.append("%s: the id is used twice" % where)
        elif content.exists("characters", ident):
            problems.append("%s: the id is also a character's in this world" % where)
        seen_ids.add(ident)
        made = "archetype" in e  # made from an archetype by tools/cast.py, or written by hand
        blank = e.get("blank") is True
        if "blank" in e and not blank:
            problems.append("%s: blank is true, or left out" % where)
        for k in ("name",) if blank else MADE_TEXT if made else CAST_TEXT:
            if not isinstance(e.get(k), str) or not e[k].strip():
                problems.append("%s: %s must be some text" % (where, k))
        if blank:
            for k in BLANK_LEAVES_OUT:
                if k in e:
                    problems.append("%s: a blank person has no %s" % (where, k))
        elif made:
            problems += made_entry_problems(e, where)
        if isinstance(e.get("name"), str):
            if e["name"].lower() in seen_names:
                problems.append("%s: the name %r is used twice" % (where, e["name"]))
            seen_names.add(e["name"].lower())
        if "pronouns" in e and not (isinstance(e["pronouns"], str) and re.fullmatch(r"[a-z]+(/[a-z]+)+", e["pronouns"])):
            problems.append("%s: pronouns are written like she/her, he/him or they/them" % where)
        motives = e.get("motivations")
        if not made and not blank and (not isinstance(motives, list) or not motives or not all(isinstance(m, str) and m.strip() for m in motives)):
            problems.append("%s: motivations must be a list of short lines" % where)
        lines = e.get("knows", [])
        if not isinstance(lines, list) or len(lines) > int(limits["knows_max"]) or not all(
                isinstance(k, str) and k.strip() and len(k) <= int(limits["line_chars"]) for k in lines):
            problems.append("%s: knows must be a list of at most %d facts, each a line of at most %d characters"
                            % (where, int(limits["knows_max"]), int(limits["line_chars"])))
        known_people = e.get("people", [])
        if not isinstance(known_people, list) or len(known_people) > int(limits["people_max"]) or not all(
                isinstance(k, dict) and set(k) == {"who", "how"} and isinstance(k["how"], str) and k["how"].strip()
                and len(k["how"]) <= int(limits["line_chars"]) for k in known_people):
            problems.append("%s: people must be a list of at most %d {\"who\", \"how\"}, how a line of at most %d characters"
                            % (where, int(limits["people_max"]), int(limits["line_chars"])))
        else:
            for k in known_people:
                if k["who"] == ident or not (k["who"] in cast_ids or content.exists("characters", str(k["who"]))):
                    problems.append("%s: people: %r is neither another of the cast nor a character in this world" % (where, k["who"]))
        if "look" in e and not (isinstance(e["look"], str) and e["look"].strip() and len(e["look"]) <= int(limits["look_chars"])):
            problems.append("%s: look must be a line of at most %d characters" % (where, int(limits["look_chars"])))
        for b in e.get("paid_beds") or []:  # nights already paid for: [{"room", "nights"}]
            if not (isinstance(b, dict) and content.exists("rooms", str(b.get("room"))) and isinstance(b.get("nights"), int)
                    and b["nights"] > 0 and isinstance(content.load("rooms", str(b["room"])).get("bed_price"), int)):
                problems.append("%s: paid_beds: each is {\"room\": a room with a bed_price, \"nights\": a number from 1}" % where)
        if "model" in e and e["model"] not in limits["models"]:
            problems.append("%s: model must be one of %s" % (where, ", ".join(limits["models"])))
        elif "model" not in e and SETTINGS["cast"]["model"] == "own":
            problems.append("%s: needs a model, since the settings ask each person's own (cast.model: own)" % where)
        if not content.exists("rooms", str(e.get("home", ""))):
            problems.append("%s: home %r is not a room" % (where, e.get("home")))
        attrs = e.get("attributes")
        if attrs is not None:
            if not isinstance(attrs, dict) or set(attrs) - set(STATS):
                problems.append("%s: attributes must give %s" % (where, ", ".join(STATS)))
            elif not all(isinstance(v, int) and limits["stat_min"] <= v <= limits["stat_max"] for v in attrs.values()):
                problems.append("%s: attributes must be whole numbers from %d to %d" % (where, limits["stat_min"], limits["stat_max"]))
            if not isinstance(e.get("hp"), int) or not 1 <= e["hp"] <= limits["hp_max"]:
                problems.append("%s: hp must be a whole number from 1 to %d" % (where, limits["hp_max"]))
        elif "hp" in e:
            problems.append("%s: hp comes with attributes (without them both are the world's)" % where)
        if "coins" in e and (not isinstance(e["coins"], int) or not 0 <= e["coins"] <= limits["coins_max"]):
            problems.append("%s: coins must be a whole number from 0 to %d" % (where, limits["coins_max"]))
        inventory = e.get("inventory", [])
        if not isinstance(inventory, list):
            problems.append("%s: inventory must be a list of item ids" % where)
            inventory = []
        for i in inventory:
            if not content.exists("items", str(i)):
                problems.append("%s: inventory: unknown item %r" % (where, i))
        if e.get("equipped") is not None:
            if e["equipped"] not in inventory:
                problems.append("%s: equipped %r isn't in their inventory" % (where, e["equipped"]))
            elif not content.load("items", e["equipped"]).get("damage"):
                problems.append("%s: equipped %r is not a weapon" % (where, e["equipped"]))


def validate_scenes(problems):
    """Scenes: two agent characters who can both be in its room, a small reward, the sections each part needs,
    and no story flags."""
    cap = int(BALANCE["scenes"]["max_reward_coins"])
    for s in content.ids("scenes"):
        sc, where = content.load("scenes", s), "scenes/%s.md" % s
        cast = scene_cast(sc)
        if len(set(cast)) != 2:
            problems.append("%s: with: lists exactly two characters" % where)
        for c in cast:
            if not content.exists("characters", c):
                problems.append("%s: unknown character %r" % (where, c))
            elif str(content.load("characters", c).get("minor", "no")).lower() == "yes":
                problems.append("%s: %s is minor; a scene is for two characters with their own agents" % (where, c))
        room = sc.get("where")
        if not content.exists("rooms", str(room)):
            problems.append("%s: where: needs a room (got %r)" % (where, room))
        else:
            placed = {content.split_condition(x)[0] for x in content.load("rooms", room).get("characters") or []}
            for c in cast:
                if c not in placed:
                    problems.append("%s: %s is never in %s, so the scene can't happen" % (where, c, room))
        reward = str(sc.get("reward") or "")
        m = re.fullmatch(r"coins\s+(\d+)", reward.strip())
        if reward.strip() != "none" and not (m and 1 <= int(m.group(1)) <= cap):
            problems.append("%s: reward is 'none' or 'coins N' with N from 1 to %d" % (where, cap))
        if not sc.get("chronicle") or len(str(sc["chronicle"])) > 160:
            problems.append("%s: needs a chronicle: line of at most 160 characters" % where)
        heads = [h for h, _ in content.sections(sc["body"])]
        for h in ["How it starts", "Premise", "How it ends"] + cast:
            if h not in heads:
                problems.append("%s: needs a ## %s section" % (where, h))
        if "flag set" in sc["body"] or "flag unset" in sc["body"]:
            problems.append("%s: scenes never change story flags" % where)


_HEADING_IF = re.compile(r"^#{2,6}\s+If\s+(.+?)\s*$", re.M)
_CODE = re.compile(r"`([^`\n]+)`")
ITEM_COMMANDS = ("take", "drop", "gain", "lose", "equip", "use", "sell", "eat", "buy")


def content_files(w):
    """Every content file of the active game as (where, meta, body), world.md first."""
    out = [("world.md", w, w["body"])]
    for kind in content.KINDS:
        for i in content.ids(kind):
            meta = content.load(kind, i)
            out.append(("%s/%s.md" % (kind, i), meta, meta["body"]))
    return out


def settable_flags(w):
    """Every flag something in the game can set: a `flag set` in any file, an encounter's flag effect, world.md's
    starting flags, the variants, the clock, a plan step, or a defeat (anyone with hp)."""
    text = "\n".join(path.read_text(encoding="utf-8") for path in content.game_dir().rglob("*.md"))
    out = set(re.findall(r"flag set ([a-z0-9_]+)", text)) | set(re.findall(r"\(effect:\s*flag\s+([a-z0-9_]+)", text))
    out.update(w.get("flags") or [])
    for opts in (w.get("variants") or {}).values():
        out.update(options_of(opts))
    clock = w.get("clock") or {}
    out.update(x for x in (clock.get("flag"), clock.get("also_flag")) if x)
    out.update(ev["sets"] for ev in content.timed(w["body"]) if ev.get("sets"))
    for r in content.ids("rooms"):  # a shared work's stages
        out.update(f for _, f in (project_of(content.load("rooms", r)) or {}).get("stages", []))
    for c in content.ids("characters"):
        meta = content.load("characters", c)
        out.update(st["sets"] for st in content.plans(meta["body"]) if st.get("sets"))
        if "hp" in meta:
            out.add("%s_defeated" % c)
    return out


def conditions_in(meta, body):
    """Every condition a content file holds: `(if …)` on its values, its bare condition keys, its objectives,
    its plan steps, and its `If …` headings."""
    out = []

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str):
            cond = content.split_condition(v)[1]
            if cond:
                out.append(cond)

    walk({k: v for k, v in meta.items() if k not in ("id", "body")})
    for k in ("started_by", "completed_by", "failed_by", "caused_by", "cured_by", "when"):
        if meta.get(k):
            out.append(str(meta[k]))
    for line in meta.get("objectives") or []:
        m = _DONE.match(str(line))
        if m:
            out.append(m.group(2))
    if meta.get("clock") and meta["clock"].get("also_if"):
        out.append(str(meta["clock"]["also_if"]))
    if isinstance(meta.get("work"), dict) and meta["work"].get("if"):
        out.append(str(meta["work"]["if"]))
    out += [st["when"] for st in content.plans(body) if st.get("when")]
    out += [ev["if"] for ev in content.timed(body) if ev.get("if")]
    out += _HEADING_IF.findall(body)
    return out


def command_problem(words):
    """What's wrong with a rules command written in content (`flag set x`, `lose honey_cake`), or None."""
    cmd, args = words[0], words[1:]
    if len(args) < COMMANDS[cmd][1]:
        return "needs %d argument(s): %s" % (COMMANDS[cmd][1], COMMANDS[cmd][2])
    if cmd in ITEM_COMMANDS and not args[0].startswith("<") and not content.exists("items", args[0]):  # `sell <item>`
        return "no item %r" % args[0]
    if cmd == "attack" and not content.exists("characters", args[0]):
        return "no character %r" % args[0]
    if cmd == "flag" and (args[0] not in ("set", "unset") or not re.fullmatch(r"[a-z0-9_]+", args[1])
                          or args[1].startswith(AUTOMATIC)):
        return "use flag set|unset <name> (has_, met_, time_, day_ and after_day_ are automatic)"
    if cmd == "coins" and (not re.fullmatch(r"[+-]\d+", args[0]) or args[1] not in COIN_REASONS):
        return "use coins +N <reason> or coins -N <reason> (%s)" % ", ".join(COIN_REASONS)
    if cmd == "check" and (args[0] not in STATS or not (args[1].isdigit() or args[1] in ("easy", "normal", "hard"))):
        return "use check <%s> <number|easy|normal|hard>" % "|".join(STATS)
    if cmd in ("hurt", "heal", "roll"):
        try:
            dice.parse(args[0])
        except ValueError as e:
            return str(e)
    if cmd == "scene" and (args[0] not in ("start", "end") or not content.exists("scenes", args[1])
                           or args[2:] not in ([], ["reward"])):
        return "use scene start|end <scene> [reward], naming a scene the game has"
    if cmd == "rent" and not (args[0].startswith("<") or content.exists("rooms", args[0]) and rent_of(content.load("rooms", args[0]))):
        return "no place to let called %r" % args[0]
    if cmd == "meet" and (args[0] not in NEEDS or args[1:] not in ([], ["bed"], ["rough"]) or args[0] == "food" and args[1:]):
        return "use meet food, or meet sleep [bed|rough]"
    if cmd == "show" and args[0] != "world" and (args[0] not in content.KINDS or len(args) < 2
                                                 or not content.exists(args[0], args[1])):
        return "use show <kind> <id>, naming something the game has, or show world"
    return None


def time_condition_problem(w, term):
    """What's wrong with a condition on the clock (time_<a time of day>, day_<n>, after_day_<n>), or None."""
    times = w.get("times") or []
    if term.startswith("time_"):
        return None if term in {time_slug(x) for x in times} else "no time of day like that in world.md's times (%s)" % (
            ", ".join(time_slug(x) for x in times) or "none")
    if str(w.get("days", "no")).lower() != "yes":
        return "days are counted only in a world with `days: yes`"
    return None if re.fullmatch(r"(after_)?day_[1-9][0-9]*", term) else "a day is a number from 1 (day_2, after_day_3)"


def validate_days(w, problems):
    """`days:` and the timed events (`## At:` sections of world.md)."""
    days, times = str(w.get("days", "no")).lower(), w.get("times") or []
    if days not in ("yes", "no"):
        problems.append("world.md days: must be yes or no")
    if days == "yes":
        if len(times) < 2:
            problems.append("world.md days: yes needs at least two times of day in times:")
        if w.get("clock"):
            problems.append("world.md days: yes can't go with a clock: (the deadline clock drives the time of day)")
    events, ids = content.timed(w["body"]), set()
    if events and days != "yes":
        problems.append("world.md: `## At:` sections need `days: yes` (they happen on a day, at a time)")
    personal = set(options_of(w.get("personal_flags") or []))
    for ev in events:
        where = "world.md %s" % ev["heading"]
        if not ev["id"]:
            problems.append("%s: the heading is `## At: <id>`, the id lowercase letters, digits and _" % where)
        elif ev["id"] in ids:
            problems.append("%s: another `## At:` has this id" % where)
        ids.add(ev["id"])
        problems += ["%s: %r isn't one of when:, if:, sets:, seen:, rumor:" % (where, line) for line in ev["bad"]]
        when = when_of(ev.get("when"))
        if not when:
            problems.append("%s: needs `when: day <n>, <a time of day>`" % where)
        elif when[0] < 1 or when[1] not in times:
            problems.append("%s: when: the day is a number from 1, and the time one of times: (%s)" % (where, ", ".join(times)))
        elif times and when == (1, times[0]):
            problems.append("%s: when: day 1, %s is when the run begins; nothing comes round to it" % (where, times[0]))
        if not any(ev.get(k) for k in ("sets", "seen", "rumor")):
            problems.append("%s: needs at least one of sets:, seen:, rumor:" % where)
        flag = ev.get("sets")
        if flag and (not re.fullmatch(r"[a-z][a-z0-9_]*", flag) or flag.startswith(AUTOMATIC) or flag in personal):
            problems.append("%s: sets: %r must be a shared flag name (not automatic, not one of personal_flags)" % (where, flag))


def validate_needs(w, problems):
    """world.md `needs:` and what meets them: `sleep_at:`, places to sleep (a room's `sleep:`), food (`food: yes`)."""
    needs = options_of(w.get("needs") or [])
    for n in needs:
        if n not in NEEDS:
            problems.append("world.md needs: %r isn't a need the kit knows (%s)" % (n, ", ".join(NEEDS)))
    if needs and str(w.get("days", "no")).lower() != "yes":
        problems.append("world.md needs: need `days: yes` (food is daily, sleep nightly)")
    beds = [r for r in content.ids("rooms") if content.load("rooms", r).get("sleep") is not None]
    for r in beds:
        if str(content.load("rooms", r)["sleep"]).lower() not in SLEEP_PLACES:
            problems.append("rooms/%s.md: sleep: must be bed or rough" % r)
    food = [i for i in content.ids("items") if str(content.load("items", i).get("food", "no")).lower() == "yes"]
    for i in content.ids("items"):
        if str(content.load("items", i).get("food", "no")).lower() not in ("yes", "no"):
            problems.append("items/%s.md: food: must be yes or no" % i)
    text = "\n".join(path.read_text(encoding="utf-8") for path in content.game_dir().rglob("*.md"))
    if "sleep" in needs:
        if w.get("sleep_at") not in (w.get("times") or []):
            problems.append("world.md: a world where people need sleep needs `sleep_at:`, one of its times of day")
        if not beds and "`meet sleep" not in text:
            problems.append("world.md needs: sleep, but nowhere has `sleep: bed` or `sleep: rough`, and nothing says `meet sleep`")
    if "food" in needs and not food and "`meet food" not in text:
        problems.append("world.md needs: food, but no item is `food: yes`, and nothing says `meet food`")


def validate_projects(w, problems):
    """Rooms' `project:`: an id of its own, stages, a stat, a dc, `until:` and `meal:`."""
    seen = {}
    for r in content.ids("rooms"):
        spec, where = content.load("rooms", r).get("project"), "rooms/%s.md" % r
        if spec is None:
            continue
        if not isinstance(spec, dict) or not re.fullmatch(r"[a-z][a-z0-9_]*", str(spec.get("id", ""))):
            problems.append("%s: project: needs an id (lowercase letters, digits and _) on an indented line" % where)
            continue
        if spec["id"] in seen:
            problems.append("%s: project: %s is also the shared work at %s" % (where, spec["id"], seen[spec["id"]]))
        seen[spec["id"]] = r
        unknown = set(spec) - {"id", "name", "stages", "until", "stat", "dc", "meal"}
        if unknown:
            problems.append("%s: project: %s isn't one of id, name, stages, until, stat, dc, meal" % (where, ", ".join(sorted(unknown))))
        parts = [s for s in str(spec.get("stages") or "").split(";") if s.strip()]
        if not parts or any(not _STAGE.match(s) for s in parts):
            problems.append("%s: project: stages: \"<amount>: <flag>; ...\" (got %r)" % (where, spec.get("stages")))
        for s in parts:
            m = _STAGE.match(s)
            if m and (m.group(2).startswith(AUTOMATIC) or m.group(2) in set(options_of(w.get("personal_flags") or []))):
                problems.append("%s: project: stage flag %r must be a shared flag" % (where, m.group(2)))
        if spec.get("stat", "might") not in STATS:
            problems.append("%s: project: stat must be one of %s" % (where, ", ".join(STATS)))
        if spec.get("dc") is not None and not (str(spec["dc"]).isdigit() or spec["dc"] in ("easy", "normal", "hard")):
            problems.append("%s: project: dc must be a number or easy, normal, hard" % where)
        if str(spec.get("meal", "no")).lower() not in ("yes", "no"):
            problems.append("%s: project: meal must be yes or no" % where)


def validate_selling(w, problems):
    """Sellers' `sells:`, rooms' `bed_price:`, `rent:` and `landlord:`."""
    for c in content.ids("characters"):
        meta = content.load("characters", c)
        if meta.get("sells") is None:
            continue
        if not isinstance(meta["sells"], dict) or not meta["sells"]:
            problems.append("characters/%s.md: sells: an item and its price on each indented line (item: price, or price, n in stock)" % c)
            continue
        for i, v in meta["sells"].items():
            if not content.exists("items", i):
                problems.append("characters/%s.md: sells: no item %r" % (c, i))
            if not _SELLS.match(str(v).strip()):
                problems.append("characters/%s.md: sells: %s: a price, or \"<price>, <n> in stock\" (got %r)" % (c, i, v))
    for r in content.ids("rooms"):
        room, where = content.load("rooms", r), "rooms/%s.md" % r
        if "bed_price" in room and (not isinstance(room["bed_price"], int) or room["bed_price"] < 0 or str(room.get("sleep")).lower() != "bed"):
            problems.append("%s: bed_price: a whole number, in a room with sleep: bed" % where)
        if "rent" in room or "landlord" in room:
            if not rent_of(room):
                problems.append("%s: rent: \"<price> for <n> days\", with a landlord:" % where)
            elif not content.exists("characters", str(room.get("landlord"))):
                problems.append("%s: landlord: no character %r" % (where, room.get("landlord")))
            if str(w.get("days", "no")).lower() != "yes":
                problems.append("%s: rent: a let runs for days, so the world needs `days: yes`" % where)


def validate_soundness(w, problems):
    """That the game can be played through: every flag a condition uses can be set by something (so the quest's
    completion can become true, and no door waits on a flag nothing sets), and every rules command written in the
    content is a real one naming real things."""
    can_set, seen = settable_flags(w), set()
    for where, meta, body in content_files(w):
        for cond in conditions_in(meta, body):
            for term in generate.TERM.findall(cond):
                if (where, term) in seen:
                    continue
                seen.add((where, term))
                if term.startswith("has_"):
                    if not content.exists("items", term[4:]):
                        problems.append("%s: condition %r: no item %r" % (where, term, term[4:]))
                elif term.startswith("met_"):
                    if not content.exists("characters", term[4:]):
                        problems.append("%s: condition %r: no character %r" % (where, term, term[4:]))
                elif term.startswith("most_"):
                    if term[5:] not in project_rooms():
                        problems.append("%s: condition %r: no shared work called %r" % (where, term, term[5:]))
                elif term.startswith(("time_", "day_", "after_day_")):
                    problem = time_condition_problem(w, term)
                    if problem:
                        problems.append("%s: condition %r: %s" % (where, term, problem))
                elif term not in can_set:
                    problems.append("%s: a condition uses %r, but nothing in the game sets it" % (where, term))
        for span in _CODE.findall(body):
            words = span.split()
            while words and words[0] in ("python3", "rules/rpg.py", "rpg.py"):
                words = words[1:]
            if words and words[0] in COMMANDS:
                why = command_problem(words)
                if why:
                    problems.append("%s: `%s`: %s" % (where, span, why))


def terrain_art_problems(folder, terrains):
    """Problems with a folder of terrain pictures: each `<terrain>.png` or `<terrain>-<n>.png`, for a terrain the
    look knows, and a picture the margin can draw."""
    out = []
    for a in (sorted(folder.iterdir()) if folder.is_dir() else []):
        kind = re.sub(r"-\d+$", "", a.stem)
        if a.suffix != ".png" or not a.is_file():
            out.append("%s: only .png pictures go here" % a.name)
        elif kind not in terrains:
            out.append("%s: names no terrain of the look's (%s)" % (a.name, ", ".join(terrains)))
        else:
            why = png.problem(a.read_bytes())
            if why:
                out.append("%s: %s" % (a.name, why))
    return out


KIT_ROOMS = (5, 8)
KIT_CHARACTERS = (3, 4)
KIT_TOP_FILES = ("world.md", "look.json", "balance.json", "settings.json", "forged.json", "cast.json")
KIT_MAX_FILES = 80
KIT_MAX_CHARS = 20000


def validate_kit_complete(w, problems):
    """What every kit feature needs to work in a world: a full world file and a look of its own, 5-8 connected
    rooms, 3-4 people (two with agents, one with plans, a maker, a builder's spot), one quest with two ways through
    and its endings, a curse, a side scene. `validate --kit-complete`; forged worlds must pass it, and so must the
    kit's own games."""
    d = content.game_dir()
    files = sorted(x for x in d.rglob("*") if x.is_file())
    if len(files) > KIT_MAX_FILES:
        problems.append("kit: %d files; a world holds at most %d" % (len(files), KIT_MAX_FILES))
    for f in files:
        parts = f.relative_to(d).parts
        picture = f.suffix == ".png" and parts[0] == "art" and (len(parts) == 2 or (len(parts) == 3 and parts[1] == "terrain"))
        known = picture or (len(parts) == 1 and parts[0] in KIT_TOP_FILES) or (len(parts) == 2 and (
            (parts[0] in content.KINDS and f.suffix == ".md") or (parts[0] == "art" and f.suffix == ".txt")))
        if not known:
            problems.append("kit: unexpected file %s (a world holds %s, .md files in %s/, and pictures in art/)"
                            % ("/".join(parts), ", ".join(KIT_TOP_FILES), "/, ".join(content.KINDS)))
        elif not picture and len(f.read_text(encoding="utf-8", errors="replace")) > KIT_MAX_CHARS:
            problems.append("kit: %s is longer than %d characters" % ("/".join(parts), KIT_MAX_CHARS))
    for k in ("title", "start_room", "stats", "rolls", "coins", "inventory", "variants", "clock", "weather", "generation"):
        if w.get(k) in (None, "", [], {}):
            problems.append("kit: world.md needs %s:" % k)
    heads = [h for h, _ in content.sections(w["body"])]
    for h in ("Opening", "Tone", "Public knowledge"):
        if h not in heads:
            problems.append("kit: world.md needs a ## %s section" % h)
    try:
        own = content.game_json("look.json")
    except ValueError:
        own = {}  # reported already
    if not own:
        problems.append("kit: needs a look.json of its own")
    else:
        if not own.get("palette"):
            problems.append("kit: look.json needs a palette")
        if not (own.get("resource") or {}).get("name") or not (own.get("resource") or {}).get("icon"):
            problems.append("kit: look.json needs a resource with a name and an icon")
    rooms = content.ids("rooms")
    if not KIT_ROOMS[0] <= len(rooms) <= KIT_ROOMS[1]:
        problems.append("kit: %d rooms; a world has %d to %d" % (len(rooms), KIT_ROOMS[0], KIT_ROOMS[1]))
    for r in rooms:
        if not content.load("rooms", r).get("terrain"):
            problems.append("kit: rooms/%s.md needs a terrain" % r)
    start = w.get("start_room")
    if content.exists("rooms", str(start)):
        reached, todo = {start}, [start]
        while todo:
            for target in (content.load("rooms", todo.pop()).get("exits") or {}).values():
                dest = content.split_condition(target)[0]
                if dest not in reached and content.exists("rooms", dest):
                    reached.add(dest)
                    todo.append(dest)
        for r in rooms:
            if r not in reached:
                problems.append("kit: rooms/%s.md can't be reached from the start room by any exit" % r)
    if not any(content.load("rooms", r).get("encounters") for r in rooms):
        problems.append("kit: no room has an encounter table (encounters:)")
    people = [content.load("characters", c) for c in content.ids("characters")]
    if not KIT_CHARACTERS[0] <= len(people) <= KIT_CHARACTERS[1]:
        problems.append("kit: %d characters; a world has %d to %d" % (len(people), KIT_CHARACTERS[0], KIT_CHARACTERS[1]))
    if sum(1 for c in people if str(c.get("minor", "no")).lower() == "no") < 2:
        problems.append("kit: needs at least two characters with their own agents (minor: no)")
    if not any(content.plans(c["body"]) for c in people):
        problems.append("kit: needs a character with plans (## Plan: sections)")
    if not any(c.get("makes") for c in people):
        problems.append("kit: needs a maker (makes:)")
    if not any(content.load("rooms", r).get("build") for r in rooms):
        problems.append("kit: needs a build spot (build:) in a room, with a builder there")
    quests = content.ids("quests")
    if len(quests) != 1:
        problems.append("kit: %d quests; a world has exactly one" % len(quests))
    for q in quests:
        meta, where = content.load("quests", q), "kit: quests/%s.md" % q
        for k in ("started_by", "completed_by", "failed_by"):
            if not meta.get(k):
                problems.append("%s needs %s:" % (where, k))
        objectives = meta.get("objectives") or []
        if len(objectives) < 2:
            problems.append("%s needs at least two objectives" % where)
        ways = [str(meta.get("completed_by") or "")] + [m.group(2) for m in (_DONE.match(str(o)) for o in objectives) if m]
        if max(len(re.split(r"\s+or\s+", x.strip())) if x.strip() else 0 for x in ways) < 2:
            problems.append("%s needs at least two ways through: an 'or' in completed_by or in an objective's done-when" % where)
        parts = dict(content.sections(meta["body"]))
        if len(re.findall(r"^###\s+If\s", parts.get("Endings", ""), re.M)) < 2:
            problems.append("%s needs a ## Endings section with at least two ### If endings" % where)
        if "After the ending" not in parts:
            problems.append("%s needs a ## After the ending section" % where)
    if not content.ids("curses"):
        problems.append("kit: needs a curse")
    if not content.ids("scenes"):
        problems.append("kit: needs a side scene")


def validate_sim_complete(w, problems):
    """What a world needs for the simulation: a cast to play it, a maker and a builder to spend with, paid work and a
    buyer to earn from, and no free growth (every new place and thing is one somebody paid for).
    `validate --sim-complete`."""
    people = [content.load("characters", c) for c in content.ids("characters")]
    rooms = [content.load("rooms", r) for r in content.ids("rooms")]
    if not content.cast():
        problems.append("sim: needs a cast (cast.json)")
    if not any(c.get("makes") for c in people):
        problems.append("sim: needs a maker (makes:)")
    if not any(r.get("build") for r in rooms):
        problems.append("sim: needs a build spot (build:) in a room, with a builder there")
    if not any(r.get("work") for r in rooms):
        problems.append("sim: needs a room with paid work (work:)")
    if not any(c.get("buys") for c in people):
        problems.append("sim: needs a buyer (buys:)")
    gen = w.get("generation") or {}
    for k in ("rooms", "items"):
        if str(gen.get(k, "no")).lower() != "no":
            problems.append("sim: world.md generation %s must be no (every new %s is one somebody paid for)" % (k, k[:-1]))


# ---------------------------------------------------------------- rounds
# Each round every player still playing takes one whole turn, in an order drawn by `round start`: a balanced
# shuffle, from the run's seed and the round number (so two runs on one seed draw the same orders), choosing among
# all the orders the one that keeps each pair of players going first about equally often over the run. It uses its
# own random stream, so it never moves the dice. `round end` closes it, and in a simulation moves the world's clock.

def balanced_order(state, number):
    """(order, how it was drawn) for round `number`."""
    run = state["run"]
    ids = [pid for pid, pl in state["players"].items() if pl["status"] == "playing"]
    rng = random.Random("%s:%s:round %d" % (state["game"], run.get("seed"), number))
    orders = [list(o) for o in itertools.permutations(ids)]
    rng.shuffle(orders)
    before = run.setdefault("before", {})  # before[a][b]: the rounds a went before b

    def imbalance(order):
        total = 0
        for i, a in enumerate(order):
            for b in order[i + 1:]:
                diff = before.get(a, {}).get(b, 0) + 1 - before.get(b, {}).get(a, 0)
                total += diff * diff
        return total

    best = min(orders, key=imbalance)  # the first of the shuffled orders with the least imbalance
    return best, {"candidates": len(orders), "imbalance": imbalance(best),
                  "tied": sum(1 for o in orders if imbalance(o) == imbalance(best))}


def whose_turn(state):
    """The player whose turn it is in the open round (the first in its order not yet narrated), or None."""
    rs = state["run"].get("round_state")
    if not rs:
        return None
    return next((p for p in rs["order"] if p not in rs.get("done", []) and state["players"][p]["status"] == "playing"), None)


def cmd_round(args):
    """round start | round end: open the next round with its order, or close the open one."""
    state = load_state()
    run = state["run"]
    open_round = run.get("round_state")
    if args[0] == "start":
        if open_round:
            raise Refused("round %d is still open: `round end` first" % run["round"])
        number = run.get("round", 0) + 1
        if endings_waiting(state):
            raise Refused("an ending is still to be told: %s" % " ".join(ending_lines(state)))
        why = why_no_round(run, number)
        if why:
            raise Refused(why)
        order, draw = balanced_order(state, number)
        if not order:
            raise Refused("no one is still playing")
        for i, a in enumerate(order):
            for b in order[i + 1:]:
                pair = run["before"].setdefault(a, {})
                pair[b] = pair.get(b, 0) + 1
        asleep = [p for p in order if state["players"][p].get("asleep")]  # gone to bed early: they sleep through this round
        run["round"], run["round_state"] = number, {"order": order, "done": list(asleep)}
        log(state, "round", phase="start", order=order, draw=draw)
        for p in asleep:
            with acting(p):
                log(state, "asleep", room=state["players"][p]["location"])
        save_state(state)
        print("ROUND %d: %s" % (number, ", ".join("%s (%s)" % (state["players"][p]["name"], p) for p in order if p not in asleep)
                                or "no one awake to act: `round end`"))
        if asleep:
            print("ASLEEP (they sleep through this round, not asked): %s" % ", ".join(
                "%s (%s)" % (state["players"][p]["name"], p) for p in asleep))
        return
    if args[0] != "end":
        raise Refused("use: round start | round end")
    if not open_round:
        raise Refused("no round is open: `round start` first")
    number = run["round"]
    missing = [p for p in open_round["order"] if p not in open_round.get("done", []) and state["players"][p]["status"] == "playing"]
    if missing:
        raise Refused("round %d isn't over: still to act: %s" % (number, ", ".join(missing)))
    events = tick_move(state) if by_rounds() else []
    with acting(None):  # an offer lapsing as the round ends is no one's doing
        events += lapse_trades(state, number)
    run["round_state"] = None
    log(state, "round", phase="end", order=open_round["order"], events=events, world_turn_due=run["world_turn_due"])
    if run.get("stop") == "end":
        end_run(state)
    after = why_no_round(run, number + 1)
    save_state(state)
    print("ROUND %d ENDS." % number)
    for line in events + ending_lines(state):
        print(line)
    if after:
        print("NO MORE ROUNDS FOR NOW: %s" % after)


def why_no_round(run, number):
    """Why round `number` may not start (the owner paused or ended the run, or it has had its rounds), or None."""
    cap = int(SETTINGS["rounds"]["max_per_run"])
    if run.get("ended"):
        return "the run has ended (round %d was its last); a new run starts with newgame" % run.get("round", 0)
    if run.get("stop") == "end":
        return "the owner has ended the run; it closes when this round ends"
    if run.get("stop") == "pause":
        return "the owner has paused the run: `run resume` (or /rounds) to go on"
    if cap and number > cap:
        return "the run has had its %d rounds (rounds.max_per_run): raise the setting to go on, or `run end`" % cap
    return None


def end_run(state):
    """Close the run for good: no more rounds; the log gets its summary."""
    run = state["run"]
    run.update(ended=True, stop=None)
    log(state, "run", action="ended", rounds=run.get("round", 0), players={
        pid: {"location": pl["location"], "hp": pl["stats"]["hp"], "coins": pl["stats"]["coins"],
              "inventory": list(pl["inventory"]), "status": pl["status"]} for pid, pl in state["players"].items()})


def cmd_run(args):
    """run status | pause | resume | end: the owner's say over a run of rounds. A pause or an end never cuts into a
    round: the one in progress finishes, and the next doesn't start (`round start` refuses). An end closes the run."""
    state = load_state()
    run, what = state["run"], args[0]
    rs = run.get("round_state")
    in_round = "round %d is in progress (%s still to act), and finishes first" % (
        run["round"], len([p for p in rs["order"] if p not in rs.get("done", [])])) if rs else None
    if what == "status":
        cap = int(SETTINGS["rounds"]["max_per_run"])
        print("RUN: %s; %d round%s played, %s" % (
            "ended" if run.get("ended") else {"pause": "pause asked", "end": "end asked"}.get(run.get("stop"), "going"),
            run.get("round", 0) - (1 if rs else 0), "" if run.get("round", 0) - (1 if rs else 0) == 1 else "s",
            "at most %d per run" % cap if cap else "no limit on rounds"))
        print(cast_line(state))
        story = run["chronicle"][-BALANCE["world"]["chronicle_lines"]:]
        print("\n".join(["STORY SO FAR:"] + ["- " + c for c in story]) if story else "STORY SO FAR: nothing yet")
        notes = _section(world()["body"], "For the referee").strip()
        if notes:  # the world's own advice on its situations, so the kit needn't know them
            print("FOR THE REFEREE (this world's own notes; follow them):\n" + notes)
        if rs:
            nxt = whose_turn(state)
            replied = nxt and (state["players"][nxt].get("turn") or {}).get("round") == run["round"]
            print("ROUND %d OPEN: next to act: %s" % (run["round"], "nobody: `round end`" if not nxt else
                  "%s (they have replied: run their turn, then `narrate`)" % nxt if replied else "%s (waiting for their reply)" % nxt))
        why = None if rs else why_no_round(run, run.get("round", 0) + 1)
        if why:
            print("NEXT ROUND WAITS: %s" % why)
        return
    if what == "referee":  # tools/rounds.py, after each round's referee session
        try:
            number, session, usd, seconds, context = int(args[1]), args[2], float(args[3]), float(args[4]), int(args[5])
        except (IndexError, ValueError):
            raise Refused("use: run referee <round> <session id> <usd> <seconds> <largest context>")
        log(state, "referee", round_run=number, session=session, spend=usd, seconds=seconds, context=context)
        save_state(state)
        print("REFEREE for round %d logged: $%.2f, %ds, context up to %d tokens." % (number, usd, seconds, context))
        return
    if what not in ("pause", "resume", "end"):
        raise Refused("use: run status | pause | resume | end | referee <round> <session> <usd> <seconds> <context>")
    if run.get("ended"):
        raise Refused("the run has already ended; a new run starts with newgame")
    if what == "pause":
        run["stop"] = "pause"
        log(state, "run", action="pause")
        save_state(state)
        print("PAUSE ASKED: %s." % (in_round + "; then no round starts until `run resume`" if in_round else "no round starts until `run resume`"))
    elif what == "resume":
        if run.get("stop") != "pause":
            raise Refused("the run isn't paused")
        run["stop"] = None
        log(state, "run", action="resume")
        save_state(state)
        print("RESUMED: the next round may start.")
    else:
        run["stop"] = "end"
        log(state, "run", action="end")
        if not rs:
            end_run(state)
        save_state(state)
        print("END ASKED: %s." % (in_round + "; then the run closes" if in_round else "the run is closed"))


# ---------------------------------------------------------------- a player's turn, and what they remember
# A player's turn in a round: the referee hands the player's reply to `reply` (what they do, and why, in their own
# words), runs the rules commands for it with --as, and hands the story they're told to `narrate`, which ends the
# turn. Both come as files in proposals/ (written with the Write tool), so their words never pass through the shell.
# Each player's memory (players[<id>].memory) is written only here: `recent`, entries kept word for word, each with
# the round it was made, its kind (seen, told, did, reasoned) and how many briefs it has been handed back in; and
# `condensed`, older stretches in the player's own words (memory condense / memory store). The log keeps it all.

def player_arg(state, ident):
    """The player a referee command names, made the acting player."""
    global ACTOR
    if ident not in state["players"]:
        raise Refused("no one called %r is playing (players: %s)" % (ident, ", ".join(state["players"])))
    ACTOR = ident
    return state["players"][ident]


def text_arg(path, what, limit):
    """The text in a file the referee wrote (normally proposals/<name>.txt), used up once read."""
    if not Path(path).is_file():
        raise Refused("no %s file at %s" % (what, path))
    try:
        text = Path(path).read_text(encoding="utf-8").strip()
    finally:
        done_with([path])
    if not text:
        raise Refused("the %s is empty" % what)
    if len(text) > limit:
        raise Refused("the %s is at most %d characters (got %d)" % (what, limit, len(text)))
    return text


_REPLY = re.compile(r"^\s*(OPTIONS|DO|JOURNAL|NO LONGER)\s*:\s*", re.M)
_OPTION = re.compile(r"^\s*([-*•])\s*(.*?)\s*(?:\(for:\s*(.*?)\s*\))?\s*$")


def parse_reply(text):
    """{"do": ..., "journal": ..., "options": [...], "options_cut": bool, "no_longer": [...]} from a player's reply,
    or Refused. The options they weighed before choosing (OPTIONS:, one a line, `* ` marking the one chosen,
    "(for: ...)" what each serves) are kept up to turns.options_chars, then cut: private notes never refuse a reply.
    NO LONGER: lines name things on their What I know list that no longer hold (strike_learned)."""
    parts = _REPLY.split(text)
    found, no_longer = {}, []
    for label, body in zip(parts[1::2], parts[2::2]):
        if label == "NO LONGER":
            said = " ".join(body.split())[:BALANCE["turns"]["learned_chars"]]
            if said and said not in no_longer:
                no_longer.append(said)
            continue
        found[label.lower()] = body if label == "OPTIONS" else " ".join(body.split())
    if not found.get("do"):
        raise Refused("the reply has no DO: line")
    options, used, cut = [], 0, False
    for line in (found.get("options") or "").splitlines():
        m = _OPTION.match(line)
        if not m or not m.group(2):
            continue
        used += len(line.strip())
        if used > BALANCE["turns"]["options_chars"]:
            cut = True
            break
        options.append({"text": m.group(2), "for": m.group(3), "chosen": m.group(1) == "*"})
    return {"do": found["do"], "journal": found.get("journal", ""), "options": options, "options_cut": cut,
            "no_longer": no_longer[:int(SETTINGS["memory"]["learned_max"])]}


def strike_learned(pl, said):
    """Their own NO LONGER: lines against what they've learned (pl["learned"]): each takes off the line it names, as
    written or nearly (a few words' difference), or nothing. Only what they learned is theirs to strike: their
    starting facts and what the run has settled stay. [{"said", "struck"}], `struck` None when nothing matched."""
    def norm(s):
        return " ".join(re.sub(r"[^\w\s']", " ", s.casefold()).split())
    out = []
    for words in said:
        lines = pl.get("learned", [])
        keyed = {norm(x): x for x in lines}
        key = norm(words) if norm(words) in keyed else next(iter(difflib.get_close_matches(norm(words), list(keyed), n=1, cutoff=0.8)), None)
        line = keyed.get(key)
        if line:
            pl["learned"] = [x for x in lines if x != line]
        out.append({"said": words, "struck": line})
    return out


def remember(pl, kind, text, number):
    pl.setdefault("memory", {"recent": [], "condensed": []})["recent"].append(
        {"round": number, "kind": kind, "text": text, "uses": 0})


def open_turn(state, pid):
    """Refused unless it's `pid`'s turn and they have replied this round; returns the turn record."""
    run = state["run"]
    if whose_turn(state) != pid:
        raise Refused("it isn't %s's turn%s" % (pid, " (it's %s's)" % whose_turn(state) if whose_turn(state) else ": no round is open"))
    turn = state["players"][pid].get("turn") or {}
    return turn if turn.get("round") == run["round"] else None


def take_spend(args):
    """The arguments without `--spend <usd>`, and that amount (what a reply cost, from tools/ask.py), or None."""
    if "--spend" not in args:
        return args, None
    i = args.index("--spend")
    try:
        usd = float(args[i + 1])
    except (IndexError, ValueError):
        raise Refused("--spend takes an amount in dollars")
    return args[:i] + args[i + 2:], usd


def take_exact_model(args):
    """The arguments without `--exact-model <id>`, and that id (the model version claude -p said it answered on), or None."""
    if "--exact-model" not in args:
        return args, None
    i = args.index("--exact-model")
    if i + 1 >= len(args):
        raise Refused("--exact-model takes the model's id")
    return args[:i] + args[i + 2:], args[i + 1]


def exact(model):
    """The log field for the exact model version a reply came from, if it's known."""
    return {} if not model else {"exact_model": model}


def spent(usd):
    """The log field for what a reply cost, if it's known."""
    return {} if usd is None else {"spend": usd}


def cmd_reply(args):
    """reply <player> <file> [--spend <usd>]: the player's reply this turn: what they do (DO:) and why (JOURNAL:)."""
    args, usd = take_spend(args)
    args, instructions = take_instructions(args)
    args, exact_model = take_exact_model(args)
    state = load_state()
    pl = player_arg(state, args[0])
    if open_turn(state, args[0]):
        raise Refused("%s has already replied this round" % args[0])
    if len(args) < 2:
        raise Refused("usage: reply <player> <file>")
    limits = BALANCE["turns"]
    # room for a long list of options too, which parse_reply cuts rather than refuse the reply for
    reply = parse_reply(text_arg(args[1], "reply", limits["do_chars"] + limits["journal_chars"] + 4 * limits["options_chars"] + 40
                                 + int(SETTINGS["memory"]["learned_max"]) * (limits["learned_chars"] + 20)))
    for k in ("do", "journal"):
        if len(reply[k]) > limits[k + "_chars"]:
            raise Refused("the %s line is at most %d characters" % (k.upper(), limits[k + "_chars"]))
    number = state["run"]["round"]
    pl["turn"] = {"round": number, "do": reply["do"], "journal": reply["journal"], "room": pl["location"]}  # where it began
    remember(pl, "did", reply["do"], number)
    if reply["journal"]:
        remember(pl, "reasoned", reply["journal"], number)
    weighed = {"options": reply["options"]} if reply["options"] else {}  # in the log only: never in memory or a brief
    if reply["options_cut"]:
        weighed["options_cut"] = True
    if reply["no_longer"]:  # what they say no longer holds goes from what they've learned, by their own word
        weighed["no_longer"] = strike_learned(pl, reply["no_longer"])
    log(state, "action", do=reply["do"], journal=reply["journal"], model=model_for(state, args[0]), **exact(exact_model),
        versions=versions(state, args[0], instructions), **weighed, **spent(usd))
    save_state(state)
    print("REPLY from %s (%s): DO: %s" % (pl["name"], pronouns(args[0]), reply["do"]))
    if reply["journal"]:
        print("JOURNAL: %s" % reply["journal"])
    if reply["options"]:  # what they weighed stays theirs: the turn is run from the DO line alone
        print("OPTIONS: %d, kept in the log%s" % (len(reply["options"]), " (cut at the limit)" if reply["options_cut"] else ""))
    if reply["no_longer"]:  # their own memory, kept up by them: nothing for the turn to act on
        print("NO LONGER: %d struck from what they've learned (of %d named)" % (
            sum(1 for x in weighed["no_longer"] if x["struck"]), len(reply["no_longer"])))
    print("Now run the turn for it with --as %s, then `narrate %s <file>`." % (args[0], args[0]))


def cmd_narrate(args):
    """narrate <player> <file>: the story the player is told this turn. It ends their turn."""
    state = load_state()
    pl = player_arg(state, args[0])
    if not open_turn(state, args[0]):
        raise Refused("%s hasn't replied this round: `reply %s <file>` first" % (args[0], args[0]))
    if len(args) < 2:
        raise Refused("usage: narrate <player> <file>")
    if endings_waiting(state):
        with acting(args[0]):
            raise Refused("an ending is still to be told: %s" % " ".join(ending_lines(state)))
    text = text_arg(args[1], "narration", BALANCE["turns"]["narration_chars"])
    run = state["run"]
    remember(pl, "seen", text, run["round"])
    refresh_view(state)
    now = snapshot(state, args[0])  # the moment ends with what changed since the last one, not a copy of the pane
    line = changed_line(pl.get("snapshot"), now)
    if line:
        remember(pl, "changed", line, run["round"])
    pl["snapshot"] = now
    pl["acted_at"] = when_text(state)  # the world's time when they last acted: their next page says how far it has moved
    unrecorded = args[0] not in run["round_state"].get("outcomes", {})
    run["round_state"]["done"].append(args[0])
    log(state, "narration", text=text, changed=line or None)  # the line their memory keeps, for the owner's dashboard too
    save_state(state)
    print("NARRATED for %s (round %d). %s%s" % (pl["name"], run["round"],
          "Next: %s." % whose_turn(state) if whose_turn(state) else "Everyone has had their turn: `round end`.",
          " (No outcome was recorded for this turn: `outcome` comes before `narrate`.)" if unrecorded else ""))


def cmd_say(args):
    """say <file>: the player's words, spoken aloud. Everyone else playing in the room hears them: they go into
    each listener's memory, to be read on their next turn and answered then if they like (proposal 6.5)."""
    state = load_state()
    require_playing(state)
    words = text_arg(args[0], "words", BALANCE["turns"]["said_chars"]).strip('"“” ')  # used up, heard or not
    listeners = awake(state, players_here(state)[1:])
    if not listeners:  # only the world's people (or no one, or sleepers) to hear: nothing for anyone's memory, nothing to retry
        save_state(state)
        print("NOT KEPT: no one else of the cast here is awake to hear it; nothing to store (the world's people answer in the story).")
        return
    speaker = me(state)["name"]
    for pid in listeners:
        remember(state["players"][pid], "told", phrase("says", name=speaker, words=words), state["run"].get("round", 0))
    log(state, "speech", text=words, heard_by=listeners)
    save_state(state)
    print("SAID by %s, heard by %s: they'll read it on their next turn, and may answer then." % (
        speaker, ", ".join("%s (%s)" % (state["players"][p]["name"], p) for p in listeners)))


def passed_by(state, pid, turn):
    """{room: [the other players there]} for each room `pid` passed through this turn (neither where it began nor where
    it ends), with someone else in it: they saw them go by."""
    ends = {turn.get("room"), state["players"][pid]["location"]}
    out = {}
    for r in turn.get("passed", []):
        here = awake(state, [p for p, pl in state["players"].items() if p != pid and pl["location"] == r and pl["status"] == "playing"])
        if r not in ends and here:
            out[r] = here
    return out


def cmd_witnessed(args):
    """witnessed <file> [<flag> ...] [--in <room>]: what the others there saw and heard of this turn, as the referee
    tells it, the world's people's words included. Every other player in the room the turn began in, or the room it
    ends in, keeps it in memory as `seen`, to read on their next turn; with `--in <room>`, only those in a room the
    player passed through on the way, who saw them go by. The player's own words go with `say`. Flags named after the
    file are personal ones the player holds that the others learned too, by seeing or hearing it: each gets them."""
    state = load_state()
    require_playing(state)
    pid = actor_id(state)
    turn = open_turn(state, pid)
    if not turn:
        raise Refused("%s hasn't replied this round: `reply %s <file>` first" % (pid, pid))
    within = None
    if "--in" in args:
        i = args.index("--in")
        within, args = (args[i + 1] if i + 1 < len(args) else None), args[:i] + args[i + 2:]
    if not args:
        raise Refused("usage: witnessed <file> [<flag> ...] [--in <room>]")
    text = text_arg(args[0], "note", BALANCE["turns"]["witnessed_chars"])  # used up, refused or not
    passed = passed_by(state, pid, turn)
    if within is not None:
        if within not in passed:
            raise Refused("%s isn't a room %s passed through this turn with someone else in it (%s)" % (
                within, me(state)["name"], ", ".join(passed) or "there's none"))
        onlookers = passed[within]
    else:
        rooms = {turn.get("room", me(state)["location"]), me(state)["location"]}
        onlookers = awake(state, [p for p, pl in state["players"].items()
                                  if p != pid and pl["location"] in rooms and pl["status"] == "playing"])
    if not onlookers:  # nobody watching: nothing to keep, and nothing to retry (unless someone was passed on the way)
        save_state(state)
        print("NOT KEPT: no one else was there to see it%s" % (
            "; on the way, %s" % "; ".join("%s was in %s (`--in %s`)" % (", ".join(state["players"][p]["name"] for p in ps), r, r)
                                           for r, ps in passed.items()) if passed else "; nothing to store."))
        return
    learned = args[1:]
    for f in learned:
        if f not in personal_flags():
            raise Refused("%s isn't anyone's own flag: a shared flag is everyone's already" % f)
        if f not in me(state).get("flags", []):
            raise Refused("%s doesn't hold %s, so there was nothing of it to learn by watching" % (me(state)["name"], f))
    for p in onlookers:
        remember(state["players"][p], "seen", text, state["run"]["round"])
        own = state["players"][p].setdefault("flags", [])
        own += [f for f in learned if f not in own]
    noted = turn.setdefault("noted", [])
    noted.append(within or "ends")
    log(state, "witnessed", text=text, seen_by=onlookers, learned=learned, **({"passing": within} if within else {}))
    save_state(state)
    print("WITNESSED by %s: they'll read it on their next turn.%s" % (", ".join(
        "%s (%s)" % (state["players"][p]["name"], p) for p in onlookers), " They learned it too: %s." % ", ".join(learned) if learned else ""))
    for r, ps in passed.items():
        if r not in noted:
            print("ALSO PASSED: %s, where %s saw %s go by: a short note of that for them, `witnessed <file> --in %s`." % (
                r, ", ".join(state["players"][p]["name"] for p in ps), me(state)["name"], r))


# ---------------------------------------------------------------- trades: one person offers, the other decides
# An offer is a set of terms (`trade offer <file>`): what the offerer gives and what they ask back, belongings and
# coins, made to someone in the same place. The words go with `say`, as any words do. The one it's for sees the
# terms in their pane and decides on their own turn (`trade accept` or `trade decline`); nobody decides for them.
# An offer lapses when the two part, or at the end of the `trades.offer_rounds`th round after the one it was made in.

TERMS = ("items", "coins")


def turn_words(state):
    """The acting player's DO and JOURNAL lines from this round's turn, or (None, None)."""
    turn = me(state).get("turn") or {}
    if turn.get("round") != state["run"].get("round"):
        return None, None
    return turn.get("do"), turn.get("journal")


def terms_arg(data, side):
    """One side of an offer, {"items": [...], "coins": n}, checked for its shape; Refused otherwise."""
    raw = data.get(side) or {}
    if not isinstance(raw, dict) or set(raw) - set(TERMS):
        raise Refused("%s holds only %s" % (side, " and ".join(TERMS)))
    items, coins = raw.get("items") or [], raw.get("coins", 0)
    if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
        raise Refused("%s items must be a list of item ids" % side)
    for i in items:
        if not ent_exists("items", i):
            raise Refused("%s is a place, and places can't change hands" % i if ent_exists("rooms", i) else "no item called %r" % i)
    if not isinstance(coins, int) or isinstance(coins, bool) or coins < 0:
        raise Refused("%s coins must be a whole number, 0 or more" % side)
    return {"items": items, "coins": coins}


def short_of(state, terms):
    """What of `terms` the acting player doesn't have (item ids, then 'n coins'), as a list: empty if they have it all."""
    held, missing = list(me(state)["inventory"]), []
    for i in terms["items"]:
        if i in held:
            held.remove(i)
        else:
            missing.append(i)
    if terms["coins"] > me(state)["stats"]["coins"]:
        missing.append("%d %s" % (terms["coins"], currency()))
    return missing


def things_text(terms):
    """'Diving Knife (2) and 3 credits': one side of an offer, as the people in it would say it."""
    counts = {}
    for i in terms["items"]:
        counts[i] = counts.get(i, 0) + 1
    parts = ["%s%s" % (item(i).get("name", i), " (%d)" % n if n > 1 else "") for i, n in counts.items()]
    if terms["coins"]:
        parts.append("%d %s" % (terms["coins"], currency()))
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " %s " % phrase("and") + parts[-1]


def wanted_text(terms):
    """What an offer asks in return, as the pane says it: 'nothing', or 'for <things>'."""
    return phrase("nothing_back") if is_empty(terms) else phrase("for_things", things=things_text(terms))


def is_empty(terms):
    return not terms["items"] and not terms["coins"]


def open_trades(state, pid=None):
    """The offers still standing, oldest first; with `pid`, only those made by or to them."""
    return [t for t in state["run"].get("trades", {}).values()
            if t["status"] == "open" and (pid is None or pid in (t["from"], t["to"]))]


def close_trade(state, t, step, **fields):
    """An offer is over: declined, accepted or lapsed. The log keeps the terms with it."""
    t["status"] = step
    log(state, "trade", trade=t["id"], step=step, offered_by=t["from"], to=t["to"], give=t["give"], want=t["want"], **fields)


def is_gift(t):
    """An offer that asks nothing back: handed over face to face, it stays the other's to take after the two part."""
    return is_empty(t["want"]) and not is_empty(t["give"])


def lapse_trades(state, round_over=None):
    """Offers whose two have parted (a gift excepted) or of whom either has stopped playing lapse; when round
    `round_over` ends, so do those it was the last round for. Returns the lines for the referee."""
    lines, cap = [], int(BALANCE["trades"]["offer_rounds"])
    for t in open_trades(state):
        a, b = state["players"][t["from"]], state["players"][t["to"]]
        if (a["location"] != b["location"] and not is_gift(t)) or "playing" != a["status"] or "playing" != b["status"]:
            why = "parted"
        elif round_over is not None and round_over - t["round"] >= cap:
            why = "time"
        else:
            continue
        close_trade(state, t, "lapsed", why=why)
        lines.append("OFFER LAPSED: %s, %s to %s (%s)." % (t["id"], a["name"], b["name"],
                                                         "they're no longer together" if why == "parted" else "no answer in time"))
    return lines


def trade_arg(state, ident):
    """The open offer `ident`, or Refused."""
    t = state["run"].get("trades", {}).get(ident)
    if not t:
        raise Refused("no offer called %r" % ident)
    if t["status"] != "open":
        raise Refused("%s is over (%s)" % (ident, t["status"]))
    return t


def trade_lines(state, pid):
    """The pane's offers for `pid`: (made to them, made by them), each line as they would read it."""
    to_me, by_me = [], []
    for t in open_trades(state, pid):
        if t["to"] == pid:
            who = state["players"][t["from"]]["name"]
            if is_empty(t["give"]):
                to_me.append(phrase("asks_you", who=who, things=things_text(t["want"])))
            else:
                to_me.append(phrase("offers_you", who=who, give=things_text(t["give"]), want=wanted_text(t["want"])))
        else:
            who = state["players"][t["to"]]["name"]
            if is_empty(t["give"]):
                by_me.append(phrase("you_asked", who=who, things=things_text(t["want"])))
            else:
                by_me.append(phrase("you_offered_to", who=who, give=things_text(t["give"]), want=wanted_text(t["want"])))
    return to_me, by_me


def cmd_trade(args):
    """trade offer <file> | trade decline <tN>: an offer to someone here (a JSON file: {"to": <id>, "give": {"items":
    [...], "coins": n}, "want": {...}}, either side may be empty), or the one it's for turning it down."""
    state = load_state()
    require_playing(state)
    pid = actor_id(state)
    if args[0] == "offer":
        if len(args) < 2:
            raise Refused("usage: trade offer <file>")
        try:
            data = read_json_arg(args[1:])
        finally:
            done_with(args[1:])
        if set(data) - {"to", "give", "want"}:
            raise Refused("an offer holds only to, give and want")
        to = data.get("to")
        if to == pid:
            raise Refused("an offer is made to someone else")
        if to not in state["players"]:
            raise Refused("no one called %r is playing (players: %s)" % (to, ", ".join(state["players"])))
        if to not in players_here(state)[1:]:
            raise Refused("%s isn't here: an offer is made face to face" % state["players"][to]["name"])
        give, want = terms_arg(data, "give"), terms_arg(data, "want")
        if is_empty(give) and is_empty(want):
            raise Refused("the offer gives nothing and asks for nothing")
        missing = short_of(state, give)
        if missing:
            raise Refused("%s doesn't have %s to give" % (me(state)["name"], ", ".join(missing)))
        lines = []
        for old in open_trades(state, pid):
            if old["from"] == pid and old["to"] == to:
                close_trade(state, old, "lapsed", why="replaced")
                lines.append("OFFER LAPSED: %s, replaced by this one." % old["id"])
        run = state["run"]
        run["trade_n"] = run.get("trade_n", 0) + 1
        t = {"id": "t%d" % run["trade_n"], "from": pid, "to": to, "give": give, "want": want, "round": run.get("round"),
             "room": me(state)["location"], "status": "open"}
        run.setdefault("trades", {})[t["id"]] = t
        words, journal = turn_words(state)
        log(state, "trade", trade=t["id"], step="offered", offered_by=pid, to=to, give=give, want=want, words=words, journal=journal)
        save_state(state)
        print("OFFERED %s to %s (%s): gives %s; asks for %s. %s reads it on their next turn and decides then: "
              "`trade accept %s` or `trade decline %s`, with --as %s." % (
                  t["id"], state["players"][to]["name"], to, things_text(give) if not is_empty(give) else "nothing",
                  things_text(want) if not is_empty(want) else "nothing", state["players"][to]["name"], t["id"], t["id"], to))
        for line in lines:
            print(line)
        return
    if args[0] == "accept":
        if len(args) < 2:
            raise Refused("usage: trade accept <offer>")
        t = trade_arg(state, args[1])
        if t["to"] != pid:
            raise Refused("only %s can accept %s" % (state["players"][t["to"]]["name"], t["id"]))
        accept_trade(state, t)
        return
    if args[0] == "decline":
        if len(args) < 2:
            raise Refused("usage: trade decline <offer>")
        t = trade_arg(state, args[1])
        if t["to"] != pid:
            raise Refused("only %s can turn down %s" % (state["players"][t["to"]]["name"], t["id"]))
        words, journal = turn_words(state)
        close_trade(state, t, "declined", words=words, journal=journal)
        save_state(state)
        print("DECLINED %s: %s turns down %s's offer. The story tells %s how it was turned down." % (
            t["id"], me(state)["name"], state["players"][t["from"]]["name"], state["players"][t["from"]]["name"]))
        return
    raise Refused("use: trade offer <file> | trade accept <offer> | trade decline <offer>")


def accept_trade(state, t):
    """Hand over both sides of offer `t`, all or nothing: every check is made before anything moves. A refusal says
    what the story can tell, and leaves the offer standing."""
    giver, taker = t["from"], t["to"]
    names = {p: state["players"][p]["name"] for p in (giver, taker)}
    if giver not in players_here(state)[1:] and not is_gift(t):  # a gift was already held out to them
        raise Refused("%s isn't here any more: things change hands face to face" % names[giver])
    for pid, side in ((giver, "give"), (taker, "want")):
        with acting(pid):
            missing = short_of(state, t[side])
        if missing:
            raise Refused("%s doesn't have %s now" % (names[pid], ", ".join(missing)))
    weight = lambda items: sum(int(item(i).get("weight", 0)) for i in items)  # noqa: E731
    for pid, gets, goes in ((taker, t["give"]["items"], t["want"]["items"]), (giver, t["want"]["items"], t["give"]["items"])):
        with acting(pid):
            load = carried_weight(state) - weight(goes) + weight(gets)
            if gets and load > carry_limit(state):
                raise Refused("%s can't carry it all: %s would make a load of %d, and %d is the most they can carry"
                              % (names[pid], things_text({"items": gets, "coins": 0}), load, carry_limit(state)))
    for frm, to, side in ((giver, taker, "give"), (taker, giver, "want")):
        for i in t[side]["items"]:
            with acting(frm):
                remove_from_inventory(state, i)  # a thing held in hand is let go of first
                log_use(state, i, "traded")
            state["players"][to]["inventory"].append(i)
        if t[side]["coins"]:
            with acting(frm):
                change_coins(state, -t[side]["coins"], "trade", note=t["id"])
            with acting(to):
                change_coins(state, t[side]["coins"], "trade", note=t["id"])
    words, journal = turn_words(state)
    after = {p: {"coins": state["players"][p]["stats"]["coins"], "items": list(state["players"][p]["inventory"])} for p in (giver, taker)}
    close_trade(state, t, "accepted", words=words, journal=journal, after=after)
    save_state(state)
    print("ACCEPTED %s: %s takes %s's offer. %s hands over %s; %s hands over %s." % (
        t["id"], names[taker], names[giver], names[giver], things_text(t["give"]) if not is_empty(t["give"]) else "nothing",
        names[taker], things_text(t["want"]) if not is_empty(t["want"]) else "nothing"))
    for pid in (taker, giver):
        with acting(pid):
            print("  %s now has %d %s, carrying: %s  [weight %d/%d]" % (names[pid], me(state)["stats"]["coins"], currency(),
                  ", ".join(me(state)["inventory"]) or "nothing", carried_weight(state), carry_limit(state)))


# ---------------------------------------------------------------- contests: a grab at what another person holds
# Turns are one person's at a time, so two people reach for the same thing in one turn only when the one whose turn
# it is grabs at what another holds (proposal 6.4). The other holds on, unasked, as anyone would: both roll, and the
# higher wins; a tie stays with the one holding it. Nobody is hurt. They answer on their own turn.

def cmd_contest(args):
    """contest <your stat> <their id> <their stat> --take <item>: grab at something another person here holds. Each
    rolls the check die plus the stat named for them; the higher total takes it, and a tie leaves it where it is."""
    state = load_state()
    require_playing(state)
    pid = actor_id(state)
    take = None
    if "--take" in args:
        i = args.index("--take")
        take, args = (args[i + 1] if i + 1 < len(args) else None), args[:i] + args[i + 2:]
    if len(args) != 3 or not take:
        raise Refused("usage: contest <your stat> <their id> <their stat> --take <item>")
    mine, other, theirs = args[0].lower(), args[1], args[2].lower()
    for stat in (mine, theirs):
        if stat not in STATS:
            raise Refused("stat must be one of %s" % ", ".join(STATS))
    if other == pid:
        raise Refused("a contest is with someone else")
    if other not in state["players"]:
        raise Refused("no one called %r is playing (players: %s)" % (other, ", ".join(state["players"])))
    names = {p: state["players"][p]["name"] for p in (pid, other)}
    if other not in players_here(state)[1:]:
        raise Refused("%s isn't here" % names[other])
    if take not in state["players"][other]["inventory"]:
        raise Refused("%s isn't holding %s" % (names[other], take))
    check_carry(state, take)  # before any die is rolled: a grab that couldn't be carried off isn't tried
    rolls = {}
    for p, stat in ((pid, mine), (other, theirs)):
        nat = dice.roll(BALANCE["check_die"])[1][0]
        rolls[p] = {"stat": stat, "d20": nat, "mod": attempt_mod(state, p, stat), "total": nat + attempt_mod(state, p, stat)}
    winner = pid if rolls[pid]["total"] > rolls[other]["total"] else other
    if winner == pid:
        with acting(other):
            remove_from_inventory(state, take)  # a thing held in hand is let go of first
            log_use(state, take, "snatched")
        me(state)["inventory"].append(take)
    words, journal = turn_words(state)
    log(state, "contest", against=other, item=take, rolls=rolls, winner=winner, words=words, journal=journal)
    save_state(state)
    print("CONTEST for %s: %s %s d20 %d %+d = %d; %s %s d20 %d %+d = %d -> %s" % (
        item(take).get("name", take), names[pid], mine, rolls[pid]["d20"], rolls[pid]["mod"], rolls[pid]["total"],
        names[other], theirs, rolls[other]["d20"], rolls[other]["mod"], rolls[other]["total"],
        "%s TAKES it  [weight %d/%d]" % (names[pid], carried_weight(state), carry_limit(state)) if winner == pid else
        "%s KEEPS hold of it%s" % (names[other], " (a tie)" if rolls[pid]["total"] == rolls[other]["total"] else "")))
    print("Tell it as it happens, never the numbers; %s was there and sees it in the onlookers' note (`witnessed`). "
          "They answer on their own turn." % names[other])


# ---------------------------------------------------------------- endings: a quest decided is news for everyone
# In a world with several people, one person's deed can decide the game's own quest for all of them (stopping the
# clock wins it for the town). The one whose deed it was hears its ending in their story; everyone else comes to
# hear of it (`ending <file>`), and their lives go on. The story isn't stored, nor a round started, until they have.

def decided(state):
    """{quest: "done" | "lost"} for each of the game's own quests (not side quests) decided for anyone still playing."""
    out = {}
    for pid in playing(state):
        with acting(pid):
            flags = condition_flags(state)
        for q in ent_ids("quests"):
            if not is_generated("quests", q) and q not in out:
                v = quest_view(q, flags)
                if v["complete"] or v["failed"]:
                    out[q] = "done" if v["complete"] else "lost"
    return out


def endings_waiting(state):
    """The quests decided that no one has been told of yet."""
    told = state["run"].get("endings", {})
    return {q: o for q, o in decided(state).items() if q not in told}


def ending_lines(state):
    """What the referee is told to do about the endings waiting, or []."""
    waiting = endings_waiting(state)
    if not waiting:
        return []
    between = ACTOR is None or ACTOR not in state["players"] or not whose_turn(state)
    lines = ["ENDING: %s is %s." % (ent("quests", q).get("name", q), o) for q, o in waiting.items()]
    if between:
        lines.append("Everyone hears of it: write what the town comes to see and hear of it, in the third person, and "
                     "store it with `ending <file>` (no --as) before the next `round start`.")
    else:
        name = state["players"][ACTOR]["name"]
        lines.append("Tell %s its ending in their story, from the quest's endings (`show quests %s`), inside the fiction: "
                     "their life goes on. Everyone else hears of it: write what the town comes to see and hear of it, in "
                     "the third person, and store it with `ending <file>` before `narrate`." % (name, next(iter(waiting))))
    return lines


def cmd_ending(args):
    """ending <file>: what everyone else comes to see and hear of a quest's ending, for their next turn."""
    state = load_state()
    waiting = endings_waiting(state)
    if not waiting:
        raise Refused("no quest has been decided that anyone is still to hear of")
    teller = None if no_one(state) else actor_id(state)
    if teller:
        require_playing(state)
    text = text_arg(args[0], "news", BALANCE["turns"]["witnessed_chars"])
    hearers = [p for p in playing(state) if p != teller]
    for p in hearers:
        remember(state["players"][p], "seen", text, state["run"].get("round", 0))
    for p in playing(state):  # the teller lives it in their story; everyone keeps what the town saw of it
        keep(state["players"][p], text, state["run"].get("round", 0))
    told = state["run"].setdefault("endings", {})
    for q, o in waiting.items():
        told[q] = {"outcome": o, "round": state["run"].get("round", 0), "by": teller, "text": text}
    log(state, "ending", text=text, quests=waiting, heard_by=hearers)
    save_state(state)
    print("ENDING TOLD: %s will read it on their next turn." % (", ".join(
        "%s (%s)" % (state["players"][p]["name"], p) for p in hearers) or "no one else is playing, so no one"))


def cmd_voiced(args):
    """voiced <file> [--spend <usd>]: one call tools/voice.py made to the npc or world agent, for the log: the
    agent, who or what it was for, the model and effort, what the referee added to the brief, and the reply as given.
    The brief itself is in the log already, as the npc-brief or world-brief command's output."""
    args, usd = take_spend(args)
    state = load_state()
    path = Path(args[0])
    if not path.is_file():
        raise Refused("no record of the call at %s" % path)
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    finally:
        done_with([str(path)])
    if not isinstance(rec, dict) or rec.get("agent") not in ("npc", "world") or not all(
            isinstance(rec.get(k), str) for k in ("about", "model", "added", "reply")):
        raise Refused("a call's record names its agent (npc or world), what it was about, the model, what was added and the reply")
    tags = record_texts(state, {"instructions:" + Path(rec["instructions"]).stem: agent_instructions(rec["instructions"])}
                        ) if isinstance(rec.get("instructions"), str) else {}
    log(state, "voice", agent=rec["agent"], about=rec["about"], model=rec["model"], effort=rec.get("effort"), versions=tags,
        **exact(rec.get("exact_model") if isinstance(rec.get("exact_model"), str) else None),
        added=rec["added"], again=bool(rec.get("again")), reply=rec["reply"], **spent(usd))
    print("VOICED: the %s agent, for %s (%s)" % (rec["agent"], rec["about"], rec["model"]))


def memory_rounds(pl):
    return sorted({e["round"] for e in pl.get("memory", {}).get("recent", [])})


def memory_chars(pl):
    return sum(len(e["text"]) for e in pl.get("memory", {}).get("recent", []))


def condensing_due(pl):
    """The rounds to condense now (the oldest, leaving `memory.recent_rounds`), or []."""
    m, rounds = SETTINGS["memory"], memory_rounds(pl)
    keep = int(m["recent_rounds"])
    if len(rounds) >= keep + int(m["condense_every"]) or (memory_chars(pl) > int(m["max_chars"]) and len(rounds) > keep):
        return rounds[:len(rounds) - keep]
    return []


def cmd_memory(args):
    """memory condense <player> | memory store <player> <file> [--spend <usd>]: fold older rounds into the player's
    own words."""
    args, usd = take_spend(args)
    args, instructions = take_instructions(args)
    args, exact_model = take_exact_model(args)
    state = load_state()
    if len(args) < 2 or args[0] not in ("condense", "store"):
        raise Refused("use: memory condense <player> | memory store <player> <file>")
    pl = player_arg(state, args[1])
    mem = pl.setdefault("memory", {"recent": [], "condensed": []})
    if args[0] == "condense":
        if SETTINGS["memory"]["condenser"] != "self":
            raise Refused("only the self condenser is built so far (memory.condenser: self)")
        rounds = condensing_due(pl)
        if not rounds:
            print("NOTHING TO CONDENSE for %s: %d rounds held word for word." % (pl["name"], len(memory_rounds(pl))))
            return
        mem["condensing"] = rounds
        save_state(state)
        print(condensing_brief(state, args[1], rounds))
        return
    rounds = mem.get("condensing")
    if not rounds:
        raise Refused("no condensing is waiting for %s: `memory condense %s` first" % (args[1], args[1]))
    if rounds != condensing_due(pl)[:len(rounds)] or not set(rounds) <= set(memory_rounds(pl)):
        mem.pop("condensing")
        save_state(state)
        raise Refused("%s's memory has changed since; run `memory condense %s` again" % (args[1], args[1]))
    if len(args) < 3:
        raise Refused("usage: memory store <player> <file>")
    turns, most = BALANCE["turns"], int(SETTINGS["memory"]["learned_max"])
    raw = text_arg(args[2], "memory", turns["memory_chars"] + 20 + most * (turns["learned_chars"] + 20))
    text, learned, cut = parse_thinkback(raw)
    if not text:
        raise Refused("the reply has no MEMORY: line")
    if len(text) > turns["memory_chars"]:
        raise Refused("the memory is at most %d characters (got %d)" % (turns["memory_chars"], len(text)))
    given = learned is not None  # a reply with no LEARNED: lines leaves the list as it was
    if given:
        pl["learned"] = learned
    before = [e for e in mem["recent"] if e["round"] in rounds]
    mem["recent"] = [e for e in mem["recent"] if e["round"] not in rounds]
    mem["condensed"].append({"rounds": [rounds[0], rounds[-1]], "kind": "condensed", "text": text,
                             "round": state["run"]["round"], "uses": 0})
    mem.pop("condensing")
    log(state, "memory", rounds=[rounds[0], rounds[-1]], text=text, replaced=len(before), learned=list(pl.get("learned", [])),
        learned_given=given, learned_cut=cut, sees=SETTINGS["memory"]["thinkback_sees"], model=model_for(state, args[1]),
        **exact(exact_model), versions=versions(state, args[1], instructions), **spent(usd))
    save_state(state)
    print("REMEMBERED by %s, rounds %d-%d, in their own words (%d entries folded in); %s." % (
        pl["name"], rounds[0], rounds[-1], len(before),
        "%d things learned%s" % (len(pl["learned"]), " (cut at the limit)" if cut else "") if given else "what they've learned left as it was"))


_THINKBACK = re.compile(r"^\s*(MEMORY|LEARNED)\s*:\s*", re.I)


def parse_thinkback(raw):
    """(memory, learned, cut) from a think-back reply: the MEMORY: text as one paragraph, and the LEARNED: lines (a
    line each, or listed under one LEARNED:), or None when it gives none. Lines past memory.learned_max, or longer
    than turns.learned_chars, are cut, never refused: what they've learned is theirs, like their options."""
    memory, learned, part, found = [], [], "MEMORY", False
    for line in raw.splitlines():
        m = _THINKBACK.match(line)
        if m:
            part, line = m.group(1).upper(), line[m.end():]
            found = found or part == "LEARNED"
        if part == "MEMORY":
            memory.append(line)
            continue
        thing = re.sub(r"^\s*[-*•]\s*", "", line).strip()
        if thing and thing not in learned:
            learned.append(thing)
    limit, most = BALANCE["turns"]["learned_chars"], int(SETTINGS["memory"]["learned_max"])
    cut = len(learned) > most or any(len(x) > limit for x in learned)
    return " ".join(" ".join(memory).split()), [x[:limit].rstrip() for x in learned[:most]] if found else None, cut


# ---------------------------------------------------------------- the words a person reads
# Every fixed word a person in the cast reads lives in rules/people/, not here: brief.md, one phrase per line (its
# name, a colon, the words, with {gaps} the code fills), and thinkback.md, the think-back prompt whole. The code
# decides which sections appear and in what order; the files say them. PHRASES lists each phrase and the gaps it
# may use, which `validate` holds the file to.

PEOPLE = ROOT / "rules" / "people"
PHRASES = {
    "who_i_am": (), "i_am": ("name", "pronouns", "personality"), "how_i_talk": ("voice",), "drives": ("motivations",),
    "what_i_want": ("wants",), "steer_clear": ("avoids",), "wont_do": ("wont",), "comes_first": ("priorities",), "then": (),
    "people_i_know": ("people",), "person_i_know": ("who", "how"), "i_know": (), "everyone_knows": (),
    "begins": (), "remember": (), "lately": (), "moment": ("n",), "did": (), "why": (), "happened": (), "told": (),
    "stood": (), "where_you_are": (), "place": ("place",), "ways_on": ("ways",), "way": ("direction", "place"),
    "with_you": ("people",), "no_one": (), "you": (), "you_are_named": ("name",), "health": ("hp", "max_hp", "stats"), "money": ("n", "currency"),
    "carrying": ("things", "load", "limit"), "nothing": (), "in_hand": (), "made_for_you": (),
    "own_places": ("places",), "being_built": ("name",),
    "waiting": ("thing", "maker", "price", "currency", "in_trade"), "in_trade": ("things",), "or": (),
    "offered_to_you": (), "you_offered": (), "asks_you": ("who", "things"), "offers_you": ("who", "give", "want"),
    "you_asked": ("who", "things"), "you_offered_to": ("who", "give", "want"), "nothing_back": (),
    "for_things": ("things",), "and": (), "working_on": (), "quest_done": (), "quest_failed": (), "step_done": (),
    "people_met": (), "places_been": (), "talk": (), "attempts": (), "closing": (), "says": ("name", "words"),
    "finished": ("place", "direction", "where", "builder"), "finished_rumor": ("place", "direction", "where"),
    "changed": (), "change_went": ("before", "after"), "change_money": ("currency", "before", "after"),
    "change_health": ("before", "after"), "change_got": ("things",), "change_lost": ("things",),
    "change_in_hand": ("things",), "change_put_away": ("things",), "change_waiting": ("things",),
    "change_building": ("things",), "change_own": ("things",), "change_met": ("people",),
    "thinkback_voice": ("voice",), "thinkback_note": (), "learned_none": (), "time_on_day": ("time", "n"), "since_last": ("then", "now"),
    "rented": ("place", "n"), "paid_bed": ("place", "nights"), "tonight": (), "nights": ("n",), "let_ended": ("place",),
    "board": ("notices",), "notice": ("text", "n"), "notice_undated": ("text",),
    "you_need": ("needs",), "you_want": ("wants",), "taken_on": (), "food_fed": (), "food_due": (), "food_hungry": (),
    "food_weak": (), "sleep_rested": (), "sleep_tired": (), "sleep_exhausted": (), "sleep_slept": (), "sleep_time": (),
}
THINKBACK_GAPS = ("name", "voice", "self", "stretch", "learned", "learned_max")
UNIVERSE_GAPS = ("currency",)
_WORDS = {}


def people_file(name):
    """The text of rules/people/<name>, as it was when this command started reading it."""
    if name not in _WORDS:
        path = PEOPLE / name
        if not path.is_file():
            raise Refused("rules/people/%s is missing" % name)
        _WORDS[name] = path.read_text(encoding="utf-8")
    return _WORDS[name]


def read_phrases(text):
    """brief.md's phrases: {name: words}, and the lines it couldn't read."""
    phrases, bad = {}, []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        m = re.match(r"^([a-z_]+):[ \t]*(.*?)[ \t]*$", line)
        if not m:
            bad.append("line %d isn't `name: words`" % n)
        elif m.group(1) in phrases:
            bad.append("line %d: %s is given twice" % (n, m.group(1)))
        else:
            phrases[m.group(1)] = m.group(2)
    return phrases, bad


def gaps(text):
    return set(re.findall(r"\{([^{}]*)\}", text))


def thinkback_text():
    """thinkback.md without its opening <!-- comment -->, and without the newline that ends the file."""
    text = re.sub(r"\A\s*<!--.*?-->[ \t]*\n", "", people_file("thinkback.md"), flags=re.S)
    return text[:-1] if text.endswith("\n") else text


def universe_lines():
    """universe.md's sentences, how life goes anywhere, with the world's money filled in."""
    lines = [l.strip() for l in people_file("universe.md").splitlines() if l.strip() and not l.startswith("#")]
    try:
        return [l.format(currency=currency()) for l in lines]
    except (KeyError, IndexError, ValueError):
        raise Refused("rules/people/universe.md has a gap the code doesn't fill (`rpg.py validate`)")


def public_knowledge():
    """The world's `## Public knowledge` (world.md), as written: what everyone around here knows."""
    return _section(world()["body"], "Public knowledge").strip()


def people_problems():
    """What's wrong with the words in rules/people/: a phrase missing, unknown or with a gap the code doesn't fill."""
    try:
        phrases, out = read_phrases(people_file("brief.md"))
        think = thinkback_text()
    except Refused as e:
        return [str(e)]
    out = ["brief.md: " + x for x in out]
    out += ["brief.md: %s is missing" % k for k in PHRASES if k not in phrases]
    out += ["brief.md: %s isn't a phrase the code uses" % k for k in phrases if k not in PHRASES]
    out += ["brief.md: %s has a gap the code doesn't fill: %s" % (k, ", ".join(sorted(gaps(v) - set(PHRASES[k]))))
            for k, v in phrases.items() if k in PHRASES and gaps(v) - set(PHRASES[k])]
    try:
        universe = people_file("universe.md")
    except Refused as e:
        return out + [str(e)]
    if gaps(universe) - set(UNIVERSE_GAPS):
        out.append("universe.md has a gap the code doesn't fill: %s" % ", ".join(sorted(gaps(universe) - set(UNIVERSE_GAPS))))
    if gaps(think) - set(THINKBACK_GAPS):
        out.append("thinkback.md has a gap the code doesn't fill: %s" % ", ".join(sorted(gaps(think) - set(THINKBACK_GAPS))))
    try:  # the definitions, and every archetype against them
        defs = json.loads(people_file("defaults.json"))
    except (Refused, ValueError) as e:
        return out + ["defaults.json: %s" % e]
    scale = defs.get("scale") or {}
    if not all(isinstance(scale.get(k), int) for k in ("min", "max", "ordinary")) or not scale["min"] <= scale["ordinary"] <= scale["max"]:
        return out + ["defaults.json: scale needs whole numbers min <= ordinary <= max"]
    for part in ("attributes", "ways"):
        for k, d in (defs.get(part) or {}).items():
            if not (isinstance(d, dict) and all(isinstance(d.get(x), str) and d[x].strip() for x in ("name", "low", "high"))):
                out.append("defaults.json: %s %s needs a name, a low line and a high line" % (part, k))
    for path in sorted(ARCHETYPES.glob("*.json")):
        try:
            arch = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as e:
            out.append("../cast/%s: not valid JSON (%s)" % (path.name, e))
            continue
        out += ["../" + x for x in archetype_problems(arch, defs, "cast/%s" % path.name)]
        if arch.get("id") != path.stem:
            out.append("../cast/%s: id must be %s, as the file is named" % (path.name, path.stem))
    return out


def phrase(key, /, **fill):
    """One phrase from brief.md, its gaps filled (a gap may be called `name`, so the phrase's own is `key`)."""
    if "phrases" not in _WORDS:
        _WORDS["phrases"] = read_phrases(people_file("brief.md"))[0]
    phrases = _WORDS["phrases"]
    if key not in phrases:
        raise Refused("rules/people/brief.md has no %s phrase (`rpg.py validate` says what's wrong)" % key)
    try:
        return phrases[key].format(**fill)
    except (KeyError, IndexError, ValueError):
        raise Refused("rules/people/brief.md: %s has a gap the code doesn't fill (`rpg.py validate`)" % key)


# ---------------------------------------------------------------- which version of each text a person was given
# Every brief, action, memory and voice entry in the log carries `versions`: a short tag (8 hex characters of a
# sha256) for each text that shaped what was read or answered: brief.md, thinkback.md, the person's cast entry
# (`cast:<id>`), and the instructions the agent was asked with (`instructions:<agent>`, named by tools/ask.py or
# tools/voice.py, which sent them). The first time a version appears in a run its whole text goes in the log once
# (a `text` entry), so a run says exactly what it was made with, an edit partway through included.

def text_tag(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def agent_instructions(path):
    """An agent's instructions as tools/ask.py sends them: the file without its front matter, stripped."""
    try:
        text = (ROOT / path).read_text(encoding="utf-8")
    except OSError:
        raise Refused("no instructions file at %s" % path)
    m = re.match(r"^---\n.*?\n---\n", text, re.S)
    return (text[m.end():] if m else text).strip()


def take_instructions(args):
    """The arguments without `--instructions <file>`, and that file (what tools/ask.py or voice.py asked with), or None."""
    if "--instructions" not in args:
        return args, None
    i = args.index("--instructions")
    if i + 1 >= len(args):
        raise Refused("--instructions takes the file the agent was asked with")
    return args[:i] + args[i + 2:], args[i + 1]


def record_texts(state, texts):
    """Tags for {name: text}; each version not yet in this run's log is logged whole, once."""
    seen = state["run"].setdefault("texts", {})
    tags = {}
    for name, text in texts.items():
        tags[name] = text_tag(text)
        if tags[name] not in seen.get(name, []):
            seen.setdefault(name, []).append(tags[name])
            log(state, "text", name=name, tag=tags[name], text=text)
    return tags


def versions(state, pid, instructions=None):
    """The tags of what shaped what `pid` read or answered, for their log entry."""
    texts = {"brief": people_file("brief.md"), "thinkback": people_file("thinkback.md"),
             "universe": people_file("universe.md"), "public:" + content.game_id(): public_knowledge(),
             "cast:" + pid: json.dumps(cast_entry(pid), sort_keys=True, ensure_ascii=False)}
    if cast_entry(pid).get("archetype"):  # made from an archetype: which one, and the definitions it was rated against
        texts["archetype:" + cast_entry(pid)["archetype"]] = json.dumps(archetype(cast_entry(pid)["archetype"]), sort_keys=True, ensure_ascii=False)
        texts["definitions"] = json.dumps(definitions(), sort_keys=True, ensure_ascii=False)
    if instructions:
        texts["instructions:" + Path(instructions).stem] = agent_instructions(instructions)
    return record_texts(state, texts)


def snapshot(state, pid):
    """How things stand for `pid`, as far as a moment's what-changed line looks: where they are, health, money, what
    they carry and hold in hand, their own places, what's being built or waits to be paid for, and who they've met.
    Names, not ids, so a thing gone from the world can still be named. Read from the view (save_state's refresh)."""
    v, run = state["view"]["players"][pid], state["run"]
    return {"place": v["location_name"], "hp": v["stats"]["hp"], "coins": v["stats"]["coins"],
            "items": {i["id"]: i["name"] for i in v["items"]}, "in_hand": [i["id"] for i in v["items"] if i["equipped"]],
            "places": [ent("rooms", r).get("name", r) for r, rec in run["rooms"].items() if rec["meta"].get("owner") == pid],
            "building": [c["record"]["meta"]["name"] for c in run["commissions"].values() if c.get("by") == pid and c["status"] == "building"],
            "waiting": [(run["items"].get(i) or c.get("record") or {}).get("meta", {}).get("name", i)
                        for i, c in run["commissions"].items() if c.get("ordered_by") == pid and c["status"] == "ordered"],
            "met": [c["name"] for c in v["people"]]}


def changed_line(before, now):
    """What changed between two snapshots, as one line for the moment's end ("you went from ... to ...; ..."), or
    "" when nothing did, or when there's nothing to compare with (a save from before snapshots were kept)."""
    if not before:
        return ""
    new = lambda key: [x for x in now[key] if x not in before[key]]
    parts = []
    if before["place"] != now["place"]:
        parts.append(phrase("change_went", before=before["place"], after=now["place"]))
    if before["coins"] != now["coins"]:
        parts.append(phrase("change_money", currency=currency(), before=before["coins"], after=now["coins"]))
    if before["hp"] != now["hp"]:
        parts.append(phrase("change_health", before=before["hp"], after=now["hp"]))
    got = [n for i, n in now["items"].items() if i not in before["items"]]
    lost = [n for i, n in before["items"].items() if i not in now["items"]]
    held = [now["items"][i] for i in now["in_hand"] if i not in before["in_hand"]]
    let_go = [now["items"][i] for i in before["in_hand"] if i not in now["in_hand"] and i in now["items"]]
    for key, things in (("change_got", got), ("change_lost", lost), ("change_in_hand", held), ("change_put_away", let_go),
                        ("change_waiting", new("waiting")), ("change_building", new("building")), ("change_own", new("places"))):
        if things:
            parts.append(phrase(key, things=", ".join(things)))
    if new("met"):
        parts.append(phrase("change_met", people=", ".join(new("met"))))
    return "; ".join(parts) + "." if parts else ""


def memory_text(entries):
    """Memory entries as the player reads them: round by round, in the second person."""
    lines, current = [], None
    label = {"did": phrase("did"), "reasoned": phrase("why"), "seen": phrase("happened"), "told": phrase("told"),
             "changed": phrase("changed"), "status": phrase("stood")}
    for e in entries:
        if e["round"] != current:
            current = e["round"]
            lines.append("")
            lines.append(phrase("moment", n=current))
        if e["kind"] == "status":  # a whole pane, as saves before what-changed lines kept: its headings become labels
            lines.append("%s:" % label["status"])
            lines += ["  %s:" % l[3:] if l.startswith("## ") else "    " + l for l in e["text"].splitlines() if l.strip()]
        else:
            lines.append("%s: %s" % (label.get(e["kind"], e["kind"]), e["text"]))
    return "\n".join(lines).strip()


def condensing_brief(state, pid, rounds):
    """What the player is asked to do to remember a stretch: their moments in those rounds, as the brief shows them."""
    entries = [e for e in state["players"][pid]["memory"]["recent"] if e["round"] in rounds]
    return thinkback_prompt(state, pid, memory_text(entries))


def thinkback_prompt(state, pid, stretch):
    """The think-back for a stretch: in their own voice, first person, seeing their whole "Who I am" note or only
    their voice (memory.thinkback_sees), and the list of what they've learned, to rewrite. (tools/bench.py asks it
    of a stretch kept from a run.)"""
    pl = state["players"][pid]
    voice = cast_entry(pid).get("voice", "")
    if is_blank(pid):  # no note and no voice: only their name, in the think-back's own first line
        self_text = ""
    elif SETTINGS["memory"]["thinkback_sees"] == "voice":
        self_text = phrase("thinkback_voice", voice=voice)
    else:
        self_text = "\n\n".join([phrase("thinkback_note"), "\n".join(who_i_am(state, pid))])
    learned = "\n".join("- " + x for x in pl.get("learned", [])) or phrase("learned_none")
    try:  # rules/people/thinkback.md, its gaps filled
        return thinkback_text().format(name=pl["name"], voice=voice, self=self_text, stretch=stretch,
                                       learned=learned, learned_max=SETTINGS["memory"]["learned_max"])
    except (KeyError, IndexError, ValueError):
        raise Refused("rules/people/thinkback.md has a gap the code doesn't fill (`rpg.py validate`)")


# ---------------------------------------------------------------- what a player is shown: pane and brief
# The pane is the margin a human player reads beside the story, as plain text: the same data (the save's view,
# computed for this player), never anything more. The brief is everything a player agent is handed on its turn:
# its opening (first turn only), its memory, then the pane. Neither ever carries GM-only text, flags, prices it
# hasn't been told, other rooms, other players' private state, the log or the meter, nor any word of the
# machinery: to the player it's a life, not a game.

def pane_text(state):
    """The acting player's pane, as plain text."""
    pid, pl = actor_id(state), me(state)
    v = state["view"]["players"][pid]
    look_cfg, stats = content.look(), pl["stats"]
    labels = look_cfg["stat_labels"]
    lines = [phrase("where_you_are"), phrase("place", place=v["location_name"] + "".join(
        ", " + x for x in (when_text(state), state["view"]["weather"]) if x))]
    if pl.get("acted_at") and when_text(state) and pl["acted_at"] != when_text(state):  # time passed, in the world's own words
        lines.append(phrase("since_last", then=pl["acted_at"], now=when_text(state)))
    exits = me(state)["map"].get(pl["location"], {}).get("exits", {})
    if exits:
        lines.append(phrase("ways_on", ways="; ".join(phrase("way", direction=d, place=ent("rooms", r).get("name", r) if ent_exists("rooms", r) else r)
                                                    for d, r in exits.items())))
    company = [c["name"] for c in v["characters_here"]] + [state["players"][o]["name"] for o in players_here(state)[1:]]
    lines.append(phrase("with_you", people=", ".join(company) if company else phrase("no_one")))
    if has_board(ent("rooms", pl["location"])) and notices(state, pl["location"]):
        lines.append(phrase("board", notices="; ".join(
            phrase("notice", text=n["text"], n=n["day"]) if n.get("day") else phrase("notice_undated", text=n["text"])
            for n in reversed(notices(state, pl["location"])))))
    lines += ["", phrase("you")] + ([phrase("you_are_named", name=pl["name"])] if is_blank(pid) else []) + [
              phrase("health", hp=stats["hp"], max_hp=stats["max_hp"],
                     stats=", ".join("%s %+d" % (labels.get(k, k.capitalize()), stat(state, pid, k)) for k in STATS)),
              phrase("money", n=stats["coins"], currency=currency())]
    carried = ["%s%s%s" % (i["name"], " " + phrase("in_hand") if i["equipped"] else "", " " + phrase("made_for_you") if i["own"] else "")
               for i in v["items"]]
    lines.append(phrase("carrying", things=", ".join(carried) if carried else phrase("nothing"), load=v["weight"], limit=v["carry_limit"]))
    mine = [ent("rooms", r).get("name", r) for r, rec in state["run"]["rooms"].items() if rec["meta"].get("owner") == pid]
    mine += [phrase("rented", place=ent("rooms", r).get("name", r), n=let_of(state, r)["until"])
             for r in state["run"].get("lets", {}) if let_of(state, r) and let_of(state, r)["tenant"] == pid]
    if mine:
        lines.append(phrase("own_places", places=", ".join(mine)))
    for r, n in sorted(pl.get("paid_beds", {}).items()):
        if n:
            lines.append(phrase("paid_bed", place=ent("rooms", r).get("name", r), nights=phrase("tonight") if n == 1 else phrase("nights", n=n)))
    going = [c for c in state["run"]["commissions"].values() if c.get("by") == pid and c["status"] == "building"]
    for c in going:
        lines.append(phrase("being_built", name=c["record"]["meta"]["name"]))
    waiting = [(i, c) for i, c in state["run"]["commissions"].items() if c.get("ordered_by") == pid and c["status"] == "ordered"]
    for i, c in waiting:
        meta = (state["run"]["items"].get(i) or c.get("record") or {}).get("meta", {})
        trade = accepts(c["maker"]) if c["kind"] == "item" else []
        lines.append(phrase("waiting", thing=meta.get("name", i), maker=ent("characters", c["maker"]).get("name", c["maker"]),
                            price=c["price"], currency=currency(), in_trade=" " + phrase("in_trade", things=(" %s " % phrase("or")).join(
                                item(t).get("name", t) for t in trade)) if trade else ""))
    to_me, by_me = trade_lines(state, pid)
    if to_me:
        lines += ["", phrase("offered_to_you")] + ["- " + x for x in to_me]
    if by_me:
        lines += ["", phrase("you_offered")] + ["- " + x for x in by_me]
    quests = [q for q in v["quests"] if q["id"] in pl.get("taken_on", [])]  # the problem is known; caring is their own
    taken = []
    for q in quests:
        state_word = " " + phrase("quest_done") if q["complete"] else " " + phrase("quest_failed") if q["failed"] else ""
        taken.append("%s%s: %s" % (q["name"], state_word, " ".join((phrase("step_done") + " " if o["done"] else "") + o["text"]
                                                                 for o in q["objectives"])))
    needs = needs_words(state, pid)
    entry = cast_entry(pid)
    wants = "; ".join(entry.get("wants_and_needs") or entry.get("motivations") or []) if SETTINGS["brief"]["wants"] else ""
    if needs or wants:  # needs, wants and what they've taken on, side by side
        lines += ["", phrase("working_on")]
        if needs:
            lines.append(phrase("you_need", needs=" ".join(needs)))
        if wants:
            lines.append(phrase("you_want", wants=wants))
        if taken:
            lines += [phrase("taken_on")] + ["- " + x for x in taken]
    elif taken:
        lines += ["", phrase("working_on")] + taken
    if v["people"]:
        lines += ["", phrase("people_met"), ", ".join("%s%s" % (c["name"], " (%s)" % c["role"] if c["role"] else "") for c in v["people"])]
    places = [e["name"] for r, e in me(state)["map"].items() if r != pl["location"]]
    if places:
        lines += ["", phrase("places_been"), ", ".join(places)]
    if pl.get("heard"):  # only what they've heard, among people (overhear)
        lines += ["", phrase("talk")] + ["- " + r for r in pl["heard"]]
    return "\n".join(lines)


def cmd_pane(args):
    """pane <player>: the player's pane as plain text: what a human player reads in the margin."""
    state = load_state()
    player_arg(state, args[0])
    print(pane_text(state))


def dice_lines(state, pid):
    """The dice lines from the player's last turn, as a human's dice tray shows them."""
    entries = [e for e in log_entries(state["run"]["id"]) if e["kind"] == "command" and e.get("player") == pid and not e["refused"]]
    if not entries:
        return []
    last = entries[-1].get("round")
    tray = ("CHECK", "PLAYER ATTACKS", "ROLL", "HURT", "HEAL", "USED")
    return [line.strip() for e in entries if e.get("round") == last for line in e["output"].splitlines() if line.strip().startswith(tray)]


def cmd_brief(args):
    """brief <player>: everything the player agent is handed on its turn."""
    args, instructions = take_instructions(args)
    state = load_state()
    pl = player_arg(state, args[0])
    mem = pl.setdefault("memory", {"recent": [], "condensed": []})
    entry = cast_entry(args[0])
    out = [] if is_blank(args[0]) else who_i_am(state, args[0]) + [""]  # a blank person has no note (their name is under You)
    # what they knew when the night began, what they've kept as learned since (theirs to revise at each think-back),
    # and what this run has settled for good (never fading)
    known = list(entry.get("knows") or []) + list(pl.get("learned", [])) + [k["text"] for k in pl.get("kept", [])]
    if known:
        out += [phrase("i_know")] + ["- " + k for k in known] + [""]
    everyone = ["- " + l for l in universe_lines()] + [l for l in public_knowledge().splitlines() if l.strip()]
    out += [phrase("everyone_knows")] + everyone + [""]
    if entry.get("opening") and not mem["condensed"] and not any(e["kind"] == "did" for e in mem["recent"]):  # words heard before a first turn
        out += [phrase("begins"), entry["opening"], ""]
    if mem["condensed"]:
        out += [phrase("remember"), "\n\n".join(c["text"] for c in mem["condensed"]), ""]  # a paragraph a stretch
    if mem["recent"]:
        out += [phrase("lately"), memory_text(mem["recent"]), ""]
    overhear(state)  # waking into the turn among people, they hear what's being said
    out.append(pane_text(state))
    if SETTINGS["brief"]["dice_lines"]:
        lines = dice_lines(state, args[0])
        if lines:
            out += ["", phrase("attempts")] + lines
    out += ["", phrase("closing")]
    text = "\n".join(out)
    for e in mem["condensed"] + mem["recent"]:
        e["uses"] += 1
    log(state, "brief", text=text, versions=versions(state, args[0], instructions))
    save_state(state)
    print(text)


def who_i_am(state, pid):
    """The "Who I am" note that opens every brief, as lines: the cast writes who they are in their own first person,
    a note to themselves, like their journal and memories. The think-back shows it too (memory.thinkback_sees)."""
    return note_lines(cast_entry(pid), state["players"][pid]["name"], pronouns(pid), lambda who: person_name(state, who))


def note_lines(entry, name, their_pronouns, name_of):
    """The Who I am note for a cast entry, as lines. One made from an archetype (PERSON-STRUCTURE-PROPOSAL.md 5.7):
    their backstory, how they talk, what they want, steer clear of and won't do, what comes first, who they know, and
    how they are; a hand-written one: their personality, how they talk, and what drives them."""
    made = "archetype" in entry
    out = [phrase("who_i_am"), phrase("i_am", name=name, pronouns=their_pronouns, personality=entry.get("backstory" if made else "personality", "")),
           phrase("how_i_talk", voice=entry.get("voice", ""))]
    if made:
        out += [phrase("what_i_want", wants="; ".join(entry.get("wants_and_needs") or [])),
                phrase("steer_clear", avoids="; ".join(entry.get("avoids_and_dislikes") or [])),
                phrase("wont_do", wont="; ".join(entry.get("wont_do") or [])),
                phrase("comes_first", priorities=(" %s " % phrase("then")).join(entry.get("priorities") or []))]
    else:
        out.append(phrase("drives", motivations="; ".join(entry.get("motivations") or [])))
    if entry.get("people"):
        out.append(phrase("people_i_know", people="; ".join(phrase("person_i_know", who=name_of(k["who"]), how=k["how"].rstrip("."))
                                                            for k in entry["people"])))
    if made and entry.get("how_i_am"):
        out.append(entry["how_i_am"])
    return out


def person_name(state, ident):
    """Someone a cast entry's `people` names: another of the cast, or one of the world's characters."""
    if ident in state["players"]:
        return state["players"][ident]["name"]
    return ent("characters", ident).get("name", ident) if ent_exists("characters", ident) else ident


def keep(pl, text, number):
    """Something this run has settled that a person never forgets (an ending, a place finished for them): shown
    under "What I know" every turn from now on."""
    pl.setdefault("kept", []).append({"round": number, "text": text})


def cast_entry(pid):
    """The player's entry in the game's cast: who they are, and what they know at the start (`opening`)."""
    return next((e for e in content.cast() if e.get("id") == pid), {})


def is_blank(pid):
    """A blank person (`"blank": true` in the cast): no Who I am note, no opening, their name under You."""
    return cast_entry(pid).get("blank") is True


def cmd_log(args):
    """log [n]: the last entries of this run's log, one line each."""
    state = load_state()
    n = int(args[0]) if args and args[0].isdigit() else 10
    for e in log_entries(state["run"]["id"])[-n:]:
        head = "r%s.%s %s" % (e.get("round") or "-", e.get("order_position") or "-", e.get("player") or "-")
        if e["kind"] == "command":
            first = (e["output"].splitlines() or [""])[0]
            print("%s command %s: %s" % (head, " ".join([e["command"]] + e["args"]), first[:100]))
        elif e["kind"] == "coins":
            print("%s coins %+d (%s) -> %d" % (head, e["delta"], e["reason"], e["balance"]))
        else:
            rest = {k: v for k, v in e.items() if k not in ("kind", "t", "round", "order_position", "player", "move")}
            print("%s %s %s" % (head, e["kind"], json.dumps(rest, ensure_ascii=False)[:160]))


def cmd_validate(args):
    """validate [--game <id> | --dir <folder>] [--kit-complete] [--sim-complete] [--sim-strict]: check the kit's games
    (or one installed game, or a draft's folder) for broken references, formats and soundness; --kit-complete adds what
    a forged world needs, --sim-complete what a simulation needs, --sim-strict what a world built for the simulation
    needs (and its warnings become errors). Warnings are printed and don't fail a world."""
    kit, sim, strict = "--kit-complete" in args, "--sim-complete" in args, "--sim-strict" in args
    args = [a for a in args if a not in ("--kit-complete", "--sim-complete", "--sim-strict")]
    if "--dir" in args:
        want = args[args.index("--dir") + 1:][:1]
        folder = (ROOT / want[0]).resolve() if want else None
        if not folder or not folder.is_dir():
            raise Refused("validate --dir <folder>: no such folder")
        if not (folder / "world.md").is_file():
            raise Refused("%s has no world.md yet: write world.md first" % want[0])
        targets = [(want[0].rstrip("/"), folder)]
    elif "--game" in args:
        want = args[args.index("--game") + 1:][:1]
        if not want or want[0] not in content.list_games():
            raise Refused("validate --game <id>, one of: %s" % ", ".join(content.list_games()))
        targets = [(want[0], None)]
    else:
        targets = [(g, None) for g in content.authored_games()]
    if not targets:
        raise Refused("no games installed in games/")
    bad = False
    kit_art = terrain_art_problems(KIT_ART, list(content.kit_look().get("terrain") or {}))
    if kit_art:
        bad = True
        print("\n".join("kit: rules/art/terrain/%s" % x for x in kit_art))
    words = people_problems()
    if words:
        bad = True
        print("\n".join("kit: rules/people/%s" % x for x in words))
    for g, folder in targets:
        try:
            choose_game(g, folder)
            problems, summary = validate_game(kit, sim, strict)
        except (Refused, KeyError, ValueError) as e:  # a file too broken to read: say so, never stop with a refusal
            problems, summary = ["checking stopped early: %s" % (e.args[0] if isinstance(e, KeyError) and e.args else e)], ""
        if problems:
            bad = True
            print("\n".join("%s: %s" % (g, x) for x in problems))
        else:
            print("CONTENT OK: %s: %s%s%s%s" % (g, summary, " (kit-complete)" if kit else "", " (sim-complete)" if sim else "",
                                                " (sim-strict)" if strict else ""))
        print("\n".join("WARNING: %s: %s" % (g, x) for x in WARNINGS) if WARNINGS else "", end="\n" if WARNINGS else "")
        WARNINGS[:] = []
    if bad:
        sys.exit(1)


# ---------------------------------------------------------------- the meter and the owner's switches

def resave_view():
    """After the meter moves, refresh the save's view so the interface shows it (when there's a save)."""
    try:
        state = load_state()
    except Refused:
        return
    save_state(state)


def meter_line():
    m, res = meter(), resource()
    return "%s %d/%d" % (res["name"], m["left"], m["capacity"])


def cmd_curse_text(args):
    """curse-text <the player's words>: the words as they come out under any curse, as JSON for the prompt hook:
    {"curses": [names], "text": "<as they came out>"}. No curse (or no game): the words unchanged."""
    text = " ".join(args)
    try:
        state = load_state()
    except Refused:
        state = None
    active = active_curses(state) if state else []
    print(json.dumps({"curses": [c.get("name", c["id"]) for c in active], "text": cursed_words(state, text) if active else text},
                     ensure_ascii=False))


def cmd_meter(args):
    """meter [refill]: the meter, or fill it to capacity (the SessionStart hook does this)."""
    if args and args[0] == "refill":
        write_json(METER, {"left": meter()["capacity"], "session": uuid.uuid4().hex[:8]})
        resave_view()
        print("REFILLED: %s" % meter_line())
        return
    if args:
        raise Refused("use: meter | meter refill")
    print("METER: %s (%s)" % (meter_line(), meter_state()))


def cmd_settings(args):
    """settings: the owner's switches for this game and what each action costs. Change them with tools/settings.py."""
    v = settings_view()
    on = lambda b: "on" if b else "off"  # noqa: E731
    print("GAME: %s, preset %s" % (content.game_id(), v["preset"]))
    print("METER: %s; refills each time Claude Code is opened here" % meter_line())
    print("PRICES: %s" % ", ".join("%s %d" % kv for kv in v["prices"].items()))
    a = v["npc_agents"]
    print("NPC AGENTS: %s, up to %d lines between two per turn%s" % (
        on(a["on"]), a["lines_per_exchange"], "; game master voices %s" % ", ".join(a["off_for"]) if a["off_for"] else ""))
    print("WORLD TURNS: %s, every %s; people with plans: %s" % (on(v["world_turns"]["on"]), ticks_text(v["world_turns"]["every_moves"]),
                                                             on(v["world_turns"]["on"] and v["world_turns"]["plans"])))
    g = v["generation"]
    print("GENERATION: %s, at most %d per run; kinds: %s" % (on(g["on"]), g["max_per_run"], ", ".join(g["kinds"]) or "none"))
    print("CRAFTING: %s, at most %d orders per run" % (on(v["crafting"]["on"]), v["crafting"]["max_per_run"]))
    print("BUILDING: %s, at most %d orders per run" % (on(v["building"]["on"]), v["building"]["max_per_run"]))
    pr = v["promotion"]
    print("PROMOTION: %s, at most %d per run, after %d conversations" % (on(pr["on"]), pr["max_per_run"], pr["after_conversations"]))
    sc = v["side_scenes"]
    print("SIDE SCENES: %s, at most %d per run, %d replies each" % (on(sc["on"] and v["npc_agents"]["on"]), sc["max_per_run"], sc["replies"]))
    print("NEW WORLDS: %s" % on(v["new_worlds"]["on"]))
    cap = int(SETTINGS["rounds"]["max_per_run"])
    print("ROUNDS: the world's clock moves by %s; %s" % (SETTINGS["rounds"]["clock"],
                                                       "at most %d rounds per run" % cap if cap else "no limit on rounds"))
    m = SETTINGS["memory"]
    print("MEMORY: the last %s rounds word for word; older ones condensed every %s rounds, or past %s characters held (%s); "
          "the think-back sees %s, and keeps at most %s things learned"
          % (m["recent_rounds"], m["condense_every"], m["max_chars"], m["condenser"],
             "the whole Who I am note" if m["thinkback_sees"] == "who_i_am" else "only their voice", m["learned_max"]))
    model = SETTINGS["cast"]["model"]
    print("PEOPLE: %s" % ("each asked on their own model, as cast.json names it" if model == "own" else "everyone asked on %s" % model))
    print("NEEDS: %s; wants %s under What you're working on" % (
        "on (" + (", ".join(world_needs()) or "none in this world") + ")" if SETTINGS["needs"]["on"] else "off",
        "shown" if SETTINGS["brief"]["wants"] else "not shown"))


# ---------------------------------------------------------------- games: list, show, switch

def shelved(ident):
    return SHELF / ("%s.json" % ident)


def save_summary(data):
    if not isinstance(data, dict):
        return "no game yet"
    if data.get("version", 1) < OLDEST_VERSION:
        return "an old save that can't be continued"
    players = (data.get("players") or {}).values()
    status = "playing" if any(pl.get("status") == "playing" for pl in players) else "over"
    return "%s, %s in" % (status, moves_text((data.get("run") or {}).get("moves", 0)))


def title_of(ident):
    content.use_game(ident)
    title = content.load_world().get("title", ident)
    content.use_game(active_game())
    return title


def cmd_game(args):
    """game [list | show | switch <id>]: the installed games, and which one is being played."""
    current = active_game()
    action = args[0] if args else "show"
    if action == "list":
        for g in content.list_games():
            data = read_json(SAVE) if g == current else read_json(shelved(g))
            print("%s %s: %s (%s)%s" % ("*" if g == current else " ", g, title_of(g), save_summary(data),
                                       ", a world forged in play" if content.is_forged(g) else ""))
        return
    if action == "show":
        print("GAME: %s (%s), in %s/" % (title_of(current), current, content.game_dir().relative_to(ROOT)))
        return
    if action != "switch":
        raise Refused("use: game list | game show | game switch <id>")
    games = content.list_games()
    if len(args) < 2 or args[1] not in games:
        raise Refused("game switch <id>, one of: %s" % ", ".join(games))
    target = args[1]
    if target == current:
        print("ALREADY PLAYING: %s" % title_of(target))
        return
    if SAVE.is_file():
        SHELF.mkdir(parents=True, exist_ok=True)
        os.replace(SAVE, shelved(current))
    if shelved(target).is_file():
        os.replace(shelved(target), SAVE)
    write_json(ACTIVE, {"game": target})
    choose_game(target)
    if not SAVE.is_file():
        print("SWITCHED to %s. No game yet: start one with /newgame." % title_of(target))
        return
    print("SWITCHED to %s. The saved game continues." % title_of(target))
    with acting(next(iter((read_json(SAVE) or {}).get("players") or {"": None}))):  # as its first player sees it
        cmd_look([])


# ---------------------------------------------------------------- the forge: new worlds on demand (Stage 8)
# `/newworld` asks `forge quote`, confirms with the player, then `forge start` charges the meter and makes a draft:
# state/forge/<draft>/ with forge.json (the request) and world/, where a worldsmith agent writes the world in the
# background. It checks its work with `validate --dir … --kit-complete` and, when done, writes READY. `forge install`
# checks it once more and moves it to state/worlds/<id>/, where /game lists it.

DRAFT = re.compile(r"^draft_[0-9a-f]{6}$")
SENTENCE_CHARS = 300


def drafts():
    """Every draft folder with a request in it, oldest first."""
    if not FORGE.is_dir():
        return []
    found = [d for d in FORGE.iterdir() if DRAFT.match(d.name) and (d / "forge.json").is_file()]
    return [d.name for d in sorted(found, key=lambda d: (read_json(d / "forge.json") or {}).get("started", ""))]


def draft_info(d):
    return read_json(FORGE / d / "forge.json") or {}


def draft_status(d):
    """ready: the worldsmith says it's done; forging: it's still at work (started this session, not stopped);
    unfinished: it stopped without finishing, or Claude Code was closed while it worked."""
    if (FORGE / d / "READY").is_file():
        return "ready"
    info = draft_info(d)
    return "unfinished" if info.get("status") == "stopped" or info.get("session") != meter_session() else "forging"


def why_no_forge():
    """New worlds don't use the meter (the owner's call, 2026-10-23); only the owner's switch stops one."""
    if not SETTINGS["new_worlds"]["on"]:
        return "the owner has new worlds switched off"
    return None


def forge_brief(d):
    """The worldsmith's whole prompt: what the player asked for, where to write, and how to check."""
    info, folder = draft_info(d), "state/forge/%s/world" % d
    taken = ", ".join("%s (%s)" % (title_of(g), g) for g in content.list_games())
    asked = ('The player asked for: "%s"' % info["sentence"]) if info.get("sentence") else \
        "The player asked for nothing in particular: surprise them with a small world of your own choosing."
    lines = [
        "# Forge a new world", "",
        asked, "",
        "- Read rules/WORLD-GUIDE.md first. It has every file format and everything the world must contain.",
        "- The kit's games in games/ are worked examples. Learn from them; don't copy their places, people or plots.",
        "- Write every file of the new world in %s/ and nowhere else." % folder,
        "- Check it with exactly: python3 rules/rpg.py validate --dir %s --kit-complete" % folder,
        "- Fix every problem it reports and check again, until it says CONTENT OK.",
        "- Then, as your very last step, write the file state/forge/%s/READY containing one line: the world's title." % d,
        "- Titles already taken (don't reuse or imitate one): %s." % taken,
    ]
    if info.get("resumes"):
        lines += ["", "An earlier attempt left files in %s/. Run the check first, and finish the world from what's there." % folder]
    return "\n".join(lines)


def world_id(title):
    """A new world's id from its title: 'The Salt Mines' -> salt_mines, made unique among installed games."""
    base = re.sub(r"[^a-z0-9]+", "_", str(title).lower()).strip("_")
    base = re.sub(r"^the_", "", base)[:30].strip("_")
    if not base or not base[0].isalpha():
        base = ("world_" + base)[:30].strip("_")
    taken = {f.name for base in (content.GAMES, content.WORLDS) if base.is_dir() for f in base.iterdir()}
    ident, n = base, 2
    while ident in taken:
        ident, n = "%s_%d" % (base[:27], n), n + 1
    return ident


def cmd_forge(args):
    """forge quote | start [sentence] | resume <draft> | status | install <draft> | discard <draft>."""
    action, rest = args[0], args[1:]
    if action == "quote":
        why = why_no_forge()
        if why:
            print("FORGE OFF: %s. Nothing starts." % why)
        else:
            print("FORGE: a new world can be made. It doesn't use the meter.")
        for d in drafts():
            status = draft_status(d)
            if status == "unfinished":
                print("UNFINISHED: %s, %s: it can be finished." % (
                    d, '"%s"' % draft_info(d)["sentence"] if draft_info(d).get("sentence") else "a surprise world"))
            elif status == "forging":
                print("FORGING: %s is still being made; only one at a time." % d)
            else:
                print("NEW WORLD READY: %s: run `forge install %s`." % (d, d))
        return
    if action == "status":
        for d in drafts():
            print("DRAFT %s: %s, %s" % (d, draft_status(d), '"%s"' % draft_info(d)["sentence"] if draft_info(d).get("sentence") else "a surprise world"))
        if not drafts():
            print("NO DRAFTS")
        return
    if action == "start":
        why = why_no_forge()
        if why:
            raise Refused("no new world: %s" % why)
        if any(draft_status(d) == "forging" for d in drafts()):
            raise Refused("a world is already being forged; only one at a time")
        sentence = " ".join(rest).strip() or None
        if sentence and len(sentence) > SENTENCE_CHARS:
            raise Refused("describe the world in one sentence, at most %d characters" % SENTENCE_CHARS)
        d = "draft_%s" % uuid.uuid4().hex[:6]
        (FORGE / d / "world").mkdir(parents=True)
        write_json(FORGE / d / "forge.json", {"sentence": sentence, "started": datetime.datetime.now().isoformat(timespec="seconds"),
                                              "session": meter_session(), "status": "forging", "resumes": 0})
        resave_view()
        print("FORGE STARTED: %s. Spawn the worldsmith in the background with exactly this brief (see the newworld skill):\n" % d)
        print(forge_brief(d))
        return
    if action in ("resume", "install", "discard"):
        if not rest or rest[0] not in drafts():
            raise Refused("forge %s <draft>, one of: %s" % (action, ", ".join(drafts()) or "none"))
        d = rest[0]
    else:
        raise Refused("use: forge quote | start [sentence] | resume <draft> | status | install <draft> | discard <draft>")
    info = draft_info(d)
    if action == "discard":
        shutil.rmtree(FORGE / d)
        print("DISCARDED: %s" % d)
        return
    if action == "resume":
        if draft_status(d) != "unfinished":
            raise Refused("%s is %s, not unfinished" % (d, draft_status(d)))
        why = why_no_forge()
        if why:
            raise Refused("can't finish it: %s" % why)
        if any(draft_status(x) == "forging" for x in drafts()):
            raise Refused("a world is already being forged; only one at a time")
        info.update(session=meter_session(), status="forging", resumes=int(info.get("resumes", 0)) + 1)
        write_json(FORGE / d / "forge.json", info)
        resave_view()
        print("FORGE RESUMED: %s. Spawn the worldsmith in the background with exactly this brief (see the newworld skill):\n" % d)
        print(forge_brief(d))
        return
    # install: the worldsmith has stopped (the GM installs on its completion notice, or when `look` says ready)
    if draft_status(d) != "ready":
        info["status"] = "stopped"
        write_json(FORGE / d / "forge.json", info)
        raise Refused("%s stopped before the world was finished (no READY). It waits; the player can finish it later "
                      "with /newworld. Say nothing in the story." % d)
    folder, current = FORGE / d / "world", active_game()
    try:
        choose_game("draft", folder)
        problems, _ = validate_game(kit=True)
        title = content.load_world().get("title") if not problems else None
    except (KeyError, ValueError) as e:
        problems, title = ["%s" % e], None
    finally:
        choose_game(current)
    if problems:
        (FORGE / d / "READY").unlink()
        info["status"] = "stopped"
        write_json(FORGE / d / "forge.json", info)
        raise Refused("%s doesn't pass the checks, so it isn't installed (%s%s). It waits, unfinished; the player can "
                      "finish it later with /newworld. Say nothing in the story." % (
                          d, "; ".join(problems[:3]), "; …" if len(problems) > 3 else ""))
    ident = world_id(title)
    content.WORLDS.mkdir(parents=True, exist_ok=True)
    shutil.move(str(folder), str(content.WORLDS / ident))
    home = content.WORLDS / ident
    if not (home / "settings.json").is_file():
        write_json(home / "settings.json", {"preset": "normal", "overrides": {}})
    write_json(home / "forged.json", {"title": title, "sentence": info.get("sentence"), "forged": datetime.date.today().isoformat()})
    shutil.rmtree(FORGE / d)
    try:  # the toast, in whatever game is being played
        state = load_state()
        add_signal(state, "A new world has taken shape: %s. /game %s goes there." % (title, ident), "world")
        save_state(state)
    except Refused:
        pass
    print("INSTALLED: %s (%s). Tell the player in one line, in the story, that somewhere a new world has taken shape: "
          "%s, and that /game %s goes there." % (title, ident, title, ident))


COMMANDS = {
    "newgame": (cmd_newgame, 0, "newgame [seed|daily]   start the active game afresh (rolls stats, variants and the clock from the seed)"),
    "look": (cmd_look, 0, "show state + current room (exits/items/characters filtered by flags)"),
    "move": (cmd_move, 1, "move <direction|room_id>   (also runs the clock and any encounter)"),
    "take": (cmd_take, 1, "take <item>   pick up from the current room"),
    "drop": (cmd_drop, 1, "drop <item>   leave in the current room"),
    "gain": (cmd_gain, 1, "gain <item>   receive from a character (trade/gift)"),
    "lose": (cmd_lose, 1, "lose <item>   give away or spend in the story"),
    "equip": (cmd_equip, 1, "equip <item>  wield a weapon"),
    "use": (cmd_use, 1, "use <item>    consume an item with a heal value"),
    "roll": (cmd_roll, 1, "roll <dice>   e.g. 2d6+1"),
    "check": (cmd_check, 2, "check <might|agility|wits> <dc|easy|normal|hard>"),
    "attack": (cmd_attack, 1, "attack <character>   one exchange of blows"),
    "hurt": (cmd_hurt, 1, "hurt <dice>   damage the player"),
    "heal": (cmd_heal, 1, "heal <dice>   heal the player"),
    "coins": (cmd_coins, 2, "coins <+n|-n> <%s>" % "|".join(COIN_REASONS)),
    "flag": (cmd_flag, 2, "flag set|unset <name>"),
    "npc-brief": (cmd_npc_brief, 1, "npc-brief <character>   what an NPC agent may know (prompt for its subagent)"),
    "remember": (cmd_remember, 2, "remember <character> <text>   add a line to that NPC's memory of the player"),
    "show": (cmd_show, 1, "show <rooms|characters|items|quests|tables> <id> [--all] | show world   content as it reads now"),
    "world-brief": (cmd_world_brief, 1, "world-brief <extra|room|item|character|quest|turn> | craft <maker> | build <builder>   prompt for the world agent"),
    "generate": (cmd_generate, 2, "generate <extra|room|item|character|quest|craft|build> <file>   add a world-agent proposal (a JSON file)"),
    "pay": (cmd_pay, 1, "pay <order> [material]   the player pays a maker or builder for an order"),
    "work": (cmd_work, 0, "work   the player works here for pay, once per visit (a check first)"),
    "buy": (cmd_buy, 1, "buy <item> [<seller>]   buy from a seller here, at their price"),
    "rent": (cmd_rent, 1, "rent <room>   take a place to let from its landlord, who is here"),
    "project": (cmd_project, 1, "project <id>   how a shared work stands: what's done, its stages, each person's turns of it"),
    "eat": (cmd_eat, 1, "eat <item>   eat something they carry that's food (a world with needs)"),
    "sleep": (cmd_sleep, 0, "sleep   sleep here, at the world's time for sleep, in a bed or rough (a world with needs)"),
    "meet": (cmd_meet, 1, "meet food | meet sleep [bed|rough]   a need met as the content says"),
    "sell": (cmd_sell, 1, "sell <item> [buyer]   the player sells something with a tier to a buyer here"),
    "say": (cmd_say, 1, "say <file>   the player's words aloud: the other players here hear them on their next turn"),
    "trade": (cmd_trade, 1, "trade offer <file> | accept <offer> | decline <offer>   the terms of an offer to another player here (a JSON file); the one it's for takes it or turns it down"),
    "contest": (cmd_contest, 3, "contest <your stat> <their id> <their stat> --take <item>   grab at what another player here holds: both roll, the higher takes it, a tie stays with them"),
    "ending": (cmd_ending, 1, "ending <file>   what everyone else comes to hear of a quest's ending, once one is decided (for no one between rounds)"),
    "voiced": (cmd_voiced, 1, "voiced <file> [--spend <usd>]   log a call tools/voice.py made to the npc or world agent"),
    "witnessed": (cmd_witnessed, 1, "witnessed <file> [<flag> ...]   what the other players there saw and heard of this turn, for their next; the personal flags they learned by it"),
    "scene": (cmd_scene, 2, "scene start <id> | scene end <id> [reward]   play a side scene between two characters"),
    "forge": (cmd_forge, 1, "forge quote | start [sentence] | resume <draft> | status | install <draft> | discard <draft>   new worlds"),
    "world-turn": (cmd_world_turn, 1, "world-turn <file>   apply the world agent's off-screen turn (a JSON file)"),
    "talk": (cmd_talk, 1, "talk <generated person>   before voicing a generated person: counts conversations, may promote them"),
    "library": (cmd_library, 1, "library suggest <id> <why>   tell the owner a generated or player-made thing deserves keeping"),
    "note": (cmd_note, 1, "note <text>   keep a detail you established about this room"),
    "post": (cmd_post, 1, "post <file> | post take <n>   the person puts up a notice on the board here (their words, from a file), or takes down one of their own"),
    "quest": (cmd_quest, 2, "quest take|leave <quest>   the person takes a quest on (it shows in what they're working on), or sets it aside"),
    "outcome": (cmd_outcome, 1, "outcome <%s> [<what>]   what this turn came to, for the record only (never told)" % "|".join(OUTCOMES)),
    "chronicle": (cmd_chronicle, 1, "chronicle <text>   add a line to the story so far"),
    "round": (cmd_round, 1, "round start | round end   open the next round (draws its order) or close it (the world's clock moves)"),
    "run": (cmd_run, 1, "run status | pause | resume | end   the owner's say over a run: a pause or end waits for the round in progress"),
    "brief": (cmd_brief, 1, "brief <player> [--instructions <file>]   everything the player agent is handed on its turn (logged)"),
    "pane": (cmd_pane, 1, "pane <player>   the player's margin as plain text"),
    "reply": (cmd_reply, 2, "reply <player> <file> [--spend <usd>] [--instructions <file>] [--exact-model <id>]   the player's reply this turn (DO: and JOURNAL: lines), from a file in proposals/"),
    "narrate": (cmd_narrate, 2, "narrate <player> <file>   the story told to the player this turn, from a file; ends their turn"),
    "memory": (cmd_memory, 2, "memory condense <player> | memory store <player> <file> [--spend <usd>] [--instructions <file>] [--exact-model <id>]   fold older rounds into the player's own words"),
    "log": (cmd_log, 0, "log [n]   the run's last n log entries (default 10), one line each, for checking"),
    "validate": (cmd_validate, 0, "validate [--game <id> | --dir <folder>] [--kit-complete] [--sim-complete] [--sim-strict]   check games' content, soundness and settings"),
    "game": (cmd_game, 0, "game [list | show | switch <id>]   the installed games; switching keeps each one's save"),
    "meter": (cmd_meter, 0, "meter [refill]   the meter, or fill it (the SessionStart hook refills it)"),
    "settings": (cmd_settings, 0, "settings   the owner's switches and prices for this game (change: tools/settings.py)"),
    "curse-text": (cmd_curse_text, 0, "curse-text <words>   the player's words as any curse makes them come out (JSON, for the prompt hook)"),
}


WORLD_COMMANDS = ("game", "validate", "settings", "meter", "forge")  # about the installed games: --as is ignored, nothing logged


def take_actor(argv):
    """Take `--as <id>` out of the arguments, wherever it is, and remember who acts."""
    global ACTOR
    if "--as" not in argv:
        return argv
    i = argv.index("--as")
    if i + 1 >= len(argv):
        raise Refused("--as needs a player id")
    ACTOR = argv[i + 1]
    return argv[:i] + argv[i + 2:]


def main(argv):
    try:
        argv = take_actor(list(argv))
    except Refused as e:
        print("REFUSED: %s" % e)
        return 1
    if not argv or argv[0] not in COMMANDS:
        print("commands:")
        for name, (_, _, help_text) in COMMANDS.items():
            print("  %-11s %s" % (name, help_text))
        return 2
    if argv[0] in WORLD_COMMANDS + RECORD_COMMANDS:
        global ACTOR
        ACTOR = None  # about the installed games, or the referee's own record: not anyone in them
    global COMMAND
    COMMAND = argv[0]
    fn, nargs, help_text = COMMANDS[argv[0]]
    if len(argv) - 1 < nargs:
        print("usage: %s" % help_text)
        return 2
    out, code = io.StringIO(), 0
    with contextlib.redirect_stdout(out):
        try:
            choose_game(active_game())
            fn(argv[1:])
        except (Refused, ValueError) as e:
            print("REFUSED: %s" % e)
            code = 1
            del _PENDING[:]  # it didn't happen
        except SystemExit as e:  # a command that sets its own exit status (validate)
            code = e.code if isinstance(e.code, int) else 1
    sys.stdout.write(out.getvalue())
    if argv[0] not in WORLD_COMMANDS + ("log",):
        log_command(argv, out.getvalue(), code)
    return code


def log_command(argv, output, code):
    """Every rules command run in a game, with what it printed, goes in that run's log."""
    state = read_json(SAVE)
    if not isinstance(state, dict) or state.get("version") != STATE_VERSION:
        return
    log(state, "command", command=argv[0], args=argv[1:], output=output.rstrip("\n"), refused=code != 0)
    flush_log()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
