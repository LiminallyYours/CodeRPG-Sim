#!/usr/bin/env python3
"""Someone talks with a person in the cast after a run, one line at a time (PLAN.md steps 77 and 78):

    talk.py <id> --page <file> --meet <text> --transcript <file> [--model <m>] [--effort <e>] [--follow-up] <line>

The person answers the line from their page (what `rpg.py brief <id>` printed, kept in a file and never rebuilt), the
meeting line (who is in front of them, and where), and the conversation so far in the transcript: each line said to
them and each SAY they gave, never their THOUGHT lines. Each answer is a fresh call, as each turn is, asked exactly as
tools/ask.py asks a person (`ask.call`: `claude -p` from /tmp/here, no tools, --safe-mode), with
rules/people/talker.md as the whole system prompt, on their model from the cast (`run status` here, or --model) at
the effort player.md names (or --effort). The answer must be two labelled parts, SAY and THOUGHT; one that isn't is
asked for once more with the same text, and a second failure ends the conversation, recorded as incomplete (exit 1).
It prints SAY and THOUGHT, and appends the line, both parts, what each call cost and the exact model to the
transcript, a Markdown file a person can read, with each exchange's data in a comment beside it. A new transcript
starts with the page's hash and the meeting line; an existing one must agree with both. --follow-up marks the line as
the interviewer's follow-up (tools/interviews.py). CODERPG_CLAUDE names another program in place of `claude`.
"""
import datetime
import hashlib
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "rules"))
import ask  # noqa: E402  the one call a person is asked through
import rpg  # noqa: E402  the version tags of the texts that shape an interview

TALKER = ROOT / "rules" / "people" / "talker.md"
DATA = re.compile(r"^<!-- data (\{.*\}) -->$", re.M)
REPLY = re.compile(r"\A\s*SAY:[ \t]*(.+?)\s*\n\s*THOUGHT:[ \t]*(.+?)\s*\Z", re.S)
TRIES = (30, 90)  # seconds to wait before asking again when an answer didn't come at all (not a malformed one)


class Refused(Exception):
    """The transcript can't take this line."""


def frame():
    """The frame phrases from talker.md's opening comment: {name: words}, as brief.md's phrases are written."""
    comment = re.match(r"\A\s*<!--(.*?)-->", TALKER.read_text(encoding="utf-8"), re.S).group(1)
    return dict((m.group(1), m.group(2).strip()) for m in re.finditer(r"^([a-z_]+):[ \t]+(.+)$", comment, re.M))


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prompt(page, meet, exchanges, line):
    """What the person is handed: their page, the meeting line, the conversation so far (their SAY lines only), the
    new line."""
    words = frame()
    out = [page, "", meet]
    done = [e for e in exchanges if e.get("say") is not None]
    if done:
        out.append("")
        for e in done:
            out += [words["said"].format(line=e["line"]), words["you_said"].format(say=e["say"])]
    out += ["", words["now"].format(line=line)]
    return "\n".join(out)


def parse(reply):
    """(SAY, THOUGHT) from an answer in the form talker.md asks for, or None."""
    m = REPLY.match(reply)
    if not m or re.search(r"^\s*(SAY|THOUGHT):", m.group(2), re.M):
        return None
    return m.group(1).strip(), m.group(2).strip()


def call(model, text, effort, agent=TALKER):
    """One answer through ask.call, asked again after a pause when it didn't come at all (an overloaded service);
    ask.Failed after the last try."""
    for wait in TRIES + (None,):
        try:
            return ask.call(model, text, agent=agent, effort=effort)
        except ask.Failed:
            if wait is None:
                raise
            time.sleep(wait)


def answer(model, effort, text):
    """The person's answer to `text`: {say, thought, cost, exact, replies}; say is None when it came malformed twice."""
    replies, cost, exact = [], 0.0, None
    for _ in (1, 2):
        reply, spent, exact = call(model, text, effort)
        replies.append(reply)
        cost += spent
        parts = parse(reply)
        if parts:
            return {"say": parts[0], "thought": parts[1], "cost": round(cost, 6), "exact": exact, "replies": replies}
    return {"say": None, "thought": None, "cost": round(cost, 6), "exact": exact, "replies": replies}


def blob(data):
    """An exchange's data as one comment line ("--" can't stand in a comment, and is written \\u002d in JSON)."""
    return "<!-- data %s -->" % json.dumps(data, ensure_ascii=False).replace("--", "-\\u002d")


def read(path):
    """A transcript's header and records, from their data comments, or (None, []) when there is none yet."""
    if not Path(path).is_file():
        return None, []
    found = [json.loads(m.group(1)) for m in DATA.finditer(Path(path).read_text(encoding="utf-8"))]
    head = found[0] if found and found[0].get("kind") == "header" else None
    return head, found[1:] if head else found


def start(path, header):
    """A new transcript, with what it was given: whose, the page (file and hash), the meeting line, the texts' tags."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    title = header.get("title") or "%s (%s)" % (header.get("name") or header["person"], header["person"])
    lines = ["# %s" % title, "",
             "- Page: `%s`, sha256 `%s`" % (header["page"], header["page_sha256"]),
             "- Meeting: %s" % header["meet"],
             "- Asked on: %s at %s effort" % (header["model"], header.get("effort") or "default"),
             "- Texts: %s" % ", ".join("%s `%s`" % kv for kv in sorted(header["texts"].items())),
             "- Started: %s" % header["started"], "", blob(dict(header, kind="header")), ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def append(path, record, text):
    """One record, in words for a reader and as data, at the end of the transcript."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(text.rstrip("\n") + "\n" + blob(record) + "\n\n")


def exchange_text(record):
    n = record.get("n")
    head = "### Follow-up: %s" % record["line"] if record["kind"] == "follow-up" else "### %s. %s" % (n, record["line"])
    cost = "*%s at %s effort (%s), $%.4f*" % (record["model"], record.get("effort") or "default", record.get("exact") or "?", record["cost"])
    if record["say"] is None:
        return "\n".join([head, "", "**Incomplete:** no answer in the form asked for, twice.", "",
                          *["Reply %d, as given:\n\n```\n%s\n```\n" % (i + 1, r) for i, r in enumerate(record["replies"])], cost])
    return "\n".join([head, "", "**SAY:** %s" % record["say"], "", "**THOUGHT:** %s" % record["thought"], "", cost])


def talk(pid, page_file, meet, transcript, line, model, effort, kind="line", n=None, extra=None, header=None):
    """Put one line to the person and keep it: the record appended (with `extra`'s fields), as a dict."""
    page = Path(page_file).read_text(encoding="utf-8")
    head, records = read(transcript)
    if head is None:
        head = dict({"person": pid, "page": str(page_file), "page_sha256": sha256(page), "meet": meet, "model": model,
                     "effort": effort, "texts": rpg.talk_versions(), "started": datetime.datetime.now().isoformat(timespec="seconds")},
                    **(header or {}))
        start(transcript, head)
    elif head["page_sha256"] != sha256(page) or head["meet"] != meet or head["person"] != pid:
        raise Refused("%s was begun with another page, meeting line or person" % transcript)
    exchanges = [r for r in records if r.get("kind") in ("line", "follow-up")]
    if any(r["say"] is None for r in exchanges):
        raise Refused("%s ended incomplete" % transcript)
    got = answer(model, effort, prompt(page, meet, exchanges, line))
    record = dict({"kind": kind, "n": n if n is not None else len(exchanges) + 1, "line": line, "model": model, "effort": effort,
                   "t": datetime.datetime.now().isoformat(timespec="seconds")}, **got, **(extra or {}))
    if got["say"] is not None:
        record.pop("replies")  # kept only when they failed: the parts are the answer
    append(transcript, record, exchange_text(record))
    return record


def take(argv, flag):
    if flag not in argv:
        return argv, None
    i = argv.index(flag)
    if i + 1 >= len(argv):
        sys.exit("%s needs a value" % flag)
    return argv[:i] + argv[i + 2:], argv[i + 1]


def main(argv):
    argv, page = take(argv, "--page")
    argv, meet = take(argv, "--meet")
    argv, transcript = take(argv, "--transcript")
    argv, model = take(argv, "--model")
    argv, effort = take(argv, "--effort")
    follow = "--follow-up" in argv
    argv = [a for a in argv if a != "--follow-up"]
    if len(argv) != 2 or not (page and meet and transcript):
        sys.exit(__doc__)
    pid, line = argv
    model = model or ask.model_of(pid)
    effort = effort or ask.front_matter()[1]
    try:
        record = talk(pid, page, meet, transcript, line, model, effort, kind="follow-up" if follow else "line")
    except ask.Failed as e:
        sys.exit("TALK FAILED: %s" % e)
    except Refused as e:
        print("TALK REFUSED: %s" % e)
        return 1
    if record["say"] is None:
        print("TALK INCOMPLETE: no answer in the form asked for, twice (kept in %s)" % transcript)
        return 1
    print("SAY: %s\nTHOUGHT: %s" % (record["say"], record["thought"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
