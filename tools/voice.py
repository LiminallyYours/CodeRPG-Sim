#!/usr/bin/env python3
"""The world's own people, and the world agent, answer outside the referee's context:

    voice.py npc <character> <file> --as <id>
        what a townsperson says: `rpg.py npc-brief <character>`, then the referee's file, which holds the scene's
        two parts under their headings, `## The scene so far` and `## What just happened`
    voice.py world <kind> [<maker>] [<file>] [--as <id>]
        what the world agent proposes: `rpg.py world-brief <kind> [<maker>]`, then the referee's file, if any (what
        the person said or did); its JSON is saved exactly as given to proposals/world-<kind>.json, for `generate`
        or `world-turn`
    voice.py world <kind> [<maker>] <file> --again [--as <id>]
        asks the world agent once more, after `generate` refused its proposal: the same brief as last time (from
        the log: world-brief isn't run again, so nothing is charged or asked for twice), then the file, which says
        what was refused and why

It prints only the reply, so the referee never holds the brief and nobody retypes it (in the long runs a referee
twice rewrote the briefs it spawned agents with). Each agent is asked as tools/ask.py asks a person: `claude -p`
under the owner's Claude Code login, with its own instructions (.claude/agents/<npc|world>.md without the front
matter) as the whole system prompt, the model and effort its front matter names, no tools, --safe-mode, from
/tmp/here. A call that fails is made once more with the same prompt; a second failure prints VOICE FAILED. A brief
that's refused (a minor character, someone not here, a kind of thing switched off) is printed as it came, and no
one is asked. Each call goes in the log (`rpg.py voiced`): the agent, who or what for, the model and effort, what
the referee added, the reply and what it cost. CODERPG_CLAUDE names another program in place of `claude`.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import ask  # noqa: E402  the one call an agent is asked through

AGENTS = ROOT / ".claude" / "agents"
SCENE = ("## The scene so far", "## What just happened")  # an npc's two parts after its brief, in the referee's file


def front_matter(agent):
    """The model and effort an agent's file names in its front matter."""
    m = re.match(r"^---\n(.*?)\n---\n", agent.read_text(encoding="utf-8"), re.S)
    fields = dict(re.findall(r"^(\w+):[ \t]*(.*?)[ \t]*$", m.group(1), re.M)) if m else {}
    return fields.get("model") or "sonnet", fields.get("effort") or None


def refuse(why):
    """Nothing asked: why, where the referee reads it (as rpg.py prints a REFUSED: line)."""
    print("VOICE REFUSED: %s" % why)
    sys.exit(1)


def take_actor(argv):
    """The arguments without `--as <id>`, and that id, or None (a world turn between rounds is no one's)."""
    if "--as" not in argv:
        return argv, None
    i = argv.index("--as")
    if i + 1 >= len(argv):
        refuse("--as needs a person's id")
    return argv[:i] + argv[i + 2:], argv[i + 1]


def last_brief(kind, maker):
    """What `world-brief <kind> [<maker>]` printed last in this run, from its log, or None."""
    try:
        run = json.loads((ROOT / "state" / "save.json").read_text())["run"]["id"]
        lines = (ROOT / "state" / "log" / ("%s.jsonl" % run)).read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError, KeyError):
        return None
    want = [kind] + ([maker] if maker else [])
    for line in reversed(lines):
        e = json.loads(line)
        if e.get("kind") == "command" and e.get("command") == "world-brief":
            return None if e["refused"] or e["args"] != want else e["output"]
    return None


def main(argv):
    argv, actor = take_actor(list(argv))
    again = "--again" in argv
    argv = [a for a in argv if a != "--again"]
    as_args = ["--as", actor] if actor else []
    if len(argv) < 2 or argv[0] not in ("npc", "world"):
        sys.exit(__doc__)
    agent, rest = argv[0], argv[1:]
    if agent == "npc":
        if len(rest) != 2 or again:
            sys.exit("usage: voice.py npc <character> <file> --as <id>")
        about, added_path, brief_cmd = rest[0], rest[1], ["npc-brief", rest[0]]
    else:
        kind, rest = rest[0], rest[1:]
        maker = rest.pop(0) if kind in ("craft", "build") and rest else None
        if kind in ("craft", "build") and not maker or len(rest) > 1 or (again and not rest):
            sys.exit("usage: voice.py world <kind> [<maker>] [<file>] [--again] [--as <id>]")
        about = kind + (" " + maker if maker else "")
        added_path, brief_cmd = (rest[0] if rest else None), ["world-brief", kind] + ([maker] if maker else [])
    added = ""
    if added_path:
        try:
            added = (ROOT / added_path).read_text(encoding="utf-8").strip()
        except OSError:
            refuse("no file %s (write it with the Write tool first)" % added_path)
    if agent == "npc" and not all(h in added for h in SCENE):
        refuse("%s needs both parts, under the headings %s and %s" % (added_path, SCENE[0], SCENE[1]))
    if again:
        brief = last_brief(kind, maker)
        if brief is None:
            refuse("there's no `world-brief %s` to ask about again: run voice.py without --again" % about)
    else:
        code, out = ask.rpg(*brief_cmd, *as_args)
        if code != 0:
            print(out, end="")
            return code
        brief = ask.printed(out)
    prompt = brief + ("\n\n" + added if added else "")
    file = AGENTS / ("%s.md" % agent)
    model, effort = front_matter(file)
    for attempt in (1, 2):
        try:
            reply, spend = ask.call(model, prompt, file, effort)
            break
        except ask.Failed as e:
            why = e
    else:
        print("VOICE FAILED: the %s agent for %s didn't answer, twice: %s" % (agent, about, why))
        return 1
    saved = None
    if agent == "world":
        saved = "proposals/world-%s.json" % kind
        (ROOT / saved).write_text(reply, encoding="utf-8")
    record = {"agent": agent, "about": about, "model": model, "effort": effort, "added": added, "again": again, "reply": reply}
    (ROOT / "proposals" / "voiced.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    code, out = ask.rpg("voiced", "proposals/voiced.json", "--spend", "%.6f" % spend, *as_args)
    if code != 0:
        print(out, end="")
        return code
    if saved:
        print("PROPOSAL from the world agent (%s), saved exactly as given to %s:" % (about, saved))
    else:
        print("REPLY from %s:" % about)
    print(reply)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
