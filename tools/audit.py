#!/usr/bin/env python3
"""Read a run back, as a review after it would:  python3 tools/audit.py [<log>] [--transcript <referee session>]

From the run's log (state/log/<run>.jsonl; the active run's by default):
    LEAKS        the tests' FORBIDDEN pattern over every brief, story, spoken line, memory, note and ending:
                 each hit with its context, to read by eye (ordinary English trips it too)
    SIGNS OF CLAUDE CODE'S LINES
                 in what the people wrote themselves (DO and JOURNAL lines, memories, spoken words): the year the
                 run took place in, Claude, Anthropic, Sonnet, Haiku, Opus, macOS, darwin, or an email address.
                 Claude Code adds lines to every person's call that can't be kept out (tools/probe.py shows them);
                 these are their traces. A hit is something to read, not proof ("Haiku" may be a poem)
    WITNESSED    each turn with someone else there, against its onlookers' note, and the flags they learned
    FLAGS        each person's own flags, from the save if it is this run's
    MEMORY       each condensing: whose, which rounds, how many entries folded; a stretch stored twice is flagged
    COINS        every coin that moved, with its reason
    ENDINGS      each quest decided, and who heard of it
    SPEND        what the people's replies cost, by model (the `spend` tools/ask.py logs)
From the referee's session transcript (~/.claude/projects/<folder>/<session>.jsonl), if given:
    CUT READS    rules commands piped through sed, head, tail or grep, or sent to /dev/null, by command
    SPAWNS       each agent spawned, and whether its prompt holds what rpg.py printed for it
    REFEREE      its calls, largest context and output tokens
It reads files and writes nothing.
"""
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from test_rules import Engine  # noqa: E402  the one FORBIDDEN pattern, the tests'

FORBIDDEN = Engine.FORBIDDEN
TOLD = ("brief", "narration", "speech", "memory", "witnessed", "ending")  # what the people read


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def leaks(log):
    out, seen = [], set()
    for e in log:
        if e["kind"] not in TOLD:
            continue
        for m in FORBIDDEN.finditer(e.get("text", "")):
            ctx = e["text"][max(0, m.start() - 60):m.end() + 60].replace("\n", " ")
            if (e["kind"], ctx) in seen:  # a brief repeats what earlier ones held
                continue
            seen.add((e["kind"], ctx))
            out.append("  r%s %s %s %r: ...%s..." % (e["round"], e["player"], e["kind"], m.group(0), ctx))
    return out


WROTE = {"action": ("do", "journal"), "memory": ("text",), "speech": ("text",)}  # what the people wrote themselves


def traces(log):
    """Signs of Claude Code's own lines in what the people wrote: each hit with its context, to read."""
    years = sorted({e["t"][:4] for e in log if str(e.get("t", ""))[:4].isdigit()})
    pattern = re.compile(r"\b(claude|anthropic|sonnet|haiku|opus|macos|darwin%s)\b|[\w.+-]+@[\w-]+(\.[\w-]+)+"
                         % "".join("|" + y for y in years), re.I)
    out, seen = [], set()
    for e in log:
        for field in WROTE.get(e["kind"], ()):
            text = e.get(field) or ""
            for m in pattern.finditer(text):
                ctx = text[max(0, m.start() - 60):m.end() + 60].replace("\n", " ")
                if (e["kind"], field, m.group(0), ctx) in seen:  # a memory may repeat a journal line
                    continue
                seen.add((e["kind"], field, m.group(0), ctx))
                out.append("  r%s %s %s %r: ...%s..." % (e["round"], e["player"], field if e["kind"] == "action" else e["kind"], m.group(0), ctx))
    return out or ["  none"]


def turns(log):
    """{(round, player): what the turn's commands showed}, in the order the turns came."""
    out = collections.OrderedDict()
    for e in log:
        if e.get("round") is None or e.get("player") is None:
            continue
        t = out.setdefault((e["round"], e["player"]), {"people": set(), "notes": []})
        if e["kind"] == "command" and not e["refused"]:
            for m in re.finditer(r"PEOPLE HERE: (.*?)\. Each acts", e["output"]):
                t["people"].update(re.findall(r"\(([a-z0-9_]+)[,)]", m.group(1)))
        elif e["kind"] == "witnessed":
            t["notes"].append((e["seen_by"], e["learned"]))
    return out


def witnessed(log):
    out, with_people, noted = [], 0, 0
    for (rnd, pid), t in turns(log).items():
        if t["people"]:
            with_people += 1
        noted += bool(t["notes"])
        problem = ("no note" if t["people"] and not t["notes"] else "%d notes" % len(t["notes"]) if len(t["notes"]) > 1
                   else "a note with no one there" if t["notes"] and not t["people"] else "")
        learned = [f for _, fl in t["notes"] for f in fl]
        if problem or learned:
            out.append("  r%s %s: %s%s" % (rnd, pid, problem or "ok", "; learned %s" % ", ".join(learned) if learned else ""))
    return ["  %d turns with someone else there, %d with a note" % (with_people, noted)] + out


def memory(log):
    out, stored = [], collections.Counter()
    for e in log:
        if e["kind"] == "memory":
            key = (e["player"], tuple(e["rounds"]))
            stored[key] += 1
            out.append("  r%s %s: rounds %s-%s, %s entries folded%s" % (e["round"], e["player"], e["rounds"][0], e["rounds"][1],
                                                                       e["replaced"], "  <<< stored again" if stored[key] > 1 else ""))
    return out or ["  none"]


def coins(log):
    out = ["  r%s %s %+d (%s) -> %s" % (e["round"], e["player"], e["delta"], e.get("reason") or "NO REASON", e["balance"])
           for e in log if e["kind"] == "coins"]
    return out or ["  none moved"]


def endings(log):
    out = ["  r%s: %s, heard by %s" % (e["round"], ", ".join("%s %s" % kv for kv in e["quests"].items()), ", ".join(e["heard_by"]) or "no one")
           for e in log if e["kind"] == "ending"]
    return out or ["  none"]


def spend(log):
    models = {e["player"]: e.get("model") for e in log if e["kind"] == "action"}
    total, n = collections.Counter(), collections.Counter()
    for e in log:
        if e["kind"] in ("action", "memory") and "spend" in e:
            m = e.get("model") or models.get(e["player"]) or "?"
            total[m] += e["spend"]
            n[m] += 1
    if not n:
        return ["  none logged (replies didn't come through tools/ask.py)"]
    return ["  %s: %d replies, $%.2f" % (m, n[m], total[m]) for m in sorted(n)] + ["  all: $%.2f" % sum(total.values())]


def flags(run_id):
    try:
        state = json.loads((ROOT / "state" / "save.json").read_text())
    except (OSError, ValueError):
        return ["  no save to read"]
    if state.get("run", {}).get("id") != run_id:
        return ["  the save isn't this run's"]
    return ["  shared: %s" % (", ".join(state["flags"]) or "none")] + [
        "  %s: %s" % (pid, ", ".join(pl.get("flags", [])) or "none") for pid, pl in state["players"].items()]


RULES = re.compile(r"(rules/rpg\.py|tools/ask\.py) ([a-z-]+)")
CUT = re.compile(r"\|\s*(sed|head|tail|grep)\b|>\s*/dev/null")


def transcript(path, log):
    rows = [r for r in read_jsonl(path) if not r.get("isSidechain")]
    cut, spawns, seen, calls, biggest, out_tokens = collections.Counter(), [], set(), 0, 0, 0
    printed = [e["output"] for e in log if e["kind"] == "command" and e["command"] in ("npc-brief", "world-brief", "brief", "memory")]
    printed += [e["text"] for e in log if e["kind"] == "brief"]
    for r in rows:
        if r.get("type") != "assistant":
            continue
        msg = r["message"]
        if msg.get("id") not in seen:
            seen.add(msg.get("id"))
            u = msg.get("usage") or {}
            calls += 1
            biggest = max(biggest, sum(u.get(k, 0) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")))
            out_tokens += u.get("output_tokens", 0) or 0
        for b in msg.get("content") or []:
            if b.get("type") != "tool_use":
                continue
            if b["name"] == "Bash":
                for piece in re.split(r"&&|;", b["input"].get("command", "")):
                    m = RULES.search(piece)
                    if m and CUT.search(piece):
                        cut[m.group(2)] += 1
            elif b["name"] in ("Agent", "Task"):
                prompt = b["input"].get("prompt", "")
                holds = any(p.strip() and p.strip() in prompt for p in printed)
                spawns.append("  %s %s (%s): %s" % (r.get("timestamp", "")[11:19], b["input"].get("subagent_type"),
                                                    b["input"].get("model") or "its own model",
                                                    "holds what rpg.py printed" if holds else "<<< NOT what rpg.py printed"))
    return (["  none"] if not cut else ["  %s: %d" % kv for kv in sorted(cut.items())]), (spawns or ["  none"]), [
        "  %d calls; largest context %d tokens; %d output tokens" % (calls, biggest, out_tokens)]


def main(argv):
    path_t = None
    if "--transcript" in argv:
        i = argv.index("--transcript")
        path_t = argv[i + 1] if i + 1 < len(argv) else sys.exit("--transcript needs a file")
        argv = argv[:i] + argv[i + 2:]
    if argv:
        path = Path(argv[0])
    else:
        try:
            path = ROOT / "state" / "log" / ("%s.jsonl" % json.loads((ROOT / "state" / "save.json").read_text())["run"]["id"])
        except (OSError, ValueError, KeyError):
            sys.exit("no active run: name a log")
    log = read_jsonl(path)
    sections = [("LEAKS", leaks(log) or ["  none"]), ("SIGNS OF CLAUDE CODE'S LINES", traces(log)), ("WITNESSED", witnessed(log)), ("FLAGS", flags(path.stem)),
                ("MEMORY", memory(log)), ("COINS", coins(log)), ("ENDINGS", endings(log)), ("SPEND", spend(log))]
    if path_t:
        cut, spawns, referee = transcript(path_t, log)
        sections += [("CUT READS", cut), ("SPAWNS", spawns), ("REFEREE", referee)]
    rounds = max([e["round"] for e in log if isinstance(e.get("round"), int)] or [0])
    print("RUN %s: %d entries, %d rounds" % (path.stem, len(log), rounds))
    for title, lines in sections:
        print("== %s" % title)
        print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1:])
