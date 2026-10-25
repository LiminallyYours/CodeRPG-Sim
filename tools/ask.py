#!/usr/bin/env python3
"""A person in the cast answers, outside the referee's context:  python3 tools/ask.py <id> [--memory]

    ask.py <id>             their turn: `rpg.py brief <id>` goes to them unchanged, and their reply is stored
                            with `rpg.py reply`
    ask.py <id> --memory    their thinking back: `rpg.py memory condense <id>`, then `rpg.py memory store`

It prints only what `reply` (or `memory store`) prints, so the referee never holds a brief: a brief is handed on
exactly as printed because nobody retypes it. The person is `claude -p` under the owner's Claude Code login, with
the model the cast gives them, the player agent's instructions as the whole system prompt (named to `rpg.py`, for the
version record its log entries carry), no tools, and
`--safe-mode`, which keeps out CLAUDE.md, skills, plugins, hooks (the meter's SessionStart would refill it) and
MCP servers, asked from a plain folder outside this one (NEUTRAL), since Claude Code tells them the folder it runs in.
Claude Code still adds its own lines (a billing line, "a Claude agent", the owner's email, an environment note with
the folder, platform, model and date): a known limit (DEVELOPING.md, Known limits; tools/probe.py shows them). A
refused reply is asked for once more with the same text, as the rounds procedure says. Each
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
NEUTRAL = Path("/tmp/here")  # where a person is asked from: its path names neither this folder nor the owner


def rpg(*args):
    r = subprocess.run([sys.executable, str(ROOT / "rules" / "rpg.py"), *args], cwd=ROOT, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


class Failed(Exception):
    """The answer didn't come."""


def instructions(agent=AGENT):
    """An agent's instructions: its file (player.md for a person) without its front matter, the one source for them."""
    text = agent.read_text(encoding="utf-8")
    m = re.match(r"^---\n.*?\n---\n", text, re.S)
    return (text[m.end():] if m else text).strip()


def model_in(status, pid):
    """Their model, from the CAST: line of `run status`'s output, or None."""
    m = re.search(r"\(%s, ([a-z0-9.-]+)" % re.escape(pid), status)
    return m.group(1) if m else None


def model_of(pid):
    _, out = rpg("run", "status")
    model = model_in(out, pid)
    if not model:
        sys.exit("ASK FAILED: %s isn't in the cast\n%s" % (pid, out.strip()))
    return model


def neutral_folder():
    """NEUTRAL, made if missing. Refused if it's inside a git repository, whose name would come with it."""
    NEUTRAL.mkdir(parents=True, exist_ok=True)
    here = NEUTRAL.resolve()
    if any((d / ".git").exists() for d in (here, *here.parents)):
        raise Failed("%s is inside a git repository" % here)
    return here


def claude_command(model, agent=AGENT, effort=None):
    """The call a person (or, for tools/voice.py, another agent) is asked through: the model, the agent's
    instructions as the whole system prompt, no tools, nothing of the owner's setup (--safe-mode), nothing kept."""
    return [os.environ.get("CODERPG_CLAUDE", "claude"), "-p", "--safe-mode", "--tools", "", "--no-session-persistence",
            "--output-format", "json", "--model", model, "--system-prompt", instructions(agent)] + (
            ["--effort", effort] if effort else [])


def call(model, prompt, agent=AGENT, effort=None):
    """The answer to `prompt`, exactly as given, what it cost, and the exact model version that answered (the one
    claude -p names, since "sonnet" names whichever is newest), or None; Failed if it didn't come."""
    try:
        r = subprocess.run(claude_command(model, agent, effort), cwd=neutral_folder(), input=prompt, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Failed(str(e))
    try:
        out = json.loads(r.stdout)
    except ValueError:
        out = {}
    if r.returncode != 0 or out.get("is_error") or not isinstance(out.get("result"), str):
        raise Failed("the answer didn't come (exit %d)\n%s" % (r.returncode, (r.stdout + r.stderr).strip()[-600:]))
    usage = out.get("modelUsage")
    exact = ",".join(sorted(usage)) if isinstance(usage, dict) and usage else None
    return out["result"], float(out.get("total_cost_usd") or 0), exact


def ask(model, prompt):
    """Their answer to `prompt`, exactly as given, what it cost, and the exact model that answered."""
    try:
        return call(model, prompt)
    except Failed as e:
        sys.exit("ASK FAILED: %s" % e)


def printed(out):
    """What rpg.py printed, with the one newline print adds taken off: the text exactly as it would be handed on."""
    return out[:-1] if out.endswith("\n") else out


def main(argv):
    if not argv or argv[0].startswith("-"):
        sys.exit(__doc__)
    pid, memory = argv[0], "--memory" in argv[1:]
    model = model_of(pid)
    told = ["--instructions", str(AGENT.relative_to(ROOT))]  # what they're asked with, for the version record
    code, out = rpg("memory", "condense", pid) if memory else rpg("brief", pid, *told)
    if code != 0 or out.startswith("NOTHING TO CONDENSE"):
        print(out, end="")
        return code
    prompt = printed(out)
    path = "proposals/%s-%s.txt" % ("memory" if memory else "reply", pid)
    for attempt in (1, 2):
        answer, spend, exact = ask(model, prompt)
        (ROOT / path).write_text(answer, encoding="utf-8")
        store = ("memory", "store", pid) if memory else ("reply", pid)
        code, out = rpg(*store, path, "--spend", "%.6f" % spend, *told, *(["--exact-model", exact] if exact else []))
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
