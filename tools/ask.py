#!/usr/bin/env python3
"""A person in the cast answers, outside the referee's context:  python3 tools/ask.py <id> [--memory]

    ask.py <id>             their turn: `rpg.py brief <id>` goes to them unchanged, and their reply is stored
                            with `rpg.py reply`
    ask.py <id> --memory    their thinking back: `rpg.py memory condense <id>`, then `rpg.py memory store`

It prints only what `reply` (or `memory store`) prints, so the referee never holds a brief: a brief is handed on
exactly as printed because nobody retypes it. The person is `claude -p` under the owner's Claude Code login, with
the model the cast gives them, the player agent's instructions as the whole system prompt, no tools, and
`--safe-mode`, which keeps out CLAUDE.md, skills, plugins, hooks (the meter's SessionStart would refill it) and
MCP servers. A refused reply is asked for once more with the same text, as the rounds procedure says. Each
reply's cost goes in the log with it (`--spend`). CODERPG_CLAUDE names another program in place of `claude`
(the tests use a stand-in).
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT = ROOT / ".claude" / "agents" / "player.md"


def rpg(*args):
    r = subprocess.run([sys.executable, str(ROOT / "rules" / "rpg.py"), *args], cwd=ROOT, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def instructions():
    """The player agent's instructions: player.md without its front matter, the one source for them."""
    text = AGENT.read_text(encoding="utf-8")
    m = re.match(r"^---\n.*?\n---\n", text, re.S)
    return (text[m.end():] if m else text).strip()


def model_of(pid):
    """Their model, from the CAST: line of `run status`."""
    _, out = rpg("run", "status")
    m = re.search(r"\(%s, ([a-z0-9.-]+)" % re.escape(pid), out)
    if not m:
        sys.exit("ASK FAILED: %s isn't in the cast\n%s" % (pid, out.strip()))
    return m.group(1)


def ask(model, prompt):
    """Their answer to `prompt`, exactly as given, and what it cost."""
    cmd = [os.environ.get("CODERPG_CLAUDE", "claude"), "-p", "--safe-mode", "--tools", "", "--no-session-persistence",
           "--output-format", "json", "--model", model, "--system-prompt", instructions()]
    try:
        r = subprocess.run(cmd, cwd=ROOT, input=prompt, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as e:
        sys.exit("ASK FAILED: %s" % e)
    try:
        out = json.loads(r.stdout)
    except ValueError:
        out = {}
    if r.returncode != 0 or out.get("is_error") or not isinstance(out.get("result"), str):
        sys.exit("ASK FAILED: the answer didn't come (exit %d)\n%s" % (r.returncode, (r.stdout + r.stderr).strip()[-600:]))
    return out["result"], float(out.get("total_cost_usd") or 0)


def printed(out):
    """What rpg.py printed, with the one newline print adds taken off: the text exactly as it would be handed on."""
    return out[:-1] if out.endswith("\n") else out


def main(argv):
    if not argv or argv[0].startswith("-"):
        sys.exit(__doc__)
    pid, memory = argv[0], "--memory" in argv[1:]
    model = model_of(pid)
    code, out = rpg("memory", "condense", pid) if memory else rpg("brief", pid)
    if code != 0 or out.startswith("NOTHING TO CONDENSE"):
        print(out, end="")
        return code
    prompt = printed(out)
    path = "proposals/%s-%s.txt" % ("memory" if memory else "reply", pid)
    for attempt in (1, 2):
        answer, spend = ask(model, prompt)
        (ROOT / path).write_text(answer, encoding="utf-8")
        store = ("memory", "store", pid) if memory else ("reply", pid)
        code, out = rpg(*store, path, "--spend", "%.6f" % spend)
        if code == 0:
            print(out, end="")
            return 0
        if memory and "has changed since" in out:  # condense again, and ask about what is due now
            code, again = rpg("memory", "condense", pid)
            if code != 0 or again.startswith("NOTHING TO CONDENSE"):
                print(again, end="")
                return code
            prompt = printed(again)
    print(out, end="")
    print("ASK FAILED: %s's %s was refused twice" % (pid, "memory" if memory else "reply"))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
