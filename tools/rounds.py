#!/usr/bin/env python3
"""Run rounds, each with a fresh referee:  python3 tools/rounds.py [n] [--model <referee's model>] [--effort <its effort>]

The owner runs it in a terminal, in place of `/rounds n` in one long Claude Code session. For each round it starts
a new headless referee, `claude -p "/rounds 1"` (Sonnet unless --model says otherwise, at the effort --effort names or
the owner's own setting), waits for it, and prints
its one line. Each round's referee starts with nothing but CLAUDE.md, the skills and the save, so its context and
cost stay the same from round to round, and every round is refereed under the same conditions; what the world
needs to remember is in the save (gm-turn: notes, the story so far, the townspeople's memories). With no n, it
runs until the run stops.

Between rounds it reads `run status`, and stops on whatever /rounds stops on: the run ended or its limit reached
(NEXT ROUND WAITS), a pause or an end asked from the dashboard, or a round's session that failed or left its round
open (the next run finishes it). Starting it is the owner's say to go on, so a pause asked earlier is lifted once,
at the start. The meter is refilled once, at the start, as opening Claude Code does; the rounds' sessions don't
refill it (CODERPG_NO_REFILL). Each round's session id, cost, time and largest context go in the log
(`run referee`), for `audit.py --referee`. Ctrl-C stops it at once; the round in progress stays open, and the
next run finishes it. CODERPG_CLAUDE names another program in place of `claude` (the tests use a stand-in).
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def rpg(*args):
    r = subprocess.run([sys.executable, str(ROOT / "rules" / "rpg.py"), *args], cwd=ROOT, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def why_stop(status):
    """Why no round should start now, from `run status`'s output, or None."""
    if status.startswith("RUN: ended"):
        return "the run has ended; /newgame starts another"
    if "RUN: pause asked" in status:
        return "the owner asked for a pause (`rpg.py run resume`, or start this again, to go on)"
    m = re.search(r"NEXT ROUND WAITS: (.*)", status)
    return m.group(1) if m else None


def played(status):
    """How many rounds the run has finished, from `run status`."""
    m = re.search(r"(\d+) rounds? played", status)
    return int(m.group(1)) if m else 0


def referee_round(model, effort=None):
    """One round's referee session. Returns (its last line, session id, usd, seconds, largest context, failed)."""
    cmd = [os.environ.get("CODERPG_CLAUDE", "claude"), "-p", "/rounds 1 from-script", "--model", model, "--permission-mode", "auto",
           "--settings", str(ROOT / ".claude" / "settings.json"), "--output-format", "stream-json", "--verbose"] + (
          ["--effort", effort] if effort else [])
    env = dict(os.environ, CODERPG_NO_REFILL="1", CLAUDE_CODE_FORCE_SESSION_PERSISTENCE="1")
    start, largest, result = time.time(), 0, {}
    errors = tempfile.TemporaryFile(mode="w+")
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=errors, text=True)
    for line in proc.stdout:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "assistant":
            u = (e.get("message") or {}).get("usage") or {}
            largest = max(largest, sum(u.get(k, 0) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")))
        elif e.get("type") == "result":
            result = e
    code = proc.wait()
    errors.seek(0)
    text = (result.get("result") or "").strip() or errors.read().strip()[-300:]
    last = text.splitlines()[-1] if text else "(no answer)"
    failed = code != 0 or result.get("is_error") or not result
    return last, result.get("session_id") or "?", float(result.get("total_cost_usd") or 0), time.time() - start, largest, failed


def main(argv):
    model, effort = "sonnet", None
    if "--model" in argv:
        i = argv.index("--model")
        if i + 1 >= len(argv):
            sys.exit("--model needs a model")
        model, argv = argv[i + 1], argv[:i] + argv[i + 2:]
    if "--effort" in argv:
        i = argv.index("--effort")
        if i + 1 >= len(argv):
            sys.exit("--effort needs a level")
        effort, argv = argv[i + 1], argv[:i] + argv[i + 2:]
    if len(argv) > 1 or (argv and not argv[0].isdigit()):
        sys.exit(__doc__)
    wanted = int(argv[0]) if argv else None
    _, status = rpg("run", "status")
    if status.startswith("REFUSED"):
        sys.exit(status.strip())
    if "RUN: pause asked" in status:
        print(rpg("run", "resume")[1].strip())
    print(rpg("meter", "refill")[1].strip())
    done, total = 0, 0.0
    try:
        while wanted is None or done < wanted:
            _, status = rpg("run", "status")
            why = why_stop(status)
            if why:
                print("STOPPED: %s" % why)
                break
            before = played(status)
            number = before + 1
            last, session, usd, seconds, largest, failed = referee_round(model, effort)
            rpg("run", "referee", str(number), session, "%.6f" % usd, "%.0f" % seconds, str(largest))
            total += usd
            print("ROUND %d: $%.2f, %dm%02ds, context up to %dk. %s" % (number, usd, seconds // 60, seconds % 60, largest // 1000, last))
            if failed:
                print("STOPPED: round %d's referee session failed (%s). If the round had started, it stays open, and the next "
                      "run finishes it." % (number, last))
                break
            after = rpg("run", "status")[1]
            if "ROUND %d OPEN" % number in after:
                print("STOPPED: round %d was left open (%s); the next run finishes it." % (number, last))
                break
            if played(after) <= before:
                print("STOPPED: round %d didn't run: %s" % (number, last))
                break
            done += 1
        else:
            print("STOPPED: the %d round%s asked for are done." % (done, "" if done == 1 else "s"))
    except KeyboardInterrupt:
        print("\nSTOPPED by Ctrl-C: whatever round was in progress stays open, and the next run finishes it.")
    print("%d round%s run, $%.2f for the referee (the people's replies are logged with each action)." % (done, "" if done == 1 else "s", total))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
