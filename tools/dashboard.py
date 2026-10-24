#!/usr/bin/env python3
"""The owner's dashboard: a live view of the run, served on this machine only.

    python3 tools/dashboard.py [--port N]     then open http://127.0.0.1:<port>/ (the port is dashboard.port)
    python3 tools/dashboard.py --csv [run]    the run's log as CSV on stdout (the current run if none is named)

It reads the save and the run's log, and refreshes every few seconds: the round and its order, each person's
place, health, money, belongings and latest journal line, and a feed of what each did, why, and the story they
were told. Its two buttons ask `rpg.py run pause` and `run end`; the dashboard never writes a game file itself.
The log is also served as CSV, one row per entry, for analysis elsewhere (`/export.csv`, or `--csv`).
Python's standard library only.
"""
import csv
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


def feed_of(entries, names):
    """What happened, newest first: each turn (what they did, why, the story they were told, and the words others
    heard), and the round markers between."""
    items, turns = [], {}
    for e in entries:
        key = (e.get("round"), e.get("player"))
        if e["kind"] == "action":
            turn = {"kind": "turn", "key": "%s:%s" % key, "round": e.get("round"), "player": e.get("player"),
                    "name": names.get(e.get("player"), e.get("player")), "model": e.get("model"),
                    "do": e.get("do", ""), "journal": e.get("journal", ""), "story": None, "heard_by": []}
            turns[key] = turn
            items.append(turn)
        elif e["kind"] == "narration" and key in turns:
            turns[key]["story"] = e.get("text", "")
        elif e["kind"] == "speech" and key in turns:
            turns[key]["heard_by"] = [names.get(p, p) for p in e.get("heard_by", [])]
        elif e["kind"] == "round" and e.get("phase") == "start":
            items.append({"kind": "round", "key": "r%s" % e.get("round"), "round": e.get("round"),
                          "order": [names.get(p, p) for p in e.get("order", [])]})
        elif e["kind"] == "round" and e.get("phase") == "end":
            items.append({"kind": "round_end", "key": "e%s" % e.get("round"), "round": e.get("round"),
                          "world_turn": bool(e.get("world_turn_due"))})
        elif e["kind"] == "run" and e.get("action") in ("pause", "resume", "end", "ended"):
            items.append({"kind": "run", "key": "run%d" % len(items), "action": e["action"], "round": e.get("round")})
    return items[::-1][:FEED_LIMIT]


def live():
    """Everything the page shows, as JSON-ready data."""
    save = read_save()
    if not save or "players" not in save:
        return {"game": None}
    rpg.choose_game(save["game"])
    run, view = save["run"], save.get("view", {})
    look = view.get("look", {})
    rs = run.get("round_state")
    players = save["players"]
    names = {pid: pl["name"] for pid, pl in players.items()}
    nxt = next((p for p in rs["order"] if p not in rs.get("done", []) and players[p]["status"] == "playing"), None) if rs else None
    entries = log_entries(run["id"])
    people = []
    for pid, pl in players.items():
        v = view.get("players", {}).get(pid, {})
        turn = pl.get("turn") or {}
        people.append({
            "id": pid, "name": pl["name"], "model": pl.get("model"), "status": pl["status"],
            "place": v.get("location_name", pl["location"]),
            "hp": pl["stats"]["hp"], "max_hp": pl["stats"]["max_hp"], "coins": pl["stats"]["coins"],
            "carrying": [i["name"] + (" (in hand)" if i.get("equipped") else "") for i in v.get("items", [])],
            "journal": turn.get("journal", ""), "journal_round": turn.get("round"),
            "now": pid == nxt, "replied": pid == nxt and turn.get("round") == run.get("round"),
        })
    cap = int(rpg.SETTINGS["rounds"]["max_per_run"])
    return {
        "game": {"id": save["game"], "title": save.get("adventure", save["game"])},
        "seed": run.get("seed"), "currency": look.get("currency", "coins"),
        "time": ", ".join(x for x in (view.get("time"), view.get("weather")) if x),
        "run": {"round": run.get("round", 0), "open": bool(rs), "played": run.get("round", 0) - (1 if rs else 0),
                "cap": cap, "stop": run.get("stop"), "ended": bool(run.get("ended")),
                "order": [names.get(p, p) for p in rs["order"]] if rs else [],
                "done": [names.get(p, p) for p in rs.get("done", [])] if rs else []},
        "people": people,
        "feed": feed_of(entries, names),
    }


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
        if self.path == "/":
            return self.send(200, PAGE, "text/html; charset=utf-8")
        if self.path == "/api/live":
            return self.send(200, json.dumps(live(), ensure_ascii=False), "application/json")
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
button:focus-visible, summary:focus-visible { outline: 2px solid var(--brass); outline-offset: 2px; }
.said { color: var(--slate); font-size: 13px; width: 100%; text-align: right; min-height: 1.2em; margin: 0; }
.people { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 0 28px; margin: 24px 0 8px; }
.person { border-top: 3px solid var(--who); padding: 12px 0 20px; }
.person.now { border-top-color: var(--brass); }
.person h2 { font: 600 19px/1.2 var(--serif); margin: 0; color: var(--who); }
.meta b { color: var(--brass); font-weight: 600; }
.meta { color: var(--slate); font-size: 13px; margin: 2px 0 10px; }
.stat { margin: 2px 0; }
.bar { height: 4px; background: var(--rule); border-radius: 2px; margin: 4px 0 8px; max-width: 180px; }
.bar i { display: block; height: 100%; border-radius: 2px; background: var(--who); }
.carry { color: var(--slate); font-size: 13.5px; margin: 6px 0 0; }
.journal { font: italic 17px/1.45 var(--serif); margin: 14px 0 0; }
.journal small { display: block; font: 13px var(--sans); font-style: normal; color: var(--slate); margin-top: 4px; }
.feed { max-width: 74ch; margin-top: 28px; }
.feed h3 { font: 600 15px var(--sans); color: var(--slate); margin: 0 0 8px; display: flex; flex-wrap: wrap;
           justify-content: space-between; gap: 4px 16px; }
.feed h3 a { font-weight: 400; color: var(--ink); }
.feed h3 a:focus-visible { outline: 2px solid var(--brass); outline-offset: 2px; }
.turn { padding: 14px 0 16px 16px; border-left: 3px solid var(--who); margin: 0 0 14px; background: var(--sheet); border-radius: 0 6px 6px 0; padding-right: 16px; }
.turn .who { font: 600 14px var(--sans); color: var(--who); margin: 0 0 6px; }
.turn .who span { color: var(--slate); font-weight: 400; }
.do { font: 17px/1.5 var(--serif); margin: 0 0 8px; }
.why { font: italic 15.5px/1.5 var(--serif); color: var(--slate); margin: 0 0 8px; }
.heard { font-size: 13px; color: var(--slate); margin: 0 0 6px; }
details summary { cursor: pointer; color: var(--slate); font-size: 13.5px; }
details .story { font: 16px/1.6 var(--serif); margin-top: 8px; }
details .story p { margin: 0 0 10px; }
.marker { color: var(--slate); font-size: 13.5px; margin: 18px 0 14px; display: flex; gap: 10px; align-items: center; }
.marker::before, .marker::after { content: ""; flex: 1; height: 1px; background: var(--rule); }
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
  <section class="feed" aria-label="What happened">
    <h3>What happened, newest first <a href="/export.csv" id="csv">Download the whole log as CSV</a></h3>
    <div id="feed"></div>
  </section>
</main>
<script>
const INKS = ["#1F6F78", "#6E3B6E", "#4E6B2F", "#9A4A1C", "#3A4FA0", "#9C3D5A"];
const INKS_DARK = ["#5FB7BF", "#C98BC9", "#9DBB72", "#E09A66", "#8EA0EA", "#E58AA6"];
const dark = matchMedia("(prefers-color-scheme: dark)");
const opened = new Set();
let inkOf = {}, last = null;

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

function runLine(d) {
  const r = d.run, cap = r.cap ? " of at most " + r.cap : "";
  const state = r.ended ? "The run has ended." : r.stop === "end" ? "Ending after this round." :
                r.stop === "pause" ? "Pausing after this round; /rounds resumes it." : "The run is going.";
  const played = r.played === 1 ? "1 round played" : r.played + " rounds played";
  return "Seed " + d.seed + ". " + played + cap + ". " + state + (d.time ? " " + d.time[0].toUpperCase() + d.time.slice(1) + "." : "");
}

function render(d) {
  const people = document.getElementById("people"), feed = document.getElementById("feed");
  if (!d.game) {
    document.getElementById("title").textContent = "Run dashboard";
    document.getElementById("facts").textContent = "";
    document.getElementById("now").textContent = "";
    people.replaceChildren(el("p", {class: "empty", text: "No run yet. Start one with /newgame, then /rounds."}));
    feed.replaceChildren();
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
    return el("article", {class: "person" + (p.now ? " now" : ""), style: "--who:" + inkOf[p.name]},
      el("h2", {text: p.name}),
      el("p", {class: "meta"}, modelName(p.model) + (p.status !== "playing" ? ", " + p.status : ""),
         p.now ? el("b", {text: p.replied ? ", acting now" : ", deciding now"}) : null),
      el("p", {class: "stat", text: p.place}),
      el("p", {class: "stat", text: "Health " + p.hp + " of " + p.max_hp}),
      el("div", {class: "bar", role: "presentation"}, el("i", {style: "width:" + pct + "%"})),
      el("p", {class: "stat", text: plural(p.coins, d.currency)}),
      el("p", {class: "carry", text: p.carrying.length ? "Carrying " + p.carrying.join(", ") : "Carrying nothing"}),
      p.journal ? el("p", {class: "journal"}, "“" + p.journal + "”",
                     el("small", {text: "Journal, round " + p.journal_round})) : null);
  }));
  if (!d.feed.length) {
    feed.replaceChildren(el("p", {class: "empty", text: "Nothing has happened yet. The first round starts with /rounds."}));
  } else {
    feed.replaceChildren(...d.feed.map(item => {
      if (item.kind === "round") return el("p", {class: "marker", text: "Round " + item.round + " begins: " + item.order.join(", then ")});
      if (item.kind === "round_end") return el("p", {class: "marker", text: "Round " + item.round + " ends" + (item.world_turn ? ", and the world turns" : "")});
      if (item.kind === "run") return el("p", {class: "marker", text: {pause: "Pause asked", resume: "Resumed", end: "End asked", ended: "The run ended"}[item.action]});
      const story = item.story ? el("details", {"data-key": item.key},
        el("summary", {text: "The story they were told"}),
        el("div", {class: "story"}, ...item.story.split(/\n\s*\n/).map(t => el("p", {text: t})))) : null;
      if (story) {
        if (opened.has(item.key)) story.open = true;
        story.addEventListener("toggle", () => story.open ? opened.add(item.key) : opened.delete(item.key));
      }
      return el("article", {class: "turn", style: "--who:" + (inkOf[item.name] || "var(--slate)")},
        el("p", {class: "who"}, item.name, el("span", {text: ", round " + item.round})),
        el("p", {class: "do", text: item.do}),
        item.journal ? el("p", {class: "why", text: item.journal}) : null,
        item.heard_by.length ? el("p", {class: "heard", text: "Heard by " + item.heard_by.join(" and ")}) : null,
        story || el("p", {class: "heard", text: "Their turn is still being played."}));
    }));
  }
  setButtons(d.run);
}

function setButtons(r) {
  const pause = document.getElementById("pause"), end = document.getElementById("end");
  pause.disabled = !r || r.ended || r.stop != null;
  end.disabled = !r || r.ended || r.stop === "end";
  pause.textContent = r && r.stop === "pause" ? "Pause asked" : "Pause after this round";
  end.textContent = r && (r.ended || r.stop === "end") ? (r.ended ? "Run ended" : "End asked") : "End the run";
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
