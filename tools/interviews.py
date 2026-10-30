#!/usr/bin/env python3
"""The interview suite after a run (PLAN.md step 78; INTERVIEW-SUITE-PLAN.md, which this follows):

    interviews.py pages <run folder> <suite folder> [--approaches <file>]
        the frozen pages: START (each person's round-1 brief, exactly as the run's log holds it), END (`rpg.py brief`
        in a scratch copy holding the run's save and log) and NEUTRAL (the same, in a second copy, with the person's
        condensed memory replaced by one plain summary, written by Sonnet from the stretches their own think-backs
        were shown, at the length of what it replaces), each checked as the plan says; pages/pages.json holds each
        page's hash. Refused once pages.json exists: the pages are made once.
    interviews.py run <suite folder> --cap <usd> [--approaches <file>] [--pilot] [--workers <n>]
        every interview not yet finished, in the plan's order: START, END, NEUTRAL, SONNET; within each, approach by
        approach, repeat 1 of everyone before repeat 2, the cast in order. Each line is put through tools/talk.py's
        `talk`; after the fixed lines the interviewer (Sonnet) writes one follow-up from this interview and its
        running notebook, which covers every interview so far (each follow-up's answer reaches it two interviews
        later, so the interviewer never waits for it), checked so it never leads; then the follow-up is asked.
        Fixed lines of different interviews are asked side by side (--workers, default 6); the interviewer goes one
        interview at a time, in order. No interview is begun once what's spent and what's under way would pass the
        cap (spent counts from when this run began), and no call is made past it; a stopped run resumes where each
        transcript ended. --pilot runs the plan's 28 pilot interviews in their own folder (pilot/), with their own
        notebook. The approaches are copied into the suite folder the first time, and that copy is used after.
    interviews.py score <suite folder> --cap <usd> [--pilot] [--workers <n>]
        each finished interview scored by Sonnet against the suite's RUBRIC.md, a row per answer, and each group of
        repeats compared line by line for the same gist; kept in scores.json
    interviews.py index <suite folder> [--pilot]
        index.json: every interview, its state, person, approach, repeat, page hash, cost and whether it finished
    interviews.py standin <suite folder> <question file>
        asks the stand-in (.claude/agents/standin.md: Fable at high effort) a question, with the plan before it;
        the question and answer go verbatim into standin.md
    interviews.py spent <suite folder>
        what has been spent, by kind
    interviews.py hand <suite folder> [--pilot]
        the tenth of the finished interviews that Claude Code scores by hand: those whose key's sha256 sorts first
    interviews.py agree <suite folder> <hand scores file> [--pilot]
        how often the hand scores and the scorer's disagree, column by column, over the same answers

Every call's cost goes into the suite's spend.jsonl, one ledger for everything (pages, pilot, suite, scoring, the
stand-in). Nothing here writes the game's save or log, the run's record or games/: pages are built in throwaway
copies. CODERPG_CLAUDE names another program in place of `claude` (the tests use a stand-in).
"""
import concurrent.futures
import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "rules"))
import ask  # noqa: E402  the one call an agent is asked through
import talk  # noqa: E402  one line put to a person, and the transcript
import rpg  # noqa: E402  the phrases a page is made of, and the texts' tags
from test_rules import Engine  # noqa: E402  the one FORBIDDEN pattern, the tests'

FORBIDDEN = Engine.FORBIDDEN
PEOPLE = ROOT / "rules" / "people"
APPROACHES = PEOPLE / "approaches.json"
INTERVIEWER, SCORER, SUMMARISER = PEOPLE / "interviewer.md", PEOPLE / "scorer.md", PEOPLE / "summariser.md"
HELPERS = ("sonnet", "medium")  # the interviewer, the scorer and the summariser, as the world's own people are asked
STANDIN = ROOT / ".claude" / "agents" / "standin.md"
PLAN = ROOT / "INTERVIEW-SUITE-PLAN.md"
NOTEBOOK_WORDS = 3000
FOLLOW_UP_CHARS = 300
PAGE_STATE = {"start": "start", "end": "end", "neutral": "neutral", "sonnet-start": "start", "sonnet-end": "end"}
WHEN = {"start": "at the start of their time in the town",
        "end": "at the end, after twenty days in the town",
        "neutral": "at the end, after twenty days in the town, with a plain account of those days in place of their own memories",
        "sonnet-start": "at the start of their time in the town, answered by another model",
        "sonnet-end": "at the end, after twenty days in the town, answered by another model"}
POINTERS = re.compile(r"\b(interviews?|notebook|others? (have |had )?(said|say|told|mentioned)|other (people|folk)'?s? (answers?|said|say)|"
                      r"someone (else )?(said|told|mentioned)|people (say|said|tell|told)|everyone (says|said)|last time|"
                      r"I('ve| have)? heard|I hear|(told|tells) me|said to me)\b", re.I)
REPLY_FORM = re.compile(r"\A\s*FOLLOW-UP:[ \t]*(.+?)\s*\n\s*BECAUSE:[ \t]*\n?(.*?)\n?\s*NOTEBOOK:[ \t]*\n?(.*)\Z", re.S)


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path, data):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def words(text):
    return len(text.split())


class Stop(Exception):
    """The cap is reached: no more calls."""


class Ledger:
    """spend.jsonl in the suite folder: every call's cost, the one total the cap is held to."""

    def __init__(self, suite):
        self.path = Path(suite) / "spend.jsonl"
        self.lock = threading.Lock()
        self.stop_line = None

    def entries(self):
        if not self.path.is_file():
            return []
        return [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def total(self):
        return round(sum(e["cost"] for e in self.entries()), 6)

    def add(self, what, key, model, effort, cost, exact=None):
        with self.lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": now(), "what": what, "key": key, "model": model, "effort": effort, "cost": round(cost, 6),
                                    "exact": exact}, ensure_ascii=False) + "\n")

    def allow(self):
        """Raises Stop when a call now would pass the cap."""
        if self.stop_line is not None and self.total() >= self.stop_line:
            raise Stop()


# ---------------------------------------------------------------- the approaches and the order

def approaches(suite, source=None):
    """The suite's approaches: its own copy, made from `source` (default rules/people/approaches.json) the first time;
    a different `source` after that is refused."""
    mine = Path(suite) / "approaches.json"
    src = Path(source) if source else APPROACHES
    if not mine.is_file():
        Path(suite).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, mine)
    elif source and Path(source).read_bytes() != mine.read_bytes():
        sys.exit("REFUSED: %s already has its approaches, and %s differs from them" % (suite, source))
    return json.loads(mine.read_text(encoding="utf-8"))


def approach(A, aid):
    return next(a for a in A["approaches"] if a["id"] == aid)


def interview(state, pid, aid, repeat):
    folder = "sonnet/%s" % state.split("-", 1)[1] if state.startswith("sonnet-") else state
    return {"key": "%s/%s/%02d-%d" % (state, pid, aid, repeat), "state": state, "person": pid, "approach": aid, "repeat": repeat,
            "path": "%s/%s/%02d-%d.md" % (folder, pid, aid, repeat)}


def plan_of(A, people, pilot=False):
    """Every interview, in the order they are run (INTERVIEW-SUITE-PLAN.md section 4)."""
    out = []
    if pilot:
        for state, aid, who in A["pilot"]:
            out += [interview(state, pid, aid, 1) for pid in (people if who == "all" else [who])]
        return out
    for state in ("start", "end"):
        for a in A["approaches"]:
            if state in a["states"]:
                out += [interview(state, pid, a["id"], r) for r in range(1, a["repeats"] + 1) for pid in people]
    n = A["neutral"]
    out += [interview("neutral", pid, aid, r) for aid in n["approaches"] for r in range(1, n["repeats"] + 1) for pid in n["people"]]
    s = A["sonnet"]
    out += [interview("sonnet-" + st, pid, aid, r) for st in s["states"] for aid in s["approaches"]
            for r in range(1, s["repeats"] + 1) for pid in s["people"]]
    return out


def lines_of(A, iv, name):
    return [l.replace("{name}", name) for l in approach(A, iv["approach"])["lines"]]


def place_of(page):
    """The place on a page's Where you are line, as a meeting line names it ("the Tithe Barn")."""
    m = re.search(r"^%s\n([^,\n]+)" % re.escape(rpg.phrase("where_you_are")), page, re.M)
    if not m:
        raise SystemExit("REFUSED: a page has no %r line" % rpg.phrase("where_you_are"))
    return re.sub(r"^The ", "the ", m.group(1).strip())


def meet_of(A, state, page):
    if PAGE_STATE[state] == "start":
        return A["meet"]["start"]
    return A["meet"]["end"].replace("{place}", place_of(page))


# ---------------------------------------------------------------- the pages

def scratch_copy(save, log):
    """A throwaway copy of the code with `save` as its save and `log` in its log folder: as the run left them."""
    d = Path(tempfile.mkdtemp(prefix="interview-pages-"))
    top = lambda path, names: [n for n in names if path == str(ROOT) and n in (".git", "state")] + [n for n in names if n == "__pycache__"]
    shutil.copytree(ROOT, d / "copy", ignore=top)
    d = d / "copy"
    (d / "state" / "log").mkdir(parents=True)
    shutil.copyfile(save, d / "state" / "save.json")
    shutil.copyfile(log, d / "state" / "log" / Path(log).name)
    (d / "state" / "active.json").write_text(json.dumps({"game": json.loads(Path(save).read_text())["game"]}))
    return d


def rpg_in(copy, *args):
    r = subprocess.run([sys.executable, "rules/rpg.py", *args], cwd=copy, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise SystemExit("REFUSED: rpg.py %s in the scratch copy: %s" % (" ".join(args), (r.stdout + r.stderr).strip()[-800:]))
    return ask.printed(r.stdout)


def pane_of(page):
    return page.split(rpg.phrase("where_you_are"), 1)[1] if rpg.phrase("where_you_are") in page else ""


def end_problems(page, end_time):
    """What keeps an END page from meeting the plan's requirement (the pane: the time, no sleep line, nobody asleep)."""
    pane = pane_of(page)
    out = []
    if end_time and end_time not in pane.split("\n", 2)[1]:
        out.append("the time isn't %s" % end_time)
    if rpg.phrase("sleep_slept") in pane:
        out.append("a sleep line")
    if "asleep" in pane.lower():
        out.append("someone asleep")
    return out


def memory_section(page):
    """A page cut in three: before its remembered section, the section, and after."""
    head, rest = page.split(rpg.phrase("remember") + "\n", 1)
    body, tail = rest.split("\n\n" + rpg.phrase("lately") + "\n", 1)
    return head, body, tail


def stretches(log, pid):
    """The stretches of moments each of `pid`'s think-backs was shown, in order: [(round, stretch)], the last one
    shown in each round, as bench.py's --thinkback keeps one."""
    import bench
    found = {}
    for line in Path(log).read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        if (e["kind"] == "command" and e.get("command") == "memory" and not e.get("refused") and e.get("args", [])[:2] == ["condense", pid]
                and "### Moment" in e.get("output", "")):
            found[e["round"]] = bench.stretch_of(e["output"])
    return sorted(found.items())


def summary_prompt(name, parts, target):
    out = ["These are the moments %s lived, stretch by stretch, in order. Summarise them in about %d words." % (name, target)]
    for i, (_, stretch) in enumerate(parts, 1):
        out += ["", "## Stretch %d" % i, stretch]
    return "\n".join(out)


def cmd_pages(args):
    args, source = take(args, "--approaches")
    if len(args) != 2:
        sys.exit(__doc__)
    run, suite = Path(args[0]), Path(args[1])
    out = suite / "pages"
    if (out / "pages.json").is_file():
        sys.exit("REFUSED: %s exists: the pages are made once" % (out / "pages.json"))
    A = approaches(suite, source)
    ledger = Ledger(suite)
    save_path = run / "save.json"
    logs = sorted(run.glob("*.jsonl"))
    if len(logs) != 1:
        sys.exit("REFUSED: %s should hold one run log, not %d" % (run, len(logs)))
    log = logs[0]
    save = json.loads(save_path.read_text(encoding="utf-8"))
    people = list(save["players"])
    out.mkdir(parents=True, exist_ok=True)
    meta = {"run": str(run), "log": log.name, "save_sha256": hashlib.sha256(save_path.read_bytes()).hexdigest(), "game": save["game"],
            "built": now(), "people": {}, "pages": {"start": {}, "end": {}, "neutral": {}}, "summaries": {}, "checks": [], "texts": rpg.talk_versions()}

    def keep(state, pid, page):
        f = out / ("%s-%s.txt" % (state, pid))
        f.write_text(page, encoding="utf-8")
        meta["pages"][state][pid] = {"file": "pages/%s" % f.name, "sha256": sha256(page), "chars": len(page)}

    # START: the round-1 page, exactly as logged
    first = {}
    for line in log.read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        if e["kind"] == "brief" and e.get("round") == 1:
            first[e["player"]] = e["text"]
    for pid in people:
        if pid not in first:
            sys.exit("REFUSED: %s has no round-1 brief for %s" % (log, pid))
        keep("start", pid, first[pid])
    meta["checks"].append("START: the round-1 brief from the log, byte for byte, for %s" % ", ".join(people))

    # END: one copy, every page from it
    copy = scratch_copy(save_path, log)
    try:
        status = rpg_in(copy, "run", "status")
        for pid in people:
            meta["people"][pid] = {"name": save["players"][pid]["name"], "model": ask.model_in(status, pid)}
        asleep = [p for p in people if save["players"][p].get("asleep")]
        pages = {pid: rpg_in(copy, "brief", pid) for pid in people}
        if asleep or any(end_problems(p, A.get("end_time")) for p in pages.values()):
            meta["checks"].append("END: %s; `round start` run once in the copy, no turns played, and the pages built again"
                                  % "; ".join(sorted({x for p in pages.values() for x in end_problems(p, A.get("end_time"))} | ({"someone asleep"} if asleep else set()))))
            rpg_in(copy, "round", "start")
            pages = {pid: rpg_in(copy, "brief", pid) for pid in people}
        problems = {pid: end_problems(p, A.get("end_time")) for pid, p in pages.items() if end_problems(p, A.get("end_time"))}
        if problems:
            sys.exit("REFUSED: END pages don't meet the plan: %s" % problems)
        for pid in people:
            keep("end", pid, pages[pid])
            meta["people"][pid]["place"] = place_of(pages[pid])
        meta["checks"].append("END: every page from one copy; the pane reads %s; no sleep line; nobody asleep" % (A.get("end_time") or "its time"))
    finally:
        shutil.rmtree(copy.parent, ignore_errors=True)

    # NEUTRAL: a summary in place of the condensed memory, in a second copy
    neutral = A["neutral"]["people"]
    edited = json.loads(save_path.read_text(encoding="utf-8"))
    for pid in neutral:
        condensed = save["players"][pid]["memory"]["condensed"]
        parts = stretches(log, pid)
        if [c["round"] for c in condensed] != [r for r, _ in parts]:
            sys.exit("REFUSED: %s's think-backs in the log (rounds %s) don't match their condensed memory (rounds %s)"
                     % (pid, [r for r, _ in parts], [c["round"] for c in condensed]))
        target = sum(words(c["text"]) for c in condensed)
        prompt = summary_prompt(save["players"][pid]["name"], parts, target)
        note = [x for l in rpg_note_lines(pid, save) for x in re.split(r"(?<=[.!?;])\s+", l.strip()) if len(x) >= 30]
        leaked = [l for l in note if l in prompt]
        if leaked:
            sys.exit("REFUSED: the summariser's prompt for %s holds lines of their Who I am note: %s" % (pid, leaked[:2]))
        (out / ("summary-%s.prompt.txt" % pid)).write_text(prompt, encoding="utf-8")
        summary, tries = None, []
        for attempt in (1, 2, 3):
            text, cost, exact = talk.call(HELPERS[0], prompt, HELPERS[1], agent=SUMMARISER)
            ledger.add("summary", pid, HELPERS[0], HELPERS[1], cost, exact)
            text = text.strip()
            (out / ("summary-%s-%d.txt" % (pid, attempt))).write_text(text, encoding="utf-8")
            tries.append(words(text))
            if 0.8 * target <= words(text) <= 1.2 * target:
                summary = text
                break
        if summary is None:
            sys.exit("REFUSED: %s's summary missed %d words by more than a fifth three times (%s)" % (pid, target, tries))
        (out / ("summary-%s.txt" % pid)).write_text(summary, encoding="utf-8")
        edited["players"][pid]["memory"]["condensed"] = [{"rounds": [condensed[0]["rounds"][0], condensed[-1]["rounds"][1]], "kind": "condensed",
                                                         "text": summary, "round": condensed[-1]["round"], "uses": 0}]
        meta["summaries"][pid] = {"target_words": target, "words": words(summary), "attempts": tries, "stretches": len(parts),
                                  "prompt": "pages/summary-%s.prompt.txt" % pid, "file": "pages/summary-%s.txt" % pid,
                                  "note_lines_checked": len(note), "forbidden_hits": sorted({m.group(0) for m in FORBIDDEN.finditer(summary)})}
    edited_path = out / "neutral-save.json"
    edited_path.write_text(json.dumps(edited, ensure_ascii=False), encoding="utf-8")
    copy = scratch_copy(edited_path, log)
    try:
        for pid in neutral:
            page = rpg_in(copy, "brief", pid)
            end = (out / ("end-%s.txt" % pid)).read_text(encoding="utf-8")
            (h1, _, t1), (h2, body, t2) = memory_section(end), memory_section(page)
            if (h1, t1) != (h2, t2) or body != (out / ("summary-%s.txt" % pid)).read_text(encoding="utf-8"):
                sys.exit("REFUSED: %s's NEUTRAL page differs from END outside the remembered section" % pid)
            keep("neutral", pid, page)
        meta["checks"].append("NEUTRAL: %s; each page differs from END only in the remembered section, which is the summary" % ", ".join(neutral))
    finally:
        shutil.rmtree(copy.parent, ignore_errors=True)
        edited_path.unlink()
    texts = out.parent / "texts"
    texts.mkdir(exist_ok=True)
    for name in rpg.TALK_TEXTS:
        (texts / ("%s-%s.md" % (Path(name).stem, rpg.text_tag(rpg.people_file(name))))).write_text(rpg.people_file(name), encoding="utf-8")
    write_json(out / "pages.json", meta)
    for state, got in meta["pages"].items():
        for pid, p in got.items():
            print("%-8s %-10s %6d chars  %s" % (state, pid, p["chars"], p["sha256"][:12]))
    for pid, s in meta["summaries"].items():
        print("summary  %-10s %d words for %d (tries: %s)" % (pid, s["words"], s["target_words"], s["attempts"]))
    print("PAGES: %s" % (out / "pages.json"))


def rpg_note_lines(pid, save):
    """The lines of `pid`'s Who I am note, as their page shows it."""
    entry = cast_entry(save["game"], pid)
    return rpg.note_lines(entry, save["players"][pid]["name"], entry.get("pronouns", "they/them"), lambda who: who)


def cast_entry(game, pid):
    cast = json.loads((ROOT / "games" / game / "cast.json").read_text(encoding="utf-8"))
    return next(e for e in cast if e["id"] == pid)


# ---------------------------------------------------------------- the interviewer

def check_follow_up(q, wall):
    """Why a follow-up leads or breaks the form, or None."""
    if not q:
        return "no question"
    if len(q) > FOLLOW_UP_CHARS:
        return "longer than %d characters" % FOLLOW_UP_CHARS
    if q.count("?") != 1 or not re.search(r"\?[\"'”’)]*$", q):
        return "not one question ending in a question mark"
    if re.search(r"[.!;]\s+[\"'“‘]?[A-Z]", q.split("?")[0]):
        return "more than one sentence"
    if POINTERS.search(q):
        return "points at other accounts (%r)" % POINTERS.search(q).group(0)
    if not wall and FORBIDDEN.search(q):
        return "a forbidden word (%r)" % FORBIDDEN.search(q).group(0)
    return None


def parse_interviewer(reply):
    """(question, [notebook lines quoted], notebook) from the interviewer's reply, or None."""
    m = REPLY_FORM.match(reply)
    if not m:
        return None
    because = [l.strip()[1:].strip() for l in m.group(2).splitlines() if l.strip().startswith(">")]
    return m.group(1).strip(), because, m.group(3).strip()


def interviewer_prompt(A, iv, name, exchanges, fed, notebook):
    a = approach(A, iv["approach"])
    out = ["## The aim", a["aim"], "", "## This interview",
           "%s, %s. Set %d (%s), repeat %d of %d." % (name, WHEN[iv["state"]], a["id"], a["title"], iv["repeat"],
                                                    A["neutral"]["repeats"] if iv["state"] == "neutral" else
                                                    A["sonnet"]["repeats"] if iv["state"].startswith("sonnet") else a["repeats"])]
    for e in exchanges:
        out += ["", "%d. Asked: %s" % (e["n"], e["line"]), "   Answered aloud: %s" % e["say"]]
    if fed:
        out += ["", "## Earlier follow-ups, answered since"]
        for f in fed:
            out += ["", "%s (%s, set %d, repeat %d): asked %s" % (f["name"], WHEN[f["state"]], f["approach"], f["repeat"], f["line"]),
                    "   Answered aloud: %s" % f["say"]]
    out += ["", "## Your notebook", notebook.strip() or "(empty: this is the first interview)"]
    return "\n".join(out)


# ---------------------------------------------------------------- one interview, and the whole run

class Runner:
    def __init__(self, suite, out, A, pages, ledger, workers):
        self.suite, self.out, self.A, self.pages, self.ledger, self.workers = Path(suite), Path(out), A, pages, ledger, workers
        self.effort = ask.front_matter()[1]
        self.book_path = self.out / "notebook.md"
        self.state_path = self.out / "notebook.json"
        self.book = self.book_path.read_text(encoding="utf-8") if self.book_path.is_file() else ""
        self.book_state = json.loads(self.state_path.read_text()) if self.state_path.is_file() else {"seen": [], "fed": [], "calls": 0}
        self.soft_stop = False
        self.lock = threading.Lock()

    def page(self, iv):
        p = self.pages["pages"][PAGE_STATE[iv["state"]]][iv["person"]]
        return self.suite / p["file"], (self.suite / p["file"]).read_text(encoding="utf-8")

    def model(self, iv):
        return self.A["sonnet"]["model"] if iv["state"].startswith("sonnet-") else self.pages["people"][iv["person"]]["model"]

    def name(self, pid):
        return self.pages["people"][pid]["name"]

    def records(self, iv):
        return talk.read(self.out / iv["path"])[1]

    def status(self, iv):
        """'done' (finished, or ended incomplete), 'follow' (only the follow-up's answer missing), or 'open'."""
        recs = self.records(iv)
        fixed = [r for r in recs if r["kind"] == "line"]
        inter = [r for r in recs if r["kind"] == "interviewer"]
        follow = [r for r in recs if r["kind"] == "follow-up"]
        if any(r["say"] is None for r in fixed + follow):
            return "done"
        if len(fixed) < len(approach(self.A, iv["approach"])["lines"]) or not inter:
            return "open"
        return "done" if follow or not inter[-1].get("question") else "follow"

    def ask_line(self, iv, line, kind, n):
        self.ledger.allow()
        file, page = self.page(iv)
        a = approach(self.A, iv["approach"])
        head = {"title": "%s (%s), %s, approach %d: %s, repeat %d" % (self.name(iv["person"]), iv["person"], iv["state"], a["id"], a["title"], iv["repeat"]),
                "name": self.name(iv["person"]), "key": iv["key"], "state": iv["state"], "approach": a["id"], "repeat": iv["repeat"], "wall": a["wall"],
                "page": str(file.relative_to(self.suite))}
        rec = talk.talk(iv["person"], file, meet_of(self.A, iv["state"], page), self.out / iv["path"],
                        line, self.model(iv), self.effort, kind=kind, n=n, header=head)
        self.ledger.add("person" if kind == "line" else "follow-up", iv["key"], self.model(iv), self.effort, rec["cost"], rec["exact"])
        return rec

    def fixed_part(self, iv):
        """The fixed lines not yet answered. 'ok', 'incomplete' or 'stopped'."""
        lines = lines_of(self.A, iv, self.name(iv["person"]))
        try:
            for n in range(len([r for r in self.records(iv) if r["kind"] == "line"]) + 1, len(lines) + 1):
                if self.ask_line(iv, lines[n - 1], "line", n)["say"] is None:
                    return "incomplete"
        except Stop:
            return "stopped"
        return "ok"

    def follow_up(self, iv, question):
        try:
            return "ok" if self.ask_line(iv, question, "follow-up", None)["say"] is not None else "incomplete"
        except Stop:
            return "stopped"

    def interviewer(self, iv, fed):
        """The follow-up for `iv`, the notebook brought up to date; the record kept in the transcript."""
        self.ledger.allow()
        a = approach(self.A, iv["approach"])
        exchanges = [r for r in self.records(iv) if r["kind"] == "line"]
        prompt = interviewer_prompt(self.A, iv, self.name(iv["person"]), exchanges, fed, self.book)
        replies, cost, exact, question, because, why, book = [], 0.0, None, None, [], None, None
        for attempt in (1, 2):
            if attempt == 2:
                self.ledger.allow()
            reply, spent, exact = talk.call(HELPERS[0], prompt if attempt == 1 else prompt + "\n\nYour last reply was not accepted (%s). Reply again, exactly in the form asked." % why,
                                            HELPERS[1], agent=INTERVIEWER)
            self.ledger.add("interviewer", iv["key"], HELPERS[0], HELPERS[1], spent, exact)
            replies.append(reply)
            cost += spent
            parsed = parse_interviewer(reply)
            if not parsed:
                why = "not in the form asked for"
                continue
            q, b, nb = parsed
            if nb and words(nb) <= NOTEBOOK_WORDS:
                book = nb
            why = check_follow_up(q, a["wall"]) or (None if nb and words(nb) <= NOTEBOOK_WORDS else "the notebook is empty or over %d words" % NOTEBOOK_WORDS)
            if why is None:
                question, because = q, b
                break
        if book is not None:
            self.book = book
            self.book_path.write_text(book + "\n", encoding="utf-8")
            with open(self.out / "notebook-history.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": now(), "after": iv["key"], "words": words(book), "text": book}, ensure_ascii=False) + "\n")
        self.book_state["seen"].append(iv["key"])
        self.book_state["fed"] += [f["key"] for f in fed]
        self.book_state["calls"] += len(replies)
        write_json(self.state_path, self.book_state)
        record = {"kind": "interviewer", "question": question, "because": because, "dropped": None if question else why,
                  "model": HELPERS[0], "effort": HELPERS[1], "exact": exact, "cost": round(cost, 6), "tries": len(replies),
                  "notebook_words": words(self.book), "notebook_kept": book is not None, "fed": [f["key"] for f in fed], "t": now()}
        if not question:
            record["replies"] = replies
        text = ["### The interviewer's follow-up", ""]
        text += ["%s" % question, "", "Because:"] + ["> %s" % l for l in because] if question else ["**Dropped:** %s." % why]
        text += ["", "*%s at %s effort (%s), $%.4f; notebook %d words*" % (HELPERS[0], HELPERS[1], exact or "?", cost, words(self.book))]
        talk.append(self.out / iv["path"], record, "\n".join(text))
        return question

    def answered_follow_up(self, iv):
        """The interview's follow-up and its answer, for the notebook, or None."""
        f = [r for r in self.records(iv) if r["kind"] == "follow-up" and r["say"] is not None]
        return dict(iv, name=self.name(iv["person"]), line=f[-1]["line"], say=f[-1]["say"]) if f else None

    def estimate(self, iv):
        """What an interview still to run may cost: its replies at the average so far for pages of its state (or a
        guess from the page's length), the interviewer's call at its average."""
        es = self.ledger.entries()
        state = PAGE_STATE[iv["state"]]
        mine = [e["cost"] for e in es if e["what"] in ("person", "follow-up") and e["key"].split("/")[0] in
                [s for s, p in PAGE_STATE.items() if p == state] and (e["model"] == self.model(iv))]
        reply = sum(mine) / len(mine) if len(mine) >= 3 else max(0.03, 0.004 * len(self.page(iv)[1]) / 1000)
        inter = [e["cost"] for e in es if e["what"] == "interviewer"]
        return (len(approach(self.A, iv["approach"])["lines"]) + 1) * reply + (sum(inter) / len(inter) if inter else 0.1)

    def still_to_spend(self, reserved):
        """What the interviews under way may still cost: each one's estimate less what it has spent already (that is
        in the ledger's total), never below nothing."""
        spent = {}
        for e in self.ledger.entries():
            spent[e["key"]] = spent.get(e["key"], 0) + e["cost"]
        return sum(max(0.0, est - spent.get(key, 0)) for key, est in list(reserved.items()))

    def run(self, order, cap):
        self.ledger.stop_line = self.ledger.total() + cap
        place = {iv["key"]: g for g, iv in enumerate(order)}
        unfed = [iv for iv in order if iv["key"] not in self.book_state["fed"] and self.status(iv) == "done" and self.answered_follow_up(iv)]
        todo = [iv for iv in order if self.status(iv) != "done"]
        print("RUN: %d interviews to finish, cap $%.2f (spent so far $%.2f, stop at $%.2f)" % (len(todo), cap, self.ledger.total(), self.ledger.stop_line), flush=True)
        pool = concurrent.futures.ThreadPoolExecutor(self.workers)
        follow_pool = concurrent.futures.ThreadPoolExecutor(3)
        fixed, follows, submitted, stopped = {}, {}, 0, None
        reserved = {}

        def top_up(pos):
            nonlocal submitted, stopped
            while submitted < len(todo) and submitted < pos + 2 * self.workers and stopped is None:
                iv = todo[submitted]
                est = self.estimate(iv)
                under_way = self.still_to_spend(reserved)
                if self.ledger.total() + under_way + est > self.ledger.stop_line:
                    stopped = "the cap: $%.2f spent, $%.2f still to spend on what's under way, $%.2f for the next" % (self.ledger.total(), under_way, est)
                    break
                reserved[iv["key"]] = est
                fixed[submitted] = pool.submit(self.fixed_part, iv) if self.status(iv) == "open" else None
                submitted += 1

        finished = 0
        try:
            for pos, iv in enumerate(todo):
                top_up(pos)
                if pos >= submitted:
                    break
                got = fixed[pos].result() if fixed[pos] else "ok"
                g = place[iv["key"]]  # the answers to follow-ups two or more interviews back, in the plan's order, go to the notebook
                for j, f in follows.items():
                    if place[todo[j]["key"]] <= g - 2 and not f.done():
                        f.result()
                for j in sorted(follows):
                    if place[todo[j]["key"]] <= g - 2 and todo[j] not in unfed and todo[j]["key"] not in self.book_state["fed"]:
                        unfed.append(todo[j])
                fed = [x for x in (self.answered_follow_up(v) for v in unfed if place[v["key"]] <= g - 2 and v["key"] not in self.book_state["fed"]) if x]
                if got == "ok" and self.status(iv) == "open":
                    try:
                        question = self.interviewer(iv, fed)
                    except Stop:
                        got = "stopped"
                    else:
                        if question:
                            follows[pos] = follow_pool.submit(self.follow_up, iv, question)
                elif got == "ok" and self.status(iv) == "follow":
                    q = [r for r in self.records(iv) if r["kind"] == "interviewer"][-1]["question"]
                    follows[pos] = follow_pool.submit(self.follow_up, iv, q)
                if pos in follows:
                    follows[pos].add_done_callback(lambda f, k=iv["key"]: reserved.pop(k, None))
                else:
                    reserved.pop(iv["key"], None)
                finished += 1
                print("%s %-28s %-10s $%.2f spent" % (now()[11:], iv["key"], got, self.ledger.total()), flush=True)
                if got == "stopped" and stopped is None:
                    stopped = "the cap, reached during %s" % iv["key"]
        finally:
            pool.shutdown(wait=True)
            follow_pool.shutdown(wait=True)
        for pos in sorted(follows):
            follows[pos].result()
        left = len([iv for iv in todo if self.status(iv) != "done"])
        print("RUN %s: %d interviews taken up, %d not finished; $%.2f spent in all" % (
            "STOPPED at %s" % stopped if stopped else "DONE", finished, left, self.ledger.total()), flush=True)
        return 0 if not stopped else 3


def load(suite, pilot, source=None):
    suite = Path(suite)
    pages = json.loads((suite / "pages" / "pages.json").read_text(encoding="utf-8"))
    A = approaches(suite, source)
    return suite, (suite / "pilot" if pilot else suite), A, pages


def cmd_run(args):
    args, source = take(args, "--approaches")
    args, cap = take(args, "--cap")
    args, workers = take(args, "--workers")
    pilot = "--pilot" in args
    args = [a for a in args if a != "--pilot"]
    if len(args) != 1 or cap is None:
        sys.exit(__doc__)
    suite, out, A, pages = load(args[0], pilot, source)
    out.mkdir(parents=True, exist_ok=True)
    runner = Runner(suite, out, A, pages, Ledger(suite), int(workers or 6))
    code = runner.run(plan_of(A, list(pages["people"]), pilot), float(cap))
    write_index(suite, out, A, pages, pilot)
    return code


# ---------------------------------------------------------------- scoring

def sheet_lines(game, pid):
    e = cast_entry(game, pid)
    out = ["- I want or need: %s" % w for w in e.get("wants_and_needs") or e.get("motivations") or []]
    out += ["- I won't: %s" % w for w in e.get("wont_do") or []]
    if e.get("how_i_am") or e.get("personality"):
        out.append("- How I am: %s" % (e.get("how_i_am") or e.get("personality")))
    return out


ROW_KEYS = ("in_character", "grounded", "beyond_page", "thought_contradicts_say", "trait")


def check_rows(data, n):
    """Why a scorer's rows aren't one a answer with allowed values, or None."""
    rows = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(rows, list) or len(rows) != n:
        return "not %d rows" % n
    for i, r in enumerate(rows, 1):
        if not isinstance(r, dict) or r.get("answer") != i:
            return "row %d isn't answer %d" % (i, i)
        for k in ("in_character", "grounded", "thought_contradicts_say"):
            if r.get(k) not in ("yes", "no"):
                return "row %d: %s is %r" % (i, k, r.get(k))
        for k in ("beyond_page", "trait"):
            if not isinstance(r.get(k), str) or not r[k].strip():
                return "row %d: %s is empty" % (i, k)
    return None


def json_of(reply):
    m = re.search(r"\{.*\}", reply, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except ValueError:
        return None


def answers_of(records):
    return [r for r in records if r["kind"] in ("line", "follow-up") and r["say"] is not None]


def score_prompt(rubric, page, sheet, answers):
    out = ["## The rubric", rubric.strip(), "", "## The page", page, "", "## The sheet lines"] + sheet + ["", "## The interview"]
    for i, r in enumerate(answers, 1):
        out += ["", "Answer %d%s. Asked: %s" % (i, " (the follow-up)" if r["kind"] == "follow-up" else "", r["line"]),
                "SAY: %s" % r["say"], "THOUGHT: %s" % r["thought"]]
    out += ["", 'Reply with JSON only: {"rows": [{"answer": 1, "in_character": "yes|no", "grounded": "yes|no", "beyond_page": "none, or what", '
                '"thought_contradicts_say": "yes|no", "trait": "a short quote from the sheet lines, or none"}, ...]}, one row for each of the %d answers, in order.' % len(answers)]
    return "\n".join(out)


def gist_prompt(rubric, name, lines, by_repeat):
    out = ["## The rubric", rubric.strip(), "", "## The answers", "%s answered the same questions in %d separate conversations." % (name, len(by_repeat))]
    for n, line in enumerate(lines, 1):
        out += ["", "Question %d: %s" % (n, line)]
        for r, answers in sorted(by_repeat.items()):
            say = next((a["say"] for a in answers if a["kind"] == "line" and a["n"] == n), None)
            out.append("  Repeat %d: %s" % (r, say if say is not None else "(no answer)"))
    out += ["", "For each question, mark each repeat's answer yes if it keeps the same gist as at least one other repeat's answer, no if it "
                'says something different from all of them. Reply with JSON only: {"lines": [{"question": 1, "repeats": {"1": "yes|no", ...}}, ...]}, '
                "one entry for each of the %d questions." % len(lines)]
    return "\n".join(out)


def cmd_score(args):
    args, cap = take(args, "--cap")
    args, workers = take(args, "--workers")
    pilot = "--pilot" in args
    args = [a for a in args if a != "--pilot"]
    if len(args) != 1 or cap is None:
        sys.exit(__doc__)
    suite, out, A, pages = load(args[0], pilot)
    ledger = Ledger(suite)
    ledger.stop_line = ledger.total() + float(cap)
    rubric = (suite / "RUBRIC.md").read_text(encoding="utf-8")
    path = out / "scores.json"
    scores = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"interviews": {}, "gist": {}}
    runner = Runner(suite, out, A, pages, ledger, 1)
    done = [iv for iv in plan_of(A, list(pages["people"]), pilot) if runner.status(iv) == "done" and (out / iv["path"]).is_file()]
    lock, stopped = threading.Lock(), []

    def one(iv):
        if iv["key"] in scores["interviews"] and "rows" in scores["interviews"][iv["key"]]:
            return
        answers = answers_of(runner.records(iv))
        if not answers:
            return
        prompt = score_prompt(rubric, runner.page(iv)[1], sheet_lines(pages["game"], iv["person"]), answers)
        why = None
        for attempt in (1, 2):
            try:
                ledger.allow()
            except Stop:
                stopped.append(iv["key"])
                return
            reply, cost, exact = talk.call(HELPERS[0], prompt if attempt == 1 else prompt + "\n\nYour last reply was not accepted (%s)." % why, HELPERS[1], agent=SCORER)
            ledger.add("score", iv["key"], HELPERS[0], HELPERS[1], cost, exact)
            data = json_of(reply)
            why = check_rows(data, len(answers)) if data else "not JSON"
            if why is None:
                break
        with lock:
            scores["interviews"][iv["key"]] = {"rows": data["rows"]} if why is None else {"failed": why}
            write_json(path, scores)

    def group(key, ivs):
        if key in scores["gist"]:
            return
        by_repeat = {iv["repeat"]: [r for r in runner.records(iv) if r["kind"] == "line" and r["say"] is not None] for iv in ivs}
        lines = lines_of(A, ivs[0], runner.name(ivs[0]["person"]))
        try:
            ledger.allow()
        except Stop:
            stopped.append(key)
            return
        reply, cost, exact = talk.call(HELPERS[0], gist_prompt(rubric, runner.name(ivs[0]["person"]), lines, by_repeat), HELPERS[1], agent=SCORER)
        ledger.add("gist", key, HELPERS[0], HELPERS[1], cost, exact)
        data = json_of(reply)
        ok = isinstance(data, dict) and isinstance(data.get("lines"), list) and len(data["lines"]) == len(lines) and all(
            set(e.get("repeats", {})) == {str(r) for r in by_repeat} and set(e["repeats"].values()) <= {"yes", "no"} for e in data["lines"])
        with lock:
            scores["gist"][key] = {"lines": data["lines"]} if ok else {"failed": "not the form asked for", "reply": reply}
            write_json(path, scores)

    groups, finished = {}, {iv["key"] for iv in done}
    for iv in plan_of(A, list(pages["people"]), pilot):
        groups.setdefault("%s/%s/%02d" % (iv["state"], iv["person"], iv["approach"]), []).append(iv)
    # a group is compared only once all its repeats are done, so scoring can run beside an unfinished suite
    groups = {k: v for k, v in groups.items() if all(iv["key"] in finished for iv in v)}
    with concurrent.futures.ThreadPoolExecutor(int(workers or 6)) as ex:
        list(ex.map(one, done))
        list(ex.map(lambda kv: group(*kv), [(k, v) for k, v in groups.items() if len(v) > 1]))
    write_json(path, scores)
    failed = [k for k, v in scores["interviews"].items() if "failed" in v]
    print("SCORED: %d interviews (%d failed), %d groups of repeats; $%.2f spent in all" % (
        len(scores["interviews"]), len(failed), len(scores["gist"]), ledger.total()))
    if stopped:  # the cap is held to the one ledger, so a suite running alongside spends from it too
        print("SCORING STOPPED at the cap: %d interviews or groups of repeats not scored; score again to go on" % len(stopped))
        return 3
    return 0


# ---------------------------------------------------------------- the index, the stand-in, the ledger

def write_index(suite, out, A, pages, pilot):
    runner = Runner(suite, out, A, pages, Ledger(suite), 1)
    rows = []
    for iv in plan_of(A, list(pages["people"]), pilot):
        head, recs = talk.read(out / iv["path"])
        st = runner.status(iv) if head else "not begun"
        answered = [r for r in recs if r["kind"] in ("line", "follow-up")]
        inter = [r for r in recs if r["kind"] == "interviewer"]
        rows.append({"key": iv["key"], "file": iv["path"], "state": iv["state"], "person": iv["person"], "approach": iv["approach"],
                     "repeat": iv["repeat"], "page_sha256": head["page_sha256"] if head else pages["pages"][PAGE_STATE[iv["state"]]][iv["person"]]["sha256"],
                     "model": head["model"] if head else None, "exact": sorted({r.get("exact") for r in answered if r.get("exact")}),
                     "cost": round(sum(r["cost"] for r in recs if "cost" in r), 6),
                     "complete": st == "done" and not any(r["say"] is None for r in answered) and bool(inter),
                     "ended_incomplete": any(r["say"] is None for r in answered),
                     "follow_up": (inter[-1]["question"] and "asked") or ("dropped: %s" % inter[-1]["dropped"]) if inter else None})
    files = {"approaches.json": suite / "approaches.json", "PREDICTIONS.md": suite / "PREDICTIONS.md", "RUBRIC.md": suite / "RUBRIC.md",
             "pages.json": suite / "pages" / "pages.json"}
    index = {"written": now(), "pilot": pilot, "interviews": len(rows), "complete": sum(r["complete"] for r in rows),
             "sha256": {k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in files.items() if p.is_file()},
             "spent_all": Ledger(suite).total(), "rows": rows}
    write_json(out / "index.json", index)
    return index


def cmd_index(args):
    pilot = "--pilot" in args
    args = [a for a in args if a != "--pilot"]
    if len(args) != 1:
        sys.exit(__doc__)
    suite, out, A, pages = load(args[0], pilot)
    index = write_index(suite, out, A, pages, pilot)
    print("INDEX: %d interviews, %d complete; %s" % (index["interviews"], index["complete"], out / "index.json"))


def cmd_standin(args):
    if len(args) != 2:
        sys.exit(__doc__)
    suite, question = Path(args[0]), Path(args[1]).read_text(encoding="utf-8")
    ledger = Ledger(suite)
    plan = PLAN.read_text(encoding="utf-8")
    model, effort = ask.front_matter(STANDIN)
    text = "## The plan (INTERVIEW-SUITE-PLAN.md)\n\n%s\n\n## The question\n\n%s" % (plan.strip(), question.strip())
    reply, cost, exact = talk.call(model, text, effort, agent=STANDIN)
    ledger.add("standin", "standin", model, effort, cost, exact)
    log = suite / "standin.md"
    n = len(re.findall(r"^## Question \d+", log.read_text(encoding="utf-8"), re.M)) + 1 if log.is_file() else 1
    if not log.is_file():
        log.write_text("# The stand-in's decisions\n\nEvery question put to the stand-in for this run (INTERVIEW-SUITE-PLAN.md section 10) and its "
                       "answer, verbatim. Each was asked with the plan before it.\n\n", encoding="utf-8")
    with open(log, "a", encoding="utf-8") as f:
        f.write("## Question %d (%s)\n\nAsked of %s at %s effort (%s), $%.4f, with INTERVIEW-SUITE-PLAN.md (sha256 `%s`) before it.\n\n"
                "### The question\n\n````\n%s\n````\n\n### The answer\n\n````\n%s\n````\n\n" % (
                    n, now(), model, effort, exact or "?", cost, sha256(plan), question.strip(), reply.strip()))
    print(reply.strip())
    print("(stand-in, $%.4f; kept as question %d in %s)" % (cost, n, log))


def hand_tenth(keys):
    """A tenth of `keys` (at least one), chosen by hash: those whose sha256 sorts first."""
    return sorted(keys, key=lambda k: sha256(k))[:max(1, round(len(keys) / 10))]


def cmd_hand(args):
    pilot = "--pilot" in args
    args = [a for a in args if a != "--pilot"]
    if len(args) != 1:
        sys.exit(__doc__)
    suite, out, A, pages = load(args[0], pilot)
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    for key in hand_tenth([r["key"] for r in index["rows"] if r["complete"]]):
        print("%s  %s" % (key, next(r["file"] for r in index["rows"] if r["key"] == key)))


def overlap(a, b):
    """Whether two short quotes share three words in a row."""
    w = lambda t: re.findall(r"[a-z']+", t.lower())
    x, y = w(a), w(b)
    return any(x[i:i + 3] == y[j:j + 3] for i in range(len(x) - 2) for j in range(len(y) - 2))


def disagree(col, mine, theirs):
    if col in ("beyond_page", "trait"):
        none_a, none_b = mine.strip().lower() == "none", theirs.strip().lower() == "none"
        if none_a != none_b:
            return True
        return col == "trait" and not none_a and not overlap(mine, theirs)
    return mine != theirs


def cmd_agree(args):
    pilot = "--pilot" in args
    args = [a for a in args if a != "--pilot"]
    if len(args) != 2:
        sys.exit(__doc__)
    suite, out, A, pages = load(args[0], pilot)
    scores = json.loads((out / "scores.json").read_text(encoding="utf-8"))["interviews"]
    hand = json.loads(Path(args[1]).read_text(encoding="utf-8"))
    counts = {c: [0, 0] for c in ROW_KEYS}
    for key, rows in hand.items():
        theirs = scores.get(key, {}).get("rows")
        if not theirs or len(theirs) != len(rows):
            print("%s: no matching scorer rows" % key)
            continue
        for mine, other in zip(rows, theirs):
            for c in ROW_KEYS:
                counts[c][1] += 1
                counts[c][0] += disagree(c, str(mine[c]), str(other[c]))
    for c, (d, n) in counts.items():
        print("%-24s %3d of %3d disagree (%.0f%%)" % (c, d, n, 100.0 * d / n if n else 0))
    return 0


def cmd_spent(args):
    if len(args) != 1:
        sys.exit(__doc__)
    by = {}
    for e in Ledger(args[0]).entries():
        by[e["what"]] = by.get(e["what"], 0) + e["cost"]
    for k, v in sorted(by.items()):
        print("%-12s $%.4f" % (k, v))
    print("%-12s $%.4f" % ("all", sum(by.values())))


def take(argv, flag):
    if flag not in argv:
        return argv, None
    i = argv.index(flag)
    if i + 1 >= len(argv):
        sys.exit("%s needs a value" % flag)
    return argv[:i] + argv[i + 2:], argv[i + 1]


def main(argv):
    commands = {"pages": cmd_pages, "run": cmd_run, "score": cmd_score, "index": cmd_index, "standin": cmd_standin, "spent": cmd_spent,
                "hand": cmd_hand, "agree": cmd_agree}
    if not argv or argv[0] not in commands:
        sys.exit(__doc__)
    return commands[argv[0]](argv[1:]) or 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
