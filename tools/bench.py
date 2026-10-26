#!/usr/bin/env python3
"""The bench: put fixed moments to the people again, cheaply, before a change goes into a run.

    bench.py add <name> <log> <person> <round> [--thinkback] [--edited <file>] [--game <id>] [--note <why>]
        keep a past moment as a fixed brief: the brief exactly as that run's log holds it for that person in that
        round (the last one, if there were several), or, with --edited, a copy of it changed by hand (the Hobb
        test's added "What I know"), kept as such. Only the instructions can vary for it: the page is frozen as
        it was, so changes to the brief itself (new sections, other wording) don't show on it. With --thinkback,
        the moment is their thinking back instead: the stretch of moments `memory condense` showed them in that
        round (or, with --edited, a stretch changed by hand), kept as it was, while the rest of the think-back
        (who they are, the wording of rules/people/thinkback.md) is built afresh each run, with nothing learned
        yet; asked as tools/ask.py --memory asks it
    bench.py save <name> <person> [--from <save.json>] [--note <why>]
        keep a moment as a saved game: the save as it stands (this folder's, or another's with --from) and whose
        turn it is. Its brief is rebuilt with the current code and wording every time it's run, so it shows every
        kind of change
    bench.py list
        the moments kept, with their kind and note
    bench.py run [<name> ...] [--variant <instructions file>] ... [--times <n>] [--dry]
        ask each moment (all of them if none is named), under each variant (default: .claude/agents/player.md,
        today's instructions; a variant is a file like it, front matter optional), <n> times each (default 3),
        exactly as tools/ask.py asks a person: `claude -p` under the owner's login, the model the moment's game
        sets (cast.model), the variant's instructions as the whole system prompt, no tools, from /tmp/here. It
        prints each moment's replies side by side, by variant, with what they cost; keeps everything in
        bench/results/<when>.json (each brief's and variant's version tag, each reply, its cost and exact model);
        and runs the audit's leak check over the briefs and its check for Claude Code's lines over the replies.
        --dry builds the briefs and prints them, and asks no one.

Moments live in bench/moments/<name>.json and variants in bench/variants/, both in git: they're part of the
instrument. Nothing here writes the game's own save or log: a saved game's brief is rebuilt in a throwaway copy.
CODERPG_CLAUDE names another program in place of `claude` (the tests use a stand-in).
"""
import concurrent.futures
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
import ask  # noqa: E402  the one call a person is asked through
import audit  # noqa: E402  the leak check and the check for Claude Code's lines
import rpg  # noqa: E402  the settings: which model a moment's game asks people on

BENCH = ROOT / "bench"
MOMENTS = BENCH / "moments"
RESULTS = BENCH / "results"
TODAY = ask.AGENT  # today's instructions, the default variant


def take(args, flag, many=False):
    """The arguments without `flag <value>` (every one of them if `many`), and the value(s)."""
    values, rest, i = [], [], 0
    while i < len(args):
        if args[i] == flag:
            if i + 1 >= len(args):
                sys.exit("%s needs a value" % flag)
            values.append(args[i + 1])
            i += 2
        else:
            rest.append(args[i])
            i += 1
    if not many and len(values) > 1:
        sys.exit("%s is given once" % flag)
    return rest, (values if many else (values[0] if values else None))


def write_moment(name, moment):
    if not name.replace("-", "").replace("_", "").isalnum():
        sys.exit("a moment's name is letters, digits, - and _")
    MOMENTS.mkdir(parents=True, exist_ok=True)
    (MOMENTS / ("%s.json" % name)).write_text(json.dumps(moment, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("KEPT %s: %s, %s" % (name, moment["person"], moment["from"]))


def cmd_add(args):
    args, game = take(args, "--game")
    args, note = take(args, "--note")
    args, edited = take(args, "--edited")
    thinkback = "--thinkback" in args
    args = [a for a in args if a != "--thinkback"]
    if len(args) != 4 or not args[3].isdigit():
        sys.exit("usage: bench.py add <name> <log> <person> <round> [--thinkback] [--edited <file>] [--game <id>] [--note <why>]")
    name, log, person, number = args[0], Path(args[1]), args[2], int(args[3])
    entries = audit.read_jsonl(log)
    if thinkback:  # the stretch `memory condense <person>` showed them, when it had one to fold
        briefs = [stretch_of(e["output"]) for e in entries if e["kind"] == "command" and e.get("command") == "memory" and not e.get("refused")
                  and e.get("args", [])[:2] == ["condense", person] and e.get("round") == number and "### Moment" in e.get("output", "")]
    else:
        briefs = [e["text"] for e in entries if e["kind"] == "brief" and e.get("player") == person and e.get("round") == number]
    if not briefs:
        sys.exit("%s has no %s for %s in round %d" % (log, "think-back" if thinkback else "brief", person, number))
    game = game or rpg.read_json(rpg.ACTIVE).get("game")
    text = Path(edited).read_text(encoding="utf-8").rstrip("\n") if edited else briefs[-1]
    write_moment(name, {"kind": "thinkback" if thinkback else "brief", "person": person, "game": game, "note": note or "",
                        "stretch" if thinkback else "brief": text,
                        "from": "%s, round %d%s" % (log.stem, number, ", edited by hand" if edited else "")})


def stretch_of(prompt):
    """The moments in a think-back as printed: what follows "## That stretch", up to the next section."""
    if "## That stretch\n" not in prompt:
        sys.exit("that think-back has no stretch of moments")
    return re.split(r"\n\n(?:## |Reply with)", prompt.split("## That stretch\n", 1)[1], maxsplit=1)[0]


def cmd_save(args):
    args, source = take(args, "--from")
    args, note = take(args, "--note")
    if len(args) != 2:
        sys.exit("usage: bench.py save <name> <person> [--from <save.json>] [--note <why>]")
    path = Path(source) if source else ROOT / "state" / "save.json"
    save = json.loads(path.read_text(encoding="utf-8"))
    if args[1] not in save.get("players", {}):
        sys.exit("%s isn't in that save (%s)" % (args[1], ", ".join(save.get("players", {}))))
    write_moment(args[0], {"kind": "save", "person": args[1], "game": save["game"],
                           "from": "%s, round %s" % (save["run"].get("seed") or save["run"]["id"], save["run"].get("round")),
                           "note": note or "", "save": save})


def moments(names):
    found = sorted(MOMENTS.glob("*.json")) if MOMENTS.is_dir() else []
    if names:
        missing = [n for n in names if not (MOMENTS / ("%s.json" % n)).is_file()]
        if missing:
            sys.exit("no moment called %s (bench.py list)" % ", ".join(missing))
        found = [MOMENTS / ("%s.json" % n) for n in names]
    return [(p.stem, json.loads(p.read_text(encoding="utf-8"))) for p in found]


def cmd_list(args):
    for name, m in moments([]):
        print("%-24s %-6s %-10s %s%s" % (name, KINDS[m["kind"]], m["person"], m["from"], " (%s)" % m["note"] if m["note"] else ""))


KINDS = {"brief": "frozen", "save": "saved", "thinkback": "think"}


def thinkback_brief(m):
    """A kept stretch's think-back, built afresh around it: who they are now, the current wording, nothing learned."""
    rpg.choose_game(m["game"])
    state = {"players": {e["id"]: {"name": e["name"], "learned": list(m.get("learned", [])) if e["id"] == m["person"] else []}
                         for e in rpg.content.cast()}}
    return rpg.thinkback_prompt(state, m["person"], m["stretch"])


def rebuilt_brief(m):
    """A saved game's brief, built afresh by the current code and wording, in a throwaway copy of the kit."""
    d = Path(tempfile.mkdtemp(prefix="bench-"))
    try:
        for sub in ("rules", "games"):
            shutil.copytree(ROOT / sub, d / sub, ignore=shutil.ignore_patterns("__pycache__"))
        (d / "state").mkdir()
        (d / "state" / "save.json").write_text(json.dumps(m["save"], ensure_ascii=False))
        (d / "state" / "active.json").write_text(json.dumps({"game": m["game"]}))
        r = subprocess.run([sys.executable, "rules/rpg.py", "brief", m["person"]], cwd=d, capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit("the saved moment's brief couldn't be built: %s" % (r.stdout + r.stderr).strip())
        return ask.printed(r.stdout)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def model_for(m):
    """The model the moment's game asks this person on, as the settings stand now."""
    rpg.choose_game(m["game"])
    setting = rpg.SETTINGS["cast"]["model"]
    if setting != "own":
        return setting
    entry = next((e for e in rpg.content.cast() if e.get("id") == m["person"]), {})
    return entry.get("model") or "sonnet"


def reply_forms(chosen, files, label, replies):
    """A line per moment and variant: how many replies `reply` would take, how many carried options and how many
    options each, and how many marked the one chosen."""
    out = []
    for name, m in chosen:
        for f in files:
            mine = [r for r in replies if r["moment"] == name and r["variant"] == label[f]]
            if m["kind"] == "thinkback":  # as `memory store` would read it: a MEMORY line, and what they learned
                read = [rpg.parse_thinkback(r["reply"]) for r in mine]
                out.append("  %s, %s: a memory in %d of %d; things learned in each: %s" % (
                    name, label[f], sum(1 for x in read if x[0]), len(mine),
                    ", ".join("-" if x[1] is None else str(len(x[1])) for x in read) or "-"))
                continue
            read = []
            for r in mine:
                try:
                    read.append(rpg.parse_reply(r["reply"]))
                except rpg.Refused:
                    pass
            weighed = [x for x in read if x["options"]]
            out.append("  %s, %s: %d of %d taken; options in %d (%s); one marked chosen in %d%s" % (
                name, label[f], len(read), len(mine), len(weighed), ", ".join(str(len(x["options"])) for x in weighed) or "-",
                sum(1 for x in weighed if sum(o["chosen"] for o in x["options"]) == 1),
                "; no longer holds, in %d (%s)" % (sum(1 for x in read if x["no_longer"]), ", ".join(str(len(x["no_longer"])) for x in read))
                if any(x["no_longer"] for x in read) else ""))
    return out


def cmd_run(args):
    args, variants = take(args, "--variant", many=True)
    args, times = take(args, "--times")
    dry = "--dry" in args
    args = [a for a in args if a != "--dry"]
    times = int(times) if times and times.isdigit() and int(times) > 0 else 3
    files = [Path(v) if Path(v).is_absolute() else ROOT / v for v in variants] or [TODAY]
    for f in files:
        if not f.is_file():
            sys.exit("no instructions file %s" % f)
    chosen = moments(args)
    if not chosen:
        sys.exit("no moments kept yet (bench.py add, bench.py save)")
    build = {"brief": lambda m: m["brief"], "save": rebuilt_brief, "thinkback": thinkback_brief}
    briefs = {name: build[m["kind"]](m) for name, m in chosen}
    if dry:
        for name, m in chosen:
            print("===== %s (%s, %s)\n%s\n" % (name, m["person"], "frozen" if m["kind"] == "brief" else "rebuilt now", briefs[name]))
        return 0
    label = {f: (f.stem if f != TODAY else "today") for f in files}
    jobs = [(name, m, f, n) for name, m in chosen for f in files for n in range(1, times + 1)]

    def one(job):
        name, m, f, n = job
        try:
            reply, cost, exact = ask.call(model_for(m), briefs[name], f)
        except ask.Failed as e:
            reply, cost, exact = "(no answer: %s)" % e, 0.0, None
        return {"moment": name, "variant": label[f], "n": n, "reply": reply, "cost": cost, "exact_model": exact}

    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        replies = list(ex.map(one, jobs))
    when = datetime.datetime.now().isoformat(timespec="seconds")
    record = {"when": when, "times": times,
              "variants": {label[f]: {"file": str(f.relative_to(ROOT)) if f.is_relative_to(ROOT) else str(f),
                                      "tag": rpg.text_tag(ask.instructions(f))} for f in files},
              "moments": {name: {"kind": m["kind"], "person": m["person"], "from": m["from"], "model": model_for(m),
                                 "brief_tag": rpg.text_tag(briefs[name])} for name, m in chosen},
              "replies": replies}
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / ("%s.json" % when.replace(":", "-"))
    out.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for name, m in chosen:
        print("===== %s: %s, %s (%s; %s)" % (name, m["person"], m["from"], {"brief": "frozen brief", "save": "brief rebuilt now",
                                                                         "thinkback": "think-back rebuilt now"}[m["kind"]],
                                            record["moments"][name]["model"]))
        for f in files:
            mine = [r for r in replies if r["moment"] == name and r["variant"] == label[f]]
            print("--- %s (instructions %s), $%.3f" % (label[f], record["variants"][label[f]]["tag"], sum(r["cost"] for r in mine)))
            for r in mine:
                print("  %d. %s" % (r["n"], r["reply"].strip().replace("\n", "\n     ")))
    log = [{"kind": "brief", "text": briefs[name], "round": 0, "player": m["person"], "t": when} for name, m in chosen]
    log += [{"kind": "action", "do": r["reply"], "journal": "", "round": 0, "player": r["moment"], "t": when} for r in replies]
    print("== LEAKS IN THE BRIEFS\n%s" % "\n".join(audit.leaks(log) or ["  none"]))
    print("== SIGNS OF CLAUDE CODE'S LINES IN THE REPLIES\n%s" % "\n".join(audit.traces(log)))
    print("== THE REPLY FORM (as `rpg.py reply` would read it)\n%s" % "\n".join(reply_forms(chosen, files, label, replies)))
    print("BENCH: %d replies, $%.2f; kept in %s" % (len(replies), sum(r["cost"] for r in replies), out.relative_to(ROOT)))
    return 0


def main(argv):
    commands = {"add": cmd_add, "save": cmd_save, "list": cmd_list, "run": cmd_run}
    if not argv or argv[0] not in commands:
        sys.exit(__doc__)
    return commands[argv[0]](argv[1:]) or 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
