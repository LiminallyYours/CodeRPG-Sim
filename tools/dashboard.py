#!/usr/bin/env python3
"""The owner's dashboard: a live view of the run, served on this machine only.

    python3 tools/dashboard.py [--port N]     then open http://127.0.0.1:<port>/ (the port is dashboard.port)
    python3 tools/dashboard.py --csv [run]    the run's log as CSV on stdout (the current run if none is named)

It reads the save and the run's log when the owner asks, never by itself: the page checks a small stamp every few
seconds (`/api/stamp`: turns told, rounds closed, the run paused or ended) and lights a signal when there's more,
with "Go to most recent" beside it; nothing on the page moves until a button is pressed. It shows one round at a
time (First, Prior, Next, Current) in three views. Narrative: each turn in the order played, in three lines (who,
where, what they were told, the options they weighed and chose, their reasoning and what they did; what came back:
who was there, the words heard, the story they were told, what onlookers saw; and, smaller, what it came to:
outcome, coins, trades, what changed), then what came between rounds (the world's turn, endings, memories
condensed). World: the six now (place, health, money, belongings, journal), the mechanics used (the audit's count
of each), and the town now (places, people, shared work, offers and lets, talk, orders, and the hooks: quests, timed
events, scarce prizes, a timeline); the state as last loaded, whatever round is shown. Engine: what's running now,
what the run has spent and each round's time, cost, context and refusals, and the round's backstage (each turn's
time, cost and model, the referee's commands with all each printed, the world agent's replies).
The town is worked out by the engine's own read functions, never a command (every command is logged).
Its two buttons ask `rpg.py run pause` and `run end`; the dashboard never writes a game file itself.
The log is also served as CSV, one row per entry, for analysis elsewhere (`/export.csv`, or `--csv`).
Python's standard library only.
"""
import csv
import datetime
import io
import json
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "rules"))
sys.path.insert(0, str(ROOT / "tools"))
import audit  # noqa: E402  the coverage count, shared with the run's audit
import rpg  # noqa: E402

LOCK = threading.Lock()  # the engine's read functions keep the acting person and the run in globals: one reader at a time



def read_save():
    """The save as it stands, or None (no game yet). rpg.py writes it atomically, so it's never half written."""
    try:
        return json.loads(rpg.SAVE.read_text())
    except (OSError, ValueError):
        return None


def log_entries(run_id):
    """The run's log; a line still being written is skipped until the next read."""
    path = rpg.LOG / ("%s.jsonl" % run_id)
    out = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


FIRST_COLUMNS = ("kind", "t", "round", "order_position", "player", "move")  # every entry has these (rpg.log)


def needs_of(pl):
    """Where a person's needs stand, in a world with them ("food hungry, sleep tired"), or ""."""
    needs = rpg.world_needs()
    parts = (["food " + rpg.food_state(pl)] if "food" in needs else []) + (
        ["sleep " + rpg.needs_of(pl)["sleep"]] if "sleep" in needs else [])
    return ", ".join(parts)


def csv_of(entries):
    """The log as CSV, one row per entry: the fields every entry has, then every other field any entry has, in
    name order. Lists and objects are written as JSON; a missing field is empty."""
    others = sorted({k for e in entries for k in e} - set(FIRST_COLUMNS))
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(FIRST_COLUMNS + tuple(others))
    for e in entries:
        writer.writerow(["" if e.get(k) is None else json.dumps(e[k], ensure_ascii=False)
                         if isinstance(e[k], (list, dict)) else e[k] for k in FIRST_COLUMNS + tuple(others)])
    return out.getvalue()


LAPSED = {"parted": "they went separate ways", "time": "no answer in time", "replaced": "a new offer replaced it"}


def trade_text(e, names, item_name, currency):
    """One step of a trade, as the owner reads it in the feed."""
    def things(side):
        parts = [item_name(i) for i in side["items"]] + (["%d %s" % (side["coins"], currency)] if side["coins"] else [])
        return ", ".join(parts) or "nothing"
    by, to = names.get(e["offered_by"], e["offered_by"]), names.get(e["to"], e["to"])
    give, want = e["give"], e["want"]
    if e["step"] == "offered":
        if not (want["items"] or want["coins"]):
            return "Offered %s %s, asking nothing back." % (to, things(give))
        if not (give["items"] or give["coins"]):
            return "Asked %s for %s, offering nothing back." % (to, things(want))
        return "Offered %s %s for %s." % (to, things(give), things(want))
    if e["step"] == "accepted":
        after = "; ".join("%s now has %d %s and %s" % (names.get(p, p), h["coins"], currency, ", ".join(map(item_name, h["items"])) or "nothing else")
                          for p, h in (e.get("after") or {}).items())
        tail = " " + after + "." if after else ""
        if not (give["items"] or give["coins"]):
            return "Gave %s what they asked for: %s.%s" % (by, things(want), tail)
        if not (want["items"] or want["coins"]):
            return "Took %s's gift: %s.%s" % (by, things(give), tail)
        return "Took %s's offer: %s gave %s, %s gave %s.%s" % (by, by, things(give), to, things(want), tail)
    if e["step"] == "declined":
        return "Turned down %s's offer." % by
    return "%s's offer to %s lapsed: %s." % (by, to, LAPSED.get(e.get("why"), e.get("why") or "it lapsed"))


def contest_text(e, names, item_name):
    """A grab at what another person held, as the owner reads it in the feed (the owner may see the numbers)."""
    me, them = e["rolls"][e["player"]], e["rolls"][e["against"]]
    who = names.get(e["against"], e["against"])
    end = "took it" if e["winner"] == e["player"] else "%s kept hold of it%s" % (who, " (a tie)" if me["total"] == them["total"] else "")
    return "Grabbed at %s's %s: %s %d against %s %d; %s." % (who, item_name(e["item"]), me["stat"], me["total"], them["stat"], them["total"], end)


QUIET = ("run", "show", "log")  # the referee's own lookups, left out of what it's seen doing
STILL = 300  # seconds with nothing logged, in a run that's going, before the page says so
SPEND_PARTS = {"referee": "referee", "action": "people", "voice": "voices", "memory": "memory"}  # who each kind's spend is for


def clip(text, n=160):
    """The first line of a command's words or output, cut to n characters."""
    line = (text or "").strip().split("\n", 1)[0]
    return line if len(line) <= n else line[:n - 1] + "…"


def said_of(reply):
    """A townsperson's words, from their agent's SAY: line (the whole reply if it has none)."""
    return next((line[4:].strip() for line in reply.splitlines() if line.startswith("SAY:")), reply.strip())


def when(e):
    try:
        return datetime.datetime.fromisoformat(e["t"])
    except (KeyError, TypeError, ValueError):
        return None


def seconds_between(a, b):
    ta, tb = when(a), when(b)
    return int((tb - ta).total_seconds()) if ta and tb else None


def order_text(e, name, currency):
    """One step of an order, as the owner reads it in the feed."""
    o, step = "Order %s: " % e.get("order"), e.get("step")
    if step == "asked":
        return o + "asked %s to %s." % (name(e.get("maker")), "build" if e.get("what") == "build" else "make something")
    if step == "shaped":
        return o + "%s will %s %s." % (name(e.get("maker")), "build" if e.get("use") == "stash" else "make", e.get("name") or e.get("id"))
    if step in ("priced", "paid"):
        return o + "%s %s %s." % (step, e.get("price"), currency)
    if step == "declined":
        return o + "declined (%s)." % e.get("reason", "")
    if step == "used":
        return o + "%s used (%s)." % (name(e.get("id")), e.get("how", ""))
    return o + "%s." % step


_ARRIVED = re.compile(r"^  arrived: (.+?) \(([a-z0-9_]+)\), (.+), at ([a-z0-9_]+)\. ")


def world_lines(output, name):
    """What a world turn changed, from `world-turn`'s output: a notice put up, someone arriving, its rumors and who
    moved where."""
    out = []
    for line in output.splitlines():
        arrived = _ARRIVED.match(line)
        if line.startswith("  notice put up at ") and ": " in line:
            room, text = line[len("  notice put up at "):].split(": ", 1)
            out.append("A notice put up at %s: %s" % (name(room), text))
        elif arrived:
            out.append("Arrived: %s, %s, at %s." % (arrived.group(1), arrived.group(3)[0].lower() + arrived.group(3)[1:], name(arrived.group(4))))
        elif line.startswith("  rumor: "):
            out.append("Rumor: " + line[9:])
        elif line.startswith("  ") and " is now at " in line:
            who, room = line.strip().split(" is now at ", 1)
            out.append("%s is now at %s." % (name(who), name(room)))
    return out


WORLD_CHANGING = ("flag", "quest", "work", "buy", "rent", "sleep", "eat", "meet", "pay", "trade", "contest", "generate", "take",
                  "drop", "gain", "lose", "coins", "sell", "ending")  # the commands that change the world, not only read it
_TAGGED = re.compile(r"^(?:[A-Z][A-Z ]+:|FLAG (?:set|unset)|EFFORT on|ENDING:)")


def changes_in(e):
    """What a state-changing command did, from the lines it printed that say so (PAID:, BOUGHT:, FLAG set, STAGE:...)."""
    lines = [clip(line, 200) for line in (e.get("output") or "").splitlines() if _TAGGED.match(line.strip())]
    return lines or [clip(" ".join([e.get("command", "")] + [str(a) for a in e.get("args", [])]), 120)]


def where_of(brief, places=()):
    """The brief's Where you are: the place, the time and the weather on one line ("where"), and the same as its parts
    ("place", "time", "weather"), the place known by its name (a name may hold a comma: "Fenn's, the Draper"), the time
    of day up to the next comma; who was with them on another line."""
    head, with_you = rpg.phrase("where_you_are"), rpg.phrase("with_you", people="\0").split("\0")[0]
    lines = brief.split(head + "\n", 1)[1].splitlines() if head + "\n" in brief else []
    with_line = next((line for line in lines[:6] if line.startswith(with_you)), None)
    where = lines[0].rstrip(".") if lines else None
    place = next((p for p in sorted(places, key=len, reverse=True) if where and (where == p or where.startswith(p + ", "))), None)
    rest = where[len(place) + 2:] if place and where != place else ""
    time, _, weather = rest.partition(", ")
    return {"where": where, "place": place or where, "time": time or None, "weather": weather or None,
            "with": with_line[len(with_you):].rstrip(".") if with_line else None}


def add(item, key, value):
    item.setdefault(key, []).append(value)


def build_feed(entries, names, name, currency="coins", places=()):
    """What happened, oldest first: each turn (from their brief: what they did, why, the story they were told, the
    words others heard, what the townspeople said, the onlookers' notes, trades, grabs, coins and orders, what was
    made, the chronicle, and the referee's commands), the round markers, with what came between rounds (world
    turns, memories condensed, the referee's session), and endings. A turn takes the entries of its round that are
    its person's or no one's, from its brief until the next turn or the round's end; anything else goes to the
    latest round marker. `places` are the place names a brief's Where you are may begin with."""
    items, turn, bucket = [], None, None

    def new_turn(e, i):
        pid = e.get("player")
        t = {"kind": "turn", "key": "%s:%s" % (e.get("round"), pid), "round": e.get("round"), "player": pid,
             "name": names.get(pid, pid), "model": None, "exact_model": None, "do": "", "journal": "", "options": None,
             "story": None, "brief_at": None, "brief_chars": None, "heard_by": [], "trades": [], "spend": 0.0,
             "seconds": None, "t": e.get("t"), "position": e.get("order_position"), "where": None, "place": None, "time": None,
             "weather": None, "with": None,
             "first": i, "last": i, "changed": None, "outcome": None, "world_changes": []}
        items.append(t)
        return t

    for i, e in enumerate(entries):
        kind = e["kind"]
        fresh = turn is not None and turn["player"] == e.get("player") and turn["round"] == e.get("round") and not turn["do"]
        if kind == "brief" and e.get("player"):
            turn = turn if fresh else new_turn(e, i)
            turn.update(brief_at=i, brief_chars=len(e.get("text", "")), **where_of(e.get("text", ""), places))
            continue
        if kind == "action":
            turn = turn if fresh else new_turn(e, i)
            turn["last"] = i
            turn.update(model=e.get("model"), exact_model=e.get("exact_model"), do=e.get("do", ""),
                        journal=e.get("journal", ""), options=e.get("options"), no_longer=e.get("no_longer"))
            turn["spend"] += e.get("spend") or 0
            continue
        if kind == "round" and e.get("phase") in ("start", "end"):
            turn = None
            bucket = ({"kind": "round", "key": "r%s" % e.get("round"), "round": e.get("round"),
                       "order": [names.get(p, p) for p in e.get("order", [])]} if e["phase"] == "start" else
                      {"kind": "round_end", "key": "e%s" % e.get("round"), "round": e.get("round"),
                       "world_turn": bool(e.get("world_turn_due"))})
            items.append(bucket)
            continue
        mine = turn is not None and e.get("round") == turn["round"] and e.get("player") in (None, turn["player"])
        theirs = mine and e.get("player") == turn["player"]  # a trade or grab is the person's own, never no one's
        here = turn if mine else bucket
        if mine:
            turn["last"] = i
        if kind == "narration" and mine:
            turn["story"] = e.get("text", "")
            turn["changed"] = e.get("changed")
            turn["seconds"] = seconds_between(turn, e)
        elif kind == "outcome" and mine:
            turn["outcome"] = {"result": e.get("result"), "what": e.get("what")}
        elif kind == "speech" and mine:
            turn["heard_by"] = [names.get(p, p) for p in e.get("heard_by", [])]
        elif kind == "trade":
            text = trade_text(e, names, name, currency)
            if theirs:
                turn["trades"].append(text)
            else:  # an offer lapsing when a round ends is no one's turn
                items.append({"kind": "trade", "key": "t%d" % len(items), "round": e.get("round"), "text": text})
        elif kind == "contest" and theirs:
            turn["trades"].append(contest_text(e, names, name))
        elif kind == "ending":
            items.append({"kind": "ending", "key": "end%d" % i, "round": e.get("round"), "by": names.get(e.get("player")),
                          "text": e.get("text", ""), "heard_by": [names.get(p, p) for p in e.get("heard_by", [])]})
        elif kind == "event" and here is not None:  # a timed event from world.md, as the clock reached it
            add(here, "world", "%s (%s): %s" % (e.get("id"), e.get("when"), "; ".join(x for x in (
                e.get("seen"), e.get("rumor") and "talk: " + e["rumor"], e.get("sets") and "now " + e["sets"]) if x)
                if e.get("happened") else "its time came, and it didn't happen"))
        elif kind == "asleep":  # gone to bed early: no turn this round
            items.append({"kind": "asleep", "key": "z%d" % i, "round": e.get("round"),
                          "text": "%s sleeps through round %s, not asked (to bed early)." % (names.get(e.get("player"), e.get("player")), e.get("round"))})
        elif kind == "run" and e.get("action") in ("pause", "resume", "end", "ended"):
            items.append({"kind": "run", "key": "run%d" % len(items), "action": e["action"], "round": e.get("round")})
        elif here is None:
            continue  # before the first round: the new game's own commands
        elif kind == "witnessed":
            add(here, "notes", {"text": e.get("text", ""), "seen_by": [names.get(p, p) for p in e.get("seen_by", [])]})
        elif kind == "voice":
            npc = e.get("agent") == "npc"
            about = name(e.get("about")) if npc else e.get("about")
            add(here, "voices", {"agent": e.get("agent"), "about": about, "said": said_of(e.get("reply", "")) if npc else None,
                                 "reply": e.get("reply", ""), "spend": e.get("spend")})
            add(here, "commands", {"text": "asked the %s agent, for %s" % (e.get("agent"), about), "said": "", "refused": False})
            if here is turn:
                turn["spend"] += e.get("spend") or 0
        elif kind == "coins":
            add(here, "money", "%+d %s (%s); now %s." % (e.get("delta", 0), currency, e.get("reason"), e.get("balance")))
        elif kind == "order":
            add(here, "money", order_text(e, name, currency))
        elif kind == "effort":
            add(here, "money", "Worked on %s (their %s; %s done in all)%s." % (e.get("project"), e.get("theirs"), e.get("total"),
                                                                          "" if e.get("moved") else ", to no avail this time"))
        elif kind == "project":
            add(here, "world", "%s reached %s." % (e.get("project"), e.get("stage")))
        elif kind == "purchase":
            add(here, "money", "Bought %s from %s for %s %s." % (e.get("item"), e.get("seller"), e.get("price"), currency))
        elif kind == "let":
            add(here, "money", "%s %s%s." % ({"taken": "Rented", "renewed": "Rented again", "ended": "No longer has"}.get(e.get("step"), e.get("step")),
                                            e.get("room"), ", to the end of day %s" % e["until"] if e.get("until") else ""))
        elif kind == "memory":
            rounds = e.get("rounds") or []
            add(here, "memories", {"who": names.get(e.get("player"), e.get("player")), "rounds": rounds,
                                   "text": e.get("text", ""), "replaced": e.get("replaced"), "spend": e.get("spend"),
                                   "learned": e.get("learned"), "learned_given": e.get("learned_given", True)})
        elif kind == "referee":
            here["referee"] = {"spend": e.get("spend"), "seconds": e.get("seconds"), "context": e.get("context")}
        elif kind == "command":
            if mine and not e.get("refused") and e.get("command") in WORLD_CHANGING:
                turn["world_changes"] += changes_in(e)
            if not e.get("refused"):
                if e.get("command") == "chronicle" and e.get("args"):
                    add(here, "chronicle", e["args"][0])
                elif e.get("command") == "world-turn":
                    for line in world_lines(e.get("output", ""), name):
                        add(here, "world", line)
                elif e.get("command") == "generate":
                    add(here, "made", clip(e.get("output", "")).replace("GENERATED: ", ""))
            if e.get("command") not in QUIET:
                add(here, "commands", {"text": clip(" ".join([e.get("command", "")] + [str(a) for a in e.get("args", [])]), 100),
                                       "said": clip(e.get("output"), 160), "refused": bool(e.get("refused"))})
    return items


def meter_of(entries, current):
    """What the run has spent, by whom it was for, and each round's cost, time, the referee's context and refusals.
    A round's time is its referee session's when one is logged (tools/rounds.py), or from its start to its end."""
    spend = dict.fromkeys(("referee", "people", "voices", "memory"), 0.0)
    rounds = {}
    for e in entries:
        r = e.get("round")
        if r is None:
            continue
        row = rounds.setdefault(r, {"round": r, "spend": 0.0, "seconds": None, "context": None, "refused": 0, "start": None, "end": None})
        part = SPEND_PARTS.get(e["kind"])
        if part and e.get("spend"):
            spend[part] += e["spend"]
            row["spend"] += e["spend"]
        if e["kind"] == "round" and e.get("phase") in ("start", "end"):
            row[e["phase"]] = e
        elif e["kind"] == "referee":
            row["seconds"], row["context"] = e.get("seconds"), e.get("context")
        elif e["kind"] == "command" and e.get("refused"):
            row["refused"] += 1
    rows = []
    for r in sorted(rounds, reverse=True):
        row = rounds.pop(r)
        if not row["start"]:
            continue
        start, end = row.pop("start"), row.pop("end")
        row["open"] = end is None
        if row["seconds"] is None:
            row["seconds"] = seconds_between(start, end) if end else seconds_between(start, {"t": now_text()})
        rows.append(row)
    last = when(entries[-1]) if entries else None
    return {"spend": dict(spend, total=sum(spend.values())), "rounds": rows,
            "quiet": int((datetime.datetime.now() - last).total_seconds()) if last else None, "still": STILL,
            "this_round": next((row for row in rows if row["round"] == current), None)}


def now_text():
    return datetime.datetime.now().isoformat(timespec="seconds")


def happening(items, run, next_name):
    """What's going on right now, from the feed's last turn or marker: who is deciding or being played, for how long,
    and the referee's latest commands; or the round closing; or the run paused or ended."""
    if run.get("ended"):
        return {"stage": "ended", "text": "The run has ended."}
    last = next((x for x in reversed(items) if x["kind"] in ("turn", "round", "round_end")), None)
    if last is None:
        return {"stage": "waiting", "text": "Nothing has happened yet."}
    since = lambda t: seconds_between({"t": t}, {"t": now_text()})
    steps = (last.get("commands") or [])[-5:]
    if last["kind"] == "turn" and last["story"] is None:
        if not last["do"]:
            return {"stage": "deciding", "who": last["name"], "since": since(last["t"]), "told": last["brief_chars"], "steps": []}
        return {"stage": "playing", "who": last["name"], "since": since(last["t"]), "steps": steps}
    if last["kind"] == "round_end":
        stage = "paused" if run.get("stop") == "pause" else "closing"
        return {"stage": stage, "round": last["round"], "steps": steps}
    return {"stage": "between", "next": next_name, "round": last["round"], "steps": steps}


_DONE = re.compile(r"^(.*?)\s*\(done when\s+(.+)\)\s*$")


def world_view(save, entries, names, name):
    """The town now, from the save and the world's content, worked out by the engine's own read-only functions
    (never a command: every command is logged): the clock, each place, each person, shared work, offers, lets and
    beds paid ahead, rumors and who has heard them, orders, and the hooks: quests, timed events, scarce prizes and
    a timeline. Called under LOCK, with rpg's run set to this save's."""
    run, view, players = save["run"], save.get("view", {}), save["players"]
    shared = list(save["flags"]) + rpg.shared_conditions(save)  # the shared flags, the clock and the lets: what decides where things are
    places = []
    for r in list(rpg.content.ids("rooms")) + [r for r in run.get("rooms", {}) if not rpg.content.exists("rooms", r)]:
        room = rpg.ent("rooms", r)
        here = [c for c in rpg.content.visible(room.get("characters"), shared) if rpg.ent_exists("characters", c)]
        places.append({"name": room.get("name", r),
                       "cast": [names[pid] for pid, pl in players.items() if pl["location"] == r and pl["status"] == "playing"],
                       "people": [name(c) for c in here], "lying": [name(i) for i in save.get("room_items", {}).get(r, [])],
                       "building": [rpg.order_name(i, c) for i, c in run.get("commissions", {}).items()
                                    if c.get("status") == "building" and c.get("room") == r]})
    lets = run.get("lets", {})
    people = []
    for pid, pl in players.items():
        own = [rpg.ent("rooms", r).get("name", r) for r, rec in run.get("rooms", {}).items() if rec.get("meta", {}).get("owner") == pid]
        own += ["%s (to the end of day %s)" % (rpg.ent("rooms", r).get("name", r), let["until"]) for r, let in lets.items() if let["tenant"] == pid]
        people.append({"name": pl["name"], "coins": pl["stats"]["coins"], "hp": pl["stats"]["hp"], "max_hp": pl["stats"]["max_hp"],
                       "needs": rpg.needs_words(save, pid) if rpg.world_needs() else [],
                       "carrying": [name(i) for i in pl.get("inventory", [])], "own": own,
                       "taken_on": [rpg.ent("quests", q).get("name", q) for q in pl.get("taken_on", []) if rpg.ent_exists("quests", q)],
                       "beds": ["%s, %d night%s" % (name(r), n, "" if n == 1 else "s") for r, n in (pl.get("paid_beds") or {}).items() if n]})
    paid = {}
    for e in entries:
        if e["kind"] == "coins" and e.get("reason") == "work":
            paid[(e.get("note"), e.get("player"))] = paid.get((e.get("note"), e.get("player")), 0) + 1
    projects = []
    for ident, r in rpg.project_rooms().items():
        spec, rec = rpg.project_of(rpg.ent("rooms", r)), run.get("projects", {}).get(ident, {"total": 0, "by": {}, "stages": []})
        top = max(rec["by"].values() or [0])
        projects.append({"name": spec["name"], "place": name(r), "total": rec["total"],
                         "stages": [{"at": a, "flag": f, "reached": f in rec["stages"]} for a, f in spec["stages"]],
                         "by": [{"name": names.get(p, p), "turns": n, "paid": paid.get((r, p), 0), "most": n == top}
                                for p, n in sorted(rec["by"].items(), key=lambda kv: -kv[1])],
                         "until": spec["until"], "open": rpg.content.condition_holds(spec["until"], shared) if spec["until"] else True})
    offers = ["%s offers %s %s for %s" % (names.get(x["from"]), names.get(x["to"]), side_text(x["give"], name), side_text(x["want"], name))
              for x in rpg.open_trades(save)]
    rumors = [{"text": r, "heard_by": [pl["name"] for pl in players.values() if r in (pl.get("heard") or [])]} for r in run.get("rumors", [])]
    orders = [{"name": rpg.order_name(i, c) if "record" in c or c["kind"] == "item" else name(i), "kind": "place" if c["kind"] == "room" else "thing",
               "maker": name(c.get("maker")), "for": names.get(c.get("by") or c.get("ordered_by")), "status": c.get("status"),
               "price": c.get("price")} for i, c in run.get("commissions", {}).items()]
    return {"clock": ", ".join(x for x in ("%s on day %d" % (view["time"], view["day"]) if view.get("time") and view.get("day") else view.get("time"),
                                          view.get("weather")) if x),
            "places": places, "people": people, "projects": projects, "offers": offers,
            "lets": ["%s: %s's to the end of day %s" % (name(r), names.get(x["tenant"]), x["until"]) for r, x in lets.items()],
            "rumors": rumors, "orders": orders, "hooks": hooks(save, entries, names, name, shared, projects)}


def side_text(side, name):
    return ", ".join([name(i) for i in side.get("items", [])] + (["%d coins" % side["coins"]] if side.get("coins") else [])) or "nothing"


def hooks(save, entries, names, name, shared, projects):
    """Each quest (its objectives done for whom and what each waits on, how it stands, who took it on and when, how
    it ended and whose doing it was), each timed event, the scarce prizes, and a timeline of them in log order."""
    run, players = save["run"], save["players"]
    flags_of = {}
    for pid in players:
        with rpg.acting(pid):
            flags_of[pid] = rpg.condition_flags(save)
    ended, taken, timeline = {}, {}, []
    quest_names = {q: rpg.ent("quests", q).get("name", q) for q in rpg.ent_ids("quests")}
    decided_by = {}  # quest: whose command first printed its ENDING (an ending may be told for no one, after)
    for e in entries:
        if e["kind"] == "command" and not e.get("refused") and e.get("player") and e.get("command") != "ending":
            for q, qname in quest_names.items():
                if "ENDING: %s" % qname in (e.get("output") or ""):
                    decided_by.setdefault(q, names.get(e["player"]))
    for e in entries:
        who = names.get(e.get("player")) or "no one"
        if e["kind"] == "command" and not e.get("refused") and e.get("command") == "quest" and len(e.get("args", [])) > 1:
            q = e["args"][1]
            taken.setdefault(q, []).append("%s (round %s%s)" % (who, e.get("round"), "" if e["args"][0] == "take" else ", set aside"))
            timeline.append("r%s %s %s %s" % (e.get("round"), who, "took on" if e["args"][0] == "take" else "set aside", quest_names.get(q, q)))
        if e["kind"] == "ending":  # told once a quest is decided: by the turn's person, or for no one after a world turn or event
            for q, how in (e.get("quests") or {}).items():
                ended.setdefault(q, {"round": e.get("round"), "how": how, "by": names.get(e.get("player")) or decided_by.get(q)
                                     or "the world (a turn or a timed event)"})
                timeline.append("r%s %s %s (%s)" % (e.get("round"), quest_names.get(q, q), how, ended[q]["by"]))
        if e["kind"] == "project":
            timeline.append("r%s %s reached %s" % (e.get("round"), e.get("project"), e.get("stage")))
        elif e["kind"] == "event" and e.get("happened"):
            timeline.append("r%s timed event %s (%s)" % (e.get("round"), e.get("id"), e.get("when")))
        elif e["kind"] == "command" and not e.get("refused") and e.get("command") == "flag" and e.get("args", [None])[0] == "set":
            timeline.append("r%s %s: flag %s" % (e.get("round"), who, e["args"][1] if len(e["args"]) > 1 else "?"))
    quests = []
    for q, qname in quest_names.items():
        meta = rpg.ent("quests", q)
        objectives = []
        for line in meta.get("objectives") or []:
            m = _DONE.match(str(line))
            text, cond = (m.group(1), m.group(2)) if m else (str(line), None)
            objectives.append({"text": text, "waits_on": cond, "done_for": [players[pid]["name"] for pid in players
                                                                             if cond and rpg.content.condition_holds(cond, flags_of[pid])]})
        complete = bool(meta.get("completed_by")) and rpg.content.condition_holds(meta["completed_by"], shared)
        failed = not complete and bool(meta.get("failed_by")) and rpg.content.condition_holds(meta["failed_by"], shared)
        quests.append({"name": qname, "side": rpg.is_generated("quests", q), "giver": name(meta.get("giver")),
                       "state": "complete" if complete else "failed" if failed else "open", "ended": ended.get(q),
                       "completed_by": meta.get("completed_by"), "failed_by": meta.get("failed_by"),
                       "taken_on": taken.get(q, []), "objectives": objectives})
    happened = {e.get("id"): e.get("happened") for e in entries if e["kind"] == "event"}
    events = [{"id": ev["id"], "when": ev.get("when"), "if": ev.get("if"),
               "state": ("happened" if happened.get(ev["id"]) else "its time came; its condition didn't hold") if ev["id"] in run.get("fired", [])
               else "waiting"} for ev in (rpg.content.timed(rpg.world()["body"]) if rpg.has_days() else [])]
    prizes = ["%s: to let, %s" % (rpg.ent("rooms", r).get("name", r), "%s's to the end of day %s" % (names.get(run.get("lets", {})[r]["tenant"]),
              run["lets"][r]["until"]) if r in run.get("lets", {}) else "free") for r in rpg.content.ids("rooms") if rpg.rent_of(rpg.ent("rooms", r))]
    prizes += ["most help on %s: %s" % (p["name"], ", ".join(b["name"] for b in p["by"] if b["most"]) or "no one yet") for p in projects]
    return {"quests": quests, "events": events, "prizes": prizes, "timeline": timeline}


def live():
    """Everything the page shows, as JSON-ready data."""
    with LOCK:
        return live_now()


def live_now():
    save = read_save()
    if not save or "players" not in save:
        return {"game": None}
    rpg.choose_game(save["game"])
    rpg._RUN = save["run"]  # what this run generated, so its names resolve (as load_state does)
    run, view = save["run"], save.get("view", {})
    look = view.get("look", {})
    rs = run.get("round_state")
    players = save["players"]
    names = {pid: pl["name"] for pid, pl in players.items()}

    def name(ident):
        """Any id the log names, as the owner reads it: a person, a character, an item or a place."""
        if ident in names:
            return names[ident]
        for kind in ("characters", "items", "rooms"):
            if ident and rpg.ent_exists(kind, ident):
                return rpg.ent(kind, ident).get("name", ident)
        return ident

    nxt = next((p for p in rs["order"] if p not in rs.get("done", []) and players[p]["status"] == "playing"), None) if rs else None
    entries = log_entries(run["id"])
    briefs, spent, exact, asked_on = {}, {}, {}, {}
    for e in entries:
        pid = e.get("player")
        if e["kind"] == "brief" and pid:
            briefs.setdefault(pid, []).append(len(e.get("text", "")))
        if e["kind"] == "action" and pid and e.get("model"):
            asked_on[pid] = e["model"]
        if e["kind"] in ("action", "memory") and pid:
            spent[pid] = spent.get(pid, 0.0) + (e.get("spend") or 0)
            if e.get("exact_model") and e["exact_model"] not in exact.setdefault(pid, []):
                exact[pid].append(e["exact_model"])
    people = []
    for pid, pl in players.items():
        v = view.get("players", {}).get(pid, {})
        turn = pl.get("turn") or {}
        people.append({
            "id": pid, "name": pl["name"], "model": asked_on.get(pid) or rpg.model_for(save, pid), "status": pl["status"],
            "exact_models": exact.get(pid, []), "spend": spent.get(pid, 0.0),
            "told": (briefs.get(pid) or [None])[-1], "first_told": (briefs.get(pid) or [None])[0],
            "place": v.get("location_name", pl["location"]),
            "hp": pl["stats"]["hp"], "max_hp": pl["stats"]["max_hp"], "coins": pl["stats"]["coins"],
            "carrying": [i["name"] + (" (in hand)" if i.get("equipped") else "") for i in v.get("items", [])],
            "journal": turn.get("journal", ""), "journal_round": turn.get("round"),
            "needs": needs_of(pl),
            "now": pid == nxt, "replied": pid == nxt and turn.get("round") == run.get("round"),
        })
    cap = int(rpg.SETTINGS["rounds"]["max_per_run"])
    currency = look.get("currency", "coins")
    items = build_feed(entries, names, name, currency, [name(r) for r in rpg.ent_ids("rooms")])
    return {
        "game": {"id": save["game"], "title": save.get("adventure", save["game"])},
        "seed": run.get("seed"), "currency": currency,
        "time": ", ".join(x for x in ("%s on day %d" % (view["time"], view["day"]) if view.get("time") and view.get("day") else view.get("time"),
                                      view.get("weather")) if x),
        "run": {"round": run.get("round", 0), "open": bool(rs), "played": run.get("round", 0) - (1 if rs else 0),
                "cap": cap, "stop": run.get("stop"), "ended": bool(run.get("ended")),
                "order": [names.get(p, p) for p in rs["order"]] if rs else [],
                "done": [names.get(p, p) for p in rs.get("done", [])] if rs else []},
        "people": people,
        "meter": meter_of(entries, run.get("round")),
        "happening": happening(items, run, names.get(nxt)),
        "feed": items[::-1],  # all of it: the page pages through every round
        "stamp": stamp_of(save, entries),
        "coverage": audit.coverage(entries),
        "world": world_view(save, entries, names, name),
    }


def stamp_of(save, entries):
    """How far the run has got, for the page's update signal: the stories told (one a turn), the rounds closed, and
    whether a pause or end is asked or the run is over."""
    run = save["run"]
    closed = [e.get("round") for e in entries if e["kind"] == "round" and e.get("phase") == "end"]
    return {"run": run["id"], "turns": sum(1 for e in entries if e["kind"] == "narration"), "rounds_closed": len(closed),
            "last_closed": closed[-1] if closed else None, "stop": run.get("stop"), "ended": bool(run.get("ended"))}


def stamp():
    """The stamp as the run stands now (asked every few seconds: the save and the log, no engine)."""
    save = read_save()
    if not save or "run" not in save:
        return {"run": None}
    return stamp_of(save, log_entries(save["run"]["id"]))


def brief_at(n):
    """The brief at line n of the current run's log, for the feed's "What they were told" (sent only when asked:
    a late brief runs to tens of thousands of characters)."""
    save = read_save()
    entries = log_entries(save["run"]["id"]) if save and "run" in save else []
    e = entries[n] if 0 <= n < len(entries) else None
    return {"text": e.get("text", "")} if e and e["kind"] == "brief" else None


def steps_of(first, last, pid):
    """A turn's commands in order with all each printed, from its log lines first to last (fetched when the card's
    What happened is opened: a look prints the whole room)."""
    save = read_save()
    entries = log_entries(save["run"]["id"]) if save and "run" in save else []
    return [{"text": " ".join([e.get("command", "")] + [str(a) for a in e.get("args", [])]), "said": e.get("output", ""),
             "refused": bool(e.get("refused"))} for e in entries[max(0, first):last + 1]
            if e["kind"] == "command" and e.get("player") in (None, pid) and e.get("command") not in QUIET]


def ask_run(what):
    """`rpg.py run pause|end`, as the owner would type it; its answer goes back to the page."""
    r = subprocess.run([sys.executable, str(ROOT / "rules" / "rpg.py"), "run", what], cwd=ROOT,
                       capture_output=True, text=True, timeout=30)
    return {"ok": r.returncode == 0, "said": r.stdout.strip()}


class Handler(BaseHTTPRequestHandler):
    def local(self):
        """Only this machine's own pages: the Host must be this machine (no DNS rebinding)."""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        return host in ("127.0.0.1", "localhost")

    def send(self, code, body, kind):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self.local():
            return self.send(403, "forbidden", "text/plain")
        if self.path.split("?", 1)[0] == "/":  # ?view=all opens the fuller view
            return self.send(200, PAGE, "text/html; charset=utf-8")
        if self.path == "/api/live":
            return self.send(200, json.dumps(live(), ensure_ascii=False), "application/json")
        if self.path == "/api/stamp":
            return self.send(200, json.dumps(stamp(), ensure_ascii=False), "application/json")
        if self.path.startswith("/api/brief/") and self.path[11:].isdigit():
            brief = brief_at(int(self.path[11:]))
            return self.send(200, json.dumps(brief, ensure_ascii=False), "application/json") if brief else \
                self.send(404, "no brief there", "text/plain")
        m = re.match(r"^/api/steps/(\d+)-(\d+)/([a-z0-9_]+)$", self.path)
        if m:
            return self.send(200, json.dumps(steps_of(int(m.group(1)), int(m.group(2)), m.group(3)), ensure_ascii=False), "application/json")
        if self.path == "/export.csv":
            save = read_save()
            if not save or "run" not in save:
                return self.send(404, "no run yet", "text/plain")
            data = csv_of(log_entries(save["run"]["id"])).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="%s-%s.csv"' % (save["game"], save["run"]["id"]))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return self.wfile.write(data)
        self.send(404, "not found", "text/plain")

    def do_POST(self):
        # a page elsewhere can't send this header without a preflight, which is never answered: no cross-site asks
        if not self.local() or self.headers.get("X-Dashboard") != "1":
            return self.send(403, "forbidden", "text/plain")
        what = {"/api/run/pause": "pause", "/api/run/end": "end"}.get(self.path)
        if not what:
            return self.send(404, "not found", "text/plain")
        self.send(200, json.dumps(ask_run(what), ensure_ascii=False), "application/json")

    def log_message(self, *args):
        pass  # quiet: the terminal stays the referee's


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Run dashboard</title>
<style>
:root {
  --paper: #E8EDF1; --sheet: #F4F7F9; --ink: #1C2A4A; --slate: #5B6B80; --rule: #C9D2DB;
  --brass: #8C6D1F; --brick: #A63D2B; --good: #2E6B3F; --part: #8A5300; --bad: #A63D2B;
  --gut: 7.5rem; --gap: 20px;
  --serif: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
  --sans: system-ui, -apple-system, "Segoe UI", sans-serif;
  --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root { --paper: #151C27; --sheet: #1C2532; --ink: #DCE3EA; --slate: #94A3B5; --rule: #2E3A4B;
          --brass: #D2AE52; --brick: #E07A66; --good: #7CC38C; --part: #E2A955; --bad: #E07A66; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink); font: 15px/1.5 var(--sans); }
main { max-width: 1180px; margin: 0 auto; padding: 24px 16px 64px; }
main { padding-top: 0; }
header.top { position: sticky; top: 0; z-index: 2; background: var(--paper); padding: 16px 0 0; }
.titles { display: flex; flex-wrap: wrap; gap: 2px 16px; align-items: baseline; }
h1 { font: 600 26px/1.15 var(--serif); margin: 0; letter-spacing: 0.005em; }
.daytime { font: italic 16px/1.4 var(--serif); margin: 0; }
/* the header's rows, and a turn's, carry their labels in a margin column */
.rows { margin: 10px 0 0; border-top: 1px solid var(--rule); }
.row { display: grid; grid-template-columns: var(--gut) minmax(0, 1fr) auto; gap: 6px var(--gap); align-items: center;
       padding: 6px 0; border-bottom: 1px solid var(--rule); }
.row.lit { background: color-mix(in srgb, var(--brass) 11%, transparent); }
.row > .k, .lg > .k, .head > .k { font: 700 11px/1.5 var(--sans); text-transform: uppercase; letter-spacing: 0.09em;
       color: var(--slate); text-align: right; }
.row > .v { font-size: 14px; min-width: 0; }
.state { font-weight: 600; }
.state.going { color: var(--good); }
.state.pausing { color: var(--part); }
.state.ended { color: var(--slate); }
.pager { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.pager button { padding: 6px 12px; }
.where { font: 600 20px/1 var(--serif); margin: 0 10px; white-space: nowrap; font-variant-numeric: tabular-nums; }
.signal { display: flex; gap: 10px; align-items: center; color: var(--slate); font-size: 14px; flex-wrap: wrap; }
.lamp { width: 12px; height: 12px; border-radius: 50%; background: var(--rule); flex: none; }
.signal.lit { color: var(--ink); font-weight: 600; }
.signal.lit .lamp { background: var(--brass); box-shadow: 0 0 0 4px color-mix(in srgb, var(--brass) 30%, transparent); }
.signal.lit button { border-color: var(--brass); background: var(--brass); color: var(--paper); }
.signal.down { color: var(--brick); }
.signal.down .lamp { background: var(--brick); }
button.small { font-size: 12.5px; padding: 4px 10px; }
.facts { color: var(--slate); margin: 0; }
.turnline { margin: 6px 0 0; }
.turnline b { color: var(--brass); font-weight: 600; }
.controls { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
button { font: 500 14px var(--sans); padding: 8px 14px; border-radius: 6px; cursor: pointer;
         border: 1px solid var(--ink); background: transparent; color: var(--ink); }
button.end { border-color: var(--brick); color: var(--brick); }
button:hover:not(:disabled) { background: var(--sheet); }
button:disabled { opacity: 0.45; cursor: default; }
button:focus-visible, summary:focus-visible, a:focus-visible, [tabindex]:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }
.said { color: var(--slate); font-size: 13px; text-align: right; margin: 4px 0 0; }
.said:empty { margin: 0; }
.people { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 0 28px; margin: 24px 0 8px; }
.person { border-top: 3px solid var(--who); padding: 12px 0 20px; }
.person.now { border-top-color: var(--brass); }
.person h2 { margin: 0; }
.person h2.name { font: 600 19px/1.2 var(--serif); color: var(--who); }
.meta b { color: var(--brass); font-weight: 600; }
.meta { color: var(--slate); font-size: 13px; margin: 2px 0 10px; }
.warn { color: var(--brick); }
.stat { margin: 2px 0; }
.bar { height: 4px; background: var(--rule); border-radius: 2px; margin: 4px 0 8px; max-width: 180px; }
.bar i { display: block; height: 100%; border-radius: 2px; background: var(--who); }
.carry, .told { color: var(--slate); font-size: 13.5px; margin: 6px 0 0; }
.journal { font: italic 17px/1.45 var(--serif); margin: 14px 0 0; }
.journal small { display: block; font: 13px var(--sans); font-style: normal; color: var(--slate); margin-top: 4px; }
.box { background: var(--sheet); border-radius: 6px; padding: 14px 16px; }
.box h3 { font: 600 13px var(--sans); text-transform: uppercase; letter-spacing: 0.06em; color: var(--slate); margin: 0 0 8px; }
.nowtext { font: 16px/1.45 var(--serif); margin: 0 0 6px; }
.nowtext b { color: var(--brass); font-weight: 600; }
.steps { list-style: none; margin: 8px 0 0; padding: 0; display: grid; gap: 6px; }
.steps li, .cmds li { font: 12.5px/1.4 var(--mono); overflow-wrap: anywhere; }
.steps li span, .cmds li span { display: block; color: var(--slate); }
.refused, .refused span { color: var(--brick) !important; }
.total { font: 600 26px/1.1 var(--serif); margin: 0 0 6px; font-variant-numeric: tabular-nums; }
.parts { font-size: 13.5px; color: var(--slate); margin: 0 0 10px; }
.parts b { color: var(--ink); font-weight: 600; font-variant-numeric: tabular-nums; }
table { border-collapse: collapse; width: 100%; font-size: 13px; font-variant-numeric: tabular-nums; }
th { text-align: right; font-weight: 500; color: var(--slate); padding: 2px 0 4px 8px; border-bottom: 1px solid var(--rule); }
td { text-align: right; padding: 3px 0 3px 8px; }
th:first-child, td:first-child { text-align: left; padding-left: 0; }
td.so-far { color: var(--slate); font-style: italic; }
.note { font-size: 12.5px; color: var(--slate); margin: 8px 0 0; }
.quiet { font-size: 13px; margin: 8px 0 0; color: var(--slate); }
.quiet.still { color: var(--brick); }
.filter { font-size: 13.5px; color: var(--slate); margin: 0 0 12px; }
.filter button { font-size: 13px; padding: 2px 10px; margin-left: 8px; }
.turn { padding: 14px 16px 16px; border-left: 3px solid var(--who); margin: 0 0 14px; background: var(--sheet); border-radius: 0 6px 6px 0; }
.turn .who { font: 600 14px var(--sans); color: var(--who); margin: 0 0 6px; }
.turn .who span { color: var(--slate); font-weight: 400; }
.do { font: 17px/1.5 var(--serif); margin: 0 0 8px; }
.why { font: italic 15.5px/1.5 var(--serif); color: var(--slate); margin: 0 0 8px; }
.waiting { font: italic 16px/1.5 var(--serif); color: var(--slate); margin: 0 0 8px; }
.options { margin: 0 0 10px; padding-left: 20px; font-size: 14px; color: var(--slate); }
.options li.chosen { color: var(--ink); }
.options span { color: var(--slate); }
.options b { color: var(--brass); font-weight: 600; font-size: 12.5px; }
.heard { font-size: 13px; color: var(--slate); margin: 0 0 6px; }
.voice { font: 15.5px/1.5 var(--serif); margin: 0 0 8px; padding-left: 10px; border-left: 2px solid var(--rule); }
.voice b { font: 600 13px var(--sans); color: var(--slate); display: block; }
.trade { font-size: 14px; margin: 0 0 6px; padding-left: 10px; border-left: 2px solid var(--brass); }
.chron { font-size: 13.5px; color: var(--slate); margin: 0 0 6px; }
.chron b { font-weight: 600; }
details { margin: 4px 0 0; }
details summary { cursor: pointer; color: var(--slate); font-size: 13.5px; }
details .story { font: 16px/1.6 var(--serif); margin-top: 8px; }
details .story p { margin: 0 0 10px; }
details pre { white-space: pre-wrap; overflow-wrap: anywhere; font: 12.5px/1.5 var(--mono); margin: 8px 0 0; max-height: 32em; overflow: auto; }
.cmds { list-style: none; margin: 10px 0 0; padding: 10px 0 0; border-top: 1px dashed var(--rule); display: grid; gap: 6px; }
.cost { font-size: 12.5px; color: var(--slate); margin: 8px 0 0; font-variant-numeric: tabular-nums; }
.marker { color: var(--slate); font-size: 13.5px; margin: 18px 0 14px; display: flex; gap: 10px; align-items: center; }
.marker::before, .marker::after { content: ""; flex: 1; height: 1px; background: var(--rule); }
.between { margin: -6px 0 18px; padding: 10px 16px; border-radius: 6px; background: var(--sheet); }
.between:empty { display: none; }
.ending { border: 1px solid var(--brass); border-radius: 6px; padding: 14px 16px; margin: 0 0 14px; }
.ending .who { font: 600 14px var(--sans); color: var(--brass); margin: 0 0 6px; }
.empty { font: 17px/1.5 var(--serif); color: var(--slate); margin: 40px 0; }
.stale { color: var(--brick); }
.tabs { display: flex; gap: 0; margin: 16px 0 0; border-bottom: 1px solid var(--rule); flex-wrap: wrap; }
.tabs button { border: 0; border-radius: 0; border-bottom: 3px solid transparent; padding: 8px 16px; color: var(--slate); }
.tabs button[aria-pressed="true"] { color: var(--ink); border-bottom-color: var(--ink); background: none; font-weight: 600; }
.coverage { margin: 12px 0 0; font-size: 13.5px; }
.coverage ul { columns: 2 280px; column-gap: 32px; list-style: none; padding: 0; margin: 8px 0 0; }
.coverage li { display: flex; justify-content: space-between; gap: 12px; padding: 1px 0; break-inside: avoid; }
.coverage li b { font-variant-numeric: tabular-nums; font-weight: 600; }
.coverage li.never { color: var(--slate); }
.coverage li.never b { font-weight: 400; }
.cards { margin-top: 20px; max-width: 80ch; }
.came { font-size: 13.5px; margin: 0 0 8px; }
.came b { color: var(--brass); font-weight: 600; }
.changed { font-size: 14px; margin: 8px 0 0; }
.changed b, .label { font: 600 12.5px var(--sans); color: var(--slate); text-transform: uppercase; letter-spacing: 0.05em; }
.changes { margin: 4px 0 0; padding-left: 20px; font-size: 13.5px; }
.world { display: grid; grid-template-columns: minmax(0, 1fr); gap: 18px; margin-top: 20px; }
.world .box { min-width: 0; }
.world .box p, .world .box li { overflow-wrap: anywhere; }
.world .scroll table { min-width: 620px; }  /* a wide table scrolls within its box on a phone, words whole */
.scroll { overflow-x: auto; }
.world table td, .world table th { text-align: left; vertical-align: top; padding: 4px 12px 4px 0; }
.world .box p, .world .box li { margin: 2px 0; font-size: 14px; }
.world .box ul { margin: 4px 0 0; padding-left: 20px; }
.quest { border-top: 1px solid var(--rule); padding: 10px 0 4px; }
.quest:first-of-type { border-top: 0; padding-top: 0; }
.quest h4 { font: 600 15px var(--serif); margin: 0 0 4px; }
.st-complete { color: var(--brass); } .st-failed { color: var(--brick); } .st-open { color: var(--slate); }
.cond { font: 12px var(--mono); color: var(--slate); }
.narrative { max-width: calc(80ch + var(--gut) + var(--gap)); margin-top: 20px; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 16px; }
.chips button { font-size: 13px; padding: 3px 10px 3px 8px; border-color: var(--rule); display: inline-flex; align-items: center; gap: 6px; }
.chips button i { width: 9px; height: 9px; border-radius: 50%; background: var(--who); flex: none; }
.chips button[aria-pressed="true"] { border-color: var(--ink); background: var(--sheet); }
.lg { display: grid; grid-template-columns: var(--gut) minmax(0, 1fr); gap: 12px var(--gap); }
.lg > .k { padding-top: 4px; }
.lg > .v { min-width: 0; overflow-wrap: break-word; }
.lg > .v > p { margin: 0; }
.lg > .v > * + * { margin-top: 6px; }
.lg > .rule { grid-column: 1 / -1; height: 1px; background: color-mix(in srgb, var(--rule) 70%, transparent); margin: 2px 0; }
.rhead { display: grid; grid-template-columns: var(--gut) minmax(0, 1fr); gap: var(--gap); align-items: end;
         margin: 8px 0 0; padding-bottom: 10px; border-bottom: 2px solid var(--ink); }
.rhead .num { text-align: right; font: 700 11px var(--sans); text-transform: uppercase; letter-spacing: 0.09em; color: var(--slate); }
.rhead .num b { display: block; font: 600 46px/0.9 var(--serif); color: var(--ink); letter-spacing: 0; margin-top: 2px; }
.rhead .order { margin: 0; font-size: 14px; color: var(--slate); }
.rhead .order b { color: var(--who); font-weight: 600; }
.t2 { padding: 20px 0 22px; border-bottom: 1px solid var(--rule); }
.t2 .head { display: grid; grid-template-columns: var(--gut) minmax(0, 1fr) auto; gap: 4px var(--gap); align-items: center; margin: 0 0 14px; }
.t2 h3 { font: 600 23px/1.2 var(--serif); color: var(--who); margin: 0; display: flex; align-items: center; gap: 10px; cursor: pointer; min-width: 0; }
.t2 h3::before { content: ""; width: 12px; height: 12px; border-radius: 2px; background: var(--who); flex: none; }
.badge { display: inline-flex; align-items: center; gap: 7px; font: 600 12.5px/1.2 var(--sans); padding: 5px 10px 5px 8px; border-radius: 999px;
         color: var(--tone); background: color-mix(in srgb, var(--tone) 13%, transparent); justify-self: end; }
.badge::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--tone); flex: none; }
.badge.good { --tone: var(--good); }
.badge.part { --tone: var(--part); }
.badge.part::before { background: linear-gradient(90deg, var(--tone) 50%, transparent 50%); box-shadow: inset 0 0 0 1.5px var(--tone); }
.badge.bad { --tone: var(--bad); }
.badge.bad::before, .badge.none::before { background: transparent; box-shadow: inset 0 0 0 2px var(--tone); }
.badge.none { --tone: var(--slate); }
.place b { font-weight: 600; }
.place span { color: var(--slate); }
.opts { list-style: none; margin: 0; padding: 0; display: grid; gap: 5px; font-size: 14px; color: var(--slate); }
.opts li { padding-left: 22px; position: relative; }
.opts li::before { content: "○"; position: absolute; left: 3px; top: 0; color: var(--slate); }
.opts li.chosen { color: var(--ink); font-weight: 500; }
.opts li.chosen::before { content: "✓"; color: var(--ink); font-weight: 700; }
.opts .for { font-size: 13px; font-style: italic; font-weight: 400; color: var(--slate); }
.t2 .do { font-size: 17.5px; line-height: 1.55; margin: 0; }
.t2 .why, .t2 .waiting { margin: 0; }
.t2 .heard { margin: 0; }
.t2 .story p { font: 16px/1.6 var(--serif); margin: 0 0 10px; }
.t2 .story p:last-child { margin-bottom: 0; }
.result p { font-size: 14px; margin: 0; }
.result p + p { margin-top: 3px; }
.inl { font: 700 11px var(--sans); text-transform: uppercase; letter-spacing: 0.09em; color: var(--slate); margin-right: 6px; }
.ledger { list-style: none; margin: 0; padding: 0; font: 12.5px/1.5 var(--mono); color: var(--slate); overflow-wrap: anywhere; }
.ledger li + li { margin-top: 2px; }
.between2 { padding: 18px 0; border-bottom: 1px solid var(--rule); }
.between2 .chron { font: 15.5px/1.55 var(--serif); color: var(--ink); margin: 0; }
.lg > .v > details { margin: 1px 0; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
@media (max-width: 600px) {
  header.top { position: static; }  /* stacked, the header would cover half a phone's screen */
  .row { grid-template-columns: minmax(0, 1fr); gap: 6px; padding: 10px 2px; }
  .row > .k { text-align: left; }
  .row > :empty { display: none; }
  .where { width: 100%; margin: 0 0 4px; order: -1; }
  .lg { grid-template-columns: minmax(0, 1fr); gap: 3px; }
  .lg > .k { text-align: left; padding-top: 12px; }
  .lg > .k:first-child { padding-top: 0; }
  .lg > .rule { margin: 10px 0 0; }
  .t2 .head { grid-template-columns: minmax(0, 1fr) auto; }
  .t2 .head > .k { grid-column: 1 / -1; text-align: left; }
  .rhead { grid-template-columns: auto minmax(0, 1fr); gap: 14px; }
  .rhead .num { text-align: left; }
}
.engine { display: grid; grid-template-columns: minmax(260px, 1fr) minmax(0, 2fr); gap: 24px; margin-top: 20px; align-items: start; }
.engine-side { display: grid; gap: 16px; }
@media (max-width: 900px) { .engine { grid-template-columns: minmax(0, 1fr); } }
.backstage h3 { font: 600 15px var(--sans); color: var(--slate); margin: 0 0 8px; }
.backstage .turn { margin-bottom: 10px; }
</style>
</head>
<body>
<main>
  <header class="top">
    <div class="titles">
      <h1 id="title">Run dashboard</h1>
      <p class="daytime" id="daytime"></p>
    </div>
    <div class="rows">
      <div class="row">
        <span class="k">Run</span>
        <div class="v facts" id="facts"></div>
        <div class="controls">
          <button id="pause" type="button" class="small">Pause after this round</button>
          <button id="end" type="button" class="small end">End the run</button>
        </div>
      </div>
      <div class="row">
        <span class="k">Viewing</span>
        <nav class="v pager" aria-label="Rounds">
          <button type="button" id="first">First</button>
          <button type="button" id="prior">Prior</button>
          <span class="where" id="where">No rounds yet</span>
          <button type="button" id="next">Next</button>
          <button type="button" id="current">Current</button>
        </nav>
        <span></span>
      </div>
      <div class="row" id="live-row">
        <span class="k">Live</span>
        <div class="v signal" id="signal">
          <span class="lamp" aria-hidden="true"></span>
          <span id="signal-text" aria-live="polite">Up to date</span>
          <button type="button" id="latest" disabled>Go to most recent</button>
        </div>
        <span></span>
      </div>
    </div>
    <p class="said" id="said" aria-live="polite"></p>
    <nav class="tabs" role="group" aria-label="Views">
      <button type="button" id="tab-narrative" aria-pressed="true">Narrative</button>
      <button type="button" id="tab-world" aria-pressed="false">World</button>
      <button type="button" id="tab-engine" aria-pressed="false">Engine</button>
    </nav>
  </header>
  <div id="view-narrative"></div>
  <div id="view-world" hidden>
    <section class="people" id="people" aria-label="The people"></section>
    <div class="coverage" id="coverage"></div>
    <div class="world" id="world"></div>
  </div>
  <div id="view-engine" hidden>
    <div class="engine">
      <div class="engine-side">
        <section class="box" aria-label="Now"><h3>Now</h3><p class="turnline" id="now"></p><div id="happening"></div></section>
        <section class="box" aria-label="The run so far"><h3>The run so far</h3><div id="meter"></div>
          <p class="note"><a href="/export.csv" id="csv">Download the whole log as CSV</a></p></section>
      </div>
      <section class="backstage" aria-labelledby="backstage-title"><h3 id="backstage-title">Backstage</h3><div id="backstage"></div></section>
    </div>
  </div>
</main>
<script>
const INKS = ["#1F6F78", "#6E3B6E", "#4E6B2F", "#9A4A1C", "#3A4FA0", "#9C3D5A"];
const INKS_DARK = ["#5FB7BF", "#C98BC9", "#9DBB72", "#E09A66", "#8EA0EA", "#E58AA6"];
const dark = matchMedia("(prefers-color-scheme: dark)");
const opened = new Set(), briefs = new Map();
const TABS = ["narrative", "world", "engine"];
let inkOf = {}, last = null, only = null, tab = "narrative", at = null, loadedAt = null;
const steps = new Map();
try { const t = localStorage.getItem("dashboard-tab"); if (TABS.includes(t)) tab = t; } catch (e) {}
{ const m = /[?&]tab=(narrative|world|engine)\b/.exec(location.search); if (m) tab = m[1]; }  // a view that can be bookmarked

function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "style") n.style.cssText = v; else if (k === "text") n.textContent = v; else n.setAttribute(k, v);
  }
  for (const k of kids) if (k != null) n.append(k);
  return n;
}
const plural = (n, word) => n + " " + word;
const modelName = m => m ? m[0].toUpperCase() + m.slice(1) : "";
const count = n => n == null ? "" : n.toLocaleString("en");
const money = x => x == null ? "" : "$" + (x > 0 && x < 0.01 ? x.toFixed(3) : x.toFixed(2));
function took(s) {
  if (s == null) return "";
  if (s < 60) return s + "s";
  if (s < 3600) return Math.floor(s / 60) + "m " + String(s % 60).padStart(2, "0") + "s";
  return Math.floor(s / 3600) + "h " + Math.floor(s % 3600 / 60) + "m";
}
const quote = t => "“" + t + "”";

// a folded part of the feed that stays open across refreshes
function fold(key, label, body) {
  const d = el("details", {"data-key": key}, el("summary", {text: label}), body);
  if (opened.has(key)) d.open = true;
  d.addEventListener("toggle", () => d.open ? opened.add(key) : opened.delete(key));
  return d;
}
const paragraphs = text => el("div", {class: "story"}, ...text.split(/\n\s*\n/).map(t => el("p", {text: t})));

// what a person was told before deciding: fetched only when opened, since a late brief is tens of thousands of characters
function briefFold(item) {
  if (item.brief_at == null) return null;
  const key = "brief:" + item.key, pre = el("pre", {text: briefs.get(item.brief_at) || "Loading…"});
  const d = fold(key, "What they were told (" + count(item.brief_chars) + " characters)", pre);
  const load = async () => {
    if (!d.open || briefs.has(item.brief_at)) return;
    try {
      const r = await fetch("/api/brief/" + item.brief_at, {cache: "no-store"});
      briefs.set(item.brief_at, r.ok ? (await r.json()).text : "Not found in the log.");
    } catch (e) { return; }
    pre.textContent = briefs.get(item.brief_at);
  };
  d.addEventListener("toggle", load);
  load();
  return d;
}

function commandList(cmds) {
  if (!cmds || !cmds.length) return null;
  return el("ul", {class: "cmds", "aria-label": "The referee's commands"}, ...cmds.map(c =>
    el("li", {class: c.refused ? "refused" : ""}, c.text, c.said ? el("span", {text: c.said}) : null)));
}

const cap1 = t => t ? t[0].toUpperCase() + t.slice(1) : t;

// the header's Run row: its state in a word, the seed, how far it has got, and when the page loaded it
function runFacts(d) {
  const r = d.run, cap = r.cap ? " of at most " + r.cap : "";
  const [tone, state, title] = r.ended ? ["ended", "Ended", "The run has ended."] :
    r.stop === "end" ? ["pausing", "Ending after this round", "The round in progress finishes, then the run closes."] :
    r.stop === "pause" ? ["pausing", "Pausing after this round", "/rounds or tools/rounds.py resumes it."] : ["going", "Going", "The run is going."];
  const played = r.played === 1 ? "1 round played" : r.played + " rounds played";
  return [el("span", {class: "state " + tone, title, text: state}),
          " · " + ["Seed " + d.seed, played + cap, loadedAt ? "Loaded " + loadedAt : null].filter(Boolean).join(" · ")];
}

function renderHappening(h, d) {
  const box = document.getElementById("happening");
  let line;
  if (h.stage === "deciding") line = [el("b", {text: h.who}), " is deciding, " + took(h.since) + " so far",
    h.told != null ? " (told " + count(h.told) + " characters)." : "."];
  else if (h.stage === "playing") line = ["The referee is playing ", el("b", {text: h.who}), "'s turn, " + took(h.since) + " so far."];
  else if (h.stage === "closing") line = ["Round " + h.round + " is closing: memories, the chronicle, the world's turn."];
  else if (h.stage === "paused") line = ["Paused after round " + h.round + ". /rounds or tools/rounds.py goes on from here."];
  else if (h.stage === "between") line = [h.next ? "Between turns; " : "Round " + h.round + ": everyone has had their turn.",
    h.next ? el("b", {text: h.next}) : "", h.next ? " is next." : ""];
  else line = [h.text];
  const steps = (h.steps || []).map(c => el("li", {class: c.refused ? "refused" : ""}, c.text, c.said ? el("span", {text: c.said}) : null));
  box.replaceChildren(...[el("p", {class: "nowtext"}, ...line),
    steps.length ? el("ul", {class: "steps", "aria-label": "The referee's latest commands"}, ...steps) : null].filter(Boolean));
}

function renderMeter(m, d) {
  const s = m.spend, box = document.getElementById("meter");
  const rows = m.rounds.map(r => el("tr", {},
    el("td", {text: r.round}), el("td", {class: r.open ? "so-far" : "", text: took(r.seconds)}),
    el("td", {class: r.open ? "so-far" : "", text: money(r.spend)}), el("td", {text: r.context ? Math.round(r.context / 1000) + "k" : ""}),
    el("td", {class: r.refused ? "warn" : "", text: r.refused || ""})));
  const going = !d.run.ended && d.run.stop !== "pause";
  const still = going && m.quiet != null && m.quiet > m.still;
  box.replaceChildren(...[
    el("p", {class: "total", text: money(s.total) + " spent"}),
    el("p", {class: "parts"}, "Referee ", el("b", {text: money(s.referee)}), " · People ", el("b", {text: money(s.people)}),
       " · Their memories ", el("b", {text: money(s.memory)}), " · Townspeople and the world ", el("b", {text: money(s.voices)})),
    rows.length ? el("table", {},
      el("thead", {}, el("tr", {}, ...["Round", "Time", "Cost", "Context", "Refused"].map(t => el("th", {scope: "col", text: t})))),
      el("tbody", {}, ...rows)) : null,
    d.run.open ? el("p", {class: "note", text: "A round's cost includes its referee once its session ends (tools/rounds.py); until then, the people's and agents' only."}) : null,
    m.quiet != null ? el("p", {class: "quiet" + (still ? " still" : ""), text: still ?
      "Nothing logged for " + took(m.quiet) + ": a long call, or nothing is running the rounds now." :
      "Last logged " + took(m.quiet) + " ago."}) : null].filter(Boolean));
}

// what came between turns or after a round ended: the chronicle, the world's turn, memories condensed; backstage (the
// Engine view), the world agent's replies, the referee's session and its commands
function renderBetween(item, backstage) {
  const ref = item.referee;
  return el("div", {class: "between"},
    ...(item.chronicle || []).map(t => el("p", {class: "chron"}, el("b", {text: "Chronicle: "}), t)),
    ...(item.world || []).map(t => el("p", {class: "chron"}, el("b", {text: "The world: "}), t)),
    ...(item.made || []).map(t => el("p", {class: "trade", text: "New in the world: " + t})),
    ...(item.money || []).map(t => el("p", {class: "trade", text: t})),
    ...(item.notes || []).map((n, i) => fold("n:" + item.key + i, "What " + (n.seen_by.join(" and ") || "no one") + " saw", paragraphs(n.text))),
    ...(item.memories || []).filter(m => !only || m.who === only).map((m, i) => fold("m:" + item.key + i,
      m.who + "'s memory of rounds " + m.rounds.join("–") + ", condensed (" + count(m.text.length) + " characters, from " + m.replaced + " entries)",
      el("div", {}, paragraphs(m.text), m.learned ? el("div", {class: "story"},
        el("p", {text: "What they've learned" + (m.learned_given ? "" : " (left as it was)") + ":"}),
        el("ul", {}, ...m.learned.map(x => el("li", {text: x})))) : null))),
    ...(item.voices || []).filter(v => backstage && v.agent !== "npc").map((v, i) =>
      fold("v:" + item.key + i, "The world agent, for " + v.about + (v.spend ? " (" + money(v.spend) + ")" : ""), el("pre", {text: v.reply}))),
    backstage && ref ? el("p", {class: "cost", text: "The referee's session: " + [took(ref.seconds), money(ref.spend),
      ref.context ? Math.round(ref.context / 1000) + "k context" : ""].filter(Boolean).join(" · ")}) : null,
    backstage ? commandList(item.commands) : null);
}

// every mechanic the kit has and how often this run has used it (the audit's COVERAGE, the same function)
function renderCoverage(d) {
  const box = document.getElementById("coverage"), used = d.coverage.filter(c => c[1]).length;
  box.replaceChildren(fold("coverage", "Mechanics used so far: " + used + " of " + d.coverage.length,
    el("ul", {}, ...d.coverage.map(([name, n]) => el("li", {class: n ? "" : "never"}, el("span", {text: name}), el("b", {text: n ? n : "never"}))))));
}

// a turn's commands in order, with all each printed: fetched when opened (a look prints the whole room)
function stepsFold(item) {
  const key = item.first + "-" + item.last + "/" + item.player, body = el("ul", {class: "cmds"});
  const fill = () => body.replaceChildren(...(steps.get(key) || [{text: "Loading…", said: ""}]).map(c =>
    el("li", {class: c.refused ? "refused" : ""}, c.text, c.said ? el("pre", {text: c.said}) : null)));
  const d = fold("steps:" + item.key, "The referee's commands, and what each printed", body);
  const load = async () => {
    if (!d.open) return;
    if (!steps.has(key) || item.story == null) {
      try { const r = await fetch("/api/steps/" + key, {cache: "no-store"}); steps.set(key, await r.json()); } catch (e) { return; }
    }
    fill();
  };
  fill();
  d.addEventListener("toggle", load);
  load();
  return d;
}

const BADGE = {done: ["good", "Done"], partly: ["part", "Partly done"], failed: ["bad", "Failed a check"],
               refused: ["bad", "Refused by someone"], out_of_reach: ["part", "Out of reach"],
               not_there: ["part", "Reached for something that isn't there"]};

// a label in the margin and what it labels, as two cells of a .lg grid
const kv = (k, ...v) => [el("div", {class: "k", text: k}), el("div", {class: "v"}, ...v.filter(x => x != null))];
const rule = () => el("div", {class: "rule", role: "presentation"});

// how the turn came out, always in words: the referee's outcome, or where the turn has got to
function badge(item) {
  const [tone, text] = item.outcome ? BADGE[item.outcome.result] || ["none", item.outcome.result] :
    ["none", !item.do ? "Deciding" : item.story == null ? "Being played" : "No outcome recorded"];
  return el("span", {class: "badge " + tone, text});
}

// a turn, its labels in the margin: what they decided (where, the options, their reasoning), what they did and what
// came back, and the bookkeeping (what it came to, the ledger, and the folds)
function turnCard(item) {
  const name = el("h3", {tabindex: "0", title: only === item.name ? "Show everyone" : "Show only " + item.name, text: item.name});
  const pick = () => { only = only === item.name ? null : item.name; draw(); };
  name.addEventListener("click", pick);
  name.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
  const options = item.options && item.options.length ?
    el("ul", {class: "opts", "aria-label": "The options they weighed"}, ...item.options.map(o =>
      el("li", {class: o.chosen ? "chosen" : ""}, o.chosen ? el("span", {class: "sr", text: "Chosen: "}) : null, o.text,
         o.for ? el("span", {class: "for", text: " — for: " + o.for}) : null))) : null;
  const place = item.place ? el("p", {class: "place"}, el("b", {text: item.place}),
    item.time ? el("span", {text: " · " + item.time}) : null, item.weather ? el("span", {text: ", " + item.weather}) : null) : null;
  const voices = (item.voices || []).filter(v => v.agent === "npc").map(v => el("p", {class: "voice"}, el("b", {text: v.about}), quote(v.said)));
  const notes = (item.notes || []).map((n, i) => fold("tn:" + item.key + i, "What " + (n.seen_by.join(" and ") || "no one") + " saw", paragraphs(n.text)));
  const result = [
    item.outcome && item.outcome.what ? el("p", {text: cap1(item.outcome.what) + "."}) : null,
    item.changed ? el("p", {}, el("span", {class: "inl", text: "For them"}), item.changed.replace(/^What changed: /, "")) : null,
    ...(item.chronicle || []).map(t => el("p", {}, el("span", {class: "inl", text: "Chronicle"}), t))].filter(Boolean);
  const ledger = [...(item.trades || []), ...(item.money || []), ...(item.made || []).map(x => "New in the world: " + x),
                  ...(item.world_changes || [])];
  const also = [briefFold(item), ...notes].filter(Boolean);
  const reasoning = [item.journal ? el("p", {class: "why", text: item.journal}) : null,
    ...(item.no_longer || []).map(x => el("p", {class: "cost", text: "No longer holds, they say: " + x.said +
      (x.struck ? " (struck from what they've learned)" : " (not on their list)")}))].filter(Boolean);
  const rows = [
    place ? kv("Where", place) : [], options ? kv("Weighed", options) : [], reasoning.length ? kv("Reasoning", ...reasoning) : [],
    rule(),
    kv("Did", item.do ? el("p", {class: "do", text: item.do}) : el("p", {class: "waiting", text: "Deciding…"})),
    item.do ? kv("Came back",
      el("p", {class: "heard", text: (item.with ? "There with them: " + item.with + "." : "No one else there.") +
        (item.heard_by.length ? " Their words were heard by " + item.heard_by.join(" and ") + "." : "")}),
      ...voices,
      item.story != null ? el("div", {class: "story"}, ...item.story.split(/\n\s*\n/).map(t => el("p", {text: t}))) :
        el("p", {class: "waiting", text: "Their turn is still being played."})) : [],
    result.length || ledger.length || also.length ? rule() : [],
    result.length ? kv("Result", el("div", {class: "result"}, ...result)) : [],
    ledger.length ? kv("Ledger", el("ul", {class: "ledger"}, ...ledger.map(x => el("li", {text: x})))) : [],
    also.length ? kv("Also", ...also) : []].flat();
  return el("article", {class: "t2", style: "--who:" + (inkOf[item.name] || "var(--slate)")},
    el("header", {class: "head"}, el("span", {class: "k", text: item.position ? "Turn " + item.position : ""}), name, badge(item)),
    el("div", {class: "lg"}, ...rows));
}

// what came between turns, at a round's start or end, as rows in the margin grid: the chronicle, the world's
// turn, what was made, money, the onlookers' notes and the memories condensed (the Engine view keeps renderBetween)
function betweenRows(item) {
  const chron = item.chronicle || [], world = item.world || [], made = item.made || [], money = item.money || [];
  const notes = (item.notes || []).map((n, i) => fold("n:" + item.key + i, "What " + (n.seen_by.join(" and ") || "no one") + " saw", paragraphs(n.text)));
  const memories = (item.memories || []).filter(m => !only || m.who === only).map((m, i) => fold("m:" + item.key + i,
    m.who + "'s memory of rounds " + m.rounds.join("–") + ", condensed (" + count(m.text.length) + " characters, from " + m.replaced + " entries)",
    el("div", {}, paragraphs(m.text), m.learned ? el("div", {class: "story"},
      el("p", {text: "What they've learned" + (m.learned_given ? "" : " (left as it was)") + ":"}),
      el("ul", {}, ...m.learned.map(x => el("li", {text: x})))) : null)));
  return [chron.length ? kv("Chronicle", ...chron.map(t => el("p", {class: "chron", text: t}))) : [],
    world.length ? kv("The world", el("ul", {class: "ledger"}, ...world.map(t => el("li", {text: t})))) : [],
    made.length || money.length ? kv("Ledger", el("ul", {class: "ledger"}, ...[...made.map(t => "New in the world: " + t), ...money].map(t => el("li", {text: t})))) : [],
    notes.length ? kv("Seen", ...notes) : [], memories.length ? kv("Memories", ...memories) : []].flat();
}
const between = rows => rows.length ? el("section", {class: "between2"}, el("div", {class: "lg"}, ...rows)) : null;

// a turn backstage: its time, cost and model, the referee's commands, and the world agent's replies for it
function backstageCard(item) {
  return el("article", {class: "turn", style: "--who:" + (inkOf[item.name] || "var(--slate)")},
    el("p", {class: "who"}, item.name, el("span", {text: " · round " + item.round + (item.position ? ", turn " + item.position : "")})),
    el("p", {class: "cost", text: [item.seconds != null ? took(item.seconds) + " from brief to story" : "still being played",
      item.spend ? money(item.spend) + " for their reply and the agents asked" : "", item.exact_model || "",
      item.brief_chars != null ? "told " + count(item.brief_chars) + " characters" : ""].filter(Boolean).join(" · ")}),
    ...(item.voices || []).filter(v => v.agent !== "npc").map((v, i) =>
      fold("bv:" + item.key + i, "The world agent, for " + v.about + (v.spend ? " (" + money(v.spend) + ")" : ""), el("pre", {text: v.reply}))),
    commandList(item.commands), stepsFold(item));
}

const roundOf = item => item.round == null ? null : Number(item.round);
function roundsIn(d) { return [...new Set(d.feed.map(roundOf).filter(r => r != null))].sort((a, b) => a - b); }
function shownRound(d) { return d.feed.filter(item => roundOf(item) === at).reverse(); }  // the order things happened

function renderNarrative(d) {
  const box = document.getElementById("view-narrative");
  if (!d.feed.length || at == null) { box.replaceChildren(el("p", {class: "empty", text: "Nothing has happened yet. The first round starts with /rounds."})); return; }
  const chips = el("div", {class: "chips", role: "group", "aria-label": "Whose turns"},
    ...[null, ...d.people.map(p => p.name)].map(n => {
      const b = el("button", {type: "button", "aria-pressed": String(only === n), style: n ? "--who:" + inkOf[n] : ""},
                   n ? el("i", {"aria-hidden": "true"}) : null, n || "Everyone");
      b.addEventListener("click", () => { only = n; draw(); });
      return b;
    }));
  const RUN = {pause: "Pause asked", resume: "Resumed", end: "End asked", ended: "The run ended"};
  const out = shownRound(d).flatMap(item => {
    if (item.kind === "turn") return !only || item.name === only ? [turnCard(item)] : [];
    if (item.kind === "round") return [el("div", {class: "rhead"},
      el("div", {class: "num"}, "Round", el("b", {text: item.round})),
      el("p", {class: "order", "aria-label": "Turn order"}, ...item.order.flatMap((n, i) => [i ? " → " : "", el("b", {style: "--who:" + (inkOf[n] || "var(--ink)"), text: n})]))),
      between(betweenRows(item))];
    if (item.kind === "round_end") return [between([...kv("Round " + item.round + " ends", item.world_turn ? el("p", {text: "And the world turns."}) : null), ...betweenRows(item)])];
    if (item.kind === "trade") return [between(kv("Trade", el("p", {text: item.text})))];
    if (item.kind === "asleep") return [between(kv("Asleep", el("p", {text: item.text})))];
    if (item.kind === "run") return [between(kv("The run", el("p", {text: RUN[item.action]})))];
    if (item.kind === "ending") return [between(kv("An ending",
      el("p", {text: "Round " + item.round + (item.by ? ", by " + item.by + "'s turn." : ".")}),
      fold("te:" + item.key, "What everyone was told" + (item.heard_by.length ? " (" + item.heard_by.join(", ") + " by a note)" : ""), paragraphs(item.text))))];
    return [];
  }).filter(Boolean);
  box.replaceChildren(el("div", {class: "narrative"}, chips, ...out));
}

function renderEngine(d) {
  renderHappening(d.happening, d);
  renderMeter(d.meter, d);
  const nowLine = document.getElementById("now"), now = d.people.find(p => p.now);
  nowLine.replaceChildren();
  if (d.run.open) {
    nowLine.append("Round " + d.run.round + ": " + d.run.order.join(", then ") + ". ");
    if (now) nowLine.append(el("b", {text: now.name}), now.replied ? " is acting." : " is deciding.");
    else nowLine.append("Everyone has had their turn.");
  }
  document.getElementById("backstage-title").textContent = at == null ? "Backstage" : "Round " + at + ", backstage";
  document.getElementById("backstage").replaceChildren(...shownRound(d).flatMap(item => {
    if (item.kind === "turn") return [backstageCard(item)];
    if (item.kind === "round" || item.kind === "round_end") return [el("p", {class: "marker", text: item.kind === "round" ?
      "Round " + item.round + " begins" : "Round " + item.round + " ends"}), renderBetween(item, true)];
    return [];
  }));
}

const list = (xs, empty) => xs && xs.length ? xs.join(", ") : (empty == null ? "none" : empty);
function box(title, ...kids) { return el("section", {class: "box"}, el("h3", {text: title}), ...kids); }
function table(heads, rows) {
  return el("div", {class: "scroll"}, el("table", {}, el("thead", {}, el("tr", {}, ...heads.map(h => el("th", {scope: "col", text: h})))),
    el("tbody", {}, ...rows.map(r => el("tr", {}, ...r.map(c => el("td", {text: c})))))));
}

function renderWorld(d) {
  const w = d.world, h = w.hooks, out = document.getElementById("world");
  const quests = h.quests.map(q => el("div", {class: "quest"},
    el("h4", {}, q.name + (q.side ? " (a side job)" : ""), " ", el("span", {class: "st-" + q.state, text: q.state})),
    el("p", {text: "From " + (q.giver || "no one") + ". Taken on by: " + list(q.taken_on, "no one yet") + "."}),
    q.ended ? el("p", {text: "Ended in round " + q.ended.round + ", " + q.ended.how + ", by " + q.ended.by + "."}) : null,
    el("p", {class: "cond", text: "complete when " + (q.completed_by || "—") + (q.failed_by ? " · failed when " + q.failed_by : "")}),
    el("ul", {}, ...q.objectives.map(o => el("li", {}, o.text + " ", el("span", {class: "cond", text: "(waits on " + (o.waits_on || "nothing") + ")"}),
      " — done for: " + list(o.done_for, "no one"))))));
  out.replaceChildren(
    box("Now", el("p", {text: w.clock || "No time of day in this world."})),
    box("Places", table(["Place", "Of the cast", "Townspeople", "Lying there", "Being built"],
      w.places.map(p => [p.name, list(p.cast, "—"), list(p.people, "—"), list(p.lying, "—"), list(p.building, "—")]))),
    box("The people", table(["Who", "Money", "Health", "Needs", "Carrying", "Their own places", "Taken on", "Beds paid ahead"],
      w.people.map(p => [p.name, p.coins + " " + d.currency, p.hp + " of " + p.max_hp, p.needs.join(" "), list(p.carrying, "nothing"),
                         list(p.own, "—"), list(p.taken_on, "—"), list(p.beds, "—")]))),
    box("Shared work", ...(w.projects.length ? w.projects.map(p => el("div", {class: "quest"},
      el("h4", {text: p.name + ", at " + p.place + ": " + p.total + " done"}),
      el("p", {text: "Stages: " + p.stages.map(s => s.at + " " + s.flag + (s.reached ? " (reached)" : "")).join(", ") + "."}),
      el("p", {}, p.until ? "Open while " : "Always open", p.until ? el("span", {class: "cond", text: p.until}) : null, p.open ? "; open now." : "; over now."),
      el("ul", {}, ...(p.by.length ? p.by.map(b => el("li", {text: b.name + ": " + b.turns + " turn" + (b.turns === 1 ? "" : "s") +
        ", " + b.paid + " paid" + (b.most ? " (most)" : "")})) : [el("li", {text: "No one has helped yet."})])))) : [el("p", {text: "None in this world."})])),
    box("Offers, lets and orders",
      el("p", {text: "Offers open: " + list(w.offers) + "."}), el("p", {text: "Places let: " + list(w.lets) + "."}),
      el("p", {text: "Things made and places built: " + list(w.orders.map(o => o.name + " (" + o.kind + ", by " + o.maker + " for " +
        (o.for || "someone") + ", " + o.status + ", " + o.price + ")")) + "."})),
    box("Talk going around", ...(w.rumors.length ? w.rumors.map(r => el("p", {text: r.text + " — heard by " + list(r.heard_by, "no one yet") + "."})) :
      [el("p", {text: "None yet."})])),
    box("Quests", ...quests),
    box("Timed events", h.events.length ? table(["Event", "When", "If", "Now"], h.events.map(e => [e.id, e.when, e.if || "", e.state])) :
      el("p", {text: "None in this world."})),
    box("Scarce prizes", el("ul", {}, ...h.prizes.map(x => el("li", {text: x})))),
    box("How the hooks went, in order", h.timeline.length ? el("ul", {}, ...h.timeline.map(x => el("li", {text: x}))) : el("p", {text: "Nothing yet."})));
}

function setTab(which) {
  tab = which;
  for (const t of TABS) {
    document.getElementById("tab-" + t).setAttribute("aria-pressed", String(t === which));
    document.getElementById("view-" + t).hidden = t !== which;
  }
  try { localStorage.setItem("dashboard-tab", which); } catch (e) {}
  draw();
}

// everything drawn from the data as last loaded: nothing here asks the server
function draw() {
  const d = last;
  if (!d) return;
  const people = document.getElementById("people");
  if (!d.game) {
    document.getElementById("title").textContent = "Run dashboard";
    document.getElementById("facts").textContent = "";
    document.getElementById("daytime").textContent = "";
    document.getElementById("now").textContent = "";
    people.replaceChildren(el("p", {class: "empty", text: "No run yet. Start one with /newgame, then /rounds."}));
    for (const id of ["view-narrative", "happening", "meter", "backstage", "coverage", "world"]) document.getElementById(id).replaceChildren();
    at = null;
    drawPager([]);
    setButtons(null);
    return;
  }
  const inks = dark.matches ? INKS_DARK : INKS;
  inkOf = {};
  d.people.forEach((p, i) => inkOf[p.name] = inks[i % inks.length]);
  document.title = d.game.title + ": round " + (at == null ? d.run.round : at);
  document.getElementById("title").textContent = d.game.title;
  document.getElementById("facts").replaceChildren(...runFacts(d));
  document.getElementById("daytime").textContent = d.time ? cap1(d.time) + "." : "";
  drawPager(roundsIn(d));
  people.replaceChildren(...d.people.map(p => {
    const pct = p.max_hp ? Math.max(0, Math.min(100, 100 * p.hp / p.max_hp)) : 0;
    const versions = p.exact_models.length > 1 ?
      el("span", {class: "warn", text: ", answered as " + p.exact_models.join(", then ")}) :
      p.exact_models.length ? ", " + p.exact_models[0] : "";
    return el("article", {class: "person" + (p.now ? " now" : ""), style: "--who:" + inkOf[p.name]},
      el("h2", {class: "name", text: p.name}),
      el("p", {class: "meta"}, modelName(p.model), versions, p.status !== "playing" ? ", " + p.status : "",
         p.now ? el("b", {text: p.replied ? ", acting now" : ", deciding now"}) : null),
      el("p", {class: "stat", text: p.place}),
      el("p", {class: "stat", text: "Health " + p.hp + " of " + p.max_hp}),
      el("div", {class: "bar", role: "presentation"}, el("i", {style: "width:" + pct + "%"})),
      el("p", {class: "stat", text: plural(p.coins, d.currency)}),
      el("p", {class: "carry", text: p.carrying.length ? "Carrying " + p.carrying.join(", ") : "Carrying nothing"}),
      p.told != null ? el("p", {class: "told", text: "Last told " + count(p.told) + " characters" +
        (p.first_told !== p.told ? " (first " + count(p.first_told) + ")" : "") + (p.spend ? "; " + money(p.spend) + " on their replies and memory" : "")}) : null,
      p.needs ? el("p", {class: "cost", text: "Needs: " + p.needs}) : null,
      p.journal ? el("p", {class: "journal"}, quote(p.journal),
                     el("small", {text: "Journal, round " + p.journal_round})) : null);
  }));
  renderCoverage(d);
  renderWorld(d);
  renderNarrative(d);
  renderEngine(d);
  setButtons(d.run);
}

// the pager: First, Prior, the round shown, Next, Current (the latest round loaded)
function drawPager(rounds) {
  const i = rounds.indexOf(at), first = rounds[0], latest = rounds[rounds.length - 1];
  document.getElementById("where").textContent = at == null ? "No rounds yet" : "Round " + at + " of " + latest;
  document.getElementById("first").disabled = document.getElementById("prior").disabled = at == null || i <= 0;
  document.getElementById("next").disabled = document.getElementById("current").disabled = at == null || i >= rounds.length - 1;
}

function go(which) {
  if (!last || !last.game) return;
  const rounds = roundsIn(last), i = rounds.indexOf(at);
  const to = {first: rounds[0], prior: rounds[Math.max(0, i - 1)], next: rounds[Math.min(rounds.length - 1, i + 1)],
              current: rounds[rounds.length - 1]}[which];
  if (to == null || to === at) return;
  at = to;
  draw();
  window.scrollTo(0, 0);
}

function setButtons(r) {
  const pause = document.getElementById("pause"), end = document.getElementById("end");
  pause.disabled = !r || r.ended || r.stop != null;
  end.disabled = !r || r.ended || r.stop === "end";
  pause.textContent = r && r.stop === "pause" ? "Pause asked" : "Pause after this round";
  end.textContent = r && (r.ended || r.stop === "end") ? (r.ended ? "Run ended" : "End asked") : "End the run";
}

// load the run as it stands; the page stays on the round shown unless asked to go to the most recent
async function load(toLatest) {
  try {
    const res = await fetch("/api/live", {cache: "no-store"});
    last = await res.json();
  } catch (e) {
    signal("down", "Can't reach the dashboard server. Is tools/dashboard.py still running?");
    return;
  }
  loadedAt = new Date().toLocaleTimeString("en-GB");
  const rounds = last.game ? roundsIn(last) : [];
  if (toLatest || at == null || !rounds.includes(at)) at = rounds.length ? rounds[rounds.length - 1] : null;
  signal("", "Up to date");
  draw();
  if (toLatest) window.scrollTo(0, 0);
}

function signal(state, text) {
  const box = document.getElementById("signal");
  box.className = "v signal" + (state ? " " + state : "");
  document.getElementById("live-row").classList.toggle("lit", state === "lit");
  document.getElementById("signal-text").textContent = text;
  document.getElementById("latest").disabled = state !== "lit";
}

// every few seconds, ask only how far the run has got; light the signal if it's further than the page
async function check() {
  if (!last) return;
  let s;
  try { s = await (await fetch("/api/stamp", {cache: "no-store"})).json(); } catch (e) {
    signal("down", "Can't reach the dashboard server. Is tools/dashboard.py still running?");
    return;
  }
  const was = last.stamp || {run: null}, news = [];
  if (s.run !== was.run) news.push(s.run ? "A new run has started" : "The run is gone");
  else if (s.run) {
    const turns = s.turns - was.turns, rounds = s.rounds_closed - was.rounds_closed;
    if (turns > 0) news.push(turns === 1 ? "1 new turn" : turns + " new turns");
    if (rounds > 0) news.push(rounds === 1 ? "round " + s.last_closed + " finished" : rounds + " rounds finished");
    if (s.ended !== was.ended || s.stop !== was.stop) news.push(s.ended ? "the run has ended" : s.stop === "pause" ? "a pause is asked" :
      s.stop === "end" ? "an end is asked" : "the run goes on");
  }
  if (news.length) { const t = news.join(", "); signal("lit", t[0].toUpperCase() + t.slice(1)); }
  else signal("", "Up to date");
}

async function ask(what) {
  const said = document.getElementById("said");
  try {
    const res = await fetch("/api/run/" + what, {method: "POST", headers: {"X-Dashboard": "1"}});
    const r = await res.json();
    said.textContent = !r.ok ? r.said.replace(/^REFUSED: /, "Not done: ") :
      what === "pause" ? "Pause asked. The round in progress finishes; /rounds goes on from there." :
      "End asked. The round in progress finishes, then the run closes.";
  } catch (e) {
    said.textContent = "Couldn't ask: the dashboard server didn't answer.";
  }
  load(false);
}

document.getElementById("pause").addEventListener("click", () => ask("pause"));
document.getElementById("end").addEventListener("click", () => {
  if (confirm("End the run? The round in progress finishes, then the run closes for good.")) ask("end");
});
for (const t of TABS) document.getElementById("tab-" + t).addEventListener("click", () => setTab(t));
for (const w of ["first", "prior", "next", "current"]) document.getElementById(w).addEventListener("click", () => go(w));
document.getElementById("latest").addEventListener("click", () => load(true));
document.addEventListener("keydown", e => {  // ← and → page through the rounds
  if (e.altKey || e.ctrlKey || e.metaKey || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
  if (e.key === "ArrowLeft") go("prior");
  if (e.key === "ArrowRight") go("next");
});
dark.addEventListener("change", draw);
setTab(tab);
load(true);
setInterval(check, 3000);
</script>
</body>
</html>
"""


def main(argv):
    if "--csv" in argv:
        i = argv.index("--csv")
        save = read_save()
        run_id = argv[i + 1] if i + 1 < len(argv) else (save or {}).get("run", {}).get("id")
        if not run_id or not (rpg.LOG / ("%s.jsonl" % run_id)).is_file():
            known = ", ".join(sorted(p.stem for p in rpg.LOG.glob("*.jsonl"))) if rpg.LOG.is_dir() else ""
            print("dashboard: no log for run %r (runs logged: %s)" % (run_id, known or "none"), file=sys.stderr)
            return 1
        sys.stdout.write(csv_of(log_entries(run_id)))
        return 0
    port = None
    if "--port" in argv:
        i = argv.index("--port")
        try:
            port = int(argv[i + 1])
        except (IndexError, ValueError):
            print("dashboard: --port needs a number")
            return 2
    if port is None:
        save = read_save()
        rpg.choose_game(save["game"] if save and save.get("game") else rpg.active_game())
        port = int(rpg.SETTINGS["dashboard"]["port"])
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("DASHBOARD: http://127.0.0.1:%d/" % server.server_address[1], flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
