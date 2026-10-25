#!/usr/bin/env python3
"""What a person in the cast is handed, exactly as Claude Code sends it, at no cost:  python3 tools/probe.py <id>

It makes <id>'s brief from a copy of the game (so the real save's memory and log stay as they were), starts a
stand-in server on 127.0.0.1, and runs `claude -p` exactly as tools/ask.py does (its `claude_command`, from its
neutral folder) with ANTHROPIC_BASE_URL pointed at the stand-in. The stand-in forwards nothing to Anthropic and
answers with an error, so claude gives up. It prints every system block and every message of the first request,
in order, as sent. Headers are never kept or printed: the Authorization header and any token are left unread.
Run it after every Claude Code update (DEVELOPING.md, Known limits).
"""
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import ask  # noqa: E402  the one call a person is asked through


class StandIn(http.server.BaseHTTPRequestHandler):
    """Keeps the body of each request to /v1/messages, and answers every request with an error."""
    bodies = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("content-length") or 0))
        if self.path.startswith("/v1/messages"):
            try:
                StandIn.bodies.append(json.loads(body))
            except ValueError:
                pass
        msg = json.dumps({"type": "error", "error": {"type": "invalid_request_error", "message": "probe: nothing is forwarded"}}).encode()
        self.send_response(400)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(msg)))
        self.end_headers()
        self.wfile.write(msg)

    do_GET = do_POST

    def log_message(self, *args):
        pass


def brief_of(pid):
    """(their model, their brief) from a copy of the game, so making the brief changes nothing here."""
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / "copy"
        for d in ("rules", "games", ".claude/agents"):
            shutil.copytree(ROOT / d, copy / d, ignore=shutil.ignore_patterns("__pycache__"))
        if (ROOT / "state").is_dir():
            shutil.copytree(ROOT / "state", copy / "state", ignore=shutil.ignore_patterns("log", "shelf", "library"))
        rpg = lambda *a: subprocess.run([sys.executable, "rules/rpg.py", *a], cwd=copy, capture_output=True, text=True)  # noqa: E731
        status = rpg("run", "status").stdout
        model = ask.model_in(status, pid)
        if not model:
            sys.exit("PROBE FAILED: %s isn't in the cast of the game in progress\n%s" % (pid, status.strip()))
        brief = rpg("brief", pid)
        if brief.returncode != 0:
            sys.exit("PROBE FAILED: no brief for %s\n%s" % (pid, brief.stdout.strip()))
        return model, ask.printed(brief.stdout)


def text_of(part):
    return part.get("text") if isinstance(part, dict) and part.get("type") == "text" else json.dumps(part, ensure_ascii=False)


def report(body, brief):
    """Each system block and each message part of a request, in order, with what it is when it's one of ours."""
    known = {ask.instructions(): "the player's instructions, exactly", brief: "the brief, exactly"}
    system = body.get("system")
    blocks = system if isinstance(system, list) else [{"type": "text", "text": system or ""}]
    for i, b in enumerate(blocks):
        t = text_of(b)
        print("== system[%d]%s" % (i, " (%s)" % known[t.strip()] if t.strip() in known else ""))
        print(t)
    for j, m in enumerate(body.get("messages") or []):
        parts = m.get("content")
        parts = parts if isinstance(parts, list) else [{"type": "text", "text": parts or ""}]
        for k, p in enumerate(parts):
            t = text_of(p)
            print("== messages[%d] %s, part %d%s" % (j, m.get("role"), k + 1, " (%s)" % known[t.strip()] if t.strip() in known else ""))
            print(t)
    print("== tools: %s" % (", ".join(t.get("name", "?") for t in body.get("tools") or []) or "none"))


def main(argv):
    if len(argv) != 1 or argv[0].startswith("-"):
        sys.exit(__doc__)
    model, brief = brief_of(argv[0])
    server = http.server.HTTPServer(("127.0.0.1", 0), StandIn)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = dict(os.environ, ANTHROPIC_BASE_URL="http://127.0.0.1:%d" % server.server_address[1])
    try:
        r = subprocess.run(ask.claude_command(model), cwd=ask.neutral_folder(), env=env, input=brief,
                           capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as e:
        sys.exit("PROBE FAILED: %s" % e)
    finally:
        server.shutdown()
    if not StandIn.bodies:
        sys.exit("PROBE FAILED: nothing reached the stand-in (exit %d)\n%s" % (r.returncode, (r.stdout + r.stderr).strip()[-600:]))
    version = subprocess.run([ask.claude_command(model)[0], "--version"], capture_output=True, text=True).stdout.strip()
    print("PROBE: %s (%s), %s, asked from %s. %d request(s) reached the stand-in, none went on; the first, as sent:"
          % (argv[0], model, version or "claude", ask.neutral_folder(), len(StandIn.bodies)))
    report(StandIn.bodies[0], brief)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
