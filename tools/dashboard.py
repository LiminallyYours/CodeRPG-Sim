#!/usr/bin/env python3
"""The owner's dashboard: a live view of the run, served on this machine only.

    python3 tools/dashboard.py [--port N]     then open http://127.0.0.1:<port>/ (the port is dashboard.port)
    python3 tools/dashboard.py --csv [run]    the run's log as CSV on stdout (the current run if none is named)

It reads the save and the run's log, and refreshes every few seconds: the round and its order; each person's
place, health, money, belongings, latest journal line, how long their brief has grown, what they've cost and the
exact model that answered; what's happening now (who is deciding or being played, for how long, and the referee's
latest commands); what the run has spent, for whom, and each round's time, cost, context and refusals; and a feed
of each turn (what they did and why, the townspeople's words, onlookers' notes, trades, coins and orders, the
chronicle, the story, and what they were told, fetched when opened), what came between rounds (the world's turn,
memories condensed) and endings. "Everything" (or `/?view=all`) adds the referee's commands and each turn's cost.
Its two buttons ask `rpg.py run pause` and `run end`; the dashboard never writes a game file itself.
The log is also served as CSV, one row per entry, for analysis elsewhere (`/export.csv`, or `--csv`).
Python's standard library only.
"""
import csv
import datetime
import io
import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "rules"))
import rpg  # noqa: E402

FEED_LIMIT = 80  # feed items sent to the page, newest first


def read_save():
    """The save as it stands, or None (no game yet). rpg.py writes it atomically, so it's never half written."""
    try:
        return json.loads(rpg.SAVE.read_text())
    except (OSError, ValueError):
        return None


def log_entries(run_id):
    """The run's log; a line still being written is skipped until the next refresh."""
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


def world_lines(output, name):
    """What a world turn changed, from `world-turn`'s output: its rumors and who moved where."""
    out = []
    for line in output.splitlines():
        if line.startswith("  rumor: "):
            out.append("Rumor: " + line[9:])
        elif line.startswith("  ") and " is now at " in line:
            who, room = line.strip().split(" is now at ", 1)
            out.append("%s is now at %s." % (name(who), name(room)))
    return out


def add(item, key, value):
    item.setdefault(key, []).append(value)


def build_feed(entries, names, name, currency="coins"):
    """What happened, oldest first: each turn (from their brief: what they did, why, the story they were told, the
    words others heard, what the townspeople said, the onlookers' notes, trades, grabs, coins and orders, what was
    made, the chronicle, and the referee's commands), the round markers, with what came between rounds (world
    turns, memories condensed, the referee's session), and endings. A turn takes the entries of its round that are
    its person's or no one's, from its brief until the next turn or the round's end; anything else goes to the
    latest round marker."""
    items, turn, bucket = [], None, None

    def new_turn(e):
        pid = e.get("player")
        t = {"kind": "turn", "key": "%s:%s" % (e.get("round"), pid), "round": e.get("round"), "player": pid,
             "name": names.get(pid, pid), "model": None, "exact_model": None, "do": "", "journal": "", "options": None,
             "story": None, "brief_at": None, "brief_chars": None, "heard_by": [], "trades": [], "spend": 0.0,
             "seconds": None, "t": e.get("t")}
        items.append(t)
        return t

    for i, e in enumerate(entries):
        kind = e["kind"]
        fresh = turn is not None and turn["player"] == e.get("player") and turn["round"] == e.get("round") and not turn["do"]
        if kind == "brief" and e.get("player"):
            turn = turn if fresh else new_turn(e)
            turn.update(brief_at=i, brief_chars=len(e.get("text", "")))
            continue
        if kind == "action":
            turn = turn if fresh else new_turn(e)
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
        if kind == "narration" and mine:
            turn["story"] = e.get("text", "")
            turn["seconds"] = seconds_between(turn, e)
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


def live():
    """Everything the page shows, as JSON-ready data."""
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
    items = build_feed(entries, names, name, currency)
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
        "feed": items[::-1][:FEED_LIMIT],
    }


def brief_at(n):
    """The brief at line n of the current run's log, for the feed's "What they were told" (sent only when asked:
    a late brief runs to tens of thousands of characters)."""
    save = read_save()
    entries = log_entries(save["run"]["id"]) if save and "run" in save else []
    e = entries[n] if 0 <= n < len(entries) else None
    return {"text": e.get("text", "")} if e and e["kind"] == "brief" else None


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
        if self.path.startswith("/api/brief/") and self.path[11:].isdigit():
            brief = brief_at(int(self.path[11:]))
            return self.send(200, json.dumps(brief, ensure_ascii=False), "application/json") if brief else \
                self.send(404, "no brief there", "text/plain")
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
  --brass: #8C6D1F; --brick: #A63D2B;
  --serif: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
  --sans: system-ui, -apple-system, "Segoe UI", sans-serif;
  --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root { --paper: #151C27; --sheet: #1C2532; --ink: #DCE3EA; --slate: #94A3B5; --rule: #2E3A4B;
          --brass: #D2AE52; --brick: #E07A66; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink); font: 15px/1.5 var(--sans); }
main { max-width: 1180px; margin: 0 auto; padding: 24px 16px 64px; }
header { display: flex; flex-wrap: wrap; gap: 12px 32px; align-items: end; justify-content: space-between;
         border-bottom: 1px solid var(--rule); padding-bottom: 16px; }
h1 { font: 600 30px/1.15 var(--serif); margin: 0 0 4px; letter-spacing: 0.005em; }
.facts { color: var(--slate); margin: 0; }
.turnline { margin: 6px 0 0; }
.turnline b { color: var(--brass); font-weight: 600; }
.controls { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
button { font: 500 14px var(--sans); padding: 8px 14px; border-radius: 6px; cursor: pointer;
         border: 1px solid var(--ink); background: transparent; color: var(--ink); }
button.end { border-color: var(--brick); color: var(--brick); }
button:hover:not(:disabled) { background: var(--sheet); }
button:disabled { opacity: 0.45; cursor: default; }
button:focus-visible, summary:focus-visible, a:focus-visible { outline: 2px solid var(--brass); outline-offset: 2px; }
.said { color: var(--slate); font-size: 13px; width: 100%; text-align: right; min-height: 1.2em; margin: 0; }
.people { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 0 28px; margin: 24px 0 8px; }
.person { border-top: 3px solid var(--who); padding: 12px 0 20px; }
.person.now { border-top-color: var(--brass); }
.person h2 { margin: 0; }
.person h2 button { font: 600 19px/1.2 var(--serif); color: var(--who); border: 0; padding: 0; background: none; text-align: left; }
.person h2 button:hover { background: none; text-decoration: underline; text-underline-offset: 3px; }
.person h2 button[aria-pressed="true"] { text-decoration: underline; text-decoration-thickness: 2px; text-underline-offset: 3px; }
.meta b { color: var(--brass); font-weight: 600; }
.meta { color: var(--slate); font-size: 13px; margin: 2px 0 10px; }
.warn { color: var(--brick); }
.stat { margin: 2px 0; }
.bar { height: 4px; background: var(--rule); border-radius: 2px; margin: 4px 0 8px; max-width: 180px; }
.bar i { display: block; height: 100%; border-radius: 2px; background: var(--who); }
.carry, .told { color: var(--slate); font-size: 13.5px; margin: 6px 0 0; }
.journal { font: italic 17px/1.45 var(--serif); margin: 14px 0 0; }
.journal small { display: block; font: 13px var(--sans); font-style: normal; color: var(--slate); margin-top: 4px; }
.below { display: grid; grid-template-columns: minmax(0, 74ch) minmax(260px, 1fr); gap: 0 40px; margin-top: 28px; align-items: start; }
aside { position: sticky; top: 16px; display: grid; gap: 16px; }
@media (max-width: 900px) { .below { grid-template-columns: minmax(0, 1fr); } aside { position: static; order: -1; margin-bottom: 24px; } }
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
.feed h3 { font: 600 15px var(--sans); color: var(--slate); margin: 0 0 8px; display: flex; flex-wrap: wrap;
           justify-content: space-between; align-items: center; gap: 6px 16px; }
.feed h3 a { font-weight: 400; color: var(--ink); }
.views { display: inline-flex; border: 1px solid var(--rule); border-radius: 6px; overflow: hidden; }
.views button { border: 0; border-radius: 0; padding: 4px 12px; font-size: 13px; color: var(--slate); }
.views button[aria-pressed="true"] { background: var(--ink); color: var(--paper); }
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
</style>
</head>
<body>
<main>
  <header>
    <div>
      <h1 id="title">Run dashboard</h1>
      <p class="facts" id="facts"></p>
      <p class="turnline" id="now"></p>
    </div>
    <div class="controls">
      <button id="pause" type="button">Pause after this round</button>
      <button id="end" type="button" class="end">End the run</button>
      <p class="said" id="said" aria-live="polite"></p>
    </div>
  </header>
  <section class="people" id="people" aria-label="The people"></section>
  <div class="below">
    <section class="feed" aria-label="What happened">
      <h3><span>What happened, newest first</span>
        <span class="views" role="group" aria-label="How much to show">
          <button type="button" id="view-people" aria-pressed="true">People</button>
          <button type="button" id="view-all" aria-pressed="false">Everything</button>
        </span>
        <a href="/export.csv" id="csv">Download the whole log as CSV</a></h3>
      <p class="filter" id="filter" hidden></p>
      <div id="feed"></div>
    </section>
    <aside aria-label="The run as it goes">
      <section class="box" aria-label="Now"><h3>Now</h3><div id="happening"></div></section>
      <section class="box" aria-label="The run so far"><h3>The run so far</h3><div id="meter"></div></section>
    </aside>
  </div>
</main>
<script>
const INKS = ["#1F6F78", "#6E3B6E", "#4E6B2F", "#9A4A1C", "#3A4FA0", "#9C3D5A"];
const INKS_DARK = ["#5FB7BF", "#C98BC9", "#9DBB72", "#E09A66", "#8EA0EA", "#E58AA6"];
const dark = matchMedia("(prefers-color-scheme: dark)");
const opened = new Set(), briefs = new Map();
let inkOf = {}, last = null, only = null, everything = false;
try { everything = localStorage.getItem("dashboard-view") === "all"; } catch (e) {}
if (/[?&]view=(all|people)\b/.test(location.search)) everything = /view=all/.test(location.search);  // a view that can be bookmarked

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
  if (!everything || !cmds || !cmds.length) return null;
  return el("ul", {class: "cmds", "aria-label": "The referee's commands"}, ...cmds.map(c =>
    el("li", {class: c.refused ? "refused" : ""}, c.text, c.said ? el("span", {text: c.said}) : null)));
}

function runLine(d) {
  const r = d.run, cap = r.cap ? " of at most " + r.cap : "";
  const state = r.ended ? "The run has ended." : r.stop === "end" ? "Ending after this round." :
                r.stop === "pause" ? "Pausing after this round; /rounds resumes it." : "The run is going.";
  const played = r.played === 1 ? "1 round played" : r.played + " rounds played";
  return "Seed " + d.seed + ". " + played + cap + ". " + state + (d.time ? " " + d.time[0].toUpperCase() + d.time.slice(1) + "." : "");
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
  const rows = m.rounds.slice(0, 10).map(r => el("tr", {},
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

function renderTurn(item) {
  const options = item.options && item.options.length ?  // what they weighed before choosing: theirs alone, like the journal
    el("ul", {class: "options", "aria-label": "The options they weighed"}, ...item.options.map(o =>
      el("li", {class: o.chosen ? "chosen" : ""}, o.text, o.for ? el("span", {text: " (for: " + o.for + ")"}) : null,
         o.chosen ? el("b", {text: " chosen"}) : null))) : null;
  const voices = (item.voices || []).map(v => v.agent === "npc" ?
    el("p", {class: "voice"}, el("b", {text: v.about}), quote(v.said)) :
    everything ? fold("v:" + item.key + v.about, "The world agent, for " + v.about, el("pre", {text: v.reply})) : null);
  const notes = (item.notes || []).map((n, i) => fold("n:" + item.key + i, "What " + (n.seen_by.join(" and ") || "no one") + " saw", paragraphs(n.text)));
  const story = item.story != null ? fold(item.key, "The story they were told", paragraphs(item.story)) : null;
  const cost = everything && (item.spend || item.seconds != null) ?
    el("p", {class: "cost", text: [item.seconds != null ? took(item.seconds) + " from brief to story" : "",
      item.spend ? money(item.spend) + " for their reply and the agents asked" : "",
      item.exact_model || ""].filter(Boolean).join(" · ")}) : null;
  return el("article", {class: "turn", style: "--who:" + (inkOf[item.name] || "var(--slate)")},
    el("p", {class: "who"}, item.name, el("span", {text: ", round " + item.round})),
    item.do ? null : el("p", {class: "waiting", text: "Deciding…"}),
    options,
    item.do ? el("p", {class: "do", text: item.do}) : null,
    item.journal ? el("p", {class: "why", text: item.journal}) : null,
    ...(item.no_longer || []).map(x => el("p", {class: "cost", text: "No longer holds, they say: " + x.said +
      (x.struck ? " (struck from what they've learned)" : " (not on their list)")})),
    item.heard_by.length ? el("p", {class: "heard", text: "Heard by " + item.heard_by.join(" and ")}) : null,
    ...voices,
    ...(item.trades || []).map(t => el("p", {class: "trade", text: t})),
    ...(item.money || []).map(t => el("p", {class: "trade", text: t})),
    ...(item.made || []).map(t => el("p", {class: "trade", text: "New in the world: " + t})),
    ...(item.chronicle || []).map(t => el("p", {class: "chron"}, el("b", {text: "Chronicle: "}), t)),
    ...notes,
    story || (item.do ? el("p", {class: "heard", text: "Their turn is still being played."}) : null),
    briefFold(item),
    cost,
    commandList(item.commands));
}

// what came between turns or after a round ended: the chronicle, the world's turn, memories condensed, and the referee's session
function renderBetween(item) {
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
    ...(item.voices || []).filter(v => everything && v.agent !== "npc").map((v, i) =>
      fold("v:" + item.key + i, "The world agent, for " + v.about + (v.spend ? " (" + money(v.spend) + ")" : ""), el("pre", {text: v.reply}))),
    everything && ref ? el("p", {class: "cost", text: "The referee's session: " + [took(ref.seconds), money(ref.spend),
      ref.context ? Math.round(ref.context / 1000) + "k context" : ""].filter(Boolean).join(" · ")}) : null,
    commandList(item.commands));
}

function renderFeed(d) {
  const feed = document.getElementById("feed"), filter = document.getElementById("filter");
  if (only) {
    filter.hidden = false;
    filter.replaceChildren("Showing only " + only + "'s turns.", el("button", {type: "button", id: "all-people"}, "Show everyone"));
    document.getElementById("all-people").addEventListener("click", () => { only = null; render(last); });
  } else filter.hidden = true;
  if (!d.feed.length) {
    feed.replaceChildren(el("p", {class: "empty", text: "Nothing has happened yet. The first round starts with /rounds."}));
    return;
  }
  const items = d.feed.filter(item => !only || item.kind !== "turn" || item.name === only);
  feed.replaceChildren(...items.flatMap(item => {
    if (item.kind === "round") return [el("p", {class: "marker", text: "Round " + item.round + " begins: " + item.order.join(", then ")}), renderBetween(item)];
    if (item.kind === "round_end") return [el("p", {class: "marker", text: "Round " + item.round + " ends" + (item.world_turn ? ", and the world turns" : "")}), renderBetween(item)];
    if (item.kind === "trade") return [el("p", {class: "marker", text: item.text})];
    if (item.kind === "run") return [el("p", {class: "marker", text: {pause: "Pause asked", resume: "Resumed", end: "End asked", ended: "The run ended"}[item.action]})];
    if (item.kind === "ending") return [el("article", {class: "ending"},
      el("p", {class: "who", text: "An ending, round " + item.round + (item.by ? ", by " + item.by + "'s turn" : "")}),
      fold(item.key, "What everyone was told" + (item.heard_by.length ? " (" + item.heard_by.join(", ") + " by a note)" : ""), paragraphs(item.text)))];
    return [renderTurn(item)];
  }));
}

function render(d) {
  const people = document.getElementById("people");
  if (!d.game) {
    document.getElementById("title").textContent = "Run dashboard";
    document.getElementById("facts").textContent = "";
    document.getElementById("now").textContent = "";
    people.replaceChildren(el("p", {class: "empty", text: "No run yet. Start one with /newgame, then /rounds."}));
    document.getElementById("feed").replaceChildren();
    document.getElementById("happening").replaceChildren();
    document.getElementById("meter").replaceChildren();
    setButtons(null);
    return;
  }
  const inks = dark.matches ? INKS_DARK : INKS;
  inkOf = {};
  d.people.forEach((p, i) => inkOf[p.name] = inks[i % inks.length]);
  document.title = d.game.title + ": round " + d.run.round;
  document.getElementById("title").textContent = d.game.title;
  document.getElementById("facts").textContent = runLine(d);
  const now = d.people.find(p => p.now);
  const nowLine = document.getElementById("now");
  nowLine.replaceChildren();
  if (d.run.open) {
    nowLine.append("Round " + d.run.round + ": " + d.run.order.join(", then ") + ". ");
    if (now) nowLine.append(el("b", {text: now.name}), now.replied ? " is acting." : " is deciding.");
    else nowLine.append("Everyone has had their turn.");
  }
  people.replaceChildren(...d.people.map(p => {
    const pct = p.max_hp ? Math.max(0, Math.min(100, 100 * p.hp / p.max_hp)) : 0;
    const name = el("button", {type: "button", "aria-pressed": String(only === p.name),
      title: only === p.name ? "Show everyone's turns" : "Show only " + p.name + "'s turns"}, p.name);
    name.addEventListener("click", () => { only = only === p.name ? null : p.name; render(last); });
    const versions = p.exact_models.length > 1 ?
      el("span", {class: "warn", text: ", answered as " + p.exact_models.join(", then ")}) :
      p.exact_models.length ? ", " + p.exact_models[0] : "";
    return el("article", {class: "person" + (p.now ? " now" : ""), style: "--who:" + inkOf[p.name]},
      el("h2", {}, name),
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
  renderHappening(d.happening, d);
  renderMeter(d.meter, d);
  renderFeed(d);
  setButtons(d.run);
}

function setButtons(r) {
  const pause = document.getElementById("pause"), end = document.getElementById("end");
  pause.disabled = !r || r.ended || r.stop != null;
  end.disabled = !r || r.ended || r.stop === "end";
  pause.textContent = r && r.stop === "pause" ? "Pause asked" : "Pause after this round";
  end.textContent = r && (r.ended || r.stop === "end") ? (r.ended ? "Run ended" : "End asked") : "End the run";
}

function setView(all) {
  everything = all;
  document.getElementById("view-people").setAttribute("aria-pressed", String(!all));
  document.getElementById("view-all").setAttribute("aria-pressed", String(all));
  try { localStorage.setItem("dashboard-view", all ? "all" : "people"); } catch (e) {}
  if (last) render(last);
}

async function refresh() {
  try {
    const res = await fetch("/api/live", {cache: "no-store"});
    last = await res.json();
    render(last);
    document.getElementById("said").classList.remove("stale");
  } catch (e) {
    const said = document.getElementById("said");
    said.textContent = "Can't reach the dashboard server. Is tools/dashboard.py still running?";
    said.classList.add("stale");
  }
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
  refresh();
}

document.getElementById("pause").addEventListener("click", () => ask("pause"));
document.getElementById("end").addEventListener("click", () => {
  if (confirm("End the run? The round in progress finishes, then the run closes for good.")) ask("end");
});
document.getElementById("view-people").addEventListener("click", () => setView(false));
document.getElementById("view-all").addEventListener("click", () => setView(true));
setView(everything);
dark.addEventListener("change", () => last && render(last));
refresh();
setInterval(refresh, 3000);
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
