#!/usr/bin/env python3
"""The cast generator: a person anywhere (an archetype, cast/<id>.json) made into that person in one world.

    cast.py make <world> <id> [--model <m>]
        asks one fresh call (rules/people/generate.md as its instructions, through `claude -p` under the owner's
        login, as tools/ask.py asks a person) for a full cast entry, from the archetype, the definitions of its traits
        (rules/people/defaults.json, with the world's people.json) and the world; checks what comes back (its shape,
        as `validate` holds a cast entry to; no word of the machinery; name, pronouns, voice and what they won't do
        the archetype's word for word; no number and no trait's line word for word in how they are), records what it
        was made with, and writes it to proposals/cast-<id>.json, with what failed, for the owner to read and edit.
        What the world's cast file already fixes for that person (home, coins, paid_beds, a `situation` line) is
        told to the generator as decided, and kept as given
    cast.py apply <world> <id>
        puts proposals/cast-<id>.json into games/<world>/cast.json in place of that person's entry (or beside the
        others), then runs `validate` on the world
    cast.py check <world> <id> [--proposal] [--archetype <a>] [--model <m>]
        the round-trip: shows a fresh call (rules/people/roundtrip.md) the Who I am note exactly as the brief would,
        has it rate the person on every trait from the note alone, and sets that beside the archetype's ratings,
        flagging any two or more apart; kept in bench/results/. The entry is the world's, or with --proposal the one
        waiting in proposals/; a hand-written entry names the archetype to compare with (--archetype)

Nothing here runs during a round: it's an authoring tool, like the forge. CODERPG_CLAUDE names another program in
place of `claude` (the tests use a stand-in).
"""
import datetime
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "rules"))
import ask  # noqa: E402  the one call everything is asked through
import audit  # noqa: E402  the tests' FORBIDDEN pattern
import rpg  # noqa: E402  the definitions, the archetypes, the note as the brief shows it

GENERATE = ROOT / "rules" / "people" / "generate.md"
ROUNDTRIP = ROOT / "rules" / "people" / "roundtrip.md"
PROPOSALS = ROOT / "proposals"
FLAG_APART = 2  # a reading this far from the archetype's rating is flagged


def take(args, flag):
    if flag not in args:
        return args, None
    i = args.index(flag)
    if i + 1 >= len(args):
        sys.exit("%s needs a value" % flag)
    return args[:i] + args[i + 2:], args[i + 1]


def setup(world, ident):
    if world not in rpg.content.list_games():
        sys.exit("no world called %s (%s)" % (world, ", ".join(rpg.content.list_games())))
    rpg.choose_game(world)
    arch = rpg.archetype(ident)
    if not arch:
        sys.exit("no archetype cast/%s.json" % ident)
    return arch, rpg.definitions()


def traits(arch, defs, every=False):
    """The archetype's ratings as lines: each trait's name, its low and high ends, and where they stand. Ordinary
    ratings only with `every`."""
    out, ordinary = [], defs["scale"]["ordinary"]
    for part in ("attributes", "ways"):
        for k, d in defs[part].items():
            n = arch[part][k]
            if every or n != ordinary:
                out.append("- %s: %d (1: %s; 5: %s)" % (d["name"], n, d["low"], d["high"]))
    return out


def world_text(world, ident):
    """The world as the generator needs it: its tone, what everyone knows, its places, people, things and money."""
    w = rpg.world()
    rooms = ["- %s: %s. %s" % (r, rpg.ent("rooms", r).get("name", r), rpg.ent("rooms", r)["body"].split("\n\n")[0].strip()[:240])
             for r in rpg.content.ids("rooms")]
    def trade(c):  # who makes things to order or builds places: a fact a person here may know
        ch = rpg.ent("characters", c)
        return "".join(x for x, k in (("; makes things to order", "makes"), ("; builds places", "builds")) if ch.get(k))
    people = ["- %s: %s, %s%s" % (c, rpg.ent("characters", c).get("name", c), rpg.ent("characters", c).get("role", ""), trade(c))
              for c in rpg.content.ids("characters")]
    things = ["- %s: %s" % (i, rpg.item(i).get("name", i)) for i in rpg.content.ids("items")]
    others = ["- %s: %s (%s)" % (e["id"], e.get("name", e["id"]), e.get("pronouns", "they/them"))  # a placeholder has no name yet
              for e in rpg.content.cast() if e.get("id") != ident]
    return "\n".join(["# The world: %s" % w.get("title", world), "", "## Its tone", rpg._section(w["body"], "Tone").strip(), "",
                      "## What everyone around here knows", rpg.public_knowledge() or "(nothing written)", "",
                      "## Money", "%s; people starting out here usually have about %s." % (rpg.currency(), w.get("coins", "a few")), "",
                      "## Places (id: name. what it is)"] + rooms + ["", "## People (id: name, role)"] + people
                     + ["", "## Things (id: name)"] + things + ["", "## The others in the cast (id: name)"] + (others or ["(none)"]))


SITUATION = ("home", "coins", "paid_beds", "situation")  # what the world's cast file may already fix for a person


def situation_of(ident):
    """What the world's cast file already fixes for this person (where they start, their money, nights paid for, a
    line on how they stand): kept as given in the made entry, and told to the generator to write around."""
    old = next((e for e in rpg.content.cast() if e.get("id") == ident), {})
    return {k: old[k] for k in SITUATION if k in old}


def situation_text(fixed):
    if not fixed:
        return []
    out = ["# Their situation here, already decided (keep it as given)"]
    if "home" in fixed:
        out.append("- They start in: %s (%s)" % (rpg.ent("rooms", fixed["home"]).get("name", fixed["home"]), fixed["home"]))
    if "coins" in fixed:
        out.append("- Their money: %d %s" % (fixed["coins"], rpg.currency()))
    for b in fixed.get("paid_beds") or []:
        out.append("- Already paid for: a bed at %s, %d night%s" % (rpg.ent("rooms", b["room"]).get("name", b["room"]), b["nights"],
                                                                    "" if b["nights"] == 1 else "s"))
    if fixed.get("situation"):
        out.append("- " + fixed["situation"])
    return out + [""]


def make_prompt(world, arch, defs, fixed=None):
    return "\n".join(["# Who they are anywhere", json.dumps({k: arch[k] for k in ("id", "name", "pronouns", "voice", "wants_and_needs",
                      "avoids_and_dislikes", "wont_do", "priorities")}, indent=2, ensure_ascii=False), "",
                      "# How they lean (1 to 5; %d is ordinary, and only the others are listed)" % defs["scale"]["ordinary"]]
                     + traits(arch, defs) + ["", world_text(world, arch["id"]), ""] + situation_text(fixed or {})
                     + ["Write their entry for this world."])


def read_entry(reply):
    """The JSON object in a reply (fenced or not), or None."""
    m = re.search(r"\{.*\}", reply, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except ValueError:
        return None


def entry_problems(world, entry, arch, defs):
    """What's wrong with a made entry: `validate`'s own checks on it (in a throwaway copy of the kit, the entry in
    place), the machinery's words, and the ratings showing through as numbers or the definitions' own lines."""
    out = []
    texts = [entry[k] for k in ("name", "voice", "backstory", "how_i_am", "look", "opening") if isinstance(entry.get(k), str)]  # the prose
    texts += [x for k in rpg.MADE_LISTS + ("knows",) for x in entry.get(k) or [] if isinstance(x, str)]
    texts += [p.get("how", "") for p in entry.get("people") or [] if isinstance(p, dict)]
    for text in texts:
        for m in audit.FORBIDDEN.finditer(text):
            out.append("a word of the machinery, %r: ...%s..." % (m.group(0), text[max(0, m.start() - 40):m.end() + 40]))
    how = str(entry.get("how_i_am", ""))
    if re.search(r"\d", how):
        out.append("how_i_am has a number in it")
    for part in ("attributes", "ways"):
        for d in defs[part].values():
            for line in (d["low"], d["high"]):
                if line.lower() in how.lower():
                    out.append("how_i_am has a trait's line word for word: %r" % line)
    d = Path(tempfile.mkdtemp(prefix="cast-"))
    try:
        for sub in ("rules", "games", "cast"):
            shutil.copytree(ROOT / sub, d / sub, ignore=shutil.ignore_patterns("__pycache__"))
        path = d / "games" / world / "cast.json"
        cast = [e for e in json.loads(path.read_text(encoding="utf-8")) if e.get("id") != entry.get("id")] + [entry]
        path.write_text(json.dumps(cast, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        r = subprocess.run([sys.executable, "rules/rpg.py", "validate", "--game", world], cwd=d, capture_output=True, text=True)
        out += [line.split(": ", 1)[1] for line in r.stdout.splitlines() if line.startswith(world + ": ") and "cast.json" in line]
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return out


def tags(arch, defs):
    return {"generate": rpg.text_tag(ask.instructions(GENERATE)), "definitions": rpg.text_tag(json.dumps(defs, sort_keys=True, ensure_ascii=False)),
            "archetype": rpg.text_tag(json.dumps(arch, sort_keys=True, ensure_ascii=False))}


def cmd_make(args):
    args, model = take(args, "--model")
    if len(args) != 2:
        sys.exit("usage: cast.py make <world> <id> [--model <m>]")
    world, ident = args
    arch, defs = setup(world, ident)
    fixed = situation_of(ident)
    try:
        reply, cost, exact = ask.call(model or "sonnet", make_prompt(world, arch, defs, fixed), GENERATE)
    except ask.Failed as e:
        sys.exit("MAKE FAILED: %s" % e)
    entry = read_entry(reply)
    PROPOSALS.mkdir(exist_ok=True)
    if not isinstance(entry, dict):
        (PROPOSALS / ("cast-%s.txt" % ident)).write_text(reply, encoding="utf-8")
        sys.exit("MAKE FAILED: the reply held no entry (kept as proposals/cast-%s.txt)" % ident)
    entry = dict({"id": ident, "archetype": ident}, **{k: v for k, v in entry.items() if k not in ("id", "archetype")})
    entry.update(fixed)  # what was already decided stays as it was, whatever the reply says
    entry["made_with"] = dict(tags(arch, defs), model=exact or model or "sonnet", cost=round(cost, 4),
                              when=datetime.datetime.now().isoformat(timespec="seconds"))
    problems = entry_problems(world, entry, arch, defs)
    (PROPOSALS / ("cast-%s.json" % ident)).write_text(json.dumps(entry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("MADE: %s for %s, in proposals/cast-%s.json ($%.3f, %s). Read it, edit it as you like, then `cast.py apply %s %s`."
          % (entry.get("name", ident), world, ident, cost, exact or model or "sonnet", world, ident))
    print("PROBLEMS:\n%s" % "\n".join("- " + p for p in problems) if problems else "PROBLEMS: none")
    return 1 if problems else 0


def cmd_apply(args):
    if len(args) != 2:
        sys.exit("usage: cast.py apply <world> <id>")
    world, ident = args
    source = PROPOSALS / ("cast-%s.json" % ident)
    if not source.is_file():
        sys.exit("nothing to apply: no proposals/cast-%s.json (cast.py make %s %s)" % (ident, world, ident))
    entry = json.loads(source.read_text(encoding="utf-8"))
    path = ROOT / "games" / world / "cast.json"
    cast = json.loads(path.read_text(encoding="utf-8"))
    at = next((i for i, e in enumerate(cast) if e.get("id") == ident), None)
    if at is None:
        cast.append(entry)
    else:
        cast[at] = entry
    path.write_text(json.dumps(cast, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    source.unlink()
    r = subprocess.run([sys.executable, "rules/rpg.py", "validate", "--game", world], cwd=ROOT, capture_output=True, text=True)
    print("APPLIED: %s's entry is in games/%s/cast.json.\n%s" % (ident, world, r.stdout.strip()))
    return r.returncode


def ratings_in(reply, ids):
    """{trait id: number} from a round-trip reply."""
    out = {}
    for m in re.finditer(r"^\s*[-*]?\s*([a-z_]+)\s*:\s*([1-5])\b", reply, re.M):
        if m.group(1) in ids:
            out[m.group(1)] = int(m.group(2))
    return out


def cmd_check(args):
    args, model = take(args, "--model")
    args, against = take(args, "--archetype")
    proposal = "--proposal" in args
    args = [a for a in args if a != "--proposal"]
    if len(args) != 2:
        sys.exit("usage: cast.py check <world> <id> [--proposal] [--archetype <a>] [--model <m>]")
    world, ident = args
    rpg.choose_game(world)
    if proposal:
        source = PROPOSALS / ("cast-%s.json" % ident)
        if not source.is_file():
            sys.exit("no proposals/cast-%s.json" % ident)
        entry = json.loads(source.read_text(encoding="utf-8"))
    else:
        entry = next((e for e in rpg.content.cast() if e.get("id") == ident), None)
        if not entry:
            sys.exit("%s has no %s in its cast" % (world, ident))
    arch, defs = setup(world, against or entry.get("archetype") or "")
    names = {e["id"]: e.get("name", e["id"]) for e in rpg.content.cast()}
    note = rpg.note_lines(entry, entry["name"], entry.get("pronouns") or "they/them",
                          lambda who: names.get(who) or rpg.ent("characters", who).get("name", who))
    ids = [k for part in ("attributes", "ways") for k in defs[part]]
    lines = ["- %s: 1 = %s; 5 = %s" % (k, d["low"], d["high"]) for part in ("attributes", "ways") for k, d in defs[part].items()]
    prompt = "\n".join(["# The note", "\n".join(note), "", "# The traits"] + lines)
    try:
        reply, cost, exact = ask.call(model or "sonnet", prompt, ROUNDTRIP)
    except ask.Failed as e:
        sys.exit("CHECK FAILED: %s" % e)
    read = ratings_in(reply, ids)
    rows, flagged = [], 0
    for part in ("attributes", "ways"):
        for k, d in defs[part].items():
            want, got = arch[part][k], read.get(k)
            far = got is None or abs(got - want) >= FLAG_APART
            flagged += far
            rows.append({"trait": k, "part": part, "archetype": want, "read": got, "flag": far})
    when = datetime.datetime.now().isoformat(timespec="seconds")
    record = {"when": when, "world": world, "person": ident, "entry": "proposal" if proposal else "cast.json", "archetype": arch["id"],
              "tags": tags(arch, defs), "roundtrip": rpg.text_tag(ask.instructions(ROUNDTRIP)), "model": exact or model or "sonnet",
              "cost": cost, "note": "\n".join(note), "reply": reply, "rows": rows}
    out = ROOT / "bench" / "results" / ("cast-check-%s-%s-%s.json" % (world, ident, when.replace(":", "-")))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("ROUND TRIP: %s in %s (%s), against cast/%s.json ($%.3f, %s)" % (entry["name"], world, record["entry"], arch["id"], cost, record["model"]))
    for r in rows:
        print("  %-18s %s  read %s%s" % (r["trait"], r["archetype"], "?" if r["read"] is None else r["read"], "   <<< " + (
            "not answered" if r["read"] is None else "%+d" % (r["read"] - r["archetype"])) if r["flag"] else ""))
    exact_hits = sum(1 for r in rows if r["read"] == r["archetype"])
    print("FLAGGED: %d of %d, %d or more apart; %d read exactly; kept in %s" % (flagged, len(rows), FLAG_APART, exact_hits, out.relative_to(ROOT)))
    return 0


def main(argv):
    commands = {"make": cmd_make, "apply": cmd_apply, "check": cmd_check}
    if not argv or argv[0] not in commands:
        sys.exit(__doc__)
    return commands[argv[0]](argv[1:]) or 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
