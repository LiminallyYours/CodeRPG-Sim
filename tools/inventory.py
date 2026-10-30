#!/usr/bin/env python3
"""Personality tests for the cast after a run (PERSONALITY-TESTS-PLAN.md): the BFI-2 and the PID-5, read to each
person by a visitor from the city, in their own world, on the interview suite's frozen pages.

    inventory.py items <workbook.xlsx> <out folder>
        the statements of both forms from JW's workbook (BFI-2_and_PID-5_fillable.xlsx) into <out>/items.json; the
        statements stay out of git (both forms are licensed for research use) and are read word for word
    inventory.py pages <suite folder> <out folder> --cap <usd>
        NEUTRAL+KNOW and NEUTRAL+LATELY for the people the texts name: the suite's NEUTRAL page with the lines under
        "What I know", or each recent moment's "What you did" and "Why", put plainly as well (rules/people/plainer.md,
        the summariser's model); each checked to differ from NEUTRAL only in those lines
    inventory.py run <suite folder> <out folder> --cap <usd> [--pilot] [--workers <n>] [--texts <file>]
        the sittings, sitting number first so a stopped run is even across people and states; each a transcript of
        talk.py's form: the BFI-2 in one batch, the PID-5 in the texts' number of batches (the pilot gives its first
        sittings in one and its second in four), and once per batch, in the visitor's words, the statements missed
        (or, when none was answered, a second ask); no sitting begun past the cap, no call made past it; a stopped
        run resumes from the transcripts. The texts are copied into the out folder the first time.
    inventory.py score <suite folder> <out folder> [--pilot]
        scores.json (each sitting's domain and facet scores, by the keys of JW's score.py) and tables.txt (by state
        and person: the mean and spread over the sittings, the identical-answer rate, missed statements, refusals and
        answers given out of character)
    inventory.py spent <out folder>
"""
import concurrent.futures
import datetime
import difflib
import html
import json
import re
import shutil
import statistics
import sys
import threading
import zipfile
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "rules"))
sys.path.insert(0, str(ROOT / "tools"))
import ask  # noqa: E402
import interviews  # noqa: E402
import talk  # noqa: E402

PEOPLE = ROOT / "rules" / "people"
TEXTS = PEOPLE / "inventory.json"
PLAINER = PEOPLE / "plainer.md"
TAKER = PEOPLE / "taker.md"
HELPERS = interviews.HELPERS
STEPPED_OUT = re.compile(r"\b(an AI|AI model|language model|Claude|Anthropic|assistant|playing (him|her|them|this character))\b|\bas an AI\b", re.I)

# ---------------------------------------------------------------- the forms' keys
# Copied as data from JW's score.py (~/Documents/claude-projects/personality/score.py), which copied them from the
# forms: bfi2-form.pdf's Scoring Key; the APA PID-5 adult form's scoring page and its missing-answer rule.
BFI2_FACETS = {
    "Sociability": "1, 16R, 31R, 46", "Assertiveness": "6, 21, 36R, 51R", "Energy Level": "11R, 26R, 41, 56",
    "Compassion": "2, 17R, 32, 47R", "Respectfulness": "7, 22R, 37R, 52", "Trust": "12R, 27, 42R, 57",
    "Organization": "3R, 18, 33, 48R", "Productiveness": "8R, 23R, 38, 53", "Responsibility": "13, 28R, 43, 58R",
    "Anxiety": "4R, 19, 34, 49R", "Depression": "9R, 24R, 39, 54", "Emotional Volatility": "14, 29R, 44R, 59",
    "Intellectual Curiosity": "10, 25R, 40, 55R", "Aesthetic Sensitivity": "5R, 20, 35, 50R", "Creative Imagination": "15, 30R, 45R, 60",
}
BFI2_DOMAINS = {
    "Extraversion": "1, 6, 11R, 16R, 21, 26R, 31R, 36R, 41, 46, 51R, 56",
    "Agreeableness": "2, 7, 12R, 17R, 22R, 27, 32, 37R, 42R, 47R, 52, 57",
    "Conscientiousness": "3R, 8R, 13, 18, 23R, 28R, 33, 38, 43, 48R, 53, 58R",
    "Negative Emotionality": "4R, 9R, 14, 19, 24R, 29R, 34, 39, 44R, 49R, 54, 59",
    "Open-Mindedness": "5R, 10, 15, 20, 25R, 30R, 35, 40, 45R, 50R, 55R, 60",
}
PID5_FACETS = {
    "Anhedonia": "1, 23, 26, 30R, 124, 155R, 157, 189",
    "Anxiousness": "79, 93, 95, 96R, 109, 110, 130, 141, 174",
    "Attention Seeking": "14, 43, 74, 111, 113, 173, 191, 211",
    "Callousness": "11, 13, 19, 54, 72, 73, 90R, 153, 166, 183, 198, 200, 207, 208",
    "Deceitfulness": "41, 53, 56, 76, 126, 134, 142R, 206, 214, 218",
    "Depressivity": "27, 61, 66, 81, 86, 104, 119, 148, 151, 163, 168, 169, 178, 212",
    "Distractibility": "6, 29, 47, 68, 88, 118, 132, 144, 199",
    "Eccentricity": "5, 21, 24, 25, 33, 52, 55, 70, 71, 152, 172, 185, 205",
    "Emotional Lability": "18, 62, 102, 122, 138, 165, 181",
    "Grandiosity": "40, 65, 114, 179, 187, 197",
    "Hostility": "28, 32, 38, 85, 92, 116, 158, 170, 188, 216",
    "Impulsivity": "4, 16, 17, 22, 58R, 204",
    "Intimacy Avoidance": "89, 97R, 108, 120, 145, 203",
    "Irresponsibility": "31, 129, 156, 160, 171, 201, 210R",
    "Manipulativeness": "107, 125, 162, 180, 219",
    "Perceptual Dysregulation": "36, 37, 42, 44, 59, 77, 83, 154, 192, 193, 213, 217",
    "Perseveration": "46, 51, 60, 78, 80, 100, 121, 128, 137",
    "Restricted Affectivity": "8, 45, 84, 91, 101, 167, 184",
    "Rigid Perfectionism": "34, 49, 105, 115, 123, 135, 140, 176, 196, 220",
    "Risk Taking": "3, 7R, 35R, 39, 48, 67, 69, 87R, 98R, 112, 159, 164R, 195, 215R",
    "Separation Insecurity": "12, 50, 57, 64, 127, 149, 175",
    "Submissiveness": "9, 15, 63, 202",
    "Suspiciousness": "2, 103, 117, 131R, 133, 177R, 190",
    "Unusual Beliefs & Experiences": "94, 99, 106, 139, 143, 150, 194, 209",
    "Withdrawal": "10, 20, 75, 82, 136, 146, 147, 161, 182, 186",
}
PID5_DOMAINS = {
    "Negative Affect": ["Emotional Lability", "Anxiousness", "Separation Insecurity"],
    "Detachment": ["Withdrawal", "Anhedonia", "Intimacy Avoidance"],
    "Antagonism": ["Manipulativeness", "Deceitfulness", "Grandiosity"],
    "Disinhibition": ["Irresponsibility", "Impulsivity", "Distractibility"],
    "Psychoticism": ["Unusual Beliefs & Experiences", "Eccentricity", "Perceptual Dysregulation"],
}
COUNTS = {"bfi2": 60, "pid5": 220}


def keyed(text):
    """'1, 16R, 31R' -> [(1, False), (16, True), (31, True)]"""
    return [(int(m.group(1)), m.group(2) == "R") for m in (re.fullmatch(r"(\d+)(R?)", t.strip()) for t in text.split(","))]


def round_half_up(x):
    return float(Decimal(repr(x)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def score_bfi2(ans, items):
    """The mean of the keyed answers given (reversed: 6 - answer); None when none was given."""
    got = [(6 - ans[i]) if r else ans[i] for i, r in items if ans.get(i) is not None]
    return statistics.fmean(got) if got else None


def score_pid5_facet(ans, items):
    """The APA rule: more than a quarter of a facet's statements unanswered, no score; otherwise the raw score
    prorated (raw x items / answered, rounded half up) over the number of statements."""
    n = len(items)
    got = [(3 - ans[i]) if r else ans[i] for i, r in items if ans.get(i) is not None]
    if len(got) == n:
        return sum(got) / n
    if n - len(got) > 0.25 * n:
        return None
    return round_half_up(sum(got) * n / len(got)) / n


def scores(answers):
    """{"BFI-2 <domain or facet>": value, "PID-5 <domain or facet>": value} for one sitting's answers."""
    out = {}
    for name, items in list(BFI2_DOMAINS.items()) + list(BFI2_FACETS.items()):
        out["BFI-2 " + name] = score_bfi2(answers["bfi2"], keyed(items))
    for name, items in PID5_FACETS.items():
        out["PID-5 " + name] = score_pid5_facet(answers["pid5"], keyed(items))
    for name, facets in PID5_DOMAINS.items():
        parts = [out["PID-5 " + f] for f in facets]
        out["PID-5 " + name] = None if None in parts else sum(parts) / 3
    return out


# ---------------------------------------------------------------- the texts, the statements and the answers

def texts(out, source=None):
    """The out folder's own copy of the texts, made from `source` (default rules/people/inventory.json) the first time."""
    mine = Path(out) / "inventory.json"
    if not mine.is_file():
        Path(out).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(source) if source else TEXTS, mine)
    elif source and Path(source).read_bytes() != mine.read_bytes():
        sys.exit("REFUSED: %s already has its texts, and %s differs from them" % (out, source))
    return json.loads(mine.read_text(encoding="utf-8"))


def statements(items, test, numbers):
    return "\n".join("%d. %s" % (n, items[test]["items"][n - 1]) for n in numbers)


def steps(T, batches):
    """A sitting's batches: (test, first statement, last statement), the BFI-2 whole, the PID-5 in `batches`."""
    size = -(-COUNTS["pid5"] // batches)
    return [("bfi2", 1, COUNTS["bfi2"])] + [("pid5", a, min(a + size - 1, COUNTS["pid5"])) for a in range(1, COUNTS["pid5"] + 1, size)]


def line_of(T, items, step, i):
    test, a, b = step
    words = T[test]["open"] if test == "bfi2" or a == 1 else T["pid5"]["next"]
    return words + "\n\n" + statements(items, test, range(a, b + 1))


NUMBERED = re.compile(r"^[\s*_\"'`(\[-]*(\d{1,3})[*_\"'`)\]]*\s*[:.)\-–—]\s*(.*)$")


def parse_answers(text, phrases, values, numbers):
    """{statement: value} for the numbered lines of `text` that begin with one of `phrases` (the first answer to a
    statement counts); statements outside `numbers` are ignored."""
    got, wanted = {}, set(numbers)
    by_length = sorted(zip(phrases, values), key=lambda pv: -len(pv[0]))
    for line in (text or "").splitlines():
        m = NUMBERED.match(line)
        if not m or int(m.group(1)) not in wanted or int(m.group(1)) in got:
            continue
        rest = re.sub(r"^[\s*_\"'`“‘]+", "", m.group(2)).lower()
        for phrase, value in by_length:
            if rest.startswith(phrase):
                got[int(m.group(1))] = value
                break
    return got


# ---------------------------------------------------------------- the statements from JW's workbook

def cmd_items(args):
    if len(args) != 2:
        sys.exit(__doc__)
    z = zipfile.ZipFile(args[0])
    out = {"source": str(Path(args[0]).resolve())}
    for sheet, test in (("sheet1", "bfi2"), ("sheet2", "pid5")):
        rows = {}
        for r in re.findall(r"<row [^>]*>(.*?)</row>", z.read("xl/worksheets/%s.xml" % sheet).decode("utf-8"), re.S):
            cells = {re.sub(r"\d+", "", c): html.unescape(re.sub(r"<[^>]+>", "", v)).strip()
                     for c, v in re.findall(r'<c r="([A-Z]+\d+)"[^>]*>(.*?)</c>', r, re.S)}
            if cells.get("A", "").isdigit() and cells.get("B") and "C" in cells:
                rows[int(cells["A"])] = cells["B"]
        if sorted(rows) != list(range(1, COUNTS[test] + 1)):
            sys.exit("REFUSED: %s's %s has %d numbered statements, not %d" % (args[0], sheet, len(rows), COUNTS[test]))
        out[test] = {"items": [rows[n] for n in range(1, COUNTS[test] + 1)]}
    forbidden = sorted({m.group(0).lower() for t in ("bfi2", "pid5") for s in out[t]["items"] for m in interviews.FORBIDDEN.finditer(s)})
    out["forbidden_words"] = forbidden  # the forms' own words, read as they stand (the plan, section 2)
    Path(args[1]).mkdir(parents=True, exist_ok=True)
    interviews.write_json(Path(args[1]) / "items.json", out)
    print("ITEMS: BFI-2 60, PID-5 220 into %s; words on the FORBIDDEN list in them, read as they stand: %s"
          % (Path(args[1]) / "items.json", ", ".join(forbidden) or "none"))
    return 0


# ---------------------------------------------------------------- NEUTRAL+KNOW and NEUTRAL+LATELY

def section_lines(lines, heading, prefixes):
    """Indexes of the lines under `heading` (to the next "## ") that begin with one of `prefixes`."""
    found, inside = [], False
    for i, line in enumerate(lines):
        if line.startswith("## "):
            inside = line.strip() == heading
            continue
        if inside and line.startswith(tuple(prefixes)):
            found.append(i)
    return found


MOST_ALIKE = 0.6  # the words a plain line may share with the line given (difflib's ratio over words, on average)
VARIANTS = {"neutral-know": ("## What I know", ("- ",)), "neutral-lately": ("## Lately", ("What you did: ", "Why: "))}


def cmd_pages(args):
    args, cap = interviews.take(args, "--cap")
    if len(args) != 2 or cap is None:
        sys.exit(__doc__)
    suite, out = Path(args[0]), Path(args[1])
    T = texts(out)
    pages = json.loads((suite / "pages" / "pages.json").read_text(encoding="utf-8"))
    mine = out / "pages" / "pages.json"
    if mine.is_file():
        sys.exit("REFUSED: %s exists; the pages are made once" % mine)
    ledger = interviews.Ledger(out)
    ledger.stop_line = ledger.total() + float(cap)
    made = {"from": str(suite / "pages" / "pages.json"), "pages": {}}
    for state, (heading, prefixes) in VARIANTS.items():
        for pid in T["states"][state]["people"]:
            src = pages["pages"]["neutral"][pid]
            text = (suite / src["file"]).read_text(encoding="utf-8")
            lines = text.split("\n")
            where = section_lines(lines, heading, prefixes)
            if not where:
                sys.exit("REFUSED: %s's NEUTRAL page has no lines to put plainly under %r" % (pid, heading))
            heads = [next(p for p in prefixes if lines[i].startswith(p)) for i in where]
            given = [lines[i][len(h):] for i, h in zip(where, heads)]
            plain, why = None, None
            for attempt in (1, 2, 3):
                ledger.allow()
                prompt = json.dumps(given, ensure_ascii=False) + ("" if why is None else "\n\nYour last reply was not accepted (%s)." % why)
                reply, cost, exact = talk.call(HELPERS[0], prompt, HELPERS[1], agent=PLAINER)
                ledger.add("plain", "%s/%s" % (state, pid), HELPERS[0], HELPERS[1], cost, exact)
                data = interviews.json_of(reply)
                got = data.get("passages") if isinstance(data, dict) else None
                if not isinstance(got, list) or len(got) != len(given) or not all(isinstance(p, str) and p.strip() and "\n" not in p.strip() for p in got):
                    why = "not %d passages, one line each, as JSON" % len(given)
                    continue
                ratio = sum(len(p) for p in got) / sum(len(p) for p in given)
                if not 0.8 <= ratio <= 1.2:
                    why = "%.0f%% of the length given, not within a fifth" % (100 * ratio)
                    continue
                same = statistics.fmean(difflib.SequenceMatcher(None, g.split(), p.split()).ratio() for g, p in zip(given, got))
                if same > MOST_ALIKE:
                    why = "%.0f%% of the wording kept; put it in your own plain words" % (100 * same)
                    continue
                plain = [p.strip() for p in got]
                break
            if plain is None:
                sys.exit("REFUSED: %s's %s lines weren't put plainly in the form asked for, three times (%s)" % (pid, state, why))
            new = list(lines)
            for i, h, p in zip(where, heads, plain):
                new[i] = h + p
            changed = [i for i, (a, b) in enumerate(zip(lines, new)) if a != b]
            if len(new) != len(lines) or not set(changed) <= set(where):
                sys.exit("REFUSED: %s's %s page differs from NEUTRAL outside the lines put plainly" % (pid, state))
            page = "\n".join(new)
            name = "pages/%s-%s.txt" % (state, pid)
            (out / "pages").mkdir(parents=True, exist_ok=True)
            (out / name).write_text(page, encoding="utf-8")
            interviews.write_json(out / "pages" / ("%s-%s.plain.json" % (state, pid)), {"given": given, "plain": plain})
            made["pages"].setdefault(state, {})[pid] = {"file": name, "sha256": interviews.sha256(page), "from_sha256": src["sha256"],
                                                       "lines": len(where), "ratio": round(sum(map(len, plain)) / sum(map(len, given)), 3),
                                                       "wording_kept": round(same, 3)}
            print("%s/%s: %d lines put plainly (%.0f%% of their length, %.0f%% of the wording kept)" % (
                state, pid, len(where), 100 * made["pages"][state][pid]["ratio"], 100 * same))
    interviews.write_json(mine, made)
    print("PAGES: %s; $%.2f spent in all" % (mine, ledger.total()))
    return 0


# ---------------------------------------------------------------- the sittings

def plan_of(T, people, pilot=False):
    """Every sitting, sitting number first, then state, then person in the cast's order."""
    if pilot:
        P = T["pilot"]
        return [{"key": "%s/%s/%02d" % (st, pid, n), "state": st, "person": pid, "n": n, "batches": 1 if n == 1 else 4}
                for n in range(1, P["sittings"] + 1) for st in P["states"] for pid in people if pid in P["people"]]
    out = []
    most = max(s["sittings"] for s in T["states"].values())
    for n in range(1, most + 1):
        for st, s in T["states"].items():
            who = people if s["people"] == "all" else s["people"]
            out += [{"key": "%s/%s/%02d" % (st, pid, n), "state": st, "person": pid, "n": n, "batches": T["pid5_batches"]}
                    for pid in who if n <= s["sittings"]]
    return out


class Sitter:
    def __init__(self, suite, out, T, ledger, workers, pilot=False):
        self.suite, self.out, self.T, self.ledger, self.workers = Path(suite), Path(out), T, ledger, workers
        self.dir = self.out / "pilot" if pilot else self.out
        self.pages = json.loads((self.suite / "pages" / "pages.json").read_text(encoding="utf-8"))
        own = self.out / "pages" / "pages.json"
        self.own = json.loads(own.read_text(encoding="utf-8")) if own.is_file() else {"pages": {}}
        self.items = json.loads((self.out / "items.json").read_text(encoding="utf-8"))
        self.A = interviews.approaches(self.suite)
        self.effort = ask.front_matter()[1]
        self.lock = threading.Lock()

    def path(self, s):
        return self.dir / (s["key"] + ".md")

    def page(self, s):
        """(file, text) of the sitting's page, or (None, None) for the model's baseline."""
        st = self.T["states"][s["state"]]["page"]
        if st is None:
            return None, None
        entry = (self.own["pages"].get(st) or {}).get(s["person"]) or self.pages["pages"].get(st, {}).get(s["person"])
        if entry is None:
            raise SystemExit("REFUSED: no %s page for %s (inventory.py pages first)" % (st, s["person"]))
        base = self.out if st in VARIANTS else self.suite
        text = (base / entry["file"]).read_text(encoding="utf-8")
        if interviews.sha256(text) != entry["sha256"]:
            raise SystemExit("REFUSED: %s isn't the page recorded" % (base / entry["file"]))
        return base / entry["file"], text

    def model(self, s):
        return "opus" if s["person"] == "opus" else self.pages["people"][s["person"]]["model"]

    def meet(self, s, text):
        if self.T["states"][s["state"]]["page"] == "start":
            return self.A["meet"]["start"]
        return self.A["meet"]["end"].replace("{place}", interviews.place_of(text))

    def records(self, s):
        return talk.read(self.path(s))[1]

    def asked(self, s, i):
        return [r for r in self.records(s) if r.get("step") == i]

    def answered(self, s, i, step):
        test, a, b = step
        got = {}
        for r in self.asked(s, i):
            for n, v in parse_answers(r.get("say"), self.T[test]["phrases"], self.T[test]["values"], range(a, b + 1)).items():
                got.setdefault(n, v)
        return got

    def status(self, s):
        """'done', 'incomplete' (a reply out of form twice) or 'open'."""
        recs = self.records(s)
        if any(r.get("say") is None for r in recs):
            return "incomplete"
        for i, step in enumerate(steps(self.T, s["batches"])):
            asks = self.asked(s, i)
            if not asks or (len(asks) == 1 and len(self.answered(s, i, step)) < step[2] - step[1] + 1):
                return "open"
        return "done"

    def ask(self, s, i, line, kind):
        self.ledger.allow()
        file, text = self.page(s)
        if file is None:
            return self.ask_baseline(s, i, line, kind)
        rec = talk.talk(s["person"], file, self.meet(s, text), self.path(s), line, self.model(s), self.effort,
                        extra={"step": i, "ask": kind}, header={"name": self.pages["people"][s["person"]]["name"], "state": s["state"]})
        self.ledger.add("person", s["key"], self.model(s), self.effort, rec["cost"], rec.get("exact"))
        return rec

    def ask_baseline(self, s, i, line, kind):
        """The model as itself: the statements with plain instructions, each batch on its own, no page, no visitor."""
        test = steps(self.T, s["batches"])[i][0]
        phrases = self.T[test]["phrases"]
        head = self.T["baseline"].format(phrases=", ".join(phrases), example="1: %s" % phrases[1])
        body = line.split("\n\n", 1)[1] if "\n\n" in line else line
        reply, cost, exact = talk.call("opus", head + "\n\n" + body, self.effort, agent=TAKER)
        path = self.path(s)
        if not path.is_file():
            talk.start(path, {"person": "opus", "title": "The model as itself (baseline)", "page": "(none)", "page_sha256": "", "meet": "(none)",
                              "model": "opus", "effort": self.effort, "texts": {"taker": interviews.sha256(TAKER.read_text())[:8]},
                              "started": interviews.now(), "state": s["state"]})
        rec = {"kind": "line", "n": len(self.records(s)) + 1, "line": body if kind == "main" else line, "model": "opus", "effort": self.effort,
               "t": interviews.now(), "say": reply.strip(), "thought": "", "cost": round(cost, 6), "exact": exact, "step": i, "ask": kind}
        talk.append(path, rec, talk.exchange_text(rec))
        self.ledger.add("person", s["key"], "opus", self.effort, cost, exact)
        return rec

    def sit(self, s):
        """One sitting, from where its transcript ended: each batch, then once the statements missed, or a second
        ask when none was answered."""
        try:
            for i, step in enumerate(steps(self.T, s["batches"])):
                test, a, b = step
                if not self.asked(s, i):
                    rec = self.ask(s, i, line_of(self.T, self.items, step, i), "main")
                    if rec["say"] is None:
                        return "incomplete"
                got = self.answered(s, i, step)
                missed = [n for n in range(a, b + 1) if n not in got]
                if missed and len(self.asked(s, i)) == 1:
                    words = self.T["missing"].format(numbers=", ".join(map(str, missed))) if got else self.T["again"]
                    if self.T["states"][s["state"]]["page"] is None:  # the baseline hears only the statements again
                        words += "\n\n" + statements(self.items, test, missed)
                    if self.ask(s, i, words, "missing" if got else "again")["say"] is None:
                        return "incomplete"
        except talk.Refused:
            return "incomplete"
        return "done"

    def estimate(self, s):
        page = self.T["states"][s["state"]]["page"]
        paid = [e for e in self.ledger.entries() if e["what"] == "person"]
        costs = [e["cost"] for e in paid if e["key"].split("/")[0] == s["state"]] or [e["cost"] for e in paid]
        each = statistics.fmean(costs) if costs else (0.1 if page in ("start", None) else 0.3)  # a state not yet tried
        return each * (len(steps(self.T, s["batches"])) + 1)

    def run(self, order, cap):
        self.ledger.stop_line = self.ledger.total() + cap
        todo = [s for s in order if self.status(s) == "open"]
        for s in todo:
            self.page(s)  # every page there and as recorded before anything is asked
        print("RUN: %d sittings to finish, cap $%.2f (spent so far $%.2f, stop at $%.2f)" % (
            len(todo), cap, self.ledger.total(), self.ledger.stop_line), flush=True)
        stopped, running, results = None, {}, {}
        with concurrent.futures.ThreadPoolExecutor(self.workers) as pool:
            for s in todo:
                while len(running) >= self.workers:
                    done, _ = concurrent.futures.wait(list(running), return_when=concurrent.futures.FIRST_COMPLETED)
                    for f in done:
                        self.report(running.pop(f), f, results)
                under_way = sum(self.estimate(x) for x in running.values())
                if self.ledger.total() + under_way + self.estimate(s) > self.ledger.stop_line:
                    stopped = s["key"]
                    break
                running[pool.submit(self.sit, s)] = s
            for f in concurrent.futures.as_completed(list(running)):
                self.report(running[f], f, results)
        left = [s for s in order if self.status(s) == "open"]
        print("RUN %s: %d sittings finished, %d not; $%.2f spent in all" % (
            "STOPPED at the cap" if left else "DONE", sum(v != "stopped" for v in results.values()), len(left), self.ledger.total()), flush=True)
        return 3 if left else 0

    def report(self, s, future, results):
        try:
            got = future.result()
        except interviews.Stop:
            got = "stopped"
        except ask.Failed as e:  # the service, not the sitting: it stays open and a later run takes it up
            got = "failed (%s)" % str(e).splitlines()[0][:60]
        results[s["key"]] = got
        with self.lock:
            print("%s %-28s %-10s $%.2f spent" % (datetime.datetime.now().strftime("%H:%M:%S"), s["key"], got, self.ledger.total()), flush=True)


# ---------------------------------------------------------------- scoring

def people_of(suite):
    return list(json.loads((Path(suite) / "pages" / "pages.json").read_text(encoding="utf-8"))["people"])


def cmd_run(args):
    args, cap = interviews.take(args, "--cap")
    args, workers = interviews.take(args, "--workers")
    args, source = interviews.take(args, "--texts")
    pilot = "--pilot" in args
    args = [a for a in args if a != "--pilot"]
    if len(args) != 2 or cap is None:
        sys.exit(__doc__)
    T = texts(args[1], source)
    sitter = Sitter(args[0], args[1], T, interviews.Ledger(args[1]), int(workers or 6), pilot)
    return sitter.run(plan_of(T, people_of(args[0]), pilot), float(cap))


def sitting_answers(sitter, s):
    out, notes = {"bfi2": {}, "pid5": {}}, {"missed": 0, "refused_batches": 0, "out_of_character": 0, "asks": 0}
    for i, step in enumerate(steps(sitter.T, s["batches"])):
        got = sitter.answered(s, i, step)
        out[step[0]].update(got)
        notes["missed"] += (step[2] - step[1] + 1) - len(got)
        notes["refused_batches"] += not got
    for r in sitter.records(s):
        notes["asks"] += 1
        if s["person"] != "opus" and STEPPED_OUT.search("%s %s" % (r.get("say") or "", r.get("thought") or "")):
            notes["out_of_character"] += 1
    return out, notes


def identical_rate(answer_sets, test):
    """The mean, over statements, of the share of sittings that gave the statement's most common answer."""
    shares = []
    for n in range(1, COUNTS[test] + 1):
        given = [a[test][n] for a in answer_sets if n in a[test]]
        if len(given) > 1:
            shares.append(max(given.count(v) for v in set(given)) / len(given))
    return statistics.fmean(shares) if shares else None


def cmd_score(args):
    pilot = "--pilot" in args
    args = [a for a in args if a != "--pilot"]
    if len(args) != 2:
        sys.exit(__doc__)
    T = texts(args[1])
    sitter = Sitter(args[0], args[1], T, interviews.Ledger(args[1]), 1, pilot)
    order = plan_of(T, people_of(args[0]), pilot)
    rows, groups = {}, {}
    for s in order:
        if not sitter.path(s).is_file():
            continue
        answers, notes = sitting_answers(sitter, s)
        rows[s["key"]] = {"state": s["state"], "person": s["person"], "n": s["n"], "status": sitter.status(s), "batches": s["batches"],
                          "scores": scores(answers), **notes}
        groups.setdefault((s["state"], s["person"]), []).append((answers, rows[s["key"]]))
    interviews.write_json(sitter.dir / "scores.json", {"sittings": rows})
    domains = ["BFI-2 " + d for d in BFI2_DOMAINS] + ["PID-5 " + d for d in PID5_DOMAINS]
    short = {"Extraversion": "E", "Agreeableness": "A", "Conscientiousness": "C", "Negative Emotionality": "N", "Open-Mindedness": "O",
             "Negative Affect": "NA", "Detachment": "Det", "Antagonism": "Ant", "Disinhibition": "Dis", "Psychoticism": "Psy"}
    lines = ["Mean (SD) over the sittings; BFI-2 1-5, PID-5 0-3. same = identical-answer rate (BFI-2 / PID-5).",
             "%-15s %-10s %3s  %s  %s" % ("state", "person", "n", "  ".join("%-11s" % short[d.split(" ", 1)[1]] for d in domains), "same       missed refused ooc")]
    for (st, pid), got in groups.items():
        vals = []
        for d in domains:
            xs = [r["scores"][d] for _, r in got if r["scores"][d] is not None]
            vals.append("%-11s" % ("%.2f (%.2f)" % (statistics.fmean(xs), statistics.pstdev(xs)) if xs else "-"))
        same = [identical_rate([a for a, _ in got], t) for t in ("bfi2", "pid5")]
        lines.append("%-15s %-10s %3d  %s  %-10s %6d %7d %3d" % (
            st, pid, len(got), "  ".join(vals), "/".join("%.2f" % x if x is not None else "-" for x in same),
            sum(r["missed"] for _, r in got), sum(r["refused_batches"] for _, r in got), sum(r["out_of_character"] for _, r in got)))
    (sitter.dir / "tables.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("SCORED: %d sittings; %s" % (len(rows), sitter.dir / "scores.json"))
    return 0


def cmd_spent(args):
    return interviews.cmd_spent(args)


def main(argv):
    commands = {"items": cmd_items, "pages": cmd_pages, "run": cmd_run, "score": cmd_score, "spent": cmd_spent}
    if not argv or argv[0] not in commands:
        sys.exit(__doc__)
    return commands[argv[0]](argv[1:]) or 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
