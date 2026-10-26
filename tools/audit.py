#!/usr/bin/env python3
"""Read a run back, as a review after it would:  python3 tools/audit.py [<log>] [--transcript <session> | --referee]

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
    CONTINUITY   what the referee kept for later rounds, per round (place notes, lines of the story so far, what the
                 town's people remember), and each minor townsperson whose file was read in a turn (as it is
                 before they're voiced) with nothing remembered of that turn
    MEMORY       each condensing: whose, which rounds, how many entries folded, what the think-back saw, and the
                 list of what they've learned as it stood after (left as it was, or cut at the limit, flagged); a
                 stretch stored twice is flagged
    COINS        every coin that moved, with its reason
    TRADES       each offer between people: who to whom, the terms, and how it ended (accepted, declined or lapsed,
                 and when); for one accepted, whether the coins moved under its id come to nothing either way
    CONTESTS     each grab at what another person held: who grabbed at whom, for what, each one's stat and total, and
                 who ended up with it
    OPTIONS      each person's options considered (the action entry's `options`): how many replies carried them,
                 how many options each, what the chosen one was for, and replies with none marked chosen or cut
    ENDINGS      each quest decided, and who heard of it
    VOICES       each call tools/voice.py made to a townsperson's agent or the world agent: the round, whose turn
                 (or no one's), the agent and what for, its model and effort, and whether it was asked again
    VERSIONS     each text that shaped what people read and answered (brief.md, thinkback.md, each cast entry, each
                 agent's instructions), by its version tag and the rounds it was used in; a text that changed partway
                 through the run is flagged, and so is a version whose whole text the log doesn't hold; and the exact
                 model version each nickname (sonnet, ...) answered on, flagged too if it changed partway
    SPEND        what the people's replies cost, by model (the `spend` tools/ask.py logs), and the townspeople's
                 and the world agent's calls (tools/voice.py)
From the referee's session transcript (~/.claude/projects/<folder>/<session>.jsonl), if given, or with --referee
from every round's session that tools/rounds.py ran (the log's `referee` entries), REFEREE then a line a round:
    CUT READS    rules commands piped through sed, head, tail or grep, or sent to /dev/null, by command
    SPAWNS       each agent spawned through the Agent tool, and whether its prompt holds what rpg.py printed for
                 it; an npc or world agent spawned so is a slip, since tools/voice.py asks them
    REFEREE      its calls, largest context and output tokens
It reads files and writes nothing.
"""
import collections
import json
import os
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


def told_text(e):
    """What a person reads of an entry: its text, and for a memory the list of what they've learned too."""
    return "\n".join([e.get("text", "")] + list(e.get("learned") or []))


def leaks(log):
    out, seen = [], set()
    for e in log:
        if e["kind"] not in TOLD:
            continue
        text = told_text(e)
        for m in FORBIDDEN.finditer(text):
            ctx = text[max(0, m.start() - 60):m.end() + 60].replace("\n", " ")
            if (e["kind"], ctx) in seen:  # a brief repeats what earlier ones held
                continue
            seen.add((e["kind"], ctx))
            out.append("  r%s %s %s %r: ...%s..." % (e["round"], e["player"], e["kind"], m.group(0), ctx))
    return out


WROTE = {"action": ("do", "journal", "options"), "memory": ("text", "learned"), "speech": ("text",)}  # what the people wrote themselves


def traces(log):
    """Signs of Claude Code's own lines in what the people wrote: each hit with its context, to read."""
    years = sorted({e["t"][:4] for e in log if str(e.get("t", ""))[:4].isdigit()})
    pattern = re.compile(r"\b(claude|anthropic|sonnet|haiku|opus|macos|darwin%s)\b|[\w.+-]+@[\w-]+(\.[\w-]+)+"
                         % "".join("|" + y for y in years), re.I)
    out, seen = [], set()
    for e in log:
        for field in WROTE.get(e["kind"], ()):
            text = e.get(field) or ""
            if field == "options":  # the options they weighed, one a line
                text = "\n".join("%s (for: %s)" % (o.get("text", ""), o.get("for") or "") for o in text)
            elif field == "learned":  # what they've learned, one a line
                text = "\n".join(text)
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


def continuity(log):
    kept = collections.OrderedDict()
    for e in log:
        if e["kind"] == "command" and not e["refused"] and e["command"] in ("note", "chronicle", "remember") and e.get("round"):
            kept.setdefault(e["round"], collections.Counter())[e["command"]] += 1
    out = ["  r%s: %d notes, %d story lines, %d remembered" % (r, c["note"], c["chronicle"], c["remember"]) for r, c in kept.items()]
    minor, shown, remembered = {}, {}, set()
    for e in log:
        if e["kind"] != "command" or e["refused"] or e.get("player") is None:
            continue
        turn = (e["round"], e["player"])
        for m in re.finditer(r"CHARACTERS HERE: (.*)", e["output"]):
            minor.setdefault(turn, set()).update(re.findall(r"([a-z0-9_]+) \[minor", m.group(1)))
        if e["command"] == "show" and e["args"][:1] == ["characters"] and len(e["args"]) > 1:
            shown.setdefault(turn, []).append(e["args"][1])
        if e["command"] == "remember" and e["args"]:
            remembered.add(turn + (e["args"][0],))
    for turn, ids in shown.items():
        for c in dict.fromkeys(ids):
            if c in minor.get(turn, ()) and turn + (c,) not in remembered:
                out.append("  r%s %s: %s (minor) spoken to, nothing remembered" % (turn[0], turn[1], c))
    return out or ["  nothing kept"]


def memory(log):
    out, stored = [], collections.Counter()
    for e in log:
        if e["kind"] == "memory":
            key = (e["player"], tuple(e["rounds"]))
            stored[key] += 1
            out.append("  r%s %s: rounds %s-%s, %s entries folded%s%s" % (e["round"], e["player"], e["rounds"][0], e["rounds"][1],
                                                                         e["replaced"], ", seeing " + e["sees"] if e.get("sees") else "",
                                                                         "  <<< stored again" if stored[key] > 1 else ""))
            if "learned" in e:
                out.append("    learned, %d%s%s" % (len(e["learned"]), " (left as it was)" if not e.get("learned_given", True) else "",
                                                     "  <<< cut at the limit" if e.get("learned_cut") else ""))
                out += ["      - " + x for x in e["learned"]]
    return out or ["  none"]


def coins(log):
    out = ["  r%s %s %+d (%s) -> %s" % (e["round"], e["player"], e["delta"], e.get("reason") or "NO REASON", e["balance"])
           for e in log if e["kind"] == "coins"]
    return out or ["  none moved"]


def trades(log):
    offers = collections.OrderedDict()
    for e in log:
        if e["kind"] == "trade":
            offers.setdefault(e["trade"], []).append(e)
    side = lambda s: ", ".join(s["items"] + (["%d coins" % s["coins"]] if s["coins"] else [])) or "nothing"  # noqa: E731
    out = []
    for tid, steps in offers.items():
        first, last = steps[0], steps[-1]
        how = "still open" if last["step"] == "offered" else "%s r%s%s" % (last["step"], last["round"], " (%s)" % last["why"] if last.get("why") else "")
        line = "  %s r%s %s -> %s: gives %s; wants %s: %s" % (tid, first["round"], first["offered_by"], first["to"], side(first["give"]), side(first["want"]), how)
        if last["step"] == "accepted":
            moved = sum(c["delta"] for c in log if c["kind"] == "coins" and c.get("reason") == "trade" and c.get("note") == tid)
            line += "" if moved == 0 else "  <<< coins don't balance (%+d)" % moved
        out.append(line)
    return out or ["  none"]


def contests(log):
    out = []
    for e in log:
        if e["kind"] == "contest":
            me, them = e["rolls"][e["player"]], e["rolls"][e["against"]]
            out.append("  r%s %s -> %s: %s, %s %d against %s %d: %s" % (
                e["round"], e["player"], e["against"], e["item"], me["stat"], me["total"], them["stat"], them["total"],
                "taken" if e["winner"] == e["player"] else "kept (a tie)" if me["total"] == them["total"] else "kept"))
    return out or ["  none"]


def options(log):
    """Each person's options considered: how many replies carried them and how many options each, the "for" of
    the one chosen each time, and replies with options but none marked chosen, or cut at the limit."""
    by = collections.OrderedDict()
    for e in log:
        if e["kind"] == "action":
            by.setdefault(e["player"], []).append(e)
    out = []
    for pid, acts in by.items():
        weighed = [a for a in acts if a.get("options")]
        if not weighed:
            continue
        counts = collections.Counter(len(a["options"]) for a in weighed)
        out.append("  %s: options in %d of %d replies (%s)" % (pid, len(weighed), len(acts), ", ".join(
            "%d options %dx" % (n, c) for n, c in sorted(counts.items()))))
        for a in weighed:
            chosen = [o for o in a["options"] if o.get("chosen")]
            line = "    r%s chose: %s" % (a["round"], "; ".join("%s (for: %s)" % (o["text"], o.get("for") or "-") for o in chosen)
                                          if chosen else "NONE MARKED")
            out.append(line + ("  <<< cut at the limit" if a.get("options_cut") else ""))
    return out or ["  none"]


def endings(log):
    out = ["  r%s: %s, heard by %s" % (e["round"], ", ".join("%s %s" % kv for kv in e["quests"].items()), ", ".join(e["heard_by"]) or "no one")
           for e in log if e["kind"] == "ending"]
    return out or ["  none"]


def voices(log):
    out = ["  r%s %s: %s agent for %s (%s%s)%s" % (e["round"], e["player"] or "no one", e["agent"], e["about"], e["model"],
                                              ", " + e["effort"] if e.get("effort") else "", ", asked again" if e.get("again") else "")
           for e in log if e["kind"] == "voice"]
    return out or ["  none"]


def versions(log):
    logged = {(e["name"], e["tag"]) for e in log if e["kind"] == "text"}
    used = collections.OrderedDict()
    for e in log:
        for name, tag in (e.get("versions") or {}).items():
            used.setdefault(name, collections.OrderedDict()).setdefault(tag, []).append(e.get("round") or 0)
        if e.get("exact_model"):  # the version a model's nickname named when it answered
            name = "model %s" % (e["model"] if e["kind"] != "voice" else "%s (%s agent)" % (e["model"], e["agent"]))
            used.setdefault(name, collections.OrderedDict()).setdefault(e["exact_model"], []).append(e.get("round") or 0)
    out = []
    for name, tags in used.items():
        line = "  %s: %s" % (name, ", then ".join("%s (r%d-%d)" % (t, min(r), max(r)) for t, r in tags.items()))
        if len(tags) > 1:
            line += "  <<< changed partway"
        missing = [t for t in tags if (name, t) not in logged and not name.startswith("model ")]
        if missing:
            line += "  <<< no text logged for %s" % ", ".join(missing)
        out.append(line)
    return out or ["  none recorded (a run from before the version record)"]


def spend(log):
    models = {e["player"]: e.get("model") for e in log if e["kind"] == "action"}
    total, n = collections.Counter(), collections.Counter()
    for e in log:
        if e["kind"] in ("action", "memory", "voice") and "spend" in e:
            m = "%s agent, %s" % (e["agent"], e["model"]) if e["kind"] == "voice" else e.get("model") or models.get(e["player"]) or "?"
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


RULES = re.compile(r"(rules/rpg\.py|tools/ask\.py|tools/voice\.py) ([a-z-]+)")
CUT = re.compile(r"\|\s*(sed|head|tail|grep)\b|>\s*/dev/null")


def session(path, log):
    """What one referee session did: (cut reads by command, spawn lines, calls, largest context, output tokens)."""
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
                kind = b["input"].get("subagent_type")
                spawns.append("  %s %s (%s): %s%s" % (r.get("timestamp", "")[11:19], kind, b["input"].get("model") or "its own model",
                                                      "holds what rpg.py printed" if holds else "<<< NOT what rpg.py printed",
                                                      "; <<< through the Agent tool, not tools/voice.py" if kind in ("npc", "world") else ""))
    return cut, spawns, calls, biggest, out_tokens


def cut_lines(cut):
    return ["  none"] if not cut else ["  %s: %d" % kv for kv in sorted(cut.items())]


def transcript(path, log):
    cut, spawns, calls, biggest, out_tokens = session(path, log)
    return cut_lines(cut), (spawns or ["  none"]), ["  %d calls; largest context %d tokens; %d output tokens" % (calls, biggest, out_tokens)]


def referee_sessions(log):
    """Every round's referee session from tools/rounds.py (the log's `referee` entries), read as one: cut reads and
    spawns over all of them, and a line a round, so whether the cost stays flat shows at a glance."""
    projects = Path(os.environ.get("CODERPG_PROJECTS") or Path.home() / ".claude" / "projects")  # the tests' stand-in
    cut, spawns, rounds = collections.Counter(), [], []
    for e in (e for e in log if e["kind"] == "referee"):
        found = sorted(projects.glob("*/%s.jsonl" % e["session"]))
        if not found:
            rounds.append("  r%s: $%.2f, %ds, context up to %d tokens; session %s not found" % (e["round_run"], e["spend"], e["seconds"], e["context"], e["session"]))
            continue
        c, s, calls, biggest, out_tokens = session(found[0], log)
        cut.update(c)
        spawns += ["  r%s%s" % (e["round_run"], line[1:]) for line in s]
        rounds.append("  r%s: $%.2f, %ds, %d calls, largest context %d tokens, %d output tokens" % (
            e["round_run"], e["spend"], e["seconds"], calls, biggest, out_tokens))
    return cut_lines(cut), (spawns or ["  none"]), (rounds or ["  no referee entries (rounds weren't run by tools/rounds.py)"])


def main(argv):
    path_t, by_round = None, "--referee" in argv
    argv = [a for a in argv if a != "--referee"]
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
                ("CONTINUITY", continuity(log)),
                ("MEMORY", memory(log)), ("COINS", coins(log)), ("TRADES", trades(log)), ("CONTESTS", contests(log)), ("OPTIONS", options(log)), ("ENDINGS", endings(log)),
                ("VOICES", voices(log)), ("VERSIONS", versions(log)), ("SPEND", spend(log))]
    if path_t:
        cut, spawns, referee = transcript(path_t, log)
        sections += [("CUT READS", cut), ("SPAWNS", spawns), ("REFEREE", referee)]
    elif by_round:
        cut, spawns, referee = referee_sessions(log)
        sections += [("CUT READS", cut), ("SPAWNS", spawns), ("REFEREE, A ROUND A LINE", referee)]
    rounds = max([e["round"] for e in log if isinstance(e.get("round"), int)] or [0])
    print("RUN %s: %d entries, %d rounds" % (path.stem, len(log), rounds))
    for title, lines in sections:
        print("== %s" % title)
        print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1:])
